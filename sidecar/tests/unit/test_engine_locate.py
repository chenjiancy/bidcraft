"""MinerU 输出定位测试：3.4.5 的 <out>/<stem>/<method>/ 布局与多源隔离。"""

from pathlib import Path

import pytest

from app.parse.engine import MinerUError, _locate_outputs


def _make_layout(base: Path, stem: str, *, method: str | None, with_v2: bool = False) -> None:
    """构造 MinerU 产物布局；method=None 时模拟散落在 <out>/<stem>/ 的旧布局。"""
    d = base / stem / method if method else base / stem
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text(f"# {stem}", encoding="utf-8")
    (d / f"{stem}_content_list.json").write_text("[]", encoding="utf-8")
    (d / f"{stem}_middle.json").write_text("{}", encoding="utf-8")
    (d / "images").mkdir(exist_ok=True)
    if with_v2:
        (d / f"{stem}_content_list_v2.json").write_text("[]", encoding="utf-8")


def test_locates_method_subdir_layout_345(tmp_path: Path) -> None:
    _make_layout(tmp_path, "招标文件正文", method="auto", with_v2=True)
    result = _locate_outputs(tmp_path, tmp_path / "招标文件正文.pdf", [], method="auto")
    assert result.markdown_path == tmp_path / "招标文件正文" / "auto" / "招标文件正文.md"
    assert result.output_dir.name == "auto"
    assert result.content_list_path is not None
    assert result.content_list_path.name == "招标文件正文_content_list.json"
    assert result.middle_json_path is not None
    assert result.images_dir == tmp_path / "招标文件正文" / "auto" / "images"


def test_two_sources_share_out_dir_without_cross_match(tmp_path: Path) -> None:
    """回归：多源共用 raw/，不得因 rglob 兜底拿到另一个源的产物。"""
    _make_layout(tmp_path, "a文件", method="auto")
    _make_layout(tmp_path, "b文件", method="auto")

    for stem in ("a文件", "b文件"):
        result = _locate_outputs(tmp_path, tmp_path / f"{stem}.pdf", [], method="auto")
        assert result.markdown_path.stem == stem
        assert stem in result.markdown_path.parts
        assert result.content_list_path is not None
        assert result.content_list_path.name == f"{stem}_content_list.json"


def test_legacy_layout_without_method_subdir(tmp_path: Path) -> None:
    _make_layout(tmp_path, "olddoc", method=None)
    result = _locate_outputs(tmp_path, tmp_path / "olddoc.pdf", [], method="auto")
    assert result.markdown_path == tmp_path / "olddoc" / "olddoc.md"


def test_missing_markdown_raises_with_log_tail(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    with pytest.raises(MinerUError, match=r"未找到 Markdown 产物[\s\S]*日志线索123"):
        _locate_outputs(tmp_path, tmp_path / "x.pdf", ["日志线索123"], method="auto")
