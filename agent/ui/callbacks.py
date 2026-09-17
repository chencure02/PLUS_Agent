import os
import asyncio
import json
import logging
import uuid
from pathlib import Path

import chainlit as cl
from chainlit.context import context
from chainlit.input_widget import Select, TextInput

from agent.config import LLM_BACKEND, LLM_CONFIG
from agent.file_utils import (
    save_uploaded_file, extract_zip_to, scan_uploads, build_context_note,
    LULC_DIR, DRIVERS_DIR, CONSTRAINTS_DIR, OUTPUTS_DIR, make_output_dir,
)
from agent.llm.adapter import LLMError, create_llm
from agent.tools.registry import ToolRegistry
from agent.tools.convert import ConvertTool
from agent.tools.expansion import ExpansionTool
from agent.tools.leas import LEASTool
from agent.tools.markov import MarkovTool
from agent.tools.linear import LinearTool
from agent.tools.cars import CARSTool
from agent.tools.validation import ValidationTool
from agent.tools.diverse import DiverseTool
from agent.tools.file_tools import ListFilesTool, ReadFileTool, SearchFilesTool
from agent.tools.neighborhood_weight import NeighborhoodWeightTool
from agent.memory import MemoryStore
from agent.core.react_loop import ReactLoop
from agent.core.plus_workflow_runner import PLUSWorkflowRunner
from agent.core.workflow_router import WorkflowRouter
from agent.core.workflow_state import WorkflowContext
from agent.ui.renderers import render_raster, render_csv

logger = logging.getLogger(__name__)

_memory: MemoryStore | None = None
_registry: ToolRegistry | None = None
_MAX_HISTORY = 100


def _ensure_runtime_services():
    global _memory, _registry
    if _memory is None:
        db_path = os.environ.get("PLUS_MEMORY_DB", "data/memory.db")
        _memory = MemoryStore(db_path)
    if _registry is None:
        _registry = ToolRegistry()
        _registry.register(ConvertTool())
        _registry.register(ExpansionTool())
        _registry.register(LEASTool())
        _registry.register(MarkovTool())
        _registry.register(LinearTool())
        _registry.register(CARSTool())
        _registry.register(ValidationTool())
        _registry.register(DiverseTool())
        _registry.register(ListFilesTool())
        _registry.register(ReadFileTool())
        _registry.register(SearchFilesTool())
        _registry.register(NeighborhoodWeightTool())
    return _memory, _registry


def _build_loop(backend: str, model: str, api_key: str, base_url: str | None = None):
    memory, registry = _ensure_runtime_services()
    cfg = {
        "model": model,
        "api_key": api_key,
        "api_key_env": LLM_CONFIG.get(backend, {}).get("api_key_env", ""),
    }
    if base_url:
        cfg["base_url"] = base_url
    if api_key:
        llm = create_llm(backend, cfg)
        return ReactLoop(llm, registry, memory)
    return None  # Will be created when user configures a key


# ── User API key persistence ─────────────────────────────────

def _get_chainlit_db():
    """Open a sync SQLite connection to chainlit.db."""
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parent.parent.parent / ".chainlit" / "chainlit.db"
    return sqlite3.connect(str(db_path))


def _load_user_settings(identifier: str) -> dict:
    """Load saved backend and API keys for a user. Returns {backend: api_key} and active_backend."""
    memory, _ = _ensure_runtime_services()
    conn = _get_chainlit_db()
    try:
        rows = conn.execute(
            "SELECT backend, api_key FROM user_api_keys WHERE identifier = ?",
            (identifier,)
        ).fetchall()
        api_keys = {row[0]: row[1] for row in rows if row[1]}
        # Active backend stored in memory's user_preferences, scoped per user.
        active = None
        if memory:
            active = (
                memory.get_scoped_preference("backend", user_id=identifier)
                or memory.get_preference(f"backend:{identifier}")
            )
        return {"api_keys": api_keys, "active_backend": active}
    finally:
        conn.close()


def _save_user_api_key(identifier: str, backend: str, api_key: str):
    """Persist a user's API key for a given backend."""
    conn = _get_chainlit_db()
    try:
        conn.execute(
            "INSERT INTO user_api_keys (identifier, backend, api_key) VALUES (?, ?, ?) "
            "ON CONFLICT(identifier, backend) DO UPDATE SET api_key = excluded.api_key",
            (identifier, backend, api_key)
        )
        conn.commit()
    finally:
        conn.close()


