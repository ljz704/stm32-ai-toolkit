# STM32 AI 开发工作流 —— 使用说明（Claude Code 版）

> 配套：安装/恢复看 [README.md](README.md)，设计说明看 [WORKFLOW_GUIDE_v2.md](WORKFLOW_GUIDE_v2.md)。
> **使用 DeepSeek Harness (DSH)？** 请看 [USAGE_DSH.md](USAGE_DSH.md)（`python install.py --dsh` 一键适配）。

## 一、安装 / 恢复

```bash
python install.py                 # 完整安装：全局 CLAUDE.md + Skills + Commands + MCP + 工具链检查
python install.py --no-mcp        # 跳过 MCP 注册
python install.py --no-deps       # 跳过 pip 依赖（fastmcp/pyserial）
python install.py --project <已有Keil工程路径>   # 只给已有工程补装 AI 辅助层
python install.py --yes           # 非交互（双击运行时默认无交互）
```

安装后验证：

```bash
claude mcp list     # 应看到 stm32-toolkit: stdio — Connected
ls %USERPROFILE%\.claude\skills\     # 4 个 skill
ls %USERPROFILE%\.claude\commands\   # 6 个命令
```

> MCP 注册时工具链路径用 `-e KEIL_PATH=...` 烤进配置，server 运行时能读到。若 Keil/CubeProgrammer 装在非默认位置，先设环境变量 `KEIL_PATH` / `STM32_PROGRAMMER` 再安装。

## 二、在工程里怎么用

### 1. 新建工程（CubeMX 优先，全家族统一）

```bash
# 默认路径：任意型号 → make_ioc(型号→最小.ioc) → CubeMX 无头生成完整 HAL 工程 → 补装 AI 层
python new_project.py --name meter --mcu STM32F103CBT6 --yes
python new_project.py --name meter --mcu STM32G431CBT6 --yes      # 非 SPL 家族同样一条命令
python new_project.py --name meter --mcu STM32F030C8T6 --hse-mhz 16 --yes   # 板载晶振非 8MHz 时指定（仅对有官方示例的家族生效）
# SPL 旧路径（仅 F0/F1/F2/F3/F4/L1 有模板）：
python new_project.py --name meter --mcu STM32F103CBT6 --template f1xx_general --yes
# 只建 config-only 骨架（不生成代码，只装 AI 层）：
python new_project.py --name meter --mcu STM32G431CBT6 --no-cubemx --yes
# 对已有 Keil 工程只补装 AI 层：
python new_project.py --dir <已有工程> --existing --yes
# 只解析型号、预览规格（不建工程，/newproject 对话里用于确认）：
python new_project.py --query-mcu STM32G431CBT6 --json
```

**AI 环境双轨（`--env`，可选）**：同一工具流可给 Claude Code 或 DSH 生成对应工程，互不干扰：

```bash
python new_project.py --name meter --mcu STM32F103CBT6 --env claude --yes   # Claude 轨：.claude/memory + hooks 默认生成
python new_project.py --name meter --mcu STM32F103CBT6 --env dsh --yes      # DSH 轨：.dsh/memory + 无 hooks
STM32_TOOLKIT_ENV=dsh python new_project.py --name meter --mcu STM32F103CBT6 --yes   # 也可用环境变量，省得每次带参
```

- **解析顺序**：`--env` 显式 > 环境变量 `STM32_TOOLKIT_ENV`（值 `dsh`）> 默认 `claude`。
- **Claude 轨**（默认）：记忆文件落 `.claude/memory/`，CLAUDE.md 用 `@.claude/memory/*.md` 自动导入；`.claude/settings.json`（hooks 强制工作流）**默认生成**，可用 `--no-hooks` 关掉。
- **DSH 轨**：记忆文件落 `.dsh/memory/`，CLAUDE.md 用显式路径引用；**默认不生成 hooks**（DSH 无 PreToolUse/PostToolUse 机制），`--hooks` 可强制生成（供该目录同时用 Claude 时使用）。
- `--hooks` / `--no-hooks` 显式参数**始终优先**于 `--env` 的默认值。
- 同一目录内同时存在两轨记忆文件时各自独立维护，互不覆盖。

