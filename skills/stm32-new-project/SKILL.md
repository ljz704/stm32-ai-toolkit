---
name: stm32-new-project
description: 新建 STM32 工程。当用户要求新建 创建 生成一个新 STM32 工程、新项目，或提到 建工程 new project 时使用。对话式确认项目名+完整芯片型号→解析规格展示→默认 CubeMX 无头生成完整 HAL 工程（全家族统一），也可选 SPL 骨架或 config-only 骨架。
---

# 新建 STM32 工程（DSH 版）

> 原 Claude Code 斜杠命令 `/newproject` 的 DSH skill 形式。DSH 中直接描述需求即可触发。

**不要猜型号。** 逐项提问，每步确认后再继续。

## 第 1 步：项目名 + 完整芯片型号

- 问**项目名**（默认 `project`）。
- 问**完整芯片型号**，引导用户给全型号，举例：
  - `STM32F103C8T6`（64K）/ `STM32F103CBT6`（128K）/ `STM32F103RCT6`（256K）
  - `STM32F334C8T6` / `STM32F407ZGT6` / `STM32G431CBT6` / `STM32H743ZIT6`
  - 用户只说了模糊信息（如"F1"、"G4"）时，**追问具体型号**，不要默认 C8T6。

## 第 2 步：解析型号，展示规格让用户确认

在工具包根目录（TOOLKIT_PATH，见 `~/.dsh/AGENTS.md` 或工具包 README）运行：

```
python mcu_knowledge.py --query <型号> --json
```

把输出的 `core / max_freq_mhz / pins / flash_kb / ram_kb / spl / startup` 用易读格式**展示给用户**：

> 解析结果：STM32F103CBT6 → Cortex-M3 / 72MHz / 48 脚 / Flash 128K / RAM 20K / SPL 支持 / 启动文件 startup_stm32f10x_md.s

- `missing` 非空 → 指出缺失字段，请用户补正确型号或直接口述该值。
- 用户对任何值有异议 → 以用户说的为准，记录下来（后续提示可手动改 hardware.yaml）。

## 第 3 步：细节确认（1~2 个问题即可）

- **HSE 晶振**（默认 8MHz）——影响 hardware.yaml 的 clock 块。
- **核心功能**一句话（用于 CLAUDE.md 项目信息，可选）。

## 第 4 步：选生成方式（CubeMX 优先，全家族统一）

默认对**任何家族**（F0/F1/F3/F4/G4/H7…）都走 **CubeMX 无头生成**：
new_project.py 自动完成「型号→最小 .ioc（make_ioc，RCC 取自官方示例）→ CubeMX 生成完整
HAL 工程（Core/Drivers/MDK-ARM）→ 补装 AI 辅助层（CLAUDE.md/.dsh/memory/hardware.yaml）」。无需用户已有 .ioc。

只有两种情况让用户选：
- 用户明确要 **SPL 骨架**（仅 F0/F1/F2/F3/F4/L1 有模板）→ 加 `--template f1xx_general|f3xx_digital_power|f4xx_spl`。
- 用户只要 **config-only 骨架**（只含 CLAUDE.md/.dsh/hardware.yaml，不生成代码）→ 加 `--no-cubemx`。

> 生成需要已装对应家族的 STM32Cube FW 包。缺包时脚本给出明确提示，先建 config-only 骨架，
> 用户装好包后重跑即可补全。

## 第 5 步：执行

```
python new_project.py --name <项目名> --mcu <完整型号> --dir <目标目录> --env dsh --yes
```

- 默认 CubeMX 路径：生成 <目标目录>/<项目名>.ioc + Core/Drivers/MDK-ARM/<项目名>.uvprojx + AI 层（DSH 轨：`.dsh/memory/` + 显式路径 CLAUDE.md，无 hooks）。
- `--env dsh` 必须带：确保生成 DSH 轨；若目标目录同时给 Claude 用，可追加 `--hooks` 强制生成 `.claude/settings.json`。
- `--template <模板名>`：SPL 旧路径骨架；`--no-cubemx`：config-only 骨架。
- 生成约 20s~3 分钟（首次含 CubeMX 启动与网络检查）。生成前可先调用 MCP `mcp__stm32-toolkit__cubemx_check` 确认工具可用。
- 成功后向用户展示生成的文件清单 + uvprojx 路径。

## 收尾

- 展示工程结构（文件树）+ 下一步：进工程目录用 DSH 打开 → 说"编译当前工程"（MCP keil_build）验证。
- 提醒：`hardware.yaml` 的 clock / 外设表按实际板卡补充。
- 说明：DSH 下无 hooks 闸门，改代码后主动编译验证；记忆文件在 `.dsh/memory/`。

## 已有工程补装 AI 层（--existing + --analyze，方案 B）

给已有 Keil 工程补装 AI 层时，**按工程类型分流**：

```
python new_project.py --dir <工程目录> --existing --mcu <型号> --env dsh --yes --analyze
```

### CubeMX/HAL 工程（有 Core/Src）
- `--analyze` 调用 analyze_hw.py 静态提取（MCU/时钟/GPIO/外设模块/行为），生成
  `hardware.yaml.draft` + `pin_usage.md.draft` + `ai_review_notes.md` 到工程目录。
- **失败自动降级**：脚本一旦跑不通（缺文件/异常/超时/退出码非 0/无草稿产物），
  new_project.py 自动提示改走 **AI 直读方案**（与 SPL 流程相同），不硬跑、不静默跳过。
- **AI 复核流程**（补装后必须执行）：
  1. 读 `ai_review_notes.md` 的复核清单
  2. 完整读取工程源码（main.c / gpio.c / 各外设 .c / main.h / hal_conf.h / uvprojx）
  3. 对关键结论（型号、时钟计算、引脚映射）**拉 2 个子代理独立读代码交叉验证**
  4. 验证通过后，把草稿定稿为正式 `hardware.yaml` / `.dsh/memory/pin_usage.md`（或 .claude/memory/）
- 注意：`--analyze` 只生成 .draft 草稿，**不会覆盖**已存在的正式 hardware.yaml（保护人工补全内容）。

### 传统 SPL 工程（无 Core，目录结构千变万化）
- **跳过 analyze_hw.py 脚本**（脚本对 SPL 变体目录覆盖不可靠），`--analyze` 会提示走 AI 直读。
- **AI 直读流程**（必须执行）：
  1. 完整读取源码：main.c（初始化调用+主循环）、各外设 .c（led/key/motor/rfid/lcd 等）、
     system_stm32f4xx.c（时钟 PLL 分支）、stm32f4xx.h（HSE_VALUE）、uvprojx（型号/内存）
  2. 填写 `hardware.yaml`（MCU/时钟/外设/引脚表）与 `.dsh/memory/pin_usage.md`
  3. **拉 2 个子代理独立读代码交叉验证**（型号/时钟计算/引脚映射/外设接口）
  4. 合并修正后定稿（注意：SPL 源码多为 GBK 编码，编辑须保持 GBK）
- 智能锁工程（STM32F401RET6，USER/CMSIS/LIB 结构）已按此流程定稿，可作参考。