def _save_user_backend(identifier: str, backend: str):
    """Persist the user's preferred backend selection."""
    if _memory:
        _memory.set_scoped_preference("backend", backend, user_id=identifier)


def _get_effective_api_key() -> str:
    """Return the API key for the current user and backend, or '' if not set."""
    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"
    backend = cl.user_session.get("active_backend", LLM_BACKEND)
    settings = _load_user_settings(identifier)
    return settings["api_keys"].get(backend, "")


# ── Lifecycle ────────────────────────────────────────────────

def _current_thread_id() -> str:
    try:
        thread_id = getattr(context.session, "thread_id", "")
    except Exception:
        thread_id = ""
    return thread_id or cl.user_session.get("workspace_thread_id") or str(uuid.uuid4())


def _init_session(thread_id: str | None = None):
    """Set up per-thread session state. Called on new chat or resume."""
    user = cl.user_session.get("user")
    user_id = user.identifier if user else "default"
    workspace_thread_id = thread_id or _current_thread_id()

    from agent.main import _user_workspace
    ws = _user_workspace(user_id, workspace_thread_id)
    cl.user_session.set("workspace_thread_id", workspace_thread_id)
    cl.user_session.set("workspace_root", ws["root"])
    cl.user_session.set("ws_uploads_lulc", ws["uploads_lulc"])
    cl.user_session.set("ws_uploads_drivers", ws["uploads_drivers"])
    cl.user_session.set("ws_uploads_constraints", ws["uploads_constraints"])
    cl.user_session.set("ws_outputs", ws["outputs"])
    cl.user_session.set("output_dir", ws["outputs"])
    return ws


def _scan_session_uploads() -> set[str]:
    scan = scan_uploads(
        cl.user_session.get("ws_uploads_lulc", str(LULC_DIR)),
        cl.user_session.get("ws_uploads_drivers", str(DRIVERS_DIR)),
        cl.user_session.get("ws_uploads_constraints", str(CONSTRAINTS_DIR)),
    )
    files = set(scan["lulc_files"])
    files.update(scan["driver_files"])
    files.update(scan["constraint_files"])
    return files


def _sync_session_workspace() -> None:
    thread_id = _current_thread_id()
    if thread_id and thread_id != cl.user_session.get("workspace_thread_id"):
        _init_session(thread_id)
        cl.user_session.set("session_files", _scan_session_uploads())


@cl.on_chat_start
async def on_chat_start():
    # Load saved settings for the current user
    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"
    settings = _load_user_settings(identifier)

    backend = settings.get("active_backend") or LLM_BACKEND
    cfg = LLM_CONFIG.get(backend, LLM_CONFIG["claude"])
    api_key = settings["api_keys"].get(backend, "")
    cl.user_session.set("active_backend", backend)

    loop = _build_loop(backend, cfg["model"], api_key, cfg.get("base_url"))
    cl.user_session.set("react_loop", loop)
    cl.user_session.set("history", [])
    cl.user_session.set("context_notes", [])
    thread_id = _current_thread_id()
    cl.user_session.set("memory_session_id", thread_id)
    _init_session(thread_id)
    cl.user_session.set("session_files", _scan_session_uploads())

    masked_key = api_key[:6] + "****" + api_key[-4:] if len(api_key) > 10 else api_key
    await cl.ChatSettings([
        Select(id="backend", label="模型后端",
               values=["claude", "openai", "deepseek", "qwen"], initial_value=backend),
        TextInput(id="api_key", label="API Key", initial=masked_key, placeholder="sk-..."),
    ]).send()

    welcome = "你好！我是 **PLUS Agent**，基于 PLUS 模型的土地利用模拟助手。\n\n"
    welcome += "对话栏左侧 ⚙ 可切换模型和配置 API Key。\n"
    welcome += "📎 直接拖拽或粘贴文件上传数据（.tif 或 .zip）。\n"
    welcome += "左侧边栏可以查看和继续历史对话。\n\n"
    if not api_key:
        welcome += "⚠ **请先在左侧 ⚙ 设置面板中配置所选模型的 API Key，否则无法正常对话。**"
    await cl.Message(content=welcome).send()


