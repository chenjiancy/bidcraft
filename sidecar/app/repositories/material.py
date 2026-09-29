"""素材库 repository。

Task 15：素材 CRUD + 版本快照 + FTS5 增量更新入口。
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models._mixins import new_id
from app.models.material import VALID_CATEGORIES, Material
from app.repositories.base import NotFoundError, Scope


class MaterialRepository:
    def __init__(self, session: Session, scope: Scope | None = None):
        self._session = session
        self._scope = scope

    def _filter(self) -> Any:
        """按 Scope 过滤：企业共享 + 本项目独享。"""
        query = select(Material).options(joinedload(Material))
        if self._scope:
            if self._scope.enterprise_id:
                query = query.where(Material.enterprise_id == self._scope.enterprise_id)
            if self._scope.project_id:
                query = query.where(
                    (Material.project_id == self._scope.project_id)
                    | (Material.project_id.is_(None))
                )
            else:
                # 仅查企业共享（project_id is null）
                query = query.where(Material.project_id.is_(None))
        return query.where(Material.deleted_at.is_(None))

    def get(self, material_id: str) -> Material:
        result = self._session.execute(
            self._filter().where(Material.id == material_id)
        ).scalar_one_or_none()
        if result is None:
            raise NotFoundError(f"素材 {material_id} 不存在")
        return result

    def list(
        self,
        *,
        category: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Sequence[Material]:
        query = self._filter()
        if category and category in VALID_CATEGORIES:
            query = query.where(Material.category == category)
        if keyword:
            query = query.where(Material.name.contains(keyword))
        query = query.order_by(Material.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        return self._session.execute(query).scalars().all()

    def list_all(self) -> Sequence[Material]:
        return self._session.execute(self._filter()).scalars().all()

    def create(
        self,
        *,
        enterprise_id: str,
        project_id: str | None,
        category: str,
        name: str,
        filename: str,
        file_path: str,
        ocr_text: str | None = None,
        valid_until: str | None = None,
    ) -> Material:
        material = Material(
            id=new_id(),
            enterprise_id=enterprise_id,
            project_id=project_id,
            category=category,
            name=name,
            filename=filename,
            file_path=file_path,
            ocr_text=ocr_text,
            valid_until=valid_until,
            version=1,
            status="active",
            indexed=True,
        )
        self._session.add(material)
        return material

    def update(
        self,
        material_id: str,
        *,
        name: str | None = None,
        filename: str | None = None,
        file_path: str | None = None,
        ocr_text: str | None = None,
        valid_until: str | None = None,
    ) -> Material:
        material = self.get(material_id)
        if name is not None:
            material.name = name
        if filename is not None:
            material.filename = filename
        if file_path is not None:
            material.file_path = file_path
        if ocr_text is not None:
            material.ocr_text = ocr_text
        if valid_until is not None:
            material.valid_until = valid_until
        # 重命名/替换文件 → version+1
        if name is not None or filename is not None or file_path is not None:
            material.version += 1
        self._session.flush()
        return material

    def soft_delete(self, material_id: str) -> None:
        material = self.get(material_id)
        material.deleted_at = material.updated_at
        material.status = "deleted"

    def restore(self, material_id: str) -> Material:
        material = self.get(material_id)
        if material.deleted_at is None:
            return material
        material.deleted_at = None
        material.status = "active"
        return material

    def delete_fts5_index(self, material_id: str) -> None:
        """从 FTS5 虚表移除记录。"""
        from app.materials.fts5 import fts5_remove  # 延迟导入防循环

        material = self.get(material_id)
        material.indexed = False
        self._session.flush()
        try:
            fts5_remove(self._session, material.id)
        except Exception:
            pass
