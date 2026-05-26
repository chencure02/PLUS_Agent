import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


class MemoryStore:
    def __init__(self, db_path: str):
        dir_path = os.path.dirname(db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        schema = Path(__file__).parent / "schema.sql"
        with self._get_conn() as conn:
            conn.executescript(schema.read_text(encoding="utf-8"))

    def save_run(self, name: str, workflow: list, params: dict, outputs: list[str]) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO simulation_runs (name, workflow_json, params_json, output_paths_json, status) VALUES (?,?,?,?,'running')",
                (name, json.dumps(workflow), json.dumps(params), json.dumps(outputs))
            )
            return cur.lastrowid

    def update_run_status(self, run_id: int, status: str, error_message: str = None, duration: float = None):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE simulation_runs SET status=?, error_message=?, duration_seconds=? WHERE id=?",
                (status, error_message, duration, run_id)
            )

    def save_step(self, run_id: int, tool_name: str, order: int, params: dict,
                  tmp: str = None, outputs: list[str] = None) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO run_steps (run_id, tool_name, step_order, params_json, tmp_content, output_paths_json, status) VALUES (?,?,?,?,?,?,'pending')",
                (run_id, tool_name, order, json.dumps(params), tmp, json.dumps(outputs or []))
            )
            return cur.lastrowid

    def update_step_status(self, run_id: int, order: int, status: str, error_message: str = None):
        with self._get_conn() as conn:
            now = datetime.now().isoformat()
            if status == "running":
                conn.execute(
                    "UPDATE run_steps SET status=?, started_at=? WHERE run_id=? AND step_order=?",
                    (status, now, run_id, order)
                )
            else:
                conn.execute(
                    "UPDATE run_steps SET status=?, error_message=?, finished_at=? WHERE run_id=? AND step_order=?",
                    (status, error_message, now, run_id, order)
                )

    def get_recent_runs(self, limit: int = 5) -> list[dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM simulation_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run_detail(self, run_id: int) -> dict | None:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return None
            steps = conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY step_order", (run_id,)
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
                (key, value, datetime.now().isoformat())
            )

    def get_frequent_paths(self) -> list[str]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT value FROM user_preferences WHERE key LIKE '%_path' OR key LIKE '%_folder' ORDER BY updated_at DESC LIMIT 10"
            ).fetchall()
            return [r[0] for r in rows]

    def save_summary(self, session_id: str, title: str = "", summary: str = "",
                     messages: list[dict] | None = None, decisions: list[dict] | None = None):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO conversation_summaries "
                "(session_id, title, summary, messages_json, key_decisions_json) VALUES (?,?,?,?,?)",
                (session_id, title, summary, json.dumps(messages or []), json.dumps(decisions or []))
            )

    def update_messages(self, session_id: str, messages: list[dict]):
        """Update messages for an existing session."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE conversation_summaries SET messages_json=? WHERE session_id=?",
                (json.dumps(messages), session_id)
            )

    def get_summary(self, session_id: str) -> dict | None:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM conversation_summaries WHERE session_id=?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_recent_summaries(self, limit: int = 10) -> list[dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, session_id, title, summary, created_at FROM conversation_summaries "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_conversation(self, session_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM conversation_summaries WHERE session_id=?", (session_id,))
