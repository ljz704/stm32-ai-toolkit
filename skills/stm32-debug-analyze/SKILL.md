---
name: stm32-debug-analyze
description: STM32 调试问题分析。当用户报告程序跑飞 死机 卡死 HardFault 进中断出不来 串口无输出或乱码 LED不亮 ADC采样不准 PWM无波形 上电无反应，或粘贴串口日志 报错 CFSR PC LR BFAR 寄存器值时使用。先收集结构化信息，读记忆文件 known_issues.md（.dsh/memory 或 .claude/memory，取存在者）历史教训，展示原始数据后给出根因与修复方案。
---

# STM32 调试问题分析

## 核心原则
1. **先收集结构化信息，再分析**
2. **展示原始数据后再给结论**
3. **读取记忆文件 `known_issues.md`（路径取存在者：DSH 轨 `.dsh/memory/`，Claude 轨 `.claude/memory/`），检查是否有历史教训**

## 调试快照模板（引导用户收集信息）

如果用户没有提供足够信息，按以下模板追问：

```markdown
### 环境
- 代码版本: <git commit hash>
- 编译选项: <Debug/Release, 优化等级>
- 运行模式: <Debug在线调试 / 独立运行>

### 现象
- 预期行为: 
- 实际行为: 
- 发生频率: <每次/偶尔/随机>
- 修改历史: <改了什么代码后出现的>

### 日志与数据
```text
<粘贴串口输出或调试日志>
```

### 寄存器状态（HardFault时）
- CFSR: 0x________
- PC: 0x________
- LR: 0x________
- BFAR: 0x________

### 已尝试的排查
- [ ] 已确认晶振起振（示波器抓 HSE 引脚）
- [ ] 已确认供电稳定
- [ ] 已确认 BOOT0 电平
- [ ] 已确认 SWD 接线
- [ ] 已读取串口输出
```

## 分析流程

### Step 1：读取项目记忆
1. 读取项目 `CLAUDE.md`（DSH 亦支持 AGENTS.md）确认 MCU 型号和配置
2. 读取记忆文件 `known_issues.md`（`.dsh/memory/` 或 `.claude/memory/`，取存在者）检查历史教训
3. 读取记忆文件 `pin_usage.md`（`.dsh/memory/` 或 `.claude/memory/`，取存在者）检查引脚冲突

### Step 2：分类定位

#### 类型 A：上电即死机/无反应
排查顺序：
1. 时钟未起振 → 检查 HSE 晶振（示波器抓 PF0/PF1 或对应晶振引脚）
2. 启动文件不匹配 → 检查 startup 文件与芯片型号是否对应
3. SystemInit 卡死 → 检查 PLL 配置是否超频
4. 全局变量初始化溢出 → 检查 `.data`/`.bss` 段大小是否超过 RAM
5. 中断未配置但触发了 → 检查是否有悬空中断线

#### 类型 B：HardFault
分析必备信息：
- LR 寄存器值（判断是线程模式还是 Handler 模式）
- PC 寄存器值（出错指令地址）
- CFSR 寄存器（精确错误原因：IBUSERR、PRECISERR、STKERR 等）
- BFAR 寄存器（如果 CFSR.BFARVALID=1，则是总线错误地址）

常见原因：
| CFSR 标志 | 含义 | 常见原因 |
|-----------|------|----------|
| IBUSERR | 指令总线错误 | 跳转到无效地址、函数指针未初始化 |
| PRECISERR | 精确数据总线错误 | 访问未映射地址、数组越界 |
| IMPRECISERR | 非精确数据总线错误 | DMA 访问无效地址 |
| STKERR | 压栈错误 | 栈溢出、中断嵌套过深 |
| UNSTKERR | 出栈错误 | 栈被破坏 |
| NOCP | 协处理器错误 | 使用了 FPU 但编译器未开启 FPU 支持 |
| INVPC | 无效 PC 加载 | 中断返回时 LR 值错误 |

#### 类型 C：外设不工作（无输出/无波形）
排查顺序：
1. RCC 时钟使能了吗？（`RCC_APBxPeriphClockCmd`）
2. GPIO 复用功能配置了吗？（`GPIO_PinAFConfig`）
3. NVIC 中断使能了吗？（`NVIC_Init`）
4. 外设本身使能了吗？（`TIM_Cmd(ENABLE)` / `ADC_Cmd(ENABLE)`）
5. DMA 配置了吗？（如果是 DMA 模式）
6. 示波器验证：信号是否到达引脚？

#### 类型 D：通信异常（串口乱码/CAN 不通/SPI 无响应）
排查顺序：
1. 波特率/时钟分频是否正确？（用示波器测量实际波特率）
2. 引脚配置是否正确？（TX 推挽输出，RX 浮空输入）
3. 是否有上拉/下拉电阻？（I2C 必须外部上拉）
4. 地线是否共地？
5. 协议时序是否符合从机要求？（用逻辑分析仪抓）

### Step 3：串口数据收集（如需要）
1. 调用 `serial_list_ports` 找可用串口
2. 调用 `serial_read` 或 `serial_monitor_start` 读取数据
3. **必须展示原始数据**后再分析

### Step 4：给出修复方案
- 针对定位到的问题，给出具体代码修改或配置调整
- 如果信息不足，给出「下一步诊断步骤」（如"请用示波器测量 PA8 引脚是否有 PWM 波形"）
- **修复后必须建议用户调用 `keil_build` 验证编译**

## 输出格式
```markdown
## 问题分类：[类型X]
## 根因分析：
[具体分析]

## 原始数据：
```text
[用户提供的日志/寄存器值]
```

## 修复方案：
```c
[具体代码]
```

## 验证步骤：
1. [步骤1]
2. [步骤2]

## 预防措施：
[记录到 known_issues.md 的建议]
```
