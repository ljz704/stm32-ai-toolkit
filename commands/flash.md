---
description: 烧录编译产物到 STM32
---

将编译产物烧录到 STM32：
1. 调用 MCP 工具 `find_build_output` 查找当前工程最新的 `.hex` / `.bin` 烧录文件；如果找不到或有多份，提示用户选择或重新编译。
2. 调用 `probe_info` 确认 ST-Link 是否连接、目标芯片型号是否正确。
3. 调用 `stlink_flash` 执行烧录（$ARGUMENTS 可包含烧录地址，默认 `0x08000000`）。
4. 烧录完成后，必须展示返回结果中 `display_for_user` 字段的完整内容。
5. 如果烧录失败，按 `stm32-build-flash-debug` skill 的「烧录失败处理」排查清单定位问题（ST-Link 驱动、接线、BOOT0、供电、读保护、Keil 占用）。
6. 最后给出烧录状态（✅/❌）与验证建议（观察板载现象或打开串口）。
