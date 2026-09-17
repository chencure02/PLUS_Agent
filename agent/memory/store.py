from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


_PATH_SUFFIXES = (
    ".tif",
    ".tiff",
    ".img",
    ".dat",
    ".shp",
    ".csv",
    ".txt",
    ".json",
)


class MemoryStore:
    def __init__(self, db_path: str):
        dir_path = os.path.dirname(db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        schema = Path(__file__).parent / "schema.sql"
        with self._get_conn() as conn:
            conn.executescript(schema.read_text(encoding="utf-8"))
            self._migrate_db(conn)

    def _migrate_db(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "simulation_runs", "user_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "simulation_runs", "thread_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "run_steps", "user_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "run_steps", "thread_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "conversation_summaries", "user_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "conversation_summaries", "thread_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(conn, "conversation_summaries", "updated_at", "TIMESTAMP")
        conn.execute(
            "UPDATE conversation_summaries "
            "SET updated_at=COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "DELETE FROM conversation_summaries "
            "WHERE id NOT IN ("
            "SELECT MAX(id) FROM conversation_summaries GROUP BY user_id, session_id"
            ")"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_user_session_unique "
            "ON conversation_summaries(user_id, session_id)"
        )

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _scoped_key(key: str, user_id: str = "", thread_id: str | None = None) -> str:
        thread_part = thread_id if thread_id else "global"
        return f"user:{user_id or ''}:thread:{thread_part}:{key}"

    @staticmethod
    def _scoped_prefix(user_id: str = "", thread_id: str | None = None) -> str:
        if thread_id:
            return f"user:{user_id or ''}:thread:{thread_id}:"
        return f"user:{user_id or ''}:thread:%:"

    def save_run(
        self,
        name: str,
        workflow: list,
        params: dict,
        outputs: list[str],
        user_id: str = "",
        thread_id: str = "",
    ) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO simulation_runs "
                "(user_id, thread_id, name, workflow_json, params_json, output_paths_json, status) "
                "VALUES (?,?,?,?,?,?,'running')",
                (user_id or "", thread_id or "", name, self._json(workflow), self._json(params), self._json(outputs)),
            )
            return cur.lastrowid

    def update_run_status(self, run_id: int, status: str, error_message: str = None, duration: float = None):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE simulation_runs SET status=?, error_message=?, duration_seconds=? WHERE id=?",
                (status, error_message, duration, run_id),
            )

    def save_step(
        self,
        run_id: int,
        tool_name: str,
        order: int,
        params: dict,
        tmp: str = None,
        outputs: list[str] = None,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> int:
        with self._get_conn() as conn:
            if user_id is None or thread_id is None:
                scope = conn.execute(
                    "SELECT user_id, thread_id FROM simulation_runs WHERE id=?",
                    (run_id,),
                ).fetchone()
                if scope:
                    user_id = scope[0] if user_id is None else user_id
                    thread_id = scope[1] if thread_id is None else thread_id
            cur = conn.execute(
                "INSERT INTO run_steps "
                "(run_id, user_id, thread_id, tool_name, step_order, params_json, tmp_content, output_paths_json, status) "
                "VALUES (?,?,?,?,?,?,?,?,'pending')",
                (
                    run_id,
                    user_id or "",
                    thread_id or "",
                    tool_name,
                    order,
                    self._json(params),
                    tmp,
                    self._json(outputs or []),
                ),
            )
            return cur.lastrowid

    def update_step_status(self, run_id: int, order: int, status: str, error_message: str = None):
        with self._get_conn() as conn:
            now = datetime.now().isoformat()
            if status == "running":
                conn.execute(
                    "UPDATE run_steps SET status=?, started_at=? WHERE run_id=? AND step_order=?",
                    (status, now, run_id, order),
                )
            else:
                conn.execute(
                    "UPDATE run_steps SET status=?, error_message=?, finished_at=? WHERE run_id=? AND step_order=?",
                    (status, error_message, now, run_id, order),
                )

    def get_recent_runs(
        self,
        limit: int = 5,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[dict]:
        clauses = []
        values: list[Any] = []
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        if thread_id is not None:
            clauses.append("thread_id=?")
            values.append(thread_id)
        where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
        values.append(limit)
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM simulation_runs {where}ORDER BY created_at DESC, id DESC LIMIT ?",
                values,
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run_detail(self, run_id: int) -> dict | None:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return None
            steps = conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY step_order",
                (run_id,),
            ).fetchall()
            result = dict(run)
            result["steps"] = [dict(s) for s in steps]
            return result

    def get_preference(self, key: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM user_preferences WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_preference(self, key: str, value: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?,?,?)",
                (key, value, datetime.now().isoformat()),
            )

    def get_scoped_preference(self, key: str, user_id: str = "", thread_id: str | None = None) -> str | None:
        return self.get_preference(self._scoped_key(key, user_id, thread_id))

    def set_scoped_preference(self, key: str, value: str, user_id: str = "", thread_id: str | None = None):
        self.set_preference(self._scoped_key(key, user_id, thread_id), value)

    def get_frequent_paths(
        self,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[str]:
        clauses = ["(key LIKE '%path_%' OR key LIKE '%_path' OR key LIKE '%folder_%' OR key LIKE '%_folder')"]
        values: list[Any] = []
        if user_id is not None:
            clauses.append("key LIKE ?")
            values.append(self._scoped_prefix(user_id, thread_id) + "%")
        query = (
            "SELECT value FROM user_preferences "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC LIMIT 10"
        )
        with self._get_conn() as conn:
            rows = conn.execute(query, values).fetchall()
            return [r[0] for r in rows]

    def save_summary(
        self,
        session_id: str,
        title: str = "",
        summary: str = "",
        messages: list[dict] | None = None,
        decisions: list[dict] | None = None,
        user_id: str = "",
        thread_id: str | None = None,
    ):
        thread_id = thread_id or session_id
        now = datetime.now().isoformat()
        messages_json = self._json(messages or [])
        decisions_json = self._json(decisions or [])
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM conversation_summaries WHERE user_id=? AND session_id=?",
                (user_id or "", session_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE conversation_summaries "
                    "SET thread_id=?, title=?, summary=?, messages_json=?, key_decisions_json=?, updated_at=? "
                    "WHERE id=?",
                    (thread_id or "", title, summary, messages_json, decisions_json, now, existing[0]),
                )
            else:
                conn.execute(
                    "INSERT INTO conversation_summaries "
                    "(user_id, thread_id, session_id, title, summary, messages_json, key_decisions_json, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (user_id or "", thread_id or "", session_id, title, summary, messages_json, decisions_json, now),
                )

    def update_messages(
        self,
        session_id: str,
        messages: list[dict],
        user_id: str = "",
    ):
        """Update messages for an existing session."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE conversation_summaries SET messages_json=?, updated_at=? WHERE user_id=? AND session_id=?",
                (self._json(messages), datetime.now().isoformat(), user_id or "", session_id),
            )

    def get_summary(self, session_id: str, user_id: str | None = None) -> dict | None:
        clauses = ["session_id=?"]
        values: list[Any] = [session_id]
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM conversation_summaries "
                f"WHERE {' AND '.join(clauses)} "
                "ORDER BY updated_at DESC, id DESC LIMIT 1",
                values,
            ).fetchone()
            return dict(row) if row else None

    def get_recent_summaries(
        self,
        limit: int = 10,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[dict]:
        clauses = []
        values: list[Any] = []
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        if thread_id is not None:
            clauses.append("thread_id=?")
            values.append(thread_id)
        where = f"WHERE {' AND '.join(clauses)} " if clauses else ""
        values.append(limit)
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, user_id, thread_id, session_id, title, summary, created_at, updated_at "
                f"FROM conversation_summaries {where}"
                "ORDER BY updated_at DESC, id DESC LIMIT ?",
                values,
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_conversation(self, session_id: str, user_id: str | None = None):
        clauses = ["session_id=?"]
        values: list[Any] = [session_id]
        if user_id is not None:
            clauses.append("user_id=?")
            values.append(user_id)
        with self._get_conn() as conn:
            conn.execute(
                f"DELETE FROM conversation_summaries WHERE {' AND '.join(clauses)}",
                values,
            )

    def save_workflow_state(self, state):
        payload = self._json(state.to_dict())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO workflow_states "
                "(thread_id, workflow_id, status, state_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(thread_id) DO UPDATE SET "
                "workflow_id=excluded.workflow_id, status=excluded.status, "
                "state_json=excluded.state_json, updated_at=excluded.updated_at",
                (
                    state.thread_id,
                    state.workflow_id,
                    state.status,
                    payload,
                    datetime.now().isoformat(),
                ),
            )

    def load_workflow_state(self, thread_id: str):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT state_json FROM workflow_states WHERE thread_id=?",
                (thread_id,),
            ).fetchone()
            if not row:
                return None
            from agent.core.workflow_state import WorkflowState

            return WorkflowState.from_dict(json.loads(row[0]))

    def delete_workflow_state(self, thread_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM workflow_states WHERE thread_id=?", (thread_id,))

    def save_workflow_run(self, user_id: str, thread_id: str, state) -> None:
        now = datetime.now().isoformat()
        state_json = self._json(state.to_dict())
        artifacts_json = self._json(getattr(state, "artifacts", {}) or {})
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO workflow_runs "
                "(workflow_id, user_id, thread_id, status, target_year, state_json, artifacts_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(workflow_id) DO UPDATE SET "
                "user_id=excluded.user_id, thread_id=excluded.thread_id, status=excluded.status, "
                "target_year=excluded.target_year, state_json=excluded.state_json, "
                "artifacts_json=excluded.artifacts_json, updated_at=excluded.updated_at",
                (
                    state.workflow_id,
                    user_id or "",
                    thread_id or state.thread_id or "",
                    state.status,
                    state.requested_target_year,
                    state_json,
                    artifacts_json,
                    now,
                ),
            )

    def save_workflow_artifacts(self, user_id: str, thread_id: str, state) -> None:
        rows = []
        for step_name, step in state.steps.items():
            for path in step.output_paths:
                rows.append((step_name, "output_path", "file", path, None))
            for key, value in step.artifacts.items():
                rows.extend(_artifact_rows(step_name, key, value))

        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM memory_artifacts WHERE user_id=? AND thread_id=? AND workflow_id=?",
                (user_id or "", thread_id or state.thread_id or "", state.workflow_id),
            )
            for step_name, artifact_key, artifact_type, path, value_json in rows:
                conn.execute(
                    "INSERT INTO memory_artifacts "
                    "(user_id, thread_id, workflow_id, step_name, artifact_key, artifact_type, path, value_json, metadata_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id or "",
                        thread_id or state.thread_id or "",
                        state.workflow_id,
                        step_name,
                        artifact_key,
                        artifact_type,
                        path,
                        value_json,
                        self._json({"source": "workflow"}),
                    ),
                )

    def get_thread_artifacts(self, user_id: str, thread_id: str) -> list[dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM memory_artifacts "
                "WHERE user_id=? AND thread_id=? "
                "ORDER BY created_at DESC, id DESC",
                (user_id or "", thread_id or ""),
            ).fetchall()
            return [dict(r) for r in rows]


def _artifact_rows(step_name: str, key: str, value: Any) -> list[tuple[str, str, str, str | None, str | None]]:
    rows: list[tuple[str, str, str, str | None, str | None]] = []
    if value in (None, ""):
        return rows
    if isinstance(value, (list, tuple, set)):
        for item in value:
            rows.extend(_artifact_rows(step_name, key, item))
        return rows
    if isinstance(value, str) and _looks_like_file_path(value):
        rows.append((step_name, key, "file", value, None))
        return rows
    rows.append((step_name, key, "value", None, json.dumps(value, ensure_ascii=False)))
    return rows


def _looks_like_file_path(value: str) -> bool:
    text = value.strip()
    if not text.lower().endswith(_PATH_SUFFIXES):
        return False
    return bool(re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith(("/", "\\")))
