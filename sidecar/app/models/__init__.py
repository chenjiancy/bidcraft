"""集中导入全部模型，保证 Alembic autogenerate 与元数据完整。"""

from app.models.app_event import AppEvent
from app.models.config_kv import ConfigKV
from app.models.enterprise import Enterprise
from app.models.project import Project

__all__ = ["AppEvent", "ConfigKV", "Enterprise", "Project"]
