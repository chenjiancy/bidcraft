"""评分表专用规则子集（Task 11，TR-11.1~11.7）。

与 rules/ 上层同机制：纯逻辑、版本化、可单元测试，不碰路径/DB/LLM。
职责：评分办法原文 → 统一层级结构（评分大类→评分项→分值→所需证明材料
→门槛条件）→ 多来源合并 → 合计校验 → score_table.json payload。
"""

from app.rules.scoring import extract, schema, thresholds

__all__ = ["extract", "schema", "thresholds"]
