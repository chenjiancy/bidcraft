"""项目数据目录解析（architecture.md 第五章）。

目录布局（Task 8 相关部分）::

    <data_root>/enterprises/<enterprise_id>/projects/<project_id>/
    ├── source/            # 用户登记的原招标文件（复制入库）
    └── parse/
        ├── raw/           # MinerU 原始产物（Markdown + JSON + images）
        ├── chapters.json  # 章节切分结果（Task 8）
        └── checkpoints/   # BP-1 长任务 checkpoint（JSON）

所有写入路径都经 ``ensure_within_project`` 校验，禁止逃逸项目根
（architecture.md 八：文件操作经路径校验）。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core import config

_SOURCE = "source"
_PARSE = "parse"
_RAW = "raw"
_CHECKPOINTS = "checkpoints"
_DOCX = "docx"
_CONFIRMED = "confirmed"
_LISTS = "lists"


class PathEscapeError(Exception):
    """目标路径逃逸了允许的项目数据根目录。"""


def data_root() -> Path:
    return config.DATA_ROOT


def project_dir(enterprise_id: str, project_id: str) -> Path:
    return config.DATA_ROOT / "enterprises" / enterprise_id / "projects" / project_id


def source_dir(enterprise_id: str, project_id: str) -> Path:
    return project_dir(enterprise_id, project_id) / _SOURCE


def parse_dir(enterprise_id: str, project_id: str) -> Path:
    return project_dir(enterprise_id, project_id) / _PARSE


def raw_dir(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / _RAW


def checkpoints_dir(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / _CHECKPOINTS


def chapters_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "chapters.json"


def extract_list_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "structured" / "extract_list.json"


def score_table_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "structured" / "score_table.json"


def docx_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 12：投标文件格式逐章 docx 产物根目录（按源文件分子目录）。"""
    return parse_dir(enterprise_id, project_id) / _DOCX


def docx_manifest_path(enterprise_id: str, project_id: str) -> Path:
    return docx_dir(enterprise_id, project_id) / "manifest.json"


def confirmed_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 13：人工确认后的最终清单目录。"""
    return parse_dir(enterprise_id, project_id) / _CONFIRMED


def checklist_path(enterprise_id: str, project_id: str) -> Path:
    """Task 13：parse_checklist.json 路径。"""
    return confirmed_dir(enterprise_id, project_id) / "parse_checklist.json"


def lists_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 14：商务标格式清单目录（format_checklist.json 等）。"""
    return project_dir(enterprise_id, project_id) / _LISTS


def format_list_path(enterprise_id: str, project_id: str) -> Path:
    """Task 14：商务标格式清单 JSON 路径。"""
    return lists_dir(enterprise_id, project_id) / "format_checklist.json"


def format_list_checkpoint_path(enterprise_id: str, project_id: str) -> Path:
    """Task 14：格式清单确认 checkpoint JSON 路径。"""
    return checkpoints_dir(enterprise_id, project_id) / "format_list.json"


def ensure_within_project(base: Path, target: Path) -> Path:
    """确保 target 解析后位于 base 之内，否则拒绝（防路径穿越）。"""
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if target_resolved != base_resolved and base_resolved not in target_resolved.parents:
        raise PathEscapeError(f"路径 {target} 逃逸项目目录 {base}")
    return target_resolved


# Windows 保留名 / 路径非法字符；同时去除控制字符
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_filename(name: str, *, fallback: str = "unnamed") -> str:
    """把用户文件名规范化为跨平台安全文件名（保留中文与扩展名）。"""
    cleaned = _INVALID_CHARS.sub("_", name).strip(" .")
    if not cleaned:
        return fallback
    if cleaned.lower().split(".")[0] in _RESERVED_NAMES:
        # Windows 保留名：替换主名部分但保留扩展名
        suffix = Path(cleaned).suffix
        cleaned = f"{fallback}{suffix}"
    return cleaned[:180]


def unique_path(target: Path) -> Path:
    """目标已存在时追加 -1/-2 后缀，避免覆盖。"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    parent = target.parent
    for i in range(1, 10_000):
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"无法为 {target} 生成不冲突的文件名")
