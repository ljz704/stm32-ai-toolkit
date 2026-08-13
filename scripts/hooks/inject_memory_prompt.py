# -*- coding: utf-8 -*-
"""
STM32 Toolkit UserPromptSubmit 记忆注入。
用户 prompt 命中关键词时，注入提醒：先读 pin_usage.md / known_issues.md。
未命中则 stdout 为空（不输出任何内容）。
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

KEYWORDS = [
    "初始化", "配置", "改代码", "ADC", "TIM", "SPI", "I2C",
    "USART", "引脚", "烧录", "编译", "报错", "串口", "HRTIM", "新建",
]


def main():
    try:
        ev = load_event()
        prompt = ev.get("prompt") or ""
        if not prompt:
            return
        prompt_str = str(prompt)
        if any(k in prompt_str for k in KEYWORDS):
            output_context(
                "开始生成外设代码前，请先读 .claude/memory/pin_usage.md 确认引脚未占用，"
                "读 .claude/memory/known_issues.md 检查历史教训。"
            )
        # 未命中：什么都不输出
    except Exception:
        pass  # 兜底静默，绝不崩溃


if __name__ == "__main__":
    main()
