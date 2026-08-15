# 全局开发规范 —— STM32 嵌入式工程师（DSH 版）

> 本文件是 DeepSeek Harness（DSH）的用户级全局指令，等价于原 Claude Code 的
> `~/.claude/CLAUDE.md`。DSH 会自动加载 `~/.dsh/AGENTS.md`（本文件安装到此处），
> 项目级差异写在各工程根目录的 `CLAUDE.md`（DSH 原生支持 AGENTS.md / CLAUDE.md 两种文件名）。

## 我是谁
- 嵌入式软件工程师，主要使用 STM32 标准外设库（SPL）进行固件开发
- 开发环境：Windows 10 + Keil MDK-ARM 5.38 + ARM Compiler 5.06 update 7
- 调试工具：ST-Link V2、CH340 USB-TTL、示波器 GDS-1104E
- 版本管理：GitHub（用户名 zhoushoujianwork）

## 工具链路径（Windows 固定）
```
Keil MDK:           D:\Keil_v5\UV4\UV4.exe
CubeProgrammer CLI: D:\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe
CubeMX:             D:\STM32CubeMX\STM32CubeMX.exe
```

## 编译与烧录命令（MCP 工具优先）
> DSH 环境中，以下能力通过 `mcp__stm32-toolkit__*` 工具直接调用，无需手敲命令：
> `keil_build`（编译）、`stlink_flash`（烧录）、`probe_info`（探针检测）、
> `serial_*`（串口）、`parse_build_log`（日志解析）、`cubemx_generate`（CubeMX 生成）。

```bash
# Keil 命令行编译（Release 模式，MCP keil_build 等价物）
"D:\Keil_v5\UV4\UV4.exe" -b Project\MDK-ARM\Project.uvprojx -o BuildLog.txt -j0

# 烧录 Hex（ST-Link SWD，MCP stlink_flash 等价物）
"STM32_Programmer_CLI.exe" -c port=SWD -w "Project\MDK-ARM\Objects\Project.hex" 0x08000000 -v -rst
```

## 编码规范（所有项目强制遵守）
- **函数命名**：`ModuleName_ActionName()`，如 `ADC_Init()`、`HRTIM_Config()`、`RN8209_ReadReg()`
- **全局变量**：`g_` 前缀，如 `g_adcBuffer`、`g_sysTick`
- **宏定义**：全大写 + 模块前缀，如 `HRTIM_PERIOD`、`ADC_SAMPLE_COUNT`、`RN8209_CS_PIN`
- **局部变量**：驼峰命名，如 `sampleCount`、`timeoutMs`
- **结构体**：`typedef struct { ... } ModuleName_TypeDef;`
- **枚举**：`typedef enum { ... } ModuleName_StateTypeDef;`
- **注释风格**：Doxygen，所有函数必须有 `@brief`、`@param`、`@retval`
- **寄存器配置注释**：必须注明参考手册章节，如 `// REF: RM0364 Section 18.4.1`

## 绝对禁止
- ❌ 使用 `malloc/free` 或任何动态内存分配
- ❌ 在中断服务函数中调用阻塞函数（如 `delay_ms`）
- ❌ 在中断中使用浮点运算（FPU 上下文保存开销大）
- ❌ 递归调用
- ❌ 魔法数字，必须用 `#define` 或 `const`

## 开发习惯与调试偏好
- 新工程第一步：验证时钟配置（LED 闪烁或串口输出 `SystemInit OK`）
- 外设初始化顺序：`RCC时钟使能` → `GPIO配置` → `NVIC中断` → `外设参数配置` → `使能外设`
- 调试时先用串口打印关键变量，再考虑 Keil 在线调试（Debug）
- 遇到硬件问题优先排查：电源 → 晶振 → 复位 → SWD 接线 → BOOT0 电平
- 示波器验证习惯：PWM 波形先看频率再看占空比，ADC 采样点用触发抓
- 串口波特率默认 115200-8-N-1，调试信息带时间戳或循环计数

## DSH 环境使用要点（区别于 Claude Code）
1. **斜杠命令**：DSH 原生 commands 是代码注册制；本工作流的 `/build` `/flash` `/serial`
   `/review` `/newissue` `/newproject` 命令已转为同名 skill（`stm32-*`），直接描述需求即可触发。
2. **MCP 工具命名**：统一为 `mcp__stm32-toolkit__<工具名>`，如 `mcp__stm32-toolkit__keil_build`。
3. **无 hooks 闸门**：DSH 没有 PreToolUse/PostToolUse 钩子，编译验证闸门靠自觉遵守——
   **改完代码必须主动调用 `keil_build` 验证，0 Error 后才能继续**。
4. **记忆文件**：工程根目录 `CLAUDE.md` 里显式引用 `.dsh/memory/*.md`（architecture /
   pin_usage / known_issues / session_log），开始相关任务前先读取。
5. **Skill 触发**：DSH 会自动按描述匹配 skill（stm32-build-flash-debug / stm32-code-review /
   stm32-debug-analyze / stm32-peripheral-config / stm32-new-project / stm32-known-issues），
   调用前先加载对应 skill 的完整说明。

## MCU 系列知识库
### STM32F103C8T6（Cortex-M3）
- 72MHz，64KB Flash，20KB SRAM，无 FPU
- 注意：部分外设引脚需要 Remap（如 USART1 到 PB6/PB7）
- 启动文件：`startup_stm32f10x_md.s`（Medium-density）
- ADC：12bit，规则组 + 注入组，注意通道 16 是温度传感器

### STM32F334C8T6（Cortex-M4F）
- 72MHz，64KB Flash，**16KB SRAM（12KB 常规 SRAM + 4KB CCM，均带硬件奇偶校验）**，**带 FPU**
- HRTIM：主定时器，4.608GHz 等效分辨率，死区时间独立配置
- ADC：双注入通道，支持 HRTIM 触发，注意采样保持时间
- 启动文件：`startup_stm32f334x8.s`
- 浮点：编译器选项必须开启 `--fpu=fpv4-sp`，代码中 `#include <arm_math.h>`

### 通用启动文件选择规则
| Flash 容量 | 后缀 | 典型型号 |
|-----------|------|----------|
| 16~32KB   | ld   | F103C6   |
| 64~128KB  | md   | F103C8, F334C8 |
| 256~512KB | hd   | F103VE   |
| ≥512KB    | xl   | F103ZG   |

## 常用外设默认配置
- **SysTick**：1ms 中断，用于 `delay_ms()` 和系统时基
- **USART**：115200-8-N-1，DMA 接收（环形缓冲区 256B）
- **ADC**：12bit，右对齐，独立模式，软件触发或定时器触发
- **TIM**：时基定时器通常配 1kHz（1ms）中断
- **I2C**：标准模式 100kHz，开漏输出 + 外部上拉 4.7kΩ
- **SPI**：模式 0（CPOL=0, CPHA=0），MSB 优先，8bit