@cl.on_chat_resume
async def on_chat_resume(thread):
    """Called when user clicks a past thread in the sidebar."""
    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"
    settings = _load_user_settings(identifier)

    backend = settings.get("active_backend") or LLM_BACKEND
    cfg = LLM_CONFIG.get(backend, LLM_CONFIG["claude"])
    api_key = settings["api_keys"].get(backend, "")
    cl.user_session.set("active_backend", backend)

    loop = _build_loop(backend, cfg["model"], api_key, cfg.get("base_url"))
    cl.user_session.set("react_loop", loop)
    cl.user_session.set("history", [])
    cl.user_session.set("context_notes", [])
    thread_id = thread.get("id", "") if isinstance(thread, dict) else getattr(thread, "id", "")
    cl.user_session.set("memory_session_id", thread_id or str(uuid.uuid4()))
    _init_session(thread_id or _current_thread_id())
    cl.user_session.set("session_files", _scan_session_uploads())

    # Inject saved context from the resumed conversation
    if thread_id and _memory:
        _inject_resume_context(thread_id)

    # Re-send ChatSettings (required for UI context on resume)
    masked_key = api_key[:6] + "****" + api_key[-4:] if len(api_key) > 10 else api_key
    await cl.ChatSettings([
        Select(id="backend", label="模型后端",
               values=["claude", "openai", "deepseek", "qwen"], initial_value=backend),
        TextInput(id="api_key", label="API Key", initial=masked_key, placeholder="sk-..."),
    ]).send()
    # Do NOT send messages here — Chainlit auto-restores thread messages after hook returns


@cl.on_settings_update
async def on_settings_update(settings):
    backend = (settings.get("backend") if isinstance(settings, dict) else settings) or LLM_BACKEND
    raw_key = (settings.get("api_key", "") if isinstance(settings, dict) else "").strip()
    if backend not in LLM_CONFIG:
        await cl.Message(content=f"❌ 未知后端：`{backend}`").send()
        return

    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"

    # Resolve effective API key: new input, or load saved, or empty
    if raw_key and "*" not in raw_key:
        api_key = raw_key  # User typed a real key
    else:
        # User didn't change the key — load saved key for this backend
        settings = _load_user_settings(identifier)
        api_key = settings["api_keys"].get(backend, "")

    cfg = LLM_CONFIG[backend]
    model = cfg["model"]
    base_url = cfg.get("base_url")

    # Persist
    _save_user_backend(identifier, backend)
    if api_key:
        _save_user_api_key(identifier, backend, api_key)
    cl.user_session.set("active_backend", backend)

    loop = _build_loop(backend, model, api_key, base_url)
    cl.user_session.set("react_loop", loop)
    cl.user_session.set("history", [])

    key_status = "✅ 已配置" if api_key else "⚠ 未配置 API Key"
    await cl.Message(content=f"✅ 已切换到 `{backend}`（`{model}`）—— {key_status}").send()


# ── Memory helpers ──────────────────────────────────────────

def _json_list(raw) -> list:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        loaded = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


def _build_resume_context_notes(summary: dict) -> list[str]:
    """Build compact context notes from persisted thread memory."""
    notes = []
    summary_text = (summary.get("summary") or "").strip()
    if summary_text:
        notes.append(f"[恢复会话摘要] {summary_text}")

    messages = _json_list(summary.get("messages_json", "[]"))[-6:]
    if messages:
        lines = ["[恢复会话最近消息]"]
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = "用户" if item.get("role") == "user" else "助手"
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content:
                lines.append(f"{role}: {content[:300]}")
        if len(lines) > 1:
            notes.append("\n".join(lines))

    decisions = _json_list(summary.get("key_decisions_json", "[]"))
    if decisions:
        lines = ["[恢复会话关键产出]"]
        for d in decisions:
            path_note = d.get("path_note", "") if isinstance(d, dict) else str(d)
            if path_note:
                lines.append(f"- {path_note}")
        if len(lines) > 1:
            notes.append("\n".join(lines))
    return notes


