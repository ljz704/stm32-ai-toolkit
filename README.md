# STM32 AI 开发工作流 —— 可移植配置包

## 这是什么？

这是你的 **STM32 + Claude Code 开发环境完整配置包**。换电脑时，把这个文件夹复制过去，**双击 `install.py`**，5 分钟后全部恢复。

## 目录结构

```
stm32-ai-toolkit/
├── install.py                    ← 双击运行，一键恢复
├── README.md                     ← 本文件
├── global_claude.md              ← 你的全局开发规范
├── install_summary.json          ← 安装摘要（安装后自动生成）
├── templates/                    ← 项目模板
│   ├── f1xx_general.md
│   └── f3xx_digital_power.md
├── skills/                       ← Claude Skills
│   ├── build_flash_debug.md
│   ├── code_review.md
│   ├── debug_analyze.md
│   └── peripheral_config.md
└── mcp/                          ← MCP Server
    ├── stm32_mcp_server.py
    └── register_mcp.py
```

## 换电脑恢复步骤

### 方式一：双击运行（推荐）

1. 把整个 `stm32-ai-toolkit` 文件夹复制到新电脑（U盘/网盘/Git）
2. 确保已安装：
   - Python 3.8+（官网下载，安装时勾选 "Add to PATH"）
   - Keil MDK-ARM
   - STM32CubeProgrammer（ST 官网免费下载）
   - Claude Code CLI（`npm install -g @anthropic-ai/claude-code`）
3. **双击 `install.py`**
4. 等待完成，按提示验证

### 方式二：让 AI 帮你恢复

在新电脑上打开 Claude Code，直接说：

> **"帮我恢复 STM32 开发环境，工具包在 D:\stm32-ai-toolkit"**

AI 会自动：
1. 读取本 README 了解结构
2. 运行 `install.py`
3. 验证 `claude mcp list` 输出
4. 测试编译一个示例工程

### 方式三：Git 同步（高级）

把这个文件夹推送到你的 GitHub 私有仓库：

```bash
cd stm32-ai-toolkit
git init
git add .
git commit -m "STM32 AI toolkit backup"
git remote add origin https://github.com/<你的账号>/stm32-ai-toolkit.git
git push -u origin main
```

新电脑：
```bash
git clone https://github.com/<你的账号>/stm32-ai-toolkit.git
cd stm32-ai-toolkit
python install.py
```

## 安装后验证清单

运行 `install.py` 后，依次验证：

```bash
# 1. 检查全局规范
ls %USERPROFILE%\.claude\CLAUDE.md

# 2. 检查模板
ls %USERPROFILE%\.claude\templates\

# 3. 检查 Skills
ls %USERPROFILE%\.claude\skills\

# 4. 检查 MCP Server
claude mcp list
# 应该看到: stm32-toolkit: stdio — Connected

# 5. 启动对话测试
claude
# 说: "编译当前工程"
```

## 日常更新

当你修改了规范或增加了新 Skill，记得同步回这个文件夹：

```bash
# 从系统目录同步回工具包（更新备份）
copy %USERPROFILE%\.claude\CLAUDE.md global_claude.md
copy %USERPROFILE%\.claude\templates\* templates\
copy %USERPROFILE%\.claude\skills\* skills\
```

然后提交到 Git 或复制到网盘。

## 常见问题

**Q: install.py 双击没反应？**
A: 右键 → 打开方式 → Python。如果提示没有 Python，先安装 Python 3.8+。

**Q: Keil 装在了 D 盘，检测不到？**
A: 在环境变量中添加 `KEIL_PATH=D:\Keil_v5\UV4\UV4.exe`，然后重新运行 install.py。

**Q: MCP 注册失败？**
A: 确认 `claude` 命令可用（在 CMD 中输入 `claude --version`）。如果不行，先安装 Node.js 和 Claude Code CLI。

**Q: 我只想恢复部分配置？**
A: 用文本编辑器打开 `install.py`，注释掉不需要的步骤（如 `# install_templates()`），然后运行。
