# STM32 编译-烧录-验证闭环

## 触发条件
用户说以下任意关键词时触发：
- "编译"、"build"、"make"
- "烧录"、"下载"、"flash"、"deploy"
- "运行"、"测试"、"验证"
- "编译烧录"、"build and flash"
- "重新编译"、"clean build"

## 执行流程

### Step 1：定位工程
1. 扫描当前目录及子目录，查找 `.uvprojx` 文件
2. 如果找到多个，列出供用户选择；如果只有一个，直接使用
3. 确认工程路径后，读取同目录下的 `CLAUDE.md`（如有）获取编译/烧录命令覆盖

### Step 2：编译（Build）
1. 执行 Keil 命令行编译：
   ```
   "C:\Keil_v5\UV4\UV4.exe" -b <工程路径> -o BuildLog.txt -j0
   ```
2. 等待编译完成，解析 `BuildLog.txt`
3. 结果分类：
   - **0 Error, 0 Warning** → 进入 Step 3
   - **有 Warning** → 列出所有 Warning，询问是否继续
   - **有 Error** → 进入「编译错误处理」子流程，**停止后续步骤**

### Step 3：烧录（Flash）
1. 自动查找编译输出的 `.hex` 或 `.bin` 文件（通常在 `Objects/` 或 `Listings/` 同级目录）
2. 确认 ST-Link 连接：
   ```
   STM32_Programmer_CLI.exe -c port=SWD
   ```
3. 执行烧录：
   ```
   STM32_Programmer_CLI.exe -c port=SWD -w <hex路径> 0x08000000 -v -rst
   ```
4. 解析烧录输出，确认 "Download verified successfully"
5. 如果烧录失败 → 进入「烧录失败处理」子流程

### Step 4：验证（Verify）
1. 提示用户观察板载现象（LED 闪烁、串口输出等）
2. 如果用户提供了串口日志或描述，分析运行状态
3. 如果配置了串口工具，主动读取串口输出（如果用户授权）
4. 输出验证报告：
   ```
   ┌─────────────────────────────┐
   │  编译烧录验证报告            │
   ├─────────────────────────────┤
   │ 编译结果: 成功 (0E, 0W)      │
   │ 代码大小: Flash XKB, RAM YB  │
   │ 烧录结果: 成功               │
   │ 设备复位: 已执行             │
   │ 串口输出: "SystemInit OK"   │
   └─────────────────────────────┘
   ```

## 子流程：编译错误处理

### 错误分类与自动修复策略
| 错误类型 | 特征 | 自动修复 | 需用户确认 |
|----------|------|----------|-----------|
| 缺少头文件 | `xxx.h: No such file` | 检查 Include Path 配置 | ✅ |
| 未定义符号 | `undefined reference` | 检查是否缺少 .c 文件或库 | ✅ |
| 语法错误 | `expected ';'` | 定位行号，给出修复建议 | ❌ |
| 类型不匹配 | `incompatible pointer type` | 检查函数声明与定义 | ✅ |
| 启动文件不匹配 | `startup_xx.s` 错误 | 检查 Device 设置与启动文件 | ✅ |
| Flash/RAM 溢出 | `region RAM overflowed` | 优化变量或调整 scatter 文件 | ✅ |

### 处理原则
- **先定位**：提取错误所在的文件名和行号
- **再分类**：根据错误关键词判断类型
- **后建议**：给出具体修复代码或配置修改方案
- **不擅自修改**：除非用户明确说"自动修复"，否则只给建议

## 子流程：烧录失败处理

### 排查清单（按优先级）
1. **ST-Link 驱动**：设备管理器中是否有 "STMicroelectronics STLink dongle"
2. **接线**：SWDIO/SWCLK/VCC/GND 是否接触良好
3. **BOOT0 电平**：烧录时是否为低电平（运行模式）或高电平（System Memory）
4. **芯片供电**：目标板是否上电，电压是否稳定
5. **芯片锁死**：是否之前设置了读保护（RDP）？需要先解除
6. **Keil 占用**：Keil 是否正在调试占用 ST-Link？先关闭 Keil

### 自动诊断命令
```
# 检查 ST-Link 连接
STM32_Programmer_CLI.exe -c port=SWD

# 检查芯片信息（确认是否连接成功）
STM32_Programmer_CLI.exe -c port=SWD -r

# 解除读保护（谨慎！会擦除 Flash）
STM32_Programmer_CLI.exe -c port=SWD -ob RDP=0xAA
```

## 输出格式
- 每个步骤用 `✅/❌/⚠️` 标记状态
- 编译错误必须列出：文件、行号、错误内容、修复建议
- 烧录失败必须给出排查清单，按优先级排序
- 最后给出「下一步建议」
