"""素材库 FTS5 检索索引（BP-8）。

独立 SQLite 库（``<enterprise>/fts5.db``）中的 **standalone** FTS5 虚表::

    CREATE VIRTUAL TABLE material_fts USING fts5(
        material_id UNINDEXED, name, ocr_text, tokenize='trigram'
    )

设计说明:
- 使用 ``trigram`` 分词器以支持中文子串检索（unicode61 对 CJK 无法命中）；
  trigram 要求查询词 ≥3 字符，短词（1-2 字）回退 ``LIKE`` 扫描。
- ``material_id`` 为 UNINDEXED 列，仅作回连主库 material 表的外键。
- 每企业独立 db 文件，天然满足企业级隔离（TR-16.12）。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_TABLE = "material_fts"
_TRIGRAM_MIN_LEN = 3


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_fts5(db_path: Path) -> None:
    """创建 FTS5 虚表（幂等）。"""
    conn = _connect(db_path)
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_TABLE} USING fts5("
            f"material_id UNINDEXED, name, ocr_text, tokenize='trigram')"
        )
        conn.commit()
    finally:
        conn.close()


def fts5_add(db_path: Path, material_id: str, name: str, ocr_text: str) -> None:
    """新增/更新一条素材索引（先删后插，保证幂等）。"""
    init_fts5(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(f"DELETE FROM {_TABLE} WHERE material_id = ?", (material_id,))
        conn.execute(
            f"INSERT INTO {_TABLE} (material_id, name, ocr_text) VALUES (?, ?, ?)",
            (material_id, name or "", ocr_text or ""),
        )
        conn.commit()
    finally:
        conn.close()


def fts5_remove(db_path: Path, material_id: str) -> None:
    """移除一条素材索引。"""
    if not db_path.exists():
        return
    conn = _connect(db_path)
    try:
        conn.execute(f"DELETE FROM {_TABLE} WHERE material_id = ?", (material_id,))
        conn.commit()
    finally:
        conn.close()


def _build_match_query(keyword: str) -> str:
    """构造安全的 FTS5 MATCH 表达式（按短语处理，转义双引号）。"""
    phrase = keyword.strip().replace('"', '""')
    return f'"{phrase}"'


def fts5_search(db_path: Path, keyword: str, limit: int = 20) -> list[dict]:
    """FTS5 检索，BM25 排序返回。

    返回 ``[{material_id, name, ocr_text, rank}]``；rank 越小越相关（BM25 为负值）。
    keyword 为空时返回空列表；1-2 字符回退 LIKE 子串匹配。
    """
    kw = (keyword or "").strip()
    if not kw or not db_path.exists():
        return []

    init_fts5(db_path)
    conn = _connect(db_path)
    try:
        if len(kw) >= _TRIGRAM_MIN_LEN:
            rows = conn.execute(
                f"SELECT material_id, name, ocr_text, rank FROM {_TABLE}"
                f" WHERE {_TABLE} MATCH ? ORDER BY rank LIMIT ?",
                (_build_match_query(kw), limit),
            ).fetchall()
        else:
            like = f"%{kw}%"
            rows = conn.execute(
                f"SELECT material_id, name, ocr_text, 0.0 AS rank FROM {_TABLE}"
                f" WHERE name LIKE ? OR ocr_text LIKE ? LIMIT ?",
                (like, like, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def bulk_index(session: Session, db_path: Path) -> int:
    """对全部 active 素材重建 FTS5 索引，返回索引条数。"""
    init_fts5(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(f"DELETE FROM {_TABLE}")
        materials = session.execute(
            text("SELECT id, name, ocr_text FROM material WHERE deleted_at IS NULL")
        ).fetchall()
        for m in materials:
            conn.execute(
                f"INSERT INTO {_TABLE} (material_id, name, ocr_text) VALUES (?, ?, ?)",
                (str(m[0]), str(m[1] or ""), str(m[2] or "")),
            )
        conn.commit()
        return len(materials)
    finally:
        conn.close()
