#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 工作流 —— 备份同步脚本
================================
当你在系统中修改了 CLAUDE.md、Skills 或 Commands 后，运行此脚本
把修改同步回工具包文件夹，方便 Git 提交或复制到新电脑。

默认方向：系统 → 工具包（备份）
反向：   --from-toolkit  工具包 → 系统（恢复）
DSH：    --dsh          同步 ~/.dsh（AGENTS.md ↔ dsh_global.md，skills ↔ skills/）

只同步含 SKILL.md 的 skills 子目录；不碰 mcp/（server 由工具包路径直接引用）、不碰 templates/。

用法:
    python backup.py                 # Claude Code: 系统 → 工具包
    python backup.py --dsh           # DSH: ~/.dsh → 工具包
    python backup.py --from-toolkit  # 工具包 → 系统（可加 --dsh 表示推送到 ~/.dsh）
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

# 工具包 skill 白名单（失效清理只动白名单内，绝不碰用户自定义 skill）
KNOWN_SKILLS = [
    "stm32-build-flash-debug",
    "stm32-code-review",
    "stm32-debug-analyze",
    "stm32-peripheral-config",
    "stm32-new-project",
    "stm32-known-issues",
]

# ── DSH（DeepSeek Harness）目标：~/.dsh ↔ 工具包 ──
DSH_DIR = USER_HOME / ".dsh"
DSH_AGENTS = DSH_DIR / "AGENTS.md"
TK_DSH_GLOBAL = SCRIPT_DIR / "dsh_global.md"


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


def sync_skill_dirs(src_dir: Path, dst_dir: Path, dry_run: bool, prune: bool = False):
    """递归同步含 SKILL.md 的 skill 子目录；跳过非目录、跳过不含 SKILL.md 的目录。

    prune=True 时清理失效项（仅限 KNOWN_SKILLS 白名单）：目标端存在但源端已删的
    工具包 skill → 移到技能目录**上级**的 .stm32-toolkit-backups/ 备份（可恢复）。

    安全约束：
      - 只清理白名单内的工具包 skill，**绝不移动用户自定义 skill**；
      - 默认方向（系统→工具包，prune=False）不做清理，避免改写工具包分发目录；
      - 备份目录放在技能目录外（install.py 约定：备份放技能目录内会被当技能加载）。
    """
    if not src_dir.exists():
        print(f"⚠️  未找到技能目录: {src_dir}")
        return
    count = 0
    src_names = set()
    for d in sorted(src_dir.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "SKILL.md").exists():
            continue
        src_names.add(d.name)
        dst = dst_dir / d.name
        if dry_run:
            print(f"✅ (预览) 将同步技能: {d.name} → {dst}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(d, dst, dirs_exist_ok=True)
            print(f"✅ 已同步技能: {d.name}")
        count += 1

    # 失效清理（仅 --from-toolkit 方向 + 白名单 + 备份放技能目录外）
    if prune and dst_dir.exists():
        stale_backup = dst_dir.parent / ".stm32-toolkit-backups"
        stale_backup.mkdir(parents=True, exist_ok=True)
        for d in sorted(dst_dir.iterdir()):
            if not d.is_dir() or d.name in src_names:
                continue
            if d.name not in KNOWN_SKILLS:  # 白名单外（用户自定义）一律不碰
                continue
            if not (d / "SKILL.md").exists():
                continue
            target = stale_backup / d.name
            if dry_run:
                print(f"⚠️ (预览) 源端已删除，将备份并移除失效技能: {d.name}")
            else:
                try:
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.move(str(d), str(target))
                    print(f"⚠️ 已备份并移除失效技能: {d.name} → {target}")
                except OSError as e:
                    print(f"❌ 移除失效技能 {d.name} 失败: {e}（跳过）")

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
        description="备份/恢复 STM32 AI 工具包配置（CLAUDE.md / AGENTS.md / Skills / Commands）。默认系统→工具包。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印要同步的文件，不复制")
    parser.add_argument("--from-toolkit", action="store_true", help="反向：把工具包推送到系统")
    parser.add_argument("--prune", action="store_true",
                        help="（仅 --from-toolkit 时生效）清理失效工具包 skill：目标端有、工具包已删的"
                             "白名单 skill 移到技能目录上级 .stm32-toolkit-backups/ 备份（不碰用户自定义 skill）")
    parser.add_argument("--dsh", action="store_true",
                        help="DSH 模式：同步 ~/.dsh（AGENTS.md ↔ dsh_global.md，skills ↔ skills/），不碰 ~/.claude")
    args = parser.parse_args()

    # 失效清理仅在"工具包→系统"方向 + 显式 --prune 时执行（默认方向不清理，避免改写工具包分发目录）
    do_prune = args.prune and args.from_toolkit

    if args.dsh:
        # DSH 模式：只同步 AGENTS.md + skills，不涉及 commands（DSH 无文件式命令）
        if args.from_toolkit:
            direction = "工具包 → ~/.dsh"
            src_agents, dst_agents = TK_DSH_GLOBAL, DSH_AGENTS
            src_skills, dst_skills = TK_SKILLS, DSH_DIR / "skills"
        else:
            direction = "~/.dsh → 工具包"
            src_agents, dst_agents = DSH_AGENTS, TK_DSH_GLOBAL
            src_skills, dst_skills = DSH_DIR / "skills", TK_SKILLS
        print(f"正在同步（DSH，{direction}）...")
        print()
        sync_file(src_agents, dst_agents, args.dry_run)
        sync_skill_dirs(src_skills, dst_skills, args.dry_run, prune=do_prune)
        print()
        print("DSH 同步完成！建议提交到 Git 或复制到网盘备份。")
        print("⚠️  MCP 注册表（~/.dsh/mcp-servers.json）不随备份同步——它可能含你自定义的 MCP，")
        print("    换机器后需重新运行 `python install.py --dsh` 重建 stm32-toolkit 的 MCP 条目。")
        if sys.stdin.isatty():
            try:
                input("按回车键退出...")
            except EOFError:
                pass
        return

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
