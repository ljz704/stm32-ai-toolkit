# -*- coding: utf-8 -*-
"""
mcu_knowledge.py —— STM32 型号知识库
=====================================
解析完整型号（如 STM32F103CBT6 / STM32G431CBT6）→ 结构化规格：
核心 / FPU / SPL 支持 / 封装引脚数 / Flash / RAM / 启动文件。

纯数据 + 解析 + CLI，无副作用：
  - new_project.py import 使用（渲染 hardware.yaml / 选模板 / 判 SPL）
  - Claude 可 `python mcu_knowledge.py --query STM32F103CBT6 --json`
    在 /newproject 对话里预览并让用户确认

型号格式（单字母家族）：
  STM32 + 家族(F/G/L/H) + 系列(1) + 产品线(03) + 封装(C) + 密度(B) + 温度(T) + 等级(6)
  例：STM32F103CBT6 = F1 / 03 / C(48脚) / B(128K) / T / 6

设计原则：查得到的给精确值，查不到/不确定的给 null 并列入 missing，
绝不静默填错 —— 提问/确认流程负责兜底。
"""

import argparse
import json
import re
import sys


def _setup_console():
    """显式 UTF-8 输出，规避 Windows GBK 控制台把中文打乱（--json 已纯 ASCII，不受影响）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

# ===================== 家族表 =====================
# spl=True：标准外设库(SPL)支持；False：走 HAL/CubeMX
FAMILIES = {
    "F0": {"core": "Cortex-M0",  "fpu": False, "spl": True},
    "F1": {"core": "Cortex-M3",  "fpu": False, "spl": True},
    "F2": {"core": "Cortex-M3",  "fpu": False, "spl": True},
    "F3": {"core": "Cortex-M4F", "fpu": True,  "spl": True},
    "F4": {"core": "Cortex-M4F", "fpu": True,  "spl": True},
    "F7": {"core": "Cortex-M7",  "fpu": True,  "spl": False},
    "L1": {"core": "Cortex-M3",  "fpu": False, "spl": True},
    "L4": {"core": "Cortex-M4F", "fpu": True,  "spl": False},
    "L5": {"core": "Cortex-M33", "fpu": True,  "spl": False},
    "G0": {"core": "Cortex-M0+", "fpu": False, "spl": False},
    "G4": {"core": "Cortex-M4F", "fpu": True,  "spl": False},
    "H7": {"core": "Cortex-M7",  "fpu": True,  "spl": False},
    "U5": {"core": "Cortex-M33", "fpu": True,  "spl": False},
    # 双字母家族（HAL/CubeMX 专属，无 SPL）
    "WB":  {"core": "Cortex-M4F", "fpu": True,  "spl": False},
    "WBA": {"core": "Cortex-M33", "fpu": True,  "spl": False},
    "WL":  {"core": "Cortex-M4F", "fpu": True,  "spl": False},
    "WL3": {"core": "Cortex-M33", "fpu": True,  "spl": False},
    "N6":  {"core": "Cortex-M33", "fpu": True,  "spl": False},
    "W5":  {"core": "Cortex-M33", "fpu": True,  "spl": False},
}

# ===================== 封装字母 → 引脚数 =====================
# 各家族大体一致；个别字母（如 U）随家族变（48 或 176），这里给常见默认。
PACKAGES = {
    "Y": 20, "F": 20, "T": 36, "K": 32, "H": 40, "C": 48, "U": 48,
    "R": 64, "S": 84, "V": 100, "Q": 128, "Z": 144, "I": 176, "A": 169, "B": 208,
    "J": 48,  # WL55 等无线家族的 J=48 脚（WLCSP/UFBGA）
}

# 家族内个别封装覆盖（如 H7/F7 的 U=176、L4 的 U=176）
PACKAGE_OVERRIDES = {
    ("H7", "U"): 176,
    ("F7", "U"): 176,
    ("L4", "U"): 176,
}

# ===================== 最高主频 (MHz) =====================
# 家族级默认值 + 个别产品线覆盖（如 F401=84MHz 而非 F4 的 168）
MAX_FREQ = {
    "F0": 48, "F1": 72, "F2": 120, "F3": 72, "F4": 168,
    "F7": 216, "L1": 32, "L4": 80, "L5": 110, "G0": 64,
    "G4": 170, "H7": 480, "U5": 160,
    "WB": 64, "WBA": 100, "WL": 64, "N6": 800,
}
MAX_FREQ_OVERRIDES = {
    ("F4", "01"): 84,   # F401 系列最高 84MHz
    ("F4", "46"): 180,  # F446 最高 180MHz
    ("H7", "50"): 400,  # H750 最高 400MHz（H743 为 480）
}

# ===================== 密度字母 → Flash (KB) =====================
DENSITY_FLASH = {
    "4": 16, "6": 32, "8": 64, "B": 128, "C": 256,
    "D": 384, "E": 512, "F": 768, "G": 1024, "I": 2048,
}

# ===================== RAM 查表（家族, 产品线）→ 密度→KB 或统一值 =====================
# 值来自各系列数据手册常见配置；未列出的组合返回 None（交给确认流程）。
RAM_BY_LINE = {
    # ---- F1 ----
    ("F1", "03"): {"4": 6, "6": 10, "8": 20, "B": 20, "C": 48, "D": 64, "E": 64, "G": 96},
    ("F1", "05"): {"8": 20, "B": 20, "C": 64, "D": 64, "E": 64},
    ("F1", "07"): {"8": 20, "B": 20, "C": 64, "D": 64, "E": 64},
    ("F1", "00"): {"4": 4, "6": 8, "8": 8, "B": 8, "C": 16, "E": 16},
    # ---- F0（RM0360：x6=4K，x8=8K，xC=16K；注意 line 是"30"不是"03"）----
    ("F0", "30"): {"4": 4, "6": 4, "8": 8, "C": 16},   # F030/F031/F038
    ("F0", "42"): 6,                                   # F042/F048
    ("F0", "51"): 8,                                   # F051/F058
    ("F0", "70"): 16,                                  # F070
    ("F0", "72"): 16,                                  # F072/F078
    ("F0", "91"): 32,                                  # F091/F098
    # ---- F3 ----
    ("F3", "34"): 16,                                    # F334 全系 16K（12K 常规 + 4K CCM）
    ("F3", "03"): {"8": 40, "B": 40, "C": 48, "D": 64, "E": 64},   # F303 全系
    # ---- F4 ----
    ("F4", "01"): {"C": 64, "E": 96},                    # F401
    ("F4", "03"): 192,                                   # F403
    ("F4", "05"): 192,                                   # F405 全系
    ("F4", "07"): 192,                                   # F407 全系（VE/VG/ZE/ZG/IE/IG 均 192K）
    ("F4", "11"): 128,                                   # F411 全系
    ("F4", "27"): {"G": 256, "I": 256},                  # F427/437
    ("F4", "29"): {"G": 256, "I": 256},                  # F429/439
    ("F4", "46"): 128,                                   # F446 全系
    # ---- G4 ----
    ("G4", "31"): 32,                                    # G431/G441
    ("G4", "73"): 128,                                   # G473
    ("G4", "74"): 128,                                   # G474（RM0440: 128K SRAM）
    # ---- H7 / L4 ----
    ("H7", "43"): 992,                                   # H743：AXI512+SRAM1/2/3(320)+ITCM32+DTCM128
    ("H7", "50"): 992,                                   # H750 同封装
    ("L4", "76"): 128,                                   # L476/L486
    # ---- 双字母家族（HAL/CubeMX 专属）----
    ("WB", "55"): 128,                                   # WB55 全系 128K（Cortex-M4F 应用核）
    ("WBA", "55"): 128,                                  # WBA55
    ("WL", "55"): 64,                                    # WL55
    ("W5", "00"): 256,                                   # W5 系列常见值
    ("N6", "00"): 160,                                   # N6 常见值
}


# ===================== 启动文件（SPL 家族） =====================
def _startup_f1(line: str, flash_kb):
    """F1 按产品线 + 密度选启动文件。F105/107=connectivity(cl)，其余按 Flash 密度。"""
    if line in ("05", "07"):
        return "startup_stm32f10x_cl.s"
    if flash_kb is None:
        return None
    if flash_kb <= 32:
        return "startup_stm32f10x_ld.s"
    if flash_kb <= 128:
        return "startup_stm32f10x_md.s"
    if flash_kb <= 512:
        return "startup_stm32f10x_hd.s"
    return "startup_stm32f10x_xl.s"


def _startup_f3(line: str):
    if line == "34":
        return "startup_stm32f334x8.s"
    if line == "37":
        return "startup_stm32f37x.s"
    return "startup_stm32f30x.s"


def _startup_f4(line: str):
    return {
        "01": "startup_stm32f401xcxe.s",
        "03": "startup_stm32f405xx.s",
        "05": "startup_stm32f405xx.s",
        "07": "startup_stm32f407xx.s",
        "11": "startup_stm32f411xe.s",
        "27": "startup_stm32f427_437xx.s",
        "29": "startup_stm32f429_439xx.s",
        "37": "startup_stm32f427_437xx.s",
        "39": "startup_stm32f429_439xx.s",
        "46": "startup_stm32f446xx.s",
        "69": "startup_stm32f469_479xx.s",
        "79": "startup_stm32f469_479xx.s",
    }.get(line)


def _startup(family: str, line: str, flash_kb):
    """SPL 家族返回启动文件名，非 SPL 返回 None（走 HAL/CubeMX）。"""
    if family == "F1":
        return _startup_f1(line, flash_kb)
    if family == "F3":
        return _startup_f3(line)
    if family == "F4":
        return _startup_f4(line)
    if family == "F2":
        return "startup_stm32f2xx.s"
    if family == "F0":
        return "startup_stm32f0xx.s"
    if family == "L1":
        if flash_kb is None:
            return None
        return "startup_stm32l1xx_hd.s" if flash_kb > 256 else "startup_stm32l1xx_md.s"
    return None


# ===================== 解析 =====================
# 密度位可是数字(4/6/8)或字母(B/C/D/E/F/G/I)，故用 [0-9A-Z]
# 完整家族表（含双字母）：与 cubemx_gen.FW_FAMILIES 保持一致，
# 拆解时按长度降序最长前缀匹配（WB 优先于 W，避免误判）。
FAMILY_KEYS = sorted([
    "F0", "F1", "F2", "F3", "F4", "F7", "G0", "G4", "H5", "H7", "H7RS",
    "L0", "L1", "L4", "L5", "U0", "U3", "U5", "N6", "C0", "M0",
    "WB", "WBA", "WB0", "WL", "WL3", "W5",
], key=len, reverse=True)


def normalize_model(model: str) -> str:
    """去空白、转大写；缺 STM32 前缀自动补；剥离 TR 订货后缀。"""
    s = (model or "").strip().upper()
    if not s:
        return ""
    if not s.startswith("STM32"):
        s = "STM32" + s
    # TR（Tape & Reel 卷带）是订购后缀，不是型号主体：
    # STM32F103C8T6TR → STM32F103C8T6。合法型号主体以等级数字/变体字母
    # （6/7/3/6B）结尾，故 strip 尾部 TR 安全，且让带 TR 的完整订货号
    # 也能命中 ioc 模板库（模板文件用主体命名）。
    if s.endswith("TR"):
        s = s[:-2]
    return s


def split_model(model: str) -> dict:
    """型号拆解（权威实现，双字母家族 WB/WL/WBA/N6 等也支持）。

    家族用 FAMILY_KEYS 最长前缀匹配；型号结构：
    STM32 + 家族 + 数字串(numeric) + 封装引脚字母 + 密度 + 封装类型字母 + 等级数字
    [+ 变体字母后缀]。变体如 F100 的 `B`（STM32F100C4T6B）、TR 已在 normalize 剥掉。
    返回 {family, series, line, numeric, package, density, temp, grade}；
    拆不出返回 {}（不抛异常）。
    parse_model 与 make_ioc.mcu_fields 共用本函数，避免两处正则漂移。
    """
    upper = normalize_model(model)
    if not upper:
        return {}
    body = upper[5:]
    family = next((f for f in FAMILY_KEYS if body.startswith(f)), None)
    if not family:
        return {}
    rest = body[len(family):]
    # 尾组 (\d[A-Z]*)：等级数字开头，可带变体字母（F100 的 "6B"）；整体可缺。
    m = re.match(r"^(\d+)([A-Z])([0-9A-Z])([A-Z])(\d[A-Z]*)?$", rest)
    if not m:
        return {}
    numeric, package, density, temp, grade = m.groups()
    # line 取数字串后两位（对齐原 MODEL_RE 的 series(1位)+line(2位)）：
    # family 已含系列号（F1 含"1"），F103 的 rest 数字串只剩 "03" → line="03"。
    line = numeric[-2:] if len(numeric) >= 2 else numeric
    return {
        "family": family,
        "series": numeric[0],
        "line": line,
        "numeric": numeric,
        "package": package,
        "density": density,
        "temp": temp,
        "grade": grade or "",
    }


def parse_model(model: str) -> dict:
    """解析完整型号 → 结构化规格。解析不出/查不到的不崩溃，返回 missing 列表。"""
    original = (model or "").strip().upper()   # 保留原始输入（检测 TR 订货后缀）
    model = normalize_model(model)
    result = {
        "model": model,
        "family": None,
        "family_label": None,
        "line": None,
        "core": None,
        "fpu": None,
        "spl": None,
        "max_freq_mhz": None,
        "package": None,
        "pins": None,
        "density": None,
        "flash_kb": None,
        "ram_kb": None,
        "startup": None,
        "missing": [],
        "note": "",
    }

    if not model:
        result["missing"] = ["model"]
        return result

    s = split_model(model)
    if not s:
        result["note"] = ("无法解析：需要形如 STM32F103CBT6 的完整型号 "
                          "（家族+系列+封装+密度+温度+等级）")
        result["missing"] = ["family", "core", "pins", "flash_kb", "ram_kb", "startup"]
        return result

    family = s["family"]
    result["family"] = family
    result["family_label"] = "STM32" + family
    result["line"] = s["line"]
    result["package"] = s["package"]
    result["density"] = s["density"]
    result["model"] = "STM32" + family + s["numeric"] + s["package"] + s["density"] + s["temp"] + s["grade"]

    fam = FAMILIES.get(family)
    if fam:
        result["core"] = fam["core"]
        result["fpu"] = fam["fpu"]
        result["spl"] = fam["spl"]
        result["max_freq_mhz"] = MAX_FREQ_OVERRIDES.get((family, s["line"])) or MAX_FREQ.get(family)
    else:
        result["missing"].append("family")

    result["pins"] = PACKAGE_OVERRIDES.get((family, s["package"])) or PACKAGES.get(s["package"])

    result["flash_kb"] = DENSITY_FLASH.get(s["density"])

    ram_rule = RAM_BY_LINE.get((family, s["line"]))
    if isinstance(ram_rule, int):
        result["ram_kb"] = ram_rule
    elif isinstance(ram_rule, dict):
        result["ram_kb"] = ram_rule.get(s["density"])
    else:
        result["ram_kb"] = None

    result["startup"] = _startup(family, s["line"], result["flash_kb"]) if fam else None

    # 非 SPL 家族补一句说明
    if fam and not fam["spl"]:
        result["note"] = "此家族无标准外设库(SPL)，建议用 CubeMX/HAL 生成工程"

    for key in ("core", "pins", "flash_kb", "ram_kb"):
        if result[key] is None:
            result["missing"].append(key)
    # 非 SPL 家族无启动文件概念（走 HAL/CubeMX 自生成），不算缺失
    if result["spl"] and result["startup"] is None:
        result["missing"].append("startup")
    if not result["missing"]:
        result["missing"] = []

    # 输入带 TR 订货后缀时提示已剥离（如 STM32F103C8T6TR → 按 STM32F103C8T6 解析）
    if original.endswith("TR"):
        result["note"] = (result["note"] + "；已剥离 TR 订货后缀").strip("；")

    return result


# ===================== CLI =====================
def human(info: dict) -> str:
    lines = []
    lines.append(f"型号: {info['model']}")
    lines.append(f"家族: {info['family']} | 产品线: {info['line']} | 密度: {info['density']}")
    lines.append(f"核心: {info['core']} | FPU: {'有' if info['fpu'] else '无'}"
                 f" | 最高主频: {info['max_freq_mhz']}MHz"
                 f" | SPL: {'支持' if info['spl'] else '不支持(走 HAL/CubeMX)'}")
    lines.append(f"封装: {info['package']} | 引脚: {info['pins'] if info['pins'] else '未知'}")
    lines.append(f"Flash: {info['flash_kb']}K | RAM: {info['ram_kb']}K")
    lines.append(f"启动文件: {info['startup'] or 'N/A(非 SPL)'}")
    if info["note"]:
        lines.append(f"提示: {info['note']}")
    if info["missing"]:
        lines.append("⚠️ 缺字段(需用户确认/补充): " + ", ".join(info["missing"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    _setup_console()
    ap = argparse.ArgumentParser(
        prog="mcu_knowledge.py",
        description="STM32 型号知识库：解析完整型号 → 核心/FPU/引脚/Flash/RAM/启动文件",
        epilog="示例: python mcu_knowledge.py --query STM32F103CBT6 [--json]",
    )
    ap.add_argument("--query", metavar="MODEL", help="完整型号，如 STM32F103CBT6（可省略 STM32 前缀）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 Claude 解析用）")
    ap.add_argument("--list-families", action="store_true", help="列出支持的家族")
    args = ap.parse_args(argv)

    if args.list_families:
        for fam, meta in FAMILIES.items():
            print(f"{fam:>3}  {meta['core']:<11} FPU={'Y' if meta['fpu'] else 'N'} "
                  f"SPL={'Y' if meta['spl'] else 'N'}")
        return 0

    if not args.query:
        ap.error("需要 --query <型号>（或 --list-families）")

    info = parse_model(args.query)
    if args.json:
        # ensure_ascii=True：纯 ASCII，规避 Windows 控制台 GBK/UTF-8 乱码，Claude 解析可靠
        print(json.dumps(info, ensure_ascii=True, indent=2))
    else:
        print(human(info))
    return 0


if __name__ == "__main__":
    sys_exit = __import__("sys").exit
    sys_exit(main())
