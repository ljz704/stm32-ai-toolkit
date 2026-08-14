---
description: 对话式新建 STM32 工程（先问型号→解析规格→确认→建骨架或 CubeMX 生成）
---

# /newproject —— 对话式新建 STM32 工程

**不要猜型号。** 逐项提问，每步确认后再继续。$ARGUMENTS 里的 `--name` / `--mcu` / `--dir` 可直接带过对应提问。

## 第 1 步：项目名 + 完整芯片型号

- 问**项目名**（默认 `rn8209_meter`）。
- 问**完整芯片型号**，引导用户给全型号，举例：
  - `STM32F103C8T6`（64K）/ `STM32F103CBT6`（128K）/ `STM32F103RCT6`（256K）
  - `STM32F334C8T6` / `STM32F407ZGT6` / `STM32G431CBT6` / `STM32H743ZIT6`
  - 用户只说了模糊信息（如"F1"、"G4"）时，**追问具体型号**，不要默认 C8T6。

## 第 2 步：解析型号，展示规格让用户确认

在工具包根目录（TOOLKIT_PATH，见 `.claude/settings.json`）运行：

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
HAL 工程（Core/Drivers/MDK-ARM）→ 补装 AI 辅助层」。无需用户已有 .ioc。

只有两种情况让用户选：
- 用户明确要 **SPL 骨架**（仅 F0/F1/F2/F3/F4/L1 有模板）→ 加 `--template f1xx_general|f3xx_digital_power|f4xx_spl`。
- 用户只要 **config-only 骨架**（只含 CLAUDE.md/.claude/hardware.yaml，不生成代码）→ 加 `--no-cubemx`。

> 生成需要已装对应家族的 STM32Cube FW 包。缺包时脚本给出明确提示，先建 config-only 骨架，
> 用户装好包后重跑即可补全。

## 第 5 步：执行

```
python new_project.py --name <项目名> --mcu <完整型号> --dir <目标目录> --yes
```

- 默认 CubeMX 路径：生成 <目标目录>/<项目名>.ioc + Core/Drivers/MDK-ARM/<项目名>.uvprojx + AI 层。
- `--template <模板名>`：SPL 旧路径骨架；`--no-cubemx`：config-only 骨架。
- 生成约 20s~3 分钟（首次含 CubeMX 启动与网络检查）。生成前可先 `cubemx_check` 确认工具可用。
- 成功后向用户展示生成的文件清单 + uvprojx 路径。

## 收尾

- 展示工程结构（文件树）+ 下一步：进工程目录开 Claude Code → `/build` 验证编译。
- 提醒：`hardware.yaml` 的 clock / 外设表按实际板卡补充。
