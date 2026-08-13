# -*- coding: utf-8 -*-
"""
STM32 Toolkit PostToolUse 串口原始数据强制展示（matcher: mcp__stm32-toolkit__serial_*）。
注入上下文：回复必须先以 text 代码块完整展示原始数据，再分析。
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

from common import load_event, output_context


def main():
    try:
        load_event()
        output_context("串口数据已获取，回复必须先以 text 代码块完整展示原始数据，再逐行分析，严禁只给结论不展示原始数据。")
    except Exception:
        pass  # 兜底静默，绝不崩溃


if __name__ == "__main__":
    main()
