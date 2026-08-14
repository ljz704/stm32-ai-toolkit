#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cubemx_gen.py —— STM32CubeMX 无头代码生成（实验脚本）
============================================================
从 .ioc 用 CubeMX 命令行无头生成完整工程（Core/Drivers/MDK-ARM 全套），
等价于 GUI 里点"生成代码"。

用法:
    python cubemx_gen.py <xxx.ioc>                 # 生成到 ioc 旁 cubemx_out/（安全，不碰原工程）
    python cubemx_gen.py <xxx.ioc> --out-dir DIR   # 生成到指定目录（先拷贝 ioc 进去）
    python cubemx_gen.py <xxx.ioc> --in-place      # 在 ioc 所在目录生成（覆盖 Core/Drivers，需确认）
    python cubemx_gen.py --check                   # 只检测 CubeMX 环境，不生成
    python cubemx_gen.py <xxx.ioc> --check-fw      # 只检测所需固件包是否就绪（不生成，缺包不卡）
    python cubemx_gen.py <xxx.ioc> --ensure-fw     # 尝试补齐固件包（zip 已下载→本地解压；否则提示去 GUI 装）
    python cubemx_gen.py <xxx.ioc> --json          # 安静模式：stdout 只输出一个 JSON 结果
                                                   #   （供 MCP/脚本子进程调用解析）

固件包预检（关键）:
    生成前先探测仓库（安装目录旁 STM32Cube/Repository 等常见位置）里是否已有
    目标家族的 STM32Cube_FW_<家族> 包。缺失 → 快速失败返回 missing_firmware，
    不再让 CubeMX 现场联网下载卡十几分钟。缺包处理见 --ensure-fw。

原理（已实测）:
    STM32CubeMX.exe -q script.txt
    script.txt 内容:
        config load <ioc 路径>
        project generate

已知坑（实测发现，本脚本已处理）:
    - CubeMX 生成完成后 javaw 进程残留不退出 → 生成结束/超时后按命令行匹配清理
    - 首次运行慢（Java 启动 + 固件包下载），约 3 分钟；后续明显加快
    - 生成会覆盖 Core/Drivers 已有文件（保留 USER CODE BEGIN/END 段手写代码）
      → 默认拷贝 ioc 到独立目录跑，--in-place 才碰原工程
    - 生成完成检测：轮询 ~/.stm32cubemx/STM32CubeMX.log 增量内容里的完成标记
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from _cmdutil import fix_console_encoding, run_cmd  # noqa: E402

fix_console_encoding()

# ===================== 常量 =====================
# CubeMX 常见安装路径；也可用环境变量 CUBEMX_PATH 显式指定
CUBEMX_DEFAULT_PATHS = [
    Path(r"D:\STM32CubeMX\STM32CubeMX.exe"),
    Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"),
    Path(r"C:\STM32CubeMX\STM32CubeMX.exe"),
]
# CubeMX 生成日志（用户级）。生成成功的完成标记（日志增量里出现即认为完成）
MX_LOG = Path.home() / ".stm32cubemx" / "STM32CubeMX.log"
DONE_MARKERS = ("Time for Generating toolchain IDE Files", "mx.scratch is deleted")
POLL_INTERVAL = 3.0
DEFAULT_TIMEOUT = 420.0   # CubeMX 启动含网络更新检查，可达 3 分钟；420s 才兜得住


# ===================== 输出 =====================
# --json 安静模式：生成过程中的 [INFO]/[OK] 改走 stderr，stdout 只保留最终
# JSON 行（供 MCP 子进程调用解析，避免污染 MCP 的 stdout 协议通道）。
QUIET = False


def _say(msg: str):
    (sys.stderr if QUIET else sys.stdout).write(msg + "\n")


def ok(msg):    _say(f"[OK]   {msg}")
def warn(msg):  _say(f"[WARN] {msg}")
def info(msg):  _say(f"[INFO] {msg}")
def err(msg):   sys.stderr.write(f"[ERR]  {msg}\n")


