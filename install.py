#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 开发工作流 —— 一键安装/恢复脚本
============================================
换电脑后，把这个文件夹复制到新电脑，双击运行 install.py，
自动完成所有配置，无需手动编辑任何文件。

也可以对 Claude 说："帮我恢复 STM32 开发环境"
AI 会调用此脚本自动执行。
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

# ===================== 颜色输出 =====================
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

def ok(msg):    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")
def warn(msg):  print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")
def err(msg):   print(f"{Colors.RED}❌ {msg}{Colors.RESET}")
def info(msg):  print(f"{Colors.CYAN}ℹ️  {msg}{Colors.RESET}")

# ===================== 路径常量 =====================
SCRIPT_DIR = Path(__file__).parent.resolve()
USER_HOME = Path.home()
CLAUDE_DIR = USER_HOME / ".claude"
TEMPLATES_DIR = CLAUDE_DIR / "templates"
SKILLS_DIR = CLAUDE_DIR / "skills"

# ===================== 步骤 1: 检查 Python 环境 =====================
def check_python():
    info("检查 Python 环境...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        err("需要 Python 3.8+，当前版本: {}.{}.{}".format(version.major, version.minor, version.micro))
        sys.exit(1)
    ok(f"Python {version.major}.{version.minor}.{version.micro}")

# ===================== 步骤 2: 安装 Python 依赖 =====================
def install_deps():
    info("检查并安装 Python 依赖...")
    deps = ["fastmcp", "pyserial"]
    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("pyserial", "serial"))
        except ImportError:
            missing.append(dep)

    if missing:
        warn(f"缺少依赖: {', '.join(missing)}，正在安装...")
        result = subprocess.run([sys.executable, "-m", "pip", "install"] + missing,
                                capture_output=True, text=True)
        if result.returncode != 0:
            err(f"安装失败: {result.stderr}")
            info("请手动运行: pip install fastmcp pyserial")
            return False
        ok(f"已安装: {', '.join(missing)}")
    else:
        ok("所有 Python 依赖已就绪")
    return True

# ===================== 步骤 3: 安装全局 CLAUDE.md =====================
def install_global_claude_md():
    info("安装全局 CLAUDE.md...")
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

    src = SCRIPT_DIR / "global_claude.md"
    dst = CLAUDE_DIR / "CLAUDE.md"

    if not src.exists():
        err(f"未找到 {src}")
        return False

    shutil.copy2(src, dst)
    ok(f"全局规范已安装: {dst}")
    return True

# ===================== 步骤 4: 安装模板 =====================
def install_templates():
    info("安装项目模板...")
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    src_dir = SCRIPT_DIR / "templates"
    if not src_dir.exists():
        warn("templates 目录不存在，跳过")
        return True

    for f in src_dir.iterdir():
        if f.suffix == ".md":
            shutil.copy2(f, TEMPLATES_DIR / f.name)
            ok(f"模板: {f.name}")
    return True

# ===================== 步骤 5: 安装 Skills =====================
def install_skills():
    info("安装 Skills...")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    src_dir = SCRIPT_DIR / "skills"
    if not src_dir.exists():
        warn("skills 目录不存在，跳过")
        return True

    for f in src_dir.iterdir():
        if f.suffix == ".md":
            shutil.copy2(f, SKILLS_DIR / f.name)
            ok(f"Skill: {f.name}")
    return True

# ===================== 步骤 6: 检查 Keil 和烧录工具 =====================
def check_toolchain():
    info("检查工具链...")

    # Keil
    keil_paths = [
        Path(r"C:\Keil_v5\UV4\UV4.exe"),
        Path(r"D:\Keil_v5\UV4\UV4.exe"),
        Path(r"C:\Keil\UV4\UV4.exe"),
    ]
    keil_found = None
    for p in keil_paths:
        if p.exists():
            keil_found = p
            break

    if keil_found:
        ok(f"Keil: {keil_found}")
    else:
        warn("Keil 未找到，请确认已安装 Keil MDK-ARM")
        info("  如果安装在其他位置，请在环境变量中设置 KEIL_PATH")

    # STM32CubeProgrammer
    prog_paths = [
        Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"),
        Path(r"D:\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"),
    ]
    prog_found = None
    for p in prog_paths:
        if p.exists():
            prog_found = p
            break

    if prog_found:
        ok(f"STM32CubeProgrammer: {prog_found}")
    else:
        warn("STM32CubeProgrammer 未找到，请从 ST 官网下载安装")
        info("  下载地址: https://www.st.com/en/development-tools/stm32cubeprog.html")

    return keil_found, prog_found

