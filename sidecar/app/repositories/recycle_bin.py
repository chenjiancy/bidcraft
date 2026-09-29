"""回收站仓储：记录软删除项、列表、恢复、物理清除。"""

from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.models.recycle_bin import RecycleBin
from app.repositories.base import NotFoundError


class RecycleBinRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        item_type: str,
        ref_id: str,
        enterprise_id: str | None = None,
    ) -> RecycleBin:
        instance = RecycleBin(
            item_type=item_type,
            ref_id=ref_id,
            enterprise_id=enterprise_id,
        )
        self.session.add(instance)
        return instance

    def save_name(
        self,
        bin_id: str,
        name: str,
        original_name: str | None = None,
        file_path: str | None = None,
    ) -> RecycleBin:
        """保存条目的名称/原名称/文件路径（用于恢复时还原）。"""
        instance = self.get(bin_id)
        instance.name = name
        if original_name is not None:
            instance.original_name = original_name
        if file_path is not None:
            instance.file_path = file_path
        return instance

    def list(
        self,
        enterprise_id: str | None = None,
        item_type: str | None = None,
        include_system: bool = False,
    ) -> list[RecycleBin]:
        """列出回收站条目。

        - 不传 enterprise_id：返回系统回收站（仅被删除的企业，当前用户可见）
        - 传 enterprise_id：返回该企业的项目/素材/模板回收项
        - include_system=True：同时包含系统回收站条目
        """
        stmt = select(RecycleBin).order_by(RecycleBin.deleted_at.desc())

        if enterprise_id is not None:
            # 该企业的项目回收项 + 素材/模板回收项
            stmt = stmt.where(RecycleBin.enterprise_id == enterprise_id)
            if item_type is not None:
                stmt = stmt.where(RecycleBin.item_type == item_type)
        else:
            # 系统回收站：仅被删除的企业（enterprise_id 为 null 或 ref_id 匹配）
            # 注意：企业被删时 enterprise_id 设为 None（因为 FK SET NULL）
            # 但 material/template 也存了 enterprise_id
            stmt = stmt.where(RecycleBin.item_type == "enterprise")
            if item_type is not None:
                stmt = stmt.where(RecycleBin.item_type == item_type)

        return list(self.session.execute(stmt).scalars().all())

    def get(self, item_id: str) -> RecycleBin:
        instance = self.session.get(RecycleBin, item_id)
        if instance is None:
            raise NotFoundError(item_id)
        return instance

    def remove(self, item_id: str) -> None:
        instance = self.get(item_id)
        self.session.delete(instance)

    def restore(self, bin_id: str) -> tuple[RecycleBin, dict[str, Any]]:
        """恢复一个回收站条目，返回 (bin_record, result_info)。

        result_info 包含：
          - restored: 是否成功恢复
          - action: "restored" | "renamed" | "skipped"
          - error: 错误信息（如有）
        """
        from app.models.material import Material
        from app.models.template import Template
        from app.repositories.base import Scope
        from app.repositories.enterprise import EnterpriseRepository
        from app.repositories.project import ProjectRepository

        instance = self.get(bin_id)
        item_type = instance.item_type
        ref_id = instance.ref_id

        if item_type == "enterprise":
            ent_repo = EnterpriseRepository(self.session)
            try:
                ent = ent_repo.get(ref_id, include_deleted=True)
            except NotFoundError:
                instance.status = "conflict"
                self.session.commit()
                return instance, {"restored": False, "action": "error", "error": "原企业已不存在"}

            ent.deleted_at = None
            ent.status = "active"

        elif item_type == "project":
            if not instance.enterprise_id:
                return instance, {
                    "restored": False,
                    "action": "error",
                    "error": "回收站项缺少企业归属",
                }
            ent_repo = EnterpriseRepository(self.session)
            try:
                ent_repo.get(instance.enterprise_id)
            except NotFoundError:
                return instance, {"restored": False, "action": "error", "error": "原企业已不存在"}

            repo = ProjectRepository(self.session, Scope(enterprise_id=instance.enterprise_id))
            try:
                project = repo.get(ref_id, include_deleted=True)
            except NotFoundError:
                return instance, {"restored": False, "action": "error", "error": "原项目已不存在"}

            project.deleted_at = None
            project.status = "active"

        elif item_type == "material":
            result = cast(
                CursorResult,
                self.session.execute(
                    sa_update(Material)
                    .where(Material.id == ref_id)
                    .where(Material.enterprise_id == instance.enterprise_id)
                    .values(deleted_at=None, status="active")
                ),
            )
            if result.rowcount == 0:
                return instance, {"restored": False, "action": "error", "error": "素材不存在"}

        elif item_type == "template":
            result = cast(
                CursorResult,
                self.session.execute(
                    sa_update(Template)
                    .where(Template.id == ref_id)
                    .where(Template.enterprise_id == instance.enterprise_id)
                    .values(deleted_at=None, status="active")
                ),
            )
            if result.rowcount == 0:
                return instance, {"restored": False, "action": "error", "error": "模板不存在"}
        else:
            return instance, {
                "restored": False,
                "action": "error",
                "error": f"未知类型: {item_type}",
            }

        self.session.delete(instance)
        self.session.commit()
        return instance, {"restored": True, "action": "restored"}

    def purge(self, bin_id: str) -> dict[str, Any]:
        """物理删除回收站条目及其关联文件。"""
        instance = self.get(bin_id)
        item_type = instance.item_type
        ref_id = instance.ref_id
        enterprise_id = instance.enterprise_id

        try:
            if item_type == "enterprise":
                # 删除企业目录
                from app.parse import paths as path_utils

                ent_dir = path_utils.data_root() / "enterprises" / ref_id
                if ent_dir.exists():
                    import shutil

                    shutil.rmtree(ent_dir, ignore_errors=True)

            elif item_type == "project":
                from app.parse import paths as path_utils

                proj_dir = path_utils.project_dir(ref_id, ref_id)  # 这里需要 enterprise_id
                # 从配置或其他地方获取 enterprise_id
                # 实际上 ref_id 是项目 id，enterprise_id 在 instance.enterprise_id
                if enterprise_id:
                    proj_dir = path_utils.project_dir(enterprise_id, ref_id)
                    if proj_dir.exists():
                        import shutil

                        shutil.rmtree(proj_dir, ignore_errors=True)

            elif item_type == "material":
                # 删除素材文件
                if instance.file_path:
                    fp = Path(instance.file_path)
                    if fp.exists():
                        fp.unlink()

            elif item_type == "template":
                # 模板文件在 path 字段，从 template 表读取路径并删除
                if enterprise_id:
                    from app.models.template import Template

                    tpl = self.session.execute(
                        select(Template).where(Template.id == ref_id)
                    ).scalar_one_or_none()
                    if tpl and tpl.path:
                        from app.parse import paths as path_utils

                        tpl_path = path_utils.data_root() / tpl.path
                        if tpl_path.exists():
                            import shutil

                            shutil.rmtree(tpl_path, ignore_errors=True)

            # 从数据库中物理删除该记录
            self.session.delete(instance)
            self.session.commit()
            return {"purged": True}

        except Exception as e:
            self.session.rollback()
            return {"purged": False, "error": str(e)}