# ===================== 环境检测 =====================
def detect_cubemx():
    """返回 CubeMX 可执行文件路径；找不到返回 None。优先 CUBEMX_PATH 环境变量。"""
    env = os.environ.get("CUBEMX_PATH")
    if env and Path(env).exists():
        return str(Path(env))
    for p in CUBEMX_DEFAULT_PATHS:
        if p.exists():
            return str(p)
    return None


def ioc_info(ioc_path: Path):
    """从 .ioc 读取 MCU 型号与目标工具链，用于报告。"""
    mcu = toolchain = None
    try:
        for line in ioc_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Mcu.Name") and mcu is None:
                mcu = line.split("=", 1)[1].strip()
            elif line.startswith("ProjectManager.TargetToolchain") and toolchain is None:
                toolchain = line.split("=", 1)[1].strip()
    except OSError as e:
        err(f"读取 {ioc_path} 失败: {e}")
    return mcu, toolchain


# ===================== 固件包自检 =====================
# CubeMX 固件包（STM32Cube FW）仓库常见位置：
#   安装目录旁：D:\STM32CubeMX\STM32Cube\Repository（多数安装选这里）
#   用户目录：  %USERPROFILE%\STM32Cube\Repository / C:\Users\Public\STM32Cube\Repository
# CubeMX 不把仓库路径写进配置文件，只能按常见位置探测。
def find_repository() -> list:
    """返回存在的固件仓库候选路径（按优先级，去重）。"""
    exe = detect_cubemx()
    candidates = []
    if exe:
        exe_dir = Path(exe).parent
        candidates.append(exe_dir / "STM32Cube" / "Repository")
        candidates.append(exe_dir / "Repository")
    candidates += [
        Path.home() / "STM32Cube" / "Repository",
        Path.home() / ".stm32cubemx" / "repository",
        Path(r"C:\Users\Public\STM32Cube\Repository"),
        Path(r"D:\STM32Cube\Repository"),
    ]
    seen, repos = set(), []
    for p in candidates:
        key = str(p).lower()
        if key not in seen and p.is_dir():
            seen.add(key)
            repos.append(p)
    return repos


# CubeMX 固件包家族名（对应 STM32Cube_FW_<家族> 目录）。含两位字母家族 WB/WL/WBA 等。
FW_FAMILIES = [
    "F0", "F1", "F2", "F3", "F4", "F7", "G0", "G4", "H5", "H7", "H7RS",
    "L0", "L1", "L4", "L5", "U0", "U3", "U5", "N6", "C0", "M0",
    "WB", "WBA", "WB0", "WL", "WL3", "W5",
]
_FW_FAMILIES_SORTED = sorted(FW_FAMILIES, key=len, reverse=True)


def family_from_ioc(ioc_path: Path):
    """从 .ioc 的 Mcu.Name 推断家族（STM32G474VETx → G4、STM32WB55CGUx → WB）。

    家族可能是两位字母（WB/WL/WBA），不能只取"字母+数字"；用已知家族表做最长前缀匹配。
    读不到返回 None。
    """
    mcu, _ = ioc_info(ioc_path)
    if not mcu:
        return None
    body = mcu[5:].upper() if mcu[:5].upper() == "STM32" else mcu.upper()
    for fam in _FW_FAMILIES_SORTED:
        if body.startswith(fam):
            return fam
    return None


def fw_prefix(family: str) -> str:
    """家族 → 固件包目录前缀（G4 → STM32Cube_FW_G4）。"""
    return f"STM32Cube_FW_{family.upper()}"


def find_fw_package(repos: list, family: str):
    """在候选仓库找某家族的固件包。

    返回 (installed_dir, zip_path)：
      installed_dir：已解压的包目录（STM32Cube_FW_G4_V1.6.3）或 None
      zip_path     ：已下载的 zip（优先最新版本）或 None
    """
    dir_prefix = fw_prefix(family)
    zip_prefix = f"stm32cube_fw_{family.lower()}_v"
    installed = None
    zips = []
    for repo in repos:
        if not repo.is_dir():
            continue
        try:
            entries = list(repo.iterdir())
        except OSError:
            continue
        if installed is None:
            installed = next((p for p in entries
                              if p.is_dir() and p.name.startswith(dir_prefix)), None)
        zips += [p for p in entries
                 if p.is_file() and p.name.lower().startswith(zip_prefix)
                 and p.suffix.lower() == ".zip"]
    zips.sort(reverse=True)   # 版本号从大到小，取最新
    return installed, (zips[0] if zips else None)


