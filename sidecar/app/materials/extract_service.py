"""素材提取服务（Task 16）：清单生成、FTS5 查询、轮次管理、确认保存。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path as _Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.materials import fts5 as fts5_mod
from app.materials.service import ArchivalError, archive_material
from app.models.material_extract import MaterialExtractItem
from app.parse import paths as path_utils
from app.repositories.base import Scope
from app.repositories.material_extract import MaterialExtractRepository
from app.schemas.extract import (
    AddRequirementIn,
    CandidateGroup,
    ExtractListItem,
    ExtractListOut,
    ExtractQueryIn,
    ExtractQueryOut,
    GenerateOut,
    ImportExternalIn,
    SaveRoundIn,
    UpdateRequirementIn,
)

# ---------- 两源聚合 ----------


def _collect_requirements_from_score_table(eid: str, pid: str) -> list[dict[str, str]]:
    """从 score_table.json 提取所有 items.materials 列表，每条一个需求项。"""
    score_path = path_utils.score_table_path(eid, pid)
    if not score_path.exists():
        return []
    with score_path.open("r", encoding="utf-8") as f:
        score_table = json.load(f)

    results: list[dict[str, str]] = []
    for cat in score_table.get("categories", []):
        for item in cat.get("items", []):
            name = item.get("name", "")
            sources = item.get("materials", [])
            anchor = item.get("source_chapter", "")
            for mat in sources:
                results.append(
                    {
                        "requirement_name": f"{name}: {mat}" if name else mat,
                        # 去重键取材料名本身（去掉评分项前缀），使两源同名材料可合并
                        "dedup_key": mat,
                        "source": "score_table",
                        "source_anchor": f"{cat.get('name', '')}/{anchor}",
                    }
                )
    return results


def _collect_requirements_from_checklist(eid: str, pid: str) -> list[dict[str, str]]:
    """从 format_checklist.json 提取 EXTERNAL 项所需证明材料（若存在）。"""
    check_path = path_utils.format_list_path(eid, pid)
    if not check_path.exists():
        return []
    with check_path.open("r", encoding="utf-8") as f:
        checklist = json.load(f)
    results: list[dict[str, str]] = []
    for section in checklist.get("sections", []):
        for item in section.get("items", []):
            if item.get("status") == "EXTERNAL":
                mat = item.get("material", item.get("name", ""))
                results.append(
                    {
                        "requirement_name": mat,
                        "dedup_key": mat,
                        "source": "format_clause",
                        "source_anchor": section.get("name", ""),
                    }
                )
    return results


def _deduplicate(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """同名需求去重（按 dedup_key 去重，保留第一个来源）。"""
    seen: dict[str, dict[str, str]] = {}
    for item in items:
        key = item.get("dedup_key") or item["requirement_name"]
        if key not in seen:
            seen[key] = item
    return list(seen.values())


# ---------- 核心服务 ----------


def generate_extract_list(
    session: Session, eid: str, pid: str, *, round_num: int = 1
) -> GenerateOut:
    """生成素材提取需求清单（两源聚合 + 去重，存入 DB）。

    首次调用创建所有 pending 条目；重复调用则先清除本轮旧条目再重建。
    """
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))

    # 清除本轮旧条目
    existing = repo.list_by_round(round_num=round_num)
    for item in existing:
        repo.delete(item.id)

    # 两源聚合
    src_scores = _collect_requirements_from_score_table(eid, pid)
    src_clauses = _collect_requirements_from_checklist(eid, pid)
    all_items = _deduplicate(src_scores + src_clauses)

    created = []
    for item_data in all_items:
        entry = repo.create(
            round=round_num,
            requirement_name=item_data["requirement_name"],
            source=item_data["source"],
            source_anchor=item_data.get("source_anchor"),
            status="pending",
        )
        created.append(ExtractListItem.from_model(entry))

    session.commit()
    return GenerateOut(requirement_count=len(created), round=round_num, items=created)


def query_candidates(session: Session, eid: str, pid: str, body: ExtractQueryIn) -> ExtractQueryOut:
    """FTS5 多条件查询（名称 + OCR 文本），结果按证件组聚合。

    仅返回本企业（共享 + 本项目独享）的 active 素材，跨企业/跨项目不可见（TR-16.12）。
    """
    fts_path = path_utils.fts5_db_path(eid)
    keywords = (body.keyword or body.requirement_name or "").strip()

    rows = fts5_mod.fts5_search(fts_path, keywords, limit=100)
    if not rows:
        return ExtractQueryOut(candidates=[], total=0)

    # 回连主库过滤 scope（企业共享 OR 本项目独享）+ 未删除
    from app.models.material import Material

    ids = [r["material_id"] for r in rows]
    matched = session.scalars(
        select(Material)
        .where(Material.id.in_(ids))
        .where(Material.enterprise_id == eid)
        .where(Material.deleted_at.is_(None))
        .where((Material.project_id.is_(None)) | (Material.project_id == pid))
    ).all()

    rank_by_id = {r["material_id"]: float(r["rank"]) for r in rows}

    # 证件组聚合：去掉末尾 _P0/_P1/... 按前缀分组
    page_re = re.compile(r"_[Pp]\d+$")
    groups: dict[str, list[dict[str, Any]]] = {}
    for m in matched:
        # 以 filename 为组键（多页共用前缀，仅页码后缀不同）
        group_key = page_re.sub("", m.filename or m.name).strip()
        groups.setdefault(group_key, []).append(
            {
                "id": m.id,
                "name": m.name,
                "filename": m.filename,
                "file_path": _Path(m.file_path).as_posix(),
                "category": m.category,
                "valid_until": m.valid_until,
                "rank": rank_by_id.get(m.id, 0.0),
            }
        )

    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: max(i["rank"] for i in kv[1]),
        reverse=True,
    )

    candidates = [
        CandidateGroup(group_key=group_key, items=items) for group_key, items in sorted_groups
    ]
    return ExtractQueryOut(
        candidates=candidates,
        total=sum(len(g.items) for g in candidates),
    )


def save_extract_round(session: Session, eid: str, pid: str, body: SaveRoundIn) -> ExtractListOut:
    """保存本轮选定状态（selected / missing / deferred）。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    for change in body.changes:
        item = repo.get(change.item_id)
        if change.status:
            item.status = change.status
        if change.selected_material_id:
            item.selected_material_id = change.selected_material_id
    session.commit()
    return list_to_out(repo.list_by_round(round_num=body.round))


