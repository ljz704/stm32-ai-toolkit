#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STM32 AI 开发工作流 —— 一键安装/恢复脚本
============================================
换电脑后，把这个文件夹复制到新电脑，双击运行 install.py，
自动完成所有配置，无需手动编辑任何文件。

也可以对 Claude 说："帮我恢复 STM32 开发环境"
AI 会调用此脚本自动执行。

用法:
    python install.py                        # 完整安装（全局配置/Skills/Commands/工具链/MCP）
    python install.py --dsh                  # DSH 模式：装到 ~/.dsh（AGENTS.md/6 skills/MCP），适配 DeepSeek Harness
    python install.py --project <已有工程>   # 只对已有工程补装 AI 辅助层（委托 new_project.py）
    python install.py --no-mcp               # 跳过 MCP 注册
    python install.py --no-deps              # 跳过 pip 依赖安装
    python install.py --yes                  # 跳过所有 input 确认（双击运行时默认无交互）
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 让脚本从其他目录运行时也能 import _cmdutil
SCRIPT_DIR = Path(__file__).parent.resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _cmdutil import fix_console_encoding, run_cmd  # noqa: E402

# ===================== 颜色输出 =====================
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    RESET = "\033[0m"

def ok(msg):    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")
def warn(msg):  print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")
def err(msg):   print(f"{Colors.RED}❌ {msg}{Colors.RESET}")
def info(msg):  print(f"{Colors.CYAN}ℹ️  {msg}{Colors.RESET}")

# ===================== 路径常量 =====================
USER_HOME = Path.home()
CLAUDE_DIR = USER_HOME / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
COMMANDS_DIR = CLAUDE_DIR / "commands"
MCP_SERVER = SCRIPT_DIR / "mcp" / "stm32_mcp_server.py"
MCP_SERVER_NAME = "stm32-toolkit"
MCP_SERVER_MARKER = "serial_monitor_start"  # 校验权威版 server 已含 serial_monitor_* 工具

# ── DSH（DeepSeek Harness）目标：配置装到 ~/.dsh 而非 ~/.claude ──
# 指令文件：~/.dsh/AGENTS.md（DSH 原生用户全局指令，dsh-agent-instructions 自动加载）
# Skills：  ~/.dsh/skills/（DSH 官方 skill 系统 + 魔改插件 skill 管理共用目录）
# MCP：     ~/.dsh/mcp-servers.json（魔改插件 dsh-host-files 动态挂载，设置界面可见可管理）
DSH_DIR = USER_HOME / ".dsh"
DSH_AGENTS = DSH_DIR / "AGENTS.md"
DSH_SKILLS_DIR = DSH_DIR / "skills"
DSH_MCP_STATE = DSH_DIR / "mcp-servers.json"
DSH_GLOBAL_SRC = SCRIPT_DIR / "dsh_global.md"  # 工具包内 DSH 版全局规范源文件

# 本工具包安装的技能/命令清单：uninstall.py 按此精确卸载，不误删其他同目录内容
KNOWN_SKILLS = [
    "stm32-build-flash-debug",
    "stm32-code-review",
    "stm32-debug-analyze",
    "stm32-peripheral-config",
    "stm32-new-project",
    "stm32-known-issues",
]
KNOWN_COMMANDS = ["build.md", "flash.md", "serial.md", "review.md", "newissue.md", "newproject.md"]

