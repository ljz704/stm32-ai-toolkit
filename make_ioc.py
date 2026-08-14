#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_ioc.py —— STM32 型号 → 可无头生成的 .ioc

为什么需要它：
  CubeMX 无头生成（cubemx_gen.py）必须输入 .ioc。手写 .ioc 最大的坑是
  RCC 时钟块——各家族语法不同（G4/F3 用 PLLM 枚举 `RCC_PLLM_DIVx`、F1 用
  PLLMUL、F4 用数字 PLLM/N/P…），一旦写错 CubeMX 报 "IP not ready: Clock"
  甚至弹窗卡死。
  因此本脚本从已安装的 STM32Cube FW 包里挑一个最近的官方示例工程，原样提取
  其 RCC.* 时钟配置（保证家族语法正确），再套上目标型号的最小骨架
  （NVIC/RCC/SYS + SysTick + HSE，无物理引脚），产出 CubeMX 一定能识别的 .ioc。

依赖：
  cubemx_gen.py（固件包仓库探测 + FW 家族表，型号家族用最长前缀匹配，
  兼容 WB/WL/WBA/N6 等双字母家族）。

用法:
  python make_ioc.py STM32G474VET6 -o test_new/test_new.ioc
  python make_ioc.py STM32F103C8T6 --json          # 只输出信息，不写文件
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from cubemx_gen import (                       # noqa: E402
    detect_cubemx, find_repository, find_fw_package, fw_prefix,
)
from mcu_knowledge import split_model

# CubeMX 生成的固件包里官方示例工程搜索深度
_EXAMPLE_GLOBS = ("Projects/**/*.ioc",)

