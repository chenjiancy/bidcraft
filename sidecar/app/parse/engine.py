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

路径解析优先级：
1. 环境变量 ``BIDCRAFT_MINERU_PYTHON``（显式覆盖）；
2. 打包后随安装包分发的可重定位运行时
   ``<BIDCRAFT_RESOURCES_PATH>/mineru/python/python.exe``（PyInstaller 外的
   python-build-standalone，不依赖用户机器安装 Python）；
3. 开发期 ``sidecar/.venv-mineru``。

打包模型（``<resources>/mineru/models``，PDF-Extract-Kit 快照内容）存在时，
在 dataRoot 下生成 ``mineru.json`` 并以 ``MINERU_MODEL_SOURCE=local`` 调用，
离线可用、不触发联网下载。未安装/版本不符时调用方明确报错（不静默降级）。
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

# Electron main 注入：打包后 process.resourcesPath；未设置表示开发环境
ENV_RESOURCES_PATH = "BIDCRAFT_RESOURCES_PATH"
ENV_MINERU_PYTHON = "BIDCRAFT_MINERU_PYTHON"
ENV_DATA_ROOT = "BIDCRAFT_DATA_ROOT"
# MinerU 3.4.5 local 模式相关环境变量
ENV_MODEL_SOURCE = "MINERU_MODEL_SOURCE"
ENV_TOOLS_CONFIG_JSON = "MINERU_TOOLS_CONFIG_JSON"
# 与 mineru/models_download_utils.MINERU_CONFIG_VERSION 对齐
_MINERU_CONFIG_VERSION = "1.3.2"


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


def _python_exe_name() -> str:
    return "python.exe" if os.name == "nt" else "bin/python3"


def _packaged_root() -> Path | None:
    """Electron 注入的 resources 目录；未设置返回 None。"""
    raw = os.environ.get(ENV_RESOURCES_PATH)
    return Path(raw) if raw else None


def _packaged_python() -> Path | None:
    """打包随包分发的可重定位 Python 运行时（resources/mineru/python）。"""
    root = _packaged_root()
    if root is None:
        return None
    candidate = root / "mineru" / "python" / _python_exe_name()
    return candidate if candidate.is_file() else None


def _packaged_models_dir() -> Path | None:
    """随包分发的 pipeline 模型快照目录（resources/mineru/models）。"""
    root = _packaged_root()
    if root is None:
        return None
    candidate = root / "mineru" / "models"
    return candidate if candidate.is_dir() else None


def mineru_python() -> Path | None:
    """定位 MinerU 运行时 python；找不到返回 None。

    优先级：BIDCRAFT_MINERU_PYTHON 显式覆盖 → 打包 resources 运行时 → 开发 venv。
    """
    candidates: list[Path] = []
    env_python = os.environ.get(ENV_MINERU_PYTHON)
    if env_python:
        candidates.append(Path(env_python))
    packaged = _packaged_python()
    if packaged is not None:
        candidates.append(packaged)
    if os.name == "nt":
        candidates.append(_DEFAULT_VENV / "Scripts" / "python.exe")
    else:
        candidates.append(_DEFAULT_VENV / "bin" / "python")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _mineru_argv(python: Path) -> list[str]:
    """MinerU CLI 调用前缀。

    统一走 ``python -m mineru.cli.client``：不依赖 pip 生成的 console 脚本
    （其 wrapper 在可重定位分发目录中可能失效），开发 venv 与打包运行时同源。
    """
    return [str(python), "-m", "mineru.cli.client"]


def ensure_packaged_mineru_config() -> Path | None:
    """内置模型存在时，在 dataRoot 生成 local 模式 mineru.json，返回配置路径。

    - 配置放 dataRoot（安装目录 Program Files 只读，不能放 resources）；
    - 幂等：目标内容与现状一致时不重写；
    - 无内置模型或无 dataRoot（非 Electron 调用）时返回 None，保持开发行为。
    """
    models_dir = _packaged_models_dir()
    if models_dir is None:
        return None
    data_root = os.environ.get(ENV_DATA_ROOT)
    if not data_root:
        return None

    cfg_dir = Path(data_root) / "mineru"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "mineru.json"
    payload = {
        "config_version": _MINERU_CONFIG_VERSION,
        "model-source": "local",
        "models-dir": {"pipeline": str(models_dir)},
    }
    existing = None
    if cfg_path.is_file():
        try:
            existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
    if existing != payload:
        cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8")
    return cfg_path


def mineru_child_env() -> dict[str, str]:
    """MinerU 子进程环境：内置模型走 local 离线模式，否则继承开发期行为。"""
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cfg_path = ensure_packaged_mineru_config()
    if cfg_path is not None:
        env[ENV_MODEL_SOURCE] = "local"
        env[ENV_TOOLS_CONFIG_JSON] = str(cfg_path)
    return env


async def probe_status(*, timeout: int = 120) -> EngineStatus:
    """检测 MinerU 环境：可执行、版本（须 3.x）、CUDA 是否可用。"""
    python = mineru_python()
    if python is None:
        return EngineStatus(
            available=False,
            error=(
                "未找到 MinerU 环境（BIDCRAFT_MINERU_PYTHON、"
                "打包 resources 或 sidecar/.venv-mineru）"
            ),
        )

    # 直接 python -c 探测可导入性与版本；import mineru 失败会以非零退出暴露，
    # 不依赖 mineru 命令（console 脚本在可重定位分发目录中可能缺失）
    check = (
        "import json, importlib.metadata as m, mineru, torch; "
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
            env=mineru_child_env(),
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
    if python is None:
        raise MinerUUnavailable("MinerU 环境不可用，请安装 mineru==3.4.5（pipeline）")
    if not input_file.is_file():
        raise MinerUError(f"输入文件不存在：{input_file}")

    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        *_mineru_argv(python),
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
        env=mineru_child_env(),
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
