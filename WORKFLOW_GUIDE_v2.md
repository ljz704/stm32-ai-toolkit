# STM32 AI 开发工作流 v3 —— 完整优化方案

## 一、痛点 → 解决方案对照表

| 痛点 | 解决方案 | 文件/工具 |
|------|----------|-----------|
| AI "失忆" | `.claude/memory/` 记忆体系 + CLAUDE.md 中 `@.claude/memory/*.md` 自动加载 | memory/*.md, CLAUDE.md |
| 生成代码 → 编译报错 → 反复拉扯 | 强制编译验证：hooks 闸门 + 提醒，编译成功后才放行 | hooks/check_build_gate.py, remind_compile.py, skills/stm32-build-flash-debug/ |
| 硬件信息同步困难 | `hardware.yaml` 结构化硬件信息 | hardware.yaml |
| 修改需求时"改坏"已有代码 | Git 检查点 + "只改这里"约束 | skills/stm32-build-flash-debug/ |
| 调试时缺少实时数据 | `serial_live.py` 独立监控 + MCP `serial_monitor_*` | scripts/serial_live.py, mcp/stm32_mcp_server.py |
| 同一个错误反复犯 | `known_issues.md` 教训沉淀 + 记忆自动注入 | memory/known_issues.md, hooks/inject_memory_prompt.py |
| 多项目切换上下文混乱 | 每工程独立 `.claude/`，new_project.py 脚手架按模板生成 | new_project.py, templates/project/ |
| AI 不展示原始串口数据 | 原始数据展示规范 + enforce_raw_data hook | hooks/enforce_raw_data.py, skills/stm32-debug-analyze/ |

## 二、项目目录结构（优化后）

```
your_project/
├── .claude/
│   ├── settings.json             # hooks 配置（编译闸门/记忆注入/会话日志）
│   ├── memory/
│   │   ├── architecture.md      # 架构决策
│   │   ├── pin_usage.md         # 引脚占用表（实时更新）
│   │   ├── known_issues.md      # 踩坑记录（AI 必须读取）
│   │   └── session_log.md       # 会话关键结论
│   └── build_state.json         # 编译状态（hooks 自动读写）
├── hardware.yaml                # 结构化硬件信息
├── CLAUDE.md                    # 项目级差异 + @.claude/memory/*.md 自动加载
├── src/
├── inc/
└── MDK-ARM/
```

## 三、使用流程

### 新会话启动时
1. AI 读取 `CLAUDE.md`（含 `@.claude/memory/*.md` 导入）
2. 记忆文件自动注入上下文（hooks 还会按关键词注入 pin_usage / known_issues）
3. AI 读取 `hardware.yaml` 获取硬件参数
4. AI 读取 `known_issues.md` 避免重复踩坑

### 生成代码时
1. AI 检查 `pin_usage.md`，避免分配已占用引脚
2. AI 生成代码后，**自动调用 `keil_build` 验证**
3. 0 Error 后才允许继续下一步

### 调试时
1. **终端 1**：`python serial_live.py COM3 115200`（你实时看）
2. **终端 2**：Claude Code + MCP `serial_monitor_start/read`（AI 分析）
3. AI **先展示原始数据**，再给出分析结论

### 修改需求时
1. AI 告知你将修改哪些文件和函数
2. AI 只改相关代码，**严禁碰不相关配置**
3. 修改后 Git commit 锁定检查点

## 四、关键约束（AI 必须遵守）

### 约束 1：强制编译验证
> 每生成或修改超过 5 行代码后，必须调用 `keil_build`，0 Error 后才能继续。

### 约束 2：原始数据展示
> 调用任何串口工具后，必须先用 ```text 代码块展示完整原始数据，再分析。

### 约束 3：引脚冲突检查
> 生成外设配置前，必须读取 `pin_usage.md`，确认引脚未被占用。

### 约束 4：历史教训检查
> 生成 HRTIM / RN8209 / ADC 等代码前，必须读取 `known_issues.md`。

### 约束 5：Git 检查点
> 每完成一个独立功能模块，必须 `git add . && git commit`。

## 五、文件清单

| 文件 | 作用 | 放置位置 |
|------|------|----------|
| `mcp/stm32_mcp_server.py` | MCP Server（14 个工具：编译/烧录/串口/日志） | 仓库 `mcp/` |
| `scripts/serial_live.py` | 独立串口实时监控脚本 | 仓库 `scripts/` |
| `skills/stm32-build-flash-debug/` | 编译烧录 Skill（强制编译 + 数据展示） | 仓库 `skills/` |
| `skills/stm32-debug-analyze/` | 调试分析 Skill（快照模板 + 记忆读取） | 仓库 `skills/` |
| `skills/stm32-code-review/` | 代码审查 Skill | 仓库 `skills/` |
| `skills/stm32-peripheral-config/` | 外设配置 Skill | 仓库 `skills/` |
| `hardware.yaml` | 结构化硬件信息 | 项目根目录 |
| `CLAUDE.md` | 项目级差异 + 记忆导入（`@.claude/memory/*.md`） | 项目根目录 |
| `.claude/settings.json` | hooks 配置（编译闸门/记忆注入/会话日志） | 项目 `.claude/` |
| `scripts/hooks/*.py` | hooks 实现（check_build_gate / record_build / inject_memory_prompt 等） | 仓库 `scripts/hooks/` |
| `architecture.md` | 架构决策 | `.claude/memory/` |
| `pin_usage.md` | 引脚占用表 | `.claude/memory/` |
| `known_issues.md` | 踩坑记录 | `.claude/memory/` |
| `session_log.md` | 会话日志 | `.claude/memory/` |