def check_fw(ioc_path: Path) -> dict:
    """预检某 .ioc 需要的固件包是否已就绪（不启动 CubeMX）。

    返回 dict：ok / family / required / repos / installed / zip / hint。
    """
    repos = find_repository()
    family = family_from_ioc(ioc_path)
    if not family:
        return {
            "ok": False, "error_type": "no_mcu",
            "family": None, "required": None,
            "repos": [str(r) for r in repos],
            "installed": None, "zip": None,
            "hint": "无法从 .ioc 读取 MCU 家族，无法预检固件包",
        }
    installed, zip_path = find_fw_package(repos, family)
    required = fw_prefix(family)
    if installed:
        hint = f"已安装: {installed.name}"
    elif zip_path:
        hint = f"zip 已下载但未解压: {zip_path.name} → 可 --ensure-fw 本地解压"
    else:
        hint = f"未找到 {required}。需联网下载/安装（CubeMX GUI → Help → Manage embedded software packages），"
    return {
        "ok": installed is not None,
        "error_type": None if installed else "missing_firmware",
        "family": family,
        "required": required,
        "repos": [str(r) for r in repos],
        "installed": str(installed) if installed else None,
        "zip": str(zip_path) if zip_path else None,
        "hint": hint,
    }


def ensure_fw(ioc_path: Path, yes: bool = False) -> dict:
    """尝试补齐 .ioc 所需固件包。

    情况 A：已安装 → 直接返回。
    情况 B：zip 已下载未解压 → 本地解压（快，无需联网）。
    情况 C：完全没有 → 提示去 CubeMX GUI 安装；若 --yes 则返回 need_download，
            由调用方决定是否用长超时跑生成（CubeMX 会在生成时联网下载）。
    """
    fw = check_fw(ioc_path)
    if fw["ok"]:
        return {**fw, "action": "already_installed"}
    if fw["zip"]:
        try:
            with zipfile.ZipFile(fw["zip"]) as zf:
                zf.extractall(Path(fw["zip"]).parent)
            installed, _ = find_fw_package(find_repository(), fw["family"])
            ok(f"已从 {Path(fw['zip']).name} 本地解压固件包")
            return {**fw, "action": "unzipped", "installed": str(installed) if installed else None,
                    "ok": installed is not None}
        except zipfile.BadZipFile as e:
            warn(f"zip 损坏: {e}")
            fw["hint"] += "（zip 损坏，需重新下载）"
            return {**fw, "action": "bad_zip"}
    # 完全没有 → 无法本地补
    if not yes:
        warn(f"缺少固件包 {fw['required']}。安装方式：CubeMX GUI → Help → Manage embedded "
             "software packages → 勾选该家族安装；或直接跑生成（CubeMX 会联网下载，较慢）")
    return {**fw, "action": "needs_download"}


# ===================== 生成 =====================
def write_script(ioc_abs: str) -> Path:
    """写 CubeMX 脚本文件（config load + project generate），返回脚本路径。"""
    script = Path(tempfile.gettempdir()) / f"cubemx_{int(time.time())}.txt"
    script.write_text(f"config load {ioc_abs}\nproject generate\n", encoding="utf-8")
    return script


def find_cubemx_javaw_pids() -> list:
    """列出命令行含 STM32CubeMX 的 javaw PID（可能一个不留）。"""
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='javaw.exe'\" | "
        "Where-Object { $_.CommandLine -like '*STM32CubeMX*' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    r = run_cmd(["powershell", "-NoProfile", "-Command", ps], timeout=30)
    return [int(x.strip()) for x in (r.stdout or "").split() if x.strip().isdigit()]


