"""解析配置（Task 9，FR-2 第 2 点）：配置项目录、默认值、校验与变更影响判定。

纯逻辑模块（不碰 DB/文件），可完全单元测试：

- 8 个关键项必选、不可取消；10 个其他项可选；
- LLM 辅助总开关默认关；开启时模式二选一（校验 / 双通道）；
- 配置为项目级，不设置时使用默认配置（DB 层负责持久化）；
- ``affected_checkpoint_items`` 建立"配置差异 → 受影响 checkpoint 项"映射，
  供配置变更后的单项重试（TR-9.4）。

Task 10 起：物理解析项（dedupe/preprocess/mineru/chapters）不消费本配置，
勾选要素或 LLM 开关变化不重跑 OCR；要素提取项 extract:coarse（恒有）与
extract:llm（校验模式）消费本配置，配置差异映射到这两项做单项重试。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, cast

from pydantic import BaseModel

CONFIG_VERSION = 1

# (稳定 key, 中文 label)；label 与 spec.md FR-2 第 2 点原文一致
KEY_ITEMS: tuple[tuple[str, str], ...] = (
    ("project_overview", "项目概述"),
    ("tech_score", "技术评分要求"),
    ("project_info", "项目信息"),
    ("buyer_info", "甲方信息"),
    ("response_requirements", "响应文件要求"),
    ("agency_info", "代理机构信息"),
    ("business_score", "商务评分要求"),
    ("invalid_bid", "无效标与废标项"),
)

OPTIONAL_ITEMS: tuple[tuple[str, str], ...] = (
    ("delivery_service", "交货和服务要求"),
    ("procurement_list", "采购清单"),
    ("bid_milestones", "投标关键节点"),
    ("bid_bond", "投标保证金"),
    ("qualification_review", "资格性审查"),
    ("compliance_review", "符合性检查"),
    ("bid_opening", "开标要求"),
    ("bid_evaluation", "评标要求"),
    ("contract_award", "合同授予与签订"),
    ("contract_termination", "合同解除和终止"),
)

REQUIRED_KEYS: frozenset[str] = frozenset(k for k, _ in KEY_ITEMS)
OPTIONAL_KEYS: frozenset[str] = frozenset(k for k, _ in OPTIONAL_ITEMS)
ALL_KEYS: frozenset[str] = REQUIRED_KEYS | OPTIONAL_KEYS

LlmMode = Literal["validate", "dual_channel"]

LLM_VALIDATE: LlmMode = "validate"
LLM_DUAL_CHANNEL: LlmMode = "dual_channel"
LLM_MODES: tuple[LlmMode, ...] = (LLM_VALIDATE, LLM_DUAL_CHANNEL)
DEFAULT_LLM_MODE: LlmMode = LLM_VALIDATE


class ConfigError(ValueError):
    """配置非法（消息可直接展示给用户）。"""


class ParseConfig(BaseModel):
    """项目级解析配置（持久化为 JSON payload）。"""

    version: int = CONFIG_VERSION
    # key → 是否勾选
    items: dict[str, bool]
    llm_enabled: bool = False
    llm_mode: LlmMode = LLM_VALIDATE


def catalog() -> list[dict[str, Any]]:
    """配置项目录（供 UI 渲染，前端不硬编码中文 label）。"""
    return [{"key": key, "label": label, "required": True} for key, label in KEY_ITEMS] + [
        {"key": key, "label": label, "required": False} for key, label in OPTIONAL_ITEMS
    ]


def default_config() -> ParseConfig:
    """默认配置：8 关键项勾选、其他项不选、LLM 总开关关。"""
    return ParseConfig(
        items={key: key in REQUIRED_KEYS for key in ALL_KEYS},
        llm_enabled=False,
        llm_mode=LLM_VALIDATE,
    )


def default_payload() -> dict[str, Any]:
    return default_config().model_dump()


def from_payload(payload: dict[str, Any] | None) -> ParseConfig:
    """从 DB JSON 还原；缺失/损坏一律回退默认（不静默吞错由调用方决定是否记录）。"""
    if not payload:
        return default_config()
    try:
        cfg = ParseConfig.model_validate(payload)
    except Exception as exc:
        raise ConfigError(f"解析配置已损坏：{exc}") from None
    # 补全新增配置项（前向兼容），剔除未知项
    merged = {key: key in REQUIRED_KEYS for key in ALL_KEYS}
    merged.update({k: bool(v) for k, v in cfg.items.items() if k in ALL_KEYS})
    cfg.items = merged
    return cfg


def build_config(
    selected: Iterable[str],
    *,
    llm_enabled: bool,
    llm_mode: str | None,
) -> ParseConfig:
    """由前端提交构建合法配置；非法输入抛 ConfigError。

    - 关键项必须全部勾选；未知项拒绝；
    - LLM 关闭时模式忽略（统一存默认 validate）；
    - LLM 开启时模式必须是 validate/dual_channel 二选一。
    """
    chosen = set(selected)
    unknown = chosen - ALL_KEYS
    if unknown:
        raise ConfigError(f"未知配置项：{', '.join(sorted(unknown))}")
    missing = REQUIRED_KEYS - chosen
    if missing:
        labels = [dict(KEY_ITEMS)[k] for k, _ in KEY_ITEMS if k in missing]
        raise ConfigError(f"关键项为必选项，不可取消：{', '.join(labels)}")

    mode: LlmMode = DEFAULT_LLM_MODE
    if llm_enabled:
        if llm_mode not in LLM_MODES:
            raise ConfigError("启用 LLM 辅助时必须选择模式：校验模式或双通道模式")
        mode = cast(LlmMode, llm_mode)
    return ParseConfig(
        items={key: key in chosen for key in ALL_KEYS},
        llm_enabled=llm_enabled,
        llm_mode=mode,
    )


def diff_configs(old: ParseConfig, new: ParseConfig) -> dict[str, Any]:
    """计算两份配置的差异（仅含发生变化的字段，供日志与影响判定）。"""
    changes: dict[str, Any] = {}
    added = sorted(k for k, v in new.items.items() if v and not old.items.get(k, False))
    removed = sorted(k for k, v in old.items.items() if v and not new.items.get(k, False))
    if added:
        changes["selected_added"] = added
    if removed:
        changes["selected_removed"] = removed
    if old.llm_enabled != new.llm_enabled:
        changes["llm_enabled"] = {"from": old.llm_enabled, "to": new.llm_enabled}
    if old.llm_mode != new.llm_mode and new.llm_enabled:
        changes["llm_mode"] = {"from": old.llm_mode, "to": new.llm_mode}
    return changes


def affected_checkpoint_items(changes: dict[str, Any]) -> tuple[str, ...]:
    """配置差异 → 需重置的 checkpoint item key（TR-9.4，复用单项重试）。

    Task 10 起：要素提取项（extract:coarse 恒有；extract:llm 仅校验模式）
    消费本配置——勾选项或 LLM 开关/模式变化都需要重置它们以单项重试。
    物理层项（dedupe/preprocess:/mineru:/chapters:）不消费本配置，
    本函数永远不得返回物理层 item key。
    """
    if not changes:
        return ()
    # 任何配置差异都影响要素层：勾选差异改变提取集合，LLM 差异改变校验行为
    return ("extract:coarse", "extract:llm")
