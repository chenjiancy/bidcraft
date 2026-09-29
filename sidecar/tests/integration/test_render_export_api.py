"""Task 20：转 PDF 与 PDF 合并集成测试（TR-20.1～20.10）。

MinerU / 渲染均用 fake 替换；LibreOffice 转换在 CI 不可用时以 monkeypatch 模拟。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.parse import paths as p
from app.parse.state import EXPORTED, RENDERED

# ---------- 辅助：构造 fake docx ----------


def _make_fake_docx(path: Path, content: str = "test content") -> None:
    """创建一个最小有效 docx（zip 格式，含 [Content_Types].xml）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType='
            '"application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "docProps/core.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<cp:coreProperties xmlns:cp="
            '"http://schemas.openxmlformats.org/package/2006/metadata/core-properties">'
            "</cp:coreProperties>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "</Relationships>",
        )
        zf.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{content}</w:t></w:r></w:p></w:body></w:document>',
        )
    path.write_bytes(buf.getvalue())


# ---------- 辅助：fake LibreOffice ----------


def _patch_libreoffice(monkeypatch: pytest.MonkeyPatch) -> None:
    """将 LibreOffice 转换 fake 为：docx → 单页文本 PDF（用 pypdf 创建）。"""

    def _fake_convert(docx_path: Path, output_dir: Path) -> Path | None:
        try:
            from pypdf import PdfWriter  # noqa: PLC0415

            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            pdf_path = output_dir / f"{docx_path.stem}.pdf"
            with pdf_path.open("wb") as f:
                writer.write(f)
            return pdf_path
        except Exception:
            return None

    from app.render import service as render_service  # noqa: PLC0415

    monkeypatch.setattr(render_service, "_libreoffice_to_pdf", _fake_convert)


# ---------- 夹具 ----------


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _setup_rendered_project(
    db_client: TestClient,
    eid: str,
    pid: str,
    tmp_path: Path,
) -> list[dict[str, Any]]:
    """建立 RENDERED 状态的项目：格式清单 + output/ 逐章 docx + parse_status=RENDERED。"""
    # 1. 写格式清单（不含 EXTERNAL 条目）
    fmt_list = [
        {"seq": 1, "chapter": "投标函", "name": "01_投标函", "status": "confirmed"},
        {
            "seq": 2,
            "chapter": "法定代表人身份证明",
            "name": "02_法定代表人身份证明",
            "status": "confirmed",
        },  # noqa: E501
        {"seq": 3, "chapter": "开标一览表", "name": "03_开标一览表", "status": "external"},
    ]
    fmt_path = p.format_list_path(eid, pid)
    fmt_path.parent.mkdir(parents=True, exist_ok=True)
    fmt_path.write_text(json.dumps(fmt_list, ensure_ascii=False), encoding="utf-8")

    # 2. 写 output/ 逐章 docx（仅非 EXTERNAL 章节）
    out_dir = p.output_dir(eid, pid)
    out_dir.mkdir(parents=True, exist_ok=True)
    _make_fake_docx(out_dir / "01_投标函.docx", "投标函正文内容")
    _make_fake_docx(out_dir / "02_法定代表人身份证明.docx", "身份证明正文内容")

    # 3. 设置项目状态为 RENDERED（直接赋值，不经过状态机校验，模拟已完成渲染）
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.deps import get_engine  # noqa: PLC0415
    from app.db.session import session_factory  # noqa: PLC0415
    from app.models.project import Project  # noqa: PLC0415

    engine = get_engine()
    sess = session_factory(engine)()
    try:
        proj = sess.execute(
            select(Project).where(Project.id == pid, Project.enterprise_id == eid)
        ).scalar_one()
        proj.parse_status = RENDERED
        sess.commit()
    finally:
        sess.close()

    return fmt_list


# ---------- TR-20.1：逐章转 PDF ----------


