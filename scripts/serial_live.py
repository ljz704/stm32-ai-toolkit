#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 串口实时监控脚本
========================
独立运行，实时打印串口数据到终端，同时写入日志文件。
可与 MCP Server 的 serial_monitor 配合使用。

用法:
    python serial_live.py COM3 115200
    python serial_live.py --list

功能:
    - 实时显示带时间戳的串口数据
    - 自动保存到 serial_log_YYYYMMDD_HHMMSS.txt
    - 支持 Ctrl+C 优雅退出
    - 自动识别 ST-Link VCP
"""

import sys
import serial
import serial.tools.list_ports
from datetime import datetime
import argparse

def list_ports():
    print("=" * 50)
    print("  可用串口列表")
    print("=" * 50)
    found = False
    for p in serial.tools.list_ports.comports():
        marker = "  ⭐ ST-Link VCP" if "ST-Link" in (p.description or "") else ""
        print(f"  {p.device:<8} {p.description or 'Unknown'}{marker}")
        found = True
    if not found:
        print("  (未找到串口)")
    print()

def monitor(port: str, baudrate: int):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"serial_log_{timestamp}.txt"

    print("=" * 50)
    print(f"  串口监控启动")
    print(f"  端口: {port}")
    print(f"  波特率: {baudrate}")
    print(f"  日志文件: {log_file}")
    print("=" * 50)
    print("  按 Ctrl+C 停止\n")

    try:
        with serial.Serial(port, baudrate, timeout=0.1) as ser, open(log_file, "w", encoding="utf-8") as f:
            line_buffer = ""
            line_count = 0

            while True:
                data = ser.read(2048).decode("utf-8", errors="ignore")
                if data:
                    line_buffer += data
                    while "\n" in line_buffer:
                        line, line_buffer = line_buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                            output = f"[{ts}] {line}"
                            print(output)
                            f.write(output + "\n")
                            f.flush()
                            line_count += 1

                            # 每 100 行提示一次
                            if line_count % 100 == 0:
                                print(f"  ... 已记录 {line_count} 行 (Ctrl+C 停止)")

            # 剩余数据
            if line_buffer.strip():
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                output = f"[{ts}] {line_buffer.strip()}"
                print(output)
                f.write(output + "\n")

    except KeyboardInterrupt:
        print(f"\n\n{'=' * 50}")
        print(f"  监控已停止")
        print(f"  共记录 {line_count} 行")
        print(f"  日志保存至: {log_file}")
        print(f"{'=' * 50}")
    except serial.SerialException as e:
        print(f"\n❌ 串口错误: {e}")
        print("   请检查:")
        print("   1. 串口是否被其他程序占用（如 Keil、串口助手）")
        print("   2. 波特率是否正确")
        print("   3. 接线是否松动")
    except Exception as e:
        print(f"\n❌ 错误: {e}")

def main():
    parser = argparse.ArgumentParser(description="STM32 串口实时监控")
    parser.add_argument("port", nargs="?", help="串口号，如 COM3")
    parser.add_argument("baudrate", nargs="?", type=int, default=115200, help="波特率，默认 115200")
    parser.add_argument("-l", "--list", action="store_true", help="列出可用串口")
    args = parser.parse_args()

    if args.list or not args.port:
        list_ports()
        if not args.port:
            print("用法: python serial_live.py <COM口> [波特率]")
            print("示例: python serial_live.py COM3 115200")
        sys.exit(0)

    monitor(args.port, args.baudrate)

if __name__ == "__main__":
    main()
