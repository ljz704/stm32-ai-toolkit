# STM32 AI 开发工作流 —— 使用说明

> 配套：安装/恢复看 [README.md](README.md)，设计说明看 [WORKFLOW_GUIDE_v2.md](WORKFLOW_GUIDE_v2.md)。

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

### 1. 新建工程

```bash
python new_project.py --name meter --mcu STM32F103CBT6 --yes
# 或对已有 Keil 工程只补装 AI 层：
python new_project.py --dir <已有工程> --existing --yes
# 只解析型号、预览规格（不建工程，/newproject 对话里用于确认）：
python new_project.py --query-mcu STM32G431CBT6 --json
```

生成的内容：`CLAUDE.md`（含 `@.claude/memory/*.md` 自动加载）、`.claude/settings.json`（hooks）、`.claude/memory/`（架构/引脚/坑记录/会话日志）、`hardware.yaml`、`src/`、`inc/`。

**型号知识库（mcu_knowledge.py）自动解析**：`--mcu` 给完整型号即可，核心/FPU/最高主频/Flash/RAM/引脚数/启动文件会按型号精确填充进 `hardware.yaml` 与 `CLAUDE.md`，不再默认 C8T6。

- **模板按家族自动选**：F1→`f1xx_general`、F3→`f3xx_digital_power`、F4/F2→`f4xx_spl`（新增 stm32f4xx_it.c/conf.h）。
- **config-only 骨架**：F0/L1（SPL 但无专用模板）与全部**非 SPL 家族**（F7/G0/G4/H7/L4/L5/U5/WB）只生成 CLAUDE.md/.claude/hardware.yaml，不生成 src/inc 移植文件；非 SPL 家族会提示转 CubeMX/HAL。
- 型号解析不出/查不到 → 缺失项标 `TBD` 并告警，配合 `/newproject` 对话确认流程兜底。

独立查询型号规格：

```bash
python mcu_knowledge.py --query STM32F103CBT6        # 人类可读
python mcu_knowledge.py --query STM32F103CBT6 --json # 纯 ASCII JSON（给 Claude 解析）
python mcu_knowledge.py --list-families              # 家族核心/FPU/SPL 支持一览
```

### 2. Claude Code 斜杠命令

| 命令 | 作用 |
|------|------|
| `/build` | 编译当前工程（调用 MCP keil_build） |
| `/flash` | 编译并烧录（keil_build + stlink_flash） |
| `/serial` | 列出串口并实时监控（serial_live.py） |
| `/review` | 用代码审查 Skill 审查当前代码 |
| `/newissue` | 记录一个踩坑/经验到 known_issues.md |
| `/newproject` | 对话式新建工程：先问项目名 + **完整芯片型号** → 解析规格给用户确认 → 选 SPL 骨架或 CubeMX 生成 |

### 3. MCP 工具（Claude 自动调用）

| 类别 | 工具 |
|------|------|
| 编译 | `keil_build` / `keil_clean` |
| 烧录 | `stlink_flash` / `stlink_erase` |
| 探测 | `probe_info`（验证 ST-Link 连接）/ `find_build_output` |
| 串口 | `serial_list_ports` / `serial_send` / `serial_read` / `serial_monitor_start` / `serial_monitor_read` / `serial_monitor_stop` |
| 日志 | `parse_build_log`（含 AC5 编译器 + L62xxE 链接器错误解析） |

### 4. Hooks 强制工作流（在带 `.claude/settings.json` 的工程里生效）

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
