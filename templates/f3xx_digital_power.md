# 模板：STM32F3xx 数字电源项目

> 基于全局规范，本模板补充 F3xx 数字电源专用特征。项目级 CLAUDE.md 只需覆盖差异。

## 自动推断的硬件特征
- MCU 系列：STM32F3xx（Cortex-M4F，带单精度 FPU）
- 最高主频：72MHz（HSE 8MHz × 9）
- 关键外设：HRTIM、ADC（双注入通道）、COMP（比较器）、DAC、DMA
- FPU：必须在 Keil 中开启 `--fpu=fpv4-sp`，代码中可安全使用 `float`

## 标准外设库配置
- 库版本：STM32F3xx Standard Peripheral Library v1.3.0
- 关键头文件：`stm32f3xx.h`、`stm32f3xx_conf.h`
- 必须在 `stm32f3xx.h` 中定义 `STM32F334x8`（或对应型号宏）

## HRTIM 默认引脚分配
| 功能 | 默认引脚 | 互补输出 | 备注 |
|------|----------|----------|------|
| HRTIM_CHA1 | PA8 | PA9 | 主 PWM |
| HRTIM_CHA2 | PA10 | PA11 | |
| HRTIM_CHB1 | PA12 | PB12 | |
| HRTIM_CHB2 | PB13 | PB14 | |
| HRTIM_CHC1 | PB15 | PC6 | |
| HRTIM_CHC2 | PC7 | PC8 | |
| HRTIM_CHD1 | PC9 | PA7 | |
| HRTIM_CHD2 | PA6 | PA5 | |
| HRTIM_CHE1 | PB8 | PB9 | |
| HRTIM_CHE2 | PB10 | PB11 | |

> ⚠️ 注意：HRTIM 引脚与 USART1（PA9/PA10）、SPI1（PA5/PA6/PA7）有冲突，需提前规划！

## ADC 默认引脚分配
| 通道 | 引脚 | 典型用途 |
|------|------|----------|
| ADC1_IN1 | PA0 | 输出电压采样 |
| ADC1_IN2 | PA1 | 电感电流采样 |
| ADC1_IN3 | PA2 | 输入电压采样 |
| ADC1_IN4 | PA3 | 温度采样 |
| ADC2_IN1 | PA4 | 备用采样（双通道并联时） |

## 数字电源核心约束
- **HRTIM 死区时间**：必须 > 100ns，建议 200ns~500ns，防止上下管直通
- **ADC 采样点**：必须在 PWM 低电平中点触发，避开开关噪声
- **控制环路频率**：通常 20kHz~100kHz，由 HRTIM 周期事件触发 ADC
- **浮点运算**：仅允许在主循环/控制算法中使用，**严禁在中断中使用 FPU**
- **注入通道**：使用 ADC 注入组（Injected），由 HRTIM 触发，不占用 DMA

## 典型控制环路架构
```
HRTIM 周期事件 → 触发 ADC 注入采样 → ADC JEOC 中断
                                      ↓
                              读取电压/电流值
                                      ↓
                              PID/补偿器计算（float）
                                      ↓
                              更新 HRTIM 占空比寄存器
```

## 工程结构
```
Project/
├── MDK-ARM/
│   ├── Project.uvprojx
│   └── Objects/
├── startup/
│   └── startup_stm32f334x8.s
├── StdPeriph_Driver/
│   ├── src/
│   └── inc/
├── src/
│   ├── main.c
│   ├── stm32f3xx_it.c
│   ├── system_stm32f3xx.c
│   ├── hrtim/
│   │   └── hrtim_config.c
│   ├── adc/
│   │   └── adc_config.c
│   ├── control/
│   │   └── pid_controller.c
│   └── comm/
│       └── uart_debug.c
└── inc/
    ├── main.h
    ├── stm32f3xx_conf.h
    └── control/
        └── pid_controller.h
```

## F3xx 特有注意事项
- **HRTIM 时钟**：来自 PLL × 2 = 144MHz，经预分频得到 4.608GHz 等效分辨率
- **ADC 校准**：每次上电后必须执行 `ADC_VoltageRegulatorCmd(ENABLE)` 和 `ADC_SelectCalibrationMode()`，等待校准完成
- **COMP 比较器**：可用于过流保护（OCP），输出直接连到 HRTIM 的 Fault 输入
- **Flash 延迟**：72MHz 时 LATENCY=2