# 官方示例里没有 .ioc 的家族（老家族 F0/F1/L1 等，示例是裸 Keil 工程）用内置 RCC 兜底。
# F1 这条是实测验证过的（TEST.ioc，8MHz HSE → 64MHz）。写新家族兜底前先跑一次
# 生成确认语法正确，否则宁可留空让用户去 CubeMX GUI 配置。
# 内置 RCC 兜底块（官方示例缺失时用）。字段语法来自 CubeMX 自带 Board.ioc：
# F1=实测 TEST.ioc（8MHz HSE→64MHz）、F0=NUCLEO-F072RB（48MHz 需显式 PLLDivider=/2）、L1=NUCLEO-L152RE。
# F1/F0 的 PLLMUL 按 --hse-mhz 缩放；L1 走 HSI 时钟与 HSE 无关，照抄固定。
_F1_RCC_BASE = [
    "RCC.ADCFreqValue=32000000",
    "RCC.AHBFreq_Value=64000000",
    "RCC.APB1CLKDivider=RCC_HCLK_DIV2",
    "RCC.APB1Freq_Value=32000000",
    "RCC.APB1TimFreq_Value=64000000",
    "RCC.APB2Freq_Value=64000000",
    "RCC.APB2TimFreq_Value=64000000",
    "RCC.FCLKCortexFreq_Value=64000000",
    "RCC.FamilyName=M",
    "RCC.HCLKFreq_Value=64000000",
    "RCC.IPParameters=ADCFreqValue,AHBFreq_Value,APB1CLKDivider,APB1Freq_Value,APB1TimFreq_Value,APB2Freq_Value,APB2TimFreq_Value,FCLKCortexFreq_Value,FamilyName,HCLKFreq_Value,MCOFreq_Value,PLLCLKFreq_Value,PLLMCOFreq_Value,PLLMUL,SYSCLKFreq_VALUE,SYSCLKSource,TimSysFreq_Value,USBFreq_Value",
    "RCC.MCOFreq_Value=64000000",
    "RCC.PLLCLKFreq_Value=64000000",
    "RCC.PLLMCOFreq_Value=32000000",
    "RCC.SYSCLKFreq_VALUE=64000000",
    "RCC.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK",
    "RCC.TimSysFreq_Value=64000000",
    "RCC.USBFreq_Value=64000000",
]
_F0_RCC_BASE = [
    "RCC.AHBFreq_Value=48000000",
    "RCC.APB1Freq_Value=48000000",
    "RCC.APB1TimFreq_Value=48000000",
    "RCC.FCLKCortexFreq_Value=48000000",
    "RCC.FamilyName=M",
    "RCC.HCLKFreq_Value=48000000",
    "RCC.IPParameters=AHBFreq_Value,APB1Freq_Value,APB1TimFreq_Value,FCLKCortexFreq_Value,FamilyName,HCLKFreq_Value,MCOFreq_Value,PLLCLKFreq_Value,PLLDivider,PLLMCOFreq_Value,PLLMUL,SYSCLKFreq_VALUE,SYSCLKSource,TimSysFreq_Value,USART1Freq_Value",
    "RCC.MCOFreq_Value=48000000",
    "RCC.PLLCLKFreq_Value=48000000",
    "RCC.PLLDivider=RCC_PREDIV_DIV2",
    "RCC.PLLMCOFreq_Value=24000000",
    "RCC.SYSCLKFreq_VALUE=48000000",
    "RCC.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK",
    "RCC.TimSysFreq_Value=48000000",
    "RCC.USART1Freq_Value=48000000",
]
_L1_RCC_BASE = [
    "RCC.AHBFreq_Value=32000000",
    "RCC.APB1Freq_Value=32000000",
    "RCC.APB1TimFreq_Value=32000000",
    "RCC.APB2Freq_Value=32000000",
    "RCC.APB2TimFreq_Value=32000000",
    "RCC.FCLKCortexFreq_Value=32000000",
    "RCC.FamilyName=M",
    "RCC.HCLKFreq_Value=32000000",
    "RCC.HSE_VALUE=8000000",
    "RCC.HSI_VALUE=16000000",
    "RCC.IPParameters=AHBFreq_Value,APB1Freq_Value,APB1TimFreq_Value,APB2Freq_Value,APB2TimFreq_Value,FCLKCortexFreq_Value,FamilyName,HCLKFreq_Value,HSE_VALUE,HSI_VALUE,LCDFreq_Value,LSE_VALUE,LSI_VALUE,MCOPinFreq_Value,MSI_VALUE,PLLCLKFreq_Value,PLLDIV,PLLMUL,PWRFreq_Value,RTCClockSelectionVirtual,RTCFreq_Value,RTCHSEDivFreq_Value,SYSCLKFreq_VALUE,SYSCLKSource,TIMFreq_Value,TimerFreq_Value,USBOutput,VCOOutputFreq_Value",
    "RCC.LCDFreq_Value=32768",
    "RCC.LSE_VALUE=32768",
    "RCC.LSI_VALUE=37000",
    "RCC.MCOPinFreq_Value=32000000",
    "RCC.MSI_VALUE=2097000",
    "RCC.PLLCLKFreq_Value=32000000",
    "RCC.PLLDIV=RCC_PLL_DIV3",
    "RCC.PLLMUL=RCC_PLL_MUL6",
    "RCC.PWRFreq_Value=32000000",
    "RCC.RTCClockSelectionVirtual=RCC_RTCCLKSOURCE_LSE",
    "RCC.RTCFreq_Value=32768",
    "RCC.RTCHSEDivFreq_Value=4000000",
    "RCC.SYSCLKFreq_VALUE=32000000",
    "RCC.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK",
    "RCC.TIMFreq_Value=32000000",
    "RCC.TimerFreq_Value=32000000",
    "RCC.USBOutput=48000000",
    "RCC.VCOOutputFreq_Value=96000000",
]


def _fallback_rcc(family: str, hse_hz: int) -> list:
    """内置 RCC 兜底块（官方示例缺失时用）。

    F1/F0/L1 内置模板一律走 HSI 时钟，与官方 NUCLEO 板默认工程一致
    （F0=HSI 8MHz/2×MUL12=48MHz、F1=HSI 8MHz/2×MUL16=64MHz、L1=HSI
    16MHz/3×MUL6=32MHz），PLL 源固定为内部 HSI，不随 --hse-mhz 缩放。
    --hse-mhz 非默认值 8 时仅告警（外接晶振请在 CubeMX GUI 时钟树里
    开启 HSE 并选 PLL 源），避免静默配错时钟。
    返回空列表表示该家族没有兜底模板。
    """
    hse_mhz = hse_hz // 1_000_000
    if hse_mhz <= 0:
        raise ValueError("--hse-mhz 必须是正整数")
    if family == "F1":
        if hse_mhz != 8:
            warn(f"F1 内置模板走 HSI 时钟（HSI 8MHz/2×MUL16=64MHz），--hse-mhz {hse_mhz} 不生效；"
                 f"外接晶振请在 CubeMX GUI 时钟树开启 HSE")
        return _F1_RCC_BASE + ["RCC.PLLMUL=RCC_PLL_MUL16"]
    if family == "F0":
        if hse_mhz != 8:
            warn(f"F0 内置模板走 HSI 时钟（HSI 8MHz/2×MUL12=48MHz），--hse-mhz {hse_mhz} 不生效；"
                 f"外接晶振请在 CubeMX GUI 时钟树开启 HSE")
        return _F0_RCC_BASE + ["RCC.PLLMUL=RCC_PLL_MUL12"]
    if family == "L1":
        if hse_mhz != 8:
            warn(f"L1 内置模板走 HSI 时钟（HSI 16MHz/3×MUL6=32MHz），--hse-mhz {hse_mhz} 不生效；"
                 f"外接晶振请在 CubeMX GUI 时钟树开启 HSE")
        return list(_L1_RCC_BASE)
    return []


