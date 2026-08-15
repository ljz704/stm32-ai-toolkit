#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new_project.py —— STM32 工程脚手架生成器
==========================================
从 templates/project/ 渲染模板生成新 STM32 工程骨架，
或给已有 Keil 工程补装 AI 辅助层（--existing）。

用法：
  python new_project.py [--name <项目名>] [--mcu <型号>] [--dir <目录>]
                        [--template f1xx_general|f3xx_digital_power|f4xx_spl]
                        [--no-cubemx] [--no-git] [--no-hooks] [--existing]
                        [--repair] [--query-mcu <型号>] [--json] [--yes]

说明：
  - **CubeMX 优先（默认路径，全家族统一）**：默认不传 --template 时，对任何型号
    都走 make_ioc.py（型号→最小 .ioc，RCC 时钟块取自官方示例/内置模板）
    + cubemx_gen.py（无头生成完整 HAL 工程：Core/Drivers/MDK-ARM + .uvprojx），
    生成后自动补装 AI 辅助层。不再区分 SPL / 非 SPL 家族——一律 CubeMX/HAL。
  - 若该型号缺固件包 / 无 RCC 来源等导致生成失败 → 自动退化为 config-only 骨架
    （只生成 CLAUDE.md/.claude/hardware.yaml），并给出明确提示。
  - --template <模板名>：**SPL 旧路径**（可选/遗留）。按家族选 SPL 模板生成
    src/inc/MDK-ARM 骨架：F1→f1xx_general、F3→f3xx_digital_power、F4/F2→f4xx_spl；
    其他家族传 --template 无匹配 → 退 config-only。
  - --no-cubemx：跳过 CubeMX 尝试，直接 config-only 骨架（纯 AI 层，不生成代码）。
  - --query-mcu <型号>：只打印解析规格，不建工程（给 /newproject 对话预览确认用）。
  - 占位符用 str.replace 渲染：{{PROJECT_NAME}}、{{MCU_MODEL}}、{{MDK_PROJECT}}、
    {{KEIL_UV4}}、settings.json.template 里的 {{TOOLKIT_PATH}}，以及 mcu_knowledge
    解析出的 {{MCU_CORE/FLASH/RAM/FPU/STARTUP/MAX_FREQ/PINS/PACKAGE/DENSITY/FAMILY_LABEL/SPL}}。
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR / "templates" / "project"
TOOLKIT_PATH = str(SCRIPT_DIR).replace("\\", "/")


def _detect_keil_uv4() -> str:
    """检测 Keil UV4.exe：优先 KEIL_PATH 环境变量 → Windows 注册表 → 常见默认路径。

    返回的路径用于渲染模板里的编译命令占位符 {{KEIL_UV4}}；
    探测不到时退回 C:\\Keil_v5 常见默认，避免模板里出现空路径。
    注册表探测与 install.py 共用（_probe_keil_from_registry），保证同机结果一致。
    """
    env = os.environ.get("KEIL_PATH")
    if env:
        return env
    try:
        from install import _probe_keil_from_registry  # 复用 install.py 的注册表探测
        reg = _probe_keil_from_registry()
        if reg:
            return reg
    except Exception:
        pass  # 注册表探测失败时退回默认路径
    for p in (
        Path(r"C:\Keil_v5\UV4\UV4.exe"),
        Path(r"D:\Keil_v5\UV4\UV4.exe"),
        Path(r"C:\Keil\UV4\UV4.exe"),
    ):
        if p.exists():
            return str(p)
    return str(Path(r"C:\Keil_v5\UV4\UV4.exe"))


KEIL_UV4 = _detect_keil_uv4()

DEFAULT_NAME = "project"
DEFAULT_MCU = "STM32F103C8T6"
F1_TEMPLATE = "f1xx_general"
F3_TEMPLATE = "f3xx_digital_power"
F4_TEMPLATE = "f4xx_spl"       # 新增：F4/F2 用（M4F 移植文件）

# 家族 → SPL 模板名（只列出有专用 src/inc 模板的家族）
TEMPLATE_BY_FAMILY = {
    "F1": F1_TEMPLATE,
    "F3": F3_TEMPLATE,
    "F4": F4_TEMPLATE,
    "F2": F4_TEMPLATE,          # F2 与 F4 同为 M4 系 SPL，暂复用 f4xx 移植文件
}
# 其他 SPL 家族（F0/L1）没有专用模板 → config-only；非 SPL 家族一律 config-only。

MEMORY_FILES = ("architecture.md", "pin_usage.md", "known_issues.md", "session_log.md")

MCU_RE = re.compile(r"STM32[FGLHUC]\d{2}[A-Z0-9]+", re.IGNORECASE)

sys.path.insert(0, str(SCRIPT_DIR))
from _cmdutil import fix_console_encoding, run_cmd  # noqa: E402
import mcu_knowledge  # noqa: E402


# ===================== 输出 =====================
def ok(msg):    print(f"[OK]   {msg}")
def warn(msg):  print(f"[WARN] {msg}")
def info(msg):  print(f"[INFO] {msg}")
def err(msg):   print(f"[ERR]  {msg}")