def confirm_extract_list(
    session: Session, eid: str, pid: str, *, round_num: int | None = None
) -> dict[str, Any]:
    """确认保存提取清单：全有结论 → 写 JSON → 状态机转 MATERIAL_CONFIRMED。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    latest_round = round_num or _latest_round(session, eid, pid)

    items = repo.list_by_round(round_num=latest_round)
    if not items:
        raise HTTPException(400, "提取清单为空，无法保存")
    unresolved = [m for m in items if m.status in ("pending", "")]
    if unresolved:
        raise HTTPException(
            400,
            f"仍有 {len(unresolved)} 项未选定（pending），不能保存清单",
        )

    # 写 material_extract.json
    lists_dir = path_utils.lists_dir(eid, pid)
    extract_path = lists_dir / "material_extract.json"
    extract_path.parent.mkdir(parents=True, exist_ok=True)

    now_str = _now_iso()
    payload = {
        "project_id": pid,
        "round": latest_round,
        "confirmed_at": now_str,
        "items": [
            {
                "id": m.id,
                "requirement_name": m.requirement_name,
                "source": m.source,
                "source_anchor": m.source_anchor,
                "status": m.status,
                "selected_material_id": m.selected_material_id,
            }
            for m in items
        ],
    }
    tmp_path = extract_path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp_path.rename(extract_path)

    # 更新 confirmed_at 到 DB
    for m in items:
        m.confirmed_at = _now_utc()

    # 状态机：MATERIAL_LOOP → MATERIAL_CONFIRMED（写 app_event 留痕，TR-16.10）
    _transition_to_material_confirmed(session, eid, pid, round_num=latest_round)

    session.commit()
    return {"confirmed_at": now_str, "round": latest_round, "item_count": len(items)}


def _transition_to_material_confirmed(
    session: Session, eid: str, pid: str, *, round_num: int
) -> None:
    """MATERIAL_LOOP → MATERIAL_CONFIRMED（幂等：已在该状态则跳过）。"""
    from app.models.project import Project  # 延迟导入防循环
    from app.parse import state
    from app.repositories.app_event import AppEventRepository

    project = session.get(Project, pid)
    if project is None:
        raise HTTPException(404, "项目不存在")

    current = project.parse_status
    if current == state.MATERIAL_CONFIRMED:
        return
    if not state.can_transition(current, state.MATERIAL_CONFIRMED):  # type: ignore[arg-type]
        raise HTTPException(400, f"当前状态 {current} 不支持保存提取清单（需先进入 MATERIAL_LOOP）")
    project.parse_status = state.MATERIAL_CONFIRMED
    AppEventRepository(session, Scope(enterprise_id=eid)).record(
        "parse_state_change",
        pid,
        {
            "from": current,
            "to": state.MATERIAL_CONFIRMED,
            "reason": "素材提取清单已确认保存",
            "round": round_num,
        },
    )


def import_external_file(
    session: Session, eid: str, pid: str, body: ImportExternalIn
) -> dict[str, Any]:
    """A 类处理：手动指定库外路径 → 复制到项目 project-materials/ 目录。"""
    original_path = _Path(body.file_path)
    if not original_path.exists():
        raise HTTPException(400, f"文件不存在: {body.file_path}")

    try:
        material = archive_material(
            session,
            eid,
            project_id=pid,
            original_path=original_path,
            category=body.category,
            custom_name=body.name,
            custom_filename=body.filename,
        )
        session.commit()
        return {"id": material.id, "file_path": material.file_path}
    except ArchivalError as e:
        raise HTTPException(400, str(e)) from e


def get_extract_list(
    session: Session, eid: str, pid: str, *, round_num: int | None = None
) -> ExtractListOut:
    """获取提取清单；round_num 为空时取最新轮次。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    target_round = round_num if round_num is not None else _latest_round(session, eid, pid)
    return list_to_out(repo.list_by_round(round_num=target_round))


