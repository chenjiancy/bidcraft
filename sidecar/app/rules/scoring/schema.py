"""score_table.json Schema 硬校验（TR-11.6，BP-3）。

产出后立即用 JSON Schema 校验结构；通过则标记 schema_validated=True，
失败则 schema_validated=False 并附 errors（进修复循环，不静默）。
Task 13 只查 schema_validated 标志位，不重复校验。
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

SCORE_TABLE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "version",
        "scoring_version",
        "generated_at",
        "categories",
        "total_score_check",
        "red_flags",
    ],
    "properties": {
        "version": {"type": "integer"},
        "scoring_version": {"type": "string"},
        "generated_at": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "source_chapter", "items", "subtotal"],
                "properties": {
                    "name": {"type": "string"},
                    "source_chapter": {"type": "string"},
                    "source_stem": {"type": "string"},
                    "subtotal": {"type": "number"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "score", "materials", "thresholds"],
                            "properties": {
                                "name": {"type": "string"},
                                "score": {"type": "number"},
                                "materials": {"type": "array", "items": {"type": "string"}},
                                "thresholds": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["kind", "text", "value"],
                                        "properties": {
                                            "kind": {"enum": ["date", "amount", "quantity"]},
                                            "text": {"type": "string"},
                                            "value": {"type": "string"},
                                        },
                                    },
                                },
                                "unrecognized": {"type": "string"},
                                "anchor": {"type": "object"},
                                "source_chapter": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "total_score_check": {
            "type": "object",
            "required": ["expected", "actual", "ok"],
            "properties": {
                "expected": {"type": "number"},
                "actual": {"type": "number"},
                "ok": {"type": "boolean"},
            },
        },
        "red_flags": {"type": "array", "items": {"type": "object"}},
        "llm": {"type": "object"},
        "schema_validated": {"type": "boolean"},
    },
}


def validate_score_table(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """校验 score_table payload；返回 (ok, errors)。

    通过时在 payload 上写入 schema_validated=True，失败写 False 并返回错误列表。
    """
    validator = Draft202012Validator(SCORE_TABLE_SCHEMA)
    errors = sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in validator.iter_errors(payload)
    )
    ok = not errors
    payload["schema_validated"] = ok
    return ok, errors
