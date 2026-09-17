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
import re
import sys
import base64
import math
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
from chainlit.auth.jwt import decode_jwt  # noqa: E402
from chainlit.server import app  # noqa: E402
from chainlit.session import WebsocketSession  # noqa: E402
from fastapi import HTTPException, Request  # noqa: E402

try:
    import aiosqlite  # noqa: F401, E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "PLUS Agent requires aiosqlite for Chainlit login and chat history. "
        "Install dependencies with: python -m pip install -r requirements.txt"
    ) from exc

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

DATA_EXTENSIONS = {".tif", ".tiff", ".csv", ".txt", ".json"}


def _path_id(path: Path) -> str:
    raw = str(path.resolve()).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _path_from_id(value: str) -> Path:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
    return Path(decoded.decode("utf-8")).resolve()


def _request_user_identifier(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        user = decode_jwt(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication") from exc
    identifier = getattr(user, "identifier", "") or ""
    if not identifier:
        raise HTTPException(status_code=401, detail="Invalid user")
    return identifier


def _workspace_root_for_user(identifier: str) -> Path:
    return (_project_root / "workspaces" / _safe_workspace_segment(identifier)).resolve()


def _workspace_roots_for_user(identifier: str) -> list[Path]:
    roots = [_workspace_root_for_user(identifier)]
    legacy = (_project_root / "workspaces" / identifier.replace("@", "_at_").replace(".", "_")).resolve()
    if legacy not in roots:
        roots.append(legacy)
    return roots


def _current_request_thread_id(request: Request) -> str | None:
    thread_id = (request.query_params.get("thread_id") or "").strip()
    if thread_id:
        return thread_id

    session_id = request.cookies.get("X-Chainlit-Session-id")
    if not session_id:
        return None
    session = WebsocketSession.get_by_id(session_id)
    if session and session.thread_id:
        return session.thread_id
    return None


def _thread_workspace_root(identifier: str, thread_id: str) -> Path:
    return _workspace_root_for_user(identifier) / "threads" / _safe_workspace_segment(thread_id, "default")


def _ensure_user_file(identifier: str, file_id: str, thread_id: str | None = None) -> Path:
    roots = [_thread_workspace_root(identifier, thread_id)] if thread_id else _workspace_roots_for_user(identifier)
    path = _path_from_id(file_id)
    if not path.exists() or path.suffix.lower() not in DATA_EXTENSIONS:
        raise HTTPException(status_code=404, detail="File not found")
    for root in roots:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue
    raise HTTPException(status_code=403, detail="File is outside this user's workspace")


def _file_role(path: Path) -> str:
    text = str(path).replace("\\", "/").lower()
    if "/outputs/" in text:
        return "output"
    if "/uploads/lulc/" in text:
        return "upload_lulc"
    if "/uploads/drivers/" in text:
        return "upload_driver"
    if "/uploads/constraints/" in text:
        return "upload_constraint"
    return "file"


def _thread_name(thread_id: str) -> str:
    _engine = sa.create_engine(f"sqlite:///{_db_path}")
    try:
        with _engine.connect() as conn:
            row = conn.execute(
                sa.text('SELECT name FROM threads WHERE id = :id'),
                {"id": thread_id},
            ).fetchone()
            if row and row[0]:
                return str(row[0])
    finally:
        _engine.dispose()
    return thread_id


def _catalog_files(identifier: str, thread_id: str | None = None) -> list[dict]:
    if not thread_id:
        return []

    target_thread = _safe_workspace_segment(thread_id, "default")
    roots = [_thread_workspace_root(identifier, thread_id)]
    items = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in DATA_EXTENSIONS:
                continue
            stat = path.stat()
            items.append({
                "id": _path_id(path),
                "name": path.name,
                "extension": path.suffix.lower(),
                "kind": "raster" if path.suffix.lower() in {".tif", ".tiff"} else "table" if path.suffix.lower() == ".csv" else "text",
                "role": _file_role(path),
                "threadId": thread_id,
                "threadName": _thread_name(thread_id),
                "threadDir": target_thread,
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
            })
    items.sort(key=lambda item: (item["threadName"], item["role"], item["name"].lower()))
    return items


def _json_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _csv_preview(path: Path) -> dict:
    import pandas as pd
    df = pd.read_csv(path)
    columns = [str(c) for c in df.columns]
    preview = df.head(200)
    numeric = df.select_dtypes(include="number")
    stats = []
    if not numeric.empty:
        desc = numeric.describe().round(4)
        for col in numeric.columns[:16]:
            stats.append({
                "name": str(col),
                "min": _json_number(desc.loc["min", col]),
                "max": _json_number(desc.loc["max", col]),
                "mean": _json_number(desc.loc["mean", col]),
            })
    return {
        "kind": "table",
        "name": path.name,
        "columns": columns,
        "rows": preview.fillna("").astype(str).values.tolist(),
        "rowCount": int(len(df)),
        "columnCount": int(len(columns)),
        "stats": stats,
    }


@app.get("/plus/data-catalog")
async def plus_data_catalog(request: Request):
    identifier = _request_user_identifier(request)
    thread_id = _current_request_thread_id(request)
    return {"threadId": thread_id, "items": _catalog_files(identifier, thread_id)}


@app.get("/plus/data-preview/{file_id}")
async def plus_data_preview(file_id: str, request: Request):
    identifier = _request_user_identifier(request)
    thread_id = _current_request_thread_id(request)
    if not thread_id:
        raise HTTPException(status_code=400, detail="No active thread")
    path = _ensure_user_file(identifier, file_id, thread_id)
    ext = path.suffix.lower()
    if ext in {".tif", ".tiff"}:
        from agent.ui.renderers import _build_geoscene_preview
        props = _build_geoscene_preview(str(path), path.name)
        return {"kind": "raster", "name": path.name, "props": props}
    if ext == ".csv":
        return _csv_preview(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"kind": "text", "name": path.name, "content": text[:20000]}


def _prioritize_plus_routes() -> None:
    routes = list(app.router.routes)
    plus_routes = [route for route in routes if getattr(route, "path", "").startswith("/plus/")]
    other_routes = [route for route in routes if route not in plus_routes]
    app.router.routes[:] = plus_routes + other_routes


_prioritize_plus_routes()

def _safe_workspace_segment(value: str, fallback: str = "default") -> str:
    """Return a filesystem-safe path segment for user and thread workspace names."""
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", (value or "").strip())
    segment = segment.strip("._-")
    return (segment or fallback)[:96]


# Per-thread workspace directories
def _user_workspace(identifier: str, thread_id: str | None = None) -> dict:
    """Return per-user, per-thread upload/output directories."""
    safe_user = _safe_workspace_segment(identifier)
    safe_thread = _safe_workspace_segment(thread_id or "default", "default")
    base = _project_root / "workspaces" / safe_user / "threads" / safe_thread
    dirs = {
        "root": base,
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
