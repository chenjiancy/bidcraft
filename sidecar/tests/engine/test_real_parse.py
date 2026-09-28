"""TR-8.1/8.2/8.3/8.5 真实样本端到端验证。

仅在装有 MinerU 独立 venv 的开发机运行：
    uv run pytest tests/engine -v
CI（windows-latest，无 GPU/模型/样本）自动 skip；扫描件 OCR 额外标记 slow：
    uv run pytest tests/engine -v -m slow
"""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from app.parse import chapters as chapters_mod
from app.parse import dedupe, engine, preprocess

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = Path(os.environ.get("BIDCRAFT_SAMPLES_ROOT", REPO_ROOT / "samples"))

LIUZHUANG = SAMPLES / "和县柳庄路综合停车场工程监理" / "招标文件正文.pdf"
YUSHAN = SAMPLES / "雨山区2026年老旧小区改造项目EPC总承包监理" / "招标文件.pdf"
HEXIAN_DOC = (
    SAMPLES
    / "和县2026年老旧小区改造项目（EPC总承包）监理采购"
    / "和县2026年老旧小区改造项目（EPC总承包）监理采购文件.doc"
)
DOCX_SAMPLE = SAMPLES / "和县市民文化中心功能恢复及安全隐患排除项目监理" / "招标文件.docx"

pytestmark = pytest.mark.engine


@pytest.fixture
def require_mineru() -> None:
    if engine.mineru_python() is None:
        pytest.skip("未安装 sidecar/.venv-mineru，跳过真实解析测试")


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_engine_probe_available(require_mineru: None) -> None:
    status = _run(engine.probe_status())
    assert status.available is True, status.error
    assert status.version and status.version.startswith("3.")
    # 本机开发机为 RTX 3060 Ti，pipeline 必须吃到 CUDA（OCR 性能前提）
    assert status.cuda_available is True
    assert status.cuda_device


# ---------- TR-8.1：文字版 PDF → Markdown + 带页码坐标的 JSON ----------


def test_text_pdf_produces_markdown_and_bbox(require_mineru: None, tmp_path: Path) -> None:
    assert LIUZHUANG.is_file(), f"缺少样本：{LIUZHUANG}"
    result = _run(engine.run_mineru(LIUZHUANG, tmp_path))

    md = result.markdown_path.read_text(encoding="utf-8")
    assert len(md) > 2_000, "文字版 PDF 的 Markdown 产物应有实质内容"

    assert result.content_list_path is not None, "必须产出 content_list.json（TR-8.1 结构化）"
    blocks = chapters_mod.load_content_list(result.content_list_path)
    assert len(blocks) > 20
    # 字段契约：chapters.py 依赖 type/text/page_idx/bbox（text_level 可缺）
    sample = next(b for b in blocks if b.get("type") == "text" and b.get("text"))
    assert isinstance(sample["page_idx"], int)
    assert "bbox" in sample

    parsed = chapters_mod.split_chapters_from_file(result.content_list_path, "招标文件正文")
    assert parsed["page_count"] > 10
    assert parsed["stats"]["chapter_count"] >= 1, "真实招标文件应切出至少一级章节"


# ---------- TR-8.3：.doc 经 LibreOffice 转 PDF 后可解析 ----------


def test_doc_conversion_via_libreoffice(require_mineru: None, tmp_path: Path) -> None:
    if preprocess.find_soffice() is None:
        pytest.skip("本机未安装 LibreOffice")
    assert HEXIAN_DOC.is_file(), f"缺少样本：{HEXIAN_DOC}"
    work = tmp_path / "work"
    pdf = _run(preprocess.convert_to_pdf(HEXIAN_DOC, work))
    assert pdf.is_file() and pdf.suffix == ".pdf"

    fp = dedupe.pdf_text_fingerprint(pdf)
    assert fp["pages"] and fp["pages"] > 5
    assert fp["chars"] > 1_000, "转换后的 PDF 应有文本层（不是扫描图）"


# ---------- TR-8.5 合成夹具：同名 docx + 其 LibreOffice 导出的同名 pdf ----------


def test_synthetic_same_name_docx_pdf_deduped(require_mineru: None, tmp_path: Path) -> None:
    if preprocess.find_soffice() is None:
        pytest.skip("本机未安装 LibreOffice")
    assert DOCX_SAMPLE.is_file(), f"缺少样本：{DOCX_SAMPLE}"

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    docx = inbox / "招标文件.docx"
    shutil.copy2(DOCX_SAMPLE, docx)
    # 由同一 docx 导出同名 pdf，合成"同一文件的两种格式"场景
    exported_pdf = _run(preprocess.convert_to_pdf(docx, tmp_path / "as_pdf"))

    sources = [
        dedupe.SourceFile(docx, "招标文件.docx"),
        dedupe.SourceFile(exported_pdf, "招标文件.pdf"),
    ]
    groups = dedupe.group_files(sources)
    assert set(groups) == {"招标文件"}
    plan = dedupe.plan_group("招标文件", groups["招标文件"])
    assert plan.primary.ext == ".docx", "优先级应为 docx > pdf（TR-8.5）"
    assert [c.stored_name for c in plan.candidates] == ["招标文件.pdf"]

    # docx 经 LibreOffice 转 PDF 后与同源 pdf 指纹应判同内容
    docx_as_pdf = _run(preprocess.convert_to_pdf(docx, tmp_path / "docx_fp"))
    fp_pdf = dedupe.pdf_text_fingerprint(exported_pdf)
    fp_docx = dedupe.pdf_text_fingerprint(docx_as_pdf)
    assert fp_pdf["chars"] > 1_000
    assert dedupe.same_content(fp_pdf, fp_docx) is True


# ---------- TR-8.2：扫描件（97 页 0 文本层）→ PP-OCRv6 出文字 ----------


@pytest.mark.slow
def test_scanned_pdf_ocr_extracts_text(require_mineru: None, tmp_path: Path) -> None:
    assert YUSHAN.is_file(), f"缺少样本：{YUSHAN}"
    # 前置事实：该样本无文本层
    bare_fp = dedupe.pdf_text_fingerprint(YUSHAN)
    assert bare_fp["pages"] > 50
    assert bare_fp["chars"] == 0, "前置条件：雨山区样本应为纯扫描件（0 文本层）"

    result = _run(engine.run_mineru(YUSHAN, tmp_path, method="auto"))
    md = result.markdown_path.read_text(encoding="utf-8")
    # OCR 必须提取出中文实质内容（而非空 md）
    assert len(md) > 5_000, f"扫描件 OCR 产物过少：{len(md)} 字符"
    assert any("一" <= ch <= "鿿" for ch in md), "OCR 产物应含中文"
    assert result.content_list_path is not None
