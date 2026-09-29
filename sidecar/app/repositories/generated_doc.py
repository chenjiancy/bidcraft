"""逐章渲染产物 repository（Task 19）。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models._mixins import new_id
from app.models.generated_doc import GeneratedDoc
from app.repositories.base import NotFoundError, Scope


class GeneratedDocRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        self.session = session
        self.scope = scope
        missing = [name for name in ("enterprise_id", "project_id") if getattr(scope, name) is None]
        if missing:
            raise ValueError(f"仓储缺少 scope 值: {', '.join(missing)}")

    def _filter(self) -> Any:
        stmt = select(GeneratedDoc)
        stmt = stmt.where(GeneratedDoc.enterprise_id == self.scope.enterprise_id)
        stmt = stmt.where(GeneratedDoc.project_id == self.scope.project_id)
        return stmt

    def list_by_project(self) -> list[GeneratedDoc]:
        """返回当前项目全部渲染记录（按 seq 排序）。"""
        stmt = self._filter().order_by(GeneratedDoc.seq)
        return list(self.session.execute(stmt).scalars().all())

    def get(self, doc_id: str) -> GeneratedDoc:
        stmt = self._filter().where(GeneratedDoc.id == doc_id)
        instance = self.session.execute(stmt).scalar_one_or_none()
        if instance is None:
            raise NotFoundError(f"渲染记录 {doc_id} 不存在")
        return instance

    def get_by_chapter(self, chapter: str) -> GeneratedDoc | None:
        """按章节名查找。"""
        stmt = self._filter().where(GeneratedDoc.chapter == chapter)
        return self.session.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        enterprise_id: str,
        project_id: str,
        chapter: str,
        seq: int,
        source_template_version: str = "",
    ) -> GeneratedDoc:
        gd = GeneratedDoc(
            id=new_id(),
            enterprise_id=enterprise_id,
            project_id=project_id,
            chapter=chapter,
            seq=seq,
            source_template_version=source_template_version,
            status="pending",
        )
        self.session.add(gd)
        self.session.flush()
        return gd

    def update(
        self,
        doc_id: str,
        *,
        file_path: str | None = None,
        source_template_version: str | None = None,
        status: str | None = None,
        error_msg: str | None = None,
        rendered_at: Any = None,
    ) -> GeneratedDoc:
        gd = self.get(doc_id)
        if file_path is not None:
            gd.file_path = file_path
        if source_template_version is not None:
            gd.source_template_version = source_template_version
        if status is not None:
            gd.status = status
        if error_msg is not None:
            gd.error_msg = error_msg
        if rendered_at is not None:
            gd.rendered_at = rendered_at
        self.session.flush()
        return gd

    def delete_all_by_project(self) -> None:
        """删除当前项目全部渲染记录（重渲染前清空旧记录）。"""
        for gd in self.list_by_project():
            self.session.delete(gd)
        self.session.flush()
