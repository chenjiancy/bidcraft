"""门槛条件抽取（TR-11.3）：日期 / 金额 / 数量三类硬性条件。

规则库用正则/模式匹配抽取为结构化字段；识别不出的原文片段由调用方
存 raw + 标红（本模块只负责识别，识别失败返回空）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 日期：近3年 / 有效期至2025年12月31日 / 三年内
_DATE = re.compile(
    r"近\s*(\d{1,2})\s*年"
    r"|(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
    r"|(\d{1,2})\s*年内"
)
# 金额：合同金额≥XX万 / 单项合同额100万元以上 / ≥500万元
_AMOUNT = re.compile(
    r"(?:合同金额|合同额|单项合同|造价|投资额|金额)"
    r"[^\n]{0,10}?(?:≥|不低于|不少于|超过|以上|达到)?\s*(\d+(?:\.\d+)?)\s*(万元|元)"
    r"|(?:≥|不低于|不少于)\s*(\d+(?:\.\d+)?)\s*(万元|元)"
)
# 数量：≥3个业绩 / 至少2项 / 不少于5人
_QUANTITY = re.compile(
    r"(?:≥|不少于|至少|不低于)\s*(\d{1,3})\s*(个|项|人|份|名)"
    r"|(\d{1,3})\s*(个|项|人)\s*(?:以上|及以上)"
)


@dataclass(frozen=True)
class Threshold:
    kind: str  # date / amount / quantity
    text: str  # 命中原文（截断）
    value: str  # 结构化值（如 "3年"、"100万元"、"3个"）

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "text": self.text, "value": self.value}


def find_thresholds(text: str) -> list[Threshold]:
    """在一段评分项原文中抽取门槛条件（确定性、可重复）。"""
    found: list[Threshold] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for m in _DATE.finditer(line):
            if m.group(1):
                value = f"{m.group(1)}年"
            elif m.group(2):
                value = f"{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
            else:
                value = f"{m.group(5)}年内"
            if ("date", value) not in seen:
                seen.add(("date", value))
                found.append(Threshold("date", line[:120], value))
        for m in _AMOUNT.finditer(line):
            num = m.group(1) or m.group(3)
            unit = m.group(2) or m.group(4)
            value = f"{num}{unit}"
            if ("amount", value) not in seen:
                seen.add(("amount", value))
                found.append(Threshold("amount", line[:120], value))
        for m in _QUANTITY.finditer(line):
            num = m.group(1) or m.group(3)
            unit = m.group(2) or m.group(4)
            value = f"{num}{unit}"
            if ("quantity", value) not in seen:
                seen.add(("quantity", value))
                found.append(Threshold("quantity", line[:120], value))
    return found
