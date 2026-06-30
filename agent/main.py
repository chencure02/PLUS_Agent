"""PLUS Agent - Chainlit entry point.

Usage:
    conda activate plus-agent
    cd /d path/to/PLUS_Agent
    chainlit run agent/main.py

Environment variables:
    PLUS_LLM_BACKEND  - LLM backend: claude (default), openai, deepseek, qwen
    PLUS_MEMORY_DB    - SQLite database path (default: PROJECT_ROOT/data/memory.db)
    ANTHROPIC_API_KEY - Claude API key
    OPENAI_API_KEY    - OpenAI API key
    DEEPSEEK_API_KEY  - DeepSeek API key
    DASHSCOPE_API_KEY - Qwen API key
"""
import os
import sys
from pathlib import Path

# Force matplotlib non-interactive backend BEFORE any other imports
# Prevents tkinter crash when rendering charts in Chainlit's async context
os.environ.setdefault("MPLBACKEND", "Agg")

# Ensure project root is on Python path so `agent` package is importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agent.config import MEMORY_DB_PATH  # noqa: E402

if not os.environ.get("PLUS_MEMORY_DB"):
    os.environ["PLUS_MEMORY_DB"] = MEMORY_DB_PATH

# Enable Chainlit conversation persistence + authentication
# Both are required for the chat history sidebar
import chainlit as cl  # noqa: E402
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer  # noqa: E402

_db_path = str(Path(__file__).resolve().parent.parent / ".chainlit" / "chainlit.db")

# Manually create tables using sync SQLAlchemy (async create_all fails on Windows+SQLite)
import sqlalchemy as sa  # noqa: E402
_sync_engine = sa.create_engine(f"sqlite:///{_db_path}")
with _sync_engine.connect() as _conn:
    # Check if tables need migration (missing columns from old manual schema)
    _elem_cols = [r[1] for r in _conn.execute(sa.text("PRAGMA table_info(elements)")).fetchall()]
    _step_cols = [r[1] for r in _conn.execute(sa.text("PRAGMA table_info(steps)")).fetchall()] if _elem_cols else []
    _need_migration = "chainlitKey" not in _elem_cols or "tags" not in _step_cols
    if _need_migration:
        for _t in ["elements", "steps", "threads", "users", "feedbacks"]:
            _conn.execute(sa.text(f"DROP TABLE IF EXISTS {_t}"))
        _conn.commit()

    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, identifier TEXT NOT NULL UNIQUE,
            "createdAt" TEXT, metadata TEXT
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY, "createdAt" TEXT, name TEXT,
            "userId" TEXT, "userIdentifier" TEXT, tags TEXT, metadata TEXT
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS steps (
            id TEXT PRIMARY KEY, name TEXT, type TEXT,
            "threadId" TEXT, "parentId" TEXT, streaming INTEGER,
            input TEXT, output TEXT, "isError" INTEGER,
            "waitForAnswer" INTEGER, "createdAt" TEXT, start TEXT,
            "end" TEXT, "defaultOpen" INTEGER, "autoCollapse" INTEGER,
            "showInput" TEXT, metadata TEXT, generation TEXT,
            tags TEXT, language TEXT, command TEXT, modes TEXT, icon TEXT
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS elements (
            id TEXT PRIMARY KEY, "threadId" TEXT, type TEXT,
            "chainlitKey" TEXT, url TEXT, "objectKey" TEXT,
            name TEXT, display TEXT, size TEXT, language TEXT,
            page INTEGER, "forId" TEXT, mime TEXT, props TEXT
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id TEXT PRIMARY KEY, "forId" TEXT, "threadId" TEXT,
            value INTEGER, comment TEXT
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_auth (
            identifier TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            workspace TEXT NOT NULL
        )
    """))
    _conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            identifier TEXT NOT NULL,
            backend TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (identifier, backend)
        )
    """))
    _conn.commit()
_sync_engine.dispose()

# Per-user workspace directories
def _user_workspace(identifier: str) -> dict:
    """Return per-user upload/output directories."""
    base = _project_root / "workspaces" / identifier.replace("@", "_at_").replace(".", "_")
    dirs = {
        "uploads_lulc": base / "uploads" / "lulc",
        "uploads_drivers": base / "uploads" / "drivers",
        "uploads_constraints": base / "uploads" / "constraints",
        "outputs": base / "outputs",
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return {k: str(v.resolve()) for k, v in dirs.items()}


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo=f"sqlite+aiosqlite:///{_db_path}")


@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    if not username or not password:
        return None
    import hashlib, secrets
    # Query or create user
    _engine = sa.create_engine(f"sqlite:///{_db_path}")
    with _engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT password_hash FROM user_auth WHERE identifier = :id"),
            {"id": username}
        ).fetchone()
        if row:
            # Existing user: verify password
            stored = row[0]
            salt, stored_hash = stored.split(":", 1)
            test_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
            if test_hash != stored_hash:
                _engine.dispose()
                return None
        else:
            # New user: register with hashed password
            salt = secrets.token_hex(16)
            pw_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
            stored = f"{salt}:{pw_hash}"
            conn.execute(
                sa.text("INSERT INTO user_auth (identifier, password_hash, workspace) VALUES (:id, :pw, :ws)"),
                {"id": username, "pw": stored, "ws": username}
            )
            conn.commit()
    _engine.dispose()
    return cl.User(identifier=username, metadata={"role": "user"})


import agent.ui.callbacks  # noqa: E402, F401 — registers Chainlit handlers
