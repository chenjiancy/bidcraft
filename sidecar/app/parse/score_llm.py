"""评分表 LLM 专项校验（TR-11.7）：完整性/合计/门槛遗漏。

纯逻辑模块（不碰路径/DB 长连接），同步阻塞；asyncio.to_thread 由调用方负责。
与 Task 10 通用校验互补：这里专注评分办法的结构化校验。

安全：API Key 仅调用时临时传入，不落库/日志。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.parse.llm_validate import _build_messages, _parse_json
from app.services.llm import ChatResult, chat_completion

_SYSTEM_SCORE = """你是一名招投标合规审查专家。

下面是规则库抽取的评分表（JSON）与评分办法原文片段。请对评分表做三项校验：
1. completeness：评分项是否覆盖原文所有评分项（列出原文有但抽取缺失的项）；
2. sum_check：各评分项分值合计是否与原文"总分/满分"一致；
3. threshold_coverage：是否遗漏原文中的门槛条件（日期/金额/数量等）。

输出严格 JSON（不含 markdown 代码块）：
{
  "completeness": {"missing_items": ["..."], "ok": true|false},
  "sum_check": {"expected_total": 100, "ok": true|false, "note": "..."},
  "threshold_coverage": {"missing": ["..."], "ok": true|false},
  "overall_risk": "low" | "medium" | "high"
}
只输出 JSON，不要任何解释。"""


def validate_score(
    score_table: dict[str, Any],
    score_snippet: str,
    base_url: str,
    model: str,
    api_key: str,
    factory: sessionmaker[Session],
    project_id: str,
) -> dict[str, Any]:
    """评分表 LLM 专项校验，同步阻塞。

    返回 {"status": "ok"|"error", "data": {...} | null, "error": ...}
    """
    import json

    user = (
        "【规则库抽取的评分表】\n"
        f"{json.dumps(score_table.get('categories', []), ensure_ascii=False)[:4000]}\n\n"
        f"【评分办法原文片段】\n{score_snippet[:4000]}"
    )
    messages = _build_messages(_SYSTEM_SCORE, user)

    result: ChatResult
    with factory() as session:
        result = chat_completion(base_url, model, api_key, messages, session, project_id)

    if not result.success or not result.content:
        return {"status": "error", "data": None, "error": result.error or "LLM 返回空"}

    data = _parse_json(result.content)
    return {"status": "ok", "data": data, "error": None}
