"""原文锚定校验（TR-10.2 / TR-10.6）：规则粗分与 LLM 校验共用。

判定方式：双方做空白归一化（去除半角/全角空白与换行）后包含匹配。
OCR 与 Markdown 合并会在字符间引入空白差异，归一化后比对可消除；
不改写任何标点与字符，保证"约束必须能在原文找到"的拦截能力。
"""

from __future__ import annotations

import re

_WS_RE = re.compile(r"[\s　]+")


def normalize(text: str) -> str:
    """空白归一化（含全角空格）；不做其他任何改写。"""
    return _WS_RE.sub("", text)


def verify_anchor(snippet: str, source_text: str) -> bool:
    """snippet 是否能在 source_text 中找到（归一化后包含）。"""
    needle = normalize(snippet)
    if not needle:
        return False
    return needle in normalize(source_text)
