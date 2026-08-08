#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 工作流 —— 备份同步脚本
================================
当你在系统中修改了 CLAUDE.md 或 Skills 后，运行此脚本
把修改同步回工具包文件夹，方便 Git 提交或复制到新电脑。

用法:
    python backup.py
"""

import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
USER_HOME = Path.home()
CLAUDE_DIR = USER_HOME / ".claude"

def backup_file(src: Path, dst: Path):
    if src.exists():
        shutil.copy2(src, dst)
        print(f"✅ {src.name}")
    else:
        print(f"❌ 未找到: {src}")

def main():
    print("正在从系统目录同步回工具包...")
    print()

    # 全局规范
    backup_file(CLAUDE_DIR / "CLAUDE.md", SCRIPT_DIR / "global_claude.md")

    # 模板
    templates_src = CLAUDE_DIR / "templates"
    templates_dst = SCRIPT_DIR / "templates"
    templates_dst.mkdir(exist_ok=True)
    if templates_src.exists():
        for f in templates_src.iterdir():
            if f.suffix == ".md":
                backup_file(f, templates_dst / f.name)

    # Skills
    skills_src = CLAUDE_DIR / "skills"
    skills_dst = SCRIPT_DIR / "skills"
    skills_dst.mkdir(exist_ok=True)
    if skills_src.exists():
        for f in skills_src.iterdir():
            if f.suffix == ".md":
                backup_file(f, skills_dst / f.name)

    print()
    print("同步完成！建议提交到 Git 或复制到网盘备份。")
    input("按回车键退出...")

if __name__ == "__main__":
    main()
