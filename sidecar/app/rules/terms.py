"""术语识别（TR-10.4）：判定文件类型（招标/采购/询比价）与术语体系；绝不改写原文。

- 文件类型判定：取首 N 页文本，匹配特征关键词；
- 术语体系映射：招标→投标人/投标文件/投标函，采购→供应商/响应文件/报价函，
  询比价→询比价响应文件（也可简称响应文件）；
- 动态词典：软件新产生文字时按判定的类型选择术语，源文件原文原样保留。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DocType = Literal["招标", "采购", "询比价", "未知"]

_DOC_TYPE_PATTERNS: dict[DocType, tuple[re.Pattern[str], ...]] = {
    "招标": (
        re.compile(r"招标(项目|公告|文件|投标|投标人)"),
        re.compile(r"(投标人|投标文件|投标函|中标)"),
    ),
    "采购": (
        re.compile(r"采购(文件|项目|需求|公告|人)"),
        re.compile(r"(供应商|响应文件|报价函|成交)"),
    ),
    "询比价": (
        re.compile(r"询比价"),
        re.compile(r"比价(采购|响应)"),
    ),
}

# 按项目记忆，供后续生成文字使用（不覆盖原文）
_TERM_MAP: dict[DocType, dict[str, str]] = {
    "招标": {
        "主体": "投标人",
        "文件": "投标文件",
        "函件": "投标函",
        "中标": "中标",
    },
    "采购": {
        "主体": "供应商",
        "文件": "响应文件",
        "函件": "报价函",
        "中标": "成交",
    },
    "询比价": {
        "主体": "供应商",
        "文件": "询比价响应文件",
        "函件": "报价函",
        "中标": "成交",
    },
}

# 默认兜底：未知→招标体系（最常用）
_DEFAULT_DOC_TYPE: DocType = "招标"


@dataclass(frozen=True)
class TermSet:
    doc_type: DocType
    words: dict[str, str]  # 如上表

    def substitute(self, label: str) -> str:
        """获取该类型下的术语（label ∈ {主体, 文件, 函件, 中标}）。"""
        return self.words.get(label, label)


def detect_doc_type(text: str) -> DocType:
    """按特征关键词匹配计数，取最高分的类型；全部不满足则未知。"""
    counts: dict[DocType, int] = {"招标": 0, "采购": 0, "询比价": 0}
    for dtype, patterns in _DOC_TYPE_PATTERNS.items():
        for pat in patterns:
            counts[dtype] += len(pat.findall(text))
    if not any(counts.values()):
        return "未知"
    return max(counts, key=lambda k: counts[k])


def term_set_for(doc_type: DocType | None) -> TermSet:
    dtype = doc_type or _DEFAULT_DOC_TYPE
    return TermSet(doc_type=dtype, words=_TERM_MAP.get(dtype, _TERM_MAP[_DEFAULT_DOC_TYPE]))


# 动态词典持久化辅助（extract 层调用，写入 <data_root>/config/keywords.dict.json）


def build_dict_payload(doc_type: DocType) -> dict[str, str]:
    """供写入 config/keywords.dict.json 的纯 dict。"""
    words = term_set_for(doc_type).words
    return {"doc_type": doc_type, **words}
