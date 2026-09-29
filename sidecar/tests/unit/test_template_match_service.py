"""模板匹配服务单元测试（TR-18.2/18.5/18.7/18.8/18.12）。"""

import json
from pathlib import Path

from app.parse import template_match as tm

# ---------- 相似度计算 ----------


def test_calculate_similarity_perfect_match() -> None:
    parse_chapters = ["投标函", "报价函", "技术方案"]
    template_chapters = ["投标函", "报价函", "技术方案"]
    result = tm.calculate_similarity(parse_chapters, template_chapters, True, True)
    assert result["score"] >= 90
    assert result["agency_match"] is True
    assert result["doc_type_match"] is True


def test_calculate_similarity_partial() -> None:
    parse_chapters = ["投标函", "报价函", "技术方案", "施工组织设计"]
    template_chapters = ["投标函", "报价函"]
    result = tm.calculate_similarity(parse_chapters, template_chapters, True, True)
    # 部分匹配，分数应高于无匹配但被 cap 在 100
    assert result["score"] <= 100
    assert result["chapter_match_rate"] == 0.5


def test_calculate_similarity_no_match() -> None:
    parse_chapters = ["完全不同A", "完全不同B"]
    template_chapters = ["另一类X", "另一类Y"]
    result = tm.calculate_similarity(parse_chapters, template_chapters, False, False)
    assert result["score"] < 50


def test_normalize_chapter_name() -> None:
    assert tm._normalize_chapter_name("1. 投标函") == "投标函"
    assert tm._normalize_chapter_name("  技术方案  ") == "技术方案"
    assert tm._normalize_chapter_name("第一章：报价函") == "第一章：报价函"


# ---------- 机械检查（BP-4） ----------


def test_mechanical_check_placeholder_count(tmp_path: Path) -> None:
    """占位符数量不一致时 is_red_flag=True。"""
    from docx import Document

    doc1 = tmp_path / "a.docx"
    doc2 = tmp_path / "b.docx"
    Document().save(doc1)
    Document().save(doc2)
    # 手动添加占位符到段落文本（通过 XML 操作）
    _add_placeholder_paragraph(doc1, "hello {{name}} world")
    _add_placeholder_paragraph(doc2, "hello {{name}} and {{project}} world")

    result = tm.mechanical_check(doc1, doc2)
    assert result["is_red_flag"] is True
    assert result["placeholder_diff"] == 1


def _add_placeholder_paragraph(doc_path: Path, text: str) -> None:
    """向现有 docx 添加一个含占位符的段落。"""
    from docx import Document

    doc = Document(str(doc_path))
    doc.add_paragraph(text)
    doc.save(str(doc_path))


def test_mechanical_check_same(tmp_path: Path) -> None:
    """占位符数量相同且无表格差异 → 无红标。"""
    from docx import Document

    doc1 = tmp_path / "a.docx"
    doc2 = tmp_path / "b.docx"
    Document().save(doc1)
    Document().save(doc2)
    _add_placeholder_paragraph(doc1, "hello {{name}} world")
    _add_placeholder_paragraph(doc2, "hello {{name}} world")

    result = tm.mechanical_check(doc1, doc2)
    assert result["is_red_flag"] is False
    assert result["placeholder_diff"] == 0


# ---------- Schema 门禁（BP-3） ----------


def test_validate_template_schema_missing_json(tmp_path: Path) -> None:
    ok, errors = tm.validate_template_schema(tmp_path)
    assert not ok
    assert any("template.json 不存在" in e for e in errors)


def test_validate_template_schema_ok(tmp_path: Path) -> None:
    """有效的 template.json + 空章节列表 → schema 通过。"""
    meta = {"chapters": [], "note": "test", "created_at": "2026-01-01T00:00:00Z"}
    (tmp_path / "template.json").write_text(json.dumps(meta), encoding="utf-8")
    ok, errors = tm.validate_template_schema(tmp_path)
    assert ok
    assert errors == []


def test_validate_template_schema_missing_chapters_file(tmp_path: Path) -> None:
    meta = {"chapters": ["chapter_a"], "note": "test", "created_at": "2026-01-01T00:00:00Z"}
    (tmp_path / "template.json").write_text(json.dumps(meta), encoding="utf-8")
    ok, errors = tm.validate_template_schema(tmp_path)
    assert not ok
    assert any("章节文件缺失" in e for e in errors)


# ---------- 关联表构建 ----------


def test_build_association_perfect_match() -> None:
    parse = ["投标函", "报价函", "技术方案"]
    template = ["投标函", "报价函", "技术方案"]
    assoc, unmatched = tm.build_association(parse, template)
    assert len(assoc) == 3
    assert all(a["matched"] for a in assoc)
    assert unmatched == []


def test_build_association_partial_match() -> None:
    parse = ["投标函", "未知章节"]
    template = ["投标函", "报价函"]
    assoc, unmatched = tm.build_association(parse, template)
    assert len(assoc) == 2
    assert assoc[0]["matched"] is True
    # "未知章节" 可能顺序匹配到 "报价函" 或不匹配
    assert len(unmatched) <= 1


def test_build_association_empty() -> None:
    assoc, unmatched = tm.build_association([], [])
    assert assoc == []
    assert unmatched == []


# ---------- 文本归一化 ----------


def test_normalize_text_ignores_whitespace() -> None:
    assert tm._normalize_text("hello   world") == "hello world"
    assert tm._normalize_text("\n\thello\n") == "hello"


# ---------- 段落 diff ----------


def test_text_diff_same() -> None:
    d = tm._text_diff("hello world", "hello world")
    assert d["has_difference"] is False
    assert d["change_lines"] == 0


def test_text_diff_different() -> None:
    d = tm._text_diff("hello world", "hello there")
    assert d["has_difference"] is True
    assert d["change_lines"] > 0
