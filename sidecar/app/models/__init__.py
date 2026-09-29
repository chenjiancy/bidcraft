"""集中导入全部模型，保证 Alembic autogenerate 与元数据完整。"""

from app.models.app_event import AppEvent
from app.models.config_kv import ConfigKV
from app.models.enterprise import Enterprise
from app.models.llm_call_log import LLMCallLog
from app.models.material import Material
from app.models.material_extract import MaterialExtractItem
from app.models.parse_config import ParseProjectConfig
from app.models.project import Project
from app.models.recycle_bin import RecycleBin
from app.models.template import Template
from app.models.template_compare import TemplateCompare

__all__ = [
    "AppEvent",
    "ConfigKV",
    "Enterprise",
    "LLMCallLog",
    "Material",
    "MaterialExtractItem",
    "ParseProjectConfig",
    "Project",
    "RecycleBin",
    "Template",
    "TemplateCompare",
]