# ===================== 输出 =====================
def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[WARN] {msg}")
def err(msg):   sys.stderr.write(f"[ERR]  {msg}\n")


# ===================== 型号 → 各字段 =====================
def mcu_fields(model: str) -> dict:
    """把完整型号拆成 .ioc 需要的字段。缺 STM32 前缀自动补。

    型号拆解统一走 mcu_knowledge.split_model（最长前缀匹配，兼容双字母
    家族 WB/WL/WBA/N6 等），本函数只补 CubeMX 侧字段 root/user。
    型号结构：STM32 + 家族 + 数字串 + 封装字母 + 密度 + 温度 + 等级。
    root（DB 文件名前缀）如 STM32F103 / STM32WB55 / STM32G431。
    """
    s = split_model(model)
    if not s:
        return {}
    upper = (model or "").strip().upper()
    if not upper.startswith("STM32"):
        upper = "STM32" + upper
    # UserName/DeviceId：末位等级(数字)→x，如 STM32G474VET6 → STM32G474VETx
    user = upper[:-1] + "x" if upper[-1:].isdigit() else upper
    return {
        "model": upper,
        "family": s["family"],
        "root": "STM32" + s["family"] + s["numeric"],
        "package": s["package"],
        "density": s["density"],
        "user": user,
    }


def db_range_name(fields: dict, db_dir: Path):
    """从 CubeMX 的 db/mcu/ 里查该型号的 DB 范围形式 + 封装名。

    CubeMX 的 MCU 库按"多密度合一"存：一个文件覆盖多个密度，如
    STM32G474V(B-C-E)Tx.xml。Mcu.Name 必须填这个文件名的 stem（完整型号会
    报 "MCU is unknown"）。这里 glob 匹配 package 字母，再校验 density 落在范围内。
    返回 dict：{name: "STM32G474V(B-C-E)Tx", package: "LQFP100"}；查不到返回 None。
    封装名直接读 DB XML 的 Package 属性，比用字母猜可靠。
    """
    root, pkg, density = fields.get("root"), fields.get("package"), fields.get("density")
    if not root or not pkg or not density:
        return None
    hits = []
    for f in db_dir.glob(f"{root}{pkg}*.xml"):
        stem = f.stem
        # 取 package 字母与温度字母之间的小括号密度范围
        m = re.search(rf"{re.escape(root)}{re.escape(pkg)}\(([^)]*)\)", stem)
        if m:
            dens = set(re.findall(r"[A-Z0-9]", m.group(1)))
            if density.upper() in dens:
                hits.append(f)
        else:                                   # 无括号（单密度文件），须校验密度字母
            # 如 STM32F030C8Tx：去掉 root+pkg 前缀后剩 "8Tx"，取密度字母集合
            tail = stem[len(root) + len(pkg):]
            dens = set(re.findall(r"[0-9A-Z]", tail))
            if density.upper() in dens:
                hits.append(f)
    if not hits:
        return None
    # 优先温度后缀 Tx 的（最常见），其次任意
    chosen = None
    for f in hits:
        if f.stem.endswith("Tx"):
            chosen = f
            break
    if chosen is None:
        chosen = sorted(hits)[0]
    # 从 DB XML 读封装名
    package = None
    try:
        head = chosen.read_text(encoding="utf-8", errors="replace")[:4096]
        m = re.search(r'Package="([^"]+)"', head)
        if m:
            package = m.group(1)
    except OSError:
        pass
    return {"name": chosen.stem, "package": package}


