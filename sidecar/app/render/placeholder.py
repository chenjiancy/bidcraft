"""占位符规范落地（Task 19 t19-1）。

三类占位约定：
- A 类（信息字段）：``{{field_name}}``  —— 从企业/项目/解析清单直接取值
- B 类（素材 OCR）：``{{ocr_field_name}}`` —— 从素材 OCR 文本提取
- 图片类：``{{img_field_name}}`` —— 图片素材，按 material_extract.json 定位

命名规则：
- A 类字段名见 A_CLASS_FIELDS 常量
- B 类字段名见 B_CLASS_FIELDS 常量
- img_ 前缀 → 图片占位
- 其余为 A 类（默认）

Jinja2 控制流（docxtpl 语法）不做占位解析：
- ``{%tr for item in items %}`` / ``{%tr endfor %}``  —— 表格循环行
- ``{%p if condition %}`` / ``{%p endif %}``  —— 条件块
- ``{%- ... %}`` / ``{%+ ... %}`` —— Jinja2 空白控制
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# ---------- A 类信息字段（确定性，从企业/项目/解析清单取值） ----------

A_CLASS_FIELDS: dict[str, str] = {
    # 企业信息
    "enterprise_name": "企业名称",
    "legal_representative": "法定代表人",
    "enterprise_address": "企业地址",
    "enterprise_phone": "企业电话",
    "enterprise_fax": "企业传真",
    "enterprise_postcode": "企业邮编",
    "unified_social_credit_code": "统一社会信用代码",
    # 项目信息
    "project_name": "项目名称",
    "project_number": "项目编号",
    "bid_deadline": "投标截止时间",
    "bid_opening_time": "开标时间",
    "bid_opening_location": "开标地点",
    "bid_bond_amount": "投标保证金金额",
    # 招标人/代理机构信息
    "tenderer_name": "招标人名称",
    "tenderer_address": "招标人地址",
    "tenderer_contact": "招标人联系人",
    "tenderer_phone": "招标人电话",
    "agency_name": "招标代理机构名称",
    "agency_address": "代理机构地址",
    "agency_contact": "代理机构联系人",
    "agency_phone": "代理机构电话",
    # 委托代理人
    "authorized_agent": "委托代理人",
    "agent_id_number": "代理人身份证号",
    # 日期
    "current_date": "当前日期",
    "current_year": "当前年份",
    "bid_date": "投标日期",
    "validity_period": "投标有效期",
}

# ---------- B 类素材 OCR 字段（从素材 OCR 文本提取） ----------

B_CLASS_FIELDS: dict[str, str] = {
    # 人员信息
    "personnel_name": "人员姓名",
    "personnel_id_number": "人员身份证号",
    "personnel_title": "人员职称",
    "personnel_cert_number": "人员证书编号",
    "personnel_position": "人员岗位",
    # 业绩信息
    "performance_project_name": "业绩项目名称",
    "performance_contract_amount": "业绩合同金额",
    "performance_contract_date": "业绩合同签订日期",
    "performance_owner": "业绩建设单位",
    "performance_supervisor": "业绩总监",
    # 资质信息
    "qualification_name": "资质名称",
    "qualification_level": "资质等级",
    "qualification_cert_number": "资质证书编号",
    "qualification_valid_until": "资质有效期",
}

# ---------- 占位符类型 ----------

PlaceholderType = Literal["a_class", "b_class", "image", "control_flow"]


@dataclass(frozen=True)
class Placeholder:
    """解析后的占位符描述。"""

    raw: str  # 原始占位文本，如 "{{enterprise_name}}"
    name: str  # 占位名，如 "enterprise_name"
    type: PlaceholderType  # a_class / b_class / image / control_flow
    description: str = ""  # 字段中文描述
    is_missing: bool = False  # 是否为未识别占位名


# Jinja2 控制流模式（不作为占位符处理）
_CONTROL_FLOW_RE = re.compile(r"\{[%+\-].*?[%+\-]\}", re.DOTALL)

# docxtpl 占位符模式：{{variable}}
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# 图片占位前缀
_IMG_PREFIX = "img_"

# B 类 OCR 占位前缀（内置规则表中的 key）
_B_CLASS_PREFIXES = tuple(B_CLASS_FIELDS.keys())


def classify_placeholder(name: str) -> PlaceholderType:
    """根据占位名分类。

    规则：
    1. img_ 前缀 → image
    2. 在 B_CLASS_FIELDS 中 → b_class
    3. 在 A_CLASS_FIELDS 中 → a_class
    4. 其余 → a_class（默认视为 A 类，运行时标记 is_missing）
    """
    if name.startswith(_IMG_PREFIX):
        return "image"
    if name in B_CLASS_FIELDS:
        return "b_class"
    return "a_class"


def parse_placeholders(text: str) -> list[Placeholder]:
    """从模板文本中解析全部占位符（纯函数，无副作用）。

    跳过 Jinja2 控制流标签（{%...%}），仅提取 {{name}} 形式。
    """
    # 先移除控制流标签，避免误匹配
    cleaned = _CONTROL_FLOW_RE.sub("", text)
    results: list[Placeholder] = []
    seen: set[str] = set()
    for m in _PLACEHOLDER_RE.finditer(cleaned):
        name = m.group(1)
        if name in seen:
            continue
        seen.add(name)
        ptype = classify_placeholder(name)
        desc = ""
        is_missing = False
        if ptype == "a_class":
            desc = A_CLASS_FIELDS.get(name, "")
            if not desc:
                is_missing = True
                desc = f"未识别A类占位: {name}"
        elif ptype == "b_class":
            desc = B_CLASS_FIELDS.get(name, "")
        elif ptype == "image":
            desc = f"图片: {name[len(_IMG_PREFIX) :]}"
        results.append(
            Placeholder(
                raw=m.group(0),
                name=name,
                type=ptype,
                description=desc,
                is_missing=is_missing,
            )
        )
    return results


def parse_placeholders_from_docx(docx_path: str) -> list[Placeholder]:
    """从 docx 文件中提取全部占位符。

    读取所有段落的 text 和表格单元格 text，合并去重。
    """
    from docx import Document  # noqa: PLC0415

    doc = Document(docx_path)
    all_text: list[str] = []

    # 段落文本
    for para in doc.paragraphs:
        all_text.append(para.text)

    # 表格单元格文本
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                all_text.append(cell.text)

    # 合并后统一解析
    combined = "\n".join(all_text)
    return parse_placeholders(combined)
