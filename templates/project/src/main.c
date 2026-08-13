/**
  ******************************************************************************
  * @file    main.c
  * @brief   工程主入口 —— SystemInit OK 验证（LED 闪烁）
  * @note    目标型号：{{MCU_MODEL}}
  * @note    首次编译前按实际硬件修改下方 LED 引脚定义。
  ******************************************************************************
  */
#include "main.h"

/* ==================== LED 硬件定义（按实际工程修改） ==================== */
#define LED_GPIO_PORT          GPIOB
#define LED_GPIO_PIN           GPIO_Pin_1

/* F1xx GPIO 时钟挂在 APB2；F3xx 挂在 AHB */
#if defined(STM32F10X_MD) || defined(STM32F10X_HD) || defined(STM32F10X_CL)
  #define LED_GPIO_CLKCMD      RCC_APB2PeriphClockCmd
  #define LED_GPIO_CLK         RCC_APB2Periph_GPIOB
#else
  #define LED_GPIO_CLKCMD      RCC_AHBPeriphClockCmd
  #define LED_GPIO_CLK         RCC_AHBPeriph_GPIOB
#endif

/**
  * @brief  简易软件延时（仅供验证骨架，正式工程请用 SysTick 时基）
  * @param  count: 空循环次数
  */
static void delay_loop(volatile uint32_t count)
{
    while (count--)
    {
        __NOP();
    }
}

/**
  * @brief  主函数
  * @note   SystemInit() 已在启动文件跳入 main 前执行，时钟已配置。
  *         第一步验证：LED 闪烁 = SystemInit OK（{{MCU_MODEL}}）。
  * @retval 不返回
  */
int main(void)
{
    GPIO_InitTypeDef gpio;

    /* ========== 1. 使能 GPIO 时钟 ========== */
    LED_GPIO_CLKCMD(LED_GPIO_CLK, ENABLE);

    /* ========== 2. 配置 LED 引脚为推挽输出 ========== */
    GPIO_StructInit(&gpio);
    gpio.GPIO_Pin  = LED_GPIO_PIN;
#if defined(STM32F10X_MD) || defined(STM32F10X_HD) || defined(STM32F10X_CL)
    gpio.GPIO_Mode  = GPIO_Mode_Out_PP;   /* F1xx: 推挽输出 */
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
#else
    gpio.GPIO_Mode  = GPIO_Mode_OUT;      /* F3xx: 输出模式 + 推挽类型 */
    gpio.GPIO_OType = GPIO_OType_PP;
    gpio.GPIO_Speed = GPIO_Speed_50MHz;
#endif
    GPIO_Init(LED_GPIO_PORT, &gpio);

    /* ========== 3. 主循环：LED 闪烁 ========== */
    while (1)
    {
        GPIO_WriteBit(LED_GPIO_PORT, LED_GPIO_PIN, Bit_SET);
        delay_loop(2000000);
        GPIO_WriteBit(LED_GPIO_PORT, LED_GPIO_PIN, Bit_RESET);
        delay_loop(2000000);
    }
}
