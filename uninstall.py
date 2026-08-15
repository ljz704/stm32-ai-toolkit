#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 开发工作流 —— 一键卸载脚本
====================================
把 install.py 装到系统里的配置移除：
  - 全局 CLAUDE.md（~/.claude/CLAUDE.md）
  - Skills（4 个 stm32-* 技能目录，精确按 KNOWN_SKILLS 匹配）
  - Commands（6 个斜杠命令文件，精确按 KNOWN_COMMANDS 匹配）
  - MCP Server 注册（claude mcp remove stm32-toolkit）

默认策略：**移动到备份目录而非直接删除**
  ~/.claude/.stm32-toolkit-uninstalled/<时间戳>/
可随时手动恢复；配合 install.py 即可干净重装。

--purge       卸载后一并删除卸载备份与 install.py 生成的 *.bak_* 备份（彻底清理，不可恢复）
--purge-deps  同时卸载 Python 依赖 fastmcp / pyserial（默认保留，怕影响其他脚本）

用法:
    python uninstall.py            # 交互确认后卸载
    python uninstall.py --yes      # 非交互
    python uninstall.py --purge    # 卸载并清空备份，彻底卸载
    python uninstall.py --yes --purge
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 让脚本从其他目录运行时也能 import install / _cmdutil
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from install import (  # noqa: E402
    CLAUDE_DIR, COMMANDS_DIR, SKILLS_DIR, MCP_SERVER_NAME,
    DSH_DIR, DSH_AGENTS, DSH_SKILLS_DIR, DSH_MCP_STATE,
    KNOWN_SKILLS, KNOWN_COMMANDS, ok, warn, err, info,
)
from _cmdutil import fix_console_encoding, run_cmd  # noqa: E402

# 模块级修复：任何入口（main / 直接调用）打印中文/emoji 都不崩
fix_console_encoding()

BACKUP_ROOT_NAME = ".stm32-toolkit-uninstalled"  # 卸载备份目录（隐藏，不参与 Claude 扫描）


def backup_root(claude_dir=CLAUDE_DIR):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(claude_dir) / BACKUP_ROOT_NAME / stamp


def collect_artifacts(claude_dir=CLAUDE_DIR):
    """收集要卸载的路径：仅匹配本工具包装过的东西。返回 [(src, 展示名), ...]。"""
    cd = Path(claude_dir)
    items = []

    claude_md = cd / "CLAUDE.md"
    if claude_md.exists():
        items.append((claude_md, "全局 CLAUDE.md"))

    for name in KNOWN_SKILLS:
        d = cd / "skills" / name
        if d.is_dir():
            items.append((d, f"Skill: {name}"))

    for name in KNOWN_COMMANDS:
        f = cd / "commands" / name
        if f.exists():
            items.append((f, f"Command: {name}"))

    return items


def collect_dsh_artifacts():
    """收集 DSH 模式（--dsh）安装到 ~/.dsh 的配置。返回 [(src, 展示名), ...]。"""
    items = []
    if DSH_AGENTS.exists():
        items.append((DSH_AGENTS, "全局指令 AGENTS.md"))
    for name in KNOWN_SKILLS:
        d = DSH_SKILLS_DIR / name
        if d.is_dir():
            items.append((d, f"Skill: {name}"))
    if DSH_MCP_STATE.exists():
        items.append((DSH_MCP_STATE, "MCP 注册表 mcp-servers.json"))
    return items


def run_uninstall_dsh(purge=False):
    """卸载 DSH 模式安装的配置（~/.dsh），移入 ~/.dsh/.stm32-toolkit-uninstalled/。"""
    bk = DSH_DIR / BACKUP_ROOT_NAME / datetime.now().strftime("%Y%m%d_%H%M%S")
    moved = 0
    for src, label in collect_dsh_artifacts():
        rel = src.relative_to(DSH_DIR)
        dst = bk / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            ok(f"已移出 {label} → {dst}")
            moved += 1
        except OSError as e:
            warn(f"移出 {label} 失败: {e}（跳过）")

    if moved == 0:
        warn("没有发现 DSH 模式安装的配置（可能尚未安装，或已被移除）")
    else:
        ok(f"已将 {moved} 项配置移出，备份在: {bk}")

    if purge:
        root = DSH_DIR / BACKUP_ROOT_NAME
        if root.exists():
            try:
                shutil.rmtree(root)
                ok(f"已删除 DSH 卸载备份目录: {root}")
            except OSError as e:
                warn(f"删除 {root} 失败: {e}")
        install_bk = DSH_DIR / ".stm32-toolkit-backups"
        if install_bk.exists():
            try:
                shutil.rmtree(install_bk)
                ok(f"已删除 DSH 安装备份目录: {install_bk}")
            except OSError as e:
                warn(f"删除 {install_bk} 失败: {e}")

    print()
    info("DSH 卸载完成；重新安装: python install.py --dsh")
    return 0


def move_to_backup(claude_dir=CLAUDE_DIR):
    """把收集到的配置移动到时间戳备份目录。返回 (moved_count, backup_path)。"""
    bk = backup_root(claude_dir)
    moved = 0
    for src, label in collect_artifacts(claude_dir):
        rel = src.relative_to(Path(claude_dir))
        dst = bk / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            ok(f"已移出 {label} → {bk / rel}")
            moved += 1
        except OSError as e:
            warn(f"移出 {label} 失败: {e}（跳过）")
    return moved, bk


