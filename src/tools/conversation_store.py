"""
SQLite Conversation Store.

Saves every conversation turn to a local SQLite database so we can
later extract useful knowledge and push it through the ingestion pipeline
(Airflow DAG → Pinecone + Neo4j update).

Single-user, no auth required.
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

# ─── Database path (data/ directory next to src/) ─────────────────────────────

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "conversations.db")


# ─── Schema Init ──────────────────────────────────────────────────────────────

def init_db() -> None:
    """Creates tables if they don't exist yet. Safe to call on every startup."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # conversations — one row per session
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                user_query      TEXT,
                final_answer    TEXT,
                route           TEXT,
                uploaded_file   TEXT,
                hitl_approved   INTEGER DEFAULT 0,
                hitl_notes      TEXT
            )
        """)

        # messages — one row per turn (user or assistant)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                turn_id         TEXT,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)
        columns = {
            row[1] for row in cursor.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "turn_id" not in columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN turn_id TEXT")
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS unique_message_turn_role
            ON messages(conversation_id, turn_id, role)
            WHERE turn_id IS NOT NULL
            """
        )

        # search_results — raw web search hits for later extraction
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                source          TEXT NOT NULL,
                title           TEXT,
                url             TEXT,
                snippet         TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
        """)

        conn.commit()
        logger.info(f"SQLite DB ready at: {DB_PATH}")
    finally:
        conn.close()


# ─── Write Helpers ─────────────────────────────────────────────────────────────

def upsert_conversation(
    conversation_id: str,
    user_query: str = "",
    final_answer: Optional[str] = None,
    route: str = "direct",
    uploaded_file: Optional[str] = None,
    hitl_approved: bool = False,
    hitl_notes: Optional[str] = None,
) -> None:
    """
    Insert or update a conversation record.
    Safe to call multiple times — updates timestamps on each call.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations
                (conversation_id, created_at, updated_at, user_query,
                 final_answer, route, uploaded_file, hitl_approved, hitl_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                updated_at   = excluded.updated_at,
                user_query   = excluded.user_query,
                final_answer = excluded.final_answer,
                route        = excluded.route,
                uploaded_file = excluded.uploaded_file,
                hitl_approved = excluded.hitl_approved,
                hitl_notes   = excluded.hitl_notes
        """, (
            conversation_id, now, now, user_query,
            final_answer, route, uploaded_file,
            int(hitl_approved), hitl_notes
        ))
        conn.commit()
    finally:
        conn.close()


def save_messages(conversation_id: str, messages: List[Dict[str, str]]) -> None:
    """
    Append new messages to the messages table.
    Skips duplicates by checking existing count — only inserts if list grew.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        # Get existing count so we only insert new ones
        cursor.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        existing_count = cursor.fetchone()[0]
        new_messages = messages[existing_count:]  # Only append what's new

        for msg in new_messages:
            cursor.execute("""
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, msg["role"], msg["content"], now))

        conn.commit()
        if new_messages:
            logger.info(f"Saved {len(new_messages)} new message(s) for conversation {conversation_id}")
    finally:
        conn.close()


def record_conversation_turn(
    conversation_id: str,
    turn_id: str,
    user_query: str,
    final_answer: str,
    route: str,
    uploaded_file: Optional[str] = None,
) -> None:
    """Atomically persist one chat turn, independently of long-term-memory approval."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO conversations
                (conversation_id, created_at, updated_at, user_query,
                 final_answer, route, uploaded_file, hitl_approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(conversation_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                user_query = excluded.user_query,
                final_answer = excluded.final_answer,
                route = excluded.route,
                uploaded_file = coalesce(excluded.uploaded_file, conversations.uploaded_file)
            """,
            (
                conversation_id,
                now,
                now,
                user_query,
                final_answer,
                route,
                uploaded_file,
            ),
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO messages
                (conversation_id, turn_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (conversation_id, turn_id, "user", user_query, now),
                (conversation_id, turn_id, "assistant", final_answer, now),
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def save_search_results(conversation_id: str, results: List[Dict[str, Any]]) -> None:
    """Saves all web search results for later knowledge extraction."""
    if not results:
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        for r in results:
            cursor.execute("""
                INSERT INTO search_results (conversation_id, source, title, url, snippet)
                VALUES (?, ?, ?, ?, ?)
            """, (
                conversation_id,
                r.get("source", "unknown"),
                r.get("title", ""),
                r.get("url", ""),
                r.get("snippet", ""),
            ))
        conn.commit()
        logger.info(f"Saved {len(results)} search result(s) for conversation {conversation_id}")
    finally:
        conn.close()


# ─── Read Helpers ──────────────────────────────────────────────────────────────

def get_conversation_history(conversation_id: str) -> List[Dict[str, str]]:
    """Retrieves all messages for a given conversation (ordered by insert)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,))
        rows = cursor.fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]
    finally:
        conn.close()


def get_recent_conversation_history(
    conversation_id: str,
    max_messages: int = 12,
    max_characters: int = 12000,
) -> List[Dict[str, str]]:
    """Return the newest complete messages, trimmed to a predictable prompt budget."""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, max(1, max_messages)),
        ).fetchall()
    finally:
        conn.close()

    selected: List[Dict[str, str]] = []
    used = 0
    for role, content in rows:
        remaining = max_characters - used
        if remaining <= 0:
            break
        trimmed = content[-remaining:]
        selected.append({"role": role, "content": trimmed})
        used += len(trimmed)
    selected.reverse()
    return selected


def list_conversations(limit: int = 20) -> List[Dict[str, Any]]:
    """Lists the most recent conversations (for UI display)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT conversation_id, created_at, user_query, final_answer, hitl_approved
            FROM conversations
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [
            {
                "conversation_id": r[0],
                "created_at": r[1],
                "user_query": r[2],
                "final_answer": r[3],
                "hitl_approved": bool(r[4]),
            }
            for r in rows
        ]
    finally:
        conn.close()


# ─── Init on import ───────────────────────────────────────────────────────────
init_db()
