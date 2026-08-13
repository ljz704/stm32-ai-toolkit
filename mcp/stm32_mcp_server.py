# -*- coding: utf-8 -*-
"""
STM32 Toolkit MCP Server（权威版）
=====================================
为 Claude Code 提供编译、烧录、串口通信、日志解析等原子操作工具。

本文件是 v1/v2 合并后的唯一权威 server：
  - 含后台串口监控（serial_monitor_start/read/stop）
  - 所有工具返回结构化数据 + display_for_user 字段（配合 skill 强制展示原始数据）
  - 统一 subprocess 封装（超时 / 编码回退 / 异常捕获），Keil 卡死不冻结会话

安装依赖:
    pip install fastmcp pyserial

注册:
    python mcp/register_mcp.py
    （或 install.py 一键注册）
"""

import subprocess  # noqa: F401  （run_cmd 内部使用，保留供 import 可见）
import json
import os
import re
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Optional  # noqa: F401

# 让根目录 _cmdutil.py 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _cmdutil import run_cmd, smart_decode  # noqa: E402

# 保护 stdout：即便 fastmcp 以文本模式写 JSON（含 emoji/中文），也不抛 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    _rc = getattr(_stream, "reconfigure", None)
    if _rc:
        try:
            _rc(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

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
CUBEMX_PATH = os.environ.get("CUBEMX_PATH", r"D:\STM32CubeMX\STM32CubeMX.exe")
# CubeMX 无头生成后端脚本（工具包根目录，与 MCP server 同仓）
CUBEMX_GEN = str(Path(__file__).resolve().parent.parent / "cubemx_gen.py")

mcp = FastMCP("stm32-toolkit")

# ===================== 全局串口监控状态 =====================
_serial_monitors = {}

# ===================== 串口打开辅助 =====================
def _open_serial(port: str, baudrate: int, timeout: float):
    """打开串口并保持 DTR/RTS 为低。

    pyserial 默认 dtr/rts 置位，open/close 的电流抖动会把接了自动复位电路
    （如 DTR 接 NRST）的板子反复复位。置为 False 不影响 ST-Link VCP 正常通信。
    """
    ser = serial.Serial(port, baudrate, timeout=timeout, dtr=False, rts=False)
    ser.set_dtr(False)
    ser.set_rts(False)
    return ser


def _is_monitored(port: str) -> bool:
    mon = _serial_monitors.get(port)
    return bool(mon and mon.get("running"))


def _read_text_file(path):
    """读文本文件，UTF-8 → 系统编码回退，中文不乱码。"""
    try:
        return smart_decode(Path(path).read_bytes())
    except OSError:
        return ""


# ===================== 工具: Keil 编译 =====================
@mcp.tool()
def keil_build(project_path: str, rebuild: bool = False) -> dict:
    """使用 Keil UV4 命令行编译工程，返回结构化结果。"""
    if not os.path.exists(project_path):
        return {"success": False, "errors": [f"工程文件不存在: {project_path}"],
                "warnings": [], "code_size": {}, "log_path": "", "raw_output": "",
                "display_for_user": f"❌ 工程文件未找到: {project_path}"}

    if not os.path.exists(KEIL_PATH):
        return {"success": False, "errors": [f"Keil 未找到: {KEIL_PATH}"],
                "warnings": [], "code_size": {}, "log_path": "",
                "raw_output": "",
                "display_for_user": f"❌ Keil 未找到: {KEIL_PATH}\n   请检查 KEIL_PATH 环境变量"}

    project_dir = os.path.dirname(project_path)
    log_file = os.path.join(project_dir, "BuildLog.txt")
    if os.path.exists(log_file):
        os.remove(log_file)

    cmd = [KEIL_PATH, "-b", project_path, "-o", log_file, "-j0"]
    if rebuild:
        clean = run_cmd([KEIL_PATH, "-c", project_path], timeout=300)
        if clean.error or clean.timed_out:
            return {"success": False, "errors": [clean.combined.strip() or "Keil Clean 失败"],
                    "warnings": [], "code_size": {}, "log_path": log_file,
                    "raw_output": clean.combined,
                    "display_for_user": f"❌ Keil Clean 失败\n{clean.combined[:500]}"}

    result = run_cmd(cmd, timeout=300)
    if result.error:
        return {"success": False, "errors": [result.error], "warnings": [],
                "code_size": {}, "log_path": log_file, "raw_output": result.stderr,
                "display_for_user": f"❌ 无法启动 Keil: {result.error}"}
    if result.timed_out:
        return {"success": False,
                "errors": ["Keil 编译超时(>300s)，检查工程是否过大或 Keil 弹窗卡住"],
                "warnings": [], "code_size": {}, "log_path": log_file,
                "raw_output": result.stderr,
                "display_for_user": "❌ Keil 编译超时(>300s)，请检查 Keil 是否有弹窗"}

    raw_log = _read_text_file(log_file)
    errors, warnings = [], []
    flash_size, ram_size = "", ""

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
    if not os.path.exists(KEIL_PATH):
        return {"success": False, "error": f"Keil 未找到: {KEIL_PATH}"}
    result = run_cmd([KEIL_PATH, "-c", project_path], timeout=120)
    return {"success": result.returncode == 0 and not result.error,
            "output": result.stdout,
            "error": result.stderr if (result.stderr or result.error) else None}


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

    result = run_cmd(cmd, timeout=120)
    output = result.combined
    # 成功判定：returncode==0 + 输出无错误关键字（不依赖英文成功子串，跨版本/跨语言稳定）
    failed = any(k in output.lower() for k in ("error", "fail", "no st-link", "unable"))
    success = result.ok and not failed

    display = "✅ 烧录成功，芯片已复位运行" if success else f"❌ 烧录失败\n{output[:500]}"

    return {"success": success, "output": output, "error": None if success else output,
            "display_for_user": display}


@mcp.tool()
def stlink_erase() -> dict:
    """全片擦除。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"success": False, "error": "Programmer 未找到"}
    result = run_cmd([PROGRAMMER_PATH, "-c", "port=SWD", "-e", "all"], timeout=120)
    output = result.combined
    failed = any(k in output.lower() for k in ("error", "fail", "no st-link", "unable"))
    success = result.ok and not failed
    return {"success": success, "output": output,
            "display_for_user": "✅ 擦除完成" if success else f"❌ 擦除失败\n{output[:300]}"}


@mcp.tool()
def probe_info() -> dict:
    """查询 ST-Link 连接状态。"""
    if not os.path.exists(PROGRAMMER_PATH):
        return {"connected": False, "devices": [], "error": "Programmer 未找到"}
    result = run_cmd([PROGRAMMER_PATH, "-c", "port=SWD", "-r"], timeout=30)
    output = result.combined
    # 恢复严格判定：只有 "Connection ... OK" 或 "Device Name:" 才算连上，
    # 避免 "Connection error: No ST-Link found" 被误判为已连接
    devices = [l.strip() for l in output.splitlines()
               if ("Device" in l and ":" in l) or ("Connection" in l and "OK" in l)]
    connected = bool(devices) or (
        "Connection to device" in output and "error" not in output.lower())
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
    if _is_monitored(port):
        return {"success": False, "sent": data, "response": "", "error":
                f"串口 {port} 正被 serial_monitor 占用，请先 serial_monitor_stop 或改用 serial_monitor_read",
                "display_for_user": f"❌ 串口 {port} 正被监控占用"}
    try:
        with _open_serial(port, baudrate, timeout=timeout) as ser:
            ser.reset_input_buffer()
            ser.write(data.encode("utf-8"))
            ser.flush()
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
    if _is_monitored(port):
        return {"success": False, "response": "", "error":
                f"串口 {port} 正被 serial_monitor 占用，请改用 serial_monitor_read",
                "display_for_user": f"❌ 串口 {port} 正被监控占用，请用 serial_monitor_read 读取"}
    try:
        with _open_serial(port, baudrate, timeout=timeout) as ser:
            response = ser.read(length).decode("utf-8", errors="ignore")
            return {"success": True, "response": response, "error": None,
                    "display_for_user": f"📥 串口数据 ({port}):\n```text\n{response}\n```"}
    except Exception as e:
        return {"success": False, "response": "", "error": str(e),
                "display_for_user": f"❌ 串口错误: {e}"}


# ===================== 工具: 串口后台监控 =====================
@mcp.tool()
def serial_monitor_start(port: str, baudrate: int, max_lines: int = 200) -> dict:
    """
    启动后台串口监控线程，持续缓存最近 N 行数据。
    可与 serial_live.py 独立脚本配合使用。
    """
    if not HAS_SERIAL:
        return {"success": False, "error": "pyserial 未安装"}
    mon = _serial_monitors.get(port)
    if mon and mon.get("running"):
        return {"success": False, "error": f"串口 {port} 已在监控中"}
    _serial_monitors.pop(port, None)  # 清掉上次残留条目，防止旧 buffer 复用

    buffer = deque(maxlen=max_lines)
    running = {"flag": True}  # 可变容器，跨线程可见

    def monitor_loop():
        try:
            with _open_serial(port, baudrate, timeout=0.1) as ser:
                line_buf = ""
                while running["flag"]:
                    data = ser.read(2048).decode("utf-8", errors="ignore")
                    if data:
                        line_buf += data
                        while "\n" in line_buf:
                            line, line_buf = line_buf.split("\n", 1)
                            buffer.append(line.strip())
                if line_buf.strip():
                    buffer.append(line_buf.strip())
        except Exception as e:
            buffer.append(f"[MONITOR_ERROR] {str(e)}")
        finally:
            # 无论正常退出还是异常，都置 running=False、保留 buffer 供 read，
            # 避免僵尸条目让后续 start/stop/read 全部异常
            running["flag"] = False
            if _serial_monitors.get(port) is mon:
                _serial_monitors[port] = {"thread": None, "buffer": buffer, "running": False}

    thread = threading.Thread(target=monitor_loop, daemon=True)
    _serial_monitors[port] = {"thread": thread, "buffer": buffer, "running": running}
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
    mon = _serial_monitors.get(port)
    if mon is None:
        return {"success": False, "error": f"串口 {port} 未在监控中",
                "display_for_user": f"❌ 串口 {port} 未启动监控，请先调用 serial_monitor_start"}

    buf = list(mon["buffer"])
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
    mon = _serial_monitors.get(port)
    if mon is None:
        return {"success": False, "error": f"串口 {port} 未在监控中",
                "display_for_user": f"⚠️ 串口 {port} 未在监控中"}
    if isinstance(mon["running"], dict):
        mon["running"]["flag"] = False  # 通知线程退出
    else:
        mon["running"] = False
    thr = mon.get("thread")
    if thr is not None and thr.is_alive():
        thr.join(timeout=2.0)  # 等线程真正退出，释放串口句柄
    _serial_monitors.pop(port, None)  # 身份守卫保证线程 finally 不再重建条目
    return {"success": True, "message": f"串口 {port} 监控已停止",
            "display_for_user": f"🔴 串口 {port} 监控已停止"}


# ===================== 工具: 日志解析 =====================
@mcp.tool()
def parse_build_log(log_path: str) -> dict:
    """解析 Keil BuildLog.txt。"""
    if not os.path.exists(log_path):
        return {"summary": "日志文件不存在", "errors": [], "warnings": [],
                "code_size": {}, "suggestions": []}
    content = _read_text_file(log_path)

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
        # Keil AC5 链接器错误格式：.\Objects\xxx.o: Error: L6218E: Undefined symbol ...
        lm = re.match(r"(.+\.o): Error: (L\d+E): (.+)", line)
        if lm:
            errors.append({"file": lm.group(1).strip(), "line": 0,
                           "message": f"{lm.group(2)}: {lm.group(3).strip()}"})

    summary = next((l.strip() for l in content.splitlines() if "Error(s)" in l and "Warning(s)" in l), "")

    if any("No such file" in e["message"] for e in errors):
        suggestions.append("缺少头文件：检查 C/C++ Include Paths")
    if any("undefined reference" in e["message"] for e in errors):
        suggestions.append("未定义符号：检查是否缺少 .c 源文件")
    if any("overflowed" in e["message"] for e in errors):
        suggestions.append("内存溢出：优化变量或调整 scatter 文件")
    if any(e["message"].startswith("L62") for e in errors):
        suggestions.append("链接错误：检查是否缺少 .c 源文件或库，或符号拼写")

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
            try:
                entries = os.listdir(sd)
            except OSError:
                continue
            for f in entries:
                fp = os.path.join(sd, f)
                if f.lower().endswith(".hex") and not result["hex"]: result["hex"] = fp
                if f.lower().endswith(".bin") and not result["bin"]: result["bin"] = fp
                if f.lower().endswith(".axf") and not result["elf"]: result["elf"] = fp
    return result


# ===================== 工具: STM32CubeMX 代码生成 =====================
# 后端统一走 cubemx_gen.py（CLI + MCP 共用一份逻辑）。用子进程调用而非 import：
# 脚本生成时会打 [INFO]/[OK] 日志，import 会把 stdout 污染成 JSON-RPC 协议通道。
# 脚本 --json 安静模式把日志改走 stderr，stdout 只留一个 JSON 行，这里解析它。


def _parse_cubemx_json(stdout: str) -> dict:
    """解析 cubemx_gen.py --json 的 stdout（最后一行 JSON）。解析失败返回空 dict。"""
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text.splitlines()[-1])
    except ValueError:
        return {}


# 嵌套 python 后端的 spawn 参数：stdin 指向 DEVNULL + CREATE_NO_WINDOW。
# 实测：MCP server（Node 拉起）再 spawn python.exe 时，子进程会继承 claude 的
# stdio 句柄导致启动卡死 60s；加这两个参数后恢复正常。普通 .exe（如
# STM32_Programmer_CLI）不受影响，无需此参数。
_CUBEMX_CREATE_NO_WINDOW = 0x08000000


@mcp.tool()
def cubemx_check() -> dict:
    """检测 STM32CubeMX 是否可用（生成模板代码前的前置检查）。"""
    if not os.path.exists(CUBEMX_GEN):
        return {"found": False, "cubemx_path": None, "builtin_jre": False,
                "error": f"后端脚本不存在: {CUBEMX_GEN}",
                "display_for_user": f"❌ 找不到 cubemx_gen.py: {CUBEMX_GEN}"}
    result = run_cmd([sys.executable, CUBEMX_GEN, "--check", "--json"], timeout=60,
                     stdin_devnull=True, creationflags=_CUBEMX_CREATE_NO_WINDOW)
    if result.error or result.timed_out:
        msg = result.error or "CubeMX 检测超时"
        return {"found": False, "cubemx_path": None, "builtin_jre": False,
                "error": msg, "display_for_user": f"❌ CubeMX 环境检测失败: {msg}"}
    data = _parse_cubemx_json(result.stdout)
    if not data:
        return {"found": False, "cubemx_path": None, "builtin_jre": False,
                "error": f"无法解析检测输出: {result.stdout[:200]}",
                "display_for_user": "❌ CubeMX 检测输出无法解析"}
    data["display_for_user"] = (
        f"✅ STM32CubeMX: {data.get('cubemx_path')}\n"
        f"   内置 JRE: {'有（无需另装 Java）' if data.get('builtin_jre') else '无'}"
        if data.get("found") else
        f"❌ STM32CubeMX 未找到\n{data.get('error', '')}")
    return data


@mcp.tool()
def cubemx_generate(ioc_path: str, out_dir: str = "", in_place: bool = False,
                    timeout: int = 420) -> dict:
    """从 .ioc 用 STM32CubeMX 无头生成完整工程（Core/Drivers/MDK-ARM）。

    生成约 20s~3 分钟（首次含固件包下载），调用会阻塞等待。
    默认输出到 <ioc 同目录>/cubemx_out/，不碰原工程。
    ⚠️ in_place=true 会在 ioc 所在目录内覆盖生成 Core/Drivers（保留 USER CODE 段），
    仅当用户明确要求"重新生成当前工程代码"时才可传 true，其余情况一律用默认安全模式。
    """
    if not os.path.exists(ioc_path):
        return {"success": False, "error": f".ioc 不存在: {ioc_path}",
                "display_for_user": f"❌ .ioc 未找到: {ioc_path}"}
    if not os.path.exists(CUBEMX_GEN):
        return {"success": False, "error": f"后端脚本不存在: {CUBEMX_GEN}",
                "display_for_user": f"❌ 找不到 cubemx_gen.py: {CUBEMX_GEN}"}

    cmd = [sys.executable, CUBEMX_GEN, ioc_path, "--timeout", str(timeout), "--json"]
    if in_place:
        cmd.append("--in-place")
    elif out_dir:
        cmd += ["--out-dir", out_dir]

    result = run_cmd(cmd, timeout=timeout + 60,   # run_cmd 硬超时比生成超时留 60s 余量
                     stdin_devnull=True, creationflags=_CUBEMX_CREATE_NO_WINDOW)
    data = _parse_cubemx_json(result.stdout)
    if not data:
        data = {"success": False,
                "error": result.error or result.stderr.strip() or "生成进程无输出",
                "raw_output": (result.stdout or "")[:800]}

    if data.get("success"):
        display = (f"✅ CubeMX 生成完成（{data.get('elapsed_s')}s）\n"
                   f"📦 MCU: {data.get('mcu')} | 工具链: {data.get('toolchain')}\n"
                   f"📁 输出: {data.get('out_dir')}\n"
                   f"📐 工程: {data.get('uvprojx') or '未找到 .uvprojx，请人工核对'}\n"
                   f"📄 共 {data.get('generated_count')} 个文件")
    else:
        display = (f"❌ CubeMX 生成失败\n"
                   f"{data.get('error') or ''}\n"
                   f"{data.get('raw_output', '')[:400]}")
    data["display_for_user"] = display
    return data


if __name__ == "__main__":
    mcp.run()
