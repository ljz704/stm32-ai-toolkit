# -*- coding: utf-8 -*-
"""
STM32 Toolkit PostToolUse 记录编译结果（matcher: mcp__stm32-toolkit__keil_build）。
写 .claude/build_state.json（status + dirty=false），并追加 .claude/memory/session_log.md。
静默执行，不输出 additionalContext，绝不崩溃。
"""

import sys
import os
import json
import datetime
from pathlib import Path

try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from common import load_event, project_root, write_build_state


def parse_tool_response(tool_response):
    """tool_response 可能是 dict 或字符串 JSON，统一转成 dict。"""
    if isinstance(tool_response, dict):
        return tool_response
    if isinstance(tool_response, str):
        try:
            data = json.loads(tool_response)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def count_errors(errors):
    """errors 可能是 list（数量取 len）或 int，兜底返回 0。"""
    if isinstance(errors, int):
        return errors
    if isinstance(errors, (list, tuple)):
        return len(errors)
    return 0


def main():
    try:
        ev = load_event()
        root = project_root(ev)
        resp = parse_tool_response(ev.get("tool_response"))

        success = bool(resp.get("success", False))

        code_size = resp.get("code_size") or {}
        if not isinstance(code_size, dict):
            code_size = {}
        flash = str(code_size.get("flash") or "N/A")
        ram = str(code_size.get("ram") or "N/A")

        n_errors = count_errors(resp.get("errors"))

        ts = datetime.datetime.now().isoformat()
        state = {"status": "success" if success else "failed",
                 "dirty": False,
                 "ts": ts}
        write_build_state(root, state)

        # 追加会话日志（不存在则创建，目录自动 mkdir）
        mem_dir = Path(root) / ".claude" / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        log_path = mem_dir / "session_log.md"
        if success:
            line = "### 编译 {ts} ✅ Flash {flash} RAM {ram}".format(
                ts=ts, flash=flash, ram=ram)
        else:
            line = "### 编译 {ts} ❌ {n} errors".format(ts=ts, n=n_errors)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # 静默，绝不崩溃


if __name__ == "__main__":
    main()
