"""MinerU CLI 封装（Task 8 第 1、3 点）。

集成形态（TS-2 决策）：MinerU 装在独立 venv，sidecar 经子进程调用 CLI，
重依赖不进入 sidecar 主环境。命令（3.4.5）::

    mineru -p <input> -o <out> -b pipeline -m auto -l ch

- ``-b pipeline``：确定性管线（版面 + PP-OCRv6），不触发 VLM 模型（Task 8 不涉及 LLM）；
- ``-m auto``：文字版走文本提取、扫描件自动 OCR（MinerU 内部按页判定）；
- GPU：CUDA 版 torch 可用时 pipeline 自动加速，无需额外参数；
- 输出（3.4.5 实测）：``<out>/<stem>/<method>/`` 内含 ``<stem>.md``、
  ``<stem>_content_list.json``（非 _v2）、``<stem>_middle.json``（页码坐标/bbox）、
  ``images/``；多源共用 out_dir 时各自独立 ``<stem>/`` 子树。

路径解析：环境变量 ``BIDCRAFT_MINERU_PYTHON`` → 开发期 ``sidecar/.venv-mineru``。
未安装/版本不符时调用方明确报错（不静默降级）。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# 本文件路径：sidecar/app/parse/engine.py → sidecar 根为 parents[2]
_SIDECAR_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_VENV = _SIDECAR_ROOT / ".venv-mineru"
_SUPPORTED_MAJOR = 3
MINERU_TIMEOUT_SECONDS = 3_600


class MinerUError(Exception):
    """MinerU 解析失败。"""


class MinerUUnavailable(MinerUError):
    """MinerU 环境未安装/版本不符，无法执行解析（须明确暴露，不静默）。"""


@dataclass
class EngineStatus:
    available: bool
    python_path: str | None = None
    version: str | None = None
    cuda_available: bool | None = None
    cuda_device: str | None = None
    error: str | None = None


@dataclass
class RawResult:
    """单个文件的 MinerU 原始产物定位。"""

    output_dir: Path
    markdown_path: Path
    content_list_path: Path | None
    middle_json_path: Path | None
    images_dir: Path | None
    log_lines: list[str] = field(default_factory=list)


def mineru_python() -> Path | None:
    """定位 MinerU 独立 venv 的 python；找不到返回 None。"""
    env_python = os.environ.get("BIDCRAFT_MINERU_PYTHON")
    candidates = []
    if env_python:
        candidates.append(Path(env_python))
    if os.name == "nt":
        candidates.append(_DEFAULT_VENV / "Scripts" / "python.exe")
    else:
        candidates.append(_DEFAULT_VENV / "bin" / "python")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _mineru_cli(python: Path) -> Path:
    scripts = python.parent
    exe = scripts / ("mineru.exe" if os.name == "nt" else "mineru")
    return exe


async def probe_status(*, timeout: int = 120) -> EngineStatus:
    """检测 MinerU 环境：可执行、版本（须 3.x）、CUDA 是否可用。"""
    python = mineru_python()
    if python is None:
        return EngineStatus(
            available=False,
            error="未找到 MinerU 环境（sidecar/.venv-mineru 或 BIDCRAFT_MINERU_PYTHON）",
        )
    if not _mineru_cli(python).is_file():
        return EngineStatus(
            available=False,
            python_path=str(python),
            error="MinerU venv 中不存在 mineru 命令，请安装 mineru==3.4.5",
        )

    check = (
        "import json, importlib.metadata as m, torch; "
        "print(json.dumps({"
        "'version': m.version('mineru'), "
        "'cuda': bool(torch.cuda.is_available()), "
        "'device': (torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
        "}))"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            str(python),
            "-c",
            check,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, OSError) as exc:
        return EngineStatus(available=False, python_path=str(python), error=f"环境探测失败：{exc}")

    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace")[-400:]
        return EngineStatus(
            available=False, python_path=str(python), error=f"环境探测异常：{detail}"
        )

    info = json.loads(stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
    version = info["version"]
    major = int(version.split(".")[0])
    if major != _SUPPORTED_MAJOR:
        return EngineStatus(
            available=False,
            python_path=str(python),
            version=version,
            cuda_available=info.get("cuda"),
            error=f"MinerU 版本为 {version}，本项目锁定 3.4.x（TS-2）",
        )
    return EngineStatus(
        available=True,
        python_path=str(python),
        version=version,
        cuda_available=info.get("cuda"),
        cuda_device=info.get("device"),
    )


async def run_mineru(
    input_file: Path,
    out_dir: Path,
    *,
    method: str = "auto",
    language: str = "ch",
    cancel_event: asyncio.Event | None = None,
    timeout: int = MINERU_TIMEOUT_SECONDS,
    on_log: Callable[[str], None] | None = None,
) -> RawResult:
    """对单个 pdf/docx 执行 MinerU 解析，定位并返回产物。

    method: auto（默认，文本/OCR 自动分流）/ txt / ocr。
    """
    python = mineru_python()
    if python is None or not _mineru_cli(python).is_file():
        raise MinerUUnavailable("MinerU 环境不可用，请先安装 mineru==3.4.5（pipeline）")
    if not input_file.is_file():
        raise MinerUError(f"输入文件不存在：{input_file}")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(_mineru_cli(python)),
        "-p",
        str(input_file),
        "-o",
        str(out_dir),
        "-b",
        "pipeline",
        "-m",
        method,
        "-l",
        language,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    log_lines: list[str] = []
    assert proc.stdout is not None

    async def _pump_logs() -> None:
        while True:
            line = await proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                log_lines.append(text)
                del log_lines[:-200]  # 只保留最近 200 行
                if on_log is not None:
                    on_log(text)

    pump_task = asyncio.create_task(_pump_logs())
    cancel_task: asyncio.Task[None] | None = None
    cancelled = False
    if cancel_event is not None:

        async def _wait_cancel() -> None:
            nonlocal cancelled
            await cancel_event.wait()
            cancelled = True  # 先置标志再 kill，避免与 proc.wait() 返回竞态
            proc.kill()

        cancel_task = asyncio.create_task(_wait_cancel())

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        await pump_task
        raise MinerUError(f"MinerU 解析超时（>{timeout}s）：{input_file.name}") from None
    finally:
        # 外层取消/异常传播时确保子进程不成为孤儿（suppress：任务取消态下 await 会再抛）
        if proc.returncode is None:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        with contextlib.suppress(Exception):
            await pump_task
        if cancel_task is not None:
            cancel_task.cancel()

    if cancelled:
        raise asyncio.CancelledError("用户取消解析")
    if proc.returncode != 0:
        tail = "\n".join(log_lines[-30:])
        raise MinerUError(f"MinerU 退出码 {proc.returncode}：{input_file.name}\n{tail}")

    return _locate_outputs(out_dir, input_file, log_lines, method)


def _locate_outputs(
    out_dir: Path,
    input_file: Path,
    log_lines: list[str],
    method: str = "auto",
) -> RawResult:
    """从 MinerU 输出目录定位 md / content_list / middle_json / images。

    3.4.5 实测布局：``<out>/<stem>/<method>/<stem>.md``（method=auto/txt/ocr），
    content_list/middle_json 同目录且文件名带 ``<stem>_`` 前缀（另有 _v2 变体，不取）。
    多个源文件共用 out_dir 时，查找必须限定在本源 ``<out>/<stem>/`` 子树，防止串源。
    """
    stem = input_file.stem
    stem_dir = out_dir / stem
    # 候选基目录（按优先级）：方法子目录 → 源名目录 → out 根（兼容散落布局）
    candidates = [stem_dir / method, stem_dir, out_dir]
    base = next((d for d in candidates if (d / f"{stem}.md").is_file()), None)
    if base is None:
        search_roots = [stem_dir] if stem_dir.is_dir() else [out_dir]
        md_files = [p for root in search_roots for p in root.rglob("*.md") if p.stem == stem]
        if not md_files:
            raise MinerUError(
                f"MinerU 执行成功但未找到 Markdown 产物：{input_file.name}；"
                f"日志尾部：{chr(10).join(log_lines[-10:])}"
            )
        base = md_files[0].parent

    markdown_path = base / f"{stem}.md"
    content_list = base / f"{stem}_content_list.json"
    middle_json = base / f"{stem}_middle.json"
    images = base / "images"
    return RawResult(
        output_dir=base,
        markdown_path=markdown_path,
        content_list_path=content_list if content_list.is_file() else None,
        middle_json_path=middle_json if middle_json.is_file() else None,
        images_dir=images if images.is_dir() else None,
        log_lines=log_lines[-30:],
    )
