"""评分表抽取（TR-11.1/11.2/11.4/11.5）：评分办法章节 → 统一层级结构。

输入为纯数据（extract_list.json 中 tech_score/business_score 的 matches
及其 content_list 块），不碰路径/DB。输出 score_table.json payload：

- categories: 评分大类列表（每类含评分项）
- 每评分项：名称/分值/所需证明材料/门槛条件/原文锚点
- total_score_check: 合计校验（≠100 标红，不阻断产出）
- red_flags: 未识别片段、合计异常等（不静默）
"""

from __future__ import annotations

import re
from typing import Any

from app.rules.scoring import thresholds as thresholds_mod

SCORING_VERSION = "1.0.0"

# 评分大类识别：商务/技术/价格（资信）等
_CATEGORY_KEYWORDS = ("商务", "技术", "价格", "资信", "报价")
# 分值行：含"分"的数字行（如 "企业业绩 20分" / "监理大纲（30分）"）
_SCORE_LINE = re.compile(r"(\d+(?:\.\d+)?)\s*分")
# 评分项标题前缀：数字编号（1. / (1) / 一、 等）
_ITEM_PREFIX = re.compile(r"^[\s]*(?:\(?\d+\)|[一二三四五六七八九十]+[、.．]|\d+[、.．])")
# 所需证明材料：括号内或"提供/附"引导
_MATERIAL_PAREN = re.compile(r"(?:提供|附|须附|需附)[：:]?([^。\n]{2,60})")
_MATERIAL_KEYWORDS = re.compile(
    r"(证明材料|证书|业绩证明|合同|中标通知书|社保|职称证|资格证|营业执照|"
    r"财务报告|审计报告|人员配置表|监理大纲|身份证|学历证)"
)

_MAX_ITEM_SCORE = 100  # 单项分值上限（防误识别）


def _norm_line(text: str) -> str:
    return text.strip()


def _is_category_line(line: str) -> bool:
    """评分大类行：含大类关键词 + 分值。

    - 无编号前缀且命中关键词+分值 → 大类行；
    - 带编号前缀时（如真实标书常见的"一、商务评分（满分40分）"），
      需额外含"满分/合计/总计/总分/共…分"的大类总分信号，
      避免把"技术方案 10分"这类评分项误判为大类。
    """
    if not any(k in line for k in _CATEGORY_KEYWORDS):
        return False
    if not _SCORE_LINE.search(line):
        return False
    if not _ITEM_PREFIX.match(line):
        return True
    return bool(re.search(r"(?:满分|合计|总计|总分|共)\s*\d+(?:\.\d+)?\s*分", line))


def _clean_category_name(line: str) -> str:
    """大类行 → 干净的大类名称：去编号前缀、去"（满分40分）"等总分括注。"""
    s = _ITEM_PREFIX.sub("", line).strip()
    s = re.sub(r"[（(][^）)]*(?:满分|合计|总计|总分)[^）)]*[）)]\s*$", "", s).strip()
    s = _SCORE_LINE.sub("", s)
    return s.strip(" ：:，,。()（）")


def _extract_materials(text: str) -> list[str]:
    """所需证明材料抽取（仅名称，不匹配素材库，TR-11.2）。"""
    materials: list[str] = []
    seen: set[str] = set()
    for m in _MATERIAL_PAREN.finditer(text):
        chunk = m.group(1)
        for part in re.split(r"[、，,；;]", chunk):
            name = part.strip().strip("（）()。")
            if name and _MATERIAL_KEYWORDS.search(name) and name not in seen:
                seen.add(name)
                materials.append(name)
    # 兜底：括号内直接命中材料关键词
    for m in re.finditer(r"（([^（）]{2,40})）", text):
        chunk = m.group(1)
        for part in re.split(r"[、，,；;]", chunk):
            name = part.strip().strip("。")
            if name and _MATERIAL_KEYWORDS.search(name) and name not in seen:
                seen.add(name)
                materials.append(name)
    return materials


