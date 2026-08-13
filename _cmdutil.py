# -*- coding: utf-8 -*-
"""
_cmdutil.py —— STM32 AI 工具包共享工具模块
=============================================
统一解决三类 Windows 环境问题：
  1. 控制台编码：GBK(cp936) 控制台打印 emoji/中文抛 UnicodeEncodeError
  2. 子进程编码：外部命令输出 UTF-8/GBK 混用导致解码失败、stdout 变 None
  3. 超时与异常：subprocess 卡死冻结会话 / 命令不存在裸抛 FileNotFoundError

供 install.py / backup.py / new_project.py / mcp/*.py / scripts/hooks/*.py 复用。
"""

import locale
import os
import shutil
import subprocess
import sys

DEFAULT_TIMEOUT = 300  # 秒；Keil 整工程编译给 5 分钟，烧录/查询在调用处覆盖


def _resolve_windows_cmd(args):
    """Windows 下 subprocess 无法直接启动 .cmd/.bat shim（CreateProcess 只认 .exe）。

    npm 全局命令（如 claude.CMD）shutil.which 能找到，但 run_cmd 会抛
    FileNotFoundError。这里把裸命令名解析后，若是 .cmd/.bat 就改用 cmd /c 启动。
    非 Windows 或已含路径的命令原样返回。
    """
    if os.name != "nt" or not args:
        return args
    first = args[0]
    if os.path.dirname(first):  # 已含目录/路径，交还调用方处理
        return args
    found = shutil.which(first)
    if found and found.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c"] + list(args)
    return args


def fix_console_encoding():
    """修复 Windows GBK 控制台打印 emoji/中文时的 UnicodeEncodeError。

    仅用于 CLI 脚本（install/backup/new_project/register_mcp/serial_live）。
    MCP server 不要调用本函数——其 stdout 是 JSON-RPC 协议通道，
    不要在 server 里 print 任何非协议内容。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def smart_decode(raw: bytes) -> str:
    """先按 UTF-8 解码，失败回退到系统编码（中文系统为 gb18030，GBK 超集）。

    Keil 编译日志在中文系统下常为 GBK，utf-8+ignore 硬解会把中文变成乱码
    （ASCII 关键字幸存，但错误行内容被污染）。本函数保证两套编码都不乱码。
    """
    if not raw:
        return ""
    encodings = ["utf-8", locale.getpreferredencoding(False) or "gb18030", "gb18030"]
    for enc in encodings:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


class RunResult:
    """统一外部命令结果，永不抛异常。"""

    __slots__ = ("returncode", "stdout", "stderr", "timed_out", "error")

    def __init__(self, returncode, stdout, stderr, timed_out=False, error=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.error = error

    @property
    def ok(self) -> bool:
        return (not self.error) and (not self.timed_out) and self.returncode == 0

    @property
    def combined(self) -> str:
        return (self.stdout or "") + (self.stderr or "")


def run_cmd(args, timeout=DEFAULT_TIMEOUT, env=None, stdin_devnull=False,
            creationflags=0) -> RunResult:
    """统一执行外部命令。

    - 超时：命令卡死返回 timed_out=True，绝不冻结调用方
    - 编码：输出按 UTF-8 → 系统编码 回退解码，中文不乱码
    - 异常：FileNotFoundError（命令不存在）转成 error 字段
    - Windows shim：.cmd/.bat 命令自动用 cmd /c 启动，避免 FileNotFoundError
    - stdin_devnull=True：子进程 stdin 指向 DEVNULL（MCP server 场景下，
      避免子进程继承 JSON-RPC 管道句柄后卡死；cubemx_gen 后端调用使用）
    - creationflags：透传给 subprocess（如 CREATE_NO_WINDOW，防止弹控制台窗）
    """
    args = _resolve_windows_cmd(args)
    kw = {}
    if stdin_devnull:
        kw["stdin"] = subprocess.DEVNULL
    if creationflags:
        kw["creationflags"] = creationflags
    try:
        r = subprocess.run(args, capture_output=True, text=False,
                           timeout=timeout, env=env, **kw)
        return RunResult(r.returncode, smart_decode(r.stdout), smart_decode(r.stderr))
    except FileNotFoundError as e:
        return RunResult(-1, "",
                         f"命令不存在: {args[0]} ({getattr(e, 'filename', '')})",
                         error=f"FileNotFoundError: {args[0]}")
    except subprocess.TimeoutExpired as e:
        out = smart_decode(e.stdout) if e.stdout else ""
        err = smart_decode(e.stderr) if e.stderr else ""
        err += f"\n[超时] 命令超过 {timeout}s 未返回，已终止"
        return RunResult(-1, out, err, timed_out=True)
