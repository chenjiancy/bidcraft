"""``preprocess.convert_to_pdf`` 单测。

覆盖 C6 缺陷：同名 doc/docx 转出的 PDF 会重名，旧实现把唯一化放在转换之后，
对已存在的产物调用 ``unique_path``，返回的 ``-1`` 路径永远不存在。
此处用假的 soffice 子进程模拟转换，不依赖本机 LibreOffice。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.parse import preprocess


class _FakeProc:
    """最小子进程替身：communicate 后置 returncode=0。"""

    returncode: int | None = None

    async def communicate(self) -> tuple[bytes, bytes]:
        self.returncode = 0
        return b"", b""

    def kill(self) -> None:
        self.returncode = -1

    async def wait(self) -> None:
        return None


def _install_fake_soffice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """让 convert_to_pdf 走假 soffice：按 --outdir 位置生成同名 PDF 产物。"""
    fake_soffice = tmp_path / "soffice.exe"
    fake_soffice.write_text("", encoding="utf-8")
    monkeypatch.setattr(preprocess, "find_soffice", lambda: fake_soffice)

    async def _fake_exec(*cmd: str, **_kwargs: object) -> _FakeProc:
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        src = Path(cmd[-1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{src.stem}.pdf").write_text(f"pdf:{src.name}", encoding="utf-8")
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)


def test_convert_to_pdf_returns_real_produced_file(tmp_path, monkeypatch) -> None:
    _install_fake_soffice(monkeypatch, tmp_path)
    src = tmp_path / "a.doc"
    src.write_text("doc", encoding="utf-8")
    out_dir = tmp_path / "work"

    pdf = asyncio.run(preprocess.convert_to_pdf(src, out_dir))

    assert pdf == out_dir / "a.pdf"
    assert pdf.is_file(), "返回值必须指向真实存在的 PDF（C6 回归点）"


def test_convert_to_pdf_unique_name_when_same_name_exists(tmp_path, monkeypatch) -> None:
    _install_fake_soffice(monkeypatch, tmp_path)
    out_dir = tmp_path / "work"
    out_dir.mkdir()
    existing = out_dir / "a.pdf"
    existing.write_text("旧产物", encoding="utf-8")
    src = tmp_path / "a.docx"
    src.write_text("docx", encoding="utf-8")

    pdf = asyncio.run(preprocess.convert_to_pdf(src, out_dir))

    assert pdf == out_dir / "a-1.pdf"
    assert pdf.read_text(encoding="utf-8") == "pdf:a.docx"
    assert existing.read_text(encoding="utf-8") == "旧产物", "旧产物不得被覆盖"


def test_convert_to_pdf_cleans_staging_dir(tmp_path, monkeypatch) -> None:
    _install_fake_soffice(monkeypatch, tmp_path)
    src = tmp_path / "a.doc"
    src.write_text("doc", encoding="utf-8")
    out_dir = tmp_path / "work"

    asyncio.run(preprocess.convert_to_pdf(src, out_dir))

    assert sorted(p.name for p in out_dir.iterdir()) == ["a.pdf"], "不得残留 staging 目录"