**CubeMX 优先（默认）**：不传 `--template` 时，任何型号都自动执行——
0. **用户模板库（最高优先级）**：`templates/ioc_templates/<家族>/<型号>/<型号>.ioc`
   （如 `F1/STM32F103C8T6/STM32F103C8T6.ioc`）是你用 CubeMX GUI 手配的金标准模板，
   **精确型号命中 → 整文件复用**（时钟/引脚/外设按模板原样，不再拼最小骨架）；
   未命中才进下面的官方示例/内置兜底。型号解析已容错 `TR` 订货后缀
   （`STM32F103C8T6TR` 按 `STM32F103C8T6` 解析，带 TR 的订货号同样命中模板）；
1. `make_ioc.py`：型号 → `.ioc`（用户模板未命中时，RCC 时钟块取自已装固件包的官方示例，老家族 F0/F1/L1 用内置模板；`--hse-mhz` 指定板载晶振，默认 8MHz——仅对有官方示例的家族生效，F1/F0/L1 内置模板走 HSI 时钟、`--hse-mhz` 非 8 时告警提示在 CubeMX GUI 配晶振）；
2. `cubemx_gen.py` 无头生成完整 HAL 工程（`Core/` `Drivers/` `MDK-ARM/<名>.uvprojx`），直接落进目标目录；
3. 自动补装 AI 辅助层（CLAUDE.md / hardware.yaml / .claude/）。

新增模板：用 CubeMX GUI 打开 → 配好时钟/引脚/外设 → 另存为
`templates/ioc_templates/<家族>/<型号>/<型号>.ioc`（`make_ioc.py --json` 会报告是否命中）。

生成约 20s~3 分钟（含 CubeMX 启动）。**缺对应家族固件包**（如 FW_G4）时会先给 config-only 骨架并提示安装，装好重跑即补全。

> 型号解析支持双字母家族（WB/WL/WBA/N6/W5），如 `STM32WB55CGU6` 也能解析出核心/引脚/Flash；缺该家族固件包时照样 fail-fast 提示先装包。

**型号知识库（mcu_knowledge.py）自动解析**：`--mcu` 给完整型号即可，核心/FPU/最高主频/Flash/RAM/引脚数会按型号精确填充进 `hardware.yaml` 与 `CLAUDE.md`，不再默认 C8T6。

- **`--template`（SPL 旧路径，可选）**：F1→`f1xx_general`、F3→`f3xx_digital_power`、F4/F2→`f4xx_spl`；其他家族传 `--template` 无匹配 → 退 config-only。
- **`--no-cubemx`（config-only 骨架）**：只生成 CLAUDE.md/.claude/hardware.yaml，不生成代码。
- 型号解析不出/查不到 → 缺失项标 `TBD` 并告警，配合 `/newproject` 对话确认流程兜底。

独立查询型号规格：

```bash
python mcu_knowledge.py --query STM32F103CBT6        # 人类可读
python mcu_knowledge.py --query STM32F103CBT6 --json # 纯 ASCII JSON（给 Claude 解析）
python mcu_knowledge.py --list-families              # 家族核心/FPU/SPL 支持一览
```

独立生成工程相关脚本：

```bash
python make_ioc.py STM32G431CBT6 -o g4.ioc           # 型号 → 最小 .ioc（不启动 CubeMX）
python make_ioc.py STM32F103C8T6 -o f1.ioc --hse-mhz 16   # F1 走 HSI，非 8MHz 时告警（内置模板不缩放 PLLMUL）
python cubemx_gen.py g4.ioc                          # .ioc → 无头生成 HAL 工程
python cubemx_gen.py --ensure-fw g4.ioc              # 缺固件包时检查/提示安装
```

### 2. Claude Code 斜杠命令

| 命令 | 作用 |
|------|------|
| `/build` | 编译当前工程（调用 MCP keil_build） |
| `/flash` | 编译并烧录（keil_build + stlink_flash） |
| `/serial` | 列出串口并实时监控（serial_live.py） |
| `/review` | 用代码审查 Skill 审查当前代码 |
| `/newissue` | 记录一个踩坑/经验到 known_issues.md |
| `/newproject` | 对话式新建工程：先问项目名 + **完整芯片型号** → 解析规格给用户确认 → 默认 CubeMX 无头生成（全家族统一，可改 SPL/config-only） |

### 3. MCP 工具（Claude 自动调用）

