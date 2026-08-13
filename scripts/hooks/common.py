# -*- coding: utf-8 -*-
"""
STM32 Toolkit Claude Code hooks —— 共用工具。
提供事件读取 / JSON 输出 / 构建状态读写，全部容错，绝不抛异常。
"""

import sys
import os
import json
import datetime
from pathlib import Path

# stdin/stdout 固定 UTF-8：Claude Code 以 UTF-8 写入事件 JSON，
# 而 Windows 上 Python stdin 默认 GBK，不修正会误解码中文 prompt / reason。
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_event():
    """从 stdin 读取 hook 事件 JSON，读不到或解析失败返回 {}。"""
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        ev = json.loads(data)
        return ev if isinstance(ev, dict) else {}
    except Exception:
        return {}


def output_decision(**kwargs):
    """输出 PreToolUse 决策 JSON，如 {"decision":"block","reason":"..."}。"""
    payload = dict(kwargs)
    if "decision" not in payload:
        payload["decision"] = "allow"
    try:
        print(json.dumps(payload, ensure_ascii=False))
    except Exception:
        print('{"decision":"allow"}')


def output_context(text):
    """输出 PostToolUse / UserPromptSubmit 的 additionalContext 注入 JSON。"""
    try:
        print(json.dumps({"hookSpecificOutput": {"additionalContext": text}},
                         ensure_ascii=False))
    except Exception:
        pass


def project_root(event):
    """项目根目录：优先用事件里的 cwd，否则用当前工作目录。"""
    ev = event or {}
    cwd = ev.get("cwd")
    if cwd:
        return cwd
    return os.getcwd()


def build_state_path(root):
    """返回 .claude/build_state.json 的 Path。"""
    return Path(root) / ".claude" / "build_state.json"


def read_build_state(root):
    """读取 build_state.json，任何失败返回 {}。"""
    try:
        p = build_state_path(root)
        if not p.exists():
            return {}
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_build_state(root, data):
    """写 build_state.json（自动建目录），任何失败静默忽略。"""
    try:
        p = build_state_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    # 自测：读一个事件并原样打印决策 allow
    ev = load_event()
    output_decision(decision="allow")