# ===================== 步骤 1: 检查 Python 环境 =====================
def check_python():
    info("检查 Python 环境...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        err("需要 Python 3.8+，当前版本: {}.{}.{}".format(version.major, version.minor, version.micro))
        sys.exit(1)
    ok(f"Python {version.major}.{version.minor}.{version.micro}")

# ===================== 工具: 覆盖前备份已有配置 =====================
# 备份统一移到 ~/.claude/.stm32-toolkit-backups/<时间戳>/（skills/commands 目录之外）。
# 不能原地生成 <name>.bak_<时间戳>：技能目录会被 Claude 当技能加载，命令文件会污染目录。
BACKUP_DIR = CLAUDE_DIR / ".stm32-toolkit-backups"

def _backup_existing(path: Path, backup_root: Path = None):
    """覆盖前把已有文件/目录移动到备份目录，避免破坏原配置。用 move 而非 copy+bak 后缀。

    backup_root 缺省为 ~/.claude/.stm32-toolkit-backups（Claude 模式）；
    DSH 模式（--dsh）传 ~/.dsh/.stm32-toolkit-backups，不污染 ~/.claude。
    """
    if not path.exists():
        return None
    root = backup_root or BACKUP_DIR
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak_dir = root / stamp
    try:
        bak_dir.mkdir(parents=True, exist_ok=True)
        dst = bak_dir / path.name
        shutil.move(str(path), str(dst))
        info(f"已备份原有 {path.name} → {dst}")
        return dst
    except OSError as e:
        warn(f"备份 {path.name} 失败: {e}，继续安装")
        return None

# ===================== 步骤 2: 安装 Python 依赖 =====================
def install_deps():
    info("检查并安装 Python 依赖...")
    deps = ["fastmcp", "pyserial"]
    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("pyserial", "serial"))
        except ImportError:
            missing.append(dep)

    if not missing:
        ok("所有 Python 依赖已就绪")
        return True

    warn(f"缺少依赖: {', '.join(missing)}，正在安装...")

    # 依次尝试：用户配置的默认源 → 阿里云（国内全量镜像）→ 官方 PyPI。
    # 清华/USTC 等镜像可能缺 fastmcp；官方 PyPI 国内直连常超时。
    bases = [
        [sys.executable, "-m", "pip", "install"],  # 用户 pip 配置的默认源
        [sys.executable, "-m", "pip", "install", "-i", "https://mirrors.aliyun.com/pypi/simple/"],
        [sys.executable, "-m", "pip", "install", "-i", "https://pypi.org/simple"],
    ]
    attempts = [base + missing for base in bases]
    labels = ["默认镜像源", "阿里云镜像", "官方 PyPI"]
    last = None
    for idx, pip_cmd in enumerate(attempts):
        if idx > 0:
            warn(f"{labels[idx-1]} 安装失败，改用{labels[idx]}...")
        result = run_cmd(pip_cmd, timeout=300)
        last = (result, pip_cmd)
        if result.ok:
            ok(f"已安装: {', '.join(missing)}")
            return True

    result, pip_cmd = last
    err(f"安装失败: {result.error or result.combined}")
    info(f"请手动运行: {' '.join(pip_cmd)}")
    return False

# ===================== 步骤 3: 安装全局 CLAUDE.md =====================
def install_global_claude_md():
    info("安装全局 CLAUDE.md...")
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

    src = SCRIPT_DIR / "global_claude.md"
    dst = CLAUDE_DIR / "CLAUDE.md"

    if not src.exists():
        err(f"未找到 {src}")
        return False

    _backup_existing(dst)
    shutil.copy2(src, dst)
    ok(f"全局规范已安装: {dst}")
    return True

# ===================== 步骤 4: 安装 Skills =====================
# 不再平铺拷贝 .md，改为递归安装"真 skill 目录"（含 SKILL.md 的目录整体拷贝）。
def install_skills():
    info("安装 Skills...")
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    src_dir = SCRIPT_DIR / "skills"
    if not src_dir.exists():
        warn("skills 目录不存在，跳过")
        return True

    count = 0
    for d in sorted(src_dir.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "SKILL.md").exists():
            continue
        dst = SKILLS_DIR / d.name
        _backup_existing(dst)  # 已有同名词目先移出备份，避免覆盖用户自定义 / 残留 .bak 污染
        shutil.copytree(d, dst, dirs_exist_ok=True)
        ok(f"Skill: {d.name}")
        count += 1

    if count == 0:
        warn(f"{src_dir} 下没有含 SKILL.md 的技能目录")
    return True

