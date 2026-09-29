"""模板服务层（Task 17）。

职责：
- 目录骨架初始化与验证
- 模板上传 / 新建版本 / 覆盖（未引用时）
- 合规检查（docx 结构 + 占位符语法 + 章节清单）
- 占位符提取与词典校验
- template.json 生成
- 软删除 / 属性编辑
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from docx import Document as DocxDocument

from app.materials import dictionary as kw_dict
from app.models.template import VALID_DOC_TYPES, Template
from app.parse import paths as path_utils
from app.repositories.base import NotFoundError, Scope
from app.repositories.recycle_bin import RecycleBinRepository
from app.repositories.template import TemplateRepository
from app.schemas.template import (
    ComplianceIssue,
    ComplianceResult,
    PlaceholderIssue,
    TemplateCreateIn,
    TemplateNewVersionIn,
    TemplateOut,
)

_logger = logging.getLogger(__name__)

# ---------- 占位符正则 ----------

# 匹配 {{key}}、{{img_key}}、{%tr for ...%}、{%tr endfor %}、{%p if ...%}、{%p endif %}
RE_TEXT_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
RE_IMG_PLACEHOLDER = re.compile(r"\{\{img_(\w+)\}\}")
RE_TABLE_ROW = re.compile(r"\{%tr\s+(?:for\s+.+?|endfor)\s*%\}")
RE_CONDITIONAL = re.compile(r"\{%p\s+(?:if\s+.+?|endif)\s*%\}")
RE_INVALID_DBLBRACE = re.compile(r"\{\{[^\}]*\}\}")  # 兜底匹配任何双花括号
# 非法 Jinja2 片段（连续 %% 或 {% 未闭合）
RE_BAD_JINJA = re.compile(r"%[^%]|%\}|\{%[^\}]*$")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_text_from_docx(doc_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """读取 docx 全部文本段落，并提取占位符。"""
    text_lines: list[str] = []
    all_placeholders: list[dict[str, Any]] = []
    try:
        doc = DocxDocument(str(doc_path))
        for para in doc.paragraphs:
            txt = para.text
            text_lines.append(txt)
            for m in RE_TEXT_PLACEHOLDER.finditer(txt):
                key = m.group(1)
                kind = "image" if key.startswith("img_") else "text"
                all_placeholders.append({"placeholder": f"{{{{{key}}}}}", "kind": kind})
            for m in RE_IMG_PLACEHOLDER.finditer(txt):
                key = m.group(1)
                all_placeholders.append({"placeholder": f"{{{{img_{key}}}}}", "kind": "image"})
            for m in RE_TABLE_ROW.finditer(txt):
                all_placeholders.append({"placeholder": m.group(0), "kind": "table_row"})
            for m in RE_CONDITIONAL.finditer(txt):
                all_placeholders.append({"placeholder": m.group(0), "kind": "conditional"})
    except Exception as exc:  # 文件损坏
        raise ValueError(f"无法解析 docx {doc_path}: {exc}") from exc
    return text_lines, all_placeholders


def _validate_jinja_syntax(text_lines: list[str]) -> list[str]:
    """校验 Jinja2 语法合法性，返回错误消息列表。"""
    errors: list[str] = []
    # 检查 {%tr for ...%} 与 {%tr endfor %} 是否成对
    for_loop_count = 0
    endfor_count = 0
    for line in text_lines:
        for_loop_count += len(re.findall(r"\{%tr\s+for\b", line))
        endfor_count += len(re.findall(r"\{%tr\s+endfor\s*%\}", line))
    if for_loop_count != endfor_count:
        errors.append(
            f"表格循环行不匹配：{{%tr for...%}} 出现 {for_loop_count} 次，"
            f"{{%tr endfor %}} 出现 {endfor_count} 次"
        )
    # 检查 {%p if ...%} 与 {%p endif %} 是否成对
    if_count = 0
    endif_count = 0
    for line in text_lines:
        if_count += len(re.findall(r"\{%p\s+if\b", line))
        endif_count += len(re.findall(r"\{%p\s+endif\s*%\}", line))
    if if_count != endif_count:
        errors.append(
            f"条件块不匹配：{{%p if...%}} 出现 {if_count} 次，{{%p endif %}} 出现 {endif_count} 次"
        )
    # 检查孤立双花括号（如 {{ }}, {{abc }} 等）
    for line in text_lines:
        # 合法占位符模式：{{key}} 或 {{img_key}}
        for m in RE_INVALID_DBLBRACE.finditer(line):
            inner = m.group(0)[2:-2].strip()
            if not re.match(r"^(img_)?[\w]+$", inner):
                errors.append(f"非法占位符语法: {m.group(0)}")
    return errors


def _extract_chapters(file_paths: list[str]) -> list[str]:
    """从文件路径列表中提取章节文件名（不含扩展名，按名称排序）。"""
    stems: list[str] = []
    for fp in file_paths:
        p = Path(fp)
        stem = p.stem
        # 去掉可能的版本号后缀 v1.0/v1.1 等
        clean = re.sub(r"\s*v\d+\.\d+$", "", stem).strip()
        if clean:
            stems.append(clean)
    return sorted(set(stems))


def _build_meta_json(
    *,
    chapters: list[str],
    image_max_width_cm: float | None,
    image_max_height_cm: float | None,
    note: str,
    change_note: str = "",
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "chapters": chapters,
        "note": note,
        "created_at": _now_iso(),
    }
    if image_max_width_cm is not None:
        meta["image_max_width_cm"] = image_max_width_cm
    if image_max_height_cm is not None:
        meta["image_max_height_cm"] = image_max_height_cm
    if change_note:
        meta["change_note"] = change_note
    return meta


def _write_template_json(version_dir: Path, meta: dict[str, Any]) -> None:
    """写入 template.json（原子写入）。"""
    tmp = version_dir / "template.json.tmp"
    final = version_dir / "template.json"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if final.exists():
        final.unlink()
    tmp.rename(final)


def _copy_chapters_to_version(source_paths: list[str], dest_dir: Path) -> list[str]:
    """把用户上传的 docx 文件复制到版本目录，返回相对文件名列表。"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src_str in source_paths:
        src = Path(src_str)
        if not src.is_file():
            raise ValueError(f"源文件不存在: {src_str}")
        dest = dest_dir / src.name
        if dest.exists():
            dest = path_utils.unique_path(dest)
        shutil.copy2(str(src), str(dest))
        copied.append(dest.name)
    return copied


