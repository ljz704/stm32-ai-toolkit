/**
  ******************************************************************************
  * @file    stm32f4xx_conf.h
  * @brief   外设头文件 include 清单（F4xx）—— 按需增删注释
  * @note    目标型号：{{MCU_MODEL}}
  ******************************************************************************
  */
#ifndef __STM32F4XX_CONF_H
#define __STM32F4XX_CONF_H

/* ============ 型号宏（通常在 Keil Options→C/C++ 预处理器中定义） ============ */
/* #define STM32F407xx     */   /* 例：F407ZGT6 */
/* #define STM32F401xC     */   /* 例：F401CCU6 */
/* #define STM32F411xE     */   /* 例：F411CEU6 */
/* #define STM32F429xx     */   /* 例：F429ZIT6 */

/* ============ 外设模块头文件清单（按需取消注释） ============ */
#include "stm32f4xx_adc.h"
#include "stm32f4xx_dma.h"
#include "stm32f4xx_flash.h"
#include "stm32f4xx_gpio.h"
#include "stm32f4xx_rcc.h"
#include "stm32f4xx_spi.h"
#include "stm32f4xx_tim.h"
#include "stm32f4xx_usart.h"

/* 未使用的外设可注释掉，以加快编译：
#include "stm32f4xx_cryp.h"
#include "stm32f4xx_dac.h"
#include "stm32f4xx_dcmi.h"
#include "stm32f4xx_exti.h"
#include "stm32f4xx_fsmc.h"
#include "stm32f4xx_i2c.h"
#include "stm32f4xx_pwr.h"
#include "stm32f4xx_rtc.h"
#include "stm32f4xx_sdio.h"
*/

#ifdef USE_FULL_ASSERT
  #define assert_param(expr) ((expr) ? (void)0 : assert_failed((uint8_t *)__FILE__, __LINE__))
  void assert_failed(uint8_t *file, uint32_t line);
#endif

#endif /* __STM32F4XX_CONF_H */
