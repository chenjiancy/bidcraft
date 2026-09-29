"""项目数据目录解析（architecture.md 第五章）。

目录布局（Task 8 相关部分）::

    <data_root>/enterprises/<enterprise_id>/projects/<project_id>/
    ├── source/            # 用户登记的原招标文件（复制入库）
    └── parse/
        ├── raw/           # MinerU 原始产物（Markdown + JSON + images）
        ├── chapters.json  # 章节切分结果（Task 8）
        └── checkpoints/   # BP-1 长任务 checkpoint（JSON）

所有写入路径都经 ``ensure_within_project`` 校验，禁止逃逸项目根
（architecture.md 八：文件操作经路径校验）。

素材库布局（Task 15）::

    <data_root>/enterprises/<enterprise_id>/
    ├── materials/
    │   ├── qualification/   # 资质证书
    │   ├── personnel/       # 人员证书
    │   ├── performance/     # 业绩合同
    │   ├── honor/           # 荣誉奖项
    │   └── finance/         # 财务材料
    └── projects/<project_id>/
        └── project-materials/  # 项目独享素材
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core import config

_SOURCE = "source"
_PARSE = "parse"
_RAW = "raw"
_CHECKPOINTS = "checkpoints"
_DOCX = "docx"
_CONFIRMED = "confirmed"
_LISTS = "lists"
_MATERIALS = "materials"
_PROJECT_MATERIALS = "project-materials"
_INBOX = "inbox"
_KEYWORDS_DICT = "keywords.dict.json"

# 素材库五大类（目录名）
MATERIAL_CATEGORIES = (
    "qualification",
    "personnel",
    "performance",
    "honor",
    "finance",
)


class PathEscapeError(Exception):
    """目标路径逃逸了允许的项目数据根目录。"""


def data_root() -> Path:
    return config.DATA_ROOT


def project_dir(enterprise_id: str, project_id: str) -> Path:
    return config.DATA_ROOT / "enterprises" / enterprise_id / "projects" / project_id


def source_dir(enterprise_id: str, project_id: str) -> Path:
    return project_dir(enterprise_id, project_id) / _SOURCE


def parse_dir(enterprise_id: str, project_id: str) -> Path:
    return project_dir(enterprise_id, project_id) / _PARSE


def raw_dir(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / _RAW


def checkpoints_dir(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / _CHECKPOINTS


def chapters_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "chapters.json"


def extract_list_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "structured" / "extract_list.json"


def score_table_path(enterprise_id: str, project_id: str) -> Path:
    return parse_dir(enterprise_id, project_id) / "structured" / "score_table.json"


def docx_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 12：投标文件格式逐章 docx 产物根目录（按源文件分子目录）。"""
    return parse_dir(enterprise_id, project_id) / _DOCX


def docx_manifest_path(enterprise_id: str, project_id: str) -> Path:
    return docx_dir(enterprise_id, project_id) / "manifest.json"


