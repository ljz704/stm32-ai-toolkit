/**
  ******************************************************************************
  * @file    stm32f10x_it.c
  * @brief   中断服务函数骨架（F1xx）
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