def _build_artifact_context_notes(artifacts: list[dict]) -> list[str]:
    if not artifacts:
        return []
    lines = ["[恢复会话产物]"]
    for item in artifacts[:12]:
        step = item.get("step_name") or "workflow"
        key = item.get("artifact_key") or "artifact"
        path = item.get("path")
        value = item.get("value_json")
        if path:
            lines.append(f"- {step}.{key}: {path}")
        elif value:
            lines.append(f"- {step}.{key}: {value[:240]}")
    return ["\n".join(lines)] if len(lines) > 1 else []


def _inject_resume_context(thread_id: str):
    """Load saved conversation context for a resumed thread."""
    if _memory is None:
        return
    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"
    summary = _memory.get_summary(thread_id, user_id=identifier) or _memory.get_summary(thread_id)
    artifacts = _memory.get_thread_artifacts(identifier, thread_id)
    if not summary and not artifacts:
        return
    context_notes: list = cl.user_session.get("context_notes", [])
    resume_notes = _build_resume_context_notes(summary) if summary else []
    context_notes[0:0] = resume_notes + _build_artifact_context_notes(artifacts)
    cl.user_session.set("context_notes", context_notes)


def _save_session_memory(session_id: str, user_msg: str, final_text: str,
                         context_notes: list[str], history: list[dict],
                         user_id: str = "", thread_id: str | None = None):
    """Persist conversation summary for cross-session recall."""
    if _memory is None or not session_id or not final_text:
        return
    decisions = []
    for note in context_notes:
        if ":" in note and not note.startswith("["):
            decisions.append({"path_note": note})
    summary = _lightweight_turn_summary(user_msg, final_text, context_notes)
    _memory.save_summary(
        session_id=session_id,
        title=user_msg[:100],
        summary=summary,
        messages=history[-20:],
        decisions=decisions,
        user_id=user_id,
        thread_id=thread_id or session_id,
    )


def _lightweight_turn_summary(user_msg: str, final_text: str, context_notes: list[str]) -> str:
    facts = [
        note for note in context_notes
        if not note.startswith("[已上传]") and not note.startswith("[输出目录]") and not note.startswith("[恢复")
    ][-5:]
    parts = [
        f"最近用户请求: {user_msg[:240]}",
        f"最近助手回复: {final_text[:360]}",
    ]
    if facts:
        parts.append("关键上下文: " + "；".join(facts))
    return "\n".join(parts)[:1000]


# ── Helpers ─────────────────────────────────────────────────

def _parse_param_value(raw: str, param_type: str):
    raw = raw.strip()
    if param_type == "array":
        if "," in raw:
            return [v.strip() for v in raw.split(",") if v.strip()]
        return [raw]
    if param_type == "integer":
        return int(raw)
    if param_type == "number":
        return float(raw)
    return raw


async def _handle_uploads(elements: list) -> tuple[str, set]:
    """Save uploaded files to per-user workspace. Returns (status_message, set_of_paths)."""
    # Use per-user workspace dirs instead of global constants
    lulc_dir = Path(cl.user_session.get("ws_uploads_lulc", str(LULC_DIR)))
    drivers_dir = Path(cl.user_session.get("ws_uploads_drivers", str(DRIVERS_DIR)))

    tif_files, zip_files, other_files = [], [], []
    for el in elements:
        name = getattr(el, "name", "")
        if name.lower().endswith(".zip"):
            zip_files.append(el)
        elif name.lower().endswith((".tif", ".tiff")):
            tif_files.append(el)
        else:
            other_files.append(el)

    msgs = []
    saved = set()
    for f in tif_files:
        subdir = drivers_dir if any(k in f.name.lower() for k in ["dem", "slope", "dist_", "pre", "tem", "gdp", "pop", "soil"]) else lulc_dir
        subdir.mkdir(parents=True, exist_ok=True)
        path = save_uploaded_file(f, subdir)
        if path:
            saved.add(path)
            msgs.append(f"✅ `{f.name}` → `{subdir}/`")
    for f in zip_files:
        if f.path and os.path.exists(f.path):
            drivers_dir.mkdir(parents=True, exist_ok=True)
            extracted = extract_zip_to(f.path, drivers_dir)
            saved.update(extracted)
            msgs.append(f"📦 `{f.name}` 解压到 `{drivers_dir}`（{len(extracted)} 个文件）")
    for f in other_files:
        msgs.append(f"⚠️ `{f.name}` 格式不支持，已跳过")

    if msgs:
        return "**文件上传结果：**\n" + "\n".join(msgs), saved
    return "", saved
    return "", saved