def remove_mcp():
    """移除 MCP 注册。返回 True 表示已处理（注册被移除或本来就没有）。"""
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        warn("未找到 claude 命令，跳过 MCP 卸载")
        info("  如曾注册过，可手动运行: claude mcp remove stm32-toolkit")
        return True
    result = run_cmd(["claude", "mcp", "remove", MCP_SERVER_NAME], timeout=60)
    if result.error:
        warn(f"claude mcp remove 执行出错: {result.error}")
        return False
    if result.timed_out:
        warn("claude mcp remove 超时（可能未注册或网络问题）")
        return False
    if result.returncode != 0:
        # 未注册过时返回非零属正常
        info("MCP 注册未找到（或已移除）")
        return True
    ok("MCP Server 注册已移除")
    return True


def purge_backups(claude_dir=CLAUDE_DIR):
    """--purge：删除卸载备份目录 + install.py 生成的 *.bak_* 备份。"""
    cd = Path(claude_dir)
    removed = 0

    root = cd / BACKUP_ROOT_NAME
    if root.exists():
        try:
            shutil.rmtree(root)
            ok(f"已删除卸载备份目录: {root}")
            removed += 1
        except OSError as e:
            warn(f"删除 {root} 失败: {e}")

    # install.py 的安装前备份目录（~/.claude/.stm32-toolkit-backups/）
    install_bk = cd / ".stm32-toolkit-backups"
    if install_bk.exists():
        try:
            shutil.rmtree(install_bk)
            ok(f"已删除安装备份目录: {install_bk}")
            removed += 1
        except OSError as e:
            warn(f"删除 {install_bk} 失败: {e}")

    # 兼容清理：早期版本 install.py 留下的 *.bak_*（CLAUDE.md.bak_xxx、skills/*.bak_xxx、commands/*.bak_xxx）
    for pattern in ["CLAUDE.md.bak_*", "skills/*.bak_*", "commands/*.bak_*"]:
        for p in cd.glob(pattern):
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                ok(f"已删除备份: {p}")
                removed += 1
            except OSError as e:
                warn(f"删除 {p} 失败: {e}")
    return removed


def purge_deps():
    """--purge-deps：卸载 fastmcp / pyserial（提示风险后执行）。"""
    info("卸载 Python 依赖 fastmcp / pyserial...")
    pip_cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "fastmcp", "pyserial"]
    result = run_cmd(pip_cmd, timeout=180)
    if result.error or result.timed_out:
        err(f"卸载依赖失败: {result.error or result.combined}")
        return False
    if result.returncode != 0:
        err(f"卸载依赖失败:\n{result.combined}")
        return False
    ok("Python 依赖已卸载（fastmcp / pyserial）")
    return True


def run_uninstall(claude_dir=CLAUDE_DIR, purge=False, purge_deps=False, do_mcp=True):
    fix_console_encoding()  # 保证直接调用（非 main 入口）时打印中文/emoji 不崩
    moved, bk = move_to_backup(claude_dir)
    if moved == 0:
        warn("没有发现本工具包安装的配置（可能尚未安装，或已被移除）")
    else:
        ok(f"已将 {moved} 项配置移出，备份在: {bk}")

    if do_mcp:
        remove_mcp()

    if purge_deps:
        purge_deps()

    if purge:
        purge_backups(claude_dir)

    print()
    print("=" * 60)
    print("  卸载完成！")
    print("=" * 60)
    print()
    info("备份位置: " + str(Path(claude_dir) / BACKUP_ROOT_NAME))
    info("重新安装: python install.py")
    if not purge:
        info("彻底清理: python uninstall.py --purge  （会删除全部备份，不可恢复）")
    print()
    return 0


def main():
    fix_console_encoding()

    parser = argparse.ArgumentParser(
        prog="uninstall.py",
        description="STM32 AI 开发工作流 —— 一键卸载。默认把配置移到备份目录（可恢复），--purge 才彻底删除。",
    )
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    parser.add_argument("--dsh", action="store_true",
                        help="卸载 DSH 模式安装的配置（~/.dsh 的 AGENTS.md / skills / mcp-servers.json）")
    parser.add_argument("--purge", action="store_true",
                        help="卸载后删除卸载备份与 *.bak_* 备份，彻底清理（不可恢复）")
    parser.add_argument("--purge-deps", action="store_true",
                        help="同时卸载 Python 依赖 fastmcp/pyserial")
    args = parser.parse_args()

    print("=" * 60)
    print("  STM32 AI 开发工作流 —— 一键卸载")
    print("=" * 60)
    print()

    if not args.yes:
        try:
            target_desc = "DSH 配置（AGENTS.md、6 个 Skill、MCP 注册）" if args.dsh else "全局 CLAUDE.md、4/6 个 Skill、6 个命令及 MCP 注册"
            ans = input(f"确认卸载？将移除{target_desc}。 [y/N] ")
        except EOFError:
            ans = ""
        if ans.strip().lower() not in ("y", "yes"):
            info("已取消卸载")
            return 0

    if args.purge:
        warn("--purge 会删除所有备份（包括你可能想保留的旧配置），不可恢复！")

    if args.dsh:
        return run_uninstall_dsh(purge=args.purge)

    return run_uninstall(purge=args.purge, purge_deps=args.purge_deps)


if __name__ == "__main__":
    sys.exit(main())
