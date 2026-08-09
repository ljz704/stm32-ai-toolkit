#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 Toolkit MCP Server v2.0
增强功能：
  - 串口后台监控（serial_monitor_start/stop/read）
  - 编译日志深度解析 + 自动修复建议
  - 所有工具返回结构化数据，支持 AI 展示原始数据

安装依赖:
    pip install fastmcp pyserial

注册:
    python scripts/register_mcp.py
"""

import subprocess
import os
import re
import threading
import time
from collections import deque
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

# ===================== 配置区 =====================
KEIL_PATH = os.environ.get("KEIL_PATH", r"C:\Keil_v5\UV4\UV4.exe")
PROGRAMMER_PATH = os.environ.get("STM32_PROGRAMMER",
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe")

mcp = FastMCP("stm32-toolkit")

# ===================== 全局串口监控状态 =====================
_serial_monitors = {}

# ===================== 工具: Keil 编译 =====================
@mcp.tool()
def keil_build(project_path: str, rebuild: bool = False) -> dict:
    """使用 Keil UV4 命令行编译工程，返回结构化结果。"""
    if not os.path.exists(project_path):
        return {"success": False, "errors": [f"工程文件不存在: {project_path}"],
                "warnings": [], "code_size": {}, "log_path": "", "raw_output": "",
                "display_for_user": f"❌ 工程文件未找到: {project_path}"}

    project_dir = os.path.dirname(project_path)
    log_file = os.path.join(project_dir, "BuildLog.txt")
    if os.path.exists(log_file):
        os.remove(log_file)

    cmd = [KEIL_PATH]
    if rebuild:
        subprocess.run([KEIL_PATH, "-c", project_path], capture_output=True, text=True)
        cmd += ["-b", project_path, "-o", log_file, "-j0"]
    else:
        cmd += ["-b", project_path, "-o", log_file, "-j0"]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    errors, warnings = [], []
    flash_size, ram_size = "", ""
    raw_log = ""

    if os.path.exists(log_file):
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_log = f.read()

    for line in raw_log.splitlines():
        if "error:" in line.lower() or "Error(s)" in line:
            errors.append(line.strip())
        if "warning:" in line.lower() or "Warning(s)" in line:
            warnings.append(line.strip())
        if "Program Size:" in line:
            parts = line.split("Program Size:")[-1]
            fm = re.search(r"Code=(\d+)", parts)
            rm = re.search(r"RW-data=(\d+).*ZI-data=(\d+)", parts)
            if fm:
                flash_size = f"{fm.group(1)} bytes"
            if rm:
                rw, zi = int(rm.group(1)), int(rm.group(2))
                ram_size = f"{rw + zi} bytes (RW={rw} + ZI={zi})"

    success = ("0 Error(s)" in raw_log) and (result.returncode in [0, 1])

    # 生成给用户看的友好输出
    if success:
        display = f"""✅ 编译成功
📦 Flash: {flash_size or 'N/A'}
💾 RAM:   {ram_size or 'N/A'}
⚠️  Warnings: {len(warnings)} 个
📄 日志: {log_file}"""
    else:
        display = f"""❌ 编译失败
🐛 Errors:   {len(errors)} 个
⚠️  Warnings: {len(warnings)} 个
📄 日志: {log_file}

前 3 个错误:
""" + "\n".join(errors[:3])

    return {
        "success": success,
        "errors": errors,
        "warnings": warnings,
        "code_size": {"flash": flash_size, "ram": ram_size},
        "log_path": log_file,
        "raw_output": raw_log[:3000],
        "display_for_user": display  # AI 必须展示这个字段
    }

@mcp.tool()
def keil_clean(project_path: str) -> dict:
    """清理 Keil 工程。"""
    if not os.path.exists(project_path):
        return {"success": False, "error": f"工程文件不存在: {project_path}"}
    result = subprocess.run([KEIL_PATH, "-c", project_path], capture_output=True, text=True)
    return {"success": result.returncode == 0, "output": result.stdout,
            "error": result.stderr if result.stderr else None}

# ===================== 工具: ST-Link 烧录 =====================
@mcp.tool()
def stlink_flash(file_path: str, address: str = "0x08000000", verify: bool = True, reset: bool = True) -> dict:
    """通过 ST-Link SWD 烧录 hex/bin。"""
    if not os.path.exists(file_path):
        return {"success": False, "output": "", "error": f"文件不存在: {file_path}",
                "display_for_user": f"❌ 烧录文件未找到: {file_path}"}
    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "output": "", "error": f"Programmer 未找到: {PROGRAMMER_PATH}",
                "display_for_user": "❌ STM32CubeProgrammer 未安装"}

    cmd = [PROGRAMMER_PATH, "-c", "port=SWD", "-w", file_path, address]
    if verify: cmd.append("-v")
    if reset: cmd.append("-rst")

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    output = result.stdout + result.stderr
    success = "Download verified successfully" in output or "Programming Complete" in output

    display = "✅ 烧录成功，芯片已复位运行" if success else f"❌ 烧录失败\n{output[:500]}"

    return {"success": success, "output": output, "error": None if success else output,
            "display_for_user": display}

@mcp.tool()
def stlink_erase() -> dict:
    """全片擦除。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "error": "Programmer 未找到"}
    result = subprocess.run([PROGRAMMER_PATH, "-c", "port=SWD", "-e", "all"],
                            capture_output=True, text=True)
    output = result.stdout + result.stderr
    success = "Erase Memory" in output and "OK" in output
    return {"success": success, "output": output,
            "display_for_user": "✅ 擦除完成" if success else f"❌ 擦除失败\n{output[:300]}"}

