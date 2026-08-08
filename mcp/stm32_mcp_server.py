"""
STM32 Toolkit MCP Server
为 Claude Code 提供编译、烧录、串口通信等原子操作工具。

安装依赖:
    pip install fastmcp pyserial

注册到 Claude Code:
    python register_mcp.py

或直接命令行:
    claude mcp add --scope project --transport stdio stm32-toolkit -- python <绝对路径>/stm32_mcp_server.py
"""

import subprocess
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError("请先安装 fastmcp: pip install fastmcp")

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ===================== 配置区（根据你的环境修改）=====================
# 如果环境变量中有定义，优先使用环境变量
KEIL_PATH = os.environ.get("KEIL_PATH", r"C:\Keil_v5\UV4\UV4.exe")
PROGRAMMER_PATH = os.environ.get("STM32_PROGRAMMER", 
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe")

# ===================== 初始化 MCP =====================
mcp = FastMCP("stm32-toolkit")

# ===================== 工具: Keil 编译 =====================
@mcp.tool()
def keil_build(project_path: str, rebuild: bool = False) -> dict:
    """
    使用 Keil UV4 命令行编译工程。

    Args:
        project_path: .uvprojx 文件的绝对路径
        rebuild: True 时先 Clean 再 Build，False 时仅 Build

    Returns:
        {
            "success": bool,
            "errors": list[str],
            "warnings": list[str],
            "code_size": {"flash": str, "ram": str},
            "log_path": str,
            "raw_output": str
        }
    """
    if not os.path.exists(project_path):
        return {"success": False, "errors": [f"工程文件不存在: {project_path}"], "warnings": [], "code_size": {}, "log_path": "", "raw_output": ""}

    project_dir = os.path.dirname(project_path)
    log_file = os.path.join(project_dir, "BuildLog.txt")

    # 如果存在旧日志，先删除
    if os.path.exists(log_file):
        os.remove(log_file)

    cmd = [KEIL_PATH]
    if rebuild:
        cmd += ["-c", project_path]  # Clean
        subprocess.run(cmd, capture_output=True, text=True)
        cmd = [KEIL_PATH, "-b", project_path, "-o", log_file, "-j0"]
    else:
        cmd += ["-b", project_path, "-o", log_file, "-j0"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    # 解析日志
    errors, warnings = [], []
    flash_size, ram_size = "", ""
    raw_log = ""

    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_log = f.read()

    # 提取错误和警告
    for line in raw_log.splitlines():
        if "error:" in line.lower() or "Error(s)" in line:
            errors.append(line.strip())
        if "warning:" in line.lower() or "Warning(s)" in line:
            warnings.append(line.strip())
        # 提取代码大小 (Keil 典型输出: Program Size: Code=xxx RO-data=xxx RW-data=xxx ZI-data=xxx)
        if "Program Size:" in line:
            parts = line.split("Program Size:")[-1]
            flash_match = re.search(r"Code=([\d]+)", parts)
            ram_match = re.search(r"RW-data=([\d]+).*ZI-data=([\d]+)", parts)
            if flash_match:
                flash_size = f"{flash_match.group(1)} bytes"
            if ram_match:
                rw = int(ram_match.group(1))
                zi = int(ram_match.group(2))
                ram_size = f"{rw + zi} bytes (RW={rw} + ZI={zi})"

    # 判断成功：BuildLog 中有 "0 Error(s)" 且命令返回码正常
    success = ("0 Error(s)" in raw_log) and (result.returncode == 0 or result.returncode == 1)

    return {
        "success": success,
        "errors": errors,
        "warnings": warnings,
        "code_size": {"flash": flash_size, "ram": ram_size},
        "log_path": log_file,
        "raw_output": raw_log[:2000]  # 限制长度
    }

@mcp.tool()
def keil_clean(project_path: str) -> dict:
    """清理 Keil 工程编译输出。"""
    if not os.path.exists(project_path):
        return {"success": False, "error": f"工程文件不存在: {project_path}"}

    cmd = [KEIL_PATH, "-c", project_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "error": result.stderr if result.stderr else None
    }

# ===================== 工具: ST-Link 烧录 =====================
@mcp.tool()
def stlink_flash(file_path: str, address: str = "0x08000000", verify: bool = True, reset: bool = True) -> dict:
    """
    通过 ST-Link SWD 接口烧录 hex/bin 文件。

    Args:
        file_path: 待烧录文件的绝对路径 (.hex 或 .bin)
        address: 烧录起始地址，hex 文件可忽略，bin 文件必须指定
        verify: 烧录后是否校验
        reset: 烧录后是否复位芯片

    Returns:
        {"success": bool, "output": str, "error": str|None}
    """
    if not os.path.exists(file_path):
        return {"success": False, "output": "", "error": f"文件不存在: {file_path}"}

    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "output": "", "error": f"STM32CubeProgrammer 未找到: {PROGRAMMER_PATH}"}

    cmd = [PROGRAMMER_PATH, "-c", "port=SWD", "-w", file_path, address]
    if verify:
        cmd.append("-v")
    if reset:
        cmd.append("-rst")

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    output = result.stdout + result.stderr

    success = "Download verified successfully" in output or "Programming Complete" in output
    return {
        "success": success,
        "output": output,
        "error": None if success else output
    }

@mcp.tool()
def stlink_erase() -> dict:
    """全片擦除 Flash。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "output": "", "error": f"STM32CubeProgrammer 未找到: {PROGRAMMER_PATH}"}

    cmd = [PROGRAMMER_PATH, "-c", "port=SWD", "-e", "all"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    output = result.stdout + result.stderr
    success = "Erase Memory ..." in output and "OK" in output
    return {
        "success": success,
        "output": output,
        "error": None if success else output
    }

@mcp.tool()
def probe_info() -> dict:
    """查询 ST-Link 连接状态和芯片信息。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "devices": [], "error": f"STM32CubeProgrammer 未找到: {PROGRAMMER_PATH}"}

    cmd = [PROGRAMMER_PATH, "-c", "port=SWD", "-r"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    output = result.stdout + result.stderr

    # 解析芯片信息
    devices = []
    for line in output.splitlines():
        if "Device" in line and ":" in line:
            devices.append(line.strip())
        if "Connection" in line and "OK" in line:
            devices.append(line.strip())

    connected = len(devices) > 0 or "Connection to device" in output
    return {
        "connected": connected,
        "devices": devices,
        "output": output,
        "error": None if connected else output
    }

# ===================== 工具: 串口通信 =====================
@mcp.tool()
def serial_list_ports() -> list:
    """列出可用串口，标记 ST-Link VCP。"""
    if not HAS_SERIAL:
        return [{"error": "pyserial 未安装，请运行: pip install pyserial"}]

    ports = []
    for p in serial.tools.list_ports.comports():
        desc = p.description or ""
        is_stlink = "ST-Link" in desc or "STM32" in desc
        ports.append({
            "port": p.device,
            "description": desc,
            "vid": f"0x{p.vid:04X}" if p.vid else None,
            "pid": f"0x{p.pid:04X}" if p.pid else None,
            "is_stlink_vcp": is_stlink
        })
    return ports

@mcp.tool()
def serial_send(port: str, baudrate: int, data: str, timeout: float = 2.0) -> dict:
    """
    打开串口发送数据并读取响应。

    Args:
        port: 串口号，如 COM3
        baudrate: 波特率，如 115200
        data: 要发送的字符串
        timeout: 读取超时（秒）

    Returns:
        {"success": bool, "sent": str, "response": str, "error": str|None}
    """
    if not HAS_SERIAL:
        return {"success": False, "sent": data, "response": "", "error": "pyserial 未安装"}

    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            ser.write(data.encode("utf-8"))
            response = ser.read(4096).decode("utf-8", errors="ignore")
            return {
                "success": True,
                "sent": data,
                "response": response,
                "error": None
            }
    except Exception as e:
        return {
            "success": False,
            "sent": data,
            "response": "",
            "error": str(e)
        }

@mcp.tool()
def serial_read(port: str, baudrate: int, length: int = 1024, timeout: float = 2.0) -> dict:
    """打开串口读取数据。"""
    if not HAS_SERIAL:
        return {"success": False, "response": "", "error": "pyserial 未安装"}

    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            response = ser.read(length).decode("utf-8", errors="ignore")
            return {
                "success": True,
                "response": response,
                "error": None
            }
    except Exception as e:
        return {
            "success": False,
            "response": "",
            "error": str(e)
        }

# ===================== 工具: 日志解析 =====================
@mcp.tool()
def parse_build_log(log_path: str) -> dict:
    """
    解析 Keil BuildLog.txt，提取错误、警告、代码大小。

    Args:
        log_path: BuildLog.txt 的绝对路径

    Returns:
        {
            "summary": str,
            "errors": list[dict],
            "warnings": list[dict],
            "code_size": dict,
            "suggestions": list[str]
        }
    """
    if not os.path.exists(log_path):
        return {"summary": "日志文件不存在", "errors": [], "warnings": [], "code_size": {}, "suggestions": []}

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    errors = []
    warnings = []
    suggestions = []

    for line in content.splitlines():
        # 匹配 Keil 错误格式: file(line): error: message
        err_match = re.match(r"(.+)\((\d+)\): error: (.+)", line)
        if err_match:
            errors.append({
                "file": err_match.group(1).strip(),
                "line": int(err_match.group(2)),
                "message": err_match.group(3).strip()
            })

        warn_match = re.match(r"(.+)\((\d+)\): warning: (.+)", line)
        if warn_match:
            warnings.append({
                "file": warn_match.group(1).strip(),
                "line": int(warn_match.group(2)),
                "message": warn_match.group(3).strip()
            })

    # 提取汇总行
    summary = ""
    for line in content.splitlines():
        if "Error(s)" in line and "Warning(s)" in line:
            summary = line.strip()
            break

    # 自动建议
    if any("No such file" in e["message"] for e in errors):
        suggestions.append("缺少头文件：检查 C/C++ Include Paths 是否包含该头文件所在目录")
    if any("undefined reference" in e["message"] for e in errors):
        suggestions.append("未定义符号：检查是否缺少对应的 .c 源文件或库文件")
    if any("overflowed" in e["message"] for e in errors):
        suggestions.append("内存溢出：检查 RAM/Flash 使用量，或优化全局变量")

    return {
        "summary": summary or f"发现 {len(errors)} 个错误, {len(warnings)} 个警告",
        "errors": errors,
        "warnings": warnings,
        "code_size": {},
        "suggestions": suggestions
    }

# ===================== 工具: 查找编译输出文件 =====================
@mcp.tool()
def find_build_output(project_path: str) -> dict:
    """
    查找 Keil 工程编译生成的 .hex / .bin 文件。

    Args:
        project_path: .uvprojx 文件路径

    Returns:
        {"hex": str|None, "bin": str|None, "elf": str|None}
    """
    project_dir = os.path.dirname(project_path)
    candidates = ["Objects", "Listings", ".", "build"]

    result = {"hex": None, "bin": None, "elf": None}

    for sub in candidates:
        search_dir = os.path.join(project_dir, sub)
        if not os.path.exists(search_dir):
            continue
        for f in os.listdir(search_dir):
            fpath = os.path.join(search_dir, f)
            if f.lower().endswith(".hex") and result["hex"] is None:
                result["hex"] = fpath
            if f.lower().endswith(".bin") and result["bin"] is None:
                result["bin"] = fpath
            if f.lower().endswith(".axf") and result["elf"] is None:
                result["elf"] = fpath

    return result

# ===================== 入口 =====================
if __name__ == "__main__":
    mcp.run()
