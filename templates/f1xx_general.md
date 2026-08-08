# 模板：STM32F1xx 通用项目

> 基于全局规范，本模板补充 F1xx 系列通用特征。项目级 CLAUDE.md 只需覆盖差异。

## 自动推断的硬件特征
- MCU 系列：STM32F1xx（Cortex-M3，无 FPU）
- 最高主频：72MHz（HSE 8MHz × 9）
- Flash/SRAM：根据具体型号（C8=64KB/20KB，C6=32KB/10KB）
- 调试接口：SWD（PA13/PA14），注意 JTAG 引脚复用

## 标准外设库配置
- 库版本：STM32F10x Standard Peripheral Library v3.5.0
- 关键头文件：`stm32f10x.h`、`stm32f10x_conf.h`
- 必须在 `stm32f10x.h` 中定义 `STM32F10X_MD`（或对应型号宏）
- 必须在 `stm32f10x_conf.h` 中 `#include` 所需外设头文件

## 默认引脚分配（需根据项目确认/覆盖）
| 功能 | 默认引脚 | 备注 |
|------|----------|------|
| USART1_TX | PA9 | 可 Remap 到 PB6 |
| USART1_RX | PA10 | 可 Remap 到 PB7 |
| USART2_TX | PA2 | |
| USART2_RX | PA3 | |
| SPI1_SCK | PA5 | |
| SPI1_MISO | PA6 | |
| SPI1_MOSI | PA7 | |
| I2C1_SCL | PB6 | 需外部上拉 4.7kΩ |
| I2C1_SDA | PB7 | 需外部上拉 4.7kΩ |
| CAN_RX | PA11 | 注意与 USB 冲突 |
| CAN_TX | PA12 | 注意与 USB 冲突 |
| TIM2_CH1 | PA0 | 注意与 ADC1_IN0 冲突 |
| TIM2_CH2 | PA1 | 注意与 ADC1_IN1 冲突 |
| ADC1_IN0 | PA0 | |
| ADC1_IN1 | PA1 | |
| ADC1_IN9 | PB1 | |

## 时钟树默认配置
```
HSE 8MHz → PLL ×9 → SYSCLK 72MHz
         → AHB 分频 1 → HCLK 72MHz
         → APB1 分频 2 → PCLK1 36MHz（TIM2~7 时钟 72MHz）
         → APB2 分频 1 → PCLK2 72MHz（TIM1/8、ADC、USART1）
         → ADC 预分频 6 → ADCCLK 12MHz（<14MHz 限制）
```

## 工程结构
```
Project/
├── MDK-ARM/
│   ├── Project.uvprojx
│   └── Objects/
├── startup/
│   └── startup_stm32f10x_md.s
├── StdPeriph_Driver/
│   ├── src/
│   └── inc/
├── src/
│   ├── main.c
│   ├── stm32f10x_it.c
│   └── system_stm32f10x.c
└── inc/
    ├── main.h
    └── stm32f10x_conf.h
```

## F1xx 特有注意事项
- **Remap**：USART1、TIM1、CAN 等引脚可通过 AFIO 重映射，配置顺序：`RCC_APB2PeriphClockCmd(RCC_APB2Periph_AFIO)` → `GPIO_PinRemapConfig()`
- **ADC 通道 16**：内部温度传感器，采样时间必须 ≥ 17.1μs
- **Flash 延迟**：72MHz 时必须设置 2 个等待周期（LATENCY=2）
- **BOOT0 引脚**：烧录时接高电平进 System Memory，运行时接低电平
