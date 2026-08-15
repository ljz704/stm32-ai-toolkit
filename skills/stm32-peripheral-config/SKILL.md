---
name: stm32-peripheral-config
description: 生成 STM32 标准外设库(SPL)外设初始化代码。当用户要求配置初始化 ADC TIM PWM USART UART SPI I2C DMA HRTIM NVIC CAN Modbus 等外设，或说 怎么配X 给我写个X初始化 时使用。先读 hardware.yaml 与记忆文件 pin_usage.md（.dsh/memory 或 .claude/memory，取存在者）确认引脚，按编码规范生成 Doxygen 注释的初始化函数，输出调用顺序与 RCC 时钟使能说明。
---

# STM32 外设配置生成（SPL 标准外设库）

## 执行流程

### Step 1：确认上下文
1. 读取项目级 `CLAUDE.md`（DSH 亦支持 AGENTS.md），确认 MCU 型号（F1/F3/F0 的 SPL API 差异很大）
2. 读取 `hardware.yaml` 确认外设与引脚分配
3. 读取记忆文件 `pin_usage.md`（路径取存在者：DSH 轨 `.dsh/memory/`，Claude 轨 `.claude/memory/`）检查引脚占用冲突
4. 如果引脚分配中已有该外设，直接基于已有引脚生成；如果引脚未分配，根据模板默认引脚推荐，并询问用户确认

### Step 2：收集外设参数
根据外设类型，询问必要参数：

**ADC：**
- 通道号（如 IN1, IN2）
- 采样时间（默认 239.5 cycles）
- 触发源（软件触发 / 定时器触发 / HRTIM 触发）
- 分辨率（12bit / 10bit / 8bit / 6bit）
- 模式（独立 / 双重 / DMA）

**TIM（通用/高级）：**
- 定时频率（如 1kHz / 100kHz）
- 主频（从 CLAUDE.md/AGENTS.md 读取，默认 72MHz）
- PWM 模式（Edge-aligned / Center-aligned）
- 通道数（CH1~CH4）
- 死区时间（高级定时器/HRTIM）

**USART：**
- 波特率（默认 115200）
- 数据位/停止位/校验位（默认 8-N-1）
- 模式（轮询 / 中断 / DMA）
- 硬件流控（无 / RTS/CTS）

**SPI：**
- 模式（CPOL, CPHA）
- 时钟分频（如 SPI_BaudRatePrescaler_256）
- 数据大小（8bit / 16bit）
- 片选方式（硬件 NSS / 软件 GPIO）

**I2C：**
- 时钟频率（标准 100kHz / 快速 400kHz）
- 从机地址（7bit / 10bit）
- 模式（主发 / 主收 / 从机）

**HRTIM（F3xx 特有）：**
- PWM 频率（如 100kHz）
- 死区时间（ns 级）
- 通道（CHA1~CHE2）
- 触发 ADC 事件（是否需要在周期点触发注入采样）

### Step 3：生成代码
按照项目编码规范生成初始化代码：
1. 函数命名符合 `ModuleName_ActionName()`
2. 包含 Doxygen 注释（@brief, @param, @retval）
3. 寄存器配置注明参考手册章节（如 `// REF: RM0008 Section 11`）
4. 提供 `xxx_Init()` 和 `xxx_DeInit()`（如有必要）

### Step 4：输出使用说明
- 告诉用户把代码放到哪个文件（如 `src/adc/adc_config.c`）
- 告诉用户需要在 `main()` 中调用的顺序
- 告诉用户需要开启的 RCC 时钟（通常已包含在代码中，但提醒确认）

## ADC 输出示例（STM32F103，SPL v3.5）

> 注意：以下示例是 F1 + SPL v3.5 的 API。F3/F0 的 API 不同（见文末说明）。

```c
/**
 * @brief  ADC1 初始化配置（STM32F103，SPL v3.5）
 * @param  None
 * @retval None
 * @note   REF: RM0008 Section 11
 */
void ADC1_Init(void)
{
    ADC_InitTypeDef ADC_InitStructure;
    GPIO_InitTypeDef GPIO_InitStructure;

    /* 1. 使能时钟 */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_ADC1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* 2. GPIO 模拟输入：F1 是 GPIO_Mode_AIN，F3/F0 才用 GPIO_Mode_AN */
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AIN;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* 3. 上电校准（F1 每次上电建议执行） */
    ADC_ResetCalibration(ADC1);
    while (ADC_GetResetCalibrationStatus(ADC1));
    ADC_StartCalibration(ADC1);
    while (ADC_GetCalibrationStatus(ADC1));

    /* 4. ADC 参数：F1 无 ADC_Resolution / ADC_ScanDirection，固定 12bit */
    ADC_InitStructure.ADC_Mode = ADC_Mode_Independent;
    ADC_InitStructure.ADC_ScanConvMode = DISABLE;
    ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;
    ADC_InitStructure.ADC_ExternalTrigConv = ADC_ExternalTrigConv_None;
    ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;
    ADC_InitStructure.ADC_NbrOfChannel = 1;
    ADC_Init(ADC1, &ADC_InitStructure);

    /* 5. 规则通道：F1 用 ADC_RegularChannelConfig(ADC, ch, 顺序, 采样时间) */
    ADC_RegularChannelConfig(ADC1, ADC_Channel_1, 1, ADC_SampleTime_239Cycles5);

    /* 6. 使能并软件触发一次 */
    ADC_Cmd(ADC1, ENABLE);
    ADC_SoftwareStartConvCmd(ADC1, ENABLE);
}
```

并附带 `main()` 中的调用位置和注意事项。

## 示例适用性说明

- 若目标片是 **F103（RM0008）**，用上面的 F1 SPL v3.5 API。
- 若目标片是 **F334（RM0364）**，才用 `ADC_Resolution_12b` / `ADC_ExternalTrigConvEdge_None` / `ADC_ScanDirection_Upward` / `ADC_ChannelConfig` 那套 F3 SPL v1.3 API。