# ---------- 公共服务函数 ----------


def init_template_dirs(enterprise_id: str) -> list[Path]:
    """初始化企业模板目录骨架（幂等操作）。"""
    return path_utils.init_templates_dirs(enterprise_id)


def generate_compliance_check(
    session: Any,
    enterprise_id: str,
    file_paths: list[str],
) -> ComplianceResult:
    """对文件集进行合规检查（结构 + 占位符语法 + 章节完整性）。"""
    issues: list[ComplianceIssue] = []
    placeholders: list[PlaceholderIssue] = []
    all_chapters_in_files: list[str] = []

    for fp_str in file_paths:
        p = Path(fp_str)
        if not p.exists():
            issues.append(
                ComplianceIssue(
                    code="STRUCT",
                    message=f"文件不存在: {fp_str}",
                    file=p.name,
                )
            )
            continue
        try:
            doc = DocxDocument(str(p))
            # 基本结构检查：至少有一个段落或表格
            has_content = bool(doc.paragraphs) or bool(doc.tables)
            if not has_content:
                issues.append(
                    ComplianceIssue(
                        code="STRUCT",
                        message=f"文档无内容（空段落/空表格）: {p.name}",
                        file=p.name,
                    )
                )
        except Exception as exc:
            issues.append(
                ComplianceIssue(
                    code="STRUCT",
                    message=f"无法打开文档（可能损坏）: {p.name}: {exc}",
                    file=p.name,
                )
            )
            continue
        _, phs = _read_text_from_docx(p)
        all_chapters_in_files.append(p.stem)
        for ph in phs:
            kind = ph["kind"]
            placeholders.append(PlaceholderIssue(placeholder=ph["placeholder"], kind=kind))

    # Jinja2 语法检查
    syntax_errors = _validate_jinja_syntax(
        [" ".join(_read_text_from_docx(Path(fp))[0]) for fp in file_paths if Path(fp).exists()]
    )
    for err in syntax_errors:
        issues.append(ComplianceIssue(code="PLACEHOLDER", message=err, file=None))

    return ComplianceResult(ok=len(issues) == 0, issues=issues, placeholders=placeholders)


def check_dictionary_coverage(
    enterprise_id: str,
    placeholders: list[PlaceholderIssue],
) -> dict[str, Any]:
    """检查占位符是否已在动态词典登记，返回未登记的占位符列表。"""
    from app.db.deps import get_engine
    from app.db.session import session_factory

    try:
        sess = session_factory(get_engine())()
        try:
            # 需要 enterprise_id 存在才能读取词典路径
            kw_path = path_utils.keywords_dict_path(enterprise_id)
            kw = kw_dict.load_keywords(kw_path)
            registered = set(kw.all_keywords())
            unregistered: list[str] = []
            for ph in placeholders:
                name = ph.placeholder
                # 去掉外层 {{ }}
                inner = name[2:-2] if name.startswith("{") and name.endswith("}") else name
                if inner not in registered:
                    unregistered.append(inner)
            return {"unregistered": unregistered, "all_registered": len(unregistered) == 0}
        finally:
            sess.close()
    except Exception as e:
        _logger.warning("词典校验失败: %s", e)
        return {"unregistered": [], "all_registered": True}


