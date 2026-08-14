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

## 第 4 步：选生成方式

**情况 A：型号是 SPL 家族**（F0/F1/F2/F3/F4/L1，`spl: true`）：

- 问用户二选一：
  1. **建 SPL 骨架**（默认）→ 走第 5 步 A。
  2. **已有 .ioc → CubeMX 无头生成** → 走第 5 步 B。

**情况 B：型号非 SPL 家族**（F7/G0/G4/H7/L4/L5/U5/WB，`spl: false`）：

- **推荐 CubeMX/HAL**：
  - 用户有该芯片的 `.ioc` → 走第 5 步 B（生成后补装 AI 层）。
  - 没有 `.ioc` → 用 new_project.py 建 **config-only 骨架**（只含 CLAUDE.md/.claude/hardware.yaml，规格已按型号填好），并提示后续用 CubeMX 生成后补装。走第 5 步 A。

## 第 5 步：执行

**A. 建骨架（new_project.py）**：

```
python new_project.py --name <项目名> --mcu <完整型号> --dir <目标目录> --yes
```

- 非 SPL 家族时脚本会自动走 config-only；SPL 家族按家族自动选 f1xx/f3xx/f4xx 模板。
- 成功后向用户展示生成的文件清单。

**B. CubeMX 生成 + 补装 AI 层**：

```
# 1) 无头生成（in_place 默认关闭，输出到 <ioc 同目录>/cubemx_out/）
#    用 MCP 工具 cubemx_generate，ioc_path 指向用户的 .ioc

# 2) 生成完成后，给生成目录补装 AI 辅助层（CLAUDE.md / hooks / hardware.yaml）
python install.py --project <生成目录>
```

> CubeMX 生成前可先 `cubemx_check` 确认工具可用；生成约 20s~3 分钟。

## 收尾

- 展示工程结构（文件树）+ 下一步：进工程目录开 Claude Code → `/build` 验证编译。
- 提醒：`hardware.yaml` 的 clock / 外设表按实际板卡补充。