| 类别 | 工具 |
|------|------|
| 编译 | `keil_build` / `keil_clean` |
| 烧录 | `stlink_flash` / `stlink_erase` |
| 探测 | `probe_info`（验证 ST-Link 连接）/ `find_build_output` |
| 串口 | `serial_list_ports` / `serial_send` / `serial_read` / `serial_monitor_start` / `serial_monitor_read` / `serial_monitor_stop` |
| 日志 | `parse_build_log`（含 AC5 编译器 + L62xxE 链接器错误解析） |

### 4. Hooks 强制工作流（仅在 Claude 轨工程、带 `.claude/settings.json` 时生效）

- **编辑源码**（`.c/.h/.s`）→ PostToolUse 置 `dirty=True` 并提醒"先编译验证"
- **再次编辑前** → PreToolUse 闸门：上次编译成功但存在未验证改动时 **block**，提示先 `/build`
- **调用 keil_build** → PostToolUse 记录结果，`dirty=False`（编译通过即放行）
- **新会话/相关话题** → 自动注入 `pin_usage.md` / `known_issues.md` 记忆
- **会话结束** → 追加 `session_log.md`
- **串口工具调用** → 强制先展示原始数据再分析

### 5. 独立串口监控（不开 Claude 也行）

```bash
python scripts/serial_live.py COM3 115200     # 实时看 + 自动存 serial_log_*.txt
python scripts/serial_live.py --list          # 列出串口
```

## 三、卸载 / 重装（验证阶段常用）

```bash
python uninstall.py            # 卸载：交互确认，配置移到备份目录（可恢复）
python uninstall.py --yes      # 非交互卸载
python uninstall.py --purge    # 卸载并删除全部备份（*.bak_* 和卸载备份），不可恢复
python install.py              # 重新安装
```

卸载行为：精确移除本工具包装的东西——全局 CLAUDE.md、4 个 Skill（按清单匹配）、6 个命令、MCP 注册；**不碰**其他同名目录里的自定义内容（如你自己加的 skill）。默认移到 `~/.claude/.stm32-toolkit-uninstalled/<时间戳>/`，随时可手动恢复；`--purge` 才真正删除。

> Python 依赖 fastmcp/pyserial 默认保留，如需一并卸载：`python uninstall.py --purge-deps`。
> 已生成工程里的 `.claude/settings.json`（hooks 配置）指向工具包路径，卸载不会删工程；若之后删除工具包文件夹，对应工程的 hooks 需自行清理。

### 工具包移动/换电脑后：自愈 hooks 路径

hooks 路径是绝对路径，工具包一旦移动或换电脑 clone，已有工程的 hooks 会静默失效。用 `--repair` 一键刷新：

```bash
python install.py --repair <已有工程目录>
# 等价：python new_project.py --dir <已有工程目录> --repair --yes
```

- 只重写 `.claude/settings.json` 里的 hooks 路径到当前工具包位置，**改动前备份旧文件**（`settings.json.bak_<时间戳>`，可回退）
- **不碰** CLAUDE.md / memory / hardware.yaml
- 已指向当前工具包 → 自动跳过；settings.json 未引用本工具包 hooks（自定义配置）→ 跳过，绝不覆盖

## 四、日常备份 / 同步

```bash
python backup.py --dry-run     # 预览要同步的文件（~/.claude → 工具包）
python backup.py               # 执行同步，覆盖前自动备份旧文件
```

`install.py` 安装 Skills/Commands 时也会先备份同名旧内容（`*.bak_时间戳`），不会静默覆盖自定义。

## 五、常见问题

| 现象 | 处理 |
|------|------|
| install.py 双击没反应 | 右键→打开方式→Python；确认装了 Python 3.8+ 并勾选 Add to PATH |
| Keil 检测不到 | 设 `KEIL_PATH=D:\Keil_v5\UV4\UV4.exe` 环境变量后重装 |
| 串口被占用打不开 | 关掉 Keil/串口助手；工具用 `dtr=False, rts=False` 避免误复位板子 |
| 编译报 `L6218E` 等链接错误 | 检查是否缺 .c 源文件/库、符号拼写（parse_build_log 会给提示） |
| 控制台打印中文乱码/崩溃 | 已统一 `fix_console_encoding()` 处理，正常环境不会触发 |
| 闸门 block 了编辑 | 按提示先 `/build` 编译通过即可继续（或对非源码文件不受影响） |
