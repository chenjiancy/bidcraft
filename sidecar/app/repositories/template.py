"""模板库 repository。

Task 17：企业级模板 CRUD + 版本查询 + 引用标记。
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models._mixins import new_id
from app.models.template import VALID_DOC_TYPES, Template
from app.repositories.base import NotFoundError, Scope


class TemplateRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        self._session = session
        self._scope = scope

    def _filter(self) -> Any:
        """按 Scope 过滤：仅本企业模板。"""
        query = select(Template)
        if self._scope.enterprise_id:
            query = query.where(Template.enterprise_id == self._scope.enterprise_id)
        return query.where(Template.deleted_at.is_(None))

    def get(self, template_id: str, include_deleted: bool = False) -> Template:
        if include_deleted:
            stmt = select(Template).where(Template.id == template_id)
            if self._scope.enterprise_id:
                stmt = stmt.where(Template.enterprise_id == self._scope.enterprise_id)
        else:
            stmt = self._filter().where(Template.id == template_id)
        instance = self._session.execute(stmt).scalar_one_or_none()
        if instance is None:
            raise NotFoundError(f"模板 {template_id} 不存在")
        return instance

    def list(
        self,
        *,
        agency: str | None = None,
        doc_type: str | None = None,
        name: str | None = None,
    ) -> Sequence[Template]:
        query = self._filter()
        if agency:
            query = query.where(Template.agency.contains(agency))
        if doc_type and doc_type in VALID_DOC_TYPES:
            query = query.where(Template.doc_type == doc_type)
        if name:
            query = query.where(Template.name.contains(name))
        query = query.order_by(
            Template.agency, Template.doc_type, Template.name, Template.version.desc()
        )
        return self._session.execute(query).scalars().all()

    def get_latest_version(self, agency: str, doc_type: str, name: str) -> Template | None:
        """返回给定 (agency, doc_type, name) 最高版本号；没有则返回 None。"""
        stmt = (
            self._filter()
            .where(
                Template.agency == agency,
                Template.doc_type == doc_type,
                Template.name == name,
            )
            .order_by(Template.version.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def count_by_agency_doc_type_name(self, agency: str, doc_type: str, name: str) -> int:
        from sqlalchemy import func as sa_func

        stmt = (
            self._filter()
            .where(
                Template.agency == agency,
                Template.doc_type == doc_type,
                Template.name == name,
            )
            .with_only_columns([sa_func.count(Template.id)])
        )
        return self._session.execute(stmt).scalar_one()

    def next_version_number(self, agency: str, doc_type: str, name: str) -> int:
        latest = self.get_latest_version(agency, doc_type, name)
        return (latest.version + 1) if latest else 1

    def create(
        self,
        *,
        enterprise_id: str,
        agency: str,
        doc_type: str,
        name: str,
        version: int,
        path: str,
        meta_json: str,
    ) -> Template:
        t = Template(
            id=new_id(),
            enterprise_id=enterprise_id,
            agency=agency,
            doc_type=doc_type,
            name=name,
            version=version,
            path=path,
            meta_json=meta_json,
            status="active",
            referenced=False,
        )
        self._session.add(t)
        return t

    def update(
        self,
        template_id: str,
        *,
        agency: str | None = None,
        doc_type: str | None = None,
        name: str | None = None,
        version: int | None = None,
        path: str | None = None,
        meta_json: str | None = None,
        status: str | None = None,
    ) -> Template:
        t = self.get(template_id)
        if agency is not None:
            t.agency = agency
        if doc_type is not None:
            t.doc_type = doc_type
        if name is not None:
            t.name = name
        if version is not None:
            t.version = version
        if path is not None:
            t.path = path
        if meta_json is not None:
            t.meta_json = meta_json
        if status is not None:
            t.status = status
        self._session.flush()
        return t

    def soft_delete(self, template_id: str) -> None:
        t = self.get(template_id)
        t.deleted_at = t.updated_at
        t.status = "deleted"

    def set_referenced(self, template_id: str) -> None:
        t = self.get(template_id)
        t.referenced = True

    def mark_all_as_deprecated(self, template_id: str) -> None:
        """新建版本时把同组所有旧版本标记为 deprecated。"""
        from sqlalchemy import update

        t = self.get(template_id)
        stmt = (
            update(Template)
            .where(
                Template.agency == t.agency,
                Template.doc_type == t.doc_type,
                Template.name == t.name,
                Template.status == "active",
            )
            .values(status="deprecated")
        )
        self._session.execute(stmt)
