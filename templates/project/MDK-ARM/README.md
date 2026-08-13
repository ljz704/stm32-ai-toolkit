# MDK-ARM

> 本目录用于放置 Keil MDK-ARM 工程文件（`.uvprojx`）。

## 如何生成 .uvprojx

脚手架不直接生成 Keil 工程文件（不同 SPL / 外设组合差异大），请用以下任一方式：

### 方式一：Keil 新建工程向导（推荐）
1. 打开 Keil μVision → `Project` → `New uVision Project...`，保存到本目录
2. 选择 MCU：`{{MCU_MODEL}}`（或同系列具体型号）
3. 启动文件：按 Flash 容量选 `startup_stm32f10x_md.s`（F1xx）或 `startup_stm32f334x8.s`（F3xx）
4. `Options for Target` → `C/C++`：
   - 预处理器定义：`STM32F10X_MD`（F1xx）或 `STM32F334x8`（F3xx）
   - 勾选 `Use MicroLIB`
   - F3xx 数字电源项目需加 `--fpu=fpv4-sp`
5. 添加源文件：`../src/main.c`、`../src/stm32f10x_it.c`（或 `stm32f3xx_it.c`）、ST 库的 `system_stm32f10x.c` / `system_stm32f3xx.c`
6. Include Paths：`../inc`、`StdPeriph_Driver/inc`、库的 `CMSIS` 目录

### 方式二：STM32CubeMX 生成
1. CubeMX 选择 `{{MCU_MODEL}}`，配置时钟与外设
2. `Project Manager` → Toolchain 选 `MDK-ARM`，输出路径指到本目录
3. CubeMX 生成的 `main.c` 可在此基础上改写

## 命令行编译
```bash
"C:\Keil_v5\UV4\UV4.exe" -b {{MDK_PROJECT}}.uvprojx -o BuildLog.txt -j0
```
