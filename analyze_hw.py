#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_hw.py —— 已有 STM32 工程硬件配置静态提取
====================================================
方案 B 的确定性部分：从已有工程源码提取硬件配置，输出 hardware.yaml /
pin_usage.md 草稿 + "待 AI 补充清单"（静态提取不到、需 AI 读代码确认的点）。

提取内容：
  - MCU 型号（uvprojx <Device> / hal_conf.h 家族 / main.h HAL 头）
  - 系统时钟（main.c SystemClock_Config：HSI/HSE → PLL → SYSCLK/HCLK/PCLK1/PCLK2）
  - GPIO 引脚（main.h #define X_Pin / X_GPIO_Port + gpio.c 初始化模式）
  - 外设模块（hal_conf.h 启用的 HAL_*_MODULE_ENABLED）
  - 使用中的外设（Core/Src/*.c 里的 MX_ 初始化调用 + USER CODE 里的 HAL 调用）
  - 中断（stm32f1xx_it.c 的 handler 列表）
  - 功能推断（main() 主循环的典型调用）

用法：
  python analyze_hw.py <工程目录> [--json]
  输出到 <工程目录>/hardware.yaml.draft + pin_usage.md.draft + ai_review_notes.md
  --json 只打印分析结果 JSON（供脚本调用方解析）
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ===================== 常量 =====================
# 各家族 HSI 频率（MHz）：F1/F3=8MHz，H7=64MHz，其余大多 16MHz
FAMILY_HSI_MHZ = {
    "F1": 8.0, "F0": 8.0, "F3": 8.0,
    "F2": 16.0, "F4": 16.0, "F7": 16.0,
    "L0": 16.0, "L1": 16.0, "L4": 16.0, "L5": 16.0,
    "G0": 16.0, "G4": 16.0, "U5": 16.0,
    "H7": 64.0,
    "WB": 16.0, "WL": 16.0, "WBA": 16.0, "N6": 16.0,
}
FAMILY_HSE_MHZ = {"F1": 8.0, "F4": 25.0}

# GPIO_PIN_x → 引脚号
PIN_NUM = {f"GPIO_PIN_{i}": i for i in range(16)}
GPIO_PORT_RE = re.compile(r"GPIO([A-Z])$")

# hal_conf 启用行（re.M：^ 匹配每行开头）
HAL_MODULE_RE = re.compile(r"^\s*#define\s+(HAL_\w+_MODULE_ENABLED)\b", re.M)
# main.h 引脚宏：#define LED1_Pin GPIO_PIN_10 / #define LED1_GPIO_Port GPIOA
PIN_MACRO_RE = re.compile(r'#define\s+(\w+)_Pin\s+GPIO_PIN_(\d+)')
PORT_MACRO_RE = re.compile(r'#define\s+(\w+)_GPIO_Port\s+GPIO([A-Z])')
# gpio.c 初始化
GPIO_INIT_RE = re.compile(r"HAL_GPIO_Init\((\w+),")
GPIO_MODE_RE = re.compile(r"GPIO_InitStruct\.Mode\s*=\s*(GPIO_MODE_\w+)")
GPIO_PULL_RE = re.compile(r"GPIO_InitStruct\.Pull\s*=\s*(GPIO_\w+)")
GPIO_SPEED_RE = re.compile(r"GPIO_InitStruct\.Speed\s*=\s*(GPIO_SPEED_\w+)")
GPIO_WRITE_RE = re.compile(r"HAL_GPIO_WritePin\((\w+),\s*(\w+),\s*(GPIO_PIN_\w+)\)")
# SPL 风格 GPIO（无宏名，直接引脚号）：GPIO_Init(GPIOB, &GPIO_InitStructure)
# 注意：SPL 标准写法是 GPIO_InitStructure（多 "ure"），兼容 GPIO_InitStruct（HAL 命名）
SPL_GPIO_PINS_RE = re.compile(r"GPIO_InitStruct(?:ure)?\.GPIO_Pin\s*=\s*([^;]+);")
SPL_GPIO_MODE_RE = re.compile(r"GPIO_InitStruct(?:ure)?\.GPIO_Mode\s*=\s*(GPIO_Mode_\w+)")
SPL_GPIO_INIT_RE = re.compile(r"GPIO_Init\(GPIO([A-Z]),\s*&GPIO_InitStruct(?:ure)?\)")
SPL_GPIO_PIN_BIT_RE = re.compile(r"GPIO_Pin_(\d+)")
SPL_GPIO_OTYPE_RE = re.compile(r"GPIO_InitStruct(?:ure)?\.GPIO_OType\s*=\s*(GPIO_OType_\w+)")
SPL_GPIO_SPEED_RE = re.compile(r"GPIO_InitStruct(?:ure)?\.GPIO_Speed\s*=\s*(GPIO_Speed_\w+)")
SPL_GPIO_PUPD_RE = re.compile(r"GPIO_InitStruct(?:ure)?\.GPIO_PuPd\s*=\s*(GPIO_PuPd_\w+)")
# 时钟
RCC_OSC_RE = re.compile(r"RCC_OscInitStruct\.OscillatorType\s*=\s*(RCC_OSCILLATORTYPE_\w+)")
HSI_STATE_RE = re.compile(r"RCC_OscInitStruct\.HSIState\s*=\s*(RCC_HSI_\w+)")
HSE_STATE_RE = re.compile(r"RCC_OscInitStruct\.HSEState\s*=\s*(RCC_HSE_\w+)")
PLL_SRC_RE = re.compile(r"RCC_OscInitStruct\.PLL\.PLLSource\s*=\s*(RCC_PLLSOURCE_\w+)")
PLL_MUL_RE = re.compile(r"RCC_OscInitStruct\.PLL\.PLLMUL\s*=\s*(RCC_PLL_MUL\w+)")
SYSCLK_SRC_RE = re.compile(r"RCC_ClkInitStruct\.SYSCLKSource\s*=\s*(RCC_SYSCLKSOURCE_\w+)")
AHB_DIV_RE = re.compile(r"RCC_ClkInitStruct\.AHBCLKDivider\s*=\s*(RCC_SYSCLK_DIV\w+)")
APB1_DIV_RE = re.compile(r"RCC_ClkInitStruct\.APB1CLKDivider\s*=\s*(RCC_HCLK_DIV\w+)")
APB2_DIV_RE = re.compile(r"RCC_ClkInitStruct\.APB2CLKDivider\s*=\s*(RCC_HCLK_DIV\w+)")
FLASH_LAT_RE = re.compile(r"FLASH_LATENCY_(\d)")
# 外设初始化调用（MX_xxx_Init / HAL_xxx_Init）
MX_INIT_RE = re.compile(r"MX_(\w+?)_Init\(\)")
HAL_INIT_RE = re.compile(r"HAL_(\w+?)_Init\(&")
# 主循环行为
WHILE_RE = re.compile(r"while\s*\(\s*1\s*\)")
TOGGLE_RE = re.compile(r"HAL_GPIO_TogglePin\((\w+),\s*(\w+)\)")
DELAY_RE = re.compile(r"HAL_Delay\((\d+)\)")


# ===================== 提取 =====================
# 工程内排除的库/系统文件前缀（SPL 库 stm32f10x_*.c、HAL 驱动、CMSIS、启动文件等）
LIB_FILE_PREFIXES = (
    "stm32f0xx_", "stm32f1xx_", "stm32f2xx_", "stm32f3xx_", "stm32f4xx_",
    "stm32f7xx_", "stm32l0xx_", "stm32l1xx_", "stm32l4xx_", "stm32g0xx_",
    "stm32g4xx_", "stm32h7xx_", "stm32wbxx_", "stm32wlxx_",
    "system_", "core_", "startup_",
)


def find_files(root: Path):
    """定位工程关键文件，兼容任意目录结构（HAL/SPL/各种变体）。

    策略：
    - uvprojx 用 rglob 找（任意层级）
    - main.c 用 rglob 找（SPL 工程目录名千变万化：USER/User/user/APP/BSP…）
    - 源码文件集合 = 工程内所有 .c（排除库/系统前缀），供 GPIO/外设扫描
    """
    root = Path(root)
    # uvprojx：任意层级
    mdk = None
    for f in root.rglob("*.uvprojx"):
        if f.stat().st_size > 0:
            mdk = f
            break

    # main.c：全局搜（排除库目录）。SPL/HAL 都必有 main.c
    main_c = None
    for f in root.rglob("main.c"):
        rel = f.relative_to(root).as_posix().lower()
        if "\\" in str(f) and any(x in rel for x in ("/lib/", "/fwlib/", "/drivers/", "/cmsis/", "/library/")):
            continue
        main_c = f
        break

    # main.h：与 main.c 同目录优先，否则全局搜
    main_h = None
    if main_c:
        cand = main_c.parent / "main.h"
        if cand.exists():
            main_h = cand
    if not main_h:
        for f in root.rglob("main.h"):
            main_h = f
            break

    # hal_conf / conf：全局搜
    hal_conf = None
    for f in root.rglob("*hal_conf.h"):
        hal_conf = f
        break
    if not hal_conf:
        for f in root.rglob("*_conf.h"):
            if "stm32" in f.name.lower():
                hal_conf = f
                break

    # system_stm32fxxx.c：全局搜
    system_c = None
    for f in root.rglob("system_stm32f*.c"):
        system_c = f
        break

    # 工程类型：有 Core/Src 且含 gpio.c 视为 HAL；否则 SPL
    core_src = root / "Core" / "Src"
    is_hal = (core_src / "main.c").exists() or (root / "Core" / "Inc").exists()

    # 源码文件集合：工程内所有 .c（排除库/系统/启动文件），供 GPIO 与行为扫描
    src_files = []
    for f in root.rglob("*.c"):
        name = f.stem.lower()
        if name.startswith(LIB_FILE_PREFIXES):
            continue
        if name in ("main", "delay", "sys"):
            continue
        rel = f.relative_to(root).as_posix().lower()
        if any(x in rel for x in ("/lib/", "/fwlib/", "/drivers/", "/cmsis/", "/library/", "/readme")):
            continue
        src_files.append(f)

    return {
        "is_hal": is_hal,
        "main_c": main_c,
        "gpio_c": next((f for f in src_files if f.stem.lower() == "gpio"), None),
        "main_h": main_h,
        "hal_conf": hal_conf,
        "system_c": system_c,
        "uvprojx": mdk,
        "src_files": src_files,       # 工程源码 .c（非库）
        "root": root,
    }


def read_text(p: Path) -> str:
    """读文件：UTF-8 优先，失败回退 GBK（传统 Keil 工程常见 ANSI/GBK 编码）。"""
    if not p or not p.exists():
        return ""
    raw = p.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("utf-8", errors="replace")


def extract_mcu(files: dict) -> dict:
    """从 uvprojx + hal_conf + main.h 推断 MCU。"""
    mcu = {"device": None, "family": None, "ram_kb": None, "flash_kb": None}
    if files["uvprojx"]:
        t = read_text(files["uvprojx"])
        m = re.search(r"<Device>([^<]+)</Device>", t)
        if m:
            mcu["device"] = m.group(1).strip()
        # 内存大小：兼容三种 uvprojx 格式
        # 1) IRAM(0x20000000-0x20004FFF) 连字符（地址范围）
        # 2) IRAM(0x20000000,0x00018000) 逗号（起始,大小）
        # 3) <IRAM>0x20000000 0x18000</IRAM> XML（起始 大小）
        m = re.search(r"IRAM\(0x(\w+)(?:-|,)(?:0x)?(\w+)\)", t)
        if m:
            start = int(m.group(1), 16)
            size = int(m.group(2), 16)
            mcu["ram_kb"] = (size - start + 1) // 1024 if size > start else size // 1024
        else:
            m = re.search(r"<IRAM>\s*\S+\s+(0x\w+)</IRAM>", t)
            if m:
                mcu["ram_kb"] = int(m.group(1), 16) // 1024
        m = re.search(r"IROM\(0x(\w+)(?:-|,)(?:0x)?(\w+)\)", t)
        if m:
            start = int(m.group(1), 16)
            size = int(m.group(2), 16)
            mcu["flash_kb"] = (size - start + 1) // 1024 if size > start else size // 1024
        else:
            m = re.search(r"<IROM>\s*\S+\s+(0x\w+)</IROM>", t)
            if m:
                mcu["flash_kb"] = int(m.group(1), 16) // 1024
    if files["hal_conf"]:
        t = read_text(files["hal_conf"])
        # HAL: stm32f1xx_hal_conf.h / stm32g4xx_hal_conf.h → F1/G4
        # SPL: stm32f4xx_conf.h → F4
        # 注意顺序：先匹配 *_hal_conf.h（hal 在前），再 *_conf.h
        m = re.search(r"stm32f(\w+)_hal_conf\.h", t) or re.search(r"stm32f(\w+)_conf\.h", t)
        if m:
            raw = m.group(1).lower()
            fam_map = {"1xx": "F1", "2xx": "F2", "3xx": "F3", "4xx": "F4",
                       "7xx": "F7", "0xx": "F0", "l0xx": "L0", "l1xx": "L1",
                       "l4xx": "L4", "l5xx": "L5", "g0xx": "G0", "g4xx": "G4",
                       "h7xx": "H7", "wbxx": "WB", "wlxx": "WL"}
            mcu["family"] = fam_map.get(raw, raw.upper())
    if files["main_h"]:
        t = read_text(files["main_h"])
        m = re.search(r'#include\s+"stm32f(\w+)_hal_conf\.h"', t) or \
            re.search(r'#include\s+"stm32f(\w+)_conf\.h"', t)
        if m and not mcu["family"]:
            raw = m.group(1).lower()
            fam_map = {"1xx": "F1", "2xx": "F2", "3xx": "F3", "4xx": "F4",
                       "7xx": "F7", "0xx": "F0", "l0xx": "L0", "l1xx": "L1",
                       "l4xx": "L4", "l5xx": "L5", "g0xx": "G0", "g4xx": "G4",
                       "h7xx": "H7", "wbxx": "WB", "wlxx": "WL"}
            mcu["family"] = fam_map.get(raw, raw.upper())
    return mcu


def extract_pins(files: dict) -> dict:
    """提取 GPIO 引脚宏 + 初始化模式。返回 {port_pin: {name, mode, pull, speed, init_level}}。"""
    pins = {}
    macros = {}  # name → {"port": "A", "num": 10}
    if files["main_h"]:
        t = read_text(files["main_h"])
        for name, num in PIN_MACRO_RE.findall(t):
            macros.setdefault(name, {})["num"] = int(num)
        for name, port in PORT_MACRO_RE.findall(t):
            macros.setdefault(name, {})["port"] = port
    if files["gpio_c"]:
        t = read_text(files["gpio_c"])
        # 每个引脚配置块：从 "Configure GPIO pin" 注释到 HAL_GPIO_Init 调用
        blocks = re.split(r"(?=/?\*.*Configure GPIO pin|\n\s*HAL_GPIO_Init\()", t)
        # 更稳的方式：按 HAL_GPIO_Init 位置向前取最近的 Mode 配置段
        for m in GPIO_INIT_RE.finditer(t):
            port_name = m.group(1)  # 如 LED1_GPIO_Port
            # 取该调用前 800 字符内的 Mode/Pull/Speed 配置
            head = t[max(0, m.start() - 800):m.start()]
            mode = GPIO_MODE_RE.search(head)
            pull = GPIO_PULL_RE.search(head)
            speed = GPIO_SPEED_RE.search(head)
            # 找到对应宏名
            for name, info in macros.items():
                if f"{name}_GPIO_Port" == port_name:
                    pin_key = f"P{info.get('port','?')}{info.get('num','?')}"
                    pins[pin_key] = {
                        "name": name,
                        "mode": mode.group(1) if mode else "?",
                        "pull": pull.group(1) if pull else "?",
                        "speed": speed.group(1) if speed else "?",
                    }
                    break
        # 初始电平
        for m in GPIO_WRITE_RE.finditer(t):
            port_name, pin_macro, level = m.group(1), m.group(2), m.group(3)
            for name, info in macros.items():
                if f"{name}_GPIO_Port" == port_name and f"{name}_Pin" == pin_macro:
                    key = f"P{info.get('port','?')}{info.get('num','?')}"
                    pins.setdefault(key, {"name": name})["init_level"] = level
                    break
    return pins


def extract_pins_spl(files: dict) -> dict:
    """SPL 风格 GPIO 提取：遍历工程源码 .c（src_files，任意目录结构）找
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_8|GPIO_Pin_9 + GPIO_Init(GPIOB, ...)。

    返回 {port_pin: {source_file, mode, otype, speed, pupd}}；无宏名，source_file 作标识。
    """
    pins = {}
    src_files = files.get("src_files") or []
    for f in sorted(src_files):
        t = read_text(f)
        # 每个 GPIO_Init 块：向前取最近的 GPIO_Pin 赋值
        for m in SPL_GPIO_INIT_RE.finditer(t):
            port = m.group(1)
            head = t[max(0, m.start() - 600):m.start()]
            pin_exprs = SPL_GPIO_PINS_RE.findall(head)
            if not pin_exprs:
                continue
            pin_expr = pin_exprs[-1]  # 取最近一次赋值（避免相邻块误配）
            # GPIO_Pin_8 | GPIO_Pin_9 → [8, 9]
            nums = [int(x) for x in SPL_GPIO_PIN_BIT_RE.findall(pin_expr)]
            mode = SPL_GPIO_MODE_RE.findall(head)
            otype = SPL_GPIO_OTYPE_RE.findall(head)
            speed = SPL_GPIO_SPEED_RE.findall(head)
            pupd = SPL_GPIO_PUPD_RE.findall(head)
            for n in nums:
                key = f"P{port}{n}"
                pins[key] = {
                    "source_file": f.name,
                    "mode": mode[-1] if mode else "?",
                    "otype": otype[-1] if otype else "?",
                    "speed": speed[-1] if speed else "?",
                    "pupd": pupd[-1] if pupd else "?",
                }
    return pins


def extract_clock(files: dict) -> dict:
    """提取时钟配置并计算 SYSCLK。支持 HAL（main.c SystemClock_Config）与
    SPL（system_stm32f4xx.c 的 PLL_M/N/P 宏 + RCC_Configuration）两种。"""
    clock = {"source": None, "hsi": None, "hse": None, "pll_input_mhz": None,
             "pll_mul": None, "sysclk_mhz": None, "hclk_mhz": None,
             "pclk1_mhz": None, "pclk2_mhz": None, "flash_latency": None,
             "pll_style": None}
    if files.get("is_hal", True):
        return _extract_clock_hal(files, clock)
    return _extract_clock_spl(files, clock)


def _extract_clock_hal(files: dict, clock: dict) -> dict:
    """HAL 时钟：main.c SystemClock_Config（RCC_OscInitStruct / RCC_ClkInitStruct）。"""
    clock["pll_style"] = "HAL"
    if not files["main_c"]:
        return clock
    t = read_text(files["main_c"])
    osc = RCC_OSC_RE.search(t)
    clock["source"] = osc.group(1) if osc else None
    hsi = HSI_STATE_RE.search(t)
    clock["hsi"] = hsi.group(1) if hsi else None
    hse = HSE_STATE_RE.search(t)
    clock["hse"] = hse.group(1) if hse else None

    pll_src = PLL_SRC_RE.search(t)
    pll_mul = PLL_MUL_RE.search(t)
    family = (extract_mcu(files) or {}).get("family") or "F1"
    hsi_mhz = FAMILY_HSI_MHZ.get(family, 16.0)  # 默认 16（大多数家族），F1/F3=8 由表覆盖

    # F4/G4/L4/F2/F7 等 HAL 用 PLLM/N/P（不是 F1 的 PLLMUL 倍频）：
    # PLL.PLLM / PLL.PLLN / PLL.PLLP → sysclk = pll_in / M * N / P
    pll_m = re.search(r"RCC_OscInitStruct\.PLL\.PLLM\s*=\s*(\d+)", t)
    pll_n = re.search(r"RCC_OscInitStruct\.PLL\.PLLN\s*=\s*(\d+)", t)
    pll_p = re.search(r"RCC_OscInitStruct\.PLL\.PLLP\s*=\s*(\d+)", t)
    if pll_src and pll_p and pll_n and pll_m:
        src = pll_src.group(1)
        m = int(pll_m.group(1))
        n = int(pll_n.group(1))
        p = int(pll_p.group(1))
        if "HSE" in src:
            pll_in = FAMILY_HSE_MHZ.get(family, 8.0)
        elif "HSI" in src:
            pll_in = hsi_mhz
        else:
            pll_in = hsi_mhz
        clock["pll_input_mhz"] = pll_in / m
        clock["pll_mul"] = f"{n}/{p}"
        clock["sysclk_mhz"] = pll_in / m * n / p
    elif pll_src and pll_mul:
        src = pll_src.group(1)
        mul_str = pll_mul.group(1).replace("RCC_PLL_MUL", "")
        # F1 的 4_5 倍频（RCC_PLL_MUL4_5）→ 4.5；下划线先去除再转浮点
        mul = float(mul_str.replace("_", "")) if "_" in mul_str else float(mul_str)
        # PLL 输入：HSI_DIV2 → hsi/2；HSE → hse
        if "HSI_DIV2" in src:
            pll_in = hsi_mhz / 2
        elif "HSE" in src:
            pll_in = FAMILY_HSE_MHZ.get(family, 8.0)
        else:
            pll_in = hsi_mhz
        clock["pll_input_mhz"] = pll_in
        clock["pll_mul"] = mul
        clock["sysclk_mhz"] = pll_in * mul
    else:
        # 无 PLL：SYSCLK = HSI 或 HSE
        if clock["hsi"] == "RCC_HSI_ON" and clock["hse"] != "RCC_HSE_ON":
            clock["sysclk_mhz"] = hsi_mhz
        elif clock["hse"] == "RCC_HSE_ON":
            clock["sysclk_mhz"] = FAMILY_HSE_MHZ.get(family, 8.0)

    # 分频
    ahb = AHB_DIV_RE.search(t)
    apb1 = APB1_DIV_RE.search(t)
    apb2 = APB2_DIV_RE.search(t)
    def div_of(s):
        if not s:
            return 1
        # RCC_SYSCLK_DIV1 / RCC_HCLK_DIV2 / DIV1 等 → 数字；解析失败回退 1
        digits = re.sub(r"\D", "", s)
        return int(digits) if digits else 1
    sysclk = clock["sysclk_mhz"] or 0
    clock["hclk_mhz"] = sysclk // div_of(ahb.group(1) if ahb else "DIV1")
    hclk = clock["hclk_mhz"]
    clock["pclk1_mhz"] = hclk // div_of(apb1.group(1) if apb1 else "DIV1")
    clock["pclk2_mhz"] = hclk // div_of(apb2.group(1) if apb2 else "DIV1")
    lat = FLASH_LAT_RE.search(t)
    clock["flash_latency"] = int(lat.group(1)) if lat else None
    return clock


def _extract_clock_spl(files: dict, clock: dict) -> dict:
    """SPL 时钟：system_stm32f4xx.c 的 #define PLL_M/N/P/Q + RCC_Configuration。

    SPL 的 SystemInit 用宏 PLL_M/PLL_N/PLL_P/PLL_Q（多个模板组并存，
    通常最后一组有效或由 HSE_VALUE 决定）。SYSCLK = HSE/HSI ÷M ×N ÷P。
    """
    clock["pll_style"] = "SPL"
    system_c = files.get("system_c")
    if not system_c:
        return clock
    t = read_text(system_c)
    lines = t.splitlines()

    # 确定型号宏：uvprojx Device → STM32F401RETx → STM32F401xx
    device = (extract_mcu(files) or {}).get("device") or ""
    model_macro = None
    if device:
        # 提取家族+数字（F401），忽略封装/密度/温度字母
        m = re.match(r"STM32([A-Z]\d+[A-Z]?\d*)", device.upper())
        if m:
            fam = m.group(1)  # F401（数字后的字母并入，如 F405）
            # 取前 4 位字母数字作为型号系列：F401 / F405 / F427 等
            series = re.match(r"([A-Z]\d{3})", fam)
            if series:
                fam = series.group(1)
            model_macro = f"STM32{fam}xx"
            # F40_41 特殊（F405/F407/F415/F417 用 STM32F40_41xxx）
            if fam in ("F405", "F407", "F415", "F417"):
                model_macro = "STM32F40_41xxx"

    # 解析条件编译分支：#if/#elif/#else/#endif 配对，取"型号宏所在分支"的 PLL 定义。
    # 用分支栈处理嵌套；#else 分支仅在"本层 #if 条件提到型号宏但未命中"时收集。
    def pll_in_branch(branch_name):
        pll = {}
        stack = []  # 每层 (active, matched, mentions_branch)
        for ln in lines:
            s = ln.strip()
            if s.startswith("#if"):
                cond = s[3:].strip()
                mentions = branch_name in cond
                active = mentions and branch_name in cond
                stack.append([active, active, mentions])
                continue
            if s.startswith("#elif"):
                if stack:
                    mentions = branch_name in s[5:].strip()
                    # elif 仅当本层尚未命中且条件提到型号时生效
                    stack[-1][2] = stack[-1][2] or mentions
                    stack[-1][0] = mentions and not stack[-1][1]
                    if stack[-1][0]:
                        stack[-1][1] = True
                continue
            if s.startswith("#else"):
                if stack:
                    # else 分支：本层 #if 提到型号但未命中 → 才收集
                    stack[-1][0] = stack[-1][2] and not stack[-1][1]
                    if stack[-1][0]:
                        stack[-1][1] = True
                continue
            if s.startswith("#endif"):
                if stack:
                    stack.pop()
                continue
            if not stack:
                continue
            # 仅当所有层都 active 才收集
            if all(layer[0] for layer in stack):
                m2 = re.match(r"#define\s+(PLL_[MNPQ])\s+(\d+)", s)
                if m2:
                    pll[m2.group(1)] = int(m2.group(2))
        return pll

    pll = {}
    if model_macro:
        pll = pll_in_branch(model_macro)
    if not pll:
        # 回退：取每个名字最后一个定义
        for name in ("PLL_M", "PLL_N", "PLL_P", "PLL_Q"):
            vals = re.findall(rf"^\s*#define\s+{name}\s+(\d+)", t, re.M)
            if vals:
                pll[name] = int(vals[-1])
    if not pll:
        return clock

    # HSE/HSI 频率：F4 HSI=16MHz；HSE 看 HSE_VALUE——可能在 system 文件，也可能在
    # stm32f4xx.h（#if !defined(HSE_VALUE) #define HSE_VALUE 25000000 #endif）
    hse_vals = [int(x) for x in re.findall(r"^\s*#define\s+HSE_VALUE\s+\(?(\d+)", t, re.M)]
    if not hse_vals and files.get("root"):
        # HSE_VALUE 通常在 stm32f4xx.h（CMSIS/Device/.../Include/ 深层），全局 rglob
        for f in files["root"].rglob("stm32f4xx.h"):
            t4 = read_text(f)
            hse_vals = [int(x) for x in
                        re.findall(r"#define\s+HSE_VALUE\s+\(?\s*\(?uint32_t\)?\s*(\d+)", t4)]
            if hse_vals:
                break
    hse_mhz = (hse_vals[-1] if hse_vals else 0) // 1000000
    family = (extract_mcu(files) or {}).get("family") or "F1"
    hsi_mhz = FAMILY_HSI_MHZ.get(family, 16.0)
    m = pll.get("PLL_M") or 1
    n = pll.get("PLL_N") or 1
    p = pll.get("PLL_P") or 1
    # SPL 默认用 HSE（F4 标准库 SystemInit 先使能 HSE），无 HSE_VALUE 或 HSE=0 时用 HSI
    if hse_mhz:
        clock["source"] = "HSE"
        clock["hse"] = f"{hse_mhz}MHz"
        clock["pll_input_mhz"] = hse_mhz / m
        clock["sysclk_mhz"] = hse_mhz / m * n / p
    else:
        clock["source"] = "HSI"
        clock["hsi"] = "ON"
        clock["pll_input_mhz"] = hsi_mhz / m
        clock["sysclk_mhz"] = hsi_mhz / m * n / p
    clock["pll_mul"] = f"{n}/{p}"
    clock["pll_branch"] = model_macro or "fallback"
    # SPL 分频通常在 RCC_Configuration（main.c 或单独函数），HCLK/APB 暂按默认：
    # F4 常见 AHB/1 APB1/2 APB2/2；解析不到时标 TBD 让 AI 确认
    clock["hclk_mhz"] = clock["sysclk_mhz"]
    clock["pclk1_mhz"] = "TBD(SPL)"
    clock["pclk2_mhz"] = "TBD(SPL)"
    clock["flash_latency"] = "TBD(SPL)"
    return clock


def extract_peripherals(files: dict) -> dict:
    """提取外设：hal_conf/conf 启用的模块 + 实际调用的外设 + 外设源文件。

    HAL：Core/Src 外设 .c；SPL：USER/src 外设 .c（排除 system/库文件）。
    """
    enabled = []
    if files["hal_conf"]:
        t = read_text(files["hal_conf"])
        enabled = list(dict.fromkeys(HAL_MODULE_RE.findall(t)))  # 去重（CubeMX 可能重复生成）
    used = []
    if files["main_c"]:
        t = read_text(files["main_c"])
        used = list(dict.fromkeys(MX_INIT_RE.findall(t)))  # MX_xxx_Init
        used += list(dict.fromkeys(HAL_INIT_RE.findall(t)))  # HAL_xxx_Init(&
    peripheral_files = []
    for f in sorted(files.get("src_files") or []):
        name = f.stem
        if name.startswith(("system_", "stm32f", "main", "gpio", "delay")):
            continue
        peripheral_files.append(name)
    return {"enabled_modules": enabled, "used_peripherals": used,
            "peripheral_files": peripheral_files}


def extract_behavior(files: dict) -> dict:
    """主循环行为推断。"""
    behavior = {"main_loop": [], "delays_ms": []}
    if not files["main_c"]:
        return behavior
    t = read_text(files["main_c"])
    if WHILE_RE.search(t):
        toggles = TOGGLE_RE.findall(t)
        delays = DELAY_RE.findall(t)
        if toggles:
            behavior["main_loop"].append("LED 翻转: " + ", ".join(f"{p}.{m}" for p, m in toggles))
        if delays:
            behavior["delays_ms"] = [int(d) for d in delays]
            behavior["main_loop"].append(f"HAL_Delay({delays[0]}) 延时")
    return behavior


def analyze(root: Path) -> dict:
    files = find_files(root)
    is_hal = files.get("is_hal", True)
    pins = extract_pins(files) if is_hal else extract_pins_spl(files)
    return {
        "mcu": extract_mcu(files),
        "clock": extract_clock(files),
        "pins": pins,
        "peripherals": extract_peripherals(files),
        "behavior": extract_behavior(files),
        "is_hal": is_hal,
    }


# ===================== 输出 =====================
def render_hardware_yaml(result: dict, project_name: str) -> str:
    mcu = result["mcu"]
    clock = result["clock"]
    pins = result["pins"]
    per = result["peripherals"]
    beh = result["behavior"]
    lines = [
        "# hardware.yaml —— 由 analyze_hw.py 静态提取（草稿）",
        f"# 工程: {project_name} | 生成时间: 需 AI 补充",
        "# ⚠️ 本文件是静态提取草稿：时钟/引脚由代码正则解析，外设用途需 AI 读代码补充确认",
        "",
        "project:",
        f'  name: "{project_name}"',
        '  version: "0.1.0"',
        f'  description: "{project_name}（待 AI 分析补充）"',
        "",
        "mcu:",
        f'  device: "{mcu.get("device") or "未知（待确认）"}"',
        f'  family: "{mcu.get("family") or "未知"}"',
        f'  flash_kb: {mcu.get("flash_kb") or "TBD"}',
        f'  ram_kb: {mcu.get("ram_kb") or "TBD"}',
        "",
        "clock:",
        f'  source: "{clock.get("source") or "TBD"}"',
        f'  sysclk_mhz: {clock.get("sysclk_mhz") or "TBD"}',
        f'  hclk_mhz: {clock.get("hclk_mhz") or "TBD"}',
        f'  pclk1_mhz: {clock.get("pclk1_mhz") or "TBD"}',
        f'  pclk2_mhz: {clock.get("pclk2_mhz") or "TBD"}',
        f'  flash_latency: {clock.get("flash_latency") or "TBD"}',
        "",
        "peripherals:",
        "  gpio:",
    ]
    for key, info in sorted(pins.items()):
        if info.get("name"):
            # HAL 风格：有宏名
            lines.append(f'    {info.get("name").lower()}: {{pin: "{key}", mode: "{info.get("mode", "?")}", purpose: "待确认"}}')
        else:
            # SPL 风格：无宏名，用源文件作标识
            lines.append(f'    pin_{key.lower()}: {{pin: "{key}", mode: "{info.get("mode", "?")}", source: "{info.get("source_file", "?")}", purpose: "待确认"}}')
    lines.append(f"  enabled_modules: {per['enabled_modules']}")
    lines.append(f"  used_peripherals: {per['used_peripherals']}")
    lines.append(f"  peripheral_files: {per['peripheral_files']}")
    lines.append("")
    lines.append("behavior:")
    lines.append(f"  main_loop: {beh['main_loop']}")
    lines.append(f"  delays_ms: {beh['delays_ms']}")
    lines.append("")
    lines.append("# ============ 待 AI 补充（ai_review_notes.md 有完整清单）============")
    return "\n".join(lines) + "\n"


def render_pin_usage(result: dict) -> str:
    pins = result["pins"]
    lines = [
        "# 引脚占用表（analyze_hw.py 静态提取草稿）",
        "",
        "## 已占用引脚",
        "| 引脚 | 功能 | 外设 | 模式 | 状态 | 备注 |",
        "|------|------|------|------|------|------|",
    ]
    for key, info in sorted(pins.items()):
        if info.get("name"):
            lines.append(f"| {key} | {info.get('name','?')} | GPIO | {info.get('mode','?')} | 使用中 | "
                         f"Pull={info.get('pull','?')} Speed={info.get('speed','?')} "
                         f"初始={info.get('init_level','未写')} |")
        else:
            lines.append(f"| {key} | {info.get('source_file','?')} | GPIO | {info.get('mode','?')} | 使用中 | "
                         f"OType={info.get('otype','?')} Speed={info.get('speed','?')} "
                         f"PuPd={info.get('pupd','?')} |")
    lines.append("")
    lines.append("## 可用引脚")
    lines.append("| 引脚 | 状态 | 建议用途 |")
    lines.append("|------|------|----------|")
    lines.append("|（待 AI 按封装补全）| 可用 | |")
    lines.append("")
    lines.append("## 冲突检查记录")
    lines.append("- [ ] 待 AI 检查")
    return "\n".join(lines) + "\n"


def render_ai_notes(result: dict) -> str:
    mcu = result["mcu"]
    clock = result["clock"]
    per = result["peripherals"]
    beh = result["behavior"]
    notes = [
        "# AI 复核清单（analyze_hw.py 静态提取后，需 AI 读代码确认的点）",
        "",
        "## 必须人工/AI 确认",
        "1. **MCU 完整型号**：静态只识别到 " + str(mcu.get("device") or "未知") +
        "，请从 .ioc / 原理图确认完整型号（如 STM32F103C8T6）与封装",
        "2. **时钟正确性**：推导 SYSCLK=" + str(clock.get("sysclk_mhz") or "?") +
        "MHz（HSI/HSE 源、PLL 倍频），请核对 SystemClock_Config 与板载晶振实际值",
        "3. **外设用途**：每个 GPIO 的实际用途（LED/按键/传感器/通信）需读 USER CODE 代码确认",
        "4. **未启用但已编译的模块**：hal_conf 启用了 " + str(per["enabled_modules"]) +
        "，实际使用的外设是 " + str(per["used_peripherals"]) + "，请区分",
        "5. **中断使用**：读 stm32f1xx_it.c 确认哪些外设中断真的在用",
        "6. **约束**：HAL vs SPL、时钟特殊限制（如 USB 48MHz）、编码规范",
        "",
        "## 静态提取结果摘要（供复核）",
        f"- 引脚: {list(result['pins'].keys())}",
        f"- 外设文件: {per['peripheral_files']}",
        f"- 主循环: {beh['main_loop']}",
        "",
        "## 交叉验证建议",
        "对关键结论（型号、时钟、引脚映射）拉两个子代理独立读代码核对后再定稿。",
    ]
    return "\n".join(notes) + "\n"


# ===================== CLI =====================
def main():
    fix_console_encoding()
    ap = argparse.ArgumentParser(prog="analyze_hw.py",
                                 description="STM32 工程硬件配置静态提取（方案 B 确定性部分）")
    ap.add_argument("project_dir", help="已有 STM32 工程目录")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 分析结果")
    ap.add_argument("--out", metavar="DIR", default=None,
                    help="输出目录（默认工程目录）")
    args = ap.parse_args()

    root = Path(args.project_dir)
    if not root.exists():
        err(f"工程目录不存在: {root}")
        return 1
    result = analyze(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    out_dir = Path(args.out) if args.out else root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hardware.yaml.draft").write_text(
        render_hardware_yaml(result, root.name), encoding="utf-8")
    (out_dir / "pin_usage.md.draft").write_text(
        render_pin_usage(result), encoding="utf-8")
    (out_dir / "ai_review_notes.md").write_text(
        render_ai_notes(result), encoding="utf-8")
    ok(f"分析完成，草稿输出到 {out_dir}/")
    info("  hardware.yaml.draft + pin_usage.md.draft + ai_review_notes.md")
    info("  下一步: AI 读 ai_review_notes.md 复核 + 双子代理交叉验证后定稿")
    return 0


def fix_console_encoding():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def ok(msg):   print(f"[OK]   {msg}")
def info(msg): print(f"[INFO] {msg}")
def err(msg):  sys.stderr.write(f"[ERR]  {msg}\n")


if __name__ == "__main__":
    sys.exit(main())
