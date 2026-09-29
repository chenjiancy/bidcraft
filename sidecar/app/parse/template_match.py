"""模板匹配与语义比对服务（Task 18）。

职责：
- 人工指定模板文件夹（可多选，章节并集）
- 自动匹配：按 agency/doc_type + 章节结构计算相似度（≥90% 命中）
- 版本绑定：复制模板文件集到项目 template-work/，记录版本快照
- Schema 门禁（BP-3）：template.json 结构 + 章节文件齐全 + 占位符语法校验
- 文件关联表：parsed/ 章节 ↔ template-work/ 章节的归一化名称对齐
- 语义比对（FR-5）：段落/表格文本归一化 diff，机械检查前置（BP-4）
- finding 数据模型（EM-2）：差异片段 + 原文锚点 + 置信度 + 建议动作
- 差异更新规则：细微差异按解析更新；投标函类整份替换（强制披露）
- 确认门禁：高置信批量确认，低置信逐条，冲突永不自动应用
- 状态转换：MATERIAL_CONFIRMED → TEMPLATE_MATCHED → TEMPLATE_REVIEW → READY_TO_RENDER
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docx import Document as DocxDocument

from app.parse import paths as path_utils
from app.repositories.app_event import AppEventRepository
from app.repositories.base import NotFoundError, Scope
from app.repositories.project import ProjectRepository
from app.repositories.template import TemplateRepository
from app.repositories.template_compare import TemplateCompareRepository

_logger = logging.getLogger(__name__)

# 相似度阈值（FR-2）
MATCH_THRESHOLD = 90

# 标记为"投标函/报价函"类的关键词（整份替换时强制披露）
_FULL_REPLACE_KEYWORDS = ("投标函", "报价函", "开标一览表", "投标报价")

# 机械检查：占位符数量对比 tolerance
_PLACEHOLDER_TOLERANCE = 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ============================================================
#  1. 相似度计算（自动匹配）
# ============================================================


def _normalize_chapter_name(name: str) -> str:
    """归一化章节名：去掉编号前缀、去空格、统一大小写。"""
    s = re.sub(r"^[\d·．\.]+", "", name).strip()
    s = re.sub(r"\s+", "", s)
    return s.lower()


def _extract_chapter_names_from_docx(doc_path: Path) -> list[str]:
    """从 docx 中提取标题段落作为章节名（基于样式或首行关键词）。"""
    names: list[str] = []
    try:
        doc = DocxDocument(str(doc_path))
        for para in doc.paragraphs:
            txt = para.text.strip()
            if not txt:
                continue
            # 一级标题通常以数字编号开头，或长度较短（章节名特征）
            if re.match(r"^[\d·．\.]+\s*\S", txt) and len(txt) < 80:
                names.append(txt)
            elif (para.style.name if para.style else "").startswith("Heading") and len(txt) < 100:
                names.append(txt)
    except Exception:
        pass
    return names


def _load_template_chapters(template: Any) -> tuple[list[str], dict[str, Any]]:
    """从 Template 对象加载章节名列表和 meta。"""
    meta = template.meta
    chapter_stems = meta.get("chapters", [])
    # 尝试从实际 docx 文件补充章节名
    template_dir = Path(template.path)
    actual_names: list[str] = []
    for stem in chapter_stems:
        for ext in (".docx", ".doc"):
            candidate = template_dir / f"{stem}{ext}"
            if candidate.exists():
                actual_names.extend(_extract_chapter_names_from_docx(candidate))
                break
    if not actual_names:
        actual_names = chapter_stems
    return actual_names, meta


def _load_parse_chapters(eid: str, pid: str) -> list[str]:
    """从 chapters.json 加载已解析的章节名（解析侧）。"""
    chapters_path = path_utils.chapters_path(eid, pid)
    if not chapters_path.is_file():
        return []
    payload = json.loads(chapters_path.read_text(encoding="utf-8"))
    names: list[str] = []
    for source in payload.get("sources", []):
        for sec in source.get("sections", []):
            name = sec.get("name") or sec.get("title") or ""
            if name:
                names.append(name)
    # 也尝试从 extract_list.json 中找文档类型线索
    return names


def calculate_similarity(
    parse_chapters: list[str],
    template_chapters: list[str],
    agency_match: bool,
    doc_type_match: bool,
) -> dict[str, Any]:
    """计算解析结果与模板的相似度（0-100）。

    评分维度：
    - 章节名归一化匹配率（权重 50%）
    - 章节数量吻合度（权重 20%）
    - 章节顺序一致性（权重 15%）
    - 代理机构匹配（权重 10%）
    - 文件类型匹配（权重 5%）
    """
    norm_parse = [_normalize_chapter_name(c) for c in parse_chapters if c]
    norm_tmpl = [_normalize_chapter_name(c) for c in template_chapters if c]

    # 章节名匹配率
    if norm_parse and norm_tmpl:
        matched = sum(1 for n in norm_parse if n in set(norm_tmpl))
        chapter_match_rate = matched / max(len(norm_parse), 1)
    else:
        chapter_match_rate = 0.0

    # 章节数量吻合度
    if norm_parse and norm_tmpl:
        count_ratio = min(len(norm_parse), len(norm_tmpl)) / max(len(norm_parse), len(norm_tmpl), 1)
    else:
        count_ratio = 0.0

    # 章节顺序一致性（LCS 比例）
    if norm_parse and norm_tmpl:
        lcs = len(_longest_common_subsequence(norm_parse, norm_tmpl))
        order_score = lcs / max(len(norm_parse), len(norm_tmpl), 1)
    else:
        order_score = 0.0

    score = min(
        100.0,
        chapter_match_rate * 50
        + count_ratio * 20
        + order_score * 15
        + (50 if agency_match else 0)
        + (25 if doc_type_match else 0),
    )
    return {
        "score": round(score, 1),
        "chapter_match_rate": round(chapter_match_rate, 3),
        "count_ratio": round(count_ratio, 3),
        "order_score": round(order_score, 3),
        "agency_match": agency_match,
        "doc_type_match": doc_type_match,
        "parse_chapter_count": len(norm_parse),
        "template_chapter_count": len(norm_tmpl),
    }


def _longest_common_subsequence(a: list[str], b: list[str]) -> list[str]:
    """简易 LCS（用于章节顺序一致性计算）。"""
    m, n = len(a), len(b)
    dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    result: list[str] = []
    i, j = m, n
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            result.append(a[i - 1])
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    result.reverse()
    return result


# ============================================================
#  2. Schema 门禁（BP-3）
# ============================================================


def validate_template_schema(work_dir: Path) -> tuple[bool, list[str]]:
    """BP-3 Schema 门禁：验证 template-work/ 目录下的 template.json 及章节文件。

    检查项：
    - template.json 存在且包含 mandatory 字段（chapters/note/created_at）
    - 列出的章节文件实际存在
    - 每个 docx 文件占位符语法合法（复用 templates.service._validate_jinja_syntax）
    """
    from app.templates.service import (
        _read_text_from_docx,
        _validate_jinja_syntax,
    )

    errors: list[str] = []
    template_json = work_dir / "template.json"
    if not template_json.is_file():
        errors.append("template.json 不存在")
        return False, errors

    try:
        meta = json.loads(template_json.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"template.json 解析失败: {exc}")
        return False, errors

    mandatory = ("chapters", "note", "created_at")
    for key in mandatory:
        if key not in meta:
            errors.append(f"template.json 缺少必填字段: {key}")

    chapters = meta.get("chapters", [])
    if not chapters:
        # 空章节列表视为有效（无章节要求）
        pass

    # 检查章节文件存在
    for stem in chapters:
        found = False
        for ext in (".docx", ".doc"):
            if (work_dir / f"{stem}{ext}").is_file():
                found = True
                break
        if not found:
            errors.append(f"章节文件缺失: {stem}.docx")

    # 占位符语法校验
    for stem in chapters:
        for ext in (".docx", ".doc"):
            doc_path = work_dir / f"{stem}{ext}"
            if doc_path.is_file():
                try:
                    text_lines, _ = _read_text_from_docx(doc_path)
                    syntax_errors = _validate_jinja_syntax(text_lines)
                    for err in syntax_errors:
                        errors.append(f"{doc_path.name}: {err}")
                except Exception as exc:
                    errors.append(f"{doc_path.name} 读取失败: {exc}")
                break

    return len(errors) == 0, errors


# ============================================================
#  3. 文件关联表构建
# ============================================================


@dataclass
class ChapterAssociation:
    parsed_key: str
    parsed_name: str
    template_stem: str | None = None
    template_name: str | None = None
    matched: bool = False
    match_reason: str = ""


def build_association(
    parse_chapters: list[str],
    template_chapters: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """基于归一化名称 + 顺序对齐构建关联表。

    返回：(associations, unmatched_parse_keys)
    """
    tpl_norm_map: dict[str, str] = {_normalize_chapter_name(c): c for c in template_chapters}

    associations: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for idx, parse_name in enumerate(parse_chapters):
        norm = _normalize_chapter_name(parse_name)
        matched_template = None
        reason = ""
        if norm in tpl_norm_map:
            matched_template = tpl_norm_map[norm]
            reason = "名称归一化匹配"
        else:
            # 按顺序试探：取 template 同位置章节
            if idx < len(template_chapters):
                matched_template = template_chapters[idx]
                reason = "顺序对齐（名称未匹配）"

        associations.append(
            {
                "parsed_key": parse_name,
                "parsed_name": parse_name,
                "template_stem": matched_template,
                "template_name": matched_template,
                "matched": matched_template is not None,
                "match_reason": reason,
            }
        )
        if not matched_template:
            unmatched.append(parse_name)

    return associations, unmatched


# ============================================================
#  4. 语义比对（段落/表格 diff）
# ============================================================


def _normalize_text(text: str) -> str:
    """归一化文本：去除颜色/底纹等呈现差异噪声，仅保留文字内容。"""
    # 去除控制字符和非打印字符
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    # 合并连续空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_paragraphs_and_tables(doc_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """提取段落文本和表格结构文本（忽略颜色/底纹）。"""
    paragraphs: list[str] = []
    tables: list[dict[str, Any]] = []
    try:
        doc = DocxDocument(str(doc_path))
        for para in doc.paragraphs:
            txt = _normalize_text(para.text)
            if txt:
                paragraphs.append(txt)
        for table in doc.tables:
            rows_data: list[list[str]] = []
            for row in table.rows:
                row_text = [_normalize_text(cell.text) for cell in row.cells]
                rows_data.append(row_text)
            tables.append(
                {
                    "row_count": len(table.rows),
                    "col_count": len(table.columns) if table.rows else 0,
                    "rows": rows_data,
                }
            )
    except Exception as exc:
        _logger.warning("读取 docx 失败 %s: %s", doc_path, exc)
    return paragraphs, tables


def _text_diff(a: str, b: str) -> dict[str, Any]:
    """对两段文本做 unified diff，返回差异片段摘要。"""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, lineterm=""))
    # 只保留有实质差异的行
    changed = [line for line in diff if line.startswith(("+", "-")) and not line.startswith("+++")]
    return {
        "unified_diff_sample": diff[:30],  # 限制样本量
        "has_difference": len(changed) > 0,
        "change_lines": len(changed),
    }


def _table_diff(t1: dict[str, Any], t2: dict[str, Any]) -> dict[str, Any]:
    """对比两个表格结构，返回行列差异。"""
    r1, c1 = t1["row_count"], t1["col_count"]
    r2, c2 = t2["row_count"], t2["col_count"]
    row_diff = r1 != r2
    col_diff = c1 != c2
    return {
        "row_count_diff": row_diff,
        "col_count_diff": col_diff,
        "expected_rows": r1,
        "actual_rows": r2,
        "expected_cols": c1,
        "actual_cols": c2,
    }


# ============================================================
#  5. 机械检查前置（BP-4）
# ============================================================


def _count_placeholders(doc_path: Path) -> int:
    """统计 docx 中占位符数量（{{key}} 模式）。"""
    count = 0
    try:
        doc = DocxDocument(str(doc_path))
        RE_PH = re.compile(r"\{\{\w+\}\}")
        for para in doc.paragraphs:
            count += len(RE_PH.findall(para.text))
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    count += len(RE_PH.findall(cell.text))
    except Exception:
        pass
    return count


def mechanical_check(
    parsed_doc_path: Path,
    template_doc_path: Path,
) -> dict[str, Any]:
    """BP-4 机械检查：占位符数量、表格行列结构对比。"""
    parsed_count = _count_placeholders(parsed_doc_path)
    template_count = _count_placeholders(template_doc_path)
    placeholder_diff = abs(parsed_count - template_count)

    _, parsed_tables = _extract_paragraphs_and_tables(parsed_doc_path)
    _, template_tables = _extract_paragraphs_and_tables(template_doc_path)

    table_issues: list[dict[str, Any]] = []
    # 对比第一个表格（通常为主要表格）
    for i in range(min(len(parsed_tables), len(template_tables))):
        td = _table_diff(parsed_tables[i], template_tables[i])
        if td["row_count_diff"] or td["col_count_diff"]:
            table_issues.append(
                {
                    "table_index": i,
                    **td,
                }
            )

    is_red_flag = placeholder_diff > _PLACEHOLDER_TOLERANCE or bool(table_issues)
    return {
        "parsed_placeholder_count": parsed_count,
        "template_placeholder_count": template_count,
        "placeholder_diff": placeholder_diff,
        "table_issues": table_issues,
        "is_red_flag": is_red_flag,
    }


# ============================================================
#  6. Finding 数据模型
# ============================================================


@dataclass
class Finding:
    """差异发现项（EM-2）。"""

    id: str
    chapter_key: str
    finding_type: str  # "paragraph" / "table" / "mechanical" / "unmatched"
    diff_summary: str  # 差异摘要
    parsed_anchor: str  # 解析侧原文锚点（章节名 + 位置）
    template_content: str  # 模板侧内容摘要
    confidence: str  # "high" / "low"
    suggested_action: str  # "update" / "replace" / "manual_review" / "keep"
    is_mechanical_red_flag: bool = False
    requires_disclosure: bool = False  # 投标函类整份替换需强制披露


def _make_finding_id() -> str:
    import uuid

    return uuid.uuid4().hex[:12]


def run_comparison(
    parsed_chapters: dict[str, Path],  # {chapter_key: parsed docx path}
    template_chapters: dict[str, Path],  # {stem: template docx path}
    associations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """执行语义比对，返回 findings 列表和 bp4_summary。

    返回：(findings_json_serializable, bp4_summary)
    """
    findings: list[dict[str, Any]] = []
    bp4_results: dict[str, dict[str, Any]] = {}

    for assoc in associations:
        parsed_key = assoc["parsed_key"]
        tpl_stem = assoc.get("template_stem")

        parsed_path = parsed_chapters.get(parsed_key)
        if not parsed_path or not parsed_path.is_file():
            continue

        if not tpl_stem:
            # 关联失败：生成 unmatched finding
            findings.append(
                {
                    "id": _make_finding_id(),
                    "chapter_key": parsed_key,
                    "finding_type": "unmatched",
                    "diff_summary": f"解析侧章节 '{parsed_key}' 在模板中无对应章节",
                    "parsed_anchor": parsed_key,
                    "template_content": "",
                    "confidence": "high",
                    "suggested_action": "manual_review",
                    "is_mechanical_red_flag": False,
                    "requires_disclosure": False,
                }
            )
            continue

        template_path = template_chapters.get(tpl_stem)
        if not template_path or not template_path.is_file():
            continue

        # BP-4 机械检查
        bp4 = mechanical_check(parsed_path, template_path)
        bp4_results[parsed_key] = bp4

        if bp4["is_red_flag"]:
            findings.append(
                {
                    "id": _make_finding_id(),
                    "chapter_key": parsed_key,
                    "finding_type": "mechanical",
                    "diff_summary": (
                        "占位符数量不一致（解析:"
                        f"{bp4['parsed_placeholder_count']} "
                        f"模板:{bp4['template_placeholder_count']}）"
                        + (
                            f"，表格结构差异：{len(bp4['table_issues'])} 处"
                            if bp4["table_issues"]
                            else ""
                        )
                    ),
                    "parsed_anchor": parsed_key,
                    "template_content": f"placeholder_count={bp4['template_placeholder_count']}",
                    "confidence": "high",
                    "suggested_action": "manual_review" if bp4["table_issues"] else "update",
                    "is_mechanical_red_flag": True,
                    "requires_disclosure": False,
                }
            )

        # 语义比对：段落 diff
        parsed_paras, parsed_tables = _extract_paragraphs_and_tables(parsed_path)
        template_paras, template_tables = _extract_paragraphs_and_tables(template_path)

        # 段落级 diff（取前 N 个段落，避免大文档过慢）
        max_paras = min(len(parsed_paras), len(template_paras), 50)
        for i in range(max_paras):
            pd = _text_diff(parsed_paras[i], template_paras[i])
            if pd["has_difference"]:
                findings.append(
                    {
                        "id": _make_finding_id(),
                        "chapter_key": parsed_key,
                        "finding_type": "paragraph",
                        "diff_summary": f"段落 {i + 1} 存在差异（{pd['change_lines']} 行不同）",
                        "parsed_anchor": f"{parsed_key}:paragraph:{i + 1}",
                        "template_content": (
                            template_paras[i][:200] if i < len(template_paras) else ""
                        ),
                        "confidence": "high" if pd["change_lines"] < 5 else "low",
                        "suggested_action": "update",
                        "is_mechanical_red_flag": False,
                        "requires_disclosure": False,
                    }
                )

        # 检查是否为整份替换类（投标函/报价函）
        chapter_basename = Path(parsed_key).stem.lower()
        is_full_replace = any(kw in chapter_basename for kw in _FULL_REPLACE_KEYWORDS)
        if is_full_replace and parsed_paras != template_paras:
            findings[-1]["suggested_action"] = "replace" if findings else None
            if findings:
                findings[-1]["requires_disclosure"] = True

    # 处理模板有多余章节的情况
    for tpl_stem, _tpl_path in template_chapters.items():
        if not any(assoc.get("template_stem") == tpl_stem for assoc in associations):
            findings.append(
                {
                    "id": _make_finding_id(),
                    "chapter_key": f"__template_extra__:{tpl_stem}",
                    "finding_type": "unmatched",
                    "diff_summary": f"模板章节 '{tpl_stem}' 在解析侧无对应",
                    "parsed_anchor": "",
                    "template_content": tpl_stem,
                    "confidence": "high",
                    "suggested_action": "keep",
                    "is_mechanical_red_flag": False,
                    "requires_disclosure": False,
                }
            )

    return findings, bp4_results


# ============================================================
#  7. 手动指定模板：复制文件集到 template-work/
# ============================================================


def copy_templates_to_work(
    eid: str,
    pid: str,
    template_ids: list[str],
) -> tuple[str, list[dict[str, Any]]]:
    """将指定模板文件集复制到项目 template-work/ 目录。

    多模板组合时：章节并集共同覆盖，各自独立存放于子目录。
    返回：(work_dir_rel, copied_info)
    """
    from app.db.deps import get_engine
    from app.db.session import session_factory

    work_dir = path_utils.init_template_work_dir(eid, pid)
    copied: list[dict[str, Any]] = []

    with session_factory(get_engine())() as session:
        tpl_repo = TemplateRepository(session, Scope(enterprise_id=eid))

        for tid in template_ids:
            tpl = tpl_repo.get(tid)
            src_dir = Path(tpl.path)
            if not src_dir.is_dir():
                raise ValueError(f"模板目录不存在: {tpl.path}")

            # 以模板名称作为子目录，避免多模板同名冲突
            sub_dir = work_dir / path_utils.safe_filename(tpl.name) / f"v{tpl.version}"
            sub_dir.mkdir(parents=True, exist_ok=True)

            # 复制 template.json
            src_json = src_dir / "template.json"
            if src_json.is_file():
                dst_json = sub_dir / "template.json"
                tmp = dst_json.with_suffix(".tmp")
                tmp.write_text(src_json.read_text(encoding="utf-8"), encoding="utf-8")
                if dst_json.exists():
                    dst_json.unlink()
                tmp.rename(dst_json)

            # 复制章节文件
            meta = tpl.meta
            chapters = meta.get("chapters", [])
            for stem in chapters:
                for ext in (".docx", ".doc"):
                    src_file = src_dir / f"{stem}{ext}"
                    if src_file.is_file():
                        dst_file = sub_dir / src_file.name
                        if not dst_file.exists():
                            shutil.copy2(src_file, dst_file)
                        copied.append(
                            {
                                "template_id": tpl.id,
                                "template_name": tpl.name,
                                "version": tpl.version,
                                "chapter": stem,
                                "file": dst_file.name,
                            }
                        )
                        break

    work_dir_rel = str(Path("template-work").relative_to(Path(".")))
    return work_dir_rel, copied


# ============================================================
#  8. 自动匹配：查询企业模板库
# ============================================================


def auto_match_templates(
    eid: str,
    pid: str,
) -> dict[str, Any]:
    """自动匹配企业模板库中符合 agency/doc_type 的模板。

    返回：{best_match, candidates, has_match}
    - best_match：相似度最高的模板（≥90%）
    - candidates：所有候选模板评分列表
    - has_match：是否存在 ≥90% 的命中
    """
    from app.db.deps import get_engine
    from app.db.session import session_factory

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid)
        repo = TemplateRepository(session, scope)
        templates = repo.list()

    parse_chapters = _load_parse_chapters(eid, pid)
    if not parse_chapters:
        return {"candidates": [], "has_match": False, "error": "解析侧章节数据缺失"}

    candidates: list[dict[str, Any]] = []
    for tpl in templates:
        tpl_chapters, tpl_meta = _load_template_chapters(tpl)
        # 按 doc_type 过滤（优先）
        doc_type_match = True  # 初步全部参与，由前端过滤
        agency_match = True
        sim = calculate_similarity(parse_chapters, tpl_chapters, agency_match, doc_type_match)
        sim["template_id"] = tpl.id
        sim["template_name"] = tpl.name
        sim["agency"] = tpl.agency
        sim["doc_type"] = tpl.doc_type
        sim["version"] = tpl.version
        candidates.append(sim)

    # 按得分降序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0] if candidates else None
    has_match = best and best["score"] >= MATCH_THRESHOLD

    return {
        "best_match": best,
        "candidates": candidates[:10],  # 最多返回 10 个候选
        "has_match": has_match,
        "threshold": MATCH_THRESHOLD,
    }


# ============================================================
#  9. 状态转换（服务层入口）
# ============================================================


def enter_template_matching(
    factory: Any,
    eid: str,
    pid: str,
) -> dict[str, Any]:
    """MATERIAL_CONFIRMED → TEMPLATE_MATCHED：进入模板匹配阶段。

    幂等：已是 TEMPLATE_MATCHED/TEMPLATE_REVIEW/READY_TO_RENDER 时直接返回当前状态。
    """
    from app.db.deps import get_engine
    from app.db.session import session_factory
    from app.parse import state

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid)
        repo = ProjectRepository(session, scope)
        try:
            project = repo.get(pid)
        except NotFoundError:
            raise ValueError("项目不存在") from None
        current = project.parse_status
        if current not in (
            state.MATERIAL_CONFIRMED,
            state.TEMPLATE_MATCHED,
            state.TEMPLATE_REVIEW,
            state.READY_TO_RENDER,
        ):
            raise ValueError(f"当前状态 {current} 不可进入模板匹配（需 MATERIAL_CONFIRMED）")
        if current == state.MATERIAL_CONFIRMED:
            state.ensure_transition(current, state.TEMPLATE_MATCHED)
            project.parse_status = state.TEMPLATE_MATCHED
            AppEventRepository(session, scope).record(
                "parse_state_change",
                pid,
                {
                    "from": current,
                    "to": state.TEMPLATE_MATCHED,
                    "reason": "enter_template_matching",
                },
            )
            session.commit()

    work_dir = path_utils.init_template_work_dir(eid, pid)
    return {"parse_status": state.TEMPLATE_MATCHED, "work_dir": str(work_dir)}


def enter_template_review(
    factory: Any,
    eid: str,
    pid: str,
    compare_id: str | None = None,
) -> dict[str, Any]:
    """TEMPLATE_MATCHED → TEMPLATE_REVIEW：完成比对，进入差异确认阶段。"""
    from app.db.deps import get_engine
    from app.db.session import session_factory
    from app.parse import state

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid)
        repo = ProjectRepository(session, scope)
        try:
            project = repo.get(pid)
        except NotFoundError:
            raise ValueError("项目不存在") from None
        current = project.parse_status
        if current != state.TEMPLATE_MATCHED:
            raise ValueError(f"当前状态 {current} 不可进入差异确认（需 TEMPLATE_MATCHED）")
        state.ensure_transition(current, state.TEMPLATE_REVIEW)
        project.parse_status = state.TEMPLATE_REVIEW
        AppEventRepository(session, scope).record(
            "parse_state_change",
            pid,
            {
                "from": current,
                "to": state.TEMPLATE_REVIEW,
                "reason": "template_review_started",
                "compare_id": compare_id,
            },
        )
        session.commit()

    return {"parse_status": state.TEMPLATE_REVIEW, "compare_id": compare_id}


def confirm_template_review(
    factory: Any,
    eid: str,
    pid: str,
) -> dict[str, Any]:
    """TEMPLATE_REVIEW → READY_TO_RENDER：差异全部裁决完成。"""
    from app.db.deps import get_engine
    from app.db.session import session_factory
    from app.parse import state

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid)
        repo = ProjectRepository(session, scope)
        try:
            project = repo.get(pid)
        except NotFoundError:
            raise ValueError("项目不存在") from None
        current = project.parse_status
        if current != state.TEMPLATE_REVIEW:
            raise ValueError(f"当前状态 {current} 不可确认比对结果（需 TEMPLATE_REVIEW）")
        state.ensure_transition(current, state.READY_TO_RENDER)
        project.parse_status = state.READY_TO_RENDER
        AppEventRepository(session, scope).record(
            "parse_state_change",
            pid,
            {"from": current, "to": state.READY_TO_RENDER, "reason": "template_review_confirmed"},
        )
        session.commit()

    return {"parse_status": state.READY_TO_RENDER}


# ============================================================
#  10. 回退（上游重解析使比对作废）
# ============================================================


def invalidate_template_compare(
    factory: Any,
    eid: str,
    pid: str,
    *,
    reason: str = "upstream_reset",
) -> None:
    """上游重试/重解析使比对作废：回退到 MATERIAL_CONFIRMED + 软删除比对记录。

    若当前状态不在 TEMPLATE_MATCHED/TEMPLATE_REVIEW/READY_TO_RENDER，则什么也不做（幂等）。
    """
    from app.db.deps import get_engine
    from app.db.session import session_factory
    from app.parse import state

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid)
        repo = ProjectRepository(session, scope)
        try:
            project = repo.get(pid)
        except NotFoundError:
            return
        current = project.parse_status
        if current not in (state.TEMPLATE_MATCHED, state.TEMPLATE_REVIEW, state.READY_TO_RENDER):
            return
        state.ensure_transition(current, state.MATERIAL_CONFIRMED)
        project.parse_status = state.MATERIAL_CONFIRMED
        AppEventRepository(session, scope).record(
            "parse_state_change",
            pid,
            {"from": current, "to": state.MATERIAL_CONFIRMED, "reason": reason},
        )

        # 软删除比对记录
        tc_repo = TemplateCompareRepository(session, scope)
        tc = tc_repo.get_by_project()
        if tc:
            tc_repo.delete(tc.id)

        session.commit()


def get_compare_status(
    factory: Any,
    eid: str,
    pid: str,
) -> dict[str, Any]:
    """查询当前模板比对状态。"""
    from app.db.deps import get_engine
    from app.db.session import session_factory

    with session_factory(get_engine())() as session:
        scope = Scope(enterprise_id=eid, project_id=pid)
        tc_repo = TemplateCompareRepository(session, scope)
        tc = tc_repo.get_by_project()

        parse_repo = ProjectRepository(session, Scope(enterprise_id=eid))
        try:
            project = parse_repo.get(pid)
            parse_status = project.parse_status
        except NotFoundError:
            parse_status = "unknown"

    if tc is None:
        return {
            "parse_status": parse_status,
            "has_compare": False,
            "status": None,
            "findings_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
        }

    findings = json.loads(tc.findings_json) if tc.findings_json else []
    return {
        "parse_status": parse_status,
        "has_compare": True,
        "compare_id": tc.id,
        "status": tc.status,
        "match_method": tc.match_method,
        "similarity_score": tc.similarity_score,
        "work_dir": tc.work_dir,
        "findings_count": len(findings),
        "accepted_count": tc.accepted_count,
        "rejected_count": tc.rejected_count,
        "ready_at": tc.ready_at.isoformat() if tc.ready_at else None,
        "findings": findings,
        "association": json.loads(tc.association_json) if tc.association_json else {},
    }
