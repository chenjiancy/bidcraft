"""规则目录（TR-10.1/10.2/10.3）：18 个解析项的大类粗分 + 标题关键词 + 约束正则。

与 parse/config.py 同 key（目录顺序即配置目录顺序），单项可单测；
规则只做大类粗分与机械约束抽取，评分表深度结构化属 Task 11。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.parse.config import KEY_ITEMS, OPTIONAL_ITEMS

RULES_VERSION = "1.0.0"

Category = Literal["资格条款", "废标条款", "商务评分", "技术要求", "通用"]
CAT_QUALIFICATION: Category = "资格条款"
CAT_INVALID: Category = "废标条款"
CAT_BIZ_SCORE: Category = "商务评分"
CAT_TECH: Category = "技术要求"
CAT_GENERAL: Category = "通用"


@dataclass(frozen=True)
class RuleEntry:
    key: str
    label: str
    category: Category
    keywords: tuple[str, ...]  # 章节/子节标题关键词（归一化后包含匹配）


# key → (category, keywords)；label 取自 parse.config，保证单一事实源
_TABLE: dict[str, tuple[Category, tuple[str, ...]]] = {
    "project_overview": (CAT_GENERAL, ("项目概述", "项目概况", "工程概况", "项目简介", "概述")),
    "tech_score": (
        CAT_TECH,
        ("技术评分", "技术部分评分", "技术标评分", "评分办法", "评标办法", "评分标准"),
    ),
    "project_info": (CAT_GENERAL, ("项目信息", "项目基本情况", "基本情况")),
    "buyer_info": (
        CAT_GENERAL,
        ("招标人信息", "采购人信息", "招标人简介", "采购人简介", "招标人:", "采购人:"),
    ),
    "response_requirements": (
        CAT_GENERAL,
        (
            "响应文件要求",
            "投标文件要求",
            "投标文件的编制",
            "响应文件的编制",
            "投标文件编制",
            "投标人须知",
        ),
    ),
    "agency_info": (CAT_GENERAL, ("代理机构", "招标代理")),
    "business_score": (CAT_BIZ_SCORE, ("商务评分", "商务部分评分", "商务标评分")),
    "invalid_bid": (CAT_INVALID, ("废标", "无效标", "无效投标", "否决投标", "否决其投标")),
    "delivery_service": (
        CAT_TECH,
        ("交货", "交付", "服务要求", "供货要求", "服务期限"),
    ),
    "procurement_list": (CAT_TECH, ("采购清单", "货物清单", "工程量清单", "采购需求", "需求清单")),
    "bid_milestones": (CAT_GENERAL, ("关键节点", "时间安排", "投标截止", "开标时间", "日程安排")),
    "bid_bond": (CAT_QUALIFICATION, ("投标保证金", "保证金")),
    "qualification_review": (
        CAT_QUALIFICATION,
        ("资格性审查", "资格审查", "资格要求", "投标人资格"),
    ),
    "compliance_review": (CAT_INVALID, ("符合性检查", "符合性审查")),
    "bid_opening": (CAT_GENERAL, ("开标",)),
    "bid_evaluation": (CAT_GENERAL, ("评标", "评审")),
    "contract_award": (CAT_GENERAL, ("合同授予", "签订合同", "合同签订", "授予合同")),
    "contract_termination": (CAT_GENERAL, ("合同解除", "合同终止", "解除和终止")),
}


def _build_rules() -> tuple[RuleEntry, ...]:
    entries: list[RuleEntry] = []
    for key, label in (*KEY_ITEMS, *OPTIONAL_ITEMS):
        category, keywords = _TABLE[key]
        entries.append(RuleEntry(key=key, label=label, category=category, keywords=keywords))
    return tuple(entries)


RULES: tuple[RuleEntry, ...] = _build_rules()
RULE_BY_KEY: dict[str, RuleEntry] = {r.key: r for r in RULES}


# ---------- 约束正则（TR-10.1：页数上限/金额/期限/社保月份/数量） ----------


@dataclass(frozen=True)
class ConstraintPattern:
    kind: str
    label: str
    pattern: re.Pattern[str]
    line_hint: re.Pattern[str] | None = None  # 行须命中提示词才套用（降噪）


_PAGE_LIMIT = re.compile(r"(?:不超过|不得超过|不得多于|控制在|限制在)\s*(\d{1,4})\s*页")
_AMOUNT = re.compile(r"(\d+(?:\.\d+)?)\s*(万元|元)")
_AMOUNT_HINT = re.compile(r"保证金|限价|预算|报价|金额|费用|合同额|投资额")
_PERIOD = re.compile(r"(\d{1,4})\s*个?(日历日|工作日|日历天|个月|月|年|天|日)")
_PERIOD_HINT = re.compile(r"期限|工期|服务期|有效期|截止|日内|天内|个月|质保")
_SOCIAL_SECURITY = re.compile(
    r"(?:近|连续)\s*(\d{1,2})\s*个月(?:的)?(?:社保|社会保险)"
    r"|(?:社保|社会保险)[^\n]{0,15}?(\d{1,2})\s*个月"
)
_QUANTITY = re.compile(r"(正本|副本)\s*(\d{1,2})\s*份|(\d{1,2})\s*份")
_QUANTITY_HINT = re.compile(r"份|正本|副本")

CONSTRAINT_PATTERNS: tuple[ConstraintPattern, ...] = (
    ConstraintPattern("page_limit", "页数上限", _PAGE_LIMIT),
    ConstraintPattern("amount", "金额", _AMOUNT, _AMOUNT_HINT),
    ConstraintPattern("period", "期限", _PERIOD, _PERIOD_HINT),
    ConstraintPattern("social_security", "社保月份", _SOCIAL_SECURITY),
    ConstraintPattern("quantity", "数量份数", _QUANTITY, _QUANTITY_HINT),
)


@dataclass(frozen=True)
class Constraint:
    kind: str
    label: str
    text: str  # 命中原文行（截断 200 字）
    value: str  # 捕获值（如 "50页"、"3个月"）
    page_idx: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "text": self.text,
            "value": self.value,
            "page_idx": self.page_idx,
        }


def find_constraints(text: str, page_idx: int | None = None) -> list[Constraint]:
    """在一段原文中机械抽取约束（确定性、可重复；TR-10.3）。"""
    found: list[Constraint] = []
    seen: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for cp in CONSTRAINT_PATTERNS:
            if cp.line_hint is not None and not cp.line_hint.search(line):
                continue
            for m in cp.pattern.finditer(line):
                if cp.kind == "page_limit":
                    value = f"{m.group(1)}页"
                elif cp.kind == "amount":
                    value = f"{m.group(1)}{m.group(2)}"
                elif cp.kind == "period":
                    value = f"{m.group(1)}{m.group(2)}"
                elif cp.kind == "social_security":
                    value = f"{m.group(1) or m.group(2)}个月"
                else:  # quantity
                    value = m.group(0)
                dedupe_key = (cp.kind, line, value)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                found.append(
                    Constraint(
                        kind=cp.kind,
                        label=cp.label,
                        text=line[:200],
                        value=value,
                        page_idx=page_idx,
                    )
                )
    return found
