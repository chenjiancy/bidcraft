"""规则粗分编排（TR-10.1/10.2/10.4/10.5）：chapters.json + content_list → 提取清单。

输入均为已落盘产物的内存形态（纯逻辑，不碰路径/DB）：
- chapters_payload：chapters.json 内容（{"sources": [{source_stem, chapters, ...}]}）；
- content_lists：{source_stem: MinerU content_list 块数组}；
- selected_keys：配置勾选项 key 集合。

输出为 extract_list.json 的 payload（version/rules_version/doc_type/items/
sections_nature/red_flags/llm），由 service 层写盘。
"""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from app.rules import nature as nature_mod
from app.rules import terms as terms_mod
from app.rules.anchor import verify_anchor
from app.rules.catalog import RULES, RULES_VERSION, find_constraints

_SNIPPET_LEN = 240
_SUBTREE_CHAR_CAP = 20_000
_DETECT_PAGE_SPAN = 3  # 术语判定用首 3 页文本

_NORM_RE = re.compile(r"[\s　.．。:：、,，;；()（）]")


def _norm(text: str) -> str:
    return _NORM_RE.sub("", text)


def _block_text(block: dict[str, Any]) -> str:
    return str(block.get("text", "")).strip()


# ---------- 章节树展开与正文映射 ----------


class _Flat:
    """章节树节点的文档序展开（含祖先路径与层级）。"""

    def __init__(self, node: dict[str, Any], path: str) -> None:
        self.node = node
        self.path = path  # 如 "第一章 招标公告 / 一、项目概述"
        self.level = int(node.get("level", 1))
        anchor = node.get("anchor") or {}
        self.page_idx = int(anchor.get("page_idx", 0))
        self.bbox = anchor.get("bbox") if isinstance(anchor.get("bbox"), list) else None
        self.start_page = int(node.get("start_page", self.page_idx))
        self.end_page = int(node.get("end_page") or self.start_page)
        self.title = str(node.get("title", ""))
        self.number = str(node.get("number", ""))
        self.heading_idx: int | None = None  # 在 content_list 中的块下标


def _flatten(nodes: list[dict[str, Any]], parent_path: str = "") -> list[_Flat]:
    out: list[_Flat] = []
    for node in nodes:
        heading = f"{node.get('number', '')}{node.get('title', '')}".strip()
        path = f"{parent_path} / {heading}" if parent_path else heading
        flat = _Flat(node, path)
        out.append(flat)
        out.extend(_flatten(node.get("children") or [], path))
    return out


def _locate_headings(blocks: list[dict[str, Any]], flats: list[_Flat]) -> None:
    """把每个章节节点定位到 content_list 块下标（文档序单调扫描）。

    匹配依据：页码一致 + 归一化文本一致（块文本 = 编号+标题）。
    定位失败的节点保持 heading_idx=None，回退按页码范围取文本。
    """
    cursor = 0
    for flat in flats:
        target = _norm(f"{flat.number}{flat.title}") or _norm(flat.title)
        if not target:
            continue
        for i in range(cursor, len(blocks)):
            block = blocks[i]
            if block.get("type") != "text":
                continue
            page = int(block.get("page_idx", 0))
            if page < flat.page_idx:
                continue
            if page > flat.page_idx:
                break
            if _norm(_block_text(block)) == target:
                flat.heading_idx = i
                cursor = i + 1
                break


def _subtree_blocks(
    blocks: list[dict[str, Any]], flats: list[_Flat], index: int
) -> list[dict[str, Any]]:
    """该节点子树覆盖的正文块（标题块之后、下一个同级或更高级标题之前）。"""
    flat = flats[index]
    if flat.heading_idx is None:
        # 回退：页码范围（含子节页），对标题定位失败的节点仍可用
        return [
            b
            for b in blocks
            if b.get("type") == "text"
            and flat.start_page <= int(b.get("page_idx", 0)) <= flat.end_page
        ]
    end = len(blocks)
    for later in flats[index + 1 :]:
        if later.level <= flat.level and later.heading_idx is not None:
            end = later.heading_idx
            break
    return blocks[flat.heading_idx + 1 : end]


def _subtree_text(blocks: list[dict[str, Any]]) -> str:
    text = "\n".join(t for b in blocks if (t := _block_text(b)))
    return text[:_SUBTREE_CHAR_CAP]


# ---------- 主入口 ----------


