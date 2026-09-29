"""企业 CRUD + 项目子资源 API（architecture.md 2.2）。

委托代理人优先级：项目 agent 缺省时回退企业 agent（TR-5.2）。
软删除不物理删，写入 recycle_bin（TR-5.3）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import require_sidecar_token
from app.db.deps import get_session
from app.models.enterprise import Enterprise
from app.models.project import Project
from app.repositories.base import NotFoundError, Scope
from app.repositories.enterprise import EnterpriseRepository
from app.repositories.project import ProjectRepository
from app.repositories.recycle_bin import RecycleBinRepository
from app.schemas.enterprise import (
    EnterpriseCreate,
    EnterpriseOut,
    EnterpriseUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_sidecar_token)])

SessionDep = Annotated[Session, Depends(get_session)]


def _project_out(project: Project, enterprise_agent: str) -> ProjectOut:
    """组装 ProjectOut：agent 回退（项目优先，缺省取企业）。"""
    return ProjectOut(
        id=project.id,
        enterprise_id=project.enterprise_id,
        name=project.name,
        code=project.code,
        agent=project.agent or enterprise_agent,
        status=project.status,
        parse_status=project.parse_status,
    )


# ========== 企业 ==========


@router.get("/enterprises", response_model=list[EnterpriseOut])
def list_enterprises(session: SessionDep) -> list[Enterprise]:
    return EnterpriseRepository(session).list()


@router.post("/enterprises", response_model=EnterpriseOut, status_code=201)
def create_enterprise(body: EnterpriseCreate, session: SessionDep) -> Enterprise:
    repo = EnterpriseRepository(session)
    fields = body.model_dump(exclude={"name", "agent"})
    ent = repo.create(name=body.name, agent=body.agent, **fields)
    session.commit()
    # Task 15：初始化素材目录骨架
    from app.parse import paths as path_utils

    path_utils.init_materials_dirs(ent.id)
    return ent


@router.get("/enterprises/{enterprise_id}", response_model=EnterpriseOut)
def get_enterprise(enterprise_id: str, session: SessionDep) -> Enterprise:
    try:
        return EnterpriseRepository(session).get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None


@router.put("/enterprises/{enterprise_id}", response_model=EnterpriseOut)
def update_enterprise(
    enterprise_id: str,
    body: EnterpriseUpdate,
    session: SessionDep,
) -> Enterprise:
    repo = EnterpriseRepository(session)
    try:
        ent = repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(ent, key, value)
    session.commit()
    return ent


@router.delete("/enterprises/{enterprise_id}", status_code=204)
def delete_enterprise(enterprise_id: str, session: SessionDep) -> None:
    repo = EnterpriseRepository(session)
    try:
        repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    repo.soft_delete(enterprise_id)
    RecycleBinRepository(session).add(
        item_type="enterprise",
        ref_id=enterprise_id,
        enterprise_id=None,
    )
    session.commit()


# ========== 项目（嵌套在企业下） ==========


@router.get("/enterprises/{enterprise_id}/projects", response_model=list[ProjectOut])
def list_projects(enterprise_id: str, session: SessionDep) -> list[ProjectOut]:
    ent_repo = EnterpriseRepository(session)
    try:
        ent = ent_repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    projects = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).list()
    return [_project_out(p, ent.agent) for p in projects]


@router.post("/enterprises/{enterprise_id}/projects", response_model=ProjectOut, status_code=201)
def create_project(
    enterprise_id: str,
    body: ProjectCreate,
    session: SessionDep,
) -> ProjectOut:
    ent_repo = EnterpriseRepository(session)
    try:
        ent = ent_repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    repo = ProjectRepository(session, Scope(enterprise_id=enterprise_id))
    fields = body.model_dump(exclude={"name"})
    project = repo.create(name=body.name, **fields)
    session.commit()
    # Task 15：初始化项目素材目录
    from app.parse import paths as path_utils

    path_utils.init_project_materials_dirs(enterprise_id, project.id)
    return _project_out(project, ent.agent)


@router.get("/enterprises/{enterprise_id}/projects/{project_id}", response_model=ProjectOut)
def get_project(enterprise_id: str, project_id: str, session: SessionDep) -> ProjectOut:
    ent_repo = EnterpriseRepository(session)
    try:
        ent = ent_repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    repo = ProjectRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        project = repo.get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    return _project_out(project, ent.agent)


@router.put("/enterprises/{enterprise_id}/projects/{project_id}", response_model=ProjectOut)
def update_project(
    enterprise_id: str,
    project_id: str,
    body: ProjectUpdate,
    session: SessionDep,
) -> ProjectOut:
    ent_repo = EnterpriseRepository(session)
    try:
        ent = ent_repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    repo = ProjectRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        project = repo.get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(project, key, value)
    session.commit()
    return _project_out(project, ent.agent)


@router.delete("/enterprises/{enterprise_id}/projects/{project_id}", status_code=204)
def delete_project(enterprise_id: str, project_id: str, session: SessionDep) -> None:
    ent_repo = EnterpriseRepository(session)
    try:
        ent_repo.get(enterprise_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="企业不存在") from None
    repo = ProjectRepository(session, Scope(enterprise_id=enterprise_id))
    try:
        repo.get(project_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="项目不存在") from None
    repo.soft_delete(project_id)
    RecycleBinRepository(session).add(
        item_type="project",
        ref_id=project_id,
        enterprise_id=enterprise_id,
    )
    session.commit()