def _workflow_context_from_session(
    user_msg_text: str,
    session_files: set[str],
    output_dir: str,
) -> WorkflowContext:
    def has_part(path: str, part: str) -> bool:
        return f"/{part}/" in path.replace("\\", "/").lower()

    lulc_files = sorted(path for path in session_files if has_part(path, "lulc"))
    driver_files = sorted(path for path in session_files if has_part(path, "drivers"))
    constraint_files = sorted(path for path in session_files if has_part(path, "constraints"))
    return WorkflowContext(
        thread_id=_current_thread_id(),
        user_message=user_msg_text,
        lulc_files=lulc_files,
        driver_files=driver_files,
        constraint_files=constraint_files,
        output_dir=output_dir,
        drivers_dir=cl.user_session.get("ws_uploads_drivers", ""),
        constraints_dir=cl.user_session.get("ws_uploads_constraints", ""),
    )


def _is_active_workflow_state(state) -> bool:
    return bool(state and state.status in {"collecting", "waiting_confirmation", "running"})


def _render_output_elements(output_paths: list[str]) -> list:
    elements = []
    for path in output_paths:
        ext = path.lower()
        if ext.endswith((".tif", ".tiff")):
            try:
                elem = render_raster(path, os.path.basename(path))
                if elem:
                    elements.append(elem)
            except Exception as e:
                logger.warning(f"Failed to render raster {path}: {e}")
        elif ext.endswith(".csv"):
            elem = render_csv(path)
            if elem:
                elements.append(elem)
    return elements


async def _send_workflow_tool_result(event: dict):
    result = event["result"]
    async with cl.Step(name=f"PLUS workflow: {event['step']}") as step:
        step.input = str(event["state"].steps[event["step"]].params)
        if result.success:
            msg = f"✅ {result.message}"
            if result.output_paths:
                msg += "\n\n**Outputs:**\n" + "\n".join(f"- `{p}`" for p in result.output_paths)
            step.output = msg
            elements = _render_output_elements(result.output_paths)
            if elements:
                step.elements = elements
        else:
            step.output = f"❌ **Error:** {result.error or 'Unknown'}"


def _persist_completed_workflow(memory: MemoryStore, user_id: str, thread_id: str, state) -> None:
    if not thread_id or state.status != "completed":
        return
    memory.save_workflow_run(user_id, thread_id, state)
    memory.save_workflow_artifacts(user_id, thread_id, state)


