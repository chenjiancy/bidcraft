"""仓储基类与隔离机制。

铁律（architecture.md 四）：所有业务查询默认带 enterprise_id / project_id
约束，杜绝跨企业/跨项目读取。约束在仓储层统一注入：
- 查询：get/list 自动追加 scope 列过滤 + 软删除过滤；
- 写入：add 校验实例 scope 列与仓储 scope 一致，不一致即拒。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session


class RepositoryError(Exception):
    pass


class NotFoundError(RepositoryError):
    """目标不存在或不在当前 scope 内（对外不区分，避免探测）。"""


class ScopeViolationError(RepositoryError):
    """试图写入超出当前 scope 的数据。"""


@dataclass(frozen=True)
class Scope:
    enterprise_id: str | None = None
    project_id: str | None = None


class ScopedRepository[ModelT]:
    """所有具体仓储的基类。

    子类设置：
    - model：ORM 类
    - scope_columns：必须参与过滤的列名（来自 Scope）
    """

    model: type[ModelT]
    scope_columns: tuple[str, ...] = ()

    def __init__(self, session: Session, scope: Scope) -> None:
        self.session = session
        self.scope = scope
        missing = [name for name in self.scope_columns if getattr(self.scope, name) is None]
        if missing:
            raise RepositoryError(f"仓储缺少 scope 值: {', '.join(missing)}")

    def _filtered(self, include_deleted: bool = False):
        stmt = select(self.model)
        for name in self.scope_columns:
            stmt = stmt.where(getattr(self.model, name) == getattr(self.scope, name))
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    def get(self, entity_id: str, include_deleted: bool = False) -> ModelT:
        stmt = self._filtered(include_deleted=include_deleted).where(self.model.id == entity_id)
        instance = self.session.execute(stmt).scalar_one_or_none()
        if instance is None:
            raise NotFoundError(entity_id)
        return instance

    def list(self, include_deleted: bool = False) -> list[ModelT]:
        return list(self.session.execute(self._filtered(include_deleted)).scalars().all())

    def add(self, instance: ModelT) -> ModelT:
        for name in self.scope_columns:
            actual = getattr(instance, name, None)
            expected = getattr(self.scope, name)
            if actual != expected:
                raise ScopeViolationError(
                    f"实例 {name}={actual!r} 与仓储 scope {expected!r} 不一致"
                )
        self.session.add(instance)
        return instance

    def add_all(self, instances: Iterable[ModelT]) -> list[ModelT]:
        return [self.add(instance) for instance in instances]
