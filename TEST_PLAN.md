# STM32 AI 工作流 —— 亲自验证测试方案

> 用途：验证阶段手动验收。按顺序逐条勾选，每步给出「命令 → 预期结果 → 通过标准」。
> 涉及破坏性操作（卸载）的先在**临时工程/假配置**上验证，再动真实环境。
> 时间预算：脚本层约 15 分钟，Claude Code 端到端约 20 分钟，硬件（可选）约 10 分钟。

## 验证进度（2026-08-13）

> 进行中。今天完成到 **阶段 3.4**；下次从下方 ⏳ 继续。

**✅ 已通过：**
- 阶段 0：Python 3.12 / Claude CLI 2.1.226 / Keil `D:\Keil_v5` / CubeProgrammer `D:\STM32CubeProgrammer` 全部就绪
- 阶段 1.1：`install.py --yes` 全绿（依赖 / 全局 CLAUDE.md / 4 Skills / 6 Commands / MCP 注册 / install_summary.json）
- 阶段 1.7：`install.py --project TEST` 补装 AI 层到真实 CubeMX 工程。验证中发现并修复 2 个脚手架 bug：
  **编译命令硬编码 `C:\Keil_v5` → 自动检测**、**.uvprojx 工程名错写默认名 → 自动探测真实文件名**
- 阶段 2：`claude mcp get stm32-toolkit` = User 级 **Connected**，env 含 `KEIL_PATH` + `STM32_PROGRAMMER`
- 阶段 3.1-3.4（在 `TEST` 工程实测）：
  - 记忆加载 ✅（hardware.yaml / CLAUDE.md / pin_usage 被 AI 读取并按实际 CubeMX 工程补全）
  - 编译 ✅ 多次成功：`Flash 2484 B / RAM 1040 B`（`keil_build` + UV4 日志解析）
  - 编译状态记录 ✅（session_log.md 自动追加 `### 编译 … ✅ Flash … RAM …`）
  - 编译闸门 / `/build` / `/review` / `/newissue` / `/newproject` ✅
  - known_issues.md 已沉淀实战问题：`??` trigraph 残留导致编译失败（`#29 expected an expression`）

**⏳ 待验证（下次继续）：**
- 阶段 1.2 / 1.3：卸载 → `--purge` → 重装 闭环（备份可逆性 / 干净重装）
- 阶段 1.4：`backup.py` 备份同步（--dry-run 预览 ✅，执行同步待跑）
- 阶段 1.6：F3 脚手架模板分流 —— **已验证 + 修复**（见下 2026-08-14）
- 阶段 3.5：会话结束落盘 —— **已验证**（追加分隔线+时间戳，追加不覆盖）
- 阶段 4：硬件验证（无板子，已挂起）—— `probe_info` / `/flash` / 串口两路
- 阶段 5：`py_compile` 全量 ✅；工具包改动已提交 git（2026-08-13 / 2026-08-14）

**✅ CubeMX 代码生成功能（2026-08-13 新增，已验证）：**
- `cubemx_gen.py`：从 .ioc 无头生成完整工程（Core/Drivers/MDK-ARM）。CLI + `--json` 安静模式
  - 完成检测：轮询 `~/.stm32cubemx/STM32CubeMX.log` 增量完成标记（+uvprojx 兜底，含竞态补抓）
  - 残留清理：重试式杀 javaw（3 轮 + 2s 缓冲），实测零残留
  - 生成物可编译：TEST.ioc → 75 文件 → Keil 0 Error / 0 Warning
- MCP 工具 `cubemx_check` + `cubemx_generate`（server 子进程调脚本 `--json`，`in_place` 默认关闭）
- `register_mcp.py` / `install.py`：Keil/Programmer/CubeMX 三路径统一探测（含 D: 盘）+ `-e CUBEMX_PATH=` 烤进注册
- **实踩并修复**：MCP server（Node 拉起）内 spawn 嵌套 python 卡死 60s → 加 `stdin=DEVNULL` + `CREATE_NO_WINDOW` 解决（见 FAQ）
- MCP 全链路实测通过：`cubemx_check` 秒回 / `cubemx_generate` 21s 生成 75 文件 / 生成物编译 0 Error

