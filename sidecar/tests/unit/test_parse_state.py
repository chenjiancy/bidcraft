"""解析状态机单元测试（TR-8.8）。"""

import pytest

from app.parse import state
from app.parse.state import IllegalTransitionError


def test_happy_path_transitions() -> None:
    assert state.can_transition(state.INIT, state.UPLOADED)
    assert state.can_transition(state.UPLOADED, state.PARSING)
    assert state.can_transition(state.PARSING, state.PARSED)


def test_failure_and_cancel_back_to_uploaded() -> None:
    assert state.can_transition(state.PARSING, state.UPLOADED)


def test_parsing_self_loop_for_crash_resume() -> None:
    """崩溃后状态残留 PARSING，续跑重新置位必须合法（幂等）。"""
    state.ensure_transition(state.PARSING, state.PARSING)


def test_parsed_allows_reparse() -> None:
    assert state.can_transition(state.PARSED, state.PARSING)
    assert state.can_transition(state.PARSED, state.UPLOADED)


def test_illegal_transitions_raise() -> None:
    illegal = [
        (state.INIT, state.PARSING),
        (state.INIT, state.PARSED),
        (state.UPLOADED, state.PARSED),
        (state.PARSED, state.INIT),
    ]
    for current, target in illegal:
        with pytest.raises(IllegalTransitionError):
            state.ensure_transition(current, target)
