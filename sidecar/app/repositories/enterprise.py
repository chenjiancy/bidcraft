"""企业仓储：顶层实体，无 scope 列；默认排除软删除。"""

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.enterprise import Enterprise
from app.repositories.base import NotFoundError


class EnterpriseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _active(self):
        from sqlalchemy import select

        return select(Enterprise).where(Enterprise.deleted_at.is_(None))

    def get(self, enterprise_id: str, include_deleted: bool = False) -> Enterprise:
        from sqlalchemy import select

        stmt = select(Enterprise).where(Enterprise.id == enterprise_id)
        if not include_deleted:
            stmt = stmt.where(Enterprise.deleted_at.is_(None))
        instance = self.session.execute(stmt).scalar_one_or_none()
        if instance is None:
            raise NotFoundError(enterprise_id)
        return instance

    def list(self, include_deleted: bool = False) -> list[Enterprise]:
        from sqlalchemy import select

        stmt = select(Enterprise)
        if not include_deleted:
            stmt = stmt.where(Enterprise.deleted_at.is_(None))
        return list(self.session.execute(stmt).scalars().all())

    def create(self, name: str, agent: str, **fields: object) -> Enterprise:
        instance = Enterprise(name=name, agent=agent, **fields)
        self.session.add(instance)
        return instance

    def soft_delete(self, enterprise_id: str) -> None:
        self.session.execute(
            update(Enterprise)
            .where(Enterprise.id == enterprise_id)
            .values(deleted_at=datetime.now(UTC))
        )