def _parse_score_items(
    lines: list[str], category: str, source_chapter: str, source_stem: str, page_idx: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """从一个大类段内解析评分项。返回 (items, red_flags)。"""
    items: list[dict[str, Any]] = []
    red_flags: list[dict[str, Any]] = []
    for line in lines:
        line = _norm_line(line)
        if not line or _is_category_line(line):
            continue
        score_m = _SCORE_LINE.search(line)
        if not score_m:
            continue
        score = float(score_m.group(1))
        if score > _MAX_ITEM_SCORE:
            continue
        # 评分项名称：分值前的文字（去除编号前缀与括号分值）
        name = _ITEM_PREFIX.sub("", line)
        name = _SCORE_LINE.sub("", name).strip(" ：:，,。()（）")
        if not name or len(name) > 60:
            continue
        materials = _extract_materials(line)
        th = [t.to_dict() for t in thresholds_mod.find_thresholds(line)]
        # 门槛识别不出的原文片段标红（行内有"须/应/提供"但无结构化门槛）
        unrecognized = ""
        if not th and re.search(r"(须|应|需|提供|具备|具有)", line) and len(line) > 15:
            unrecognized = line[:200]
            red_flags.append(
                {
                    "type": "threshold_unrecognized",
                    "category": category,
                    "item": name,
                    "source": source_stem,
                    "detail": f"门槛条件未能结构化识别，需人工核对：{line[:80]}",
                }
            )
        items.append(
            {
                "name": name,
                "score": score,
                "materials": materials,
                "thresholds": th,
                "unrecognized": unrecognized,
                "anchor": {"page_idx": page_idx},
                "source_chapter": source_chapter,
            }
        )
    return items, red_flags


def extract_score_table(
    score_matches: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    """评分表抽取主入口（多来源合并，TR-11.4）。

    score_matches: extract_list.json 中 tech_score/business_score 的 matches
    数组（每项含 chapter_path/snippet/source/constraints/anchor）。
    返回 score_table.json payload（不含 schema_validated，由 schema 模块补）。
    """
    categories: list[dict[str, Any]] = []
    red_flags: list[dict[str, Any]] = []
    total_score = 0.0

    for match in score_matches:
        chapter_path = str(match.get("chapter_path", ""))
        source_stem = str(match.get("source", ""))
        snippet = str(match.get("snippet", ""))
        anchor = match.get("anchor") or {}
        page_idx = int(anchor.get("page_idx", 0))

        lines = snippet.splitlines()
        # 找大类段：含大类关键词+分值的行作为大类标题，其后到下一个大类前的行属于该类
        current_cat: str | None = None
        current_lines: list[str] = []
        segments: list[tuple[str, list[str], int]] = []
        for line in lines:
            if _is_category_line(line):
                if current_cat is not None:
                    segments.append((current_cat, current_lines, page_idx))
                current_cat = _clean_category_name(line)
                current_lines = []
            elif current_cat is not None:
                current_lines.append(line)
        if current_cat is not None:
            segments.append((current_cat, current_lines, page_idx))

        # 若无大类结构，整段归"未分类"
        if not segments:
            segments = [("未分类", lines, page_idx)]

        for cat_name, cat_lines, seg_page in segments:
            items, cat_red = _parse_score_items(
                cat_lines, cat_name, chapter_path, source_stem, seg_page
            )
            red_flags.extend(cat_red)
            if not items:
                continue
            cat_total = sum(i["score"] for i in items)
            total_score += cat_total
            categories.append(
                {
                    "name": cat_name,
                    "source_chapter": chapter_path,
                    "source_stem": source_stem,
                    "items": items,
                    "subtotal": cat_total,
                }
            )

    # TR-11.5：合计校验（≠100 标红披露，不阻断产出）
    expected = 100.0
    score_check = {
        "expected": expected,
        "actual": total_score,
        "ok": abs(total_score - expected) < 0.01,
    }
    if not score_check["ok"]:
        red_flags.append(
            {
                "type": "score_sum_mismatch",
                "detail": f"评分合计 {total_score:g} 分 ≠ 预期 {expected:g} 分，需人工核对",
            }
        )

    return {
        "version": 1,
        "scoring_version": SCORING_VERSION,
        "generated_at": generated_at,
        "categories": categories,
        "total_score_check": score_check,
        "red_flags": red_flags,
        "llm": {"enabled": False, "status": "not_run"},
    }
