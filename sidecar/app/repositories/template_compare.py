"""模板比对 repository（Task 18）。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models._mixins import new_id
from app.models.template_compare import TemplateCompare
from app.repositories.base import NotFoundError, Scope


class TemplateCompareRepository:
    def __init__(self, session: Session, scope: Scope) -> None:
        self.session = session
        self.scope = scope
        missing = [name for name in ("enterprise_id", "project_id") if getattr(scope, name) is None]
        if missing:
            raise ValueError(f"仓储缺少 scope 值: {', '.join(missing)}")

    def _filter(self) -> Any:
        stmt = select(TemplateCompare)
        stmt = stmt.where(TemplateCompare.enterprise_id == self.scope.enterprise_id)
        stmt = stmt.where(TemplateCompare.project_id == self.scope.project_id)
        stmt = stmt.where(TemplateCompare.deleted_at.is_(None))
        return stmt

    def get(self, compare_id: str) -> TemplateCompare:
        stmt = self._filter().where(TemplateCompare.id == compare_id)
        instance = self.session.execute(stmt).scalar_one_or_none()
        if instance is None:
            raise NotFoundError(f"比对记录 {compare_id} 不存在")
        return instance

    def get_by_project(self) -> TemplateCompare | None:
        """返回当前项目的比对记录（每项目只有一条）。"""
        stmt = self._filter().order_by(TemplateCompare.created_at.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        enterprise_id: str,
        project_id: str,
        matched_template_id: str | None = None,
        match_method: str = "manual",
        similarity_score: int | None = None,
        work_dir: str = "",
    ) -> TemplateCompare:
        tc = TemplateCompare(
            id=new_id(),
            enterprise_id=enterprise_id,
            project_id=project_id,
            matched_template_id=matched_template_id,
            match_method=match_method,
            similarity_score=similarity_score,
            work_dir=work_dir,
        )
        self.session.add(tc)
        self.session.flush()
        return tc

    def update(
        self,
        compare_id: str,
        *,
        findings_json: str | None = None,
        association_json: str | None = None,
        status: str | None = None,
        rejected_count: int | None = None,
        accepted_count: int | None = None,
        ready_at: Any = None,
        bp4_summary_json: str | None = None,
    ) -> TemplateCompare:
        tc = self.get(compare_id)
        if findings_json is not None:
            tc.findings_json = findings_json
        if association_json is not None:
            tc.association_json = association_json
        if status is not None:
            tc.status = status
        if rejected_count is not None:
            tc.rejected_count = rejected_count
        if accepted_count is not None:
            tc.accepted_count = accepted_count
        if ready_at is not None:
            tc.ready_at = ready_at
        if bp4_summary_json is not None:
            tc.bp4_summary_json = bp4_summary_json
        self.session.flush()
        return tc

    def delete(self, compare_id: str) -> None:
        tc = self.get(compare_id)
        tc.deleted_at = tc.updated_at