async def _handle_managed_workflow(
    user_msg_text: str,
    thread_id: str,
    workflow_context: WorkflowContext,
    user_id: str,
) -> bool:
    memory, registry = _ensure_runtime_services()
    router = WorkflowRouter()
    active_state = memory.load_workflow_state(thread_id) if thread_id else None
    has_active = _is_active_workflow_state(active_state)

    if not router.should_use_workflow(user_msg_text, has_active_workflow=has_active):
        return False

    runner = PLUSWorkflowRunner(registry)
    state = active_state if active_state and active_state.status not in {"completed", "cancelled"} else None
    if state is None:
        state = runner.start(thread_id, workflow_context)
        await cl.Message(content="✅ 已进入 PLUS 标准模拟工作流。系统会在每个工具执行前展示参数，确认后再运行。").send()

    event = runner.prepare_next(state, workflow_context)
    while True:
        memory.save_workflow_state(state)
        event_type = event.get("type")

        if event_type in {"workflow_completed", "workflow_text"}:
            _persist_completed_workflow(memory, user_id, thread_id, state)
            await cl.Message(content=event.get("content", "")).send()
            return True

        if event_type not in {"workflow_confirm", "workflow_collect"}:
            await cl.Message(content=event.get("content", "工作流状态已更新。")).send()
            return True

        response = await cl.AskUserMessage(content=event["text"], timeout=600).send()
        if not response or not response.get("output") or not response["output"].strip():
            memory.save_workflow_state(state)
            await cl.Message(content="⏸ 当前工作流已暂停在参数确认阶段。你稍后发送“继续”即可恢复。").send()
            return True

        action = runner.apply_user_reply(state, response["output"])
        memory.save_workflow_state(state)
        action_type = action.get("type")

        if action_type == "workflow_invalid_reply":
            await cl.Message(content=f"⚠ {action.get('content', '')}").send()
            continue
        if action_type == "workflow_cancelled":
            await cl.Message(content=action.get("content", "已取消当前 PLUS 工作流。")).send()
            return True
        if action_type in {"workflow_confirm", "workflow_collect"}:
            event = action
            continue
        if action_type != "workflow_ready":
            await cl.Message(content=action.get("content", "工作流状态已更新。")).send()
            return True

        await cl.Message(content=f"✅ `{action['step']}` 参数已确认，开始执行。").send()
        exec_event = await asyncio.to_thread(runner.execute_current_step, state)
        memory.save_workflow_state(state)
        await _send_workflow_tool_result(exec_event)

        if not exec_event.get("success"):
            result = exec_event["result"]
            await cl.Message(
                content=f"❌ 工作流在 `{exec_event['step']}` 失败：`{result.error or 'Unknown error'}`"
            ).send()
            return True
        if state.status == "completed":
            _persist_completed_workflow(memory, user_id, thread_id, state)
            await cl.Message(content="✅ PLUS 标准模拟工作流已完成。你可以在右下角数据看板查看输出结果。").send()
            return True

        event = runner.prepare_next(state, workflow_context)


