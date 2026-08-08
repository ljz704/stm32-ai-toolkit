# STM32 外设配置生成

## 触发条件
用户说以下任意关键词时触发：
- "配置 ADC"、"初始化 TIM"、"设置 UART"
- "给我写个 SPI 初始化"、"I2C 怎么配"
- "HRTIM 怎么配置"、"PWM 初始化"
- "DMA 配置"、"中断配置"
- "CAN 总线初始化"、"Modbus 配置"

## 执行流程

### Step 1：确认上下文
1. 读取项目级 `CLAUDE.md`，确认 MCU 型号和引脚分配
2. 如果引脚分配中已有该外设，直接基于已有引脚生成
3. 如果引脚未分配，根据模板默认引脚推荐，并询问用户确认

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
- 主频（从 CLAUDE.md 读取，默认 72MHz）
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
3. 寄存器配置注明参考手册章节
4. 提供 `xxx_Init()` 和 `xxx_DeInit()`（如有必要）

### Step 4：输出使用说明
- 告诉用户把代码放到哪个文件（如 `src/adc/adc_config.c`）
- 告诉用户需要在 `main()` 中调用的顺序
- 告诉用户需要开启的 RCC 时钟（通常已包含在代码中，但提醒确认）

## 输出格式
```c
/**
 * @brief  ADC1 初始化配置
 * @param  None
 * @retval None
 * @note   REF: RM0364 Section 18.4.1
 */
void ADC1_Init(void)
{
    ADC_InitTypeDef ADC_InitStructure;
    GPIO_InitTypeDef GPIO_InitStructure;

    /* 1. 使能时钟 */
    RCC_APB2PeriphClockCmd(RCC_APB2Periph_ADC1 | RCC_APB2Periph_GPIOA, ENABLE);

    /* 2. 配置 GPIO */
    GPIO_InitStructure.GPIO_Pin = GPIO_Pin_0;
    GPIO_InitStructure.GPIO_Mode = GPIO_Mode_AN;
    GPIO_Init(GPIOA, &GPIO_InitStructure);

    /* 3. 配置 ADC 参数 */
    ADC_InitStructure.ADC_Resolution = ADC_Resolution_12b;
    ADC_InitStructure.ADC_ContinuousConvMode = DISABLE;
    ADC_InitStructure.ADC_ExternalTrigConvEdge = ADC_ExternalTrigConvEdge_None;
    ADC_InitStructure.ADC_DataAlign = ADC_DataAlign_Right;
    ADC_InitStructure.ADC_ScanDirection = ADC_ScanDirection_Upward;
    ADC_Init(ADC1, &ADC_InitStructure);

    /* 4. 配置采样时间 */
    ADC_ChannelConfig(ADC1, ADC_Channel_1, ADC_SampleTime_239Cycles5);

    /* 5. 使能 ADC */
    ADC_Cmd(ADC1, ENABLE);
}
```

并附带 `main()` 中的调用位置和注意事项。
