# -*- coding: utf-8 -*-
"""
STM32 MCP Server 一键注册脚本
自动检测环境并注册到 Claude Code。

使用方法:
    python mcp/register_mcp.py
"""

import os
import sys
import shutil
from pathlib import Path

# 让根目录 _cmdutil.py 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _cmdutil import fix_console_encoding, run_cmd

fix_console_encoding()

# ===================== 默认工具路径（可用环境变量覆盖） =====================
def _resolve_keil() -> str:
    """Keil 探测：环境变量 → 常见默认路径。"""
    env = os.environ.get("KEIL_PATH")
    if env:
        return env
    for p in (
        r"C:\Keil_v5\UV4\UV4.exe",
        r"D:\Keil_v5\UV4\UV4.exe",
        r"C:\Keil\UV4\UV4.exe",
    ):
        if os.path.exists(p):
            return p
    return os.environ.get("KEIL_PATH", r"C:\Keil_v5\UV4\UV4.exe")


DEFAULT_KEIL = _resolve_keil()


def _resolve_prog() -> str:
    """STM32CubeProgrammer 探测：环境变量 → 常见默认路径（C:/D: 盘都试）。"""
    env = os.environ.get("STM32_PROGRAMMER")
    if env:
        return env
    for p in (
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
        r"D:\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
    ):
        if os.path.exists(p):
            return p
    return os.environ.get("STM32_PROGRAMMER",
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe")


DEFAULT_PROG = _resolve_prog()


def _resolve_cubemx() -> str:
    """STM32CubeMX 探测：环境变量 → 常见默认路径。"""
    env = os.environ.get("CUBEMX_PATH")
    if env:
        return env
    for p in (
        r"D:\STM32CubeMX\STM32CubeMX.exe",
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe",
        r"C:\STM32CubeMX\STM32CubeMX.exe",
    ):
        if os.path.exists(p):
            return p
    return os.environ.get("CUBEMX_PATH", r"D:\STM32CubeMX\STM32CubeMX.exe")


DEFAULT_CUBEMX = _resolve_cubemx()


def find_python() -> str:
    """找到当前 Python 解释器的绝对路径。"""
    return os.path.abspath(sys.executable)


def find_server_script() -> str:
    """找到 stm32_mcp_server.py 的路径（假设和本脚本同目录）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "stm32_mcp_server.py")
    if os.path.exists(server_path):
        return os.path.abspath(server_path)

    # 如果不在同目录，提示用户输入
    print("未在同目录找到 stm32_mcp_server.py")
    user_path = input("请输入 stm32_mcp_server.py 的绝对路径: ").strip().strip('"')
    if os.path.exists(user_path):
        return os.path.abspath(user_path)
    print(f"文件不存在: {user_path}")
    sys.exit(1)


def check_claude_code() -> bool:
    """检查 claude 命令是否可用。"""
    return shutil.which("claude") is not None


def check_dependencies():
    """检查必要的 Python 包。"""
    missing = []
    try:
        import fastmcp
    except ImportError:
        missing.append("fastmcp")
    try:
        import serial
    except ImportError:
        missing.append("pyserial")

    if missing:
        print(f"❌ 缺少依赖: {', '.join(missing)}")
        print(f"   请运行: pip install {' '.join(missing)}")
        return False
    print("✅ Python 依赖检查通过")
    return True


def check_tools():
    """检查 Keil / STM32CubeProgrammer / STM32CubeMX 是否存在。"""
    keil = DEFAULT_KEIL
    prog = DEFAULT_PROG
    cubemx = DEFAULT_CUBEMX

    if os.path.exists(keil):
        print(f"✅ Keil found: {keil}")
    else:
        print(f"⚠️  Keil 未找到: {keil}")
        print("   请通过环境变量 KEIL_PATH 指定（安装脚本会把它写入注册配置）")

    if os.path.exists(prog):
        print("✅ STM32CubeProgrammer found")
    else:
        print("⚠️  STM32CubeProgrammer 未找到于默认路径")
        print("   请通过环境变量 STM32_PROGRAMMER 指定")

    if os.path.exists(cubemx):
        print(f"✅ STM32CubeMX found: {cubemx}")
    else:
        print("⚠️  STM32CubeMX 未找到于默认路径")
        print("   请通过环境变量 CUBEMX_PATH 指定（cubemx_generate 依赖它）")

    return os.path.exists(keil), os.path.exists(prog), os.path.exists(cubemx)


def register_mcp(server_path: str, python_path: str, keil_ok: bool, prog_ok: bool,
                 cubemx_ok: bool = False):
    """注册 MCP Server 到 Claude Code。"""
    print("\n正在注册 MCP Server 到 Claude Code...")

    # 先尝试删除旧的（避免重复）
    run_cmd(["claude", "mcp", "remove", "stm32-toolkit"], timeout=60)

    # 工具路径用 -e KEY=VALUE 写进注册配置，server 运行时才能读到
    cmd = ["claude", "mcp", "add", "--scope", "user", "--transport", "stdio", "stm32-toolkit"]
    if keil_ok:
        cmd += ["-e", f"KEIL_PATH={DEFAULT_KEIL}"]
    if prog_ok:
        cmd += ["-e", f"STM32_PROGRAMMER={DEFAULT_PROG}"]
    if cubemx_ok:
        cmd += ["-e", f"CUBEMX_PATH={DEFAULT_CUBEMX}"]
    cmd += ["--", python_path, server_path]

    result = run_cmd(cmd, timeout=60)
    if result.ok:
        print("✅ 注册成功！")
        print("\n验证命令:")
        print("   claude mcp get stm32-toolkit")
        print("\n确认 command 指向的 server 路径正确")
    else:
        print(f"❌ 注册失败: {result.stderr or result.error}")
        print("\n请手动运行:")
        print(f"   claude mcp add --scope user --transport stdio stm32-toolkit -- {python_path} {server_path}")


def main():
    print("=" * 60)
    print("  STM32 MCP Server 注册向导")
    print("=" * 60)

    if not check_claude_code():
        print("❌ 未找到 claude 命令，请确保 Claude Code 已安装并加入 PATH")
        sys.exit(1)
    print("✅ Claude Code CLI 已找到")

    if not check_dependencies():
        sys.exit(1)

    keil_ok, prog_ok, cubemx_ok = check_tools()

    python_path = find_python()
    server_path = find_server_script()

    print(f"\nPython 路径: {python_path}")
    print(f"Server 路径: {server_path}")

    confirm = input("\n确认注册? [Y/n]: ").strip().lower()
    if confirm in ("", "y", "yes"):
        register_mcp(server_path, python_path, keil_ok, prog_ok, cubemx_ok)
    else:
        print("已取消")


if __name__ == "__main__":
    main()