# ── Message handler ─────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
    _sync_session_workspace()
    user = cl.user_session.get("user")
    identifier = user.identifier if user else "default"
    history = cl.user_session.get("history", [])
    context_notes = cl.user_session.get("context_notes", [])
    session_files: set = cl.user_session.get("session_files", set())
    out_dir = cl.user_session.get("output_dir", "")

    # Handle file uploads FIRST, before building context
    user_msg_text = message.content
    if message.elements:
        upload_msg, new_paths = await _handle_uploads(message.elements)
        session_files.update(new_paths)
        cl.user_session.set("session_files", session_files)
        if upload_msg:
            upload_elements = []
            for path in sorted(new_paths):
                ext = path.lower()
                if ext.endswith((".tif", ".tiff")):
                    try:
                        elem = render_raster(path, os.path.basename(path))
                        if elem:
                            upload_elements.append(elem)
                    except Exception as e:
                        logger.warning(f"Failed to render uploaded raster {path}: {e}")
            await cl.Message(content=upload_msg, elements=upload_elements).send()
        # Inject upload info into the user message so the LLM sees it
        if new_paths:
            names = ", ".join(os.path.basename(p) for p in new_paths)
            user_msg_text = f"(用户刚刚上传了文件: {names})\n{user_msg_text}"

    # Sync to Chainlit's real thread ID (available once first message arrives)
    chainlit_sid = _current_thread_id()
    if chainlit_sid:
        cl.user_session.set("memory_session_id", chainlit_sid)

    # Build context: only show files from THIS session
    context_notes = [n for n in context_notes
                     if not n.startswith("[已上传]") and not n.startswith("[输出目录]")]
    if session_files:
        # Build a custom note from session files only
        lulc = [p for p in session_files if "/lulc/" in p.replace("\\", "/")]
        drivers = sorted(set(os.path.dirname(p) for p in session_files
                            if "/drivers/" in p.replace("\\", "/")))
        constraints = [p for p in session_files if "/constraints/" in p.replace("\\", "/")]
        parts = []
        if lulc:
            parts.append(f"LULC 数据 ({len(lulc)} 张): " + ", ".join(lulc))
        if drivers:
            parts.append("驱动因子文件夹: " + ", ".join(drivers))
        if constraints:
            parts.append("约束图: " + ", ".join(constraints))
        if parts:
            context_notes.insert(0, f"[已上传] {' | '.join(parts)}")
    if out_dir:
        context_notes.insert(1, f"[输出目录] 所有输出结果请使用此目录: {out_dir}")

    workflow_context = _workflow_context_from_session(message.content, session_files, out_dir)
    if await _handle_managed_workflow(message.content, chainlit_sid, workflow_context, identifier):
        return

    # Ordinary ReAct chat still requires a configured model backend.
    api_key = _get_effective_api_key()
    if not api_key:
        backend = cl.user_session.get("active_backend", LLM_BACKEND)
        await cl.Message(
            content=f"⚠ 当前后端 `{backend}` 尚未配置 API Key。\n"
                    f"请在左侧 ⚙ 设置面板中填入对应的 API Key 后再开始对话。"
        ).send()
        return

    final_text = ""
    loop = cl.user_session.get("react_loop")
    if loop is None:
        backend = cl.user_session.get("active_backend", LLM_BACKEND)
        await cl.Message(
            content=f"⚠ 当前后端 `{backend}` 尚未初始化。请在左侧 ⚙ 设置面板中重新保存 API Key。"
        ).send()
        return

    try:
        async for event in loop.run(
            user_msg_text,
            history,
            context_notes,
            user_id=identifier,
            thread_id=chainlit_sid,
        ):
            if event["type"] == "ask_params":
                tool_name = event["tool"]
                collected = {}
                cancelled = False
                for pinfo in event["missing"]:
                    desc = pinfo["description"] or f"type: {pinfo['type']}"
                    hint = ""
                    existing = event.get("params", {}).get(pinfo["name"])
                    if existing:
                        hint = f"\n(current: `{existing}` — type a new value or press Enter to keep)"
                    res = await cl.AskUserMessage(
                        content=f"**`{tool_name}`** needs parameter **`{pinfo['name']}`**\n{desc}{hint}\n\n(输入 **cancel** 取消此工具调用)",
                        timeout=600,
                    ).send()
                    if not res or not res.get("output"):
                        continue
                    raw = res["output"].strip()
                    if raw.lower() in ("取消", "cancel", "stop", "停"):
                        await cl.Message(content="⏸ 已取消").send()
                        cancelled = True
                        break
                    try:
                        collected[pinfo["name"]] = _parse_param_value(
                            raw, pinfo["type"])
                    except (ValueError, TypeError):
                        await cl.Message(
                            content=f"⚠️ Invalid value for `{pinfo['name']}` (expected {pinfo['type']}), skipping."
                        ).send()
                if cancelled:
                    await event["queue"].put({"cancel": True, "message": "用户取消参数输入"})
                else:
                    await event["queue"].put(collected)

            elif event["type"] == "confirm_params":
                res = await cl.AskUserMessage(content=event["text"], timeout=600).send()
                if not res or not res.get("output") or not res["output"].strip():
                    await cl.Message(content="⏸ 超时或空输入，已取消。请重新给出指令。").send()
                    await event["queue"].put({"cancel": True, "message": "用户未响应确认提示"})
                    continue

                raw_output = res["output"].strip()
                raw_lower = raw_output.lower()
                if raw_lower in ("ok", "confirm", "yes", "y"):
                    await cl.Message(content="✅ 按当前参数继续。").send()
                    await event["queue"].put({})
                elif raw_lower in ("停", "取消", "cancel", "stop"):
                    await cl.Message(content="⏸ 已取消").send()
                    await event["queue"].put({"cancel": True, "message": raw_output})
                else:
                    # Not a simple ok/cancel — cancel tool and forward to main LLM for intelligent handling
                    await cl.Message(content="🤔 已转发给模型处理...").send()
                    await event["queue"].put({"cancel": True, "message": raw_output})

            elif event["type"] == "tool_result":
                tr = event["result"]
                async with cl.Step(name=tr["tool"]) as step:
                    step.input = str(tr.get("params", {}))
                    if tr["success"]:
                        msg = f"✅ {tr.get('message', '')}"
                        if tr.get("output_paths"):
                            msg += "\n\n**Outputs:**\n" + "\n".join(f"- `{p}`" for p in tr["output_paths"])
                        step.output = msg
                        elements = []
                        for path in tr.get("output_paths", []):
                            ext = path.lower()
                            if ext.endswith(".tif") or ext.endswith(".tiff"):
                                try:
                                    elem = render_raster(path, os.path.basename(path))
                                    if elem:
                                        elements.append(elem)
                                except Exception as e:
                                    logger.warning(f"Failed to render raster {path}: {e}")
                            elif ext.endswith(".csv"):
                                elem = render_csv(path)
                                if elem:
                                    elements.append(elem)
                        if elements:
                            step.elements = elements
                    else:
                        step.output = f"❌ **Error:** {tr.get('error', 'Unknown')}"

            elif event["type"] == "text":
                final_text = event["content"]
    except LLMError as exc:
        logger.exception("LLM call failed")
        await cl.Message(
            content="⚠ 模型接口连接失败，Agent 已收到你的消息，但无法从当前 LLM 后端拿到回复。\n\n"
                    f"后端错误：`{exc}`\n\n"
                    "请检查：\n"
                    "1. 左侧 ⚙ 中选择的模型后端和 API Key 是否正确；\n"
                    "2. 当前启动 Chainlit 的终端是否可以访问对应模型服务；\n"
                    "3. 如果服务是由 Codex 启动的，外部网络可能受限，建议在 VS Code 终端中手动启动项目后再试。"
        ).send()
        return
    except Exception as exc:
        logger.exception("Unhandled error while processing user message")
        await cl.Message(
            content="⚠ Agent 处理消息时发生未捕获异常，详情已写入后端终端日志。\n\n"
                    f"错误：`{type(exc).__name__}: {exc}`"
        ).send()
        return

    # Update history
    history.append({"role": "user", "content": message.content})
    if final_text:
        history.append({"role": "assistant", "content": final_text})
        await cl.Message(content=final_text).send()
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    cl.user_session.set("history", history)

    # Persist context facts
    _extract_context_facts(message.content, final_text, context_notes)
    cl.user_session.set("context_notes", context_notes)

    _maybe_save_paths(message.content, identifier, chainlit_sid)
    if final_text:
        _maybe_save_paths(final_text, identifier, chainlit_sid)

    # Persist conversation summary for cross-session recall
    session_id = cl.user_session.get("memory_session_id", "")
    _save_session_memory(
        session_id,
        message.content,
        final_text,
        context_notes,
        history,
        user_id=identifier,
        thread_id=chainlit_sid,
    )


