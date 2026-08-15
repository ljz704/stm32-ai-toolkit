# 换电脑恢复指令（存到你的笔记里）

当你在新电脑上需要对 Claude 说：

> "帮我恢复 STM32 开发环境"

AI 会执行以下步骤：

1. 询问工具包位置（如 D:\stm32-ai-toolkit）
2. 检查 Python 3.8+ 是否安装
3. 运行 install.py 完成配置
4. 验证 claude mcp list 输出
5. 测试编译一个示例工程确认通路

如果 AI 没有自动执行，你可以给它这个指令：

```
我的 STM32 AI 开发工具包在 <路径>。
请帮我：
1. 检查 Python 和 pip 是否可用
2. 安装 fastmcp 和 pyserial
3. 运行 <路径>/install.py
4. 验证 ~/.claude/CLAUDE.md、skills（6 个）、commands（6 个）是否就位
5. 运行 claude mcp list 确认 stm32-toolkit 已注册
6. 如果有错误，帮我排查
```

## DSH（DeepSeek Harness）恢复

用 DSH 时，在新电脑上直接说：

> "帮我恢复 STM32 开发环境（DSH），工具包在 <路径>"

或者手动执行：

```
我的 STM32 AI 开发工具包在 <路径>，我用的是 DeepSeek Harness (DSH)。
请帮我：
1. 检查 Python 和 pip 是否可用
2. 安装 fastmcp 和 pyserial
3. 运行 <路径>/install.py --dsh
4. 验证 ~/.dsh/AGENTS.md、skills（6 个）是否就位
5. 确认 ~/.dsh/mcp-servers.json 含 stm32-toolkit（或 DSH 设置 → MCP 管理可见）
6. 如果有错误，帮我排查
```

> DSH 与 Claude Code 配置互不干扰（~/.dsh vs ~/.claude），可同时安装两套。
