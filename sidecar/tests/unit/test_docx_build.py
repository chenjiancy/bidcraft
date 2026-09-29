"""Task 12 投标文件格式章节化纯逻辑测试（TR-12.1～12.5）。

不跑 MinerU：content_list 用最小手工块，docx 落盘用 tmp_path。
"""

from pathlib import Path

import pytest

from app.parse import docx_build
from app.parse.docx_build import (
    SectionPlan,
    blocks_to_docx,
    collect_blocks,
    find_format_chapter,
    plan_all_sources,
    plan_source,
    render_section,
)


def _node(title, start, end=None, level=1, children=None):
    return {
        "id": f"id-{title}",
        "seq": 1,
        "number": "",
        "title": title,
        "level": level,
        "start_page": start,
        "end_page": end,
        "anchor": {"page_idx": start, "bbox": None},
        "children": children or [],
    }


def _fmt_source(chapters, page_count=10, stem="招标文件"):
    return {"source_stem": stem, "page_count": page_count, "chapters": chapters}


def _text(text, page, level=None):
    block = {"type": "text", "text": text, "page_idx": page}
    if level is not None:
        block["text_level"] = level
    return block


# ---------- 定位与计划 ----------


def test_find_format_chapter_nested_and_cover():
    fmt = _node("第八章 投标文件格式", 5, 9, children=[])
    tree = [_node("第一章 投标人须知", 0, 1), _node("第七章 评标办法", 2, 4), fmt]
    assert find_format_chapter(tree) is fmt


def test_plan_source_not_found_returns_empty_with_note():
    plan = plan_source(_fmt_source([_node("第一章 投标人须知", 0, 4)]), [])
    assert plan.found is False
    assert plan.sections == []
    assert "投标文件格式" in (plan.note or "")


def test_plan_source_direct_children_with_cover_numbering_and_ranges():
    cover = _node("封面", 5, 5, level=2)
    bid_letter = _node("一、投标函", 6, 7, level=2)
    legal_rep = _node("二、法定代表人身份证明", 8, 9, level=2)
    fmt = _node("投标文件格式", 5, 9, children=[cover, bid_letter, legal_rep])

    plan = plan_source(_fmt_source([fmt]), [])

    assert plan.found is True
    assert [s.seq for s in plan.sections] == [0, 1, 2]
    assert [s.kind for s in plan.sections] == ["cover", "section", "section"]
    assert [s.title for s in plan.sections] == ["封面", "一、投标函", "二、法定代表人身份证明"]
    assert plan.sections[0].filename == "00_封面.docx"
    assert plan.sections[1].filename == "01_一、投标函.docx"
    # 页码闭区间，章末节 end_page 兜底到格式章末页
    assert (plan.sections[1].start_page, plan.sections[1].end_page) == (6, 7)
    assert plan.sections[2].end_page == 9
    assert plan.sections[2].checkpoint_key == "docx:招标文件:02"


def test_plan_source_cover_as_sibling_chapter_found_via_full_tree():
    # chapters.py 把"封面"识别为一级章（格式章的同级），整棵树兜底搜索
    cover = _node("封面", 3, 3, level=1)
    fmt = _node(
        "第八章 投标文件格式",
        4,
        8,
        children=[_node("投标函", 4, 6, level=2), _node("授权委托书", 7, 8, level=2)],
    )
    plan = plan_source(_fmt_source([cover, fmt], page_count=9), [])
    assert [s.seq for s in plan.sections] == [0, 1, 2]
    assert plan.sections[0].kind == "cover"
    assert plan.sections[0].start_page == 3


def test_plan_source_fallback_text_level_when_no_children():
    fmt = _node("投标文件格式", 5, 8, children=[])
    blocks = [
        _text("投标文件格式", 5, level=1),
        _text("说明文字", 5),
        _text("投标函", 6, level=2),
        _text("投标函正文", 6),
        _text("授权委托书", 8, level=2),
    ]
    plan = plan_source(_fmt_source([fmt], page_count=9), blocks)

    titles = [(s.seq, s.title, s.start_page, s.end_page) for s in plan.sections]
    assert titles == [(1, "投标函", 6, 7), (2, "授权委托书", 8, 8)]


def test_plan_source_flat_chapter_becomes_single_docx():
    fmt = _node("投标文件格式", 5, 8, children=[])
    blocks = [_text("纯表单内容无标题", 6)]
    plan = plan_source(_fmt_source([fmt], page_count=9), blocks)
    assert len(plan.sections) == 1
    assert plan.sections[0].seq == 1
    assert plan.sections[0].title == "投标文件格式"
    assert (plan.sections[0].start_page, plan.sections[0].end_page) == (5, 8)


