# -*- coding: utf-8 -*-
"""
STM32 Toolkit SessionEnd 会话日志收尾。
仅追加分隔线 --- 与会话结束时间戳，不自动总结内容（自动写内容风险高）。
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

from common import load_event, project_root


def main():
    try:
        ev = load_event()
        root = project_root(ev)
        mem_dir = Path(root) / ".claude" / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        log_path = mem_dir / "session_log.md"
        ts = datetime.datetime.now().isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("---\n")
            f.write("会话结束 " + ts + "\n")
    except Exception:
        pass  # 兜底静默，绝不崩溃


if __name__ == "__main__":
    main()
