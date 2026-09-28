"""项目仓储：enterprise_id 强制隔离。"""

from datetime import UTC, datetime

from sqlalchemy import update

from app.models.project import Project
from app.repositories.base import ScopedRepository


class ProjectRepository(ScopedRepository[Project]):
    model = Project
    scope_columns = ("enterprise_id",)

    def create(self, name: str, **fields: object) -> Project:
        instance = Project(name=name, enterprise_id=self.scope.enterprise_id, **fields)
        return self.add(instance)

    def soft_delete(self, project_id: str) -> None:
        # 先过 scope 校验，确保只能删本企业项目
        self.get(project_id)
        self.session.execute(
            update(Project)
            .where(Project.id == project_id)
            .where(Project.enterprise_id == self.scope.enterprise_id)
            .values(deleted_at=datetime.now(UTC))
        )