def test_plan_all_sources_matches_content_lists_by_stem():
    fmt1 = _node("投标文件格式", 0, 1, children=[_node("投标函", 0, 1, level=2)])
    fmt2 = _node("投标文件格式", 0, 0, children=[])
    payload = {
        "sources": [
            _fmt_source([fmt1], stem="A文件"),
            _fmt_source([fmt2], stem="B文件"),
        ]
    }
    plans = plan_all_sources(payload, {"A文件": [], "B文件": []})
    assert [p.source_stem for p in plans] == ["A文件", "B文件"]
    assert plans[0].found is True
    # B 无 children 且无标题块 → 整章单文件
    assert plans[1].sections[0].title == "投标文件格式"


# ---------- 块收集 ----------


def test_collect_blocks_page_inclusive_and_dedup_heading():
    section = SectionPlan("s", 1, "投标函", "section", 6, 7)
    blocks = [
        _text("投标函", 6, level=2),  # 同页同名标题块 → 跳过
        _text("正文1", 6),
        _text("正文2", 7),
        _text("下一章", 8, level=1),
    ]
    collected = collect_blocks(blocks, section)
    assert [b["text"] for b in collected] == ["正文1", "正文2"]


# ---------- docx 落盘 ----------


def test_blocks_to_docx_text_headings_and_html_table(tmp_path: Path):
    blocks = [
        _text("一级标题", 0, level=1),
        _text("普通段落", 0),
        {
            "type": "table",
            "page_idx": 0,
            "table_body": (
                "<table><tr><th>项</th><th>值</th></tr>"
                "<tr><td>名称</td><td>XX公司</td></tr></table>"
            ),
        },
    ]
    out = tmp_path / "a.docx"
    counters = blocks_to_docx(blocks, out, "投标函")

    assert out.is_file() and out.stat().st_size > 0
    assert counters == {"paragraphs": 1, "tables": 1, "images": 0, "red_flags": 0}

    from docx import Document

    doc = Document(out)
    assert doc.paragraphs[0].text == "投标函"
    assert any(p.text == "普通段落" for p in doc.paragraphs)
    table = doc.tables[0]
    assert table.rows[0].cells[0].text == "项"
    assert table.rows[1].cells[1].text == "XX公司"


def test_blocks_to_docx_markdown_table_fallback(tmp_path: Path):
    blocks = [
        {
            "type": "table",
            "page_idx": 0,
            "text": "| 项 | 值 |\n|---|---|\n| 名称 | XX |",
        }
    ]
    out = tmp_path / "md.docx"
    counters = blocks_to_docx(blocks, out, "t")
    assert counters["tables"] == 1
    assert counters["red_flags"] == 0


def test_blocks_to_docx_image_and_bad_table_are_red_flags(tmp_path: Path):
    blocks = [
        {"type": "image", "page_idx": 0, "img_caption": "盖章示意图"},
        {"type": "table", "page_idx": 0, "table_body": "不是表格"},
    ]
    out = tmp_path / "b.docx"
    counters = blocks_to_docx(blocks, out, "t")
    assert counters["images"] == 1
    assert counters["red_flags"] == 2


def test_blocks_to_docx_empty_range_flags(tmp_path: Path):
    out = tmp_path / "empty.docx"
    counters = blocks_to_docx([], out, "空章节")
    assert counters["red_flags"] == 1
    assert out.is_file()


def test_render_section_writes_per_source_dir_and_filename(tmp_path: Path):
    project_dir = tmp_path
    docx_root = project_dir / "parse" / "docx"
    section = SectionPlan("招标*文件", 1, "投标/函", "section", 0, 1)
    content_lists = {"招标*文件": [_text("投标函正文", 0)]}

    record = render_section(section, content_lists, project_dir, docx_root)

    # 非法文件名字符（/ * 等）被清洗
    out = docx_root / record["file"]
    assert out.is_file()
    assert record["file"].startswith("招标_文件/")
    assert record["file"].endswith("01_投标_函.docx")
    assert record["kind"] == "section"
    assert record["paragraphs"] == 1


def test_render_section_path_escape_rejected(tmp_path: Path):
    section = SectionPlan("s", 1, "t", "section", 0, 0)
    # project_dir 与 docx_root 不在同一根 → 逃逸拒绝
    with pytest.raises(docx_build.paths.PathEscapeError):
        render_section(section, {}, tmp_path / "other", tmp_path / "parse" / "docx")
