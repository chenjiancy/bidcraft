"""解析配置纯逻辑单测（Task 9：目录/默认/校验/diff/影响映射）。"""

import pytest

from app.parse import config as cfg
from app.parse.config import ConfigError


def test_catalog_has_exactly_8_required_and_10_optional() -> None:
    # TR-9.1：8 关键项 + 其他项，与 spec FR-2 第 2 点一致
    entries = cfg.catalog()
    required = [e for e in entries if e["required"]]
    optional = [e for e in entries if not e["required"]]
    assert len(required) == 8
    assert len(optional) == 10
    assert [e["label"] for e in required] == [
        "项目概述",
        "技术评分要求",
        "项目信息",
        "甲方信息",
        "响应文件要求",
        "代理机构信息",
        "商务评分要求",
        "无效标与废标项",
    ]
    assert [e["label"] for e in optional] == [
        "交货和服务要求",
        "采购清单",
        "投标关键节点",
        "投标保证金",
        "资格性审查",
        "符合性检查",
        "开标要求",
        "评标要求",
        "合同授予与签订",
        "合同解除和终止",
    ]
    assert len({e["key"] for e in entries}) == 18  # key 唯一


def test_default_config_required_selected_optional_off_llm_off() -> None:
    # TR-9.3：默认配置——关键项必选、其他不选、LLM 总开关默认关
    d = cfg.default_config()
    assert all(d.items[k] is True for k in cfg.REQUIRED_KEYS)
    assert all(d.items[k] is False for k in cfg.OPTIONAL_KEYS)
    assert d.llm_enabled is False
    assert d.llm_mode == cfg.LLM_VALIDATE


def test_build_config_optional_toggle_ok() -> None:
    selected = sorted(cfg.REQUIRED_KEYS) + ["bid_bond"]
    c = cfg.build_config(selected, llm_enabled=False, llm_mode=None)
    assert c.items["bid_bond"] is True
    assert c.items["bid_opening"] is False
    assert c.llm_enabled is False
    assert c.llm_mode == cfg.LLM_VALIDATE


def test_build_config_required_cannot_be_deselected() -> None:
    # TR-9.1：关键项不可取消
    selected = sorted(cfg.REQUIRED_KEYS - {"invalid_bid"})
    with pytest.raises(ConfigError, match="必选"):
        cfg.build_config(selected, llm_enabled=False, llm_mode=None)


def test_build_config_unknown_key_rejected() -> None:
    with pytest.raises(ConfigError, match="未知配置项"):
        cfg.build_config(
            [*sorted(cfg.REQUIRED_KEYS), "nonexistent"], llm_enabled=False, llm_mode=None
        )


def test_llm_mode_rules() -> None:
    # TR-9.2：总开关关闭时模式被忽略（统一 validate）；开启时必须二选一
    off = cfg.build_config(sorted(cfg.REQUIRED_KEYS), llm_enabled=False, llm_mode="dual_channel")
    assert off.llm_enabled is False
    assert off.llm_mode == cfg.LLM_VALIDATE

    validate = cfg.build_config(
        sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode=cfg.LLM_VALIDATE
    )
    assert validate.llm_enabled is True and validate.llm_mode == cfg.LLM_VALIDATE

    dual = cfg.build_config(
        sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode=cfg.LLM_DUAL_CHANNEL
    )
    assert dual.llm_mode == cfg.LLM_DUAL_CHANNEL

    with pytest.raises(ConfigError, match="模式"):
        cfg.build_config(sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode=None)
    with pytest.raises(ConfigError, match="模式"):
        cfg.build_config(sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode="bogus")


def test_diff_reports_only_actual_changes() -> None:
    old = cfg.default_config()
    new = cfg.build_config(
        [*sorted(cfg.REQUIRED_KEYS), "bid_bond"], llm_enabled=False, llm_mode=None
    )
    changes = cfg.diff_configs(old, new)
    assert changes == {"selected_added": ["bid_bond"]}

    assert cfg.diff_configs(old, cfg.default_config()) == {}


def test_diff_llm_enable_and_mode_switch() -> None:
    old = cfg.default_config()
    enabled = cfg.build_config(
        sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode=cfg.LLM_VALIDATE
    )
    diff1 = cfg.diff_configs(old, enabled)
    assert diff1["llm_enabled"] == {"from": False, "to": True}
    assert "llm_mode" not in diff1  # 模式从默认 validate 启用 validate，不算模式变更

    dual = cfg.build_config(
        sorted(cfg.REQUIRED_KEYS), llm_enabled=True, llm_mode=cfg.LLM_DUAL_CHANNEL
    )
    diff2 = cfg.diff_configs(enabled, dual)
    assert diff2 == {"llm_mode": {"from": "validate", "to": "dual_channel"}}


def test_payload_roundtrip_and_default_for_none() -> None:
    assert cfg.from_payload(None) == cfg.default_config()
    c = cfg.build_config(
        [*sorted(cfg.REQUIRED_KEYS), "bid_bond"], llm_enabled=True, llm_mode="dual_channel"
    )
    restored = cfg.from_payload(c.model_dump())
    assert restored == c


def test_payload_forward_compatible_fills_new_keys() -> None:
    payload = cfg.default_payload()
    payload["items"].pop("bid_bond", None)
    payload["items"]["future_item"] = True  # 未知项剔除
    c = cfg.from_payload(payload)
    assert c.items["bid_bond"] is False  # 新可选项默认不选
    assert "future_item" not in c.items


def test_affected_checkpoint_items_never_touches_physical_layer() -> None:
    # TR-9.4（Task 9 阶段）：配置变化不得触发 mineru/chapters 等物理层重跑
    changes = {"selected_added": ["bid_bond"], "llm_enabled": {"from": False, "to": True}}
    affected = cfg.affected_checkpoint_items(changes)
    assert affected == ()
    assert cfg.affected_checkpoint_items({}) == ()
