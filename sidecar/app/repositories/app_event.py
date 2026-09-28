"""app_event 仓储：追加审计事件；按项目查询时强制企业隔离。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.app_event import AppEvent
from app.models.project import Project
from app.repositories.base import NotFoundError, Scope


class RepositoryConfigError(Exception):
    pass


class AppEventRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        if scope.enterprise_id is None:
            raise RepositoryConfigError("AppEventRepository 需要 enterprise_id")
        self.session = session
        self.scope = scope

    def record(
        self,
        event_type: str,
        project_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AppEvent:
        if project_id is not None:
            # 验证项目确实属于当前企业（防伪造 project_id）
            owned = self.session.execute(
                select(Project.id)
                .where(Project.id == project_id)
                .where(Project.enterprise_id == self.scope.enterprise_id)
            ).scalar_one_or_none()
            if owned is None:
                raise NotFoundError(project_id)
        instance = AppEvent(type=event_type, project_id=project_id, payload=payload)
        self.session.add(instance)
        return instance

    def list_for_project(self, project_id: str) -> list[AppEvent]:
        # join project 限定企业：跨企业项目查不到任何事件
        stmt = (
            select(AppEvent)
            .join(Project, Project.id == AppEvent.project_id)
            .where(Project.enterprise_id == self.scope.enterprise_id)
            .where(AppEvent.project_id == project_id)
            .order_by(AppEvent.created_at)
        )
        return list(self.session.execute(stmt).scalars().all())
