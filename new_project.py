#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new_project.py —— STM32 工程脚手架生成器
==========================================
从 templates/project/ 渲染模板生成新 STM32 工程骨架，
或给已有 Keil 工程补装 AI 辅助层（--existing）。

用法：
  python new_project.py [--name <项目名>] [--mcu <型号>] [--dir <目录>]
                        [--template f1xx_general|f3xx_digital_power]
                        [--no-git] [--no-hooks] [--existing] [--yes]

说明：
  - 交互模式逐个提问；带 --yes 或 stdin 非 tty（AI / install.py 委托调用）时用默认值不阻塞。
  - MCU 型号含 "F3" 自动选 f3xx_digital_power，否则 f1xx_general，可 --template 显式指定。
  - --existing：目标目录已有 Keil 工程，只补装 AI 辅助层
    （CLAUDE.md / .claude/settings.json / memory 空白模板 / hardware.yaml），
    不创建 src/inc/MDK-ARM。
  - 占位符用 str.replace 渲染：{{PROJECT_NAME}}、{{MCU_MODEL}}、{{MDK_PROJECT}}（默认=项目名）、
    {{KEIL_UV4}}（自动检测 Keil 路径）、settings.json.template 里的 {{TOOLKIT_PATH}}（反斜杠转成 /）。
