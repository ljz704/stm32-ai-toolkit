# STM32 AI 开发工作流 —— DSH（DeepSeek Harness）使用说明

> 本工作流原为 Claude Code 设计（见 [USAGE.md](USAGE.md)），现已适配 DSH。
> 本文档说明如何在 DeepSeek Harness 中使用本工具包的全部能力。

## 一、DSH 模式安装（一次性）

```bash
python install.py --dsh    # 装到 ~/.dsh：AGENTS.md + 6 skills + 魔改插件 + MCP 注册
```

> ⚠️ **不要加 `--no-deps`**：它会跳过 fastmcp/pyserial 安装，导致 MCP 工具不可用。
> 只有确认依赖已装好（如换机恢复时）才用 `--no-deps`。

安装内容（全部落在 `~/.dsh/`，不碰 `~/.claude`）：

| 组件 | 位置 | DSH 中的作用 |
|------|------|--------------|
| 全局指令 | `~/.dsh/AGENTS.md` | DSH 原生自动加载（新会话生效） |
| Skills（6 个） | `~/.dsh/skills/` | DSH 官方 skill 系统 + 设置 → Skill 管理 |
| 魔改插件 | `~/.dsh/profiles/node_modules/@anoslide/` | MCP 动态挂载 / 设置界面 / 文件树（**已装则跳过**，未装自动从工具包 `dsh_plugins/` 安装） |
| MCP | `~/.dsh/mcp-servers.json` | 设置 → MCP 管理，动态挂载即时生效 |

卸载：`python uninstall.py --dsh`（配置移到备份，MCP 条目外科手术式移除——只删 stm32-toolkit，保留你添加的其他 MCP；`--purge` 彻底清理）。

## 二、DSH 与 Claude Code 的机制对应

| 原 Claude Code 机制 | DSH 对应 | 说明 |
|---------------------|----------|------|
| `~/.claude/CLAUDE.md` 全局规范 | `~/.dsh/AGENTS.md` | DSH 原生用户全局指令文件 |
| 项目根 `CLAUDE.md` | **原样兼容** | DSH 原生支持 AGENTS.md / CLAUDE.md 两种文件名 |
| `@.claude/memory/*.md` 导入语法 | `.dsh/memory/*.md` 显式引用 | DSH 不解析 `@` 语法，改为 CLAUDE.md 中显式列出 |
| `.claude/settings.json` hooks | **无 hooks** | DSH 无 PreToolUse/PostToolUse 机制，编译闸门靠自觉（铁律） |
| `.claude/commands/*.md` 斜杠命令 | **转为 skill** | DSH commands 是代码注册制；6 个命令已转为 stm32-* skill |
| `claude mcp add` | `~/.dsh/mcp-servers.json` | 魔改插件 dsh-host-files 动态挂载，设置界面可见 |
| 4 个 skill | 6 个 skill | 新增 stm32-new-project / stm32-known-issues |

## 三、在 DSH 中的日常使用

### 新建工程
直接说："新建一个 STM32 工程，型号 STM32F103C8T6，名字 xxx"。
DSH 会自动触发 `stm32-new-project` skill → 解析型号 → CubeMX 无头生成 → 补装 AI 层（DSH 轨）。

**生成目标默认 DSH 轨**：`stm32-new-project` skill 调用脚本时自带 `--env dsh`（或设环境变量 `STM32_TOOLKIT_ENV=dsh`），产物是 `.dsh/memory/` + 显式路径 CLAUDE.md，无 hooks。
手动执行时同理：

```bash
python new_project.py --name xxx --mcu STM32F103C8T6 --env dsh --yes
# 或设一次环境变量，之后不用带参：
set STM32_TOOLKIT_ENV=dsh
```

**解析顺序**：`--env` 显式 > 环境变量 `STM32_TOOLKIT_ENV` > 默认 `claude`。想给该目录同时配 Claude 轨（hooks 闸门）时：`--env claude`（或 `--hooks` 在 dsh 轨上强制生成 `.claude/settings.json`）。