def run_extraction(
    chapters_payload: dict[str, Any],
    content_lists: dict[str, list[dict[str, Any]]],
    selected_keys: set[str],
    *,
    generated_at: str,
    llm_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """规则粗分：产出 extract_list.json 的完整 payload（LLM 段由调用方给初始值）。"""
    sources = chapters_payload.get("sources") or []

    # 术语识别：首 N 页文本判型（原文不改写，仅产出类型与术语体系）
    head_text = "\n".join(
        _block_text(b)
        for src in sources
        for b in content_lists.get(str(src.get("source_stem")), [])
        if int(b.get("page_idx", 0)) < _DETECT_PAGE_SPAN
    )
    doc_type = terms_mod.detect_doc_type(head_text)
    term_set = terms_mod.term_set_for(None if doc_type == "未知" else doc_type)

    # 每源：展开章节树、定位标题块、标注子节性质
    per_source: list[dict[str, Any]] = []
    full_texts: dict[str, str] = {}
    sections_nature: dict[str, list[dict[str, Any]]] = {}
    for src in sources:
        stem = str(src.get("source_stem"))
        blocks = content_lists.get(stem, [])
        flats = _flatten(src.get("chapters") or [])
        _locate_headings(blocks, flats)
        full_texts[stem] = "\n".join(t for b in blocks if (t := _block_text(b)))
        records = nature_mod.annotate_tree(src.get("chapters") or [])
        sections_nature[stem] = [asdict(r) for r in records]
        per_source.append({"stem": stem, "blocks": blocks, "flats": flats})

    # 逐项粗分
    items: list[dict[str, Any]] = []
    red_flags: list[dict[str, Any]] = []
    for rule in RULES:
        selected = rule.key in selected_keys
        item: dict[str, Any] = {
            "key": rule.key,
            "label": rule.label,
            "category": rule.category,
            "selected": selected,
            "status": "off",
            "matches": [],
        }
        if not selected:
            items.append(item)
            continue

        norm_keywords = [_norm(k) for k in rule.keywords]
        matches: list[dict[str, Any]] = []
        for src in per_source:
            stem = src["stem"]
            blocks = src["blocks"]
            flats = src["flats"]
            full_text = full_texts[stem]
            for idx, flat in enumerate(flats):
                norm_title = _norm(flat.title)
                if not any(k in norm_title for k in norm_keywords):
                    continue
                subtree = _subtree_blocks(blocks, flats, idx)
                text = _subtree_text(subtree)
                constraints: list[dict[str, Any]] = []
                for b in subtree:
                    bt = _block_text(b)
                    if not bt:
                        continue
                    for c in find_constraints(bt, int(b.get("page_idx", flat.page_idx))):
                        c_dict = c.to_dict()
                        # TR-10.2：约束必须能在原文找到，找不到标红
                        c_dict["anchor_verified"] = verify_anchor(c.text, full_text)
                        constraints.append(c_dict)
                        if not c_dict["anchor_verified"]:
                            red_flags.append(
                                {
                                    "type": "anchor_failed",
                                    "item": rule.key,
                                    "source": stem,
                                    "detail": f"约束未能在原文锚定：{c.text[:80]}",
                                }
                            )
                snippet = re.sub(r"\s+", " ", text).strip()[:_SNIPPET_LEN]
                matches.append(
                    {
                        "source": stem,
                        "chapter_path": flat.path,
                        "heading": f"{flat.number}{flat.title}".strip(),
                        "anchor": {"page_idx": flat.page_idx, "bbox": flat.bbox},
                        "snippet": snippet,
                        "anchor_verified": verify_anchor(flat.title, full_text),
                        "constraints": constraints,
                    }
                )
        item["matches"] = matches
        item["status"] = "found" if matches else "missing"
        if not matches:
            red_flags.append(
                {
                    "type": "item_missing",
                    "item": rule.key,
                    "detail": f"勾选项「{rule.label}」未匹配到章节（规则库粗分，需人工核对）",
                }
            )
        items.append(item)

    return {
        "version": 1,
        "rules_version": RULES_VERSION,
        "generated_at": generated_at,
        "doc_type": {
            "type": doc_type,
            "terms": terms_mod.build_dict_payload(doc_type),
            "term_words": term_set.words,
        },
        "items": items,
        "sections_nature": sections_nature,
        "red_flags": red_flags,
        "llm": llm_info or {"enabled": False, "mode": None, "status": "not_run"},
    }
