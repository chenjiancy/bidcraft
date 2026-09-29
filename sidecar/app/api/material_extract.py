"""素材提取清单 API（Task 16）。

路由前缀：/api/v1/enterprises/{enterprise_id}/projects/{project_id}/material-extract
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.materials import extract_service as svc
from app.schemas.extract import (
    AddRequirementIn,
    ExtractListItem,
    ExtractListOut,
    ExtractQueryIn,
    ExtractQueryOut,
    GenerateOut,
    ImportExternalIn,
    SaveRoundIn,
    UpdateRequirementIn,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])
SessionDep = Annotated[Session, Depends(get_session)]

_PREFIX = "/enterprises/{enterprise_id}/projects/{project_id}/material-extract"


@router.get(f"{_PREFIX}", response_model=ExtractListOut)
def get_extract_list(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
    round: Annotated[int | None, Query()] = None,
) -> ExtractListOut:
    """获取素材提取清单（默认最新轮次）。"""
    return svc.get_extract_list(session, enterprise_id, project_id, round_num=round)


@router.post(f"{_PREFIX}/generate", response_model=GenerateOut)
def generate_extract_list(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
    round: Annotated[int, Query()] = 1,
) -> GenerateOut:
    """两源聚合生成待查素材清单（score_table + 格式清单条款），同名去重。"""
    return svc.generate_extract_list(session, enterprise_id, project_id, round_num=round)


@router.post(f"{_PREFIX}/query", response_model=ExtractQueryOut)
def query_candidates(
    enterprise_id: str,
    project_id: str,
    body: ExtractQueryIn,
    session: SessionDep,
) -> ExtractQueryOut:
    """FTS5 多条件查询候选素材（按证件组聚合），仅本企业范围。"""
    return svc.query_candidates(session, enterprise_id, project_id, body)


@router.post(f"{_PREFIX}/items", response_model=ExtractListItem, status_code=201)
def add_requirement(
    enterprise_id: str,
    project_id: str,
    body: AddRequirementIn,
    session: SessionDep,
) -> ExtractListItem:
    """手工新增需求项。"""
    return svc.add_requirement(session, enterprise_id, project_id, body)


@router.put(f"{_PREFIX}/items/{{item_id}}", response_model=ExtractListItem)
def update_requirement(
    enterprise_id: str,
    project_id: str,
    item_id: Annotated[str, PathParam()],
    body: UpdateRequirementIn,
    session: SessionDep,
) -> ExtractListItem:
    """修改需求项名称。"""
    try:
        return svc.update_requirement(session, enterprise_id, project_id, item_id, body)
    except Exception as e:  # NotFoundError
        raise HTTPException(404, "需求项不存在") from e


@router.delete(f"{_PREFIX}/items/{{item_id}}", status_code=200)
def delete_requirement(
    enterprise_id: str,
    project_id: str,
    item_id: Annotated[str, PathParam()],
    session: SessionDep,
) -> dict[str, str]:
    """删除需求项（软删除）。"""
    try:
        svc.delete_requirement(session, enterprise_id, project_id, item_id)
    except Exception as e:
        raise HTTPException(404, "需求项不存在") from e
    return {"deleted": item_id}


@router.post(f"{_PREFIX}/save-round", response_model=ExtractListOut)
def save_round(
    enterprise_id: str,
    project_id: str,
    body: SaveRoundIn,
    session: SessionDep,
) -> ExtractListOut:
    """保存本轮选定状态（selected / missing / deferred）。"""
    try:
        return svc.save_extract_round(session, enterprise_id, project_id, body)
    except Exception as e:
        raise HTTPException(404, "需求项不存在") from e


@router.post(f"{_PREFIX}/new-round")
def start_new_round(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """开启新一轮（复制上轮条目，供补充素材后复核）。"""
    return svc.start_new_round(session, enterprise_id, project_id)


@router.post(f"{_PREFIX}/import-external")
def import_external(
    enterprise_id: str,
    project_id: str,
    body: ImportExternalIn,
    session: SessionDep,
) -> dict[str, Any]:
    """A 类处理：库外文件复制进项目 project-materials/ 作副本。"""
    return svc.import_external_file(session, enterprise_id, project_id, body)


@router.post(f"{_PREFIX}/confirm")
def confirm_extract_list(
    enterprise_id: str,
    project_id: str,
    session: SessionDep,
    round: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    """确认保存提取清单（全部有结论才可保存）→ MATERIAL_CONFIRMED。"""
    return svc.confirm_extract_list(session, enterprise_id, project_id, round_num=round)
