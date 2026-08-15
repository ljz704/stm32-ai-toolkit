---
name: stm32-build-flash-debug
description: STM32/Keil 工程编译-烧录-验证闭环。当用户要求编译构建 Keil 工程、clean build、修复编译错误、烧录下载固件、验证运行，或提到 编译 烧录 build flash 下载程序 重新编译 时使用。按 keil_build 到 stlink_flash 到串口验证顺序执行，强制展示编译结果与串口原始数据。
---

# STM32 编译-烧录-验证闭环

## 核心原则
1. **每生成或修改超过 5 行代码后，必须调用 `keil_build` 编译验证**
2. **调用任何串口工具后，必须先用 \`\`\`text 代码块展示原始数据，再分析**
3. **严禁只给结论不展示原始数据**

## 执行流程

### Step 1：定位工程
1. 扫描当前目录及子目录，查找 `.uvprojx` 文件
2. 如果找到多个，列出供用户选择；如果只有一个，直接使用
3. 确认工程路径后，读取同目录下的 `CLAUDE.md`（DSH 亦支持 AGENTS.md）和记忆文件 `.dsh/memory/known_issues.md`（旧工程可能是 `.claude/memory/known_issues.md`，同样有效）

### Step 2：编译（Build）
1. 调用 `keil_build` 执行 Keil 编译（需要 clean build 时传 `rebuild=True`）
2. **展示编译结果**：必须输出 `display_for_user` 字段的内容，不得省略
3. 结果分类：
   - **0 Error, 0 Warning** → 进入 Step 3
   - **有 Warning** → 列出所有 Warning，询问是否继续
   - **有 Error** → 进入「编译错误处理」子流程，**停止后续步骤**

### Step 3：烧录（Flash）
1. 调用 `find_build_output` 自动查找编译输出的 `.hex` 或 `.bin`
2. 调用 `probe_info` 确认 ST-Link 连接
3. 调用 `stlink_flash` 执行烧录，**展示 `display_for_user` 结果**
4. 烧录失败 → 进入「烧录失败处理」子流程

### Step 4：验证（Verify）
1. 提示用户观察板载现象（LED 闪烁、串口输出等）
2. 如果用户要求读取串口：
   - **方式 A（单次）**：调用 `serial_read`，展示原始数据后分析
   - **方式 B（持续监控）**：调用 `serial_monitor_start`，等待用户说"好了"，再调用 `serial_monitor_read` 展示缓存数据
3. 输出验证报告：
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

## 串口数据展示规范（强制）

调用 `serial_read`、`serial_send`、`serial_monitor_read` 后，必须：

```markdown
### 原始串口数据
```text
[这里粘贴完整的 response 内容，不要省略、不要截断]
```

### 分析
[基于上述数据给出结论]
```

**严禁**：
- ❌ "串口收到了一些数据，看起来正常"
- ❌ "数据显示电压是 3.3V"（没有展示原始数据支撑）

**必须**：
- ✅ 先展示完整原始数据
- ✅ 再逐行解读关键值
- ✅ 如果有异常，指出具体哪一行、哪个值异常

## 编译错误处理子流程

### 错误分类与自动修复策略

特征列以 ARMCC v5.06 输出为准。

| 错误类型 | Keil AC5 特征输出 | 自动修复 | 需用户确认 |
|----------|------------------|----------|-----------|
| 缺少头文件 | `error: #5: cannot open source input file "xxx.h": No such file or directory` | 检查 Include Path 配置 | ✅ |
| 未定义符号（编译期） | `error: #20: identifier "xxx" is undefined` | 检查声明 / 是否漏包含头文件 | ✅ |
| 未定义符号（链接期） | `Error: L6218E: Undefined symbol xxx (referred from xxx.o)` | 检查是否缺少 .c 文件或库 | ✅ |
| 语法错误 | `error: #65: expected a ";"` / `error: #29: expected an expression` | 定位行号，给出修复建议 | ❌ |
| 类型不匹配 | `error: #167: argument of type "x" is incompatible with parameter of type "y"` | 检查函数声明与定义 | ✅ |
| Flash/RAM 溢出 | `Error: L6406E: No space in execution regions` / `L6220E: Execution region ... too small` | 优化变量或调整 scatter 文件 | ✅ |
| 启动文件不匹配 | 汇编报 `A1xxxE`，或链接缺 `Reset_Handler`（`L6218E`） | 检查 Device 设置与启动文件 | ✅ |

### 处理原则
- **先定位**：提取错误所在的文件名和行号
- **再分类**：根据错误关键词判断类型
- **后建议**：给出具体修复代码或配置修改方案
- **不擅自修改**：除非用户明确说"自动修复"，否则只给建议

## 烧录失败处理子流程

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
- 串口数据必须先展示原始输出，再分析
- 烧录失败必须给出排查清单，按优先级排序
- 最后给出「下一步建议」
