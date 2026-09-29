"""素材库 FTS5 检索索引（BP-8）。

SQLite 虚表 + BM25 排序，随归档/编辑增量更新，供 Task 16 素材查询使用。
表结构::

    CREATE VIRTUAL TABLE material_fts USING fts5(
        name, ocr_text,
        content='material',
        content_rowid='rowid'
    )

索引列：material.name, material.ocr_text（BM25 排序）
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


def _fts_table_name() -> str:
    return "material_fts"


def init_fts5(session: Session, db_path: Path | None = None) -> None:
    """初始化 FTS5 虚表（幂等）。"""
    # 通过 SQLite 原生连接执行（FTS5 不支持 SQL alchemy 直接创建虚表）
    conn = _get_fts_connection(db_path)
    try:
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_fts_table_name()} USING fts5("
            f"name, ocr_text, content='material', content_rowid='rowid')"
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def _fts_connection(db_path: Path | None):
    if db_path is None:
        yield None
        return
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _get_fts_connection(db_path: Path | None):
    if db_path is None:
        raise RuntimeError("FTS5 需要指定 sqlite 数据库路径")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def fts5_add(conn, material_id: str, name: str, ocr_text: str) -> None:
    """向 FTS5 插入或更新一条素材索引。"""
    conn.execute(
        f"INSERT OR REPLACE INTO {_fts_table_name()} (rowid, name, ocr_text) VALUES (?, ?, ?)",
        (material_id, name or "", ocr_text or ""),
    )
    conn.commit()


def fts5_remove(conn, material_id: str) -> None:
    """从 FTS5 移除一条素材索引。"""
    conn.execute(f"DELETE FROM {_fts_table_name()} WHERE rowid = ?", (material_id,))
    conn.commit()


def fts5_search(conn, keyword: str, limit: int = 20) -> list[dict]:
    """FTS5 检索，返回 BM25 排序结果。"""
    rows = conn.execute(
        f"SELECT rowid, name, ocr_text, rank FROM {_fts_table_name()}"
        f" WHERE {_fts_table_name()} MATCH ? ORDER BY rank LIMIT ?",
        (keyword, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def bulk_index(session: Session, db_path: Path | None = None) -> int:
    """对全部 active 素材建立 FTS5 索引（全量重建）。"""

    init_fts5(session, db_path)
    conn = _get_fts_connection(db_path)
    try:
        conn.execute(f"DELETE FROM {_fts_table_name()}")
        conn.commit()
        materials = session.execute(
            text("SELECT id, name, ocr_text FROM material WHERE deleted_at IS NULL")
        ).fetchall()
        count = 0
        for m in materials:
            fts5_add(conn, str(m[0]), str(m[1] or ""), str(m[2] or ""))
            count += 1
        return count
    finally:
        conn.close()