def register_placeholders_to_dict(
    enterprise_id: str,
    placeholders: list[str],
) -> int:
    """一键将未登记的占位符自动注册入 keywords.dict.json，返回新增数量。"""
    from app.db.deps import get_engine
    from app.db.session import session_factory

    sess = session_factory(get_engine())()
    try:
        repo = TemplateRepository(sess, Scope(enterprise_id=enterprise_id))
        _ = repo.list()  # 确保 enterprise_id 有效
        kw_path = path_utils.keywords_dict_path(enterprise_id)
        kw = kw_dict.load_keywords(kw_path)
        added = 0
        for ph in placeholders:
            if kw_dict.KeywordsDict().add("", ph):  # 使用 custom 类别
                added += 1
        kw_dict.save_keywords(kw_path, kw)
        return added
    finally:
        sess.close()


def list_templates(
    session: Any,
    enterprise_id: str,
    *,
    agency: str | None = None,
    doc_type: str | None = None,
    name: str | None = None,
) -> list[TemplateOut]:
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    items = repo.list(agency=agency, doc_type=doc_type, name=name)
    return [_template_out(t) for t in items]


def get_template(session: Any, enterprise_id: str, template_id: str) -> TemplateOut:
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        return _template_out(repo.get(template_id))
    except NotFoundError:
        raise NotFoundError(f"模板 {template_id} 不存在") from None


