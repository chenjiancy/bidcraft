"""模板匹配状态转换单元测试（TR-18.14）。"""

import pytest

from app.parse import state
from app.parse.state import IllegalTransitionError


def test_new_states_exist() -> None:
    assert state.TEMPLATE_MATCHED == "TEMPLATE_MATCHED"
    assert state.TEMPLATE_REVIEW == "TEMPLATE_REVIEW"
    assert state.READY_TO_RENDER == "READY_TO_RENDER"


def test_material_confirmed_to_template_matched() -> None:
    assert state.can_transition(state.MATERIAL_CONFIRMED, state.TEMPLATE_MATCHED)
    state.ensure_transition(state.MATERIAL_CONFIRMED, state.TEMPLATE_MATCHED)


def test_template_matched_to_template_review() -> None:
    assert state.can_transition(state.TEMPLATE_MATCHED, state.TEMPLATE_REVIEW)
    state.ensure_transition(state.TEMPLATE_MATCHED, state.TEMPLATE_REVIEW)


def test_template_review_to_ready_to_render() -> None:
    assert state.can_transition(state.TEMPLATE_REVIEW, state.READY_TO_RENDER)
    state.ensure_transition(state.TEMPLATE_REVIEW, state.READY_TO_RENDER)


def test_backward_transitions() -> None:
    """允许回退：TEMPLATE_MATCHED → MATERIAL_CONFIRMED，TEMPLATE_REVIEW → TEMPLATE_MATCHED。"""
    assert state.can_transition(state.TEMPLATE_MATCHED, state.MATERIAL_CONFIRMED)
    assert state.can_transition(state.TEMPLATE_REVIEW, state.TEMPLATE_MATCHED)
    assert state.can_transition(state.READY_TO_RENDER, state.TEMPLATE_REVIEW)


def test_illegal_transitions() -> None:
    illegal = [
        (state.MATERIAL_CONFIRMED, state.READY_TO_RENDER),  # 跳过中间态
        (state.TEMPLATE_MATCHED, state.READY_TO_RENDER),  # 跳过 TEMPLATE_REVIEW
        (state.PARSE_CONFIRMED, state.TEMPLATE_MATCHED),  # 未进入 MATERIAL_CONFIRMED
        (state.READY_TO_RENDER, state.MATERIAL_CONFIRMED),  # 不能直接回退到 MATERIAL_CONFIRMED
    ]
    for current, target in illegal:
        with pytest.raises(IllegalTransitionError):
            state.ensure_transition(current, target)


def test_full_chain() -> None:
    """完整链路：MATERIAL_CONFIRMED → TEMPLATE_MATCHED → TEMPLATE_REVIEW → READY_TO_RENDER。"""
    state.ensure_transition(state.MATERIAL_CONFIRMED, state.TEMPLATE_MATCHED)
    state.ensure_transition(state.TEMPLATE_MATCHED, state.TEMPLATE_REVIEW)
    state.ensure_transition(state.TEMPLATE_REVIEW, state.READY_TO_RENDER)