# ===================== 官方示例 =====================
def parse_ioc_meta(ioc_path: Path) -> dict:
    """读 .ioc 的 Mcu 行，返回 {name, family, package, pins}。"""
    meta = {}
    try:
        for ln in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("Mcu.Name="):
                meta["name"] = ln.split("=", 1)[1].strip()
            elif ln.startswith("Mcu.Family="):
                meta["family"] = ln.split("=", 1)[1].strip().replace("STM32", "")
            elif ln.startswith("Mcu.Package="):
                meta["package"] = ln.split("=", 1)[1].strip()
            elif ln.startswith("Mcu.PinsNb="):
                meta["pins"] = int(ln.split("=", 1)[1].strip())
    except OSError:
        pass
    return meta


def find_example_ioc(fw_dir: Path, fields: dict):
    """在固件包 Projects/ 里找"最接近"目标型号的官方示例 .ioc。

    打分：同 package 字母 +8；同 density 覆盖 +4；物理引脚越少越通用 -pins。
    返回 (path, meta) 或 (None, None)。
    """
    family, pkg = fields.get("family"), fields.get("package")
    best, best_meta, best_score = None, None, -10 ** 9
    for pat in _EXAMPLE_GLOBS:
        for f in sorted(fw_dir.glob(pat)):
            meta = parse_ioc_meta(f)
            if not meta or meta.get("family") != family:
                continue
            score = 0
            if meta.get("package") == pkg:
                score += 8
            score -= meta.get("pins", 30)
            if score > best_score:
                best, best_meta, best_score = f, meta, score
    return best, best_meta


def extract_rcc_lines(example_ioc: Path) -> list:
    """原样提取示例工程的 RCC.* 与 VP_RCC_VS_HSE.* 时钟配置行（家族语法正确）。"""
    out = []
    for ln in example_ioc.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith(("RCC.", "VP_RCC_VS_HSE.")):
            out.append(ln)
    return out


# ===================== 最小 .ioc 骨架 =====================
def build_minimal_ioc(fields: dict, range_name: str, package_name: str,
                      rcc: list, fw_package: str, project_name: str) -> str:
    """拼最小 .ioc：NVIC/RCC/SYS + SysTick + HSE，无物理引脚。"""
    model = fields["model"]
    user = fields["user"]
    lines = [
        "#MicroXplorer Configuration settings - do not modify",
        "CAD.formats=", "CAD.pinconfig=", "CAD.provider=",
        "File.Version=6", "GPIO.groupedBy=", "KeepUserPlacement=false",
        f"Mcu.CPN={model}", f"Mcu.Family=STM32{fields['family']}",
        "Mcu.IP0=NVIC", "Mcu.IP1=RCC", "Mcu.IP2=SYS", "Mcu.IPNb=3",
        f"Mcu.Name={range_name}", f"Mcu.Package={package_name}",
        # 只声明 SysTick 虚拟引脚。HSE 用物理晶振引脚（如 PF0-OSC_IN），不能声明
        # VP_RCC_VS_HSE 虚拟引脚——F1 等家族没有该引脚，"cannot be retrieved" 会
        # 导致 config load 失败、CubeMX 静默退出（对照实测通过的 TEST.ioc）。
        "Mcu.Pin0=VP_SYS_VS_Systick", "Mcu.PinsNb=1",
        "Mcu.ThirdPartyNb=0", "Mcu.UserConstants=", f"Mcu.UserName={user}",
        "MxCube.Version=6.18.1", "MxDb.Version=DB.6.0.181",
        "NVIC.BusFault_IRQn=true", "NVIC.DebugMonitor_IRQn=true",
        "NVIC.HardFault_IRQn=true", "NVIC.MemoryManagement_IRQn=true",
        "NVIC.NonMaskableInt_IRQn=true", "NVIC.PendSV_IRQn=true",
        "NVIC.PriorityGroup=NVIC_PRIORITYGROUP_4", "NVIC.SVCall_IRQn=true",
        "NVIC.SysTick_IRQn=true",
        "PinOutPanel.RotationAngle=0",
        "ProjectManager.AskForMigrate=true", "ProjectManager.BackupPrevious=false",
        "ProjectManager.CompilerLinker=GCC", "ProjectManager.CompilerOptimize=6",
        "ProjectManager.ComputerToolchain=false", "ProjectManager.CoupleFile=true",
        "ProjectManager.CustomerFirmwarePackage=", "ProjectManager.DefaultFWLocation=true",
        "ProjectManager.DeletePrevious=true", f"ProjectManager.DeviceId={user}",
        f"ProjectManager.FirmwarePackage={fw_package}",
        "ProjectManager.FreePins=false", "ProjectManager.FreePinsContext=",
        "ProjectManager.HalAssertFull=false", "ProjectManager.HeapSize=0x200",
        "ProjectManager.KeepUserCode=true", "ProjectManager.LastFirmware=true",
        "ProjectManager.LibraryCopy=1", "ProjectManager.MainLocation=Core/Src",
        "ProjectManager.NoMain=false", "ProjectManager.PreviousToolchain=",
        "ProjectManager.ProjectBuild=false",
        f"ProjectManager.ProjectFileName={project_name}.ioc",
        f"ProjectManager.ProjectName={project_name}", "ProjectManager.ProjectStructure=",
        "ProjectManager.RegisterCallBack=", "ProjectManager.StackSize=0x400",
        "ProjectManager.TargetToolchain=MDK-ARM V5.32", "ProjectManager.ToolChainLocation=",
        "ProjectManager.UAScriptAfterPath=", "ProjectManager.UAScriptBeforePath=",
        "ProjectManager.UnderRoot=false",
        "ProjectManager.functionlistsort=1-SystemClock_Config-RCC-false-HAL-false,2-MX_GPIO_Init-GPIO-false-HAL-true",
    ]
    lines += rcc
    lines += [
        "VP_SYS_VS_Systick.Mode=SysTick", "VP_SYS_VS_Systick.Signal=SYS_VS_Systick",
        "board=custom",
    ]
    return "\n".join(lines) + "\n"