# ---------- 清单条目增删改（TR-16.2） ----------


def add_requirement(
    session: Session, eid: str, pid: str, body: AddRequirementIn
) -> ExtractListItem:
    """手工新增需求项。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    latest_round = _latest_round(session, eid, pid)
    item = repo.create(
        round=body.round or latest_round,
        requirement_name=body.requirement_name,
        source=body.source or "manual",
        source_anchor=body.source_anchor,
        status="pending",
    )
    session.commit()
    return ExtractListItem.from_model(item)


def update_requirement(
    session: Session, eid: str, pid: str, item_id: str, body: UpdateRequirementIn
) -> ExtractListItem:
    """修改需求项名称。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    item = repo.update(item_id, requirement_name=body.requirement_name)
    session.commit()
    return ExtractListItem.from_model(item)


def delete_requirement(session: Session, eid: str, pid: str, item_id: str) -> None:
    """删除需求项（软删除）。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    repo.delete(item_id)
    session.commit()


# ---------- 轮次 ----------


def start_new_round(session: Session, eid: str, pid: str) -> dict[str, Any]:
    """开启新一轮：复制上一轮条目（保留选定结论，状态重置 pending 供复核）。"""
    repo = MaterialExtractRepository(session, Scope(enterprise_id=eid, project_id=pid))
    latest = _latest_round(session, eid, pid)
    prev_items = repo.list_by_round(round_num=latest)
    new_round = latest + 1
    for prev in prev_items:
        repo.create(
            round=new_round,
            requirement_name=prev.requirement_name,
            source=prev.source,
            source_anchor=prev.source_anchor,
            selected_material_id=prev.selected_material_id,
            status=prev.status,
        )
    session.commit()
    return {"round": new_round, "item_count": len(prev_items)}


def _latest_round(session: Session, eid: str, pid: str) -> int:
    return (
        session.scalar(
            select(MaterialExtractItem.round)
            .where(
                MaterialExtractItem.enterprise_id == eid,
                MaterialExtractItem.project_id == pid,
                MaterialExtractItem.deleted_at.is_(None),
            )
            .order_by(MaterialExtractItem.round.desc())
            .limit(1)
        )
        or 1
    )


# ---------- 工具函数 ----------


def list_to_out(items: list[MaterialExtractItem]) -> ExtractListOut:
    pending = sum(1 for m in items if m.status == "pending")
    selected = sum(1 for m in items if m.status == "selected")
    missing = sum(1 for m in items if m.status == "missing")
    return ExtractListOut(
        items=[ExtractListItem.from_model(m) for m in items],
        total=len(items),
        pending=pending,
        selected=selected,
        missing=missing,
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_utc() -> datetime:
    return datetime.now(UTC)