def confirmed_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 13：人工确认后的最终清单目录。"""
    return parse_dir(enterprise_id, project_id) / _CONFIRMED


def checklist_path(enterprise_id: str, project_id: str) -> Path:
    """Task 13：parse_checklist.json 路径。"""
    return confirmed_dir(enterprise_id, project_id) / "parse_checklist.json"


def lists_dir(enterprise_id: str, project_id: str) -> Path:
    """Task 14：商务标格式清单目录（format_checklist.json 等）。"""
    return project_dir(enterprise_id, project_id) / _LISTS


def format_list_path(enterprise_id: str, project_id: str) -> Path:
    """Task 14：商务标格式清单 JSON 路径。"""
    return lists_dir(enterprise_id, project_id) / "format_checklist.json"


def format_list_checkpoint_path(enterprise_id: str, project_id: str) -> Path:
    """Task 14：格式清单确认 checkpoint JSON 路径。"""
    return checkpoints_dir(enterprise_id, project_id) / "format_list.json"


# ---------- Task 15：素材库目录布局 ----------


def _enterprise_dir(enterprise_id: str) -> Path:
    return config.DATA_ROOT / "enterprises" / enterprise_id


def materials_dir(enterprise_id: str) -> Path:
    """企业共享素材库根目录。"""
    return _enterprise_dir(enterprise_id) / _MATERIALS


def materials_category_dir(enterprise_id: str, category: str) -> Path:
    """企业共享素材库按分类子目录。"""
    if category not in MATERIAL_CATEGORIES:
        raise ValueError(f"非法素材分类: {category}")
    return materials_dir(enterprise_id) / category


def project_materials_dir(enterprise_id: str, project_id: str) -> Path:
    """项目独享素材库根目录。"""
    return project_dir(enterprise_id, project_id) / _PROJECT_MATERIALS


def inbox_dir(enterprise_id: str, project_id: str | None = None) -> Path:
    """收件箱目录：project_id 为 None 时为企业共享收件箱，否则为项目独享收件箱。"""
    if project_id is None:
        base = _enterprise_dir(enterprise_id)
    else:
        base = project_dir(enterprise_id, project_id)
    return base / _INBOX


def keywords_dict_path(enterprise_id: str) -> Path:
    """动态关键字词典文件路径（config/keywords.dict.json）。"""
    return _enterprise_dir(enterprise_id) / "config" / _KEYWORDS_DICT


def fts5_db_path(enterprise_id: str) -> Path:
    """FTS5 索引数据库路径。"""
    return _enterprise_dir(enterprise_id) / "fts5.db"


def init_materials_dirs(enterprise_id: str) -> list[Path]:
    """初始化企业素材目录骨架，返回创建/确保存在的目录列表。"""
    dirs: list[Path] = []
    cat_base = materials_dir(enterprise_id)
    cat_base.mkdir(parents=True, exist_ok=True)
    dirs.append(cat_base)
    for cat in MATERIAL_CATEGORIES:
        sub = cat_base / cat
        sub.mkdir(exist_ok=True)
        dirs.append(sub)
    # 收件箱
    inbox = inbox_dir(enterprise_id)
    inbox.mkdir(exist_ok=True)
    dirs.append(inbox)
    # 词典与 FTS5 目录
    config_dir = _enterprise_dir(enterprise_id) / "config"
    config_dir.mkdir(exist_ok=True)
    return dirs


def init_project_materials_dirs(enterprise_id: str, project_id: str) -> list[Path]:
    """初始化项目独享素材目录骨架。"""
    pm = project_materials_dir(enterprise_id, project_id)
    pm.mkdir(parents=True, exist_ok=True)
    inbox = inbox_dir(enterprise_id, project_id)
    inbox.mkdir(exist_ok=True)
    return [pm, inbox]


# ---------- Task 18：模板比对目录布局 ----------

_TEMPLATE_WORK = "template-work"


def template_work_dir(enterprise_id: str, project_id: str) -> Path:
    """项目模板工作目录：template-work/（从企业模板库复制过来）。"""
    return project_dir(enterprise_id, project_id) / _TEMPLATE_WORK


def template_compare_path(enterprise_id: str, project_id: str) -> Path:
    """template_compare.json：关联表与比对摘要（磁盘持久化备份）。"""
    return parse_dir(enterprise_id, project_id) / "template_compare.json"


def init_template_work_dir(enterprise_id: str, project_id: str) -> Path:
    """确保 template-work/ 目录存在。"""
    d = template_work_dir(enterprise_id, project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- Task 19：渲染目录布局 ----------

_OUTPUT = "output"
_PDF = "pdf"
_RENDER_PLAN = "render_plan.json"
_WARNING_LIST = "warning_list.json"
_AUDIT_RESULT = "audit_result.json"


def output_dir(enterprise_id: str, project_id: str) -> Path:
    """渲染产物目录：逐章 Word 输出。"""
    return project_dir(enterprise_id, project_id) / _OUTPUT


def pdf_dir(enterprise_id: str, project_id: str) -> Path:
    """PDF 产物目录（Task 20 使用，Task 19 跨页检测也临时写入此目录）。"""
    return project_dir(enterprise_id, project_id) / _PDF


def render_plan_path(enterprise_id: str, project_id: str) -> Path:
    """渲染计划 JSON 路径。"""
    return project_dir(enterprise_id, project_id) / _RENDER_PLAN


def warning_list_path(enterprise_id: str, project_id: str) -> Path:
    """警告清单 JSON 路径。"""
    return project_dir(enterprise_id, project_id) / _WARNING_LIST


def audit_result_path(enterprise_id: str, project_id: str) -> Path:
    """一致性审计结果 JSON 路径。"""
    return project_dir(enterprise_id, project_id) / _AUDIT_RESULT


def render_checkpoint_path(enterprise_id: str, project_id: str) -> Path:
    """渲染 checkpoint 路径。"""
    return checkpoints_dir(enterprise_id, project_id) / "render.json"


def init_output_dir(enterprise_id: str, project_id: str) -> Path:
    """确保 output/ 目录存在。"""
    d = output_dir(enterprise_id, project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- Task 17：模板库目录布局 ----------

_TEMPLATE = "templates"

# 文件类型常量（与 schema VALID_DOC_TYPES 对应）
DOC_TYPE_LABELS: dict[str, str] = {
    "bid": "招标",
    "procurement": "采购",
    "quotation": "询比价",
}


def templates_dir(enterprise_id: str) -> Path:
    """企业共享模板库根目录。"""
    return _enterprise_dir(enterprise_id) / _TEMPLATE


def template_version_dir(
    enterprise_id: str, agency: str, doc_type: str, name: str, version: int
) -> Path:
    """某版本模板文件集所在目录：templates/<agency>/<doc_type>/<name>/v{version}/。"""
    return templates_dir(enterprise_id) / agency / doc_type / safe_filename(name) / f"v{version}"


def init_templates_dirs(enterprise_id: str) -> list[Path]:
    """初始化企业模板目录骨架。"""
    base = templates_dir(enterprise_id)
    base.mkdir(parents=True, exist_ok=True)
    return [base]


def ensure_within_project(base: Path, target: Path) -> Path:
    """确保 target 解析后位于 base 之内，否则拒绝（防路径穿越）。"""
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if target_resolved != base_resolved and base_resolved not in target_resolved.parents:
        raise PathEscapeError(f"路径 {target} 逃逸项目目录 {base}")
    return target_resolved


# Windows 保留名 / 路径非法字符；同时去除控制字符
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_filename(name: str, *, fallback: str = "unnamed") -> str:
    """把用户文件名规范化为跨平台安全文件名（保留中文与扩展名）。"""
    cleaned = _INVALID_CHARS.sub("_", name).strip(" .")
    if not cleaned:
        return fallback
    if cleaned.lower().split(".")[0] in _RESERVED_NAMES:
        # Windows 保留名：替换主名部分但保留扩展名
        suffix = Path(cleaned).suffix
        cleaned = f"{fallback}{suffix}"
    return cleaned[:180]


def unique_path(target: Path) -> Path:
    """目标已存在时追加 -1/-2 后缀，避免覆盖。"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    parent = target.parent
    for i in range(1, 10_000):
        candidate = parent / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"无法为 {target} 生成不冲突的文件名")