# ===================== CLI =====================
def make_ioc(model: str, project_name: str = "project", hse_hz: int = 8_000_000) -> dict:
    """核心入口：型号 → {ok, ioc_text?, ...}。不写文件，返回结构供 CLI/MCP 用。

    project_name 会写进 .ioc 的 ProjectManager.ProjectName/FileName；
    生成时 CubeMX 以 .ioc 文件名为准，但两处保持一致最稳妥。
    hse_hz 仅影响内置 RCC 兜底（F1/F0 的 PLLMUL 按晶振缩放）。
    """
    result = {"ok": False, "model": model}
    fields = mcu_fields(model)
    if not fields or fields.get("root") is None:
        result["error"] = f"无法解析型号 {model!r}。请给完整型号，如 STM32G474VET6。"
        err(result["error"])
        return result
    result["family"] = fields["family"]
    result["package"] = fields.get("package")

    exe = detect_cubemx()
    if not exe:
        result["error"] = "未找到 STM32CubeMX.exe。设 CUBEMX_PATH 或安装到默认路径。"
        err(result["error"])
        return result

    repos = find_repository()
    if not repos:
        result["error"] = "找不到 CubeMX 固件包仓库目录（探测过常见位置均不存在）。"
        err(result["error"])
        return result

    fw_prefix_name = fw_prefix(fields["family"])
    installed, _zip = find_fw_package(repos, fields["family"])
    if not installed:
        result["error_type"] = "missing_firmware"
        result["required_fw"] = fw_prefix_name
        result["fw_repos"] = [str(p) for p in repos]
        result["error"] = (
            f"缺少固件包 {fw_prefix_name}（仓库: {result['fw_repos']}）。\n"
            "  处理: 先在 CubeMX GUI → Help → Manage embedded software packages 安装，"
            "或运行 python cubemx_gen.py --ensure-fw 配合已有 .ioc。"
        )
        err(result["error"])
        return result
    result["fw"] = str(installed)

    db_dir = Path(exe).parent / "db" / "mcu"
    range_info = db_range_name(fields, db_dir) if db_dir.exists() else None
    if not range_info:
        result["error"] = (
            f"在 CubeMX MCU 库 {db_dir} 里找不到 {fields['root']}{fields.get('package', '')}*.xml"
            f"（密度 {fields.get('density')} 不在范围内？）。"
        )
        err(result["error"])
        return result
    range_name = range_info["name"]
    result["mcu_name"] = range_name
    if range_info.get("package"):
        result["package_name"] = range_info["package"]

    example, meta = find_example_ioc(installed, fields)
    rcc, clock_note = [], None
    if example:
        rcc = extract_rcc_lines(example)
        if rcc:
            result["example"] = str(example)
            result["rcc_lines"] = len(rcc)
            result["example_clock"] = clock_note = _clock_summary(example)
    if not rcc:
        # 老家族（F0/F1/L1…）包内无 .ioc 示例 → 用内置兜底模板
        try:
            fb = _fallback_rcc(fields["family"], hse_hz)
        except ValueError as e:
            result["error"] = str(e)
            err(result["error"])
            return result
        if fb:
            rcc = list(fb)
            result["rcc_source"] = f"内置模板（{fields['family']}，HSI 时钟，与官方板一致）"
            clock_note = f"内置模板时钟（{fields['family']}，HSI，PLL 源固定）"
        else:
            result["error"] = (
                f"固件包 {fw_prefix_name} 里没有 {fields['family']} 官方示例 .ioc，"
                "且未提供该家族内置 RCC 模板。请到 CubeMX GUI 手工建工程，或用新版本固件包。"
            )
            err(result["error"])
            return result
    if clock_note:
        result["clock_note"] = clock_note

    # FirmwarePackage 字段格式是 "STM32Cube FW_<家族> V<版本>"，V 不能丢
    # （实测 TEST.ioc 为 "STM32Cube FW_F1 V1.8.7"；缺 V 时 CubeMX 找不到包）。
    fw_package = f"STM32Cube FW_{fields['family']} V{_fw_version(installed)}"
    package_name = range_info.get("package") or fields.get("package", "")
    result["ioc"] = build_minimal_ioc(fields, range_name, package_name, rcc, fw_package,
                                      project_name or "project")
    result["ok"] = True
    return result


