"""Task 16 TR-16.3/16.4：FTS5 素材检索索引单元测试。"""

from pathlib import Path

from app.materials import fts5


def _db(tmp_path: Path) -> Path:
    return tmp_path / "fts5.db"


def test_add_and_search_chinese_long_keyword(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "监理资质证书", "住房和城乡建设部颁发")
    fts5.fts5_add(db, "m2", "建造师注册证书", "一级建造师")

    rows = fts5.fts5_search(db, "资质证书", limit=10)
    assert [r["material_id"] for r in rows] == ["m1"]


def test_search_short_keyword_falls_back_to_like(tmp_path: Path) -> None:
    """1-2 字符（trigram 无法命中）走 LIKE 回退。"""
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "监理资质证书", "")

    rows = fts5.fts5_search(db, "资质", limit=10)
    assert [r["material_id"] for r in rows] == ["m1"]


def test_search_matches_ocr_text_column(tmp_path: Path) -> None:
    """多条件查询：应同时命中 name 与 ocr_text 两列。"""
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "扫描件", "注册监理工程师执业印章")

    rows = fts5.fts5_search(db, "监理工程师", limit=10)
    assert [r["material_id"] for r in rows] == ["m1"]


def test_add_is_idempotent(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "监理资质证书", "")
    fts5.fts5_add(db, "m1", "监理资质证书（更新）", "")

    rows = fts5.fts5_search(db, "监理资质", limit=10)
    assert len(rows) == 1
    assert rows[0]["name"] == "监理资质证书（更新）"


def test_remove(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "监理资质证书", "")
    fts5.fts5_remove(db, "m1")

    assert fts5.fts5_search(db, "监理资质", limit=10) == []


def test_search_on_missing_file_returns_empty(tmp_path: Path) -> None:
    assert fts5.fts5_search(tmp_path / "none.db", "监理", limit=10) == []


def test_search_empty_keyword_returns_empty(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "监理资质证书", "")
    assert fts5.fts5_search(db, "   ", limit=10) == []


def test_special_chars_do_not_break_match(tmp_path: Path) -> None:
    """FTS5 MATCH 语法字符需被安全转义，不得抛异常。"""
    db = _db(tmp_path)
    fts5.fts5_add(db, "m1", "资质证书(副本)", "")

    # 输入含双引号/括号，应安全处理不抛异常
    rows = fts5.fts5_search(db, '资质"证书', limit=10)
    assert isinstance(rows, list)
