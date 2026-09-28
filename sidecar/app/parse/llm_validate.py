"""LLM 校验模式（TR-10.6/10.7/10.8）：先预热再并发，quote 回原文校验。

纯逻辑模块（不碰路径/DB 连接长持有），全部函数为同步阻塞型；
asyncio.to_thread 由调用方（service.py）负责包入协程。

- validate_item: 单项 LLM 校验，输出 JSON {is_hard_constraint, constraint, quote, risk}；
- audit_gap: 全文摘要审计，比对规则粗分的大类覆盖；
- LLM 预热：先单跑 project_overview，成功后再并发其余项。

安全：API Key 仅调用时临时传入，不落库/日志。
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.rules.anchor import verify_anchor
from app.services.llm import ChatResult, chat_completion

_SYSTEM_VALIDATE = """你是一名招投标合规审查专家。

对用户提供的一条招标文件要素进行审查，输出严格 JSON（不含 markdown 代码块）：
{
  "is_hard_constraint": true | false,
  "constraint": "约束条件的文字描述",
  "quote": "原文中支撑该约束的确切片段（不得改写）",
  "risk": "low" | "medium" | "high"
}

规则：
1. is_hard_constraint 为 true 当且仅当该要素包含实质性要求或否决投标项；
2. quote 必须能在招标文件原文中找到，不得编造、不得改写；
3. 若 quote 找不到原文依据，risk 必须为 high，并返回空字符串 quote。
4. 只输出 JSON，不要任何解释。"""

_SYSTEM_AUDIT = """你是一名招投标合规审查专家。

通读以下招标文件全文，列出该文件涉及的要求大类及其估计数量
（如：资格条款 N 项、废标条款 M 项、技术要求 K 项等）。

输出严格 JSON：
{
  "categories_count": {"大类名": 数量, ...},
  "gaps": ["可能遗漏的大类说明..."]
}
只输出 JSON，不要任何解释。"""


def _build_messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_json(content: str) -> dict[str, Any]:
    """从严包 JSON 代码块中提取 JSON 对象；失败返回空 dict。"""
    if "```json" in content:
        m = re.search(r"```json\s*(.*?)```", content, re.S)
        if m:
            content = m.group(1)
    elif "```" in content:
        m = re.search(r"```\s*(.*?)```", content, re.S)
        if m:
            content = m.group(1)
    try:
        return json.loads(content)
    except Exception:
        return {}


def validate_item(
    item_key: str,
    item_label: str,
    full_markdown: str,
    snippet: str,
    base_url: str,
    model: str,
    api_key: str,
    factory: sessionmaker[Session],
    project_id: str,
) -> dict[str, Any]:
    """单项 LLM 校验，同步阻塞。

    返回结构（供 extract_list.json 的 items[i].llm 字段）:
        {
          "status": "ok" | "error",
          "data": {...} | null,
          "error": null | str,
          "anchor_verified": bool
        }
    """
    user = (
        f"招标要素：{item_label}\n\n"
        f"【要素原文片段】\n{snippet[:2400]}\n\n"
        f"【全文上下文（用于比对 quote）】\n{full_markdown[:6000]}"
    )
    messages = _build_messages(_SYSTEM_VALIDATE, user)

    result: ChatResult
    with factory() as session:
        result = chat_completion(base_url, model, api_key, messages, session, project_id)

    if not result.success or not result.content:
        return {
            "status": "error",
            "data": None,
            "error": result.error or "LLM 返回空",
            "anchor_verified": False,
        }

    data = _parse_json(result.content)
    quote = str(data.get("quote", "")).strip()
    anchor_verified = bool(quote and verify_anchor(quote, full_markdown))
    if not anchor_verified and data.get("risk") != "high":
        # 自动修正：quote 找不到时风险升为 high
        data["risk"] = "high"
        data["quote"] = ""
    else:
        data["quote"] = quote if anchor_verified else ""

    return {
        "status": "ok",
        "data": data,
        "error": None,
        "anchor_verified": anchor_verified,
    }


def audit_gap(
    full_markdown: str,
    rule_items: list[dict[str, Any]],
    base_url: str,
    model: str,
    api_key: str,
    factory: sessionmaker[Session],
    project_id: str,
) -> dict[str, Any]:
    """全文摘要审计（TR-10.7），同步阻塞。

    rule_items 为 extract_list.json 中 items 的列表（含 category/selected）。
    返回 {"status": "ok"|"error", "data": {"categories_count":..., "gaps":...} | null, "error":...}
    """
    # 规则粗分已覆盖的大类（仅已勾选）
    selected = [i for i in rule_items if i.get("selected")]
    found = {i["category"] for i in selected if i.get("status") == "found"}
    brief = f"规则粗分已识别的大类：{', '.join(sorted(found))}（共 {len(selected)} 项）。"

    user = f"{brief}\n\n【招标文件全文】\n{full_markdown[:8000]}"
    messages = _build_messages(_SYSTEM_AUDIT, user)

    result: ChatResult
    with factory() as session:
        result = chat_completion(base_url, model, api_key, messages, session, project_id)

    if not result.success or not result.content:
        return {"status": "error", "data": None, "error": result.error or "审计 LLM 返回空"}

    data = _parse_json(result.content)
    return {"status": "ok", "data": data, "error": None}


def validate_batch(
    item_key: str,
    item_label: str,
    full_markdown: str,
    snippet: str,
    base_url: str,
    model: str,
    api_key: str,
    factory: sessionmaker[Session],
    project_id: str,
) -> dict[str, Any]:
    """validate_item 的别名，与 audit_gap 区分以便调用方统一用 asyncio.to_thread。"""
    return validate_item(
        item_key, item_label, full_markdown, snippet, base_url, model, api_key, factory, project_id
    )
