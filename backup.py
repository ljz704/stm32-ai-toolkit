#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 工作流 —— 备份同步脚本
================================
当你在系统中修改了 CLAUDE.md、Skills 或 Commands 后，运行此脚本
把修改同步回工具包文件夹，方便 Git 提交或复制到新电脑。

默认方向：系统 → 工具包（备份）
反向：   --from-toolkit  工具包 → 系统（恢复）

只同步含 SKILL.md 的 skills 子目录；不碰 mcp/（server 由工具包路径直接引用）、不碰 templates/。

用法:
    python backup.py                 # 系统 → 工具包
    python backup.py --from-toolkit  # 工具包 → 系统
    python backup.py --dry-run       # 只预览要同步的文件，不复制
"""

import argparse
import shutil
import sys
from pathlib import Path

# 让脚本从其他目录运行时也能 import _cmdutil
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _cmdutil import fix_console_encoding  # noqa: E402

USER_HOME = Path.home()
CLAUDE_DIR = USER_HOME / ".claude"
SYSTEM_SKILLS = CLAUDE_DIR / "skills"
SYSTEM_COMMANDS = CLAUDE_DIR / "commands"
TK_SKILLS = SCRIPT_DIR / "skills"
TK_COMMANDS = SCRIPT_DIR / "commands"


def sync_file(src: Path, dst: Path, dry_run: bool):
    """同步单个文件。"""
    if not src.exists():
        print(f"❌ 未找到: {src}")
        return
    if dry_run:
        print(f"✅ (预览) 将同步: {src.name} → {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"✅ 已同步: {src.name}")


def sync_skill_dirs(src_dir: Path, dst_dir: Path, dry_run: bool):
    """递归同步含 SKILL.md 的 skill 子目录；跳过非目录、跳过不含 SKILL.md 的目录。"""
    if not src_dir.exists():
        print(f"⚠️  未找到技能目录: {src_dir}")
        return
    count = 0
    for d in sorted(src_dir.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "SKILL.md").exists():
            continue
        dst = dst_dir / d.name
        if dry_run:
            print(f"✅ (预览) 将同步技能: {d.name} → {dst}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(d, dst, dirs_exist_ok=True)
            print(f"✅ 已同步技能: {d.name}")
        count += 1
    if count == 0:
        print(f"⚠️  {src_dir} 下没有含 SKILL.md 的技能目录")


def sync_commands(src_dir: Path, dst_dir: Path, dry_run: bool):
    """同步 *.md 命令文件。"""
    if not src_dir.exists():
        print(f"⚠️  未找到命令目录: {src_dir}")
        return
    count = 0
    for f in sorted(src_dir.glob("*.md")):
        if dry_run:
            print(f"✅ (预览) 将同步命令: {f.name} → {dst_dir / f.name}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst_dir / f.name)
            print(f"✅ 已同步命令: {f.name}")
        count += 1
    if count == 0:
        print(f"⚠️  {src_dir} 下没有 .md 命令文件")


def main():
    # 必须先修编码：GBK 控制台打印 emoji/中文会崩
    fix_console_encoding()

    parser = argparse.ArgumentParser(
        prog="backup.py",
        description="备份/恢复 STM32 AI 工具包配置（CLAUDE.md / Skills / Commands）。默认系统→工具包。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印要同步的文件，不复制")
    parser.add_argument("--from-toolkit", action="store_true", help="反向：把工具包推送到系统")
    args = parser.parse_args()

    direction = "工具包 → 系统" if args.from_toolkit else "系统 → 工具包"
    print(f"正在同步（{direction}）...")
    print()

    if args.from_toolkit:
        # 工具包 → 系统
        sync_file(SCRIPT_DIR / "global_claude.md", CLAUDE_DIR / "CLAUDE.md", args.dry_run)
        sync_skill_dirs(TK_SKILLS, SYSTEM_SKILLS, args.dry_run)
        sync_commands(TK_COMMANDS, SYSTEM_COMMANDS, args.dry_run)
    else:
        # 系统 → 工具包
        sync_file(CLAUDE_DIR / "CLAUDE.md", SCRIPT_DIR / "global_claude.md", args.dry_run)
        sync_skill_dirs(SYSTEM_SKILLS, TK_SKILLS, args.dry_run)
        sync_commands(SYSTEM_COMMANDS, TK_COMMANDS, args.dry_run)

    print()
    print("同步完成！建议提交到 Git 或复制到网盘备份。")
    if sys.stdin.isatty():
        try:
            input("按回车键退出...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
