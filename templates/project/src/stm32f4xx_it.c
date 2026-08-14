/**
  ******************************************************************************
  * @file    stm32f4xx_it.c
  * @brief   中断服务函数骨架（F4xx）
  * @note    目标型号：{{MCU_MODEL}}
  * @note    只保留用到的中断，未用到的注释掉，避免告警。
  ******************************************************************************
  */
#include "main.h"

/**
  * @brief  SysTick 中断（1ms 时基，按需填充）
  */
void SysTick_Handler(void)
{
    /* TODO: 在此维护 g_sysTick / delay_ms 时基 */
}

/**
  * @brief  HardFault 中断 —— 调试入口
  */
void HardFault_Handler(void)
{
    /* TODO: 断点 / 打印 CFSR、HFSR、BFAR 寄存器辅助定位 */
    while (1)
    {
        /* 死循环，便于调试器停在现场 */
    }
}

/**
  * @brief  ADC 转换完成中断（按需填充）
  * @note   F4xx 的 ADC 共用 ADC_IRQHandler；规则组/注入组使能中断后进入
  */
void ADC_IRQHandler(void)
{
    /* TODO: 读取转换结果 → 控制环路 / 采样处理 */
}
