"""同名多格式去重（Task 8 第 5 点）。

规则：
- 按"同名"（去扩展名的 stem）分组，识别如 ``资格证明.doc`` + ``资格证明.pdf``；
- 主格式优先级：``docx > doc > pdf``；
- 只有"同内容"才去重：非主格式与主格式经 PDF 文本指纹比对，
  相似才丢弃非主格式（内部消化，不入解析清单/风险清单，仅记日志）；
- 同名但内容不同：**不去重**，全部保留并在报告中披露（防止误删，不静默）。

doc/docx 的 PDF 化由 preprocess 完成；本模块只负责分组、优先级与文本指纹。
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_EXTS = (".docx", ".doc", ".pdf")
# 主格式优先级（数字越小越优先）
_PRIORITY = {".docx": 0, ".doc": 1, ".pdf": 2}

_WS_RE = re.compile(r"\s+")
# 指纹取样上限：招标文件正文足够区分，超长文本截断提速
_FINGERPRINT_CHARS = 20_000
_SIMILARITY_THRESHOLD = 0.85


@dataclass
class SourceFile:
    """登记入库的一个原招标文件。"""

    path: Path
    stored_name: str  # 入库文件名（安全化后，可能带 -1 后缀）

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()

    @property
    def stem(self) -> str:
        """同名分组键：入库文件名去扩展名、去重名后缀（-1/-2）与大小写归一。"""
        stem = self.path.stem
        stem = re.sub(r"-\d+$", "", stem)
        return stem.strip().lower()


@dataclass
class DropRecord:
    path: str
    stored_name: str
    reason: str
    kept_as: str


@dataclass
class MismatchRecord:
    """同名但内容不同的文件组：不去重，全部保留并披露。"""

    stem: str
    members: list[str] = field(default_factory=list)
    reason: str = "同名文件内容不一致，全部保留待人工确认"


@dataclass
class DedupeDecision:
    """单个同名组的去重决策（内容判定前的初步结果）。"""

    stem: str
    members: list[SourceFile]
    primary: SourceFile
    candidates: list[SourceFile]  # 非主格式，等待同内容判定


def group_files(files: list[SourceFile]) -> dict[str, list[SourceFile]]:
    """按同名 stem 分组；不支持的扩展名直接抛错（入口已校验，双保险）。"""
    groups: dict[str, list[SourceFile]] = {}
    for f in files:
        if f.ext not in SUPPORTED_EXTS:
            raise ValueError(f"不支持的文件类型：{f.stored_name}")
        groups.setdefault(f.stem, []).append(f)
    return groups


def plan_group(stem: str, members: list[SourceFile]) -> DedupeDecision:
    """选出主格式与待判定候选（同组同扩展名重名理论上已被 unique_path 排除）。"""
    ordered = sorted(members, key=lambda f: _PRIORITY[f.ext])
    return DedupeDecision(stem=stem, members=ordered, primary=ordered[0], candidates=ordered[1:])


def pdf_text_fingerprint(
    pdf_path: Path, *, max_chars: int = _FINGERPRINT_CHARS
) -> dict[str, object]:
    """提取 PDF 文本指纹：页数 + 归一化文本的 sha256 + 归一化文本（用于相似度）。

    扫描件无文本层时 text 为空，调用方应回退到页数/大小启发式判定。
    """
    reader = PdfReader(str(pdf_path))
    pages = len(reader.pages)
    parts: list[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    normalized = _WS_RE.sub("", "".join(parts))[:max_chars]
    return {
        "pages": pages,
        "chars": len(normalized),
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "text": normalized,
    }


def same_content(
    fp_a: dict[str, object],
    fp_b: dict[str, object],
    *,
    threshold: float = _SIMILARITY_THRESHOLD,
) -> bool:
    """两份 PDF 指纹是否同内容。

    - 文本层充足：相似度（SequenceMatcher）≥ 阈值即同内容；
    - 双方都无文本层（扫描件）：页数相等视为同内容（同名+同页数的噪声场景）；
    - 仅一方无文本层或页数差异过大：判不同内容（保守，防误删）。
    """
    pages_a, pages_b = fp_a["pages"], fp_b["pages"]
    text_a, text_b = fp_a["text"], fp_b["text"]
    assert isinstance(pages_a, int) and isinstance(pages_b, int)
    assert isinstance(text_a, str) and isinstance(text_b, str)

    if not text_a and not text_b:
        return pages_a == pages_b
    if not text_a or not text_b:
        return False
    # 页数差 > 2 页直接判不同（正常格式转换不会增减页）
    if abs(pages_a - pages_b) > 2:
        return False
    ratio = difflib.SequenceMatcher(None, text_a, text_b).ratio()
    return ratio >= threshold


def make_drop_record(candidate: SourceFile, primary: SourceFile, reason: str) -> DropRecord:
    return DropRecord(
        path=str(candidate.path),
        stored_name=candidate.stored_name,
        reason=reason,
        kept_as=primary.stored_name,
    )