# ===================== 交互提问 =====================
class Prompter:
    """交互提问器。auto=True 时直接用默认值，不阻塞 stdin。"""

    def __init__(self, auto: bool):
        self.auto = auto

    def ask(self, label: str, default: str) -> str:
        if self.auto:
            return default
        try:
            raw = input(f"{label} [{default}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return default
        return raw if raw else default

    def ask_yesno(self, label: str, default: bool = True) -> bool:
        hint = "y" if default else "n"
        if self.auto:
            return default
        try:
            raw = input(f"{label} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        return default


# ===================== 型号知识库对接 =====================
def select_template(mcu_info: dict):
    """按家族选 SPL 模板名；config-only 家族返回 None。"""
    fam = mcu_info["family"]
    if not fam:
        warn("无法识别型号家族，回退 f1xx_general 模板")
        return F1_TEMPLATE
    if mcu_info["spl"] is False:
        return None                    # 非 SPL：走 CubeMX/HAL，config-only
    return TEMPLATE_BY_FAMILY.get(fam)  # F0/L1 等无专用模板 → None → config-only


def mcu_tokens_from_info(mcu_info: dict) -> dict:
    """把 mcu_knowledge 解析结果转成模板替换表。

    None 值（缺失字段）填 "TBD"（待确认）；非 SPL 家族的 startup 填 "N/A"
    （HAL/CubeMX 自生成，无启动文件概念）。
    """
    def s(v, na="TBD"):
        if v is None:
            return na
        if isinstance(v, bool):
            return "true" if v else "false"
        return str(v)

    startup = "N/A" if (mcu_info["spl"] is False) else s(mcu_info["startup"])

    # 时钟推导：按型号主频 + 家族 APB 分频惯例（避免写死 72MHz 导致 AI 误判）。
    # 仅是"合理默认"，注释已提示按实际时钟树确认；HSE 仍默认 8MHz（用户可用 --hse-mhz 指定）。
    max_freq = mcu_info.get("max_freq_mhz")
    fam = (mcu_info.get("family") or "").upper()
    sysclk = max_freq if max_freq else "TBD"
    hclk = sysclk
    # APB 分频惯例：F1 常用 /1 或 /2；F3/F4/G4/H7 常用 /2（H7 更复杂，标 TBD 更安全）
    if fam == "F1":
        pclk1, pclk2 = "36", "72"          # F1 典型 APB1/2 分频
    elif fam in ("F0", "G0"):
        pclk1 = pclk2 = s(min(max_freq, 48) if max_freq else None)
    elif fam in ("F3", "F4", "G4", "L4", "L5", "U5", "F7"):
        pclk1 = s(round(max_freq / 2)) if max_freq else "TBD"
        pclk2 = s(max_freq) if max_freq else "TBD"
    elif fam == "H7":
        # H7 时钟树复杂（AXI/APB 多级），不猜，标 TBD 让用户填
        pclk1 = pclk2 = "TBD"
    else:
        pclk1 = pclk2 = s(max_freq) if max_freq else "TBD"

    return {
        "{{MCU_MODEL}}": mcu_info["model"] or "N/A",
        "{{MCU_FAMILY_LABEL}}": s(mcu_info["family_label"]),
        "{{MCU_CORE}}": s(mcu_info["core"]),
        "{{MCU_MAX_FREQ}}": s(mcu_info["max_freq_mhz"]),
        "{{MCU_FLASH_KB}}": s(mcu_info["flash_kb"]),
        "{{MCU_RAM_KB}}": s(mcu_info["ram_kb"]),
        "{{MCU_HAS_FPU}}": s(mcu_info["fpu"]),
        "{{MCU_PACKAGE}}": s(mcu_info["package"]),
        "{{MCU_PINS}}": s(mcu_info["pins"]),
        "{{MCU_DENSITY}}": s(mcu_info["density"]),
        "{{MCU_STARTUP}}": startup,
        "{{MCU_SPL}}": "true" if mcu_info["spl"] else "false",
        "{{MCU_SPL_TEXT}}": "标准外设库(SPL)" if mcu_info["spl"] else "HAL/CubeMX（无 SPL）",
        "{{MCU_SYSCLK}}": s(sysclk),
        "{{MCU_HCLK}}": s(hclk),
        "{{MCU_PCLK1}}": s(pclk1),
        "{{MCU_PCLK2}}": s(pclk2),
    }


# ===================== 渲染与推断 =====================
def render(text: str, project_name: str, mcu_model: str, mdk_project: str,
           toolkit_path: str = TOOLKIT_PATH, keil_uv4: str = KEIL_UV4,
           mcu_tokens: dict = None, mdk_dir: str = "MDK-ARM") -> str:
    """渲染模板占位符（str.replace；未出现的占位符原样保留）。

    mcu_tokens: mcu_tokens_from_info() 的输出（{{MCU_*}} 替换表）。
    mdk_dir: uvprojx 所在目录相对路径（新工程默认 MDK-ARM；--existing 按实际探测）。
    """
    text = text.replace("{{PROJECT_NAME}}", project_name)
    text = text.replace("{{MCU_MODEL}}", mcu_model)
    text = text.replace("{{MDK_PROJECT}}", mdk_project)
    text = text.replace("{{MDK_DIR}}", mdk_dir)
    text = text.replace("{{TOOLKIT_PATH}}", toolkit_path)
    text = text.replace("{{KEIL_UV4}}", keil_uv4)
    if mcu_tokens:
        for token, val in mcu_tokens.items():
            text = text.replace(token, val)
    return text


def template_io_files(template: str):
    """按模板返回 src/inc 差异文件名（it.c, conf.h）。"""
    if template == F3_TEMPLATE:
        return "stm32f3xx_it.c", "stm32f3xx_conf.h"
    if template == F4_TEMPLATE:
        return "stm32f4xx_it.c", "stm32f4xx_conf.h"
    return "stm32f10x_it.c", "stm32f10x_conf.h"


def find_existing_mdk_project(target: Path):
    """--existing 模式：探测工程真实的 .uvprojx（名字 + 所在目录）。

    查找顺序：MDK-ARM/ 子目录 → 工程根目录 → 任意层级（rglob 兜底）。
    返回 (stem, rel_dir)（rel_dir 如 "MDK-ARM" / "."）；找不到返回 None。
    有了它，编译命令里的工程路径就不会错写成默认项目名/错误目录。
    """
    target = Path(target)
    candidates = []
    mdk_dir = target / "MDK-ARM"
    if mdk_dir.is_dir():
        candidates += sorted(mdk_dir.glob("*.uvprojx"))
    candidates += sorted(target.glob("*.uvprojx"))
    if not candidates:
        candidates = sorted(target.rglob("*.uvprojx"))
    for p in candidates:
        return p.stem, p.parent.relative_to(target).as_posix() or "."
    return None


def read_mcu_from_claude(target: Path):
    """从已有 CLAUDE.md 尝试读取 MCU 型号。"""
    claude = Path(target) / "CLAUDE.md"
    if not claude.exists():
        return None
    try:
        content = claude.read_text(encoding="utf-8")
    except OSError:
        return None
    m = MCU_RE.search(content)
    return m.group(0).upper() if m else None


def render_to_file(src: Path, dst: Path, **kwargs) -> bool:
    """渲染模板写入目标文件；目标已存在则跳过。返回是否写入。"""
    if dst.exists():
        return False
    if not src.exists():
        warn(f"未找到模板: {src}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = render(src.read_text(encoding="utf-8"), **kwargs)
    dst.write_text(text, encoding="utf-8")
    return True


# ===================== AI 环境（Claude Code / DSH 双轨） =====================
def resolve_env(env_arg) -> str:
    """解析目标 AI 环境：--env 显式 > 环境变量 STM32_TOOLKIT_ENV > 默认 claude。

    claude：.claude/memory + @ 自动导入 + hooks 默认生成（Claude Code 风格）；
    dsh：   .dsh/memory + 显式路径引用 + 无 hooks（DeepSeek Harness 风格）。
    """
    if env_arg:
        return env_arg
    if os.environ.get("STM32_TOOLKIT_ENV", "").strip().lower() == "dsh":
        return "dsh"
    return "claude"


def memory_rel_dir(env: str) -> Path:
    """按 AI 环境返回工程内 memory 目录相对路径（claude→.claude/memory，dsh→.dsh/memory）。"""
    return Path(".claude" if env == "claude" else ".dsh") / "memory"


def claude_template_for(env: str) -> Path:
    """按 AI 环境选 CLAUDE.md 模板：claude→@ 自动导入版，dsh→显式路径版。"""
    return TEMPLATES_DIR / ("CLAUDE.md.dsh.template" if env == "dsh" else "CLAUDE.md.template")


# ===================== 生成逻辑 =====================
def generate_full_skeleton(target: Path, project_name: str, mcu_model: str,
                           template: str, mdk_project: str, do_hooks: bool,
                           mcu_tokens: dict, full: bool = True,
                           env: str = "claude") -> list:
    """生成工程骨架。

    full=True：含 src/inc/MDK-ARM（SPL 移植文件，需 template）。
    full=False：config-only，只生成 CLAUDE.md / hardware.yaml / memory。
    env="claude"→.claude/memory + @ 导入 + hooks 默认；env="dsh"→.dsh/memory + 显式路径。
    返回创建的文件列表。
    """
    created = []

    files = [
        (claude_template_for(env),    target / "CLAUDE.md"),
        (TEMPLATES_DIR / "hardware.yaml.blank",   target / "hardware.yaml"),
    ]
    if full and template:
        it_c, conf_h = template_io_files(template)
        files += [
            (TEMPLATES_DIR / "src" / "main.c",        target / "src" / "main.c"),
            (TEMPLATES_DIR / "src" / it_c,            target / "src" / it_c),
            (TEMPLATES_DIR / "inc" / "main.h",        target / "inc" / "main.h"),
            (TEMPLATES_DIR / "inc" / conf_h,          target / "inc" / conf_h),
            (TEMPLATES_DIR / "MDK-ARM" / "README.md", target / "MDK-ARM" / "README.md"),
        ]

    for src, dst in files:
        kwargs = dict(project_name=project_name, mcu_model=mcu_model,
                      mdk_project=mdk_project, mcu_tokens=mcu_tokens, mdk_dir="MDK-ARM")
        if render_to_file(src, dst, **kwargs):
            created.append(dst)

    # 记忆文件放 memory_rel_dir(env)（claude→.claude/memory，dsh→.dsh/memory）
    for mem in MEMORY_FILES:
        dst = target / memory_rel_dir(env) / mem
        if render_to_file(TEMPLATES_DIR / "memory" / mem, dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project, mcu_tokens=mcu_tokens):
            created.append(dst)

    if do_hooks:
        # 仅 Claude Code 需要 hooks（DSH 无 PreToolUse/PostToolUse 机制）。
        # claude 环境默认生成；dsh 环境仅显式 --hooks 时生成（见 main）。
        dst = target / ".claude" / "settings.json"
        if render_to_file(TEMPLATES_DIR / "settings.json.template", dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project, mcu_tokens=mcu_tokens):
            created.append(dst)

    return created


def run_cubemx_flow(target: Path, project_name: str, mcu_model: str,
                    hse_hz: int = 8_000_000) -> dict:
    """CubeMX 优先路径：make_ioc（型号→最小 .ioc）→ 无头生成完整 HAL 工程。

    生成直接输出到 target（HAL 的 Core/Drivers/MDK-ARM 落进目标目录，不套 cubemx_out/）。
    返回 dict：{ok, ioc?, gen?, error?, error_type?}。
    失败（缺固件包 / 无 RCC 来源 / 超时）时 ok=False 带可读 error，由调用方退化为
    config-only 骨架。惰性 import，避免拖慢 --query-mcu / --repair / --existing。
    """
    from make_ioc import make_ioc
    from cubemx_gen import generate, DEFAULT_TIMEOUT

    result = {"ok": False}
    info(f"第 1 步: make_ioc 生成最小 .ioc（型号 {mcu_model}）...")
    r = make_ioc(mcu_model, project_name=project_name, hse_hz=hse_hz)
    if not r.get("ok"):
        result["error"] = r.get("error", "make_ioc 失败")
        result["error_type"] = r.get("error_type")
        err(result["error"])
        return result

    ioc_path = target / f"{project_name}.ioc"
    ioc_path.write_text(r["ioc"], encoding="utf-8")
    result["ioc"] = ioc_path
    ok(f"  {ioc_path.name}（MCU={r.get('mcu_name')}，固件包={r.get('fw')}）")
    if r.get("clock_note"):
        info(f"  时钟: {r['clock_note']}")

    info(f"第 2 步: CubeMX 无头生成（输出到 {target}，首次 3 分钟+ 耐心等待）...")
    gen = generate(ioc_path, out_dir=target, timeout=DEFAULT_TIMEOUT, in_place=False)
    result["gen"] = gen
    if not gen.get("success"):
        result["error"] = gen.get("error") or "CubeMX 生成失败"
        result["error_type"] = gen.get("error_type")
        err(result["error"])
        return result
    result["ok"] = True
    return result


def install_existing_layer(target: Path, project_name: str, mcu_model: str,
                           mdk_project: str, do_hooks: bool, mcu_tokens: dict,
                           env: str = "claude", mdk_dir: str = "MDK-ARM") -> list:
    """给已有 Keil 工程补装 AI 辅助层，返回创建/更新的文件列表。

    env="claude"→.claude/memory + @ 导入版 CLAUDE.md；env="dsh"→.dsh/memory + 显式路径版。
    mdk_dir：探测到的 uvprojx 所在目录（相对工程根），编译命令按实际位置渲染。
    CLAUDE.md 为覆盖渲染；若已有文件内容不同（用户/AI 定制过），先备份再覆盖。
    """
    touched = []

    # CLAUDE.md：生成/更新（覆盖渲染，内容不同则先备份）
    claude_src = claude_template_for(env)
    claude_dst = target / "CLAUDE.md"
    if claude_src.exists():
        claude_dst.parent.mkdir(parents=True, exist_ok=True)
        text = render(claude_src.read_text(encoding="utf-8"),
                      project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project,
                      mcu_tokens=mcu_tokens, mdk_dir=mdk_dir)
        if claude_dst.exists():
            try:
                old = claude_dst.read_text(encoding="utf-8")
            except OSError:
                old = None
            if old is not None and old != text:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = claude_dst.with_name(f"CLAUDE.md.bak_{ts}")
                try:
                    claude_dst.rename(bak)
                    info(f"已备份旧 CLAUDE.md -> {bak.name}")
                except OSError as e:
                    warn(f"备份旧 CLAUDE.md 失败（{e}），跳过覆盖")
                    return touched
        claude_dst.write_text(text, encoding="utf-8")
        touched.append(claude_dst)
    else:
        warn(f"未找到模板: {claude_src}，跳过 CLAUDE.md")

    # memory 空白模板：已存在不覆盖（目录按 env：claude→.claude/memory，dsh→.dsh/memory）
    for mem in MEMORY_FILES:
        dst = target / memory_rel_dir(env) / mem
        if render_to_file(TEMPLATES_DIR / "memory" / mem, dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project, mcu_tokens=mcu_tokens):
            touched.append(dst)

    # hardware.yaml：不存在才生成（mcu 块按解析出的规格填充）
    hw_dst = target / "hardware.yaml"
    if render_to_file(TEMPLATES_DIR / "hardware.yaml.blank", hw_dst,
                      project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project,
                      mcu_tokens=mcu_tokens):
        touched.append(hw_dst)

    # settings.json：仅 Claude Code hooks（DSH 无 hooks 机制）；生成/更新（覆盖，TOOLKIT_PATH 可能变化）
    if do_hooks:
        settings_src = TEMPLATES_DIR / "settings.json.template"
        settings_dst = target / ".claude" / "settings.json"
        if settings_src.exists():
            settings_dst.parent.mkdir(parents=True, exist_ok=True)
            text = render(settings_src.read_text(encoding="utf-8"),
                          project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project,
                          mcu_tokens=mcu_tokens)
            settings_dst.write_text(text, encoding="utf-8")
            touched.append(settings_dst)
        else:
            warn(f"未找到 hooks 模板: {settings_src}，跳过 settings.json")

    return touched


def repair_hooks(target: Path, project_name: str, mcu_model: str, mdk_project: str) -> list:
    """把已有工程 .claude/settings.json 的 hooks 路径刷新到当前工具包（Claude Code 兼容用）。

    用途：工具包被移动 / 换电脑 clone 后，工程里 settings.json 仍指向旧路径，
    hooks 静默失效。本函数只动 settings.json，不碰 CLAUDE.md / memory / hardware.yaml。
    DSH 无 hooks 机制，此修复仅对继续使用 Claude Code 的工程有意义。

    保守策略：
      - settings.json 不存在或未引用本工具包 hooks（无 "scripts/hooks"）→ 视为用户自定义配置，跳过；
      - 已指向当前工具包 → 跳过；
      - 需要修复 → 先把旧文件改名备份（settings.json.bak_<时间戳>），再按模板重渲染。

    返回处理的文件列表（未处理/跳过时为空）。
    """
    p = target / ".claude" / "settings.json"
    if not p.exists():
        warn(f"{target} 没有 .claude/settings.json，无需修复")
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        warn(f"无法读取 {p}，跳过")
        return []

    if "scripts/hooks" not in text and "scripts\\hooks" not in text:
        warn(f"{target}/.claude/settings.json 未引用本工具包 hooks，视为自定义配置，跳过")
        return []

    cur_fwd = TOOLKIT_PATH
    if cur_fwd in text or cur_fwd.replace("/", "\\") in text:
        info(f"{target} hooks 已指向当前工具包，无需修复")
        return []

    src = TEMPLATES_DIR / "settings.json.template"
    if not src.exists():
        warn(f"缺少 hooks 模板: {src}")
        return []

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(f"settings.json.bak_{ts}")
    try:
        p.rename(bak)
    except OSError as e:
        warn(f"备份旧 settings.json 失败（{e}），跳过")
        return []

    p.parent.mkdir(parents=True, exist_ok=True)
    rendered = render(src.read_text(encoding="utf-8"),
                      project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project,
                      toolkit_path=TOOLKIT_PATH)
    p.write_text(rendered, encoding="utf-8")
    ok(f"已修复 {target}/.claude/settings.json hooks 路径 -> {cur_fwd}（旧文件备份为 {bak.name}）")
    return [p]


def analyze_hw(target: Path) -> None:
    """工程硬件分析（方案 B），按工程类型分流：

    - HAL/CubeMX 工程（有 Core/Src）：优先静态提取脚本（结构规整，脚本可靠），
      生成 hardware.yaml.draft / pin_usage.md.draft / ai_review_notes.md；
      脚本一旦跑不通（缺文件/异常/超时/退出码非 0/无草稿产物）→ 自动降级为
      AI 直读方案，不硬跑、不静默跳过。
    - 传统 SPL 工程（无 Core，目录结构千变万化）：不跑脚本——AI 直接完整读取
      源码填写硬件档案，再双子代理交叉验证后定稿（脚本对 SPL 变体覆盖不可靠）。
    """

    def ai_direct(reason: str) -> None:
        warn(f"静态提取脚本未使用（{reason}）→ 改为 AI 直读方案")
        info("  流程：AI 读代码 → 双子代理交叉验证 → 定稿（无需 analyze_hw.py）")
        info("  说明：AI 直接完整读取源码（main.c / 外设 .c / uvprojx）填写 hardware.yaml 与 pin_usage.md")

    # SPL 检测：无 Core/Src 且无 Core/Inc → 判定 SPL（或未知结构），走 AI 直读
    is_hal_like = (target / "Core" / "Src").exists() or (target / "Core" / "Inc").exists()
    if not is_hal_like:
        info(f"检测到非 CubeMX 结构工程（{target}），跳过静态提取脚本")
        ai_direct("非 CubeMX/SPL 结构，脚本对变体目录覆盖不可靠")
        return

    script = SCRIPT_DIR / "analyze_hw.py"
    if not script.exists():
        ai_direct(f"未找到 analyze_hw.py（{script}）")
        return
    info(f"静态提取工程硬件配置（{target}）...")
    try:
        result = run_cmd([sys.executable, str(script), str(target)], timeout=60)
    except Exception as exc:  # run_cmd 设计上不抛，兜底防未来改动
        ai_direct(f"脚本执行异常: {exc}")
        return
    if result.error or result.timed_out:
        ai_direct(f"脚本失败: {result.error or result.combined}")
        return
    if result.returncode != 0:
        ai_direct(f"脚本退出码 {result.returncode}:\n{result.combined}")
        return
    drafts = [p for p in ("hardware.yaml.draft", "pin_usage.md.draft", "ai_review_notes.md")
              if (target / p).exists()]
    if not drafts:
        ai_direct("脚本退出码 0 但未产出任何草稿文件")
        return
    ok("硬件分析完成，草稿已生成")
    info("  hardware.yaml.draft / pin_usage.md.draft / ai_review_notes.md")
    info("  下一步: AI 读 ai_review_notes.md 复核，必要时双子代理交叉验证后定稿")


# ===================== 辅助 =====================
def do_git_init(target: Path) -> None:
    info("执行 git init ...")
    old = Path.cwd()
    os.chdir(target)
    try:
        result = run_cmd(["git", "init"], timeout=60)
    finally:
        os.chdir(old)
    if result.ok:
        ok("git init 完成")
    else:
        warn(f"git init 未成功: {result.combined.strip() or result.error}")


def print_next_steps(target: Path, template: str, mcu_info: dict = None,
                     cubemx_ok: bool = False, env: str = "claude",
                     existing: bool = False) -> None:
    print()
    info("=" * 58)
    # AI 环境提示语：claude→Claude Code /build；dsh→DSH 说编译
    if env == "dsh":
        open_hint = f"进 {target} 用 DSH 打开，说\"编译当前工程\"（MCP keil_build 自动编译）"
        build_hint = "用 DSH 打开说\"编译当前工程\"验证编译"
    else:
        open_hint = f"进 {target} 打开 Claude Code，运行 /build 验证编译"
        build_hint = "进入 Claude Code 打开该目录，运行 /build 验证编译"
    if existing:
        # 已有工程补装完成：先看有没有硬件分析草稿待定稿，再编译验证
        drafts = [p for p in ("hardware.yaml.draft", "pin_usage.md.draft", "ai_review_notes.md")
                  if (Path(target) / p).exists()]
        info("下一步（已有工程补装完成）：")
        if drafts:
            info("  1. ⚠️ 存在硬件分析草稿（hardware.yaml.draft / ai_review_notes.md）→ **先完成定稿**：")
            info("     AI 读 ai_review_notes.md 复核 + 完整读源码 + 双子代理交叉验证后，")
            info("     写正式 hardware.yaml / memory/pin_usage.md，并删除/归档草稿")
        else:
            info("  1. 检查 CLAUDE.md / hardware.yaml / memory 是否反映实际工程（未填项补全）")
        info(f"  2. {build_hint}")
        info("  3. 编译 0 Error 后 git 提交")
        info("=" * 58)
        return
    if cubemx_ok:
        info("下一步（CubeMX 已生成完整 HAL 工程）：")
        info(f"  1. {open_hint}")
        info("  2. 需配置引脚/外设时，用 CubeMX GUI 打开同目录 <工程名>.ioc 调整后重新生成")
        info("  3. hardware.yaml 的 clock / 外设表按实际板卡补充")
        info("  4. git init 并首次提交（若未在本脚本执行）")
        info("=" * 58)
        return
    if template is None:
        # config-only 骨架
        if mcu_info and mcu_info["spl"] is False:
            info("下一步（非 SPL 家族，建议 CubeMX/HAL 生成）：")
            info(f"  1. STM32CubeMX 配置 {mcu_info['model']} 并生成工程到 {target}/")
            info("  2. 生成后补装 AI 辅助层:")
            info(f"     python install.py --project {target}")
            info("     （补装 CLAUDE.md / memory / hardware.yaml，规格已按型号填好）")
        else:
            info("下一步（config-only 骨架，无 SPL 移植文件）：")
            info(f"  1. 用 STM32CubeMX 生成 {target}/ 下工程（Core/Drivers/MDK-ARM）")
            info(f"  2. 生成后补装 AI 辅助层: python install.py --project {target}")
        info("=" * 58)
        return
    it_c, _ = template_io_files(template)
    info("下一步：")
    info(f"  1. 用 Keil 向导 / CubeMX 在 {target}/MDK-ARM 生成 .uvprojx 工程")
    info(f"  2. 加入源文件: src/main.c、src/{it_c}、ST 库 system 文件，Include Paths 加 inc/")
    info(f"  3. {build_hint}")
    info("  4. git init 并首次提交（若未在本脚本执行）")
    info("=" * 58)


# ===================== CLI =====================
def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="new_project.py",
        description="STM32 工程脚手架：按型号生成新工程骨架，或给已有 Keil 工程补装 AI 辅助层",
        epilog="示例: python new_project.py --name meter --mcu STM32F103C8T6 --yes",
    )
    ap.add_argument("--name", help=f"项目名（默认 {DEFAULT_NAME}）")
    ap.add_argument("--mcu", help="MCU 完整型号，如 STM32F103CBT6 / STM32F334C8T6 / STM32G431CBT6")
    ap.add_argument("--dir", help="目标目录（默认 ./<项目名>）")
    ap.add_argument("--template", choices=[F1_TEMPLATE, F3_TEMPLATE, F4_TEMPLATE],
                    help=f"SPL 旧路径模板（传了就不走 CubeMX；默认按 MCU 家族推断："
                         f"F1→{F1_TEMPLATE}，F3→{F3_TEMPLATE}，F4/F2→{F4_TEMPLATE}；"
                         f"F0/L1/非 SPL → config-only）")
    ap.add_argument("--no-cubemx", action="store_true",
                    help="跳过 CubeMX 无头生成，直接建 config-only 骨架（不生成代码）")
    ap.add_argument("--hse-mhz", type=int, default=8, metavar="N",
                    help="板载晶振 MHz（默认 8；F1/F0/L1 内置兜底走 HSI，非 8 时告警提示）")
    ap.add_argument("--query-mcu", metavar="MODEL",
                    help="只打印型号解析规格，不建工程（/newproject 对话预览确认用）")
    ap.add_argument("--json", action="store_true",
                    help="与 --query-mcu 搭配：JSON 输出（纯 ASCII，给 Claude 解析）")
    ap.add_argument("--no-git", action="store_true", help="不执行 git init")
    ap.add_argument("--env", choices=["claude", "dsh"], default=None,
                    help="目标 AI 环境（默认读环境变量 STM32_TOOLKIT_ENV，未设则 claude）："
                         "claude→.claude/memory + @ 自动导入 + hooks 默认生成；"
                         "dsh→.dsh/memory + 显式路径引用 + 无 hooks")
    ap.add_argument("--hooks", action="store_true",
                    help="强制生成 .claude/settings.json（Claude Code hooks；默认 claude 环境生成、dsh 环境不生成）")
    ap.add_argument("--no-hooks", action="store_true",
                    help="强制不生成 .claude/settings.json（覆盖 env 默认）")
    ap.add_argument("--existing", action="store_true",
                    help="目标目录已有 Keil 工程，只补装 AI 辅助层（不创建 src/inc/MDK-ARM）")
    ap.add_argument("--analyze", action="store_true",
                    help="（仅配合 --existing）补装前先静态提取工程硬件配置（analyze_hw.py），"
                         "生成 hardware.yaml.draft / pin_usage.md.draft / ai_review_notes.md，供 AI 复核后定稿")
    ap.add_argument("--repair", action="store_true",
                    help="只刷新已有工程的 hooks 路径到当前工具包（工具包移动后自愈用，不碰其他文件）")
    ap.add_argument("--yes", action="store_true", help="非交互，全部使用默认值")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    fix_console_encoding()
    args = parse_args(argv)
    auto = args.yes or not sys.stdin.isatty()
    p = Prompter(auto)

    if args.analyze and not args.existing:
        err("--analyze 仅用于已有工程（必须配合 --existing），新建工程无需分析")
        return 1

    if args.query_mcu:
        mcu_info = mcu_knowledge.parse_model(args.query_mcu)
        if args.json:
            print(json.dumps(mcu_info, ensure_ascii=True, indent=2))
        else:
            print(mcu_knowledge.human(mcu_info))
        return 0

    project_name = args.name or p.ask("项目名", DEFAULT_NAME)
    mdk_project = project_name  # Keil 工程名默认取项目名

    if args.repair:
        target = Path(args.dir) if args.dir else Path(p.ask("目标目录", f"./{project_name}"))
        if not target.exists():
            err(f"目标目录不存在: {target}")
            return 1
        touched = repair_hooks(target, project_name, mcu_model=args.mcu or DEFAULT_MCU,
                               mdk_project=mdk_project)
        if touched:
            ok(f"hooks 修复完成，共 {len(touched)} 个文件")
        else:
            info("没有需要修复的 hooks（已最新 / 无 settings.json / 自定义配置跳过）")
        return 0

    if args.existing:
        target = Path(args.dir) if args.dir else Path(p.ask("目标目录", f"./{project_name}"))
        # 已有工程：项目名默认取目录名（避免模板里残留 "project" 占位符）
        project_name = args.name or target.name
        mdk_dir = "MDK-ARM"
        detected = find_existing_mdk_project(target)
        if detected:
            mdk_project, mdk_dir = detected
            info(f"检测到 Keil 工程: {mdk_project}.uvprojx（目录: {mdk_dir or '.'}，编译命令将指向它）")
        if args.mcu:
            mcu_model = args.mcu
        else:
            mcu_model = read_mcu_from_claude(target)
            if mcu_model:
                info(f"从 {target}/CLAUDE.md 读取到 MCU: {mcu_model}")
        if not mcu_model:
            mcu_model = p.ask("MCU 型号", DEFAULT_MCU)
        # --analyze：补装前静态提取工程硬件配置（方案 B 确定性部分）
        if args.analyze:
            analyze_hw(target)
    else:
        mcu_model = args.mcu or p.ask("MCU 型号", DEFAULT_MCU)
        target = Path(args.dir) if args.dir else Path(p.ask("目标目录", f"./{project_name}"))
        mdk_dir = "MDK-ARM"

    mcu_info = mcu_knowledge.parse_model(mcu_model)
    template = args.template if args.template else select_template(mcu_info)
    mcu_tokens = mcu_tokens_from_info(mcu_info)
    config_only = template is None

    if mcu_info["missing"]:
        warn(f"型号 {mcu_model} 有字段缺失: {', '.join(mcu_info['missing']) or '格式'}，"
             "缺失项将填 TBD，请用 --query-mcu 确认或修正型号")
    if args.template and mcu_info["spl"] is False:
        warn(f"{mcu_info['family']} 无标准外设库(SPL)，SPL 模板仅供 F0/F1/F2/F3/F4/L1；"
             "该型号建议去掉 --template 走 CubeMX 路径")

    # CubeMX 优先：默认（未指定 --template）任何家族都走无头生成；--no-cubemx 跳过
    want_cubemx = args.template is None and not args.no_cubemx

    # AI 环境双轨：--env > 环境变量 STM32_TOOLKIT_ENV > 默认 claude
    env = resolve_env(args.env)
    info(f"AI 环境: {env}")

    do_git = not args.no_git
    # hooks：claude 默认生成、dsh 默认不生成；--hooks/--no-hooks 强制覆盖
    do_hooks = env == "claude"
    if args.hooks:
        do_hooks = True
    if args.no_hooks:
        do_hooks = False
    if not auto and not args.hooks and not args.no_hooks:
        do_hooks = p.ask_yesno("生成 Claude Code hooks(.claude/settings.json)", default=do_hooks)

    if want_cubemx:
        mode_desc = "CubeMX 无头生成" if not args.existing else "补装 AI 辅助层（不动工程代码）"
        info(f"项目: {project_name} | MCU: {mcu_model} | 方式: {mode_desc} | 目录: {target}")
    elif config_only:
        info(f"项目: {project_name} | MCU: {mcu_model} | config-only 骨架 | 目录: {target}")
    else:
        info(f"项目: {project_name} | MCU: {mcu_model} | 模板: {template} | 目录: {target}")

    cubemx_ok = False
    if args.existing:
        if not target.exists():
            warn(f"目标目录不存在（--existing 模式应指向已有 Keil 工程）: {target}")
        created = install_existing_layer(target, project_name, mcu_model, mdk_project,
                                         do_hooks, mcu_tokens, env=env, mdk_dir=mdk_dir)
    else:
        if target.exists():
            if not target.is_dir():
                err(f"目标路径已存在但不是目录: {target}")
                return 1
            if any(target.iterdir()):
                if auto or not p.ask_yesno(f"目录 {target} 已存在且非空，是否继续生成骨架",
                                           default=False):
                    warn(f"目录非空，已跳过生成: {target}")
                    return 1
        target.mkdir(parents=True, exist_ok=True)
        if want_cubemx:
            flow = run_cubemx_flow(target, project_name, mcu_model,
                                   hse_hz=args.hse_mhz * 1_000_000)
            if flow.get("ok"):
                cubemx_ok = True
                # uvprojx 名 = ioc 名 = 项目名，但以实际产物为准（hooks 编译命令指向它）
                mdk_project = Path(flow["gen"]["uvprojx"]).stem
                info(f"CubeMX 生成 {flow['gen'].get('generated_count', 0)} 个文件"
                     f"（Core/Drivers/MDK-ARM 已就绪），补装 AI 辅助层...")
                created = install_existing_layer(target, project_name, mcu_model,
                                                 mdk_project, do_hooks, mcu_tokens, env=env,
                                                 mdk_dir="MDK-ARM")
            else:
                err(f"CubeMX 路径失败: {flow.get('error')}")
                if flow.get("error_type") == "missing_firmware":
                    info("装好固件包后重跑本命令即可生成完整 HAL 工程，先给 config-only 骨架。")
                created = generate_full_skeleton(target, project_name, mcu_model, None,
                                                 mdk_project, do_hooks, mcu_tokens,
                                                 full=False, env=env)
        else:
            created = generate_full_skeleton(target, project_name, mcu_model, template,
                                             mdk_project, do_hooks, mcu_tokens,
                                             full=not config_only, env=env)

    if created:
        ok(f"已生成/更新 {len(created)} 个文件:")
        for f in created:
            ok(f"  {f.relative_to(target)}")
    else:
        warn("没有需要创建的文件（目标文件均已存在？）")

    if do_git:
        do_git_init(target)

    print_next_steps(target, template, mcu_info, cubemx_ok=cubemx_ok, env=env,
                     existing=args.existing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
