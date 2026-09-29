"""解析阶段项目级状态机（EM-5，architecture.md 6.1）。

本 Task 落地：``INIT → UPLOADED → PARSING → PARSED``
- PARSING 失败/取消 → 回 UPLOADED（已成功的 checkpoint 项保留，可续跑）；
- 每次转换写 ``app_event``（type=parse_state_change，payload 含 from/to/reason）；
- 异常信息随事件与 checkpoint 留痕，不静默。

Task 11 扩展：``PARSED → SCORE_PARSED``（评分办法解析独立阶段留痕）。
Task 13 扩展：``SCORE_PARSED → PARSE_REVIEW → PARSE_CONFIRMED``
（人工确认清单后解锁业务模块；上游重解析/重试使确认作废，回退 SCORE_PARSED）。
"""

from __future__ import annotations

from typing import Literal

ParseStatus = Literal[
    "INIT",
    "UPLOADED",
    "PARSING",
    "PARSED",
    "SCORE_PARSED",
    "PARSE_REVIEW",
    "PARSE_CONFIRMED",
]

INIT: ParseStatus = "INIT"
UPLOADED: ParseStatus = "UPLOADED"
PARSING: ParseStatus = "PARSING"
PARSED: ParseStatus = "PARSED"
SCORE_PARSED: ParseStatus = "SCORE_PARSED"
PARSE_REVIEW: ParseStatus = "PARSE_REVIEW"
PARSE_CONFIRMED: ParseStatus = "PARSE_CONFIRMED"

# 合法转换表（key=当前状态，value=可转入的状态集合）
_TRANSITIONS: dict[ParseStatus, frozenset[ParseStatus]] = {
    INIT: frozenset({UPLOADED}),
    UPLOADED: frozenset({PARSING}),
    # PARSING 自环：进程崩溃后状态残留 PARSING，续跑重新置位（幂等）
    # Task 11：PARSING → SCORE_PARSED（评分办法解析成功，一次跑完直达）
    PARSING: frozenset({PARSING, PARSED, UPLOADED, SCORE_PARSED}),
    # PARSED 后允许重新解析（用户重新上传/重跑）：经 UPLOADED/PARSING
    # Task 11：PARSED → SCORE_PARSED（评分解析）或重跑回 PARSING
    PARSED: frozenset({UPLOADED, PARSING, SCORE_PARSED}),
    # SCORE_PARSED 后允许重跑评分（回 PARSED）或重跑整解析（回 UPLOADED/PARSING）
    # Task 13：→ PARSE_REVIEW（进入清单复核）
    SCORE_PARSED: frozenset({PARSED, UPLOADED, PARSING, SCORE_PARSED, PARSE_REVIEW}),
    # Task 13：PARSE_REVIEW → PARSE_CONFIRMED（全部确认）；→ SCORE_PARSED（上游重试回退）
    PARSE_REVIEW: frozenset({SCORE_PARSED, PARSE_CONFIRMED}),
    # Task 13：PARSE_CONFIRMED 后允许重解析（回退使确认失效）
    PARSE_CONFIRMED: frozenset({SCORE_PARSED, PARSED, UPLOADED, PARSING}),
}


class IllegalTransitionError(Exception):
    """非法状态转换（编程错误，必须暴露）。"""


def can_transition(current: ParseStatus, target: ParseStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def ensure_transition(current: ParseStatus, target: ParseStatus) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(f"非法解析状态转换：{current} → {target}")
