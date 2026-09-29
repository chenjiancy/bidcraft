"""素材库归档管线（Task 15 TR-15.1～15.15）。

流程：上传至收件箱 → OCR/字段识别 → 按命名规范生成文件名 → 转图片
→ 归档到对应目录 → 入库 + FTS5 增量更新。
全程原子写入（NFR-5）：先写 tmp 再 rename。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from app.materials.dictionary import load_keywords, save_keywords
from app.materials.imaging import pdf_to_pngs, word_to_pdf
from app.materials.naming import generate_filename
from app.materials.ocr import OcrBackend, OcrResult, StubOcr
from app.models.material import VALID_CATEGORIES, Material
from app.parse import paths as path_utils
from app.repositories.base import Scope
from app.repositories.material import MaterialRepository

# ---------- 常量 ----------

_MAX_IMAGE_SIZE_MB = 10
_DEFAULT_DPI = 150
_SUPPORTED_UPLOAD_EXTS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff"}


class ArchivalError(Exception):
    """归档失败异常。"""


# ---------- 归档管线 ----------


def archive_material(
    session: Session,
    enterprise_id: str,
    *,
    project_id: str | None = None,
    original_path: Path,
    category: str,
    ocr_backend: OcrBackend | None = None,
    custom_name: str | None = None,
    custom_filename: str | None = None,
    valid_until: str | None = None,
    fields: dict | None = None,
) -> Material:
    """将文件上传至素材库：收件箱 → 转图 → 归档 → 入库 → FTS5。

    Args:
        session: SQLAlchemy Session
        enterprise_id: 企业 ID
        project_id: 项目 ID（None 表示企业共享库）
        original_path: 原始文件路径（已在收件箱内）
        category: 素材分类（qualification/personnel/performance/honor/finance）
        ocr_backend: OCR 后端，默认用 StubOcr（开发环境）
        custom_name: 用户手动指定的素材名称
        custom_filename: 用户手动指定的规范文件名
        valid_until: 有效期（YYYYMMDD 字符串或 "changqi"）
        fields: 命名字段字典（OCR 识别后填充，或用户提供）
    """
    if category not in VALID_CATEGORIES:
        raise ArchivalError(f"非法素材分类: {category}")

    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    dest_dir = (
        path_utils.project_materials_dir(enterprise_id, project_id)
        if project_id
        else path_utils.materials_category_dir(enterprise_id, category)
    )
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = original_path.suffix.lower()
    if ext not in _SUPPORTED_UPLOAD_EXTS:
        raise ArchivalError(f"不支持的文件格式: {ext}")

    # Step 1: 转图片（PDF/Word → PNG，图片直接复制）
    image_bytes_list: list[bytes] = []
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
        raw = original_path.read_bytes()
        image_bytes_list = [raw]
    elif ext == ".pdf":
        image_bytes_list = pdf_to_pngs(original_path, dpi=_DEFAULT_DPI)
    elif ext in (".doc", ".docx"):
        pdf_tmp = word_to_pdf(original_path)
        try:
            image_bytes_list = pdf_to_pngs(pdf_tmp, dpi=_DEFAULT_DPI)
        finally:
            pdf_tmp.unlink(missing_ok=True)

    if not image_bytes_list:
        raise ArchivalError("无法将文件转为图片")

    # Step 2: OCR 识别
    ocr = ocr_backend or StubOcr()
    combined_ocr: list[str] = []
    for img_bytes in image_bytes_list:
        result: OcrResult = ocr.recognize(img_bytes)
        combined_ocr.append(result.text)
    ocr_text = "\n\n".join(combined_ocr)

    # Step 3: 命名
    name_fields = fields or {}
    if custom_filename:
        filename = custom_filename
    else:
        filename = generate_filename(
            category,
            custom_name or original_path.stem,
            page_index=None,
            **name_fields,
        )

    # Step 4: 写入磁盘（原子写入）
    written_paths: list[str] = []
    # 无项目时素材存于企业共享目录，用企业根目录作路径校验基准；有项目时用项目目录
    _path_base = (
        path_utils.project_dir(enterprise_id, project_id)
        if project_id
        else path_utils.materials_dir(enterprise_id)
    )
    for page_idx, img_bytes in enumerate(image_bytes_list):
        stem = filename if page_idx == 0 else f"{filename}_P{page_idx}"
        safe_stem = path_utils.safe_filename(stem)
        dest_path = path_utils.unique_path(dest_dir / f"{safe_stem}.png")
        dest_path = path_utils.ensure_within_project(_path_base, dest_path)
        tmp = dest_path.with_suffix(dest_path.suffix + ".tmp")
        tmp.write_bytes(img_bytes)
        tmp.replace(dest_path)
        written_paths.append(str(dest_path.relative_to(_path_base)))

    final_path = written_paths[0]  # 第一页作为主文件路径
    # 企业共享素材：file_path 为绝对路径（purge 时直接 unlink）；项目素材：相对路径
    if project_id:
        file_path_val = str(dest_dir / final_path)
    else:
        file_path_val = str(path_utils.materials_dir(enterprise_id) / final_path)
    # Step 5: 入库（事务内）
    material = repo.create(
        enterprise_id=enterprise_id,
        project_id=project_id,
        category=category,
        name=custom_name or original_path.stem,
        filename=filename,
        file_path=file_path_val,
        ocr_text=ocr_text,
        valid_until=valid_until,
    )

    # Step 6: 更新动态词典
    _update_keyword_dict(session, enterprise_id, material.name, ocr_text)

    # Step 6.5: 写入 FTS5 索引（Task 16 查询依据）
    _index_material(enterprise_id, material)

    # Step 7: 清理收件箱（C2 修复：归档成功后不删除用户源文件，收件箱由用户/定时清理管理）
    # 删除源文件会导致用户无法取回原始文件，且中途失败时源文件丢失。

    session.commit()
    return material


def _index_material(enterprise_id: str, material: Material) -> None:
    """把素材写入企业级 FTS5 索引（失败不阻断归档，仅标记未索引）。"""
    from app.materials import fts5 as fts5_mod
    from app.parse.paths import fts5_db_path

    try:
        fts5_mod.fts5_add(
            fts5_db_path(enterprise_id),
            material.id,
            material.name,
            material.ocr_text or "",
        )
        material.indexed = True
    except Exception:
        material.indexed = False


def _update_keyword_dict(session: Session, enterprise_id: str, name: str, ocr_text: str) -> None:
    """识别新关键字并写入动态词典。"""
    from app.parse.paths import keywords_dict_path

    kw_path = keywords_dict_path(enterprise_id)
    kw = load_keywords(kw_path)
    # 从素材名称提取中文关键词（简单实现：保留连续中文字段）
    import re

    chinese_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", name)
    for token in chinese_tokens:
        kw.add("person_names" if len(token) <= 4 else "custom", token, category="custom")
    # 从 OCR 文本提取长词（>= 4 字且非停用词）
    stopwords = {
        "的",
        "了",
        "是",
        "在",
        "有",
        "和",
        "与",
        "及",
        "等",
        "个",
        "这",
        "那",
        "我",
        "你",
        "他",
    }
    tokens = re.findall(r"[\u4e00-\u9fff]{4,}", ocr_text)
    for t in tokens:
        if t not in stopwords:
            kw.add("custom", t, category="custom")
    save_keywords(kw_path, kw)


def archive_multiple_pages(
    session: Session,
    enterprise_id: str,
    project_id: str | None,
    pages: Sequence[Path],
    *,
    category: str,
    name: str,
    fields: dict | None = None,
    valid_until: str | None = None,
) -> Material:
    """多页证件一次性归档（页码按上传顺序 _P0/_P1...）。"""
    if not pages:
        raise ArchivalError("无页素材可归档")

    repo = MaterialRepository(session, Scope(enterprise_id=enterprise_id))
    dest_dir = (
        path_utils.project_materials_dir(enterprise_id, project_id)
        if project_id
        else path_utils.materials_category_dir(enterprise_id, category)
    )
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename_base = generate_filename(category, name, **fields or {})
    all_ocr: list[str] = []
    written: list[str] = []

    for page_idx, src in enumerate(pages):
        if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".tiff"):
            img_bytes = src.read_bytes()
        elif src.suffix.lower() == ".pdf":
            img_bytes_list = pdf_to_pngs(src, dpi=_DEFAULT_DPI)
            if len(img_bytes_list) != 1:
                raise ArchivalError("多页 PDF 需使用 submit_inbox 单页上传")
            img_bytes = img_bytes_list[0]
        elif src.suffix.lower() in (".doc", ".docx"):
            pdf_tmp = word_to_pdf(src)
            try:
                img_bytes_list = pdf_to_pngs(pdf_tmp, dpi=_DEFAULT_DPI)
            finally:
                pdf_tmp.unlink(missing_ok=True)
            if len(img_bytes_list) != 1:
                raise ArchivalError("多页 Word 需使用 submit_inbox 单页上传")
            img_bytes = img_bytes_list[0]
        else:
            raise ArchivalError(f"不支持的格式: {src.suffix}")

        stem = f"{filename_base}_P{page_idx}" if page_idx > 0 else filename_base
        safe_stem = path_utils.safe_filename(stem)
        dest_path = path_utils.unique_path(dest_dir / f"{safe_stem}.png")
        dest_path = path_utils.ensure_within_project(
            path_utils.project_dir(enterprise_id, project_id or ""), dest_path
        )
        tmp = dest_path.with_suffix(dest_path.suffix + ".tmp")
        tmp.write_bytes(img_bytes)
        tmp.replace(dest_path)
        _base = path_utils.project_dir(enterprise_id, project_id or "")
        written.append(str(dest_path.relative_to(_base)))
        all_ocr.append("")  # 多页归档时 OCR 在调用方已执行

    material = repo.create(
        enterprise_id=enterprise_id,
        project_id=project_id,
        category=category,
        name=name,
        filename=filename_base,
        file_path=str(dest_dir / written[0]),
        ocr_text="\n".join(all_ocr) or None,
        valid_until=valid_until,
    )
    _index_material(enterprise_id, material)
    session.commit()
    return material
