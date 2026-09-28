"""项目路径解析与安全文件名单元测试（TR-8.9 隔离 + 路径穿越防护）。"""

import pytest

from app.parse import paths


def test_safe_filename_keeps_chinese_and_ext() -> None:
    assert paths.safe_filename("招标文件正文.pdf") == "招标文件正文.pdf"


def test_safe_filename_replaces_invalid_chars() -> None:
    result = paths.safe_filename("a/b\\c:d*.pdf")
    assert "/" not in result and "\\" not in result and ":" not in result and "*" not in result


def test_safe_filename_reserved_names_fallback() -> None:
    assert paths.safe_filename("con.pdf").startswith("unnamed")
    assert paths.safe_filename("aux.doc") == "unnamed.doc"


def test_safe_filename_strips_trailing_dots() -> None:
    assert paths.safe_filename("ok....") == "ok"


def test_unique_path_appends_counter(tmp_path) -> None:
    first = tmp_path / "f.pdf"
    first.write_text("a", encoding="utf-8")
    second = paths.unique_path(first)
    assert second.name == "f-1.pdf"
    second.write_text("b", encoding="utf-8")
    third = paths.unique_path(first)
    assert third.name == "f-2.pdf"


def test_unique_path_no_collision_returns_self(tmp_path) -> None:
    target = tmp_path / "new.pdf"
    assert paths.unique_path(target) == target


def test_ensure_within_project_accepts_nested(tmp_path) -> None:
    base = tmp_path / "proj"
    target = base / "parse" / "raw" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    assert paths.ensure_within_project(base, target) == target.resolve()


def test_ensure_within_project_rejects_escape(tmp_path) -> None:
    base = (tmp_path / "proj").resolve()
    base.mkdir()
    outside = tmp_path / "secret.pdf"
    outside.write_text("x", encoding="utf-8")
    evil = base / ".." / "secret.pdf"
    with pytest.raises(paths.PathEscapeError):
        paths.ensure_within_project(base, evil)
