# -*- coding: utf-8 -*-
"""
STM32 Toolkit PostToolUse 编译提醒（matcher: Edit|Write）。
目标为 .c/.h/.s 时注入上下文提醒先编译验证。
同一文件 5 分钟内不重复提醒（.claude/remind_state.json 记录）。异常兜底静默 allow。
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

from common import load_event, output_context, project_root, read_build_state, write_build_state

SOURCE_EXTS = (".c", ".h", ".s")
REMIND_WINDOW_SECONDS = 5 * 60  # 5 分钟


def main():
    try:
        ev = load_event()
        tool_input = ev.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {}
        file_path = tool_input.get("file_path") or ""
        if not file_path:
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SOURCE_EXTS:
            return

        root = project_root(ev)

        # 标记"有未验证改动"：让 PreToolUse 闸门(check_build_gate)能生效。
        # 放在去重之前，保证 5 分钟窗口内的重复编辑也持续保持 dirty=True。
        try:
            bs = read_build_state(root)
            if not isinstance(bs, dict):
                bs = {}
            bs["dirty"] = True
            write_build_state(root, bs)
        except Exception:
            pass  # 写失败不影响提醒本身

        state_path = Path(root) / ".claude" / "remind_state.json"
        now = datetime.datetime.now()

        # 读取上次提醒记录
        state = {}
        try:
            if state_path.exists():
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
        except Exception:
            state = {}
        if not isinstance(state, dict):
            state = {}

        # 去重：同一文件 5 分钟内不再提醒
        last = state.get(file_path)
        if last:
            try:
                last_t = datetime.datetime.fromisoformat(str(last))
                if (now - last_t).total_seconds() < REMIND_WINDOW_SECONDS:
                    return
            except Exception:
                pass

        # 更新提醒时间
        state[file_path] = now.isoformat()
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        output_context("刚修改了源码，按铁律应先编译验证（keil_build 或 /build），0 Error 后再继续。")
    except Exception:
        pass  # 兜底静默（等价 allow）


if __name__ == "__main__":
    main()
