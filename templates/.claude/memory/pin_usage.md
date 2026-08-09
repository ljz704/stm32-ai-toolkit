# 引脚占用表

> 实时更新，每次新增外设后必须登记

## 已占用引脚
| 引脚 | 功能 | 外设 | 模式 | 状态 | 备注 |
|------|------|------|------|------|------|
| PA0 | ADC1_IN0 | ADC1 | AIN | 已用 | 电压采样 |
| PA1 | ADC1_IN1 | ADC1 | AIN | 已用 | 电流采样 |
| PA4 | GPIO_OUT | SPI1 | OUT_PP | 已用 | RN8209 软件片选 |
| PA5 | SPI1_SCK | SPI1 | AF_PP | 已用 | |
| PA6 | SPI1_MISO | SPI1 | IN_FLOATING | 已用 | |
| PA7 | SPI1_MOSI | SPI1 | AF_PP | 已用 | |
| PA9 | USART1_TX | USART1 | AF_PP | 已用 | 调试串口 |
| PA10 | USART1_RX | USART1 | IN_FLOATING | 已用 | 调试串口 |
| PB0 | EXTI0 | GPIO | IN_FLOATING | 已用 | RN8209 脉冲中断 |

## 可用引脚
| 引脚 | 状态 | 建议用途 |
|------|------|----------|
| PA2 | 可用 | USART2_TX / TIM2_CH3 |
| PA3 | 可用 | USART2_RX / TIM2_CH4 |
| PA8 | 可用 | TIM1_CH1 / MCO |
| PB1 | 可用 | ADC1_IN9 / TIM3_CH4 |
| PB6 | 可用 | I2C1_SCL / USART1_TX(Remap) |
| PB7 | 可用 | I2C1_SDA / USART1_RX(Remap) |

## 冲突检查记录
- [ ] 已检查 HRTIM 与 USART1 引脚冲突（仅 F3xx）
- [ ] 已检查 ADC 与 TIM 引脚冲突
- [ ] 已检查 I2C 外部上拉