**✅ 2026-08-14 修复与完善（已验证）：**
- **record_build「❌ 0 errors」误导记录** → 重写 `keil_build` 错误解析：
  - 摘要行权威计数（`N Error(s)`）+ 真实错误行正则（含 AC5 链接错误 `L6218E` / `Target not created`）
  - 修复成功时把摘要行 `0 Error(s), 0 Warning(s).` 误抓进 errors 的问题（成功日志 errors 现为空）
  - 失败但 0 具体错误时带原因落盘（如 `❌ 失败(0 具体错误, ❌ 编译失败)`），杜绝裸 `❌ 0 errors`
  - 实测：TEST 真实编译 success=True errors=[] returncode=0；4 项脚本断言全过
- **hooks 路径自愈** → 新增 `install.py --repair <工程>`（等价 `new_project.py --dir <工程> --repair --yes`）：
  - 工具包移动/换电脑 clone 后一键刷新 `.claude/settings.json` 的 hooks 路径（改前备份，可回退）
  - 保守策略：已指向当前路径跳过 / 自定义配置（未引用 scripts/hooks）跳过，绝不覆盖
  - 三场景实测通过（免改 / 陈旧路径备份+重写 / 自定义跳过）
- **hardware.yaml F3 家族分流修复**：模板 mcu 块原本写死 F1 值（F334 也生成 20KB RAM / M3 / 无 FPU）
  → 新增 {{MCU_CORE/RAM/FLASH/FPU/STARTUP}} 按模板填充；实测 F334=16KB/M4F/FPU/startup_stm32f334x8.s
- 阶段 1.4 `backup.py --dry-run` 预览、3.5 `finalize_session_log` 落盘：验证通过

**✅ 2026-08-14 型号知识库 + 对话式新建工程（已完成，待 1.8 验收清单勾选）：**
- 新增 `mcu_knowledge.py`：完整型号解析（F1/F3/F4/G4/H7/L4…）→ 核心/FPU/主频/引脚/Flash/RAM/启动文件
  - 密度→Flash 通用规则（4=16K…I=2M）；RAM 按家族/产品线查表（查不到→missing 不崩）
  - 启动文件按密度/产品线（F1 的 cl/md/hd/xl、F3 的 f334x8、F4 的 f407xx 等）
  - `--query <型号> --json`（纯 ASCII，规避 GBK 乱码）；`--list-families`
  - 实测 8+ 型号：C8T6/CBT6/ZET6/F334/F407/G431(无 SPL)/H743(2M)/乱型号
- `new_project.py` 重写 MCU 处理：模板按家族自动选（F1/F3/F4+F2），F0/L1 与全部非 SPL → **config-only 骨架**
  - hardware.yaml mcu 块全动态（+max_freq/package/pins/density/family_label/spl_support）
  - 新增 `--query-mcu`（预览规格）；非 SPL 家族提示转 CubeMX/HAL
  - 实测 F103CBT6/F334C8T6/F407ZGT6/G431CBT6/H743ZIT6 + `--existing` 回归
- 新增 F4 模板 `stm32f4xx_it.c` / `stm32f4xx_conf.h`；`/newproject` 重写为对话提问流

---

## 阶段 0：前置检查（2 分钟）

| 检查项 | 命令 | 通过标准 |
|--------|------|----------|
| Python | `python --version` | ≥ 3.8 |
| Claude CLI | `claude --version` | 有版本号 |
| Keil | `ls "C:/Keil_v5/UV4/UV4.exe"` 或 `echo %KEIL_PATH%` | 找到 exe，或已设环境变量 |
| STM32CubeProgrammer | `ls "C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe"` | 找到 exe，或已设 `STM32_PROGRAMMER` |
| 硬件（可选） | 板子接 ST-Link / USB 转串口 | 设备管理器能看到 |

> Keil/CubeProgrammer 在非默认路径：先设 `KEIL_PATH` / `STM32_PROGRAMMER` 环境变量，再继续。

---

## 阶段 1：脚本层自测（不需要 Claude，15 分钟）

### 1.1 全新安装

```bash
cd C:\Users\lqt\Desktop\test\stm32-ai-toolkit
python install.py --yes
```

**预期输出：** 依次 `✅`（依赖安装）→ 全局 CLAUDE.md → 4 个 Skill → 6 个命令 → 工具链检查 → MCP 注册 → 生成 `install_summary.json`。