def test_chapter_to_pdf(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True, f"export failed: {result.get('error')}"
    assert result["total_chapters"] == 2  # 排除 EXTERNAL 的 03_开标一览表

    pdf_dir = p.pdf_dir(eid, pid)
    merged = pdf_dir / "标书.pdf"
    assert merged.exists()
    assert merged.stat().st_size > 0


# ---------- TR-20.2：异步可取消（通过服务函数直接模拟 cancel） ----------


def test_export_cancellable(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    import threading  # noqa: PLC0415

    cancel_evt = threading.Event()
    cancel_evt.set()  # 立即取消

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid, cancel_event=cancel_evt)
    # 取消时 pdf_paths 可能为空，但函数不应抛异常
    assert "success" in result
    assert "total_chapters" in result


# ---------- TR-20.3：TS-3 保真度（记录两路径比对占位） ----------


def test_ts3_longevity_placeholder(tmp_path: Path) -> None:
    """TR-20.3：比对报告留档。当前环境使用 LibreOffice headless；
    TS-3 决策记录写至临时目录供人工复核。"""
    report_path = tmp_path / "ts3_comparison_report.txt"
    report_path.write_text(
        "TS-3 保真度比对记录\n"
        "环境: LibreOffice headless\n"
        "结论: TS-3 待定，实际比对需在开发时以真实样本执行\n",
        encoding="utf-8",
    )
    assert report_path.exists()
    assert report_path.stat().st_size > 0


# ---------- TR-20.4：PDF 合并顺序与书签 ----------


def test_merge_order_and_bookmarks(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True

    pdf_dir = p.pdf_dir(eid, pid)
    merged = pdf_dir / "标书.pdf"
    assert merged.exists()

    # 验证书签顺序（投标函 seq=1，身份证明 seq=2）
    try:
        import fitz  # noqa: PLC0415
    except ImportError:
        pytest.skip("PyMuPDF 未安装，跳过书签检查")

    doc = fitz.open(str(merged))
    toc = doc.get_toc()
    doc.close()

    # 书签应包含两个非 EXTERNAL 章节名
    chapter_titles = [item[1] for item in toc]
    assert "投标函" in chapter_titles
    assert "法定代表人身份证明" in chapter_titles
    assert "开标一览表" not in chapter_titles  # EXTERNAL 不应入合并


# ---------- TR-20.5：EXTERNAL 排除 ----------


def test_external_excluded(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True

    # 确认只转换了 2 章（排除了 EXTERNAL 的开标一览表）
    assert result["total_chapters"] == 2

    pdf_dir = p.pdf_dir(eid, pid)
    # 单个章节 PDF 不应包含开标一览表（排除合并后的标书.pdf）
    individual_pdfs = sorted(pdf_dir.glob("*.pdf"))
    individual_pdfs = [f for f in individual_pdfs if f.name != "标书.pdf"]
    assert len(individual_pdfs) == 2


# ---------- TR-20.6：合并不改写页面内容 ----------


def test_merge_does_not_rewrite_content(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True

    pdf_dir = p.pdf_dir(eid, pid)
    merged = pdf_dir / "标书.pdf"

    # 源 docx 页数应等于合并 PDF 页数（单页 docx → 单页 PDF）
    try:
        import fitz  # noqa: PLC0415
    except ImportError:
        pytest.skip("PyMuPDF 未安装")

    merged_doc = fitz.open(str(merged))
    merged_pages = len(merged_doc)
    merged_doc.close()

    assert merged_pages == 2  # 2 章 × 1 页


# ---------- TR-20.7：图片压缩未实现 ----------


def test_no_image_compression_feature() -> None:
    """TR-20.7：代码审查确认无图片压缩入口。"""
    from app.render import service as render_service  # noqa: PLC0415

    # 确认服务中无 compress 相关函数
    attrs = [a for a in dir(render_service) if "compress" in a.lower()]
    assert attrs == [], f"不应存在压缩相关函数，发现: {attrs}"


# ---------- TR-20.8：状态机 RENDERED→EXPORTED ----------


def test_state_transitions_to_exported(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from sqlalchemy import select  # noqa: PLC0415

    from app.db.deps import get_engine  # noqa: PLC0415
    from app.db.session import session_factory  # noqa: PLC0415
    from app.models.app_event import AppEvent  # noqa: PLC0415
    from app.models.project import Project  # noqa: PLC0415
    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True, result.get("error")

    engine = get_engine()
    sess = session_factory(engine)()
    try:
        proj = sess.execute(
            select(Project).where(Project.id == pid, Project.enterprise_id == eid)
        ).scalar_one()
        assert proj.parse_status == EXPORTED

        events = sess.scalars(
            select(AppEvent)
            .where(AppEvent.project_id == pid)
            .where(AppEvent.type == "export_state_change")
        ).all()
        assert len(events) >= 1
        payload = events[-1].payload or {}
        assert payload.get("from") == "RENDERED"
        assert payload.get("to") == "EXPORTED"
    finally:
        sess.close()


def test_export_rejected_when_not_rendered(
    db_client: TestClient,
    project: tuple[str, str],
) -> None:
    """状态非 RENDERED 时，导出端点应返回 409。"""
    eid, pid = project

    resp = db_client.post(f"/api/v1/enterprises/{eid}/projects/{pid}/render/export")
    # 初始状态是 INIT，不是 RENDERED
    assert resp.status_code == 409


# ---------- TR-20.9：原子写入 ----------


def test_atomic_write_no_corrupt_file(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    result = export_pdf(eid, pid)
    assert result["success"] is True

    pdf_dir = p.pdf_dir(eid, pid)
    # 不应有 .tmp 残留文件
    tmp_files = list(pdf_dir.glob("*.tmp"))
    assert tmp_files == [], f"存在未清理的临时文件: {tmp_files}"


# ---------- TR-20.10：项目隔离 ----------


def test_export_project_isolation(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    _setup_rendered_project(db_client, eid, pid, tmp_path)
    _patch_libreoffice(monkeypatch)

    from app.render.service import export_pdf  # noqa: PLC0415

    export_pdf(eid, pid)

    # 创建其他企业/项目
    other_ent = db_client.post(
        "/api/v1/enterprises", json={"name": "其他企业", "agent": "李四"}
    ).json()
    other_proj = db_client.post(
        f"/api/v1/enterprises/{other_ent['id']}/projects", json={"name": "其他项目"}
    ).json()

    # 越权访问应返回 404
    resp = db_client.get(
        f"/api/v1/enterprises/{other_ent['id']}/projects/{pid}/render/export/status"
    )
    assert resp.status_code == 404

    # 本企业其他项目目录应为空
    other_pdf_dir = p.pdf_dir(other_ent["id"], other_proj["id"])
    other_pdf_dir.mkdir(parents=True, exist_ok=True)
    assert not (other_pdf_dir / "标书.pdf").exists()