# ===================== 步骤 5: 安装 Commands =====================
def install_commands():
    info("安装 Commands...")
    COMMANDS_DIR.mkdir(parents=True, exist_ok=True)

    src_dir = SCRIPT_DIR / "commands"
    if not src_dir.exists():
        warn("commands 目录不存在，跳过")
        return True

    count = 0
    for f in sorted(src_dir.glob("*.md")):
        dst = COMMANDS_DIR / f.name
        _backup_existing(dst)  # 覆盖前备份同名旧命令
        shutil.copy2(f, dst)
        ok(f"Command: {f.name}")
        count += 1

    if count == 0:
        warn(f"{src_dir} 下没有 .md 命令文件")
    return True

# ===================== 步骤 6: 检查 Keil 和烧录工具 =====================
# 探测顺序（每个工具）：
#   1. 环境变量 KEIL_PATH / STM32_PROGRAMMER / CUBEMX_PATH（最优先，用户显式指定）
#   2. Windows 注册表（Keil Products\MDK、Uninstall DisplayIcon、App Paths）
#   3. 常见默认路径列表（C:/D 盘固定位置）
# 这样装在任意自定义位置也能自动找到，无需手动配置。

def _reg_read(path: str, value: str):
    """读 Windows 注册表值，失败返回 None。仅 Windows 生效。"""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            v, _ = winreg.QueryValueEx(k, value)
            return v if isinstance(v, str) else None
    except OSError:
        return None
    except ImportError:
        return None


def _reg_read_hkcu(path: str, value: str = ""):
    """读 HKCU 注册表（value 为空时读默认值），失败返回 None。仅 Windows 生效。"""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            if value:
                v, _ = winreg.QueryValueEx(k, value)
            else:
                v, _ = winreg.QueryValueEx(k, None)
            return v if isinstance(v, str) else None
    except OSError:
        return None
    except ImportError:
        return None


def _find_in_uninstall(display_match: str):
    """在卸载注册表列表（HKLM + WOW6432Node + HKCU）里按 DisplayName 找安装路径。

    返回 (install_location, display_icon)；两者都可能为 None。
    DisplayIcon 通常直接指向 exe/ico，可反推安装目录。
    """
    if os.name != "nt":
        return None, None
    try:
        import winreg
    except ImportError:
        return None, None
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, sub in roots:
        try:
            with winreg.OpenKey(hive, sub) as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, name) as subkey:
                            display = ""
                            icon = ""
                            loc = ""
                            try:
                                display, _ = winreg.QueryValueEx(subkey, "DisplayName")
                            except OSError:
                                pass
                            if not isinstance(display, str) or display_match not in display:
                                continue
                            try:
                                icon, _ = winreg.QueryValueEx(subkey, "DisplayIcon")
                            except OSError:
                                pass
                            try:
                                loc, _ = winreg.QueryValueEx(subkey, "InstallLocation")
                            except OSError:
                                pass
                            return (loc if isinstance(loc, str) and loc else None,
                                    icon if isinstance(icon, str) and icon else None)
                    except OSError:
                        continue
        except OSError:
            continue
    return None, None


def _probe_keil_from_registry():
    """从注册表定位 Keil UV4.exe。返回路径或 None。"""
    # 1. Keil Products\MDK 的 Path（如 D:\Keil_v5\ARM）→ 父目录下 UV4\UV4.exe
    for sub in (r"SOFTWARE\WOW6432Node\Keil\Products\MDK", r"SOFTWARE\Keil\Products\MDK"):
        base = _reg_read(sub, "Path")
        if base:
            cand = Path(base).parent / "UV4" / "UV4.exe"
            if cand.exists():
                return str(cand)
            # 个别版本 Path 直接指安装根
            cand2 = Path(base) / "UV4" / "UV4.exe"
            if cand2.exists():
                return str(cand2)
    # 2. 卸载列表 DisplayIcon 直接指向 UV4.exe
    _, icon = _find_in_uninstall("Keil")
    if icon:
        icon = icon.strip('"').split(",")[0]
        if icon.lower().endswith("uv4.exe") and Path(icon).exists():
            return icon
    return None