"""

import argparse
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR / "templates" / "project"
TOOLKIT_PATH = str(SCRIPT_DIR).replace("\\", "/")


def _detect_keil_uv4() -> str:
    """检测 Keil UV4.exe：优先 KEIL_PATH 环境变量，再探测常见默认路径。

    返回的路径用于渲染模板里的编译命令占位符 {{KEIL_UV4}}；
    探测不到时退回 C:\\Keil_v5 常见默认，避免模板里出现空路径。
    """
    env = os.environ.get("KEIL_PATH")
    if env:
        return env
    for p in (
        Path(r"C:\Keil_v5\UV4\UV4.exe"),
        Path(r"D:\Keil_v5\UV4\UV4.exe"),
        Path(r"C:\Keil\UV4\UV4.exe"),
    ):
        if p.exists():
            return str(p)
    return str(Path(r"C:\Keil_v5\UV4\UV4.exe"))


KEIL_UV4 = _detect_keil_uv4()

DEFAULT_NAME = "rn8209_meter"
DEFAULT_MCU = "STM32F103C8T6"
F1_TEMPLATE = "f1xx_general"
F3_TEMPLATE = "f3xx_digital_power"

MEMORY_FILES = ("architecture.md", "pin_usage.md", "known_issues.md", "session_log.md")

MCU_RE = re.compile(r"STM32F\d{2}[A-Z0-9]+", re.IGNORECASE)

sys.path.insert(0, str(SCRIPT_DIR))
from _cmdutil import fix_console_encoding, run_cmd  # noqa: E402


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


# ===================== 渲染与推断 =====================
def render(text: str, project_name: str, mcu_model: str, mdk_project: str,
           toolkit_path: str = TOOLKIT_PATH, keil_uv4: str = KEIL_UV4) -> str:
    """渲染模板占位符（str.replace；未出现的占位符原样保留）。"""
    text = text.replace("{{PROJECT_NAME}}", project_name)
    text = text.replace("{{MCU_MODEL}}", mcu_model)
    text = text.replace("{{MDK_PROJECT}}", mdk_project)
    text = text.replace("{{TOOLKIT_PATH}}", toolkit_path)
    text = text.replace("{{KEIL_UV4}}", keil_uv4)
    return text


def infer_template(mcu_model: str) -> str:
    """MCU 型号含 'F3' → f3xx_digital_power，否则 f1xx_general。"""
    if mcu_model and "F3" in mcu_model.upper():
        return F3_TEMPLATE
    return F1_TEMPLATE


def template_io_files(template: str):
    """按模板返回 src/inc 差异文件名（it.c, conf.h）。"""
    if template == F3_TEMPLATE:
        return "stm32f3xx_it.c", "stm32f3xx_conf.h"
    return "stm32f10x_it.c", "stm32f10x_conf.h"


def find_existing_mdk_project(target: Path):
    """--existing 模式：探测 MDK-ARM 下真实的 .uvprojx 工程名（第一个匹配的 stem）。

    找不到返回 None。有了它，编译命令里的工程文件就不会错写成默认项目名。
    """
    mdk_dir = Path(target) / "MDK-ARM"
    if not mdk_dir.is_dir():
        return None
    for p in mdk_dir.glob("*.uvprojx"):
        return p.stem
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


# ===================== 生成逻辑 =====================
def generate_full_skeleton(target: Path, project_name: str, mcu_model: str,
                           template: str, mdk_project: str, do_hooks: bool):
    """生成完整工程骨架，返回创建的文件列表。"""
    created = []
    it_c, conf_h = template_io_files(template)

    files = [
        (TEMPLATES_DIR / "CLAUDE.md.template",    target / "CLAUDE.md"),
        (TEMPLATES_DIR / "hardware.yaml.blank",   target / "hardware.yaml"),
        (TEMPLATES_DIR / "src" / "main.c",        target / "src" / "main.c"),
        (TEMPLATES_DIR / "src" / it_c,            target / "src" / it_c),
        (TEMPLATES_DIR / "inc" / "main.h",        target / "inc" / "main.h"),
        (TEMPLATES_DIR / "inc" / conf_h,          target / "inc" / conf_h),
        (TEMPLATES_DIR / "MDK-ARM" / "README.md", target / "MDK-ARM" / "README.md"),
    ]
    for src, dst in files:
        if render_to_file(src, dst, project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project):
            created.append(dst)

    for mem in MEMORY_FILES:
        dst = target / ".claude" / "memory" / mem
        if render_to_file(TEMPLATES_DIR / "memory" / mem, dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project):
            created.append(dst)

    if do_hooks:
        dst = target / ".claude" / "settings.json"
        if render_to_file(TEMPLATES_DIR / "settings.json.template", dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project):
            created.append(dst)

    return created


def install_existing_layer(target: Path, project_name: str, mcu_model: str,
                           mdk_project: str, do_hooks: bool):
    """给已有 Keil 工程补装 AI 辅助层，返回创建/更新的文件列表。"""
    touched = []

    # CLAUDE.md：生成/更新（覆盖渲染）
    claude_src = TEMPLATES_DIR / "CLAUDE.md.template"
    claude_dst = target / "CLAUDE.md"
    if claude_src.exists():
        claude_dst.parent.mkdir(parents=True, exist_ok=True)
        text = render(claude_src.read_text(encoding="utf-8"),
                      project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project)
        claude_dst.write_text(text, encoding="utf-8")
        touched.append(claude_dst)
    else:
        warn(f"未找到模板: {claude_src}，跳过 CLAUDE.md")

    # memory 空白模板：已存在不覆盖
    for mem in MEMORY_FILES:
        dst = target / ".claude" / "memory" / mem
        if render_to_file(TEMPLATES_DIR / "memory" / mem, dst,
                          project_name=project_name, mcu_model=mcu_model,
                          mdk_project=mdk_project):
            touched.append(dst)

    # hardware.yaml：不存在才生成
    hw_dst = target / "hardware.yaml"
    if render_to_file(TEMPLATES_DIR / "hardware.yaml.blank", hw_dst,
                      project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project):
        touched.append(hw_dst)

    # settings.json：生成/更新（覆盖，TOOLKIT_PATH 可能变化）
    if do_hooks:
        settings_src = TEMPLATES_DIR / "settings.json.template"
        settings_dst = target / ".claude" / "settings.json"
        if settings_src.exists():
            settings_dst.parent.mkdir(parents=True, exist_ok=True)
            text = render(settings_src.read_text(encoding="utf-8"),
                          project_name=project_name, mcu_model=mcu_model, mdk_project=mdk_project)
            settings_dst.write_text(text, encoding="utf-8")
            touched.append(settings_dst)
        else:
            warn(f"未找到 hooks 模板: {settings_src}，跳过 settings.json")

    return touched


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


def print_next_steps(target: Path, template: str) -> None:
    it_c, _ = template_io_files(template)
    print()
    info("=" * 58)
    info("下一步：")
    info(f"  1. 用 Keil 向导 / CubeMX 在 {target}/MDK-ARM 生成 .uvprojx 工程")
    info(f"  2. 加入源文件: src/main.c、src/{it_c}、ST 库 system 文件，Include Paths 加 inc/")
    info(f"  3. 进入 {target} 打开 Claude Code，运行 /build 验证编译")
    info("  4. git init 并首次提交（若未在本脚本执行）")
    info("=" * 58)


# ===================== CLI =====================
def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="new_project.py",
        description="STM32 工程脚手架：生成新工程骨架，或给已有 Keil 工程补装 AI 辅助层",
        epilog="示例: python new_project.py --name meter --mcu STM32F103C8T6 --yes",
    )
    ap.add_argument("--name", help=f"项目名（默认 {DEFAULT_NAME}）")
    ap.add_argument("--mcu", help="MCU 型号，如 STM32F103C8T6 / STM32F334C8T6")
    ap.add_argument("--dir", help="目标目录（默认 ./<项目名>）")
    ap.add_argument("--template", choices=[F1_TEMPLATE, F3_TEMPLATE],
                    help=f"模板（默认按 MCU 推断：含 F3 用 {F3_TEMPLATE}，否则 {F1_TEMPLATE}）")
    ap.add_argument("--no-git", action="store_true", help="不执行 git init")
    ap.add_argument("--no-hooks", action="store_true",
                    help="不生成 .claude/settings.json（CLAUDE.md 与 memory 照常）")
    ap.add_argument("--existing", action="store_true",
                    help="目标目录已有 Keil 工程，只补装 AI 辅助层（不创建 src/inc/MDK-ARM）")
    ap.add_argument("--yes", action="store_true", help="非交互，全部使用默认值")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    fix_console_encoding()
    args = parse_args(argv)
    auto = args.yes or not sys.stdin.isatty()
    p = Prompter(auto)

    project_name = args.name or p.ask("项目名", DEFAULT_NAME)
    mdk_project = project_name  # Keil 工程名默认取项目名

    if args.existing:
        target = Path(args.dir) if args.dir else Path(p.ask("目标目录", f"./{project_name}"))
        detected = find_existing_mdk_project(target)
        if detected:
            mdk_project = detected
            info(f"检测到 Keil 工程: {mdk_project}.uvprojx（编译命令将指向它）")
        if args.mcu:
            mcu_model = args.mcu
        else:
            mcu_model = read_mcu_from_claude(target)
            if mcu_model:
                info(f"从 {target}/CLAUDE.md 读取到 MCU: {mcu_model}")
        if not mcu_model:
            mcu_model = p.ask("MCU 型号", DEFAULT_MCU)
    else:
        mcu_model = args.mcu or p.ask("MCU 型号", DEFAULT_MCU)
        target = Path(args.dir) if args.dir else Path(p.ask("目标目录", f"./{project_name}"))

    template = args.template or infer_template(mcu_model)

    do_git = not args.no_git
    do_hooks = not args.no_hooks
    if not auto:
        if not args.no_git:
            do_git = p.ask_yesno("git init", default=True)
        if not args.no_hooks:
            do_hooks = p.ask_yesno("生成 hooks(.claude/settings.json)", default=True)

    info(f"项目: {project_name} | MCU: {mcu_model} | 模板: {template} | 目录: {target}")

    if args.existing:
        if not target.exists():
            warn(f"目标目录不存在（--existing 模式应指向已有 Keil 工程）: {target}")
        created = install_existing_layer(target, project_name, mcu_model, mdk_project, do_hooks)
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
        created = generate_full_skeleton(target, project_name, mcu_model, template,
                                         mdk_project, do_hooks)

    if created:
        ok(f"已生成/更新 {len(created)} 个文件:")
        for f in created:
            ok(f"  {f.relative_to(target)}")
    else:
        warn("没有需要创建的文件（目标文件均已存在？）")

    if do_git:
        do_git_init(target)

    print_next_steps(target, template)
    return 0


if __name__ == "__main__":
    sys.exit(main())