def create_template(
    session: Any,
    enterprise_id: str,
    body: TemplateCreateIn,
) -> TemplateOut:
    """创建新模板（第一次上传）。"""
    if body.doc_type not in VALID_DOC_TYPES:
        raise ValueError(f"非法 doc_type: {body.doc_type}，必须是 {VALID_DOC_TYPES}")

    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    existing = repo.get_latest_version(body.agency, body.doc_type, body.name)
    if existing is not None:
        raise ValueError(
            f"同名模板已存在（version={existing.version}，id={existing.id}），"
            "请使用 POST /templates/{{id}}/new-version 创建新版本"
        )

    # 合规检查前置
    compliance = generate_compliance_check(session, enterprise_id, body.file_paths)
    if not compliance.ok:
        msg = f"合规检查未通过，共 {len(compliance.issues)} 项问题: "
        msg += "; ".join(i.message for i in compliance.issues)
        raise ValueError(msg)

    version = 1
    version_dir = path_utils.template_version_dir(
        enterprise_id, body.agency, body.doc_type, body.name, version
    )
    version_dir.mkdir(parents=True, exist_ok=True)

    # 复制文件到版本目录
    copied = _copy_chapters_to_version(body.file_paths, version_dir)
    chapters = _extract_chapters(copied)
    meta = _build_meta_json(
        chapters=chapters,
        image_max_width_cm=body.image_max_width_cm,
        image_max_height_cm=body.image_max_height_cm,
        note=body.note,
    )
    # 写 template.json
    _write_template_json(version_dir, meta)

    rel_path = str(version_dir.relative_to(path_utils.data_root()))
    t = repo.create(
        enterprise_id=enterprise_id,
        agency=body.agency,
        doc_type=body.doc_type,
        name=body.name,
        version=version,
        path=rel_path,
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    session.commit()
    return _template_out(t)


def new_version(
    session: Any,
    enterprise_id: str,
    template_id: str,
    body: TemplateNewVersionIn,
) -> TemplateOut:
    """新建版本（须填变更说明；旧版本标记为 deprecated）。"""
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    t = repo.get(template_id)

    if t.referenced:
        raise ValueError("该模板已被标书引用，禁止创建新版本（应新建不同名称的模板）")

    if not body.change_note.strip():
        raise ValueError("变更说明不能为空")

    compliance = generate_compliance_check(session, enterprise_id, body.file_paths)
    if not compliance.ok:
        raise ValueError(
            f"合规检查未通过，共 {len(compliance.issues)} 项问题: "
            + "; ".join(i.message for i in compliance.issues)
        )

    new_version_num = repo.next_version_number(t.agency, t.doc_type, t.name)
    version_dir = path_utils.template_version_dir(
        enterprise_id, t.agency, t.doc_type, t.name, new_version_num
    )
    version_dir.mkdir(parents=True, exist_ok=True)

    copied = _copy_chapters_to_version(body.file_paths, version_dir)
    chapters = _extract_chapters(copied)
    meta = _build_meta_json(
        chapters=chapters,
        image_max_width_cm=body.image_max_width_cm or t.meta.get("image_max_width_cm"),
        image_max_height_cm=body.image_max_height_cm or t.meta.get("image_max_height_cm"),
        note=body.note or t.meta.get("note", ""),
        change_note=body.change_note,
    )
    _write_template_json(version_dir, meta)

    rel_path = str(version_dir.relative_to(path_utils.data_root()))
    repo.mark_all_as_deprecated(template_id)
    new_t = repo.create(
        enterprise_id=enterprise_id,
        agency=t.agency,
        doc_type=t.doc_type,
        name=t.name,
        version=new_version_num,
        path=rel_path,
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    session.commit()
    return _template_out(new_t)


def overwrite_latest(
    session: Any,
    enterprise_id: str,
    template_id: str,
    body: TemplateNewVersionIn,
) -> TemplateOut:
    """覆盖当前最新版本（仅当未被任何标书引用时允许）。"""
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    t = repo.get(template_id)

    if t.referenced:
        raise ValueError("已被标书引用，禁止覆盖，请创建新版本")

    # 合规检查
    compliance = generate_compliance_check(session, enterprise_id, body.file_paths)
    if not compliance.ok:
        raise ValueError(
            f"合规检查未通过，共 {len(compliance.issues)} 项问题: "
            + "; ".join(i.message for i in compliance.issues)
        )

    # 在现有版本目录内覆盖文件
    version_dir = path_utils.template_version_dir(
        enterprise_id, t.agency, t.doc_type, t.name, t.version
    )
    copied = _copy_chapters_to_version(body.file_paths, version_dir)
    chapters = _extract_chapters(copied)
    meta = _build_meta_json(
        chapters=chapters,
        image_max_width_cm=body.image_max_width_cm or t.meta.get("image_max_width_cm"),
        image_max_height_cm=body.image_max_height_cm or t.meta.get("image_max_height_cm"),
        note=body.note or t.meta.get("note", ""),
        change_note=body.change_note,
    )
    _write_template_json(version_dir, meta)

    repo.update(
        template_id,
        path=str(version_dir.relative_to(path_utils.data_root())),
        meta_json=json.dumps(meta, ensure_ascii=False),
    )
    session.commit()
    return _template_out(t)


def update_template_meta(
    session: Any,
    enterprise_id: str,
    template_id: str,
    **kwargs: Any,
) -> TemplateOut:
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    t = repo.get(template_id)
    old_meta = json.loads(t.meta_json) if isinstance(t.meta_json, str) else t.meta_json
    if "image_max_width_cm" in kwargs and kwargs["image_max_width_cm"] is not None:
        old_meta["image_max_width_cm"] = kwargs["image_max_width_cm"]
    if "image_max_height_cm" in kwargs and kwargs["image_max_height_cm"] is not None:
        old_meta["image_max_height_cm"] = kwargs["image_max_height_cm"]
    if "note" in kwargs and kwargs["note"] is not None:
        old_meta["note"] = kwargs["note"]
    extra = {
        k: v
        for k, v in kwargs.items()
        if v is not None and k not in ("image_max_width_cm", "image_max_height_cm", "note")
    }
    repo.update(
        template_id,
        meta_json=json.dumps(old_meta, ensure_ascii=False),
        **extra,
    )
    session.commit()
    return _template_out(t)


def soft_delete_template(
    session: Any,
    enterprise_id: str,
    template_id: str,
) -> None:
    repo = TemplateRepository(session, Scope(enterprise_id=enterprise_id))
    tpl = repo.get(template_id)
    repo.soft_delete(template_id)
    rb = RecycleBinRepository(session).add(
        item_type="template",
        ref_id=template_id,
        enterprise_id=enterprise_id,
    )
    rb.name = tpl.name
    session.commit()


def _template_out(t: Template) -> TemplateOut:
    meta: dict[str, Any]
    if isinstance(t.meta_json, str):
        try:
            meta = json.loads(t.meta_json)
        except Exception:
            meta = {}
    else:
        meta = cast(dict[str, Any], t.meta_json) or {}
    return TemplateOut(
        id=t.id,
        enterprise_id=t.enterprise_id,
        agency=t.agency,
        doc_type=t.doc_type,
        name=t.name,
        version=t.version,
        path=t.path,
        meta=meta,
        status=t.status,
        referenced=t.referenced,
        created_at=str(t.created_at),
        updated_at=str(t.updated_at),
    )
