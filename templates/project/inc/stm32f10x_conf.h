/**
  ******************************************************************************
  * @file    stm32f10x_conf.h
  * @brief   外设头文件 include 清单（F1xx）—— 按需增删注释
  * @note    目标型号：{{MCU_MODEL}}
  ******************************************************************************
  */
#ifndef __STM32F10X_CONF_H
#define __STM32F10X_CONF_H

/* ============ 型号宏（通常在 Keil Options→C/C++ 预处理器中定义） ============ */
/* #define STM32F10X_MD    */   /* Medium-density: F103C8T6 */
/* #define STM32F10X_HD    */   /* High-density */

/* ============ 外设模块头文件清单（按需取消注释） ============ */
#include "stm32f10x_adc.h"
#include "stm32f10x_dma.h"
#include "stm32f10x_flash.h"
#include "stm32f10x_gpio.h"
#include "stm32f10x_rcc.h"
#include "stm32f10x_spi.h"
#include "stm32f10x_tim.h"
#include "stm32f10x_usart.h"

/* 未使用的外设可注释掉，以加快编译：
#include "stm32f10x_bkp.h"
#include "stm32f10x_can.h"
#include "stm32f10x_cec.h"
#include "stm32f10x_dac.h"
#include "stm32f10x_exti.h"
#include "stm32f10x_i2c.h"
#include "stm32f10x_iwdg.h"
#include "stm32f10x_pwr.h"
#include "stm32f10x_rtc.h"
#include "stm32f10x_sdio.h"
#include "stm32f10x_wwdg.h"
*/

#ifdef USE_FULL_ASSERT
  #define assert_param(expr) ((expr) ? (void)0 : assert_failed((uint8_t *)__FILE__, __LINE__))
  void assert_failed(uint8_t *file, uint32_t line);
#endif

#endif /* __STM32F10X_CONF_H */
