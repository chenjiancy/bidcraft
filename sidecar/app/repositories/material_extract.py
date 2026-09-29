"""素材提取清单条目仓库（Task 16）。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models._mixins import new_id
from app.models.material_extract import MaterialExtractItem
from app.repositories.base import NotFoundError, Scope


class MaterialExtractRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        self.session = session
        self.scope = scope

    def get(self, item_id: str) -> MaterialExtractItem:
        item = (
            self.session.query(MaterialExtractItem)
            .filter_by(
                id=item_id,
                enterprise_id=self.scope.enterprise_id,
                project_id=self.scope.project_id,
                deleted_at=None,
            )
            .first()
        )
        if item is None:
            raise NotFoundError(f"MaterialExtractItem {item_id} not found")
        return item

    def list_by_round(self, round_num: int | None = None) -> list[MaterialExtractItem]:
        filters = [
            MaterialExtractItem.enterprise_id == self.scope.enterprise_id,
            MaterialExtractItem.project_id == self.scope.project_id,
            MaterialExtractItem.deleted_at.is_(None),
        ]
        if round_num is not None:
            filters.append(MaterialExtractItem.round == round_num)
        return list(
            self.session.scalars(
                select(MaterialExtractItem).where(*filters).order_by(MaterialExtractItem.created_at)
            ).all()
        )

    def list_pending(self) -> list[MaterialExtractItem]:
        """返回当前最高轮次中 status=pending 的条目。"""
        latest_round = (
            self.session.scalar(
                select(MaterialExtractItem.round)
                .where(
                    MaterialExtractItem.enterprise_id == self.scope.enterprise_id,
                    MaterialExtractItem.project_id == self.scope.project_id,
                    MaterialExtractItem.deleted_at.is_(None),
                )
                .order_by(MaterialExtractItem.round.desc())
                .limit(1)
            )
            or 1
        )
        return [m for m in self.list_by_round(round_num=latest_round) if m.status == "pending"]

    def create(self, **kwargs: Any) -> MaterialExtractItem:
        item = MaterialExtractItem(
            id=new_id(),
            enterprise_id=self.scope.enterprise_id,
            project_id=self.scope.project_id,
            **kwargs,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def update(self, item_id: str, **kwargs: Any) -> MaterialExtractItem:
        item = self.get(item_id)
        for key, val in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, val)
        return item

    def delete(self, item_id: str) -> None:
        item = self.get(item_id)
        item.deleted_at = datetime.now(UTC)
        self.session.flush()