def _extract_context_facts(user_msg: str, assistant_msg: str, notes: list[str]):
    import re
    all_text = f"{user_msg}\n{assistant_msg}"
    drives = r"[A-Za-z]:"
    path_pattern = rf"({drives}[\\/][^\s,;]+\.(?:tif|tiff|img|dat|shp|csv))"
    found_paths = set()
    for match in re.findall(path_pattern, all_text, re.IGNORECASE):
        path = match if isinstance(match, str) else match[0]
        found_paths.add(path)
    for path in found_paths:
        basename = os.path.basename(path).lower()
        if "landuse" in basename or "expansion" in basename:
            note = f"用地扩张结果: {path}"
        elif "potential" in basename or "band" in basename:
            note = f"LEAS 概率图: {path}"
        elif "simulation" in basename:
            note = f"CARS 模拟结果: {path}"
        elif "drivingfactor" in basename or "driver" in basename:
            note = f"驱动因子文件夹: {path}"
        elif "refy" in basename or "lulc" in basename:
            note = f"土地利用数据: {path}"
        elif "markov" in basename:
            note = f"Markov 预测结果: {path}"
        elif "kappa" in basename or "fom" in basename:
            note = f"精度验证结果: {path}"
        elif "contribution" in basename:
            note = f"驱动因子贡献度: {path}"
        else:
            note = f"文件路径: {path}"
        if note not in notes:
            notes.append(note)
    while len(notes) > 20:
        notes.pop(0)


def _maybe_save_paths(text: str, user_id: str = "", thread_id: str = ""):
    if _memory is None:
        return
    import re
    drives = r"[A-Za-z]:"
    pattern = rf"({drives}[\\/][^\s,;]+\.(?:tif|tiff|img|dat|shp|csv))"
    for match in re.findall(pattern, text, re.IGNORECASE):
        path = match if isinstance(match, str) else match[0]
        name = os.path.splitext(os.path.basename(path))[0]
        key = f"path_{name}"[:50]
        if not _memory.get_scoped_preference(key, user_id=user_id, thread_id=thread_id):
            _memory.set_scoped_preference(key, path, user_id=user_id, thread_id=thread_id)
