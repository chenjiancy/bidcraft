"""输入预处理（Task 8 第 2 点）：``.doc`` 经 LibreOffice headless 转 PDF。

- ``.docx`` / ``.pdf`` 直接进 MinerU，不转换（保留原貌）；
- ``.doc``（老二进制 Word）转 PDF 后进 MinerU；
- soffice 路径解析：环境变量 ``BIDCRAFT_SOFFICE`` → PATH → Windows 默认安装目录；
- 每次转换使用独立 UserInstallation profile，规避 LibreOffice 同 profile 并发锁；
- 转换失败明确报错（不静默），由编排层记入 checkpoint error。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from pathlib import Path

from app.parse import paths

CONVERT_TIMEOUT_SECONDS = 600

_WINDOWS_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


class PreprocessError(Exception):
    """LibreOffice 转换失败或环境不可用。"""


def find_soffice() -> Path | None:
    """按 环境变量 → PATH → 默认安装目录 顺序定位 soffice。"""
    env_path = os.environ.get("BIDCRAFT_SOFFICE")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    on_path = shutil.which("soffice")
    if on_path:
        return Path(on_path)
    for candidate in _WINDOWS_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
    return None


def soffice_available() -> bool:
    return find_soffice() is not None


async def convert_to_pdf(
    src: Path,
    out_dir: Path,
    *,
    cancel_event: asyncio.Event | None = None,
    timeout: int = CONVERT_TIMEOUT_SECONDS,
) -> Path:
    """把单个 .doc/.docx 转换为 PDF，返回输出 PDF 路径。

    输出文件名与源同名（``a.doc`` → ``a.pdf``）；已存在则调用方负责命名。
    """
    soffice = find_soffice()
    if soffice is None:
        raise PreprocessError(
            "未找到 LibreOffice（soffice），无法转换 .doc 文件；"
            "请安装 LibreOffice 或设置 BIDCRAFT_SOFFICE 环境变量"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    # 独立 profile：避免并发转换时 " soffice 已在运行" 的 profile 锁
    profile_dir = Path(tempfile.mkdtemp(prefix="bidcraft-lo-", dir=str(out_dir)))
    profile_url = profile_dir.resolve().as_uri()

    cmd = [
        str(soffice),
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        f"-env:UserInstallation={profile_url}",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(src),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    cancelled = False
    cancel_task: asyncio.Task[None] | None = None
    try:
        if cancel_event is not None:

            async def _wait_cancel() -> None:
                nonlocal cancelled
                await cancel_event.wait()
                cancelled = True  # 先置标志再 kill，避免与 communicate 返回竞态
                proc.kill()

            cancel_task = asyncio.create_task(_wait_cancel())
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            finally:
                cancel_task.cancel()
            if cancelled:
                raise asyncio.CancelledError("用户取消转换")
        else:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise PreprocessError(f"LibreOffice 转换超时（>{timeout}s）：{src.name}") from None
    finally:
        # 外层取消时确保 soffice 不成为孤儿
        if proc.returncode is None:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        shutil.rmtree(profile_dir, ignore_errors=True)

    if proc.returncode != 0:
        detail = (stderr or stdout).decode("utf-8", errors="replace")[-500:]
        raise PreprocessError(f"LibreOffice 转换失败（exit {proc.returncode}）：{detail}")

    produced = out_dir / f"{src.stem}.pdf"
    if not produced.is_file():
        detail = (stdout or b"").decode("utf-8", errors="replace")[-500:]
        raise PreprocessError(f"转换完成但未找到输出 PDF：{produced.name}；{detail}")

    # C6 修复：同名 doc/docx 转换结果可能覆盖，返回唯一路径
    produced = paths.unique_path(produced)
    return produced
