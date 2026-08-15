# STM32 AI 开发工作流 —— 可移植配置包

> **双平台支持**：本工具包同时适配 **Claude Code**（默认，见 [USAGE.md](USAGE.md)）和
> **DeepSeek Harness (DSH)**（`python install.py --dsh`，见 [USAGE_DSH.md](USAGE_DSH.md)）。

## 这是什么？

这是你的 **STM32 + AI 开发环境完整配置包**。换电脑时，把这个文件夹复制过去，**双击 `install.py`**，几分钟后全部恢复。

包含四层配置：

- **Skills** —— AI 的开发技能（编译烧录、调试分析、代码审查、外设配置、新建工程、记录踩坑）
- **Commands** —— 常用斜杠命令（`/build`、`/flash`、`/serial`、`/review`、`/newproject` 等；DSH 下转为同名 skill）
- **MCP Server** —— 让 AI 能直接调用 Keil 编译、STM32CubeProgrammer 烧录、串口收发
- **Hooks + 模板** —— 强制编译验证（Claude Code）、记忆自动注入、新工程脚手架（DSH 无 hooks，靠 skill 铁律约束）

## 目录结构

```
stm32-ai-toolkit/
├── install.py                    ← 双击运行，一键安装/恢复（--dsh 装到 ~/.dsh）
├── uninstall.py                  ← 一键卸载（默认移到备份，--purge 彻底清理；--dsh 卸载 DSH 配置）
├── backup.py                     ← 把 ~/.claude 的配置同步回本包（备份）
├── new_project.py                ← 新工程脚手架（默认 CubeMX 无头生成，记忆文件生成到 .dsh/memory）
├── mcu_knowledge.py              ← STM32 型号知识库（解析型号→核心/内存/启动文件，预览用）
├── make_ioc.py                   ← 型号 → 最小 .ioc（RCC 时钟块取自官方示例/内置模板，全家族通用）
├── cubemx_gen.py                 ← STM32CubeMX 无头生成（固件包预检 / 生成 / 清理残留进程）
├── README.md                     ← 本文件
├── USAGE_DSH.md                  ← DSH（DeepSeek Harness）使用说明
├── global_claude.md              ← 你的全局开发规范（Claude Code 版，装到 ~/.claude/CLAUDE.md）
├── dsh_global.md                 ← 你的全局开发规范（DSH 版，装到 ~/.dsh/AGENTS.md）
├── _cmdutil.py                   ← 脚本共用模块（编码/子进程封装）
├── install_summary_{claude,dsh}.json ← 安装摘要（安装后自动生成，按轨分文件）
├── skills/                       ← AI Skills（每个含 SKILL.md，共 6 个）
│   ├── stm32-build-flash-debug/  stm32-code-review/
│   ├── stm32-debug-analyze/      stm32-peripheral-config/
│   └── stm32-new-project/        stm32-known-issues/
├── commands/                     ← 斜杠命令（装到 ~/.claude/commands/；DSH 下转为同名 skill）
│   ├── build.md  flash.md  serial.md
│   ├── review.md  newissue.md  newproject.md
├── templates/
│   └── project/                  ← new_project.py 的工程骨架模板
│       ├── CLAUDE.md.template    （DSH 兼容：显式引用 .dsh/memory，无 @ 导入）
│       ├── settings.json.template（hooks 配置，仅 Claude Code；DSH 默认不生成）
│       ├── hardware.yaml.blank
│       ├── memory/               ← architecture / pin_usage / known_issues / session_log
│       ├── src/  inc/  MDK-ARM/
├── mcp/
│   ├── stm32_mcp_server.py       ← MCP Server（15 个工具）
│   └── register_mcp.py
└── scripts/
    ├── serial_live.py            ← 独立串口实时监控
    └── hooks/                    ← 编译闸门 / 记忆注入 / 会话日志等（仅 Claude Code）
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
4. 等待完成，按下方清单验证

### 方式二：让 AI 帮你恢复

在新电脑上打开 Claude Code，直接说：

> **"帮我恢复 STM32 开发环境，工具包在 D:\stm32-ai-toolkit"**

AI 会自动：
1. 读取本 README 了解结构
2. 运行 `install.py`
3. 验证 `claude mcp list` 输出
4. 用 `new_project.py` 生成一个测试工程并编译验证通路

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

### 方式四：DSH（DeepSeek Harness）

用 DSH 时，把配置装到 `~/.dsh`（不碰 `~/.claude`）：

```bash
python install.py --dsh       # AGENTS.md + 6 skills + MCP 注册（~/.dsh/mcp-servers.json）
python uninstall.py --dsh     # 卸载（移到备份，--purge 彻底清理）
```

DSH 原生自动加载：
- **全局规范** `~/.dsh/AGENTS.md`（新会话生效）
- **项目级** `CLAUDE.md` / `AGENTS.md`（工程根目录自动加载，已验证）
- **6 个 skill**（设置 → Skill 管理，可开关/删除）
- **MCP**（设置 → MCP 管理，动态挂载即时生效）

详细用法见 [USAGE_DSH.md](USAGE_DSH.md)。

## 安装后验证清单

```bash
# Claude Code 模式
# 1. 全局规范
ls %USERPROFILE%\.claude\CLAUDE.md

