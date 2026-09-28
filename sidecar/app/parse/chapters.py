"""章节切分与子节结构建立（Task 8 第 4、6 点）。

输入：MinerU 的 ``*_content_list.json``（块序列，标题块带 ``text_level``，
每块带 ``page_idx`` / ``bbox``，满足原文锚定）。

原则（FR-2 第 4 点 + Task 8 噪声容错）：
1. **以正文实质内容为准，目录仅交叉校验**：目录页只用于核对章节齐全性，
   切分边界一律取正文标题；
2. **按内容顺序匹配，不依赖编号数字**：编号跳号/重复不影响切分；
3. 目录页码错乱、目录与正文标题措辞小差异、页眉页脚重复标题等噪声
   一律内部消化（记入 ``noise``，不打扰用户、不进风险清单）；
4. 文字颜色/底纹等格式噪声在 MinerU 文本层已不存在，无需处理。

输出章节树（章 → 子节），内容性质标注（商务/技术子节）属 Task 10，
本模块只建立结构。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------- 标题模式（按层级） ----------

# 第一章 / 第一节 / 第一篇 / 第一部分 / 第一卷
_RE_CHAPTER = re.compile(
    r"^\s*(第\s*[0-9零一二三四五六七八九十百]+\s*[章节篇卷]"
    r"|第\s*[0-9零一二三四五六七八九十百]+\s*部分)\s*[:：.、]?\s*(.*)$"
)
# 一、二、…
_RE_CN_NUM = re.compile(r"^\s*([一二三四五六七八九十百]+)\s*[、.．]\s*(.+)$")
# （一）(一)
_RE_CN_PAREN = re.compile(r"^\s*[（(]\s*([一二三四五六七八九十百]+)\s*[）)]\s*(.+)$")
# 1. / 1、 / 1．
_RE_NUM = re.compile(r"^\s*(\d+)\s*[.、．]\s*(.+)$")
# 1.1 / 1.1.1
_RE_NUM_DOTTED = re.compile(r"^\s*(\d+(?:\.\d+)+)\s*[.、．]?\s*(.+)$")

# 投标文件格式常见无编号章标题（Task 12 会在该章内做子章节，Task 8 先识别）
_BARE_TITLES = {
    "投标函",
    "投标函附录",
    "法定代表人身份证明",
    "授权委托书",
    "投标保证金",
    "开标一览表",
    "资格证明文件",
    "商务响应文件",
    "技术响应文件",
    "报价一览表",
    "投标文件格式",
    "投标人须知",
    "招标公告",
    "投标邀请书",
    "投标邀请",
    "采购需求",
    "评标办法",
    "评分办法",
    "合同条款",
    "合同协议书",
    "工程量清单",
    "封面",
}

_TOC_LEADER_RE = re.compile(r"(?:\.{2,}|…{1,}|·{2,}|—{2,})\s*\d+\s*$")
_TOC_PAGE_RE = re.compile(r"\s\d{1,3}\s*$")
_TOC_TITLE_RE = re.compile(r"^目[\s　]*录$")
_SENTENCE_END_RE = re.compile(r"[。；！？]$")
_MAX_HEADING_LEN = 60

# 无编号但被 MinerU 误标 text_level 的正文/表单噪声（实测监理招标文件）
_FORM_MARK_RE = re.compile(r"[□☑☒√✓]")
_BODY_TAIL_RE = re.compile(r"[：:、，,。；！？）)]\s*$")
_FORM_ENUM_RE = re.compile(r"^[（(]\s*\d+\s*[）)]")

# 同页出现 >=3 个无编号一级标题时，判定为目录残留/文件名列举（真实章标题不会如此堆叠）
_BARE_STACK_PER_PAGE = 3


@dataclass
class Heading:
    text: str  # 完整标题文本
    number: str  # 编号部分（可能为空）
    title: str  # 标题名称部分
    level: int
    page_idx: int
    bbox: list[float] | None
    in_toc: bool = False


@dataclass
class ChapterNode:
    id: str
    seq: int
    number: str
    title: str
    level: int
    page_idx: int
    bbox: list[float] | None
    start_page: int
    end_page: int | None = None
    children: list[ChapterNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "seq": self.seq,
            "number": self.number,
            "title": self.title,
            "level": self.level,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "anchor": {"page_idx": self.page_idx, "bbox": self.bbox},
            "children": [c.to_dict() for c in self.children],
        }


def _norm(text: str) -> str:
    """标题归一化：去全部空白与常见标点差异，用于目录/正文比对与页眉去重。"""
    return re.sub(r"[\s　.．。:：、,，;；()（）]", "", text)


def _match_heading_pattern(text: str) -> tuple[int, str, str] | None:
    """返回 (level, number, title)；非标题返回 None。"""
    if len(text) > _MAX_HEADING_LEN or _SENTENCE_END_RE.search(text):
        return None
    if m := _RE_CHAPTER.match(text):
        body = m.group(2).strip()
        if body and len(body) <= 40:
            return 1, m.group(1).replace(" ", ""), body
        return None
    if m := _RE_NUM_DOTTED.match(text):
        return 2 + m.group(1).count("."), m.group(1), m.group(2).strip()
    if m := _RE_CN_NUM.match(text):
        body = m.group(2).strip()
        if body and len(body) <= 45:
            return 2, f"{m.group(1)}、", body
        return None
    if m := _RE_CN_PAREN.match(text):
        body = m.group(2).strip()
        if body and len(body) <= 45:
            return 3, f"（{m.group(1)}）", body
        return None
    if m := _RE_NUM.match(text):
        body = m.group(2).strip()
        if body and len(body) <= 45:
            return 3, f"{m.group(1)}.", body
        return None
    bare = text.strip()
    if bare in _BARE_TITLES:
        return 1, "", bare
    return None


def _looks_like_body_noise(text: str) -> bool:
    """无编号 text_level 短行是否实为正文/表单噪声（不应进入章节树）。"""
    stripped = text.strip()
    if _FORM_MARK_RE.search(stripped) or _BODY_TAIL_RE.search(stripped):
        return True
    if _FORM_ENUM_RE.match(stripped):
        return True
    # "合同价的2%" 一类表单取值
    if stripped.endswith(("%", "％")) and len(stripped) <= 12:
        return True
    return False


def _looks_like_toc_line(text: str) -> bool:
    return bool(_TOC_LEADER_RE.search(text) or _TOC_PAGE_RE.search(text))


def load_content_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"content_list 格式异常（应为数组）：{path.name}")
    return data


def detect_toc_pages(blocks: list[dict[str, Any]]) -> set[int]:
    """识别目录页：标题样式行密集且普遍带页码/点线引导。

    判定：某页至少 4 行"标题样"文本，其中 >=50% 带页码引导 → 目录页；
    含"目录"字样的页直接纳入。
    """
    by_page: dict[int, list[str]] = {}
    for block in blocks:
        if block.get("type") != "text":
            continue
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        page = int(block.get("page_idx", 0))
        by_page.setdefault(page, []).append(text)

    toc_pages: set[int] = set()
    for page, lines in by_page.items():
        heading_like = [
            ln
            for ln in lines
            if len(ln) <= _MAX_HEADING_LEN
            and (_match_heading_pattern(ln) or _looks_like_toc_line(ln))
        ]
        if any(_TOC_TITLE_RE.fullmatch(ln.strip()) for ln in lines):
            toc_pages.add(page)
        if len(heading_like) >= 4:
            with_page = sum(1 for ln in heading_like if _looks_like_toc_line(ln))
            if with_page / len(heading_like) >= 0.5:
                toc_pages.add(page)
    return toc_pages


def extract_headings(
    blocks: list[dict[str, Any]],
    toc_pages: set[int],
) -> tuple[list[Heading], list[Heading], int]:
    """抽取正文标题与目录条目。

    标题来源：① MinerU 标注 text_level 的块；② 中文编号模式匹配的短行。
    返回 (正文标题, 目录条目, 被内部消化的噪声标题数)。
    """
    body: list[Heading] = []
    toc: list[Heading] = []
    noise_dropped = 0

    for block in blocks:
        if block.get("type") != "text":
            continue
        text = str(block.get("text", "")).strip()
        if not text or len(text) > _MAX_HEADING_LEN:
            continue
        page_idx = int(block.get("page_idx", 0))
        bbox = block.get("bbox")
        bbox_list = [float(x) for x in bbox] if isinstance(bbox, list) else None

        text_level = block.get("text_level")
        match = _match_heading_pattern(text)

        if text_level is not None and not match:
            # MinerU 判定为标题但无编号：过滤表单/正文误标后整行作为标题，level 钳到 1-4
            if _looks_like_body_noise(text):
                noise_dropped += 1
                continue
            level = min(max(int(text_level), 1), 4)
            heading = Heading(
                text=text, number="", title=text, level=level, page_idx=page_idx, bbox=bbox_list
            )
        elif match is not None:
            level, number, title = match
            # MinerU 若给了更可信的 level（章级），以 MinerU 为准做下限修正
            if text_level is not None and level > 1 and int(text_level) == 1:
                level = 1
            heading = Heading(
                text=text,
                number=number,
                title=title,
                level=level,
                page_idx=page_idx,
                bbox=bbox_list,
            )
        else:
            continue

        if page_idx in toc_pages:
            toc.append(heading)
            continue

        # 页眉/页脚重复标题：同层级同标题在前 3 页内已出现则跳过（仅看最近 8 条）
        norm_title = _norm(heading.title)
        if any(
            h.level == heading.level
            and _norm(h.title) == norm_title
            and 0 <= heading.page_idx - h.page_idx <= 3
            for h in body[-8:]
        ):
            continue
        body.append(heading)

    # 同页一级标题堆叠（>=3，含"第X章"编号）：目录残留或"采购文件包括：
    # 第一章…第七章"式文件构成清单，整组丢弃（真实章标题不会多个同页起始）
    bare_l1_by_page: dict[int, list[Heading]] = {}
    for h in body:
        if h.level == 1:
            bare_l1_by_page.setdefault(h.page_idx, []).append(h)
    stacked = [h for hs in bare_l1_by_page.values() if len(hs) >= _BARE_STACK_PER_PAGE for h in hs]
    if stacked:
        noise_dropped += len(stacked)
        stacked_ids = {id(h) for h in stacked}
        body = [h for h in body if id(h) not in stacked_ids]

    return body, toc, noise_dropped


def build_tree(headings: list[Heading], page_count: int) -> list[ChapterNode]:
    """按出现顺序与层级建章节树；计算每章起止页。"""
    roots: list[ChapterNode] = []
    # 栈元素：(level, node)
    stack: list[tuple[int, ChapterNode]] = []
    top_seq = 0

    for heading in headings:
        while stack and stack[-1][0] >= heading.level:
            stack.pop()
        node = ChapterNode(
            id="",  # 建树后统一编号
            seq=0,
            number=heading.number,
            title=heading.title,
            level=heading.level,
            page_idx=heading.page_idx,
            bbox=heading.bbox,
            start_page=heading.page_idx,
        )
        if stack:
            stack[-1][1].children.append(node)
        else:
            top_seq += 1
            node.seq = top_seq
            node.id = f"ch{top_seq}"
            roots.append(node)
        stack.append((heading.level, node))

    # 子节序号 + id
    def _assign(parent: ChapterNode, parent_id: str) -> None:
        for i, child in enumerate(parent.children, start=1):
            child.id = f"{parent_id}.{i}"
            child.seq = i
            _assign(child, child.id)

    for root in roots:
        _assign(root, root.id)

    # 起止页：下一个同级/更高级标题的起始页 -1；最后一个到文档末页
    all_nodes: list[ChapterNode] = []

    def _flatten(nodes: list[ChapterNode]) -> None:
        for n in nodes:
            all_nodes.append(n)
            _flatten(n.children)

    _flatten(roots)
    for i, node in enumerate(all_nodes):
        later = [n for n in all_nodes[i + 1 :] if n.level <= node.level]
        # 同页连续标题时下一标题 start_page 可能等于本标题页，end 不得小于 start
        node.end_page = (
            max(node.start_page, later[0].start_page - 1)
            if later
            else max(page_count - 1, node.start_page)
        )

    return roots


def crosscheck_toc(
    chapters: list[ChapterNode],
    toc_headings: list[Heading],
) -> dict[str, Any]:
    """目录 ↔ 正文章节交叉校验（按顺序+标题归一化模糊匹配，忽略目录页码）。

    噪声（不进风险清单）：目录有正文无、正文有目录无、标题措辞小差异。
    """

    def _flatten(nodes: list[ChapterNode], acc: list[ChapterNode]) -> None:
        for n in nodes:
            acc.append(n)
            _flatten(n.children, acc)

    body_nodes: list[ChapterNode] = []
    _flatten(chapters, body_nodes)

    body_norms = [_norm(n.title) for n in body_nodes]
    noise: list[str] = []
    matched = 0
    cursor = 0
    for toc_item in toc_headings:
        target = _norm(toc_item.title)
        found_idx = -1
        # 顺序匹配：从游标向后找（允许目录漏项/多项）
        for idx in range(cursor, len(body_norms)):
            candidate = body_norms[idx]
            if (
                candidate == target
                or (len(target) >= 4 and target in candidate)
                or (len(candidate) >= 4 and candidate in target)
            ):
                found_idx = idx
                break
        if found_idx >= 0:
            matched += 1
            cursor = found_idx + 1
        else:
            noise.append(f"目录条目未在正文匹配：{toc_item.text}（页码已忽略）")

    top_level = [n for n in body_nodes if n.level == 1]
    toc_top = [h for h in toc_headings if h.level == 1]
    if toc_top and len(toc_top) != len(top_level):
        noise.append(
            f"目录一级标题 {len(toc_top)} 个 vs 正文一级章节 {len(top_level)} 个（按正文为准）"
        )
    return {"matched": matched, "toc_count": len(toc_headings), "noise": noise}


def split_chapters(content_list: list[dict[str, Any]], source_stem: str) -> dict[str, Any]:
    """章节切分主入口：content_list → 章节树 + 目录校验结果。"""
    page_indices = [int(b.get("page_idx", 0)) for b in content_list if "page_idx" in b]
    page_count = max(page_indices) + 1 if page_indices else 0

    toc_pages = detect_toc_pages(content_list)
    body_headings, toc_headings, noise_dropped = extract_headings(content_list, toc_pages)
    chapters = build_tree(body_headings, page_count)
    toc_check = crosscheck_toc(chapters, toc_headings)

    section_count = 0

    def _count(nodes: list[ChapterNode]) -> None:
        nonlocal section_count
        for n in nodes:
            section_count += len(n.children)
            _count(n.children)

    _count(chapters)

    return {
        "source_stem": source_stem,
        "generated_at": datetime.now(UTC).isoformat(),
        "page_count": page_count,
        "toc_pages": sorted(toc_pages),
        "chapters": [c.to_dict() for c in chapters],
        "toc_crosscheck": toc_check,
        "stats": {
            "chapter_count": len(chapters),
            "section_count": section_count,
            "heading_noise_dropped": noise_dropped,
        },
    }


def split_chapters_from_file(content_list_path: Path, source_stem: str) -> dict[str, Any]:
    return split_chapters(load_content_list(content_list_path), source_stem)
