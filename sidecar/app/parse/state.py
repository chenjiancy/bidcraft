"""解析阶段项目级状态机（EM-5，architecture.md 6.1 的 Task 8 部分）。

本 Task 落地：``INIT → UPLOADED → PARSING → PARSED``
- PARSING 失败/取消 → 回 UPLOADED（已成功的 checkpoint 项保留，可续跑）；
- 每次转换写 ``app_event``（type=parse_state_change，payload 含 from/to/reason）；
- 异常信息随事件与 checkpoint 留痕，不静默。

后续 Task 扩展：PARSED → SCORE_PARSED（Task 11）
→ PARSE_REVIEW → PARSE_CONFIRMED（Task 13）。
"""

from __future__ import annotations

from typing import Literal

ParseStatus = Literal["INIT", "UPLOADED", "PARSING", "PARSED"]

INIT: ParseStatus = "INIT"
UPLOADED: ParseStatus = "UPLOADED"
PARSING: ParseStatus = "PARSING"
PARSED: ParseStatus = "PARSED"

# 合法转换表（key=当前状态，value=可转入的状态集合）
_TRANSITIONS: dict[ParseStatus, frozenset[ParseStatus]] = {
    INIT: frozenset({UPLOADED}),
    UPLOADED: frozenset({PARSING}),
    # PARSING 自环：进程崩溃后状态残留 PARSING，续跑重新置位（幂等）
    PARSING: frozenset({PARSING, PARSED, UPLOADED}),
    # PARSED 后允许重新解析（用户重新上传/重跑）：经 UPLOADED/PARSING
    PARSED: frozenset({UPLOADED, PARSING}),
}


class IllegalTransitionError(Exception):
    """非法状态转换（编程错误，必须暴露）。"""


def can_transition(current: ParseStatus, target: ParseStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def ensure_transition(current: ParseStatus, target: ParseStatus) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(f"非法解析状态转换：{current} → {target}")
