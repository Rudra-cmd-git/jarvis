"""SQLite persistence for conversations, memory, action log and productivity data.

One connection guarded by a lock is plenty for a desktop app and keeps the code
simple and testable. All timestamps are stored as local ISO-8601 strings.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from jarvis.core.util import now_iso, redact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'fact',
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'user',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool TEXT NOT NULL,
    risk TEXT NOT NULL,
    ok INTEGER NOT NULL,
    summary TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_created ON actions(id DESC);
CREATE TABLE IF NOT EXISTS todos (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    due TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    due_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    steps_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timers (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL DEFAULT '',
    duration_s INTEGER NOT NULL,
    ends_at TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'running',
    created_at TEXT NOT NULL
);
"""


def _uid() -> str:
    return uuid.uuid4().hex


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------ conversations
    def create_conversation(self, title: str = "") -> str:
        cid = _uid()
        stamp = now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?,?,?,?)",
                (cid, title or "New conversation", stamp, stamp),
            )
            self._conn.commit()
        return cid

    def list_conversations(self, limit: int = 100, include_archived: bool = False) -> list[dict]:
        query = "SELECT * FROM conversations"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY updated_at DESC LIMIT ?"
        with self._lock:
            rows = self._conn.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return _row_to_dict(row)

    def rename_conversation(self, conversation_id: str, title: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, now_iso(), conversation_id),
            )
            self._conn.commit()

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._conn.commit()

    def add_message(
        self, conversation_id: str, role: str, content: str, meta: dict | None = None
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO messages(conversation_id, role, content, meta, created_at) "
                "VALUES (?,?,?,?,?)",
                (conversation_id, role, content, json.dumps(meta or {}), now_iso()),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now_iso(), conversation_id)
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def list_messages(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        query = "SELECT id, conversation_id, role, content, meta, created_at FROM messages WHERE conversation_id = ? ORDER BY id"
        params: list[Any] = [conversation_id]
        if limit:
            query = (
                "SELECT * FROM (SELECT id, conversation_id, role, content, meta, created_at "
                "FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id"
            )
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def search_messages(self, query: str, limit: int = 50) -> list[dict]:
        pattern = f"%{query.strip()}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT m.*, c.title AS conversation_title FROM messages m "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.content LIKE ? ORDER BY m.id DESC LIMIT ?",
                (pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ memory
    def add_memory(self, content: str, kind: str = "fact", source: str = "user") -> dict:
        from jarvis.core.util import contains_secret

        content = content.strip()
        if not content:
            raise ValueError("Memory content cannot be empty")
        if contains_secret(content):
            raise ValueError(
                "Refusing to store text that looks like a password, OTP, token or API key."
            )
        entry = {
            "id": _uid(),
            "kind": kind,
            "content": content,
            "source": source,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO memories(id, kind, content, source, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    entry["id"],
                    entry["kind"],
                    entry["content"],
                    entry["source"],
                    entry["created_at"],
                    entry["updated_at"],
                ),
            )
            self._conn.commit()
        return entry

    def list_memories(self, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_memory(self, memory_id: str, content: str) -> None:
        if not content.strip():
            raise ValueError("Memory content cannot be empty")
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET content = ?, updated_at = ? WHERE id = ?",
                (content.strip(), now_iso(), memory_id),
            )
            self._conn.commit()

    def delete_memory(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._conn.commit()

    def clear_memories(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memories")
            self._conn.commit()

    # -------------------------------------------------------------- action log
    def log_action(
        self,
        tool: str,
        risk: str,
        ok: bool,
        summary: str,
        detail: str = "",
        duration_ms: int = 0,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO actions(tool, risk, ok, summary, detail, duration_ms, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (tool, risk, int(ok), redact(summary), redact(detail), duration_ms, now_iso()),
            )
            self._conn.commit()

    def recent_actions(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_actions(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM actions")
            self._conn.commit()

    # ------------------------------------------------------------------- todos
    def add_todo(self, text: str, due: str | None = None) -> dict:
        entry = {
            "id": _uid(),
            "text": text.strip(),
            "due": due,
            "created_at": now_iso(),
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO todos(id, text, due, created_at) VALUES (?,?,?,?)",
                (entry["id"], entry["text"], due, entry["created_at"]),
            )
            self._conn.commit()
        return entry

    def list_todos(self, include_done: bool = True) -> list[dict]:
        query = "SELECT * FROM todos"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY done ASC, COALESCE(due, created_at) ASC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    def complete_todo(self, todo_id: str, done: bool = True) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE todos SET done = ?, completed_at = ? WHERE id = ?",
                (int(done), now_iso() if done else None, todo_id),
            )
            self._conn.commit()

    def delete_todo(self, todo_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
            self._conn.commit()

    # --------------------------------------------------------------- reminders
    def add_reminder(self, text: str, due_at: str) -> dict:
        entry = {"id": _uid(), "text": text.strip(), "due_at": due_at, "created_at": now_iso()}
        with self._lock:
            self._conn.execute(
                "INSERT INTO reminders(id, text, due_at, created_at) VALUES (?,?,?,?)",
                (entry["id"], entry["text"], due_at, entry["created_at"]),
            )
            self._conn.commit()
        return entry

    def list_reminders(self, include_done: bool = False) -> list[dict]:
        query = "SELECT * FROM reminders"
        if not include_done:
            query += " WHERE done = 0"
        query += " ORDER BY due_at ASC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    def complete_reminder(self, reminder_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE reminders SET done = 1, completed_at = ? WHERE id = ?",
                (now_iso(), reminder_id),
            )
            self._conn.commit()

    def delete_reminder(self, reminder_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            self._conn.commit()

    def due_reminders(self, now: datetime | None = None) -> list[dict]:
        stamp = (now or datetime.now()).replace(microsecond=0).isoformat(timespec="seconds")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE done = 0 AND due_at <= ? ORDER BY due_at", (stamp,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------- notes
    def add_note(self, title: str, body: str) -> dict:
        entry = {"id": _uid(), "title": title.strip(), "body": body, "created_at": now_iso()}
        with self._lock:
            self._conn.execute(
                "INSERT INTO notes(id, title, body, created_at, updated_at) VALUES (?,?,?,?,?)",
                (entry["id"], entry["title"], body, entry["created_at"], entry["created_at"]),
            )
            self._conn.commit()
        return entry

    def list_notes(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notes ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_note(self, note_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return _row_to_dict(row)

    def search_notes(self, query: str, limit: int = 50) -> list[dict]:
        pattern = f"%{query.strip()}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? OR body LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (pattern, pattern, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_note(self, note_id: str, title: str, body: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                (title, body, now_iso(), note_id),
            )
            self._conn.commit()

    def delete_note(self, note_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            self._conn.commit()

    # --------------------------------------------------------------- workflows
    def save_workflow(self, name: str, description: str, steps: Iterable[dict]) -> dict:
        steps_json = json.dumps(list(steps), ensure_ascii=False)
        stamp = now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO workflows(id, name, description, steps_json, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
                "steps_json=excluded.steps_json, updated_at=excluded.updated_at",
                (_uid(), name, description, steps_json, stamp, stamp),
            )
            self._conn.commit()
        return self.get_workflow(name) or {}

    def list_workflows(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workflows ORDER BY name").fetchall()
        return [dict(row) for row in rows]

    def get_workflow(self, name: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM workflows WHERE name = ?", (name,)).fetchone()
        data = _row_to_dict(row)
        if data:
            try:
                data["steps"] = json.loads(data.get("steps_json") or "[]")
            except json.JSONDecodeError:
                data["steps"] = []
        return data

    def delete_workflow(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM workflows WHERE name = ?", (name,))
            self._conn.commit()

    # ------------------------------------------------------------------ timers
    def start_timer(self, label: str, duration_s: int) -> dict:
        ends = datetime.now() + timedelta(seconds=duration_s)
        entry = {
            "id": _uid(),
            "label": label or "Timer",
            "duration_s": int(duration_s),
            "ends_at": ends.isoformat(timespec="seconds"),
            "created_at": now_iso(),
        }
        with self._lock:
            self._conn.execute("UPDATE timers SET state = 'cancelled' WHERE state = 'running'")
            self._conn.execute(
                "INSERT INTO timers(id, label, duration_s, ends_at, state, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    entry["id"],
                    entry["label"],
                    entry["duration_s"],
                    entry["ends_at"],
                    "running",
                    entry["created_at"],
                ),
            )
            self._conn.commit()
        return entry

    def active_timer(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM timers WHERE state = 'running' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return _row_to_dict(row)

    def stop_timer(self, timer_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE timers SET state = 'stopped' WHERE id = ?", (timer_id,))
            self._conn.commit()

    def complete_timer(self, timer_id: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE timers SET state = 'done' WHERE id = ?", (timer_id,))
            self._conn.commit()