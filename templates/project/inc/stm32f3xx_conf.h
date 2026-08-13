/**
  ******************************************************************************
  * @file    stm32f3xx_conf.h
  * @brief   外设头文件 include 清单（F3xx）—— 按需增删注释
  * @note    目标型号：{{MCU_MODEL}}
  ******************************************************************************
  */
#ifndef __STM32F3XX_CONF_H
#define __STM32F3XX_CONF_H

/* ============ 型号宏（通常在 Keil Options→C/C++ 预处理器中定义） ============ */
/* #define STM32F334x8     */   /* 例：F334C8T6 */

/* ============ 外设模块头文件清单（按需取消注释） ============ */
#include "stm32f3xx_adc.h"
#include "stm32f3xx_dma.h"
#include "stm32f3xx_flash.h"
#include "stm32f3xx_gpio.h"
#include "stm32f3xx_rcc.h"
#include "stm32f3xx_spi.h"
#include "stm32f3xx_tim.h"
#include "stm32f3xx_usart.h"
#include "stm32f3xx_hrtim.h"   /* F3xx 数字电源核心外设 */

/* 未使用的外设可注释掉，以加快编译：
#include "stm32f3xx_comp.h"
#include "stm32f3xx_dac.h"
#include "stm32f3xx_exti.h"
#include "stm32f3xx_i2c.h"
#include "stm32f3xx_pwr.h"
#include "stm32f3xx_rtc.h"
*/

#ifdef USE_FULL_ASSERT
  #define assert_param(expr) ((expr) ? (void)0 : assert_failed((uint8_t *)__FILE__, __LINE__))
  void assert_failed(uint8_t *file, uint32_t line);
#endif

#endif /* __STM32F3XX_CONF_H */
