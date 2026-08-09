# STM32 AI 开发工作流 v2.0 —— 完整优化方案

## 一、痛点 → 解决方案对照表

| 痛点 | 解决方案 | 文件/工具 |
|------|----------|-----------|
| AI "失忆" | `.claude/memory/` 记忆体系 + `project.json` 自动加载 | memory/*.md, project.json |
| 生成代码 → 编译报错 → 反复拉扯 | 强制编译验证：每改 5 行代码后自动 `keil_build` | skill_build_flash_debug_v2.md |
| 硬件信息同步困难 | `hardware.yaml` 结构化硬件信息 | hardware.yaml |
| 修改需求时"改坏"已有代码 | Git 检查点 + "只改这里"约束 | skill_build_flash_debug_v2.md |
| 调试时缺少实时数据 | `serial_live.py` 独立监控 + MCP `serial_monitor_*` | serial_live.py, mcp_server_v2.py |
| 同一个错误反复犯 | `known_issues.md` 教训沉淀 + Skill 强制读取 | memory/known_issues.md |
| 多项目切换上下文混乱 | `project.json` 项目隔离配置 | project.json |
| AI 不展示原始串口数据 | `display_for_user` 字段 + Skill 强制展示规范 | mcp_server_v2.py, skill_build_flash_debug_v2.md |

## 二、项目目录结构（优化后）

```
your_project/
├── .claude/
│   ├── memory/
│   │   ├── architecture.md      # 架构决策
│   │   ├── pin_usage.md         # 引脚占用表（实时更新）
│   │   ├── known_issues.md      # 踩坑记录（AI 必须读取）
│   │   └── session_log.md       # 会话关键结论
│   └── project.json             # 项目配置（AI 自动加载）
├── hardware.yaml                # 结构化硬件信息
├── CLAUDE.md                    # 项目级差异（极简）
├── src/
├── inc/
└── MDK-ARM/
```

## 三、使用流程

### 新会话启动时
1. AI 读取 `.claude/project.json`
2. AI 自动加载 `memory_files` 列表中的记忆文件
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
| `stm32_mcp_server.py` | MCP Server v2.0（含 serial_monitor） | 仓库 `mcp/` 或全局 |
| `serial_live.py` | 独立串口实时监控脚本 | 仓库 `scripts/` |
| `skill_build_flash_debug_v2.md` | 编译烧录 Skill（强制编译 + 数据展示） | `~/.claude/skills/` |
| `skill_debug_analyze_v2.md` | 调试分析 Skill（快照模板 + 记忆读取） | `~/.claude/skills/` |
| `hardware.yaml` | 结构化硬件信息 | 项目根目录 |
| `project.json` | 项目配置（AI 自动加载） | `.claude/` |
| `architecture.md` | 架构决策 | `.claude/memory/` |
| `pin_usage.md` | 引脚占用表 | `.claude/memory/` |
| `known_issues.md` | 踩坑记录 | `.claude/memory/` |
| `session_log.md` | 会话日志 | `.claude/memory/` |