def _probe_programmer_from_registry():
    """从注册表定位 STM32_Programmer_CLI.exe。返回路径或 None。"""
    # 卸载列表 DisplayIcon 指向 <安装根>\util\Programmer.ico
    _, icon = _find_in_uninstall("STM32CubeProgrammer")
    if icon:
        icon = icon.strip('"').split(",")[0]
        root = Path(icon).parent.parent  # util/.. → 安装根
        cand = root / "bin" / "STM32_Programmer_CLI.exe"
        if cand.exists():
            return str(cand)
    return None


def _probe_cubemx_from_registry():
    """从注册表定位 STM32CubeMX.exe。返回路径或 None。"""
    # 1. App Paths（HKCU/HKLM）默认值直接指向 exe
    for hive, sub in (("hkcu", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\STM32CubeMX.exe"),
                      ("hklm", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\STM32CubeMX.exe"),
                      ("hklm", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\STM32CubeMX.exe")):
        v = _reg_read_hkcu(sub) if hive == "hkcu" else _reg_read(sub, "")
        if v and v.strip('"').lower().endswith("stm32cubemx.exe") and Path(v.strip('"')).exists():
            return v.strip('"')
    # 2. 卸载列表（HKCU 常见，安装器按用户级装）
    loc, icon = _find_in_uninstall("STM32CubeMX")
    for probe in (loc, icon):
        if probe:
            probe = probe.strip('"').split(",")[0]
            if probe.lower().endswith("stm32cubemx.exe") and Path(probe).exists():
                return probe
            p = Path(probe)
            if p.is_dir():
                cand = p / "STM32CubeMX.exe"
                if cand.exists():
                    return str(cand)
    return None


def check_toolchain():
    info("检查工具链...")

    # ── Keil ──
    keil_found = None
    keil_env = os.environ.get("KEIL_PATH")
    if keil_env:
        keil_found = Path(keil_env)
        ok(f"Keil (KEIL_PATH 环境变量): {keil_found}")
    else:
        reg = _probe_keil_from_registry()
        if reg:
            keil_found = Path(reg)
            ok(f"Keil (注册表): {keil_found}")
        else:
            keil_paths = [
                Path(r"C:\Keil_v5\UV4\UV4.exe"),
                Path(r"D:\Keil_v5\UV4\UV4.exe"),
                Path(r"C:\Keil\UV4\UV4.exe"),
            ]
            for p in keil_paths:
                if p.exists():
                    keil_found = p
                    break
        if keil_found:
            ok(f"Keil: {keil_found}")
        else:
            warn("Keil 未找到，请确认已安装 Keil MDK-ARM")
            info("  如果安装在其他位置，请在环境变量中设置 KEIL_PATH")

    # ── STM32CubeProgrammer ──
    prog_found = None
    prog_env = os.environ.get("STM32_PROGRAMMER")
    if prog_env:
        prog_found = Path(prog_env)
        ok(f"STM32CubeProgrammer (STM32_PROGRAMMER 环境变量): {prog_found}")
    else:
        reg = _probe_programmer_from_registry()
        if reg:
            prog_found = Path(reg)
            ok(f"STM32CubeProgrammer (注册表): {prog_found}")
        else:
            prog_paths = [
                Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"),
                Path(r"D:\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"),
            ]
            for p in prog_paths:
                if p.exists():
                    prog_found = p
                    break
        if prog_found:
            ok(f"STM32CubeProgrammer: {prog_found}")
        else:
            warn("STM32CubeProgrammer 未找到，请从 ST 官网下载安装")
            info("  下载地址: https://www.st.com/en/development-tools/stm32cubeprog.html")

    # ── STM32CubeMX ──
    cubemx_found = None
    cubemx_env = os.environ.get("CUBEMX_PATH")
    if cubemx_env:
        cubemx_found = Path(cubemx_env)
        ok(f"STM32CubeMX (CUBEMX_PATH 环境变量): {cubemx_found}")
    else:
        reg = _probe_cubemx_from_registry()
        if reg:
            cubemx_found = Path(reg)
            ok(f"STM32CubeMX (注册表): {cubemx_found}")
        else:
            cubemx_paths = [
                Path(r"D:\STM32CubeMX\STM32CubeMX.exe"),
                Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"),
                Path(r"C:\STM32CubeMX\STM32CubeMX.exe"),
            ]
            for p in cubemx_paths:
                if p.exists():
                    cubemx_found = p
                    break
        if cubemx_found:
            ok(f"STM32CubeMX: {cubemx_found}")
        else:
            warn("STM32CubeMX 未找到（cubemx_generate 代码生成工具不可用）")
            info("  如果安装在其他位置，请在环境变量中设置 CUBEMX_PATH")

    return keil_found, prog_found, cubemx_found

# ===================== DSH 安装（--dsh 模式） =====================
# 目标：把本工作流适配到 DeepSeek Harness（DSH）——
#   ~/.dsh/AGENTS.md        全局指令（DSH 原生加载）
#   ~/.dsh/skills/          6 个 skill（官方 skill 系统 + 魔改插件管理共用）
#   ~/.dsh/mcp-servers.json MCP 注册（魔改插件动态挂载，即时生效）
def install_dsh():
    info("以 DSH 模式安装（~/.dsh）...")

    # DSH 模式的备份根：~/.dsh/.stm32-toolkit-backups（不污染 ~/.claude）
    dsh_backup_root = DSH_DIR / ".stm32-toolkit-backups"

    # 1. 全局指令 → ~/.dsh/AGENTS.md
    DSH_DIR.mkdir(parents=True, exist_ok=True)
    src = DSH_GLOBAL_SRC if DSH_GLOBAL_SRC.exists() else SCRIPT_DIR / "global_claude.md"
    dst = DSH_AGENTS
    if not src.exists():
        warn(f"未找到全局规范源文件（{DSH_GLOBAL_SRC.name} / global_claude.md），跳过 AGENTS.md")
    else:
        _backup_existing(dst, dsh_backup_root)
        shutil.copy2(str(src), str(dst))
        ok(f"全局指令已安装: {dst}")

    # 2. Skills → ~/.dsh/skills/（6 个，含 SKILL.md 的目录整体拷贝）
    DSH_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    src_dir = SCRIPT_DIR / "skills"
    count = 0
    if src_dir.exists():
        for d in sorted(src_dir.iterdir()):
            if not d.is_dir() or not (d / "SKILL.md").exists():
                continue
            target = DSH_SKILLS_DIR / d.name
            _backup_existing(target, dsh_backup_root)
            shutil.copytree(str(d), str(target), dirs_exist_ok=True)
            ok(f"Skill: {d.name}")
            count += 1
    if count == 0:
        warn(f"{src_dir} 下没有含 SKILL.md 的技能目录")
    else:
        info(f"已安装 {count} 个 skill 到 {DSH_SKILLS_DIR}（DSH 设置 → Skill 管理可见）")

    # 3. MCP → ~/.dsh/mcp-servers.json（魔改插件 dsh-host-files 的注册表格式）
    keil_path, prog_path, cubemx_path = check_toolchain()
    mcp_ok = _register_mcp_dsh(keil_path, prog_path, cubemx_path)

    # 4. 生成安装摘要（DSH 版，记录实际安装内容）
    try:
        dsh_skills = [d.name for d in sorted(DSH_SKILLS_DIR.iterdir()) if d.is_dir()] if DSH_SKILLS_DIR.exists() else []
        summary = {
            "install_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "dsh",
            "python": sys.executable,
            "dsh_dir": str(DSH_DIR),
            "agents_md": str(DSH_AGENTS),
            "keil_path": str(keil_path) if keil_path else None,
            "programmer_path": str(prog_path) if prog_path else None,
            "cubemx_path": str(cubemx_path) if cubemx_path else None,
            "mcp_registered": mcp_ok,
            "installed_skills": dsh_skills,
        }
        summary_file = SCRIPT_DIR / "install_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        ok(f"配置摘要已保存: {summary_file}")
    except OSError as e:
        warn(f"生成配置摘要失败: {e}")

    print()
    info("=" * 58)
    info("DSH 模式安装完成！")
    info("  - 全局指令: ~/.dsh/AGENTS.md（新会话自动加载）")
    info("  - Skills:   6 个（设置 → Skill 管理可见，可开关/删除）")
    info("  - MCP:      stm32-toolkit（设置 → MCP 管理可见，即时生效）")
    if mcp_ok:
        ok("MCP 已注册，可以在 DSH 对话中直接调用 mcp__stm32-toolkit__* 工具")
    else:
        warn("MCP 未写入注册表，请检查 ~/.dsh/mcp-servers.json 或手动在设置 → MCP 管理中添加")
    info("  - 命令:     /build /flash /serial /review /newissue /newproject")
    info("              已转为 skill（stm32-*），DSH 中直接描述需求即可触发")
    info("  - 工程模板: 新工程自动生成 .dsh/memory/ 记忆文件，CLAUDE.md 兼容 DSH 原生加载")
    info("=" * 58)
    return 0


def _register_mcp_dsh(keil_path=None, prog_path=None, cubemx_path=None) -> bool:
    """把 stm32-toolkit 写入 ~/.dsh/mcp-servers.json（魔改插件格式，动态挂载）。

    与 Claude Code 的 claude mcp add 不同，DSH 用 dsh-host-files 插件的注册表：
    {version:1, servers:[{id, serverName, transport, command, args, env, url, headers, enabled}]}
    插件启动时读取并动态挂载 dsh-mcp-client，无需重启 DSH、设置界面可见。
    """
    if not MCP_SERVER.exists():
        err(f"MCP Server 脚本未找到: {MCP_SERVER}")
        return False

    server = {
        "id": MCP_SERVER_NAME,
        "serverName": MCP_SERVER_NAME,
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(MCP_SERVER)],
        "env": {},
        "url": "",
        "headers": {},
        "enabled": True,
    }
    if keil_path:
        server["env"]["KEIL_PATH"] = str(keil_path)
    if prog_path:
        server["env"]["STM32_PROGRAMMER"] = str(prog_path)
    if cubemx_path:
        server["env"]["CUBEMX_PATH"] = str(cubemx_path)

    try:
        DSH_DIR.mkdir(parents=True, exist_ok=True)
        state = {"version": 1, "servers": []}
        if DSH_MCP_STATE.exists():
            try:
                import json as _json
                raw = _json.loads(DSH_MCP_STATE.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("servers"), list):
                    state = raw
            except Exception:
                warn(f"{DSH_MCP_STATE} 解析失败，将重建（旧配置保留在备份中）")
                _backup_existing(DSH_MCP_STATE, DSH_DIR / ".stm32-toolkit-backups")

        # 同 serverName 已存在 → 更新；否则追加
        replaced = False
        for i, s in enumerate(state["servers"]):
            if s.get("serverName") == MCP_SERVER_NAME:
                state["servers"][i] = server
                replaced = True
                break
        if not replaced:
            state["servers"].append(server)

        DSH_MCP_STATE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        ok(f"MCP 已写入 {DSH_MCP_STATE}")
        info("  动态挂载由 dsh-host-files 插件完成；若 DSH 已在运行，设置 → MCP 管理 立即可见")
        return True
    except OSError as e:
        err(f"写入 MCP 注册表失败: {e}")
        return False


# ===================== 步骤 7: 注册 MCP Server =====================
def register_mcp(keil_path=None, prog_path=None, cubemx_path=None):
    info("注册 MCP Server...")

    # 检查 claude 命令
    claude_cmd = shutil.which("claude")
    if not claude_cmd:
        warn("未找到 claude 命令，跳过 MCP 注册")
        info("  请确保 Claude Code CLI 已安装并加入 PATH（npm install -g @anthropic-ai/claude-code）")
        return False

    if not MCP_SERVER.exists():
        err(f"MCP Server 脚本未找到: {MCP_SERVER}")
        return False

    # 校验权威版 server：必须已合并 serial_monitor_* 工具，否则版本不对
    try:
        server_text = MCP_SERVER.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        err(f"读取 {MCP_SERVER} 失败: {e}")
        return False
    if MCP_SERVER_MARKER not in server_text:
        warn(f"{MCP_SERVER.name} 版本不对：未包含 {MCP_SERVER_MARKER} 工具，跳过注册")
        info("  请先把 serial_monitor_* 工具合并进权威版 server，再重新运行本脚本")
        return False

    # 先移除旧注册（未注册过时返回非零属正常，仅当命令本身报错/超时才提示）
    remove = run_cmd(["claude", "mcp", "remove", MCP_SERVER_NAME], timeout=60)
    if remove.error:
        warn(f"移除旧注册失败: {remove.error}（继续注册）")
    elif remove.timed_out:
        warn("移除旧注册超时（继续注册）")

    # 关键修复：把检测到的工具路径用 -e KEY=VALUE 烤进注册配置，
    # 让 MCP server 运行时能读到，修复原版 env=env 传不到 server 的问题。
    add_cmd = [
        "claude", "mcp", "add",
        "--scope", "user",
        "--transport", "stdio",
        MCP_SERVER_NAME,
    ]
    if keil_path:
        add_cmd += ["-e", f"KEIL_PATH={keil_path}"]
    if prog_path:
        add_cmd += ["-e", f"STM32_PROGRAMMER={prog_path}"]
    if cubemx_path:
        add_cmd += ["-e", f"CUBEMX_PATH={cubemx_path}"]
    add_cmd += ["--", sys.executable, str(MCP_SERVER)]

    result = run_cmd(add_cmd)
    if result.error:
        err(f"注册失败: {result.error}")
        info(f"请手动运行: {' '.join(add_cmd)}")
        return False
    if result.timed_out:
        err("注册超时（claude 命令 60s 内未返回，可能网络或登录问题）")
        info(f"请手动运行: {' '.join(add_cmd)}")
        return False
    if result.returncode != 0:
        err(f"注册失败:\n{result.combined}")
        info(f"请手动运行: {' '.join(add_cmd)}")
        return False

    ok("MCP Server 注册成功")
    info(f"  验证: claude mcp get {MCP_SERVER_NAME}")
    return True

# ===================== 步骤 8: 生成配置摘要 =====================
def generate_summary(keil_path, prog_path, mcp_ok, cubemx_path=None):
    info("生成配置摘要...")

    installed_skills = [d.name for d in sorted(SKILLS_DIR.iterdir()) if d.is_dir()] if SKILLS_DIR.exists() else []
    installed_commands = [f.name for f in sorted(COMMANDS_DIR.glob("*.md"))] if COMMANDS_DIR.exists() else []

    summary = {
        "install_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.executable,
        "claude_dir": str(CLAUDE_DIR),
        "keil_path": str(keil_path) if keil_path else None,
        "programmer_path": str(prog_path) if prog_path else None,
        "cubemx_path": str(cubemx_path) if cubemx_path else None,
        "mcp_registered": mcp_ok,
        "installed_skills": installed_skills,
        "installed_commands": installed_commands,
    }

    summary_file = SCRIPT_DIR / "install_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    ok(f"配置摘要已保存: {summary_file}")
    return summary

# ===================== --project 模式: 对已有工程补装 AI 辅助层 =====================
def install_project(project_dir: Path):
    info(f"对已有工程补装 AI 辅助层: {project_dir}")

    np_script = SCRIPT_DIR / "new_project.py"
    if not np_script.exists():
        err(f"未找到 {np_script}，无法补装")
        return 1

    cmd = [sys.executable, str(np_script), "--dir", str(project_dir), "--existing", "--yes"]
    result = run_cmd(cmd, timeout=300)
    if result.error or result.timed_out:
        err(f"补装失败: {result.error or result.combined}")
        return 1
    if result.returncode != 0:
        err(f"补装失败:\n{result.combined}")
        return 1

    ok("补装完成")
    info("  已为该工程生成 .claude 配置 / SKILL.md 等 AI 辅助文件")
    info("  打开该工程后，让 Claude 读取工程内 .claude/CLAUDE.md 即可使用")
    return 0


def repair_project(project_dir: Path):
    """工具包移动后，刷新已有工程 hooks 路径到当前工具包（只动 settings.json）。"""
    info(f"刷新工程 hooks 路径: {project_dir}")

    np_script = SCRIPT_DIR / "new_project.py"
    if not np_script.exists():
        err(f"未找到 {np_script}，无法修复")
        return 1

    cmd = [sys.executable, str(np_script), "--dir", str(project_dir), "--repair", "--yes"]
    result = run_cmd(cmd, timeout=120)
    if result.error or result.timed_out:
        err(f"修复失败: {result.error or result.combined}")
        return 1
    if result.returncode != 0:
        err(f"修复失败:\n{result.combined}")
        return 1
    return 0

# ===================== 主流程 =====================
def main():
    # 必须先修编码：GBK 控制台打印 emoji/中文会崩
    fix_console_encoding()

    parser = argparse.ArgumentParser(
        prog="install.py",
        description="STM32 AI 开发工作流 —— 一键安装/恢复。默认安装全局配置、Skills、Commands、工具链检查并注册 MCP。",
    )
    parser.add_argument("--project", metavar="PATH",
                        help="不装全局配置，改为对指定已有工程补装 AI 辅助层（委托 new_project.py）")
    parser.add_argument("--repair", metavar="PATH",
                        help="工具包移动/换电脑后，刷新已有工程 hooks 路径到当前工具包（只动 settings.json，带备份）")
    parser.add_argument("--dsh", action="store_true",
                        help="DSH 模式：装到 ~/.dsh（AGENTS.md + 6 skills + mcp-servers.json），适配 DeepSeek Harness")
    parser.add_argument("--no-mcp", action="store_true", help="跳过 MCP 注册")
    parser.add_argument("--no-deps", action="store_true", help="跳过 pip 依赖安装")
    parser.add_argument("--yes", action="store_true",
                        help="跳过所有 input 确认（双击运行时默认无交互，可不用本参数）")
    args = parser.parse_args()

    if args.project:
        # --project 模式：只补装已有工程，不装全局配置、不注册 MCP
        check_python()
        rc = install_project(Path(args.project).resolve())
        sys.exit(rc)

    if args.repair:
        # --repair 模式：只刷新已有工程 hooks 路径，不装全局配置
        check_python()
        rc = repair_project(Path(args.repair).resolve())
        sys.exit(rc)

    if args.dsh:
        # --dsh 模式：装到 ~/.dsh，适配 DeepSeek Harness（不碰 ~/.claude）
        check_python()
        if not args.no_deps:
            install_deps()
        else:
            info("已跳过依赖安装（--no-deps）")
        sys.exit(install_dsh())

    print("=" * 60)
    print("  STM32 AI 开发工作流 —— 一键安装/恢复")
    print("=" * 60)
    print()

    check_python()

    if not args.no_deps:
        install_deps()
    else:
        info("已跳过依赖安装（--no-deps）")

    install_global_claude_md()
    install_skills()
    install_commands()

    keil_path, prog_path, cubemx_path = check_toolchain()

    if args.no_mcp:
        info("已跳过 MCP 注册（--no-mcp）")
        mcp_ok = False
    else:
        mcp_ok = register_mcp(keil_path, prog_path, cubemx_path)

    summary = generate_summary(keil_path, prog_path, mcp_ok, cubemx_path)

    print()
    print("=" * 60)
    print("  安装完成！")
    print("=" * 60)
    print()

    if mcp_ok:
        ok("全部就绪，可以开始使用 Claude Code 进行 STM32 开发了")
        print()
        print("建议测试命令:")
        print(f"  1. claude mcp get {MCP_SERVER_NAME}   # 查看 MCP Server 配置")
        print('  2. claude                   # 启动对话，说"编译当前工程"')
    else:
        warn("基础配置已完成，但 MCP Server 未注册")
        print("请检查 Claude Code CLI 是否安装，然后手动注册:")
        print(f"  claude mcp add --scope user --transport stdio {MCP_SERVER_NAME} -e KEIL_PATH=<路径> -- {sys.executable} {MCP_SERVER}")

    print()
    # --yes 或非交互（如双击/重定向）时末尾不阻塞
    if not args.yes and sys.stdin.isatty():
        try:
            input("按回车键退出...")
        except EOFError:
            pass

if __name__ == "__main__":
    main()