### 编译 / 烧录 / 串口
直接说："编译当前工程" / "烧录到板子" / "打开串口 COM3"。
DSH 会自动匹配 skill（stm32-build-flash-debug）并调用 `mcp__stm32-toolkit__*` 工具。

### 代码审查 / 调试分析 / 外设配置
说"审查一下代码" / "程序跑飞了帮我分析" / "帮我配一个 ADC"，
对应触发 stm32-code-review / stm32-debug-analyze / stm32-peripheral-config。

### 记录踩坑
说"记一条踩坑：xxx"，触发 stm32-known-issues，写入 `.dsh/memory/known_issues.md`。

### 工程内记忆文件（DSH 自动加载）
```
工程根/
├── CLAUDE.md              ← DSH 原生自动加载（含记忆文件显式引用）
├── hardware.yaml
└── .dsh/memory/
    ├── architecture.md    ← 架构决策
    ├── pin_usage.md       ← 引脚占用表（生成外设代码前必须读）
    ├── known_issues.md    ← 踩坑记录（写外设代码前必须读）
    └── session_log.md     ← 会话结论
```

## 四、MCP 工具（15 个，模型可直接调用）

`mcp__stm32-toolkit__keil_build` / `keil_clean` / `stlink_flash` / `stlink_erase` /
`probe_info` / `serial_list_ports` / `serial_send` / `serial_read` /
`serial_monitor_start/read/stop` / `parse_build_log` / `find_build_output` /
`cubemx_check` / `cubemx_generate`

在 DSH **设置 → MCP 管理** 中可开关/删除；**设置 → Skill 管理** 中可开关/删除 6 个 skill。

## 五、注意事项

1. **新会话才加载新全局指令**：修改 `~/.dsh/AGENTS.md` 后，新会话生效。
2. **无 hooks 闸门**：DSH 没有编译强制闸门，改完代码要主动编译验证（工作流铁律第 1 条）。
3. **记忆文件路径**：新工程用 `.dsh/memory/`；旧工程 `.claude/memory/` 同样兼容读取。
4. **MCP 即时生效**：`mcp-servers.json` 由魔改插件动态挂载，无需重启 DSH。
5. **已生成工程加外设**：日常小改动（加外设/改参数）**优先手写 USER CODE 代码**（CubeMX 重新生成不覆盖 `USER CODE BEGIN/END` 区），几分钟完成；大改（时钟树/引脚映射）才走"改 .ioc → cubemx_out 合并"流程（经验见工程 `.dsh/memory/known_issues.md`）。
6. **已有工程补装 AI 层（方案 B）**：`new_project.py --dir <工程> --existing --mcu <型号> --env dsh --yes --analyze`
   - **CubeMX/HAL 工程**（有 Core/）：`--analyze` 静态提取硬件配置（MCU/时钟/GPIO/外设），生成 `hardware.yaml.draft` + `pin_usage.md.draft` + `ai_review_notes.md`；AI 复核（读源码 + 双子代理交叉验证）后定稿。草稿不覆盖已有人工内容。
   - **脚本跑不通一律 AI 直读**：SPL/非 CubeMX 结构**不跑脚本**；HAL 工程脚本一旦跑不通（缺文件/异常/超时/退出码非 0/无草稿产物），`--analyze` **自动降级为 AI 直读**并打印原因，不硬跑、不静默跳过。
   - **AI 直读流程**（SPL 或降级时）：AI 直接完整读源码（main.c + 外设 .c + system 时钟 + uvprojx）→ 双子代理交叉验证 → 定稿。SPL 源码多为 GBK 编码，编辑须保持 GBK。

## 六、待完善（TODO）

- 常用外设（ADC/TIM/USART/SPI/I2C）HAL 初始化代码模板进 `stm32-peripheral-config` skill，直接插 USER CODE 区
- "外设 → .ioc 回填 → 重新生成 → 自动合并"脚本化，让大改也一键完成