def kill_cubemx_javaw(retries: int = 3) -> int:
    """清理 CubeMX 残留的 javaw 进程（重试至无残留）。

    实测：完成标记出现后 javaw 可能尚在收尾，一次 taskkill 会漏杀，
    或进程刚退出。因此每轮重新枚举、逐轮重试，直到清空或到轮次上限。
    只杀命令行含 STM32CubeMX 的 javaw，不误伤其他 Java 程序。
    返回累计杀掉的进程数。
    """
    killed = 0
    for _ in range(max(retries, 1)):
        pids = find_cubemx_javaw_pids()
        if not pids:
            break
        for pid in pids:
            r = run_cmd(["taskkill", "/PID", str(pid), "/F"], timeout=15)
            if r.ok:
                killed += 1
        time.sleep(2)   # 给被杀进程退场 / 新进程现身留时间，再进下一轮复查
    return killed


def wait_generation(out_dir: Path, mdk_name: str, timeout: float, launched_log_size: int):
    """轮询判断生成是否完成。

    主要依据：日志自启动点新增内容里出现完成标记。
    兜底：目标 MDK-ARM/<name>.uvprojx 出现且大小稳定。
    实测：日志完成标记可能比 .uvprojx 落盘早几秒 → 标记出现后若
    uvprojx 未就绪，再多等几秒补抓，避免"生成了却报没找到"。
    返回 (完成?, 已见 uvprojx?)。
    """
    deadline = time.time() + timeout
    uvprojx = out_dir / "MDK-ARM" / f"{mdk_name}.uvprojx"
    seen_uvprojx = False
    uvprojx_first_seen = None
    anchor = launched_log_size
    marker_seen_at = None
    while time.time() < deadline:
        # 1) 日志增量找完成标记
        if marker_seen_at is None:
            try:
                size = MX_LOG.stat().st_size
                if size < anchor:          # 日志被截断/重建，重置锚点
                    anchor = 0
                if size > anchor:
                    with open(MX_LOG, encoding="utf-8", errors="replace") as f:
                        f.seek(anchor)
                        new = f.read()
                    if any(m in new for m in DONE_MARKERS):
                        marker_seen_at = time.time()
                    anchor = size
            except OSError:
                pass
        # 2) uvprojx 出现即记录首次时间
        try:
            if uvprojx.exists() and uvprojx.stat().st_size > 0:
                if not seen_uvprojx:
                    seen_uvprojx = True
                    uvprojx_first_seen = time.time()
        except OSError:
            pass
        # 3) 完成判定
        if marker_seen_at is not None:
            if seen_uvprojx:               # 标记 + uvprojx 就绪 → 立即确认
                return True, True
            if time.time() - marker_seen_at >= 6.0:   # 标记出现后最多再等 6s 补抓
                return True, False
        elif seen_uvprojx and uvprojx_first_seen and \
                time.time() - uvprojx_first_seen >= 2 * POLL_INTERVAL:
            return True, True              # 无标记兜底：uvprojx 稳定出现
        time.sleep(POLL_INTERVAL)
    return False, seen_uvprojx