# 2. Skills（6 个真 skill，含 SKILL.md）
ls %USERPROFILE%\.claude\skills\
#   应看到 stm32-build-flash-debug / stm32-code-review / stm32-debug-analyze /
#          stm32-peripheral-config / stm32-new-project / stm32-known-issues

# 3. Commands（6 个斜杠命令）
ls %USERPROFILE%\.claude\commands\
#   应看到 build.md flash.md serial.md review.md newissue.md newproject.md

# 4. MCP Server
claude mcp list
#   应看到: stm32-toolkit: stdio — Connected

# 5. 启动对话测试
claude
#   说: "编译当前工程"  （若在带 hooks 的工程里，AI 会自动调用 keil_build）
```

```bash
# DSH 模式验证（装到 ~/.dsh）
# 1. 全局指令
ls %USERPROFILE%\.dsh\AGENTS.md

# 2. Skills（6 个，含 SKILL.md）
ls %USERPROFILE%\.dsh\skills\
#   应看到 stm32-build-flash-debug / stm32-code-review / stm32-debug-analyze /
#          stm32-peripheral-config / stm32-new-project / stm32-known-issues

# 3. MCP 注册表
ls %USERPROFILE%\.dsh\mcp-servers.json
#   或在 DSH 设置 → MCP 管理 看到 stm32-toolkit（enabled）

# 4. 打开 DSH 对话测试
#   说: "编译当前工程" → 模型调用 mcp__stm32-toolkit__keil_build
```

## 日常更新

当你修改了规范、Skill 或命令，记得同步回这个文件夹：

```bash
# 从 ~/.claude 同步回工具包（更新备份），先预览
python backup.py --dry-run
# 确认无误后执行（默认方向：~/.claude → 本包）
python backup.py
```

然后提交到 Git 或复制到网盘。

## 常见问题

**Q: install.py 双击没反应？**
A: 右键 → 打开方式 → Python。如果提示没有 Python，先安装 Python 3.8+。

**Q: Keil 装在了 D 盘，检测不到？**
A: 在环境变量中添加 `KEIL_PATH=D:\Keil_v5\UV4\UV4.exe`，然后重新运行 install.py。

**Q: MCP 注册失败？**
A: 确认 `claude` 命令可用（在 CMD 中输入 `claude --version`）。如果不行，先安装 Node.js 和 Claude Code CLI。

**Q: 依赖装不上（镜像源没有 fastmcp）？**
A: install.py 会先用你配置的 pip 镜像，失败后自动回退官方 PyPI（`-i https://pypi.org/simple`）。若你配置的镜像较慢，也可手动：
   `pip install -i https://pypi.org/simple fastmcp pyserial`

**Q: 注册时报 FileNotFoundError: claude？**
A: 这是 Windows 上 npm 的 `claude.CMD` 批处理 shim 无法被 subprocess 直接启动的已知问题，已修复（run_cmd 自动用 `cmd /c` 启动）。若仍出现，检查 claude 是否在 PATH 里。

**Q: 我只想恢复部分配置？**
A: 用 `python install.py --no-mcp` 跳过 MCP 注册，`--no-deps` 跳过 pip 依赖；对已有工程补装 AI 辅助层用 `python install.py --project <路径>`。

**Q: 工具包移动后工程 hooks 不生效了？**
A: hooks 路径是绝对路径。移动工具包 / 换电脑 clone 后，重跑 `python install.py --repair <工程目录>` 刷新即可（只重写 settings.json，带备份，不碰 CLAUDE.md）。

**Q: 想卸载重装（验证/试验阶段）？**
A: 一键卸载，默认把配置移到备份目录（可恢复），`--purge` 才彻底清理：

```bash
python uninstall.py            # 卸载（交互确认，配置移到 ~/.claude/.stm32-toolkit-uninstalled/<时间戳>/）
python uninstall.py --purge    # 卸载并删除全部备份，干净重装
python install.py              # 重新安装
```
