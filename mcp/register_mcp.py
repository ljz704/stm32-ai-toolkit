"""
STM32 MCP Server 一键注册脚本
自动检测环境并注册到 Claude Code。

使用方法:
    python register_mcp.py
"""

import os
import sys
import subprocess
import shutil

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
    """检查 Keil 和 STM32CubeProgrammer 是否存在。"""
    keil = r"C:\Keil_v5\UV4\UV4.exe"
    prog = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"

    if os.path.exists(keil):
        print(f"✅ Keil  found: {keil}")
    else:
        print(f"⚠️  Keil 未找到于默认路径: {keil}")
        print("   请在 stm32_mcp_server.py 中修改 KEIL_PATH，或通过环境变量 KEIL_PATH 指定")

    if os.path.exists(prog):
        print(f"✅ STM32CubeProgrammer found")
    else:
        print(f"⚠️  STM32CubeProgrammer 未找到于默认路径")
        print("   请在 stm32_mcp_server.py 中修改 PROGRAMMER_PATH，或通过环境变量 STM32_PROGRAMMER 指定")

def register_mcp(server_path: str, python_path: str):
    """注册 MCP Server 到 Claude Code。"""
    print("\n正在注册 MCP Server 到 Claude Code...")

    # 先尝试删除旧的（避免重复）
    subprocess.run(["claude", "mcp", "remove", "stm32-toolkit"], 
                   capture_output=True, text=True)

    cmd = [
        "claude", "mcp", "add",
        "--scope", "user",
        "--transport", "stdio",
        "stm32-toolkit",
        "--",
        python_path,
        server_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ 注册成功！")
        print("\n验证命令:")
        print("   claude mcp list")
        print("\n你应该能看到: stm32-toolkit (stdio)")
    else:
        print(f"❌ 注册失败: {result.stderr}")
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

    check_tools()

    python_path = find_python()
    server_path = find_server_script()

    print(f"\nPython 路径: {python_path}")
    print(f"Server 路径: {server_path}")

    confirm = input("\n确认注册? [Y/n]: ").strip().lower()
    if confirm in ("", "y", "yes"):
        register_mcp(server_path, python_path)
    else:
        print("已取消")

if __name__ == "__main__":
    main()
