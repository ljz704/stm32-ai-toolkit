# -*- coding: utf-8 -*-
"""
STM32 Toolkit PreToolUse 硬约束闸门（matcher: Edit|Write）。
仅当目标为 .c/.h/.s 源码文件，且上次编译成功但存在未验证改动时 block。
其余任何情况（编译失败中、无状态、非源码、异常）一律 allow，绝不自锁。
"""

import sys
import os
import json
import datetime

try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from common import load_event, output_decision, project_root, read_build_state

SOURCE_EXTS = (".c", ".h", ".s")

# 兜底：任何异常都输出 allow，绝不 block
def _safe_allow():
    print('{"decision":"allow"}')


def main():
    try:
        ev = load_event()
        tool_input = ev.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        file_path = tool_input.get("file_path") or ""
        if not file_path:
            output_decision(decision="allow")
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SOURCE_EXTS:
            output_decision(decision="allow")
            return

        root = project_root(ev)
        state = read_build_state(root)
        # 上次编译成功(status==success)但有未验证改动(dirty==true)才 block
        if state.get("dirty") is True and state.get("status") == "success":
            output_decision(
                decision="block",
                reason="有未验证的源码改动，请先 /build 或让 AI 调用 keil_build 编译通过再继续编辑。",
            )
        else:
            output_decision(decision="allow")
    except Exception:
        _safe_allow()


if __name__ == "__main__":
    main()