def _fw_version(installed_dir: Path) -> str:
    m = re.search(r"_V([\d.]+)$", installed_dir.name)
    return m.group(1) if m else "?"


def _clock_summary(example_ioc: Path) -> str:
    hse = pll = "?"
    try:
        for ln in example_ioc.read_text(encoding="utf-8", errors="replace").splitlines():
            if ln.startswith("RCC.HSE_VALUE="):
                hse = ln.split("=", 1)[1].strip()
            elif ln.startswith("RCC.PLLM="):
                pll = ln.split("=", 1)[1].strip()
    except OSError:
        pass
    return f"HSE={hse}Hz, PLLM={pll}（沿用官方示例时钟，可在 CubeMX GUI 调整）"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="STM32 型号 → 可无头生成的 .ioc")
    ap.add_argument("model", help="完整型号，如 STM32G474VET6")
    ap.add_argument("-o", "--out", help="输出 .ioc 路径（默认 当前目录/<型号>.ioc）")
    ap.add_argument("--json", action="store_true", help="只输出 JSON，不写文件")
    ap.add_argument("--project-name", default=None, help="工程名（默认取型号）")
    ap.add_argument("--hse-mhz", type=int, default=8, metavar="N",
                    help="板载晶振 MHz（默认 8；F1/F0/L1 内置兜底走 HSI，非 8 时告警提示）")
    args = ap.parse_args(argv)

    # 工程名写进 .ioc（ProjectManager.ProjectName），与输出文件名一致最稳；
    # --json 不落盘，用默认即可。
    if args.json:
        proj = args.project_name or "project"
    elif args.out:
        proj = args.project_name or Path(args.out).stem
    else:
        proj = args.project_name or args.model

    r = make_ioc(args.model, proj, hse_hz=args.hse_mhz * 1_000_000)
    if args.json:
        # ensure_ascii：GBK 控制台安全
        out = {k: v for k, v in r.items() if k != "ioc"}
        print(json.dumps(out, ensure_ascii=True))
        return 0 if r["ok"] else 1

    if not r["ok"]:
        return 1
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = Path(f"{args.model}.ioc")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(r["ioc"], encoding="utf-8")
    info(f"已生成 {out_path}（MCU={r['mcu_name']}，固件包={r['fw']}）")
    info(f"时钟    : {r.get('clock_note') or r.get('example_clock', '?')}")
    info(f"下一步  : python cubemx_gen.py {out_path}  → 无头生成完整工程")
    info("         或 CubeMX GUI 打开该 .ioc 配置引脚/外设后再生成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
