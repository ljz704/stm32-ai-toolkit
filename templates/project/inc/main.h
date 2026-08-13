/**
  ******************************************************************************
  * @file    main.h
  * @brief   工程主头文件
  * @note    目标型号：{{MCU_MODEL}}
  ******************************************************************************
  */
#ifndef __MAIN_H
#define __MAIN_H

/* ==================== 库头文件（按型号系列自动选择） ==================== */
#if defined(STM32F10X_MD) || defined(STM32F10X_HD) || defined(STM32F10X_CL)
  #include "stm32f10x.h"
  #include "stm32f10x_conf.h"
#else
  #include "stm32f3xx.h"
  #include "stm32f3xx_conf.h"
#endif

/* ==================== 标准头文件 ==================== */
#include <stdint.h>
#include <string.h>

/* ==================== 用户宏 / 全局变量声明 ==================== */
/* TODO: 在此添加项目级宏与 extern 声明 */

#endif /* __MAIN_H */
