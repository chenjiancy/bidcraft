"""混合章节子节内容性质标注（TR-10.5）：商务/技术子节。

Task 8 已按标题层级建立子节结构；本模块按标题关键词给每个子节
打上 nature 标签：
- business（商务子节）：供应商介绍、人员力量、业绩、荣誉、财务、服务承诺等；
- tech（技术子节）：监理大纲、技术方案、实施方案、服务方案等；
- general（通用）：无法归入上述两类的章/子节（如封面、目录、总则）。

状态机按子节记录状态：后续商务标/检查按 (chapter_id, section_id) 记录，
section_id 由章节树章/子节 id 组合生成（如 ch1.2）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

Nature = Literal["business", "tech", "general"]

# 商务：供应商介绍、人员力量、业绩、荣誉、财务、承诺函等
_BUSINESS_KEYWORDS = (
    "供应商介绍",
    "供应商简介",
    "投标人介绍",
    "投标人简介",
    "人员力量",
    "人员配备",
    "业绩",
    "荣誉",
    "获奖",
    "财务状况",
    "财务报表",
    "服务承诺",
    "承诺函",
    "售后服务",
    "公司介绍",
    "企业简介",
)

# 技术：监理大纲、技术方案、实施方案、技术参数等
_TECH_KEYWORDS = (
    "监理大纲",
    "技术方案",
    "实施方案",
    "技术参数",
    "技术规格",
    "技术指标",
    "服务方案",
    "施工组织",
    "技术响应",
)

_NATURE_PRIORITY: tuple[tuple[re.Pattern[str], Nature], ...] = (
    (re.compile("|".join(_TECH_KEYWORDS)), "tech"),
    (re.compile("|".join(_BUSINESS_KEYWORDS)), "business"),
)


def classify_section(title: str) -> Nature:
    """按标题判定子节内容性质；命中即返回，否则 general。"""
    for pat, nature in _NATURE_PRIORITY:
        if pat.search(title):
            return nature
    return "general"


@dataclass(frozen=True)
class SectionRecord:
    """子节记录：章节 id + 子节 id + 性质 + 标题 + 页码锚点。"""

    section_id: str  # 如 ch1.2
    chapter_id: str  # 如 ch1
    nature: Nature
    title: str
    page_idx: int
    bbox: list[float] | None


def annotate_tree(nodes: list[dict[str, Any]]) -> list[SectionRecord]:
    """对 Task 8 章节树做后序遍历，给每个节点打 nature，并返回全部子节记录。

    输入节点结构与 chapters.json 一致（含 children / title / anchor / id）。
    本函数只读，不改写输入。
    """
    records: list[SectionRecord] = []

    def _walk(node: dict[str, Any]) -> None:
        nature = classify_section(str(node.get("title", "")))
        anchor = node.get("anchor") or {}
        rec = SectionRecord(
            section_id=str(node.get("id", "")),
            chapter_id=str(node.get("id", "")).split(".")[0],
            nature=nature,
            title=str(node.get("title", "")),
            page_idx=int(anchor.get("page_idx", 0)),
            bbox=anchor.get("bbox") if isinstance(anchor.get("bbox"), list) else None,
        )
        records.append(rec)
        for child in node.get("children") or []:
            _walk(child)

    for n in nodes:
        _walk(n)
    return records