**通过标准（逐项核对文件）：**
- [x] `%USERPROFILE%\.claude\CLAUDE.md` 存在
- [x] `%USERPROFILE%\.claude\skills\` 下有 4 个目录，每个含 `SKILL.md`：
  `stm32-build-flash-debug` / `stm32-code-review` / `stm32-debug-analyze` / `stm32-peripheral-config`
- [x] `%USERPROFILE%\.claude\commands\` 下有 6 个 `.md`：
  `build` / `flash` / `serial` / `review` / `newissue` / `newproject`
- [x] 工具包目录生成 `install_summary.json`，内容含 `installed_skills`（4 项）、`installed_commands`（6 项）
- [x] 工具链检查：Keil / CubeProgrammer 至少一项 `✅`（若都是 warn，先回阶段 0 设环境变量）

### 1.2 卸载（验证可逆性）

```bash
python uninstall.py --yes
```

**预期输出：** 逐项「✅ 已移出 … → …\.stm32-toolkit-uninstalled\<时间戳>\」，最后 `claude mcp remove` 提示。

**通过标准：**
- [ ] `%USERPROFILE%\.claude\CLAUDE.md` 已消失
- [ ] skills/commands 里本工具包的内容已消失
- [ ] 备份目录 `%USERPROFILE%\.claude\.stm32-toolkit-uninstalled\<时间戳>\` 存在，且 **CLAUDE.md / skills / commands 都完整**
- [ ] `claude mcp list` 不再显示 `stm32-toolkit`

### 1.3 彻底清理 + 重装（干净重装闭环）

```bash
python uninstall.py --yes --purge     # 删除备份，彻底清理
python install.py --yes               # 重新安装
```

**通过标准：**
- [ ] 卸载备份目录已不存在
- [ ] 重装后 1.1 的 6 项检查全部复现 ✅

### 1.4 备份同步

```bash
python backup.py --dry-run
python backup.py
```

**通过标准：**
- [ ] `--dry-run` 列出将同步的文件，无报错
- [ ] 执行后工具包 `global_claude.md` 等与 `~/.claude` 内容一致

### 1.5 脚手架：F1 工程

```bash
python new_project.py --name demo --mcu STM32F103C8T6 --dir C:\Users\lqt\Desktop\test\demo_f1 --yes
```

**通过标准（生成 12 个左右文件）：**
- [x] `CLAUDE.md` 存在，含 `@.claude/memory/*.md` 导入行
- [x] `.claude/settings.json` 存在且是合法 JSON，其中 `TOOLKIT_PATH` 渲染为 `C:/Users/lqt/Desktop/test/stm32-ai-toolkit`
- [x] `.claude/memory/` 有 4 个 md（architecture / pin_usage / known_issues / session_log）
- [x] `hardware.yaml`、`src/main.c`、`src/stm32f10x_it.c`、`inc/main.h`、`inc/stm32f10x_conf.h`、`MDK-ARM/README.md`
- [x] 自动 `git init`（除非 `--no-git`）

### 1.6 脚手架：F3 工程（验证模板分流）

```bash
python new_project.py --name demo3 --mcu STM32F334C8T6 --dir C:\Users\lqt\Desktop\test\demo_f3 --yes
```

**通过标准：**
- [ ] 生成的是 `stm32f3xx_it.c` / `stm32f3xx_conf.h`（而非 f10x 版本）
- [ ] `hardware.yaml` 注明的内存为 16KB SRAM（F334）
- [ ] 你的 MCU 若为 F334，检查 `CLAUDE.md` 里 SRAM 描述一致

### 1.7 对已有 Keil 工程补装 AI 层

```bash
python install.py --project C:\你的\已有Keil工程
# 等价：python new_project.py --dir <已有工程> --existing --yes
```

**通过标准：**
- [x] 只补 `.claude/`（CLAUDE.md / settings.json / memory / hardware.yaml），**不创建** src/inc/MDK-ARM
- [x] 原有工程文件零改动

### 1.8 型号知识库 / 多家族脚手架（mcu_knowledge.py + new_project.py）

**型号解析单测（不建工程）：**

```bash
python mcu_knowledge.py --query STM32F103C8T6 --json    # → 64K / 20K / M3 / startup_md / 48脚
python mcu_knowledge.py --query STM32F103CBT6 --json    # → 128K（C8 之外的第二密度）
python mcu_knowledge.py --query STM32F103ZET6 --json    # → 512K / 64K / startup_hd
python mcu_knowledge.py --query STM32F334C8T6 --json    # → 16K / M4F / startup_f334x8
python mcu_knowledge.py --query STM32F407ZGT6 --json    # → 1M / 192K / 168MHz / startup_f407xx
python mcu_knowledge.py --query STM32G431CBT6 --json    # → spl=false（无 SPL），128K/32K，missing 不含 startup
python mcu_knowledge.py --query STM32H743ZIT6 --json    # → 2M / 992K / 480MHz / spl=false
python mcu_knowledge.py --query "不是型号" --json        # → missing 非空，不崩溃
```

**多家族脚手架（默认已改 CubeMX 优先，SPL/config-only 走显式参数）：**

```bash
# SPL 旧路径（不启动 CubeMX）：
python new_project.py --name t1 --mcu STM32F103CBT6 --template f1xx_general --dir <tmp> --no-git --yes   # f1xx 全骨架，hw=128K/20K/pins48
python new_project.py --name t2 --mcu STM32F334C8T6 --template f3xx_digital_power --dir <tmp> --no-git --yes  # f3xx 全骨架，16K/M4F
# config-only（--no-cubemx，不启动 CubeMX）：
python new_project.py --name t3 --mcu STM32G431CBT6 --no-cubemx --dir <tmp> --no-git --yes   # 无 src/inc，只装 AI 层
python new_project.py --name t4 --mcu STM32H743ZIT6 --no-cubemx --dir <tmp> --no-git --yes   # 480MHz/2M
```

**通过标准：**
- [x] 各型号 `hardware.yaml` mcu 块核心/FPU/主频/Flash/RAM/引脚数/启动文件与数据手册一致（CBT6=128K、G431=32K、H743=992K）—— 已实测四份
- [x] `--template`：F1/F3/F4 生成 src/inc/MDK-ARM 全套 + 对应 it.c/conf.h；`--no-cubemx` 只生成 7 个 config 文件（无 src/inc）
- [x] `new_project.py --query-mcu STM32F407ZGT6 --json` 输出与 mcu_knowledge 完全一致（diff 为空）
- [x] 默认（无 `--template`）走 CubeMX 路径且打印「方式: CubeMX 无头生成」；F103/G431 两条 e2e 见 1.9
- [ ] `/newproject` 对话流：问型号 → 展示规格确认 → 默认 CubeMX 生成 → 产出工程（需在工程里交互测，命令已同步安装最新版）

### 1.9 型号→.ioc→无头生成（make_ioc.py + cubemx_gen.py，CubeMX 优先核心链路）

**单测（不启动 CubeMX）：**

```bash
python make_ioc.py STM32F103C8T6 --json      # ok=true；mcu_name=STM32F103C(8-B)Tx；package_name=LQFP48；rcc_source=内置模板（F1）
python make_ioc.py STM32G431CBT6 --json      # ok=true；mcu_name=STM32G431C(6-8-B)Tx；example=<FW_G4 官方示例路径>；example_clock 带 HSE/PLLM
python make_ioc.py STM32WB55CGU6 --json      # ok=false；error_type=missing_firmware；required_fw=STM32Cube_FW_WB
python make_ioc.py STM32F334C8T6 --json      # ok=false；error_type=missing_firmware（未装 FW_F3）
```

**端到端（启动 CubeMX，20s~3 分钟）：**

```bash
# F1 兜底 RCC 家族（包内无官方 .ioc 示例）
python new_project.py --name np_f103 --mcu STM32F103C8T6 --dir <tmp> --yes --no-git
# G4 官方示例 RCC 家族
python new_project.py --name np_g4 --mcu STM32G431CBT6 --dir <tmp> --yes --no-git
```

**通过标准（2026-08-14 已实测）:**
- [x] F103：21.1s 生成 73 文件 + `MDK-ARM/np_f103.uvprojx`；AI 层 7 文件；ioc 含 `FirmwarePackage=STM32Cube FW_F1 V1.8.7`（带 V）、无 `VP_RCC_VS_HSE`、`PinsNb=1`
- [x] G431：21.1s 生成 82 文件 + `MDK-ARM/np_g4.uvprojx`；RCC 块取自官方示例（HSE=24MHz、PLLM=DIV4）
- [x] 缺固件包家族 fail-fast（WB 报 missing_firmware，不启动 CubeMX 傻等）
- [x] `out_dir == ioc 所在目录` 时 generate 跳过自拷贝（修复 WinError 32 PermissionError）
- [x] Keil 打开生成的 uvprojx 能编译通过：`new_project.py --name np_f103_keil --mcu STM32F103C8T6` → keil_build 0 Error / 0 Warning，Flash 2062B / RAM 1648B（Compiler V5.06 update 7）
- [x] F0 家族：`F030C8T6` → `Mcu.Name=STM32F030C8Tx`（DB 单密度文件校验，修 C6Tx 误选）；21.1s/79 文件 + keil_build 0 Error（M0/48MHz/64K/8K 全规格无 TBD）
- [x] 双字母家族统一解析：`mcu_knowledge --query STM32WB55CGU6` → WB/Cortex-M4F/1MB/64MHz（split_model 替换单字母正则，make_ioc 复用同函数）
- [x] `--hse-mhz` 缩放：`--mcu STM32F103C8T6 --hse-mhz 16` → ioc `PLLMUL=RCC_PLL_MUL8`（64MHz），keil_build 0 Error；8MHz 默认仍 MUL16 无回归
- [x] DONE_MARKERS 误报修复：`done=True` 但 uvprojx 未落盘 → success=False 报工具链失败（不再"生成完成"假成功）
- [ ] L1 内置 RCC 兜底：需装 FW_L1 后实测（字段照抄 NUCLEO-L152RE Board.ioc，走 HSI 与 HSE 无关）

---

## 阶段 2：MCP 注册验证（2 分钟）

```bash
claude mcp list
claude mcp get stm32-toolkit
```

**通过标准：**
- [x] `list` 显示 `stm32-toolkit: stdio — Connected`
- [x] `get` 能看到 `env` 里有 `KEIL_PATH` / `STM32_PROGRAMMER`（说明路径已烤进配置）
- [x] 若注册在 install 之后，先**新开一个 Claude 会话**再测（MCP 按会话加载）

---

## 阶段 3：Claude Code 端到端（核心，20 分钟）

> 本次验证用的是真实 CubeMX 工程 **`TEST`**（`install.py --project` 补装的 AI 层），效果等同新脚手架工程 + hooks。
> 启动命令（PS 5.1 用 `;` 不用 `&&`）：`cd C:\Users\lqt\Desktop\test\TEST; claude`

### 3.1 记忆/文档自动加载
问 Claude：**"这个工程的目标 MCU 和内存大小是多少？硬件有哪些？"**
- [x] 它应从 `hardware.yaml` + `CLAUDE.md` 准确回答（F103C8T6，20KB RAM 等）
- 不准确 → 检查 CLAUDE.md 的 `@.claude/memory/*.md` 与 hardware.yaml 内容

### 3.2 编译 + 编译状态记录
说：**"编译当前工程"**
- [x] Claude 调用 `keil_build`（或运行 UV4.exe 命令），返回 0 Error 结果
- [x] `.claude\build_state.json` 变成 `{"status": "success", "dirty": false, ...}`
- [x] `.claude\memory\session_log.md` 追加了一行 `### 编译 … ✅ Flash … RAM …`

### 3.3 编译闸门（核心验收项）
1. 说：**"在 main.c 里加一个空的辅助函数 test_helper()"**
   - [x] Claude 改完后注入提醒：「刚修改了源码，按铁律应先编译验证…」
   - [x] `build_state.json` 的 `dirty` 变为 `true`
2. **紧接着**再说：**"再在 main.c 里加一个 test_helper2()"**（此时上次编译成功但改动未验证）
   - [x] 应出现 **block** 提示（PreToolUse 闸门：有未验证的源码改动，请先 /build）
   - [x] Claude 会停下来请你先编译
3. 说：**"/build 编译通过后再继续"** 或直接 `/build`
   - [x] 编译成功后 `dirty` 回到 `false`，继续编辑不再被 block

> 说明：闸门只在「上次编译成功 + 有未验证改动」时拦截；工程从没编译成功过不会 block（避免死锁）。

### 3.4 斜杠命令
- [x] `/build` → 编译当前工程
- [x] `/review` → 对当前代码做审查（输出审查结论）
- [x] `/newissue` → 记录一条已知问题到 `known_issues.md`
- [x] `/newproject` → 交互式新建工程（按提示给名字/型号）
- `/flash`、`/serial` 在阶段 4 有板子时测

### 3.5 会话结束落盘
正常退出会话（exit）或让会话结束
- [ ] `session_log.md` 追加本次会话的关键结论（finalize_session_log）

---

## 阶段 4：硬件验证（可选，有板子时 10 分钟）

在 demo 工程会话里：

### 4.1 连接探测
说：**"检查 ST-Link 连接"**
- [ ] `probe_info` 返回 `Connection OK`（或列出设备 ID）

### 4.2 编译 + 烧录
放一个能验证动作的固件（如 LED 翻转），然后：
- [ ] `/flash` → STM32_Programmer_CLI 烧录成功，板子出现预期动作
- [ ] 烧录失败时能读懂错误（工具给出 stlink 相关提示）

### 4.3 串口实时监控（两路）
1. 独立脚本（终端 1）：
   ```bash
   python scripts\serial_live.py COM<实际口> 115200
   ```
   - [ ] 板子 `printf` 实时打印带时间戳，日志写入 `serial_log_*.txt`
2. Claude 会话（终端 2）：
   - [ ] 用 `serial_monitor_start` 让 AI 读串口 → AI **先原样展示原始数据**，再分析
   - [ ] 若 AI 跳过原始数据直接结论，`enforce_raw_data` hook 应注入提醒

---

## 阶段 5：收尾

- [ ] `cd C:\Users\lqt\Desktop\test\stm32-ai-toolkit && python -m py_compile _cmdutil.py install.py uninstall.py backup.py new_project.py mcu_knowledge.py mcp/stm32_mcp_server.py scripts/serial_live.py scripts/hooks/*.py` → 无报错
- [ ] 卸载测试用的 demo_f1 / demo_f3 目录（或保留作样例）。**删除时 Explorer 可能提示"需要管理员权限"——这是含 `.git` 隐藏目录的已知怪癖，直接命令行删即可，不需要管理员**：
      ```bash
      rm -rf C:\Users\lqt\Desktop\test\demo_f1   # Git Bash
      # 或 cmd:  rmdir /s /q C:\Users\lqt\Desktop\test\demo_f1
      ```
- [ ] 有修改的话把工具包改动提交 git

---

## 常见问题速查

| 现象 | 原因 / 处理 |
|------|-------------|
| install 装依赖卡住/超时 | 网络问题，重试；或手动 `pip install fastmcp pyserial` |
| Keil 检测不到 | 设 `KEIL_PATH` 环境变量后重跑 install |
| MCP 工具 Claude 调不到 | 先 `claude mcp list` 确认 Connected；新开会话 |
| hooks 不生效 | 必须在带 `.claude/settings.json` 的工程目录里启动 claude |
| 闸门从不 block | 该工程还没有"成功编译"记录，先让它编译成功一次 |
| 串口打不开 | 关掉占用串口的软件；工具已用 dtr=False 避免误复位 |
| 卸载后想恢复 | 备份在 `%USERPROFILE%\.claude\.stm32-toolkit-uninstalled\<时间戳>\`，手动拷回即可 |
| 删除 demo 工程提示"需要管理员权限" | 含 `.git` 隐藏目录的 Explorer 已知怪癖，权限本身没问题。用 `rm -rf` / `rmdir /s /q` 删，或在 Explorer 弹窗点"继续" |
| PowerShell 5.1 报 `&&` 不是有效语句分隔符 | 本清单命令为 bash 风格。PS 5.1 不支持 `&&`，改用 `;` 或分行（如 `cd 目录; claude`） |
| 中文/emoji 乱码 | 脚本已统一 fix_console_encoding，正常环境不应出现；若出现报告路径 |
| MCP 工具调不到/刚加的 cubemx 工具没有 | MCP 按会话加载：新加的 @mcp.tool 需要**新开 claude 会话**才出现；`claude mcp list` 确认 Connected |
| MCP server 内 spawn 嵌套 python 卡死 60s 超时 | 根因：claude(Node) 拉起的 MCP server 再 spawn python.exe 时，子进程继承 claude stdio 句柄导致启动卡死。**已修**：cubemx 后端调用加 `stdin_devnull=True` + `creationflags=CREATE_NO_WINDOW`（见 `_cmdutil.run_cmd` 可选参数）。若未来新增嵌套 python 工具，务必带上这两个参数 |
