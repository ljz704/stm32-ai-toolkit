---
description: 编译当前 Keil 工程并展示结果
---

定位当前目录（含子目录）下的 `.uvprojx` 工程文件：
1. 如果找到多个 `.uvprojx`，列出全部并让用户选择要编译的工程；如果只有一个，直接使用。
2. 确认工程路径后，调用 MCP 工具 `keil_build` 执行编译（$ARGUMENTS 包含 `rebuild` 时传 `rebuild=True` 做 clean build）。
3. 编译完成后，必须展示返回结果中 `display_for_user` 字段的完整内容，不得省略或只给结论。
4. 如果结果中有 **Error**，按 `stm32-build-flash-debug` skill 的「编译错误处理」子流程分类定位并修复（特征以 ARMCC v5.06 输出为准）；修复后重新编译，直到通过。
5. 最后用 ✅/❌ 标记编译状态，并给出代码大小与下一步建议。
