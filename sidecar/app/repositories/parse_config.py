"""项目级解析配置仓储：join project 强制企业隔离（架构第四节铁律）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.parse_config import ParseProjectConfig
from app.models.project import Project
from app.repositories.base import NotFoundError, Scope


class ParseConfigRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        if scope.enterprise_id is None:
            raise ValueError("ParseConfigRepository 需要 enterprise_id")
        self.session = session
        self.scope = scope

    def _stmt(self):
        # 企业隔离：join project 限定企业；具体项目由调用方按 project_id 过滤
        return (
            select(ParseProjectConfig)
            .join(Project, Project.id == ParseProjectConfig.project_id)
            .where(Project.enterprise_id == self.scope.enterprise_id)
        )

    def get(self, project_id: str) -> ParseProjectConfig | None:
        return self.session.execute(
            self._stmt().where(ParseProjectConfig.project_id == project_id)
        ).scalar_one_or_none()

    def get_payload(self, project_id: str) -> dict[str, Any] | None:
        row = self.get(project_id)
        if row is None:
            return None
        return json.loads(row.payload)

    def upsert(self, project_id: str, payload: dict[str, Any]) -> None:
        row = self.get(project_id)
        raw = json.dumps(payload, ensure_ascii=False)
        if row is None:
            # 写入前校验项目归属（防伪造 project_id；与 AppEventRepository 同策略）
            owned = self.session.execute(
                select(Project.id)
                .where(Project.id == project_id)
                .where(Project.enterprise_id == self.scope.enterprise_id)
            ).scalar_one_or_none()
            if owned is None:
                raise NotFoundError(project_id)
            self.session.add(ParseProjectConfig(project_id=project_id, payload=raw))
        else:
            row.payload = raw