def generate(ioc_path: Path, out_dir: Path, timeout: float, in_place: bool) -> dict:
    """在 out_dir（或 in_place 时 ioc 所在目录）生成工程。

    返回结构化结果 dict（--json 模式由 main 直接转成 JSON 输出）：
    success / cubemx_path / ioc / mcu / toolchain / out_dir /
    elapsed_s / uvprojx / generated_count / generated / error
    """
    result = {
        "success": False, "cubemx_path": None, "ioc": str(ioc_path),
        "mcu": None, "toolchain": None, "out_dir": None,
        "elapsed_s": None, "uvprojx": None,
        "generated_count": 0, "generated": [], "error": None,
    }
    exe = detect_cubemx()
    if not exe:
        result["error"] = "未找到 STM32CubeMX.exe。设 CUBEMX_PATH 环境变量，或安装到默认路径后重试。"
        err(result["error"])
        return result
    result["cubemx_path"] = exe

    mcu, toolchain = ioc_info(ioc_path)
    result["mcu"], result["toolchain"] = mcu, toolchain
    mdk_name = ioc_path.stem
    info(f"CubeMX   : {exe}")
    info(f"ioc      : {ioc_path}  (MCU={mcu}, toolchain={toolchain})")

    # ---- 预检：目标芯片所需固件包是否已就绪（缺失则快速失败，不启动 CubeMX 傻等下载） ----
    fw = check_fw(ioc_path)
    if not fw["ok"]:
        result["error_type"] = fw.get("error_type") or "missing_firmware"
        result["required_fw"] = fw.get("required")
        result["fw_repos"] = fw.get("repos", [])
        result["error"] = (
            f"缺少固件包 {fw.get('required')}，无法生成。\n"
            f"  仓库探测: {fw.get('repos')}\n"
            f"  提示: {fw.get('hint')}\n"
            f"  处理: 先跑 python cubemx_gen.py --ensure-fw <ioc>，"
            "或在 CubeMX GUI → Help → Manage embedded software packages 安装后重试。"
        )
        err(result["error"])
        return result
    info(f"固件包   : {fw['required']} 已就绪（{fw.get('installed')}）")

    if in_place:
        working = ioc_path.parent
        ioc_for_mx = ioc_path.resolve()
        warn(f"原位生成：会覆盖 {working / 'Core'} / {working / 'Drivers'} 已有文件（USER CODE 段保留）")
    else:
        working = out_dir
        working.mkdir(parents=True, exist_ok=True)
        ioc_for_mx = working / ioc_path.name
        # 若输出目录 == ioc 所在目录（如 new_project 直接生成进目标目录），跳过自拷贝
        # （Windows 上 copy2 同路径会 PermissionError）
        if ioc_for_mx.resolve() != ioc_path.resolve():
            shutil.copy2(ioc_path, ioc_for_mx)   # 拷贝 ioc 过去，CubeMX 输出到 ioc 所在目录
        info(f"输出目录 : {working}")
    result["out_dir"] = str(working)

    script = write_script(str(ioc_for_mx))
    try:
        anchor = MX_LOG.stat().st_size if MX_LOG.exists() else 0
        info("启动 STM32CubeMX 无头生成（首次 3 分钟+，耐心等待）...")
        start = time.time()
        try:
            subprocess.Popen(
                [exe, "-q", str(script)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            result["error"] = f"启动 CubeMX 失败: {e}"
            err(result["error"])
            return result

        done, seen_uvprojx = wait_generation(working, mdk_name, timeout, anchor)
        result["elapsed_s"] = round(time.time() - start, 1)

        time.sleep(2)                       # 完成标记后给 CubeMX 收尾写盘留缓冲
        killed = kill_cubemx_javaw()        # 无论成败都清理残留进程
        if killed:
            info(f"已清理 CubeMX 残留进程 x{killed}")

        if not done:
            result["error"] = f"生成超时（>{int(timeout)}s）。日志: {MX_LOG}"
            err(result["error"])
            return result

        uvprojx = working / "MDK-ARM" / f"{mdk_name}.uvprojx"
        if seen_uvprojx:
            result["uvprojx"] = str(uvprojx)
            ok(f"生成完成，耗时 {result['elapsed_s']}s，工程: {uvprojx}")
        else:
            ok(f"生成完成，耗时 {result['elapsed_s']}s（未找到 .uvprojx，请人工核对输出目录）")

        files = list_files(working)
        result["generated_count"] = len(files)
        result["generated"] = files[:50]
        result["success"] = True
        return result
    finally:
        try:
            script.unlink()                   # 清理临时脚本
        except OSError:
            pass


def list_files(out_dir: Path):
    """列出输出目录下的生成文件（相对路径 + 数量）。"""
    if not out_dir.is_dir():
        return []
    return sorted(str(p.relative_to(out_dir)).replace("\\", "/")
                  for p in out_dir.rglob("*") if p.is_file())


# ===================== CLI =====================
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="cubemx_gen.py",
        description="STM32CubeMX 无头代码生成实验脚本。用法见文件头注释。",
    )
    ap.add_argument("ioc", nargs="?", help=".ioc 文件路径")
    ap.add_argument("--check", action="store_true", help="只检测 CubeMX 环境，不生成")
    ap.add_argument("--check-fw", action="store_true",
                    help="只检测 .ioc 所需固件包是否就绪，不生成（缺包也不卡住）")
    ap.add_argument("--ensure-fw", action="store_true",
                    help="尝试补齐固件包：zip 已下载则本地解压；没有则提示去 GUI 装")
    ap.add_argument("--in-place", action="store_true",
                    help="在 ioc 所在目录生成（覆盖 Core/Drivers，需确认）")
    ap.add_argument("--out-dir", help="生成到指定目录（默认: ioc 旁 cubemx_out/）")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"生成超时秒数（默认 {DEFAULT_TIMEOUT:.0f}）")
    ap.add_argument("--yes", action="store_true", help="跳过确认（配合 --in-place）")
    ap.add_argument("--json", action="store_true",
                    help="安静模式：stdout 只输出一个 JSON 结果（供 MCP/脚本解析）")
    args = ap.parse_args(argv)

    global QUIET
    QUIET = args.json

    def emit(obj: dict):
        if args.json:
            print(json.dumps(obj, ensure_ascii=False))

    # ---- --check：只检测环境 ----
    if args.check:
        exe = detect_cubemx()
        if not exe:
            msg = "未找到 STM32CubeMX.exe。设 CUBEMX_PATH 环境变量，或安装到默认路径。"
            err(msg)
            emit({"found": False, "cubemx_path": None, "builtin_jre": False, "error": msg})
            return 1
        jre = Path(exe).parent / "jre"
        ok(f"STM32CubeMX: {exe}")
        ok(f"内置 JRE   : {'存在（无需另装 Java）' if jre.is_dir() else '未内置（需 Java 11+）'}")
        emit({"found": True, "cubemx_path": exe, "builtin_jre": jre.is_dir(), "error": None})
        return 0

    if not args.ioc:
        ap.error("需要 .ioc 文件路径（或用 --check）")

    ioc = Path(args.ioc).resolve()
    if not ioc.exists():
        msg = f".ioc 不存在: {ioc}"
        err(msg)
        emit({"success": False, "error": msg})
        return 1
    if ioc.suffix.lower() != ".ioc":
        warn(f"路径不是 .ioc 文件: {ioc}")

    # ---- --check-fw：只查固件包，不生成 ----
    if args.check_fw:
        fw = check_fw(ioc)
        if args.json:
            emit(fw)
        else:
            info(f"所需固件包: {fw['required']}")
            info(f"仓库位置  : {fw['repos']}")
            if fw["ok"]:
                ok(f"已就绪: {fw['installed']}")
            else:
                err(f"缺失: {fw['hint']}")
        return 0 if fw["ok"] else 1

    # ---- --ensure-fw：尝试补齐固件包 ----
    if args.ensure_fw:
        fw = ensure_fw(ioc, yes=args.yes)
        if args.json:
            emit(fw)
        else:
            info(f"所需固件包: {fw['required']} | 动作: {fw['action']}")
            if fw["ok"]:
                ok(f"已就绪: {fw['installed']}")
            else:
                err(f"未就绪: {fw['hint']}")
        return 0 if fw["ok"] else 1

    # ---- 确认 in-place 覆盖（非交互 / MCP --json 下跳过，靠调用方兜底） ----
    if args.in_place and not args.yes and not args.json and sys.stdin.isatty():
        warn(f"将在 {ioc.parent} 原位生成，覆盖 Core/Drivers。确认？[y/N] ", end="")
        try:
            ans = input().strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            info("已取消")
            return 0

    out_dir = Path(args.out_dir).resolve() if args.out_dir else ioc.parent / "cubemx_out"
    result = generate(ioc, out_dir, args.timeout, args.in_place)
    emit(result)
    if not result["success"]:
        return 1

    # ---- 报告生成结果（人类可读，仅非 --json 时） ----
    if not args.json:
        print()
        info(f"输出目录共 {result['generated_count']} 个文件:")
        for f in result["generated"]:
            info(f"  {f}")
        if result["generated_count"] > 50:
            info(f"  ... 其余 {result['generated_count'] - 50} 个省略")
    return 0


if __name__ == "__main__":
    sys.exit(main())
