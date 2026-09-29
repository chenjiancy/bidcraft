"""素材命名规范模块（FR-4 第 2 点）。

全部逻辑无 I/O、无依赖，可独立 pytest 单测。

命名规则：
- 日期统一 YYYYMMDD；长期有效记 "changqi"
- 多页证件后缀 _P0 / _P1（按上传顺序）
- 资质/人员：类型_姓名_编号_有效期
- 业绩：类型_项目名_签订日期_总监
- 荣誉：ry_荣誉名称_颁发单位_年度
- 财务：类型_年度

文件名生成：generate_filename(category, **fields) -> str
文件名解析：parse_filename(name) -> dict | None
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# ---------- 命名模板 ----------

_CERT_TYPE_PREFIX: dict[str, str] = {
    "注册证书": "zcs",
    "岗位证书": "gwz",
    "职称证书": "zc",
    "身份证": "sfz",
    "毕业证": "byz",
    "学位证": "xww",
    "个人荣誉": "ry",
    "退休证": "tti",
    "返聘协议": "fp",
    "简历": "jl",
}

_PERF_TYPE_PREFIX: dict[str, str] = {
    "监理合同": "jlst",
    "竣工报告": "jg",
    "备案证书": "ba",
}

_FIN_TYPE_PREFIX: dict[str, str] = {
    "中小企业声明函": "zxxq",
    "审计报告": "smbg",
    "财务报表": "cwbb",
}

_HONOR_PREFIX = "ry"


def _date_str(d: date | str | None) -> str:
    """日期格式化为 YYYYMMDD；None → 'changqi'。"""
    if isinstance(d, str):
        cleaned = d.replace("年", "-").replace("月", "-").replace("日", "")
        try:
            d = date.fromisoformat(cleaned)
        except ValueError:
            return "changqi"
    if d is None:
        return "changqi"
    return d.strftime("%Y%m%d")


def _strip_non_alpha(s: str) -> str:
    """保留中文、字母、数字，去除多余空格。"""
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    return s[:30]


# ---------- 生成文件名 ----------


def generate_filename(
    category: str,
    name: str,
    *,
    page_index: int | None = None,
    **fields: Any,
) -> str:
    """根据分类和字段生成规范文件名（不含扩展名）。"""
    name = _strip_non_alpha(name)
    suffix = ""

    if category == "qualification" or category == "personnel":
        cert_type = fields.get("cert_type", "")
        person_name = _strip_non_alpha(fields.get("name_person", ""))
        id_no = _strip_non_alpha(fields.get("id_no", ""))
        valid_until = fields.get("valid_until")
        prefix = _CERT_TYPE_PREFIX.get(cert_type, "zc") if cert_type else "zc"
        parts = [prefix]
        if person_name:
            parts.append(person_name)
        if id_no:
            parts.append(id_no)
        parts.append(_date_str(valid_until))
        filename = "_".join(parts)

    elif category == "performance":
        project_name = _strip_non_alpha(fields.get("project_name", ""))
        contract_date = fields.get("contract_date")
        supervisor = _strip_non_alpha(fields.get("supervisor", ""))
        perf_type = fields.get("perf_type", "")
        prefix = _PERF_TYPE_PREFIX.get(perf_type, "xm") if perf_type else "xm"
        parts = [prefix]
        if project_name:
            parts.append(project_name)
        parts.append(_date_str(contract_date))
        if supervisor:
            parts.append(supervisor)
        filename = "_".join(parts)

    elif category == "honor":
        honor_name = _strip_non_alpha(fields.get("honor_name", ""))
        issuer = _strip_non_alpha(fields.get("issuer", ""))
        year = fields.get("year")
        parts = [_HONOR_PREFIX]
        if honor_name:
            parts.append(honor_name)
        if issuer:
            parts.append(issuer)
        if year:
            parts.append(str(year)[:4])
        filename = "_".join(parts)

    elif category == "finance":
        fin_type = fields.get("fin_type", "")
        year = fields.get("year")
        prefix = _FIN_TYPE_PREFIX.get(fin_type, "cw") if fin_type else "cw"
        parts = [prefix]
        if year:
            parts.append(str(year)[:4])
        filename = "_".join(parts)

    else:
        filename = name or "unnamed"

    if page_index is not None and page_index > 0:
        suffix = f"_P{page_index}"

    filename = (filename + suffix)[:120]
    return filename


# ---------- 解析文件名 ----------

_RE_DATE = re.compile(r"(?:^|_)(\d{4})(\d{2})(\d{2})(?:$|_)")
_RE_PAGE = re.compile(r"(_P(\d+))$")

# 所有已知前缀按长度降序，避免短前缀优先匹配（如 jlst 被 jl 截断）
_ALL_PREFIXES: list[str] = sorted(
    list(_CERT_TYPE_PREFIX.values())
    + list(_PERF_TYPE_PREFIX.values())
    + list(_FIN_TYPE_PREFIX.values())
    + [_HONOR_PREFIX],
    key=len,
    reverse=True,
)


def parse_filename(name: str) -> dict[str, Any] | None:
    """从规范文件名解析出结构化字段。"""
    result: dict[str, Any] = {}

    page_match = _RE_PAGE.search(name)
    if page_match:
        result["page_index"] = int(page_match.group(2))
        name = name[: page_match.start()]

    dates = _RE_DATE.findall(name)
    if dates:
        last_date = dates[-1]
        try:
            result["valid_until"] = date(int(last_date[0]), int(last_date[1]), int(last_date[2]))
        except ValueError:
            pass

    remaining = name
    for prefix in _ALL_PREFIXES:
        if remaining.startswith(prefix + "_"):
            reverse_cert = {v: k for k, v in _CERT_TYPE_PREFIX.items()}
            reverse_perf = {v: k for k, v in _PERF_TYPE_PREFIX.items()}
            reverse_fin = {v: k for k, v in _FIN_TYPE_PREFIX.items()}
            if prefix in reverse_cert:
                result["cert_type"] = reverse_cert[prefix]
            elif prefix in reverse_perf:
                result["perf_type"] = reverse_perf[prefix]
            elif prefix in reverse_fin:
                result["fin_type"] = reverse_fin[prefix]
            else:
                result["honor_type"] = True
            result["extra"] = remaining[len(prefix) + 1 :]
            break

    return result if result else None