# ===================== 步骤 7: 注册 MCP Server =====================
def register_mcp(keil_path: Path = None, prog_path: Path = None):
    info("注册 MCP Server...")

    # 检查 claude 命令
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        warn("未找到 claude 命令，跳过 MCP 注册")
        info("  请确保 Claude Code CLI 已安装并加入 PATH")
        info("  安装后手动运行: claude mcp add --scope user --transport stdio stm32-toolkit -- python <路径>/stm32_mcp_server.py")
        return False

    server_script = SCRIPT_DIR / "mcp" / "stm32_mcp_server.py"
    if not server_script.exists():
        err(f"MCP Server 脚本未找到: {server_script}")
        return False

    # 先移除旧的
    subprocess.run(["claude", "mcp", "remove", "stm32-toolkit"],
                   capture_output=True, text=True)

    # 设置环境变量（让 MCP Server 知道工具路径）
    env = os.environ.copy()
    if keil_path:
        env["KEIL_PATH"] = str(keil_path)
    if prog_path:
        env["STM32_PROGRAMMER"] = str(prog_path)

    cmd = [
        "claude", "mcp", "add",
        "--scope", "user",
        "--transport", "stdio",
        "stm32-toolkit",
        "--",
        sys.executable,
        str(server_script)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode == 0:
        ok("MCP Server 注册成功")
        info("  验证: claude mcp list")
        return True
    else:
        err(f"注册失败: {result.stderr}")
        return False

# ===================== 步骤 8: 生成恢复摘要 =====================
def generate_summary(keil_path, prog_path, mcp_ok):
    info("生成配置摘要...")

    summary = {
        "install_time": str(subprocess.check_output(["cmd", "/c", "echo %date% %time%"], text=True).strip()),
        "python": sys.executable,
        "claude_dir": str(CLAUDE_DIR),
        "keil_path": str(keil_path) if keil_path else None,
        "programmer_path": str(prog_path) if prog_path else None,
        "mcp_registered": mcp_ok,
        "templates": [f.name for f in TEMPLATES_DIR.iterdir()] if TEMPLATES_DIR.exists() else [],
        "skills": [f.name for f in SKILLS_DIR.iterdir()] if SKILLS_DIR.exists() else [],
    }

    summary_file = SCRIPT_DIR / "install_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    ok(f"配置摘要已保存: {summary_file}")
    return summary

# ===================== 主流程 =====================
def main():
    print("=" * 60)
    print("  STM32 AI 开发工作流 —— 一键安装/恢复")
    print("=" * 60)
    print()

    check_python()
    install_deps()
    install_global_claude_md()
    install_templates()
    install_skills()
    keil_path, prog_path = check_toolchain()
    mcp_ok = register_mcp(keil_path, prog_path)
    summary = generate_summary(keil_path, prog_path, mcp_ok)

    print()
    print("=" * 60)
    print("  安装完成！")
    print("=" * 60)
    print()

    if mcp_ok:
        ok("全部就绪，可以开始使用 Claude Code 进行 STM32 开发了")
        print()
        print("建议测试命令:")
        print('  1. claude mcp list          # 查看 MCP Server')
        print('  2. claude                   # 启动对话，说"编译当前工程"')
    else:
        warn("基础配置已完成，但 MCP Server 注册失败")
        print("请检查 Claude Code CLI 是否安装，然后手动注册:")
        print(f'  claude mcp add --scope user --transport stdio stm32-toolkit -- python {SCRIPT_DIR / "mcp" / "stm32_mcp_server.py"}')

    print()
    input("按回车键退出...")

if __name__ == "__main__":
    main()
