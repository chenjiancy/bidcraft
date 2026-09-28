"""同名多格式去重单元测试（TR-8.5 规则，不含真实文件转换）。"""

import pytest

from app.parse.dedupe import (
    SUPPORTED_EXTS,
    SourceFile,
    group_files,
    plan_group,
    same_content,
)


def _f(tmp_path, name: str) -> SourceFile:
    path = tmp_path / name
    path.write_bytes(b"x")
    return SourceFile(path=path, stored_name=name)


def test_group_by_stem_ignores_ext_and_dedupe_suffix(tmp_path) -> None:
    files = [
        _f(tmp_path, "招标文件正文.docx"),
        _f(tmp_path, "招标文件正文.pdf"),
        _f(tmp_path, "资格证明-1.pdf"),  # unique_path 产生的重名后缀
        _f(tmp_path, "资格证明.doc"),
        _f(tmp_path, "其他文件.pdf"),
    ]
    groups = group_files(files)
    assert set(groups) == {"招标文件正文", "资格证明", "其他文件"}
    assert len(groups["招标文件正文"]) == 2
    assert len(groups["资格证明"]) == 2


def test_primary_priority_docx_doc_pdf(tmp_path) -> None:
    docx = _f(tmp_path, "a.docx")
    doc = _f(tmp_path, "a.doc")
    pdf = _f(tmp_path, "a.pdf")
    decision = plan_group("a", [pdf, doc, docx])
    assert decision.primary is docx
    assert sorted(f.stored_name for f in decision.candidates) == ["a.doc", "a.pdf"]

    decision2 = plan_group("a", [pdf, doc])
    assert decision2.primary is doc


def test_unsupported_ext_rejected(tmp_path) -> None:
    # group_files 对未知扩展名直接抛错（入口校验的双保险）
    bad = _f(tmp_path, "a.txt")
    with pytest.raises(ValueError):
        group_files([bad])
    assert ".txt" not in SUPPORTED_EXTS


# ---------- same_content：以指纹 dict 直接判定 ----------


def _fp(pages: int, text: str) -> dict[str, object]:
    import hashlib

    return {
        "pages": pages,
        "chars": len(text),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
    }


def test_same_content_similar_text() -> None:
    a = _fp(10, "第一章招标公告" * 30)
    b = _fp(10, "第一章招标公告" * 30 + "细微差异")
    assert same_content(a, b) is True


def test_different_content_not_deduped() -> None:
    a = _fp(10, "完全不同的内容甲" * 30)
    b = _fp(12, "毫不相干的正文乙" * 30)
    assert same_content(a, b) is False


def test_two_scanned_files_equal_pages_treated_same() -> None:
    # 双方都无文本层（扫描件）：同名 + 同页数视为同内容
    assert same_content(_fp(97, ""), _fp(97, "")) is True
    assert same_content(_fp(97, ""), _fp(50, "")) is False


def test_one_side_missing_text_is_conservative() -> None:
    # 仅一方无文本层：保守判不同，防误删
    assert same_content(_fp(5, ""), _fp(5, "有文本层")) is False


def test_page_count_gap_over_two_is_different() -> None:
    a = _fp(10, "共同正文" * 40)
    b = _fp(15, "共同正文" * 40)
    assert same_content(a, b) is False