@mcp.tool()
def probe_info() -> dict:
    """查询 ST-Link 连接状态。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"connected": False, "devices": [], "error": "Programmer 未找到"}
    result = subprocess.run([PROGRAMMER_PATH, "-c", "port=SWD", "-r"],
                            capture_output=True, text=True)
    output = result.stdout + result.stderr
    devices = [l.strip() for l in output.splitlines() if "Device" in l or "Connection" in l]
    connected = len(devices) > 0 or "Connection to device" in output
    return {"connected": connected, "devices": devices, "output": output,
            "display_for_user": "✅ ST-Link 已连接" if connected else "❌ ST-Link 未连接"}

# ===================== 工具: 串口（单次） =====================
@mcp.tool()
def serial_list_ports() -> list:
    """列出可用串口。"""
    if not HAS_SERIAL:
        return [{"error": "pyserial 未安装"}]
    ports = []
    for p in serial.tools.list_ports.comports():
        is_stlink = "ST-Link" in (p.description or "")
        ports.append({"port": p.device, "description": p.description or "",
                      "is_stlink_vcp": is_stlink})
    return ports

@mcp.tool()
def serial_send(port: str, baudrate: int, data: str, timeout: float = 2.0) -> dict:
    """发送数据并读取响应。"""
    if not HAS_SERIAL:
        return {"success": False, "sent": data, "response": "", "error": "pyserial 未安装"}
    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            ser.write(data.encode("utf-8"))
            response = ser.read(4096).decode("utf-8", errors="ignore")
            return {"success": True, "sent": data, "response": response, "error": None,
                    "display_for_user": f"📤 发送: {data}\n📥 接收:\n```text\n{response}\n```"}
    except Exception as e:
        return {"success": False, "sent": data, "response": "", "error": str(e),
                "display_for_user": f"❌ 串口错误: {e}"}

@mcp.tool()
def serial_read(port: str, baudrate: int, length: int = 1024, timeout: float = 2.0) -> dict:
    """读取串口数据。"""
    if not HAS_SERIAL:
        return {"success": False, "response": "", "error": "pyserial 未安装"}
    try:
        with serial.Serial(port, baudrate, timeout=timeout) as ser:
            response = ser.read(length).decode("utf-8", errors="ignore")
            return {"success": True, "response": response, "error": None,
                    "display_for_user": f"📥 串口数据 ({port}):\n```text\n{response}\n```"}
    except Exception as e:
        return {"success": False, "response": "", "error": str(e),
                "display_for_user": f"❌ 串口错误: {e}"}

# ===================== 工具: 串口后台监控（新增） =====================
@mcp.tool()
def serial_monitor_start(port: str, baudrate: int, max_lines: int = 200) -> dict:
    """
    启动后台串口监控线程，持续缓存最近 N 行数据。
    可与 serial_live.py 独立脚本配合使用。
    """
    if not HAS_SERIAL:
        return {"success": False, "error": "pyserial 未安装"}
    if port in _serial_monitors and _serial_monitors[port]["running"]:
        return {"success": False, "error": f"串口 {port} 已在监控中"}

    buffer = deque(maxlen=max_lines)
    running = True

    def monitor_loop():
        try:
            with serial.Serial(port, baudrate, timeout=0.1) as ser:
                line_buf = ""
                while _serial_monitors.get(port, {}).get("running", False):
                    data = ser.read(2048).decode("utf-8", errors="ignore")
                    if data:
                        line_buf += data
                        while "\n" in line_buf:
                            line, line_buf = line_buf.split("\n", 1)
                            buffer.append(line.strip())
                # 剩余数据
                if line_buf.strip():
                    buffer.append(line_buf.strip())
        except Exception as e:
            buffer.append(f"[MONITOR_ERROR] {str(e)}")

    thread = threading.Thread(target=monitor_loop, daemon=True)
    _serial_monitors[port] = {"thread": thread, "buffer": buffer, "running": True}
    thread.start()

    return {
        "success": True,
        "monitor_id": port,
        "message": f"串口 {port} 监控已启动，缓存最近 {max_lines} 行",
        "display_for_user": f"🟢 串口 {port} 监控已启动\n   缓存: {max_lines} 行\n   使用 serial_monitor_read 读取数据"
    }

@mcp.tool()
def serial_monitor_read(port: str, lines: int = 30) -> dict:
    """读取监控缓存中的最近 N 行。"""
    if port not in _serial_monitors:
        return {"success": False, "error": f"串口 {port} 未在监控中",
                "display_for_user": f"❌ 串口 {port} 未启动监控，请先调用 serial_monitor_start"}

    buf = list(_serial_monitors[port]["buffer"])
    recent = buf[-lines:] if len(buf) >= lines else buf
    text = "\n".join(recent)

    return {
        "success": True,
        "lines": recent,
        "total_buffered": len(buf),
        "display_for_user": f"📥 串口 {port} 最近 {len(recent)} 行数据:\n```text\n{text}\n```"
    }

@mcp.tool()
def serial_monitor_stop(port: str) -> dict:
    """停止串口监控。"""
    if port in _serial_monitors:
        _serial_monitors[port]["running"] = False
        del _serial_monitors[port]
        return {"success": True, "message": f"串口 {port} 监控已停止",
                "display_for_user": f"🔴 串口 {port} 监控已停止"}
    return {"success": False, "error": f"串口 {port} 未在监控中",
            "display_for_user": f"⚠️ 串口 {port} 未在监控中"}

# ===================== 工具: 日志解析 =====================
@mcp.tool()
def parse_build_log(log_path: str) -> dict:
    """解析 Keil BuildLog.txt。"""
    if not os.path.exists(log_path):
        return {"summary": "日志文件不存在", "errors": [], "warnings": [],
                "code_size": {}, "suggestions": []}
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    errors, warnings, suggestions = [], [], []
    for line in content.splitlines():
        em = re.match(r"(.+)\((\d+)\): error: (.+)", line)
        if em:
            errors.append({"file": em.group(1).strip(), "line": int(em.group(2)),
                           "message": em.group(3).strip()})
        wm = re.match(r"(.+)\((\d+)\): warning: (.+)", line)
        if wm:
            warnings.append({"file": wm.group(1).strip(), "line": int(wm.group(2)),
                             "message": wm.group(3).strip()})

    summary = next((l.strip() for l in content.splitlines() if "Error(s)" in l and "Warning(s)" in l), "")

    if any("No such file" in e["message"] for e in errors):
        suggestions.append("缺少头文件：检查 C/C++ Include Paths")
    if any("undefined reference" in e["message"] for e in errors):
        suggestions.append("未定义符号：检查是否缺少 .c 源文件")
    if any("overflowed" in e["message"] for e in errors):
        suggestions.append("内存溢出：优化变量或调整 scatter 文件")

    return {"summary": summary or f"{len(errors)} 错误, {len(warnings)} 警告",
            "errors": errors, "warnings": warnings, "suggestions": suggestions}

@mcp.tool()
def find_build_output(project_path: str) -> dict:
    """查找编译输出文件。"""
    project_dir = os.path.dirname(project_path)
    result = {"hex": None, "bin": None, "elf": None}
    for sub in ["Objects", "Listings", ".", "build"]:
        sd = os.path.join(project_dir, sub)
        if os.path.exists(sd):
            for f in os.listdir(sd):
                fp = os.path.join(sd, f)
                if f.lower().endswith(".hex") and not result["hex"]: result["hex"] = fp
                if f.lower().endswith(".bin") and not result["bin"]: result["bin"] = fp
                if f.lower().endswith(".axf") and not result["elf"]: result["elf"] = fp
    return result

if __name__ == "__main__":
    mcp.run()
