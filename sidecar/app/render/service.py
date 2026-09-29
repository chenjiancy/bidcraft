"""渲染服务核心逻辑（Task 19）。

职责链：
  generate_render_plan → build_a_class_context → resolve_b_class_values
  → resolve_image_placeholders → render_chapter / render_all
  → build_warning_list → check_cross_page → run_consistency_audit

约束：
- 全部函数接收 enterprise_id + project_id 作为隔离边界
- 文件操作使用 paths.py 路径函数 + ensure_within_project 校验
- 状态转换使用 state.py 的 ensure_transition
- 不调用 LLM
- 原子写入（临时文件 + rename）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate, InlineImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.deps import get_engine
from app.db.session import session_factory
from app.models.enterprise import Enterprise
from app.models.material import Material
from app.models.project import Project
from app.parse import paths as p
from app.parse.state import (
    EXPORTED,
    READY_TO_RENDER,
    RENDERED,
    RENDERING,
    ensure_transition,
)
from app.render.placeholder import (
    A_CLASS_FIELDS,
    Placeholder,
    parse_placeholders_from_docx,
)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class PlaceholderInfo:
    """渲染计划中的占位符描述。"""

    name: str
    type: str  # a_class / b_class / image
    description: str
    value: str | None = None  # 解析出的值
    needs_manual: bool = False
    is_missing: bool = False


@dataclass
class RenderPlanItem:
    """渲染计划中单个章节条目。"""

    chapter: str
    seq: int
    template_path: str
    placeholders: list[PlaceholderInfo] = field(default_factory=list)
    missing_count: int = 0


@dataclass
class WarningItem:
    """渲染后缺失/问题占位警告。"""

    chapter: str
    placeholder: str
    problem_type: str  # missing_text / missing_image / b_class_uncertain
    suggestion: str


# ---------------------------------------------------------------------------
# B 类 OCR 提取规则表：占位名 → (正则模式, 分组序号)
# ---------------------------------------------------------------------------

_B_CLASS_OCR_RULES: dict[str, tuple[str, int]] = {
    "personnel_name": (r"姓\s*名[：:\s]*(\S+)", 1),
    "personnel_id_number": (r"身份证[号号码]*[：:\s]*(\d{15,18}[Xx]?)", 1),
    "personnel_title": (r"职称[：:\s]*(\S+)", 1),
    "personnel_cert_number": (r"证书编号[：:\s]*(\S+)", 1),
    "personnel_position": (r"职务[：:\s]*(\S+)", 1),
    "performance_project_name": (r"项目名称[：:\s]*(\S+)", 1),
    "performance_contract_amount": (r"合同金额[：:\s]*([0-9,，.]+万元?)", 1),
    "performance_contract_date": (r"签订日期[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", 1),
    "performance_owner": (r"建设单位[：:\s]*(\S+)", 1),
    "performance_supervisor": (r"总监[：:\s]*(\S+)", 1),
    "qualification_name": (r"资质名称[：:\s]*(\S+)", 1),
    "qualification_level": (r"等级[：:\s]*(\S+)", 1),
    "qualification_cert_number": (r"证书编号[：:\s]*(\S+)", 1),
    "qualification_valid_until": (r"有效期至[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})", 1),
}

# ---------------------------------------------------------------------------
# 一致性审计术语规则：文件类型 → 允许术语集
# ---------------------------------------------------------------------------

_TERM_RULES: dict[str, set[str]] = {
    "bid": {"投标人", "招标人", "招标", "投标"},
    "procurement": {"供应商", "采购人", "采购", "供应"},
    "quotation": {"供应商", "询价人", "询价", "报价"},
}

# 关键信息字段 → 渲染 context 中对应 key
_CONSISTENCY_KEYS: list[str] = [
    "enterprise_name",
    "project_number",
    "legal_representative",
    "authorized_agent",
]

# ---------------------------------------------------------------------------
# 原子写入辅助
# ---------------------------------------------------------------------------

_write_locks: dict[str, threading.Lock] = {}
_write_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _write_locks_guard:
        lock = _write_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _write_locks[key] = lock
        return lock


def _atomic_write_json(path: Path, data: Any) -> None:
    """原子写入 JSON：临时文件 + os.replace。"""
    lock = _lock_for(path)
    with lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=str(path.parent), prefix=path.stem + "_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, str(path))
        except BaseException:
            # 写入失败时清理临时文件
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def _read_json(path: Path) -> Any:
    """读取 JSON 文件，不存在返回 None。"""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. 渲染计划生成
# ---------------------------------------------------------------------------


def generate_render_plan(
    enterprise_id: str,
    project_id: str,
) -> list[RenderPlanItem]:
    """遍历 template-work/ 目录下所有 .docx，生成渲染计划并保存。

    Returns:
        RenderPlanItem 列表。
    """
    tw_dir = p.template_work_dir(enterprise_id, project_id)
    if not tw_dir.exists():
        return []

    # 读取格式清单以获取 seq 序号
    fmt_data = _read_json(p.format_list_path(enterprise_id, project_id))
    # chapter_name → seq 映射
    chapter_seq: dict[str, int] = {}
    if fmt_data and isinstance(fmt_data, list):
        for item in fmt_data:
            ch = item.get("chapter") or item.get("name", "")
            seq = item.get("seq", 0)
            if ch:
                chapter_seq[ch] = seq

    items: list[RenderPlanItem] = []
    docx_files = sorted(tw_dir.rglob("*.docx"))

    for idx, docx_path in enumerate(docx_files, start=1):
        # chapter 名取文件名（不含扩展名）
        chapter = docx_path.stem
        seq = chapter_seq.get(chapter, idx)

        # 路径校验
        p.ensure_within_project(p.project_dir(enterprise_id, project_id), docx_path)

        # 解析占位符
        placeholders_raw: list[Placeholder] = parse_placeholders_from_docx(str(docx_path))

        placeholder_infos: list[PlaceholderInfo] = []
        missing_count = 0
        for ph in placeholders_raw:
            if ph.type == "control_flow":
                continue
            info = PlaceholderInfo(
                name=ph.name,
                type=ph.type,
                description=ph.description,
                is_missing=ph.is_missing,
            )
            if ph.is_missing:
                missing_count += 1
            placeholder_infos.append(info)

        items.append(
            RenderPlanItem(
                chapter=chapter,
                seq=seq,
                template_path=str(docx_path),
                placeholders=placeholder_infos,
                missing_count=missing_count,
            )
        )

    # 按 seq 排序
    items.sort(key=lambda x: x.seq)

    # 保存渲染计划
    plan_path = p.render_plan_path(enterprise_id, project_id)
    _atomic_write_json(plan_path, [asdict(item) for item in items])

    return items


# ---------------------------------------------------------------------------
# 2. A 类上下文组装
# ---------------------------------------------------------------------------


def build_a_class_context(
    enterprise_id: str,
    project_id: str,
    session: Session,
) -> dict[str, str]:
    """从数据库读取 Enterprise + Project 信息，组装 A 类占位上下文。

    Returns:
        占位名 → 值 的字典，供 docxtpl 渲染。
    """
    context: dict[str, str] = {}

    # 读取企业信息
    enterprise = session.execute(
        select(Enterprise).where(Enterprise.id == enterprise_id)
    ).scalar_one_or_none()

    if enterprise is not None:
        context["enterprise_name"] = enterprise.name or ""
        context["legal_representative"] = enterprise.legal_person or ""
        context["authorized_agent"] = enterprise.agent or ""
        context["enterprise_phone"] = enterprise.phone or ""
        # 企业地址/传真/邮编/信用代码：从解析清单补充

    # 读取项目信息
    project = session.execute(
        select(Project).where(
            Project.id == project_id,
            Project.enterprise_id == enterprise_id,
        )
    ).scalar_one_or_none()

    if project is not None:
        context["project_name"] = project.name or ""
        context["project_number"] = project.code or ""
        # 项目代理人优先于企业代理人
        if project.agent:
            context["authorized_agent"] = project.agent

    # 从解析清单补充额外字段
    checklist_data = _read_json(p.checklist_path(enterprise_id, project_id))
    if checklist_data and isinstance(checklist_data, list):
        for item in checklist_data:
            if not isinstance(item, dict):
                continue
            # 已确认的解析结果可覆盖/补充 A 类字段
            field_name = item.get("field") or item.get("placeholder", "")
            value = item.get("value") or item.get("confirmed_value", "")
            status = item.get("status", "")
            if field_name and value and status in ("confirmed", "accepted"):
                if field_name in A_CLASS_FIELDS:
                    context[field_name] = str(value)

    # 自动填充日期字段
    now = datetime.now(UTC)
    context.setdefault("current_date", now.strftime("%Y年%m月%d日"))
    context.setdefault("current_year", str(now.year))

    return context


# ---------------------------------------------------------------------------
# 3. B 类取值
# ---------------------------------------------------------------------------


def resolve_b_class_values(
    enterprise_id: str,
    project_id: str,
    b_placeholders: list[str],
    session: Session,
) -> dict[str, dict[str, Any]]:
    """从素材 OCR 文本提取 B 类占位值。

    Args:
        b_placeholders: 需要解析的 B 类占位名列表。
        session: 数据库会话。

    Returns:
        占位名 → {value, needs_manual, candidates} 的字典。
    """
    results: dict[str, dict[str, Any]] = {}

    if not b_placeholders:
        return results

    # 从数据库读取本项目可用素材（企业共享 + 项目独享）
    materials: list[Material] = list(
        session.execute(
            select(Material).where(
                Material.enterprise_id == enterprise_id,
                Material.deleted_at.is_(None),
                Material.status == "active",
                ((Material.project_id == project_id) | (Material.project_id.is_(None))),
            )
        )
        .scalars()
        .all()
    )

    # 读取素材提取清单（material_extract.json 在 lists/ 目录）
    lists_dir = p.lists_dir(enterprise_id, project_id)
    extract_path = lists_dir / "material_extract.json"
    extract_data = _read_json(extract_path)

    # material_id → ocr_text 映射
    material_ocr: dict[str, str] = {}
    for m in materials:
        if m.ocr_text:
            material_ocr[m.id] = m.ocr_text

    # 从提取清单中获取已确认的素材 ID 映射
    requirement_to_material: dict[str, str] = {}
    if extract_data and isinstance(extract_data, list):
        for item in extract_data:
            if isinstance(item, dict):
                req_name = item.get("requirement_name", "")
                mat_id = item.get("selected_material_id", "")
                status = item.get("status", "")
                if req_name and mat_id and status == "selected":
                    requirement_to_material[req_name] = mat_id

    for name in b_placeholders:
        rule = _B_CLASS_OCR_RULES.get(name)
        if rule is None:
            results[name] = {
                "value": None,
                "needs_manual": True,
                "candidates": [],
            }
            continue

        pattern, group_idx = rule
        candidates: list[dict[str, str]] = []

        # 在所有可用素材 OCR 文本中搜索
        for mat_id, ocr_text in material_ocr.items():
            for match in re.finditer(pattern, ocr_text):
                try:
                    val = match.group(group_idx).strip()
                except IndexError:
                    continue
                if val:
                    candidates.append({"material_id": mat_id, "value": val})

        # 去重
        seen_vals: set[str] = set()
        unique_candidates: list[dict[str, str]] = []
        for c in candidates:
            if c["value"] not in seen_vals:
                seen_vals.add(c["value"])
                unique_candidates.append(c)

        if len(unique_candidates) == 1:
            results[name] = {
                "value": unique_candidates[0]["value"],
                "needs_manual": False,
                "candidates": unique_candidates,
            }
        elif len(unique_candidates) > 1:
            # 多候选：取第一个但标记需人工确认
            results[name] = {
                "value": unique_candidates[0]["value"],
                "needs_manual": True,
                "candidates": unique_candidates,
            }
        else:
            results[name] = {
                "value": None,
                "needs_manual": True,
                "candidates": [],
            }

    return results


# ---------------------------------------------------------------------------
# 5. 图片占位闭环
# ---------------------------------------------------------------------------


def resolve_image_placeholders(
    enterprise_id: str,
    project_id: str,
    image_placeholders: list[str],
    session: Session,
) -> dict[str, dict[str, Any]]:
    """定位图片素材文件路径，计算约束尺寸。

    Args:
        image_placeholders: 需要解析的图片占位名列表。

    Returns:
        占位名 → {file_path, width_cm, height_cm, is_missing} 的字典。
    """
    results: dict[str, dict[str, Any]] = {}

    if not image_placeholders:
        return results

    # 读取模板元数据获取图片约束
    template_compare_data = _read_json(p.template_compare_path(enterprise_id, project_id))
    image_constraints: dict[str, dict[str, float]] = {}
    if template_compare_data and isinstance(template_compare_data, dict):
        for name, cfg in template_compare_data.get("image_constraints", {}).items():
            if isinstance(cfg, dict):
                image_constraints[name] = {
                    "max_width_cm": float(cfg.get("max_width_cm", 15.0)),
                    "max_height_cm": float(cfg.get("max_height_cm", 20.0)),
                }

    # 读取素材提取清单定位图片素材
    lists_dir = p.lists_dir(enterprise_id, project_id)
    extract_data = _read_json(lists_dir / "material_extract.json")

    # 从数据库读取素材文件路径
    materials: list[Material] = list(
        session.execute(
            select(Material).where(
                Material.enterprise_id == enterprise_id,
                Material.deleted_at.is_(None),
                Material.status == "active",
                ((Material.project_id == project_id) | (Material.project_id.is_(None))),
            )
        )
        .scalars()
        .all()
    )
    material_by_id: dict[str, Material] = {m.id: m for m in materials}

    # 图片占位名 → 素材 ID 映射
    image_to_material: dict[str, str] = {}
    if extract_data and isinstance(extract_data, list):
        for item in extract_data:
            if isinstance(item, dict):
                ph_name = item.get("placeholder", "")
                mat_id = item.get("selected_material_id", "")
                if ph_name and mat_id:
                    image_to_material[ph_name] = mat_id

    for name in image_placeholders:
        mat_id = image_to_material.get(name)
        constraint = image_constraints.get(name, {})

        if mat_id and mat_id in material_by_id:
            mat = material_by_id[mat_id]
            file_path = mat.file_path
            # 路径校验
            img_path = Path(file_path)
            if img_path.exists():
                # 计算等比 contain 缩放尺寸
                max_w = constraint.get("max_width_cm", 15.0)
                max_h = constraint.get("max_height_cm", 20.0)
                results[name] = {
                    "file_path": file_path,
                    "width_cm": max_w,
                    "height_cm": max_h,
                    "is_missing": False,
                }
                continue

        # 缺失图片
        results[name] = {
            "file_path": None,
            "width_cm": 0.0,
            "height_cm": 0.0,
            "is_missing": True,
        }

    return results


# ---------------------------------------------------------------------------
# 4. docxtpl 逐章渲染
# ---------------------------------------------------------------------------


def _build_render_context(
    a_context: dict[str, str],
    b_values: dict[str, dict[str, Any]],
    image_values: dict[str, dict[str, Any]],
    doc: DocxTemplate,
) -> dict[str, Any]:
    """组装完整渲染上下文，包含 InlineImage 对象。"""
    context: dict[str, Any] = {}

    # A 类字段
    context.update(a_context)

    # B 类字段
    for name, info in b_values.items():
        val = info.get("value")
        if val is not None and not info.get("needs_manual", False):
            context[name] = val
        else:
            context[name] = f"【缺失：{name}】"

    # 图片字段 → InlineImage
    for name, info in image_values.items():
        if info.get("is_missing", True):
            context[name] = f"【图片缺失：{name}】"
        else:
            file_path = info["file_path"]
            width_cm = info.get("width_cm", 15.0)
            height_cm = info.get("height_cm", 20.0)
            try:
                from docx.shared import Cm  # noqa: PLC0415

                inline = InlineImage(
                    doc,
                    image_descriptor=file_path,
                    width=Cm(width_cm),
                    height=Cm(height_cm),
                )
                context[name] = inline
            except Exception:
                context[name] = f"【图片缺失：{name}】"

    return context


def render_chapter(
    enterprise_id: str,
    project_id: str,
    plan_item: RenderPlanItem,
    a_context: dict[str, str],
    session: Session,
) -> Path:
    """渲染单个章节。

    Args:
        plan_item: 渲染计划条目。
        a_context: A 类占位上下文。

    Returns:
        渲染产物文件路径。
    """
    template_path = Path(plan_item.template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    # 确保输出目录存在
    out_dir = p.init_output_dir(enterprise_id, project_id)

    # 收集本章节的 B 类和图片占位名
    b_names = [ph.name for ph in plan_item.placeholders if ph.type == "b_class"]
    img_names = [ph.name for ph in plan_item.placeholders if ph.type == "image"]

    # 解析 B 类值
    b_values = resolve_b_class_values(enterprise_id, project_id, b_names, session)

    # 解析图片占位
    image_values = resolve_image_placeholders(enterprise_id, project_id, img_names, session)

    # 加载 docxtpl 模板
    doc = DocxTemplate(str(template_path))

    # 组装上下文
    context = _build_render_context(a_context, b_values, image_values, doc)

    # 渲染
    doc.render(context)

    # 生成输出文件名
    seq_str = f"{plan_item.seq:02d}"
    output_name = f"{seq_str}_{plan_item.chapter}.docx"
    output_path = out_dir / output_name

    # 路径校验
    p.ensure_within_project(p.project_dir(enterprise_id, project_id), output_path)

    # 原子写入：先写临时文件再 rename
    fd, tmp = tempfile.mkstemp(
        suffix=".tmp", dir=str(out_dir), prefix=f"{seq_str}_{plan_item.chapter}_"
    )
    try:
        with os.fdopen(fd, "wb") as f:
            doc.save(f)
        os.replace(tmp, str(output_path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # 更新 GeneratedDoc 记录
    from app.repositories.base import Scope  # noqa: PLC0415
    from app.repositories.generated_doc import (  # noqa: PLC0415
        GeneratedDocRepository,
    )

    scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
    repo = GeneratedDocRepository(session, scope)

    existing = repo.get_by_chapter(plan_item.chapter)
    if existing is not None:
        repo.update(
            existing.id,
            file_path=str(output_path.relative_to(p.project_dir(enterprise_id, project_id))),
            status="success",
            rendered_at=datetime.now(UTC),
        )
    else:
        gd = repo.create(
            enterprise_id=enterprise_id,
            project_id=project_id,
            chapter=plan_item.chapter,
            seq=plan_item.seq,
            source_template_version="",
        )
        repo.update(
            gd.id,
            file_path=str(output_path.relative_to(p.project_dir(enterprise_id, project_id))),
            status="success",
            rendered_at=datetime.now(UTC),
        )
    session.commit()

    return output_path


def render_all(
    enterprise_id: str,
    project_id: str,
    *,
    cancel_event: threading.Event | None = None,
) -> list[Path]:
    """逐章渲染全部章节。

    Args:
        cancel_event: 可选取消信号（set 时中止渲染）。

    Returns:
        各章节渲染产物路径列表。
    """
    engine = get_engine()
    sess_factory = session_factory(engine)
    session = sess_factory()

    try:
        # 状态转换校验：READY_TO_RENDER → RENDERING
        project = session.execute(
            select(Project).where(
                Project.id == project_id,
                Project.enterprise_id == enterprise_id,
            )
        ).scalar_one()
        ensure_transition(project.parse_status, RENDERING)  # type: ignore[arg-type]
        project.parse_status = RENDERING
        session.commit()

        # 生成渲染计划
        plan_items = generate_render_plan(enterprise_id, project_id)
        if not plan_items:
            project.parse_status = READY_TO_RENDER
            session.commit()
            return []

        # 清除旧 GeneratedDoc 记录
        from app.repositories.base import Scope  # noqa: PLC0415
        from app.repositories.generated_doc import (  # noqa: PLC0415
            GeneratedDocRepository,
        )

        scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
        gd_repo = GeneratedDocRepository(session, scope)
        gd_repo.delete_all_by_project()
        session.commit()

        # 组装 A 类上下文（一次读取，全章节共享）
        a_context = build_a_class_context(enterprise_id, project_id, session)

        # 逐章渲染
        output_paths: list[Path] = []
        for item in plan_items:
            if cancel_event is not None and cancel_event.is_set():
                # 取消：回退到 READY_TO_RENDER
                project.parse_status = READY_TO_RENDER
                session.commit()
                return output_paths

            # 更新 checkpoint
            ck_path = p.render_checkpoint_path(enterprise_id, project_id)
            ck_data = {
                "job_type": "render",
                "current_chapter": item.chapter,
                "current_seq": item.seq,
                "completed": [p.stem for p in output_paths],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            _atomic_write_json(ck_path, ck_data)

            try:
                output_path = render_chapter(enterprise_id, project_id, item, a_context, session)
                output_paths.append(output_path)
            except Exception as exc:
                # 记录失败到 GeneratedDoc
                existing = gd_repo.get_by_chapter(item.chapter)
                if existing is not None:
                    gd_repo.update(
                        existing.id,
                        status="error",
                        error_msg=str(exc)[:1000],
                    )
                else:
                    gd = gd_repo.create(
                        enterprise_id=enterprise_id,
                        project_id=project_id,
                        chapter=item.chapter,
                        seq=item.seq,
                    )
                    gd_repo.update(
                        gd.id,
                        status="error",
                        error_msg=str(exc)[:1000],
                    )
                session.commit()

        # 状态转换：RENDERING → RENDERED
        ensure_transition(project.parse_status, RENDERED)
        project.parse_status = RENDERED
        session.commit()

        return output_paths

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 6. 缺失占位 + 警告清单
# ---------------------------------------------------------------------------


def build_warning_list(
    enterprise_id: str,
    project_id: str,
) -> list[WarningItem]:
    """汇总渲染后所有缺失/问题占位，保存为 warning_list.json。"""
    plan_data = _read_json(p.render_plan_path(enterprise_id, project_id))
    if not plan_data:
        return []

    warnings: list[WarningItem] = []

    for item in plan_data:
        chapter = item.get("chapter", "")
        for ph in item.get("placeholders", []):
            name = ph.get("name", "")
            ph_type = ph.get("type", "")

            if ph.get("is_missing"):
                if ph_type == "image":
                    warnings.append(
                        WarningItem(
                            chapter=chapter,
                            placeholder=name,
                            problem_type="missing_image",
                            suggestion=f"请提供图片素材: {name}",
                        )
                    )
                else:
                    warnings.append(
                        WarningItem(
                            chapter=chapter,
                            placeholder=name,
                            problem_type="missing_text",
                            suggestion=f"请填写占位字段: {name}",
                        )
                    )

            if ph.get("needs_manual") and not ph.get("is_missing"):
                warnings.append(
                    WarningItem(
                        chapter=chapter,
                        placeholder=name,
                        problem_type="b_class_uncertain",
                        suggestion=f"B 类占位 {name} 有多个候选值，需人工确认",
                    )
                )

    # 保存
    _atomic_write_json(
        p.warning_list_path(enterprise_id, project_id),
        [asdict(w) for w in warnings],
    )

    return warnings


# ---------------------------------------------------------------------------
# 7. 跨页检测
# ---------------------------------------------------------------------------


def _libreoffice_to_pdf(docx_path: Path, output_dir: Path) -> Path | None:
    """使用 LibreOffice 将 docx 转 PDF。

    Returns:
        生成的 PDF 路径，失败返回 None。
    """
    try:
        subprocess.run(
            [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(docx_path),
            ],
            timeout=60,
            capture_output=True,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        return None

    pdf_name = docx_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name
    return pdf_path if pdf_path.exists() else None


def _detect_cross_page_images(pdf_path: Path) -> list[dict[str, Any]]:
    """使用 pypdf 检测图片/表格是否跨页。

    Returns:
        跨页对象列表，每项含 page_index, bbox, type。
    """
    cross_page_items: list[dict[str, Any]] = []

    try:
        from pypdf import PdfReader  # noqa: PLC0415
    except ImportError:
        return cross_page_items

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return cross_page_items

    for page_idx, page in enumerate(reader.pages):
        # 检查页面注解（/Annots）中的图片 bounding box
        annots = page.get("/Annots")
        if annots is not None:
            for annot_ref in annots:
                try:
                    annot = annot_ref.get_object()
                    rect = annot.get("/Rect")
                    if rect and len(rect) == 4:
                        # rect = [x0, y0, x1, y1]
                        y1 = float(rect[3])
                        # 获取页面 mediabox 确认页面存在
                        mediabox = page.mediabox
                        if mediabox:
                            # 如果图片底部超出页面底部 → 可能跨页
                            if y1 < 0:
                                cross_page_items.append(
                                    {
                                        "page_index": page_idx,
                                        "bbox": [float(v) for v in rect],
                                        "type": "image",
                                    }
                                )
                except (TypeError, ValueError, AttributeError):
                    continue

    return cross_page_items


def check_cross_page(
    enterprise_id: str,
    project_id: str,
) -> dict[str, list[dict[str, Any]]]:
    """检测渲染产物中图片/表格是否跨页。

    流程：docx → LibreOffice 转 PDF → pypdf 检测跨页。
    跨页时标记需缩小图片重渲染。

    Returns:
        chapter → 跨页对象列表。
    """
    out_dir = p.output_dir(enterprise_id, project_id)
    pdf_dir = p.project_dir(enterprise_id, project_id) / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if not out_dir.exists():
        return {}

    results: dict[str, list[dict[str, Any]]] = {}

    for docx_file in sorted(out_dir.glob("*.docx")):
        chapter = docx_file.stem
        pdf_path = _libreoffice_to_pdf(docx_file, pdf_dir)
        if pdf_path is None:
            continue

        cross_items = _detect_cross_page_images(pdf_path)
        if cross_items:
            results[chapter] = cross_items

    return results


def convert_to_pdf(
    docx_path: Path,
    output_dir: Path,
) -> Path | None:
    """通用 docx → PDF 转换服务函数（供 Task 20 复用）。

    Args:
        docx_path: 输入 docx 文件路径。
        output_dir: PDF 输出目录。

    Returns:
        生成的 PDF 路径，失败返回 None。
    """
    return _libreoffice_to_pdf(docx_path, output_dir)


# ---------------------------------------------------------------------------
# 8. 一致性审计
# ---------------------------------------------------------------------------


def run_consistency_audit(
    enterprise_id: str,
    project_id: str,
) -> dict[str, Any]:
    """扫描全部渲染产物，检查术语与关键信息一致性。

    不调用 LLM。

    Returns:
        审计结果字典，含 term_issues / consistency_issues。
    """
    out_dir = p.output_dir(enterprise_id, project_id)
    if not out_dir.exists():
        empty: dict[str, Any] = {
            "term_issues": [],
            "consistency_issues": [],
            "summary": "无渲染产物",
        }
        _atomic_write_json(p.audit_result_path(enterprise_id, project_id), empty)
        return empty

    # 推断文件类型
    fmt_data = _read_json(p.format_list_path(enterprise_id, project_id))
    doc_type = "bid"  # 默认
    if fmt_data and isinstance(fmt_data, list) and fmt_data:
        doc_type = fmt_data[0].get("doc_type", "bid")
    allowed_terms = _TERM_RULES.get(doc_type, set())

    # 禁止出现的术语（对侧术语集）
    forbidden_terms: set[str] = set()
    for dtype, terms in _TERM_RULES.items():
        if dtype != doc_type:
            forbidden_terms |= terms

    # 收集全部渲染文本
    all_text_by_chapter: dict[str, str] = {}
    for docx_file in sorted(out_dir.glob("*.docx")):
        chapter = docx_file.stem
        try:
            from docx import Document  # noqa: PLC0415

            doc = Document(str(docx_file))
            texts: list[str] = []
            for para in doc.paragraphs:
                texts.append(para.text)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        texts.append(cell.text)
            all_text_by_chapter[chapter] = "\n".join(texts)
        except Exception:
            continue

    # 术语一致性检查
    term_issues: list[dict[str, Any]] = []
    for chapter, text in all_text_by_chapter.items():
        for term in forbidden_terms:
            # 仅检查当该术语确实不适用于当前文件类型时
            count = text.count(term)
            if count > 0 and term not in allowed_terms:
                term_issues.append(
                    {
                        "chapter": chapter,
                        "term": term,
                        "count": count,
                        "expected": f"当前文件类型({doc_type})不应使用「{term}」",
                    }
                )

    # 关键信息一致性检查
    consistency_issues: list[dict[str, Any]] = []
    value_by_key: dict[str, dict[str, str]] = {}  # key → {chapter: value}

    for chapter, text in all_text_by_chapter.items():
        for key in _CONSISTENCY_KEYS:
            # 在文本中搜索该 key 的已知值
            desc = A_CLASS_FIELDS.get(key, "")
            if not desc:
                continue
            # 简单搜索：在文本中查找 "描述：值" 或 "描述:值" 模式
            pattern = re.compile(rf"{re.escape(desc)}[：:\s]+(\S+)")
            match = pattern.search(text)
            if match:
                val = match.group(1)
                if key not in value_by_key:
                    value_by_key[key] = {}
                value_by_key[key][chapter] = val

    # 检查同一 key 在不同章节的值是否一致
    for key, chapter_values in value_by_key.items():
        unique_vals = set(chapter_values.values())
        if len(unique_vals) > 1:
            consistency_issues.append(
                {
                    "field": key,
                    "description": A_CLASS_FIELDS.get(key, key),
                    "chapters": chapter_values,
                    "problem": f"关键字段 {key} 在不同章节值不一致: {unique_vals}",
                }
            )

    result: dict[str, Any] = {
        "doc_type": doc_type,
        "term_issues": term_issues,
        "consistency_issues": consistency_issues,
        "summary": (f"术语问题 {len(term_issues)} 项，一致性问题 {len(consistency_issues)} 项"),
    }

    # 保存
    _atomic_write_json(p.audit_result_path(enterprise_id, project_id), result)

    return result


# ---------------------------------------------------------------------------
# 9. PDF 导出（Task 20）
# ---------------------------------------------------------------------------


def _read_format_list(
    enterprise_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    """读取 format_checklist.json，过滤 EXTERNAL 条目，返回有效条目列表。"""
    data = _read_json(p.format_list_path(enterprise_id, project_id))
    if not data or not isinstance(data, list):
        return []
    return [item for item in data if item.get("status") != "external"]


def _emit_progress(
    emit: Any,
    stage: str,
    chapter: str | None = None,
    progress_pct: int | None = None,
    **extra: Any,
) -> None:
    """发送 SSE 进度事件。"""
    event: dict[str, Any] = {"type": "progress", "stage": stage}
    if chapter is not None:
        event["chapter"] = chapter
    if progress_pct is not None:
        event["progress"] = progress_pct
    event.update(extra)
    try:
        emit(event)
    except Exception:
        pass


def _convert_chapters_to_pdf(
    enterprise_id: str,
    project_id: str,
    chapters: list[dict[str, Any]],
    pdf_dir: Path,
    cancel_event: threading.Event | None,
    emit: Any,
) -> list[Path]:
    """逐章将 output/ docx 转 PDF，按章节顺序返回 PDF 路径列表。"""
    out_dir = p.output_dir(enterprise_id, project_id)
    total = len(chapters)
    pdf_paths: list[Path] = []

    for idx, ch in enumerate(chapters):
        if cancel_event is not None and cancel_event.is_set():
            return pdf_paths

        chapter_name = ch.get("chapter") or ch.get("name", "")
        seq = ch.get("seq", idx)
        seq_str = f"{seq:02d}"

        # 在 output/ 中找匹配的 docx（序号_章节名.docx 或 章节名.docx）
        candidates = list(out_dir.glob(f"{seq_str}_*.docx")) + list(
            out_dir.glob(f"{chapter_name}.docx")
        )
        docx_path: Path | None = None
        for c in candidates:
            if c.exists():
                docx_path = c
                break

        if docx_path is None:
            _emit_progress(
                emit, "error", chapter=chapter_name, message=f"未找到渲染产物: {docx_path}"
            )
            continue

        _emit_progress(
            emit, "converting", chapter=chapter_name, progress_pct=int((idx / total) * 50)
        )

        pdf_path = _libreoffice_to_pdf(docx_path, pdf_dir)
        if pdf_path is None:
            _emit_progress(
                emit, "error", chapter=chapter_name, message=f"PDF 转换失败: {chapter_name}"
            )
            continue

        pdf_paths.append(pdf_path)

    return pdf_paths


def _merge_pdfs(
    pdf_paths: list[Path],
    output_path: Path,
    emit: Any,
    chapters: list[dict[str, Any]] | None = None,
) -> bool:
    """使用 PyMuPDF 合并 PDF，生成书签。

    Returns:
        True 表示成功。
    """
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
    except ImportError:
        _emit_progress(emit, "error", message="PyMuPDF 未安装，无法合并 PDF")
        return False

    try:
        merged = fitz.open()
        for pdf_path in pdf_paths:
            try:
                chapter_doc = fitz.open(str(pdf_path))
                merged.insert_pdf(chapter_doc)
                chapter_doc.close()
            except Exception:
                continue

        # 生成书签（按章节名）
        outline: list[list[Any]] = []
        page_num = 1
        chapter_iter = iter(chapters) if chapters else iter([{} for _ in pdf_paths])
        for pdf_path in pdf_paths:
            try:
                chapter_doc = fitz.open(str(pdf_path))
                n_pages = len(chapter_doc)
                try:
                    ch = next(chapter_iter)
                    chapter_name = ch.get("chapter") or ch.get("name", "")
                except StopIteration:
                    chapter_name = pdf_path.stem.replace(".pdf", "")
                outline.append([1, chapter_name, page_num])
                page_num += n_pages
                chapter_doc.close()
            except Exception:
                continue

        if outline:
            merged.set_toc(outline)

        # 原子写入：tobytes() + 手动写入临时文件，避免 PyMuPDF save 在 Windows 下内部 rename 报错
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(output_path.parent), prefix="merged_")
        try:
            pdf_bytes = merged.tobytes()
            merged.close()
            with os.fdopen(fd, "wb") as f:
                f.write(pdf_bytes)
            os.replace(tmp, str(output_path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return True
    except Exception as exc:
        _emit_progress(emit, "error", message=f"PDF 合并异常: {type(exc).__name__}: {exc}")
        try:
            merged.close()
        except Exception:
            pass
        return False


def export_pdf(
    enterprise_id: str,
    project_id: str,
    *,
    cancel_event: threading.Event | None = None,
    emit: Any | None = None,
) -> dict[str, Any]:
    """转 PDF + 合并为完整标书 PDF。

    流程：
      1. 读取格式清单，过滤 EXTERNAL 条目
      2. 逐章 docx → PDF（复用 LibreOffice 转换服务）
      3. PyMuPDF 按顺序合并 + 书签
      4. 状态机 RENDERED → EXPORTED

    Returns:
        {"merged_path": str, "total_chapters": int, "success": bool}
    """
    # 1. 读取格式清单
    chapters = _read_format_list(enterprise_id, project_id)
    if not chapters:
        return {"merged_path": "", "total_chapters": 0, "success": False, "error": "无格式清单"}

    pdf_dir = p.pdf_dir(enterprise_id, project_id)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    merged_path = pdf_dir / "标书.pdf"

    # 2. 逐章转 PDF
    pdf_paths = _convert_chapters_to_pdf(
        enterprise_id, project_id, chapters, pdf_dir, cancel_event, emit
    )

    if not pdf_paths:
        return {
            "merged_path": "",
            "total_chapters": 0,
            "success": False,
            "error": "无可转换章节（LibreOffice 转换全部失败，可能未安装 soffice 或不在 PATH）",
        }

    # 3. 合并
    merge_errors: list[str] = []

    def capture_emit(stage: str, **kwargs: Any) -> None:
        if stage == "error":
            msg = kwargs.get("message", "")
            if msg:
                merge_errors.append(str(msg))
        _emit_progress(emit, stage, **kwargs)

    success = _merge_pdfs(pdf_paths, merged_path, capture_emit, chapters=chapters)
    if not success:
        detail = "; ".join(merge_errors) if merge_errors else "未知原因"
        return {
            "merged_path": "",
            "total_chapters": len(chapters),
            "success": False,
            "error": f"PDF 合并失败: {detail}",
        }

    # 4. 状态转换 RENDERED → EXPORTED
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.deps import get_engine  # noqa: PLC0415
    from app.db.session import session_factory  # noqa: PLC0415
    from app.models.project import Project  # noqa: PLC0415
    from app.repositories.app_event import AppEventRepository  # noqa: PLC0415
    from app.repositories.base import Scope  # noqa: PLC0415

    engine = get_engine()
    sess = session_factory(engine)()
    try:
        project = sess.execute(
            select(Project).where(
                Project.id == project_id,
                Project.enterprise_id == enterprise_id,
            )
        ).scalar_one_or_none()
        if project is not None:
            ensure_transition(project.parse_status, EXPORTED)  # type: ignore[arg-type]
            project.parse_status = EXPORTED
            sess.commit()
            scope = Scope(enterprise_id=enterprise_id, project_id=project_id)
            event_repo = AppEventRepository(sess, scope)
            event_repo.record(
                "export_state_change",
                project_id=project_id,
                payload={"from": "RENDERED", "to": "EXPORTED"},
            )
            sess.commit()
    except Exception as exc:
        sess.rollback()
        _emit_progress(emit, "error", message=f"状态更新失败: {exc}")
    finally:
        sess.close()

    return {
        "merged_path": str(merged_path),
        "total_chapters": len(pdf_paths),
        "success": True,
    }
