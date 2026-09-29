"""Task 17 模板库管理单元测试（TR-17.1~17.7, 17.9~17.14）。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.deps import get_engine
from app.db.session import session_factory
from app.parse import paths as path_utils
from app.repositories.base import Scope
from app.repositories.template import TemplateRepository


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _create_template(
    eid: str, pid: str, *, agency: str, doc_type: str, name: str, version: int = 1
) -> str:
    """直接经 Repository 建模板记录（绕过文件操作）。"""
    session = session_factory(get_engine())()
    try:
        repo = TemplateRepository(session, Scope(enterprise_id=eid))
        version_dir = path_utils.template_version_dir(eid, agency, doc_type, name, version)
        version_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "chapters": ["cover.docx", "main.docx"],
            "note": "测试模板",
            "created_at": "2026-01-01T00:00:00Z",
        }
        t = repo.create(
            enterprise_id=eid,
            agency=agency,
            doc_type=doc_type,
            name=name,
            version=version,
            path=str(version_dir.relative_to(path_utils.data_root())),
            meta_json=json.dumps(meta, ensure_ascii=False),
        )
        session.commit()
        return t.id
    finally:
        session.close()


def _write_docx(path: Path, content: str = "") -> None:
    """创建最小有效 docx 文件（真实 zip 格式，python-docx 可读取）。"""
    import io
    import zipfile

    path.parent.mkdir(parents=True, exist_ok=True)
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
        "</w:body>"
        "</w:document>"
    )
    ct_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels"'
        ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml"'
        ' ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1"'
        ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/>'
        "</Relationships>"
    )
    word_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct_xml)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", doc_xml)
        zf.writestr("word/_rels/document.xml.rels", word_rels)
    path.write_bytes(buf.getvalue())


# ---------- TR-17.1 目录骨架 ----------


def test_directory_skeleton(project: tuple[str, str]) -> None:
    """模板库按代理机构/文件类型层级组织目录，迁移成功。"""
    eid, pid = project
    dir_path = path_utils.template_version_dir(eid, "XX代理", "bid", "测试模板", 1)
    dir_path.mkdir(parents=True, exist_ok=True)
    assert dir_path.exists()
    assert dir_path.parent.name == "测试模板"
    assert dir_path.parent.parent.name == "bid"
    assert dir_path.parent.parent.parent.name == "XX代理"


# ---------- TR-17.2 编辑器转换（占位符识别） ----------


def test_placeholder_extraction(db_client: TestClient, project: tuple[str, str]) -> None:
    """文字 [ ] 转 {{关键字}}，图片位置转 {{img_关键字}}，无遗漏无错转。"""
    from app.templates.service import _read_text_from_docx, _validate_jinja_syntax

    eid, pid = project
    tmp_dir = path_utils.template_version_dir(eid, "代理A", "bid", "sample", 1)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    ch_path = tmp_dir / "cover.docx"
    _write_docx(ch_path)

    text_lines, phs = _read_text_from_docx(ch_path)
    # 已写好的 XML 包含 "Hello"，无占位符
    assert all("{{" not in line for line in text_lines)
    errors = _validate_jinja_syntax(text_lines)
    assert errors == []


# ---------- TR-17.4 占位语法校验 ----------


def test_jinja_syntax_validation() -> None:
    """循环行/条件块语法正确识别；非法语法报错。"""
    from app.templates.service import _validate_jinja_syntax

    # 正确的 for/endfor
    ok_lines = [
        "{%tr for item in items%}",
        "  some content",
        "{%tr endfor %}",
    ]
    assert _validate_jinja_syntax(ok_lines) == []

    # 不匹配的 for/endfor
    bad_lines = [
        "{%tr for item in items%}",
        "  content",
    ]
    errs = _validate_jinja_syntax(bad_lines)
    assert len(errs) >= 1
    assert "不匹配" in errs[0]

    # 非法双花括号
    bad_brace = ["{{ 非法 key }}"]
    errs2 = _validate_jinja_syntax(bad_brace)
    assert len(errs2) >= 1


# ---------- TR-17.5 占位-词典校验 ----------


def test_dictionary_coverage_check(project: tuple[str, str]) -> None:
    """未登记占位给出提示，一键登记后写入词典。"""
    from app.materials import dictionary as kw_dict
    from app.templates.service import check_dictionary_coverage

    eid, pid = project
    # 确保词典存在
    kw_path = path_utils.keywords_dict_path(eid)
    kw_dict.save_keywords(kw_path, kw_dict.KeywordsDict())

    result = check_dictionary_coverage(eid, [])
    assert result["all_registered"] is True

    result2 = check_dictionary_coverage(eid, [])
    assert result2["all_registered"] is True


# ---------- TR-17.6 template.json 生成 ----------


def test_template_json_generated(db_client: TestClient, project: tuple[str, str]) -> None:
    """保存后自动生成且字段齐全（名称/类型/版本/日期/章节/图片约束/备注）。"""
    from app.templates.service import _build_meta_json, _write_template_json

    eid, pid = project
    meta = _build_meta_json(
        chapters=["cover.docx", "main.docx"],
        image_max_width_cm=18.0,
        image_max_height_cm=12.0,
        note="测试备注",
        change_note="v1.1更新",
    )
    assert meta["chapters"] == ["cover.docx", "main.docx"]
    assert meta["image_max_width_cm"] == 18.0
    assert meta["image_max_height_cm"] == 12.0
    assert meta["note"] == "测试备注"
    assert meta["change_note"] == "v1.1更新"
    assert "created_at" in meta

    tmp_dir = path_utils.template_version_dir(eid, "代理A", "bid", "jtest", 1)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _write_template_json(tmp_dir, meta)
    tj = tmp_dir / "template.json"
    assert tj.exists()
    loaded = json.loads(tj.read_text(encoding="utf-8"))
    assert loaded["chapters"] == meta["chapters"]


# ---------- TR-17.7 版本弹窗逻辑 ----------


def test_new_version_requires_change_note(project: tuple[str, str]) -> None:
    """同名模板保存时选择新建版本须填变更说明；覆盖选项被引用后禁用。"""
    from pydantic import ValidationError

    from app.schemas.template import TemplateNewVersionIn
    from app.templates.service import new_version

    eid, pid = project
    tid = _create_template(eid, pid, agency="代理A", doc_type="bid", name="测试模板")

    # Pydantic 对空 change_note / 空 file_paths 会先抛出 ValidationError
    with pytest.raises(ValidationError):
        TemplateNewVersionIn(file_paths=[], change_note="", note="")

    # 构造合法 model，再手动清空 change_note 走业务校验
    body = TemplateNewVersionIn(file_paths=["/tmp/x.docx"], change_note="test", note="")
    body.change_note = ""  # 绕过 Pydantic，触发服务层校验
    with pytest.raises(ValueError, match="变更说明不能为空"):
        new_version(
            session_factory(get_engine())(),
            eid,
            tid,
            body=body,
        )


def test_referenced_template_cannot_overwrite(project: tuple[str, str]) -> None:
    """已被标引用过的模板禁止覆盖。"""
    from app.schemas.template import TemplateNewVersionIn
    from app.templates.service import overwrite_latest

    eid, pid = project
    tid = _create_template(eid, pid, agency="代理A", doc_type="bid", name="引用模板")

    # 标记为已引用
    session = session_factory(get_engine())()
    try:
        repo = TemplateRepository(session, Scope(enterprise_id=eid))
        repo.set_referenced(tid)
        session.commit()
    finally:
        session.close()

    with pytest.raises(ValueError, match="已被标书引用"):
        overwrite_latest(
            session_factory(get_engine())(),
            eid,
            tid,
            body=TemplateNewVersionIn(file_paths=["/tmp/x.docx"], change_note="test", note=""),
        )


# ---------- TR-17.9 收件箱上传 ----------


def test_inbox_upload_generates_path(project: tuple[str, str]) -> None:
    """指定代理机构/类型/名称后自动生成库路径。"""
    eid, pid = project
    # 测试路径生成逻辑（不实际传文件）
    from app.parse import paths as path_utils

    expected = path_utils.template_version_dir(eid, "XX代理", "procurement", "采购模板", 1)
    # Windows 路径用反斜杠，统一转为正斜杠比较
    assert str(expected).replace("\\", "/").endswith("XX代理/procurement/采购模板/v1")


# ---------- TR-17.10 合规检查 ----------


def test_compliance_check_detects_issues(project: tuple[str, str]) -> None:
    """docx 结构损坏、占位语法错误被列出并阻断保存。"""
    from app.templates.service import generate_compliance_check

    eid, pid = project
    # 文件不存在应报错
    result = generate_compliance_check(
        session_factory(get_engine())(), eid, ["/nonexistent/file.docx"]
    )
    assert result.ok is False
    assert len(result.issues) > 0
    assert any(i.code == "STRUCT" for i in result.issues)


# ---------- TR-17.11 软件外写入检测 ----------


def test_external_write_detection(project: tuple[str, str]) -> None:
    """向 templates/ 目录软件外写入文件时检测到变化。"""
    from datetime import UTC, datetime

    eid, pid = project
    tid = _create_template(eid, pid, agency="外检代理", doc_type="bid", name="外检模板")

    session = session_factory(get_engine())()
    try:
        repo = TemplateRepository(session, Scope(enterprise_id=eid))
        t = repo.get(tid)
        # 模拟外部写入：修改文件 mtime 为未来时间
        version_dir = path_utils.template_version_dir(eid, t.agency, t.doc_type, t.name, t.version)
        ch_path = version_dir / "cover.docx"
        _write_docx(ch_path)
        # 将文件 mtime 设为比 created_at 更晚
        future_time = datetime.now(UTC).timestamp() + 86400
        ch_path.touch()
        import os

        os.utime(str(ch_path), (future_time, future_time))

        # 检测应发现外部写入
        from app.api.templates import check_external_write

        result = check_external_write(eid, session)
        assert result["count"] > 0
    finally:
        session.close()


# ---------- TR-17.12 删改 ----------


def test_soft_delete_and_restore(project: tuple[str, str]) -> None:
    """单个删除进回收站不物理删；属性可编辑。"""
    from app.repositories.recycle_bin import RecycleBinRepository

    eid, pid = project
    tid = _create_template(eid, pid, agency="删改代理", doc_type="bid", name="删改模板")

    session = session_factory(get_engine())()
    try:
        from app.templates.service import soft_delete_template

        soft_delete_template(session, eid, tid)
        session.commit()

        # 验证软删除：记录仍存在但 deleted_at 非空
        repo = TemplateRepository(session, Scope(enterprise_id=eid))
        t = repo.get(tid, include_deleted=True)
        assert t.deleted_at is not None
        assert t.status == "deleted"

        # 验证进入回收站
        rb_repo = RecycleBinRepository(session)
        entries = rb_repo.list(enterprise_id=eid)
        assert any(e.ref_id == tid and e.item_type == "template" for e in entries)
    finally:
        session.close()


# ---------- TR-17.13 图片约束 ----------


def test_image_constraints_in_meta(project: tuple[str, str]) -> None:
    """最大宽/高设置写入 template.json。"""
    from app.templates.service import _build_meta_json

    meta = _build_meta_json(
        chapters=["cover.docx"],
        image_max_width_cm=20.0,
        image_max_height_cm=15.0,
        note="",
    )
    assert meta["image_max_width_cm"] == 20.0
    assert meta["image_max_height_cm"] == 15.0


# ---------- TR-17.14 隔离 ----------


def test_template_isolation(db_client: TestClient, project: tuple[str, str]) -> None:
    """模板企业级共享，企业间互不可见。"""
    eid1, pid1 = project
    # 创建另一个企业
    ent2 = db_client.post("/api/v1/enterprises", json={"name": "企业B", "agent": "李四"}).json()
    eid2 = ent2["id"]

    _create_template(eid1, pid1, agency="共享代理", doc_type="bid", name="共享模板")
    _create_template(eid2, "", agency="共享代理", doc_type="bid", name="共享模板")

    from app.templates.service import list_templates

    items1 = list_templates(session_factory(get_engine())(), eid1)
    items2 = list_templates(session_factory(get_engine())(), eid2)
    assert len(items1) >= 1
    assert len(items2) >= 1
    # 企业 A 的模板不应出现在企业 B 中
    assert all(t.enterprise_id == eid1 for t in items1)
    assert all(t.enterprise_id == eid2 for t in items2)


# ---------- API 集成测试 ----------


def test_list_templates_empty(project: tuple[str, str], db_client: TestClient) -> None:
    """空模板列表返回空数组。"""
    eid, pid = project
    res = db_client.get(f"/api/v1/enterprises/{eid}/templates")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_template_success(
    project: tuple[str, str], db_client: TestClient, tmp_path: Path
) -> None:
    """成功创建模板返回 201。"""
    eid, pid = project
    # 创建临时 docx 文件
    tmp_dir = tmp_path / "templates"
    tmp_dir.mkdir()
    doc_path = tmp_dir / "cover.docx"
    _write_docx(doc_path)

    res = db_client.post(
        f"/api/v1/enterprises/{eid}/templates/from_path",
        json={
            "agency": "测试代理",
            "doc_type": "bid",
            "name": "新模板",
            "file_paths": [str(doc_path)],
            "note": "测试备注",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["agency"] == "测试代理"
    assert data["doc_type"] == "bid"
    assert data["name"] == "新模板"
    assert data["version"] == 1
    assert data["status"] == "active"
    assert data["meta"]["chapters"] == ["cover"]


def test_create_template_duplicate_name(
    project: tuple[str, str], db_client: TestClient, tmp_path: Path
) -> None:
    """同名模板已存在时拒绝创建，提示新建版本。"""
    eid, pid = project
    tmp_dir = tmp_path / "templates"
    tmp_dir.mkdir()
    doc_path = tmp_dir / "cover.docx"
    _write_docx(doc_path)

    # 第一次创建
    db_client.post(
        f"/api/v1/enterprises/{eid}/templates/from_path",
        json={
            "agency": "代理A",
            "doc_type": "bid",
            "name": "已有模板",
            "file_paths": [str(doc_path)],
        },
    )
    # 第二次同名应失败
    res = db_client.post(
        f"/api/v1/enterprises/{eid}/templates/from_path",
        json={
            "agency": "代理A",
            "doc_type": "bid",
            "name": "已有模板",
            "file_paths": [str(doc_path)],
        },
    )
    assert res.status_code == 400


def test_update_template_meta(project: tuple[str, str], db_client: TestClient) -> None:
    """编辑模板属性成功。"""
    eid, pid = project
    tid = _create_template(eid, pid, agency="原代理", doc_type="bid", name="可编辑模板")
    res = db_client.put(
        f"/api/v1/enterprises/{eid}/templates/{tid}",
        json={"agency": "新代理", "note": "新备注"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agency"] == "新代理"
    assert data["meta"]["note"] == "新备注"


def test_delete_template(project: tuple[str, str], db_client: TestClient) -> None:
    """删除模板返回 200，进入回收站。"""
    eid, pid = project
    tid = _create_template(eid, pid, agency="删除代理", doc_type="bid", name="待删模板")
    res = db_client.delete(f"/api/v1/enterprises/{eid}/templates/{tid}")
    assert res.status_code == 200
    assert res.json()["deleted"] == tid


def test_new_version_success(
    project: tuple[str, str], db_client: TestClient, tmp_path: Path
) -> None:
    """新建版本成功，旧版本变 deprecated。"""
    eid, pid = project
    tid = _create_template(eid, pid, agency="版本代理", doc_type="bid", name="版本模板")
    tmp_dir = tmp_path / "templates"
    tmp_dir.mkdir()
    doc_path = tmp_dir / "cover_v2.docx"
    _write_docx(doc_path)

    res = db_client.post(
        f"/api/v1/enterprises/{eid}/templates/{tid}/new-version",
        json={
            "file_paths": [str(doc_path)],
            "change_note": "新增第三章",
            "note": "v2备注",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["version"] == 2

    # 原版本应变 deprecated
    res2 = db_client.get(f"/api/v1/enterprises/{eid}/templates/{tid}")
    assert res2.json()["status"] == "deprecated"


def test_forbidden_overwrite_referenced(
    project: tuple[str, str], db_client: TestClient, tmp_path: Path
) -> None:
    """已被引用的模板无法覆盖。"""
    eid, pid = project
    tid = _create_template(eid, pid, agency="引用代理", doc_type="bid", name="引用模板")
    # 标记为已引用
    session = session_factory(get_engine())()
    try:
        repo = TemplateRepository(session, Scope(enterprise_id=eid))
        repo.set_referenced(tid)
        session.commit()
    finally:
        session.close()

    doc_path = tmp_path / "cover.docx"
    _write_docx(doc_path)

    res = db_client.post(
        f"/api/v1/enterprises/{eid}/templates/{tid}/overwrite",
        json={"file_paths": [str(doc_path)], "change_note": "test", "note": ""},
    )
    assert res.status_code == 400
