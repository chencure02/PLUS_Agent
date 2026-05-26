import os
import asyncio
import logging
from pathlib import Path

import chainlit as cl
from chainlit.input_widget import Select, TextInput

from agent.config import LLM_BACKEND, LLM_CONFIG
from agent.file_utils import (
    save_uploaded_file, extract_zip_to, scan_uploads, build_context_note,
    LULC_DIR, DRIVERS_DIR, CONSTRAINTS_DIR, OUTPUTS_DIR, make_output_dir,
)
from agent.llm.adapter import create_llm
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
from agent.ui.renderers import render_raster, render_csv

logger = logging.getLogger(__name__)

_loop: ReactLoop | None = None
_memory: MemoryStore | None = None
_registry: ToolRegistry | None = None
_MAX_HISTORY = 100


def _build_loop(backend: str, api_key_env: str, model: str, base_url: str | None = None):
    global _loop, _memory, _registry
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
    cfg = {"model": model, "api_key_env": "_PLUS_USER_API_KEY"}
    if base_url:
        cfg["base_url"] = base_url
    os.environ.setdefault("_PLUS_USER_API_KEY", os.environ.get(api_key_env, ""))
    llm = create_llm(backend, cfg)
    _loop = ReactLoop(llm, _registry, _memory)


# ── Lifecycle ────────────────────────────────────────────────

def _init_session():
    """Set up per-user session state. Called on new chat or resume."""
    user = cl.user_session.get("user")
    user_id = user.identifier if user else "default"
    safe_id = user_id.replace("@", "_at_").replace(".", "_")

    from agent.main import _user_workspace
    ws = _user_workspace(user_id)
    cl.user_session.set("ws_uploads_lulc", ws["uploads_lulc"])
    cl.user_session.set("ws_uploads_drivers", ws["uploads_drivers"])
    cl.user_session.set("ws_uploads_constraints", ws["uploads_constraints"])
    cl.user_session.set("ws_outputs", ws["outputs"])
    cl.user_session.set("output_dir", ws["outputs"])


@cl.on_chat_start
async def on_chat_start():
    backend = LLM_BACKEND
    cfg = LLM_CONFIG.get(backend, LLM_CONFIG["claude"])
    _build_loop(backend, cfg["api_key_env"], cfg["model"], cfg.get("base_url"))
    cl.user_session.set("history", [])
    cl.user_session.set("context_notes", [])
    cl.user_session.set("session_files", set())
    _init_session()

    await cl.ChatSettings([
        Select(id="backend", label="模型后端",
               values=["claude", "openai", "deepseek", "qwen"], initial_value=backend),
        TextInput(id="api_key", label="API Key（留空则使用 .env 配置）", initial=""),
    ]).send()

    runs = _memory.get_recent_runs(3)
    welcome = "你好！我是 **PLUS Agent**，基于 PLUS 模型的土地利用模拟助手。\n\n"
    welcome += "对话栏左侧 ⚙ 可切换模型和配置 API Key。\n"
    welcome += "📎 直接拖拽或粘贴文件上传数据（.tif 或 .zip）。\n"
    welcome += "左侧边栏可以查看和继续历史对话。\n\n"
    if runs:
        welcome += "### 最近运行\n"
        for r in runs:
            icon = "✅" if r["status"] == "success" else "❌"
            welcome += f"- {icon} **{r['name']}** ({r['created_at'][:10]})\n"
    await cl.Message(content=welcome).send()


@cl.on_chat_resume
async def on_chat_resume(thread):
    """Called when user clicks a past thread in the sidebar."""
    backend = LLM_BACKEND
    cfg = LLM_CONFIG.get(backend, LLM_CONFIG["claude"])
    _build_loop(backend, cfg["api_key_env"], cfg["model"], cfg.get("base_url"))
    cl.user_session.set("history", [])
    cl.user_session.set("context_notes", [])
    cl.user_session.set("session_files", set())
    _init_session()
    # Re-send ChatSettings (required for UI context on resume)
    await cl.ChatSettings([
        Select(id="backend", label="模型后端",
               values=["claude", "openai", "deepseek", "qwen"], initial_value=backend),
        TextInput(id="api_key", label="API Key（留空则使用 .env 配置）", initial=""),
    ]).send()
    # Do NOT send messages here — Chainlit auto-restores thread messages after hook returns


@cl.on_settings_update
async def on_settings_update(settings):
    backend = (settings.get("backend") if isinstance(settings, dict) else settings) or LLM_BACKEND
    api_key = (settings.get("api_key", "") if isinstance(settings, dict) else "").strip()
    if backend not in LLM_CONFIG:
        await cl.Message(content=f"❌ 未知后端：`{backend}`").send()
        return
    cfg = LLM_CONFIG[backend]
    model = cfg["model"]
    base_url = cfg.get("base_url")
    if api_key:
        os.environ["_PLUS_USER_API_KEY"] = api_key
    else:
        os.environ["_PLUS_USER_API_KEY"] = os.environ.get(cfg["api_key_env"], "")
    _build_loop(backend, cfg["api_key_env"], model, base_url)
    cl.user_session.set("history", [])
    await cl.Message(content=f"✅ 已切换到 `{backend}`（`{model}`）").send()


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


async def _llm_parse_intent(user_text: str, event: dict):
    """Let the LLM parse user intent: confirm, cancel, or modify parameters."""
    import json
    tool_name = event["tool"]
    params = event.get("params", {})
    tool = _loop.registry.get(tool_name)
    props = tool.parameters if tool else {}

    param_lines = []
    for name, pinfo in props.get("properties", {}).items():
        cur = params.get(name, "<not set>")
        ptype = pinfo.get("type", "string")
        desc = pinfo.get("description", "")[:80]
        param_lines.append(f"  {name} ({ptype}): current={cur}  — {desc}")

    prompt = f"""You are a parameter parser. Analyze the user's response to a confirmation prompt.

Tool: "{tool_name}"
Parameters:
{chr(10).join(param_lines)}

User said: "{user_text}"

Return ONLY JSON (no markdown, no explanation):
- Proceed: {{"action":"confirm"}}
- Cancel: {{"action":"cancel","reason":"why"}}
- Modify: {{"action":"modify","changes":{{"param":value}}}}"""

    try:
        response = await asyncio.to_thread(_loop.llm.chat, [{"role": "user", "content": prompt}], [])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("\n```", 1)[0]
        data = json.loads(content)
        action = data.get("action", "confirm")

        if action == "modify":
            changes = data.get("changes", {})
            converted = {}
            for k, v in changes.items():
                pinfo = props.get("properties", {}).get(k, {})
                try:
                    converted[k] = _parse_param_value(str(v), pinfo.get("type", "string"))
                except (ValueError, TypeError):
                    converted[k] = v
            await cl.Message(content="✅ 已更新: " + ", ".join(f"`{k}={v}`" for k, v in converted.items())).send()
            return converted
        elif action == "cancel":
            await cl.Message(content="⏸ 已取消").send()
            return {"cancel": True, "message": f"{user_text}（{data.get('reason', '')}）"}
        else:
            await cl.Message(content="✅ 按当前参数继续。").send()
            return {}
    except Exception as e:
        logger.warning(f"Intent parse failed: {e}, forwarding to LLM")
        await cl.Message(content="🤔 已转发给模型处理").send()
        return {"cancel": True, "message": user_text}


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


# ── Message handler ─────────────────────────────────────────

@cl.on_message
async def on_message(message: cl.Message):
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
            await cl.Message(content=upload_msg).send()
        # Inject upload info into the user message so the LLM sees it
        if new_paths:
            names = ", ".join(os.path.basename(p) for p in new_paths)
            user_msg_text = f"(用户刚刚上传了文件: {names})\n{user_msg_text}"

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

    final_text = ""
    async for event in _loop.run(user_msg_text, history, context_notes):
        if event["type"] == "ask_params":
            tool_name = event["tool"]
            collected = {}
            for pinfo in event["missing"]:
                desc = pinfo["description"] or f"type: {pinfo['type']}"
                hint = ""
                existing = event.get("params", {}).get(pinfo["name"])
                if existing:
                    hint = f"\n(current: `{existing}` — type a new value or press Enter to keep)"
                res = await cl.AskUserMessage(
                    content=f"**`{tool_name}`** needs parameter **`{pinfo['name']}`**\n{desc}{hint}",
                    timeout=600,
                ).send()
                if res and res["output"]:
                    try:
                        collected[pinfo["name"]] = _parse_param_value(res["output"], pinfo["type"])
                    except (ValueError, TypeError):
                        await cl.Message(
                            content=f"⚠️ Invalid value for `{pinfo['name']}` (expected {pinfo['type']}), skipping."
                        ).send()
            await event["queue"].put(collected)

        elif event["type"] == "confirm_params":
            res = await cl.AskUserMessage(content=event["text"], timeout=600).send()
            # Default: cancel if no response (timeout / empty input)
            if not res or not res.get("output") or not res["output"].strip():
                await cl.Message(content="⏸ 超时或空输入，已取消。请重新给出指令。").send()
                await event["queue"].put({"cancel": True, "message": "用户未响应确认提示"})

            raw_output = res["output"].strip()
            raw_lower = raw_output.lower()
            if raw_lower in ("ok", "confirm", "yes", "y"):
                await cl.Message(content="✅ 按当前参数继续。").send()
                await event["queue"].put({})
            elif raw_lower in ("停", "取消", "cancel", "stop"):
                await cl.Message(content="⏸ 已取消").send()
                await event["queue"].put({"cancel": True, "message": raw_output})
            else:
                await cl.Message(content="🤔 ...").send()
                modifications = await _llm_parse_intent(raw_output, event)
                await event["queue"].put(modifications)

        elif event["type"] == "tool_result":
            tr = event["result"]
            async with cl.Step(name=tr["tool"]) as step:
                step.input = str(tr.get("params", {}))
                if tr["success"]:
                    msg = f"✅ {tr.get('message', '')}"
                    if tr.get("output_paths"):
                        msg += "\n\n**Outputs:**\n" + "\n".join(f"- `{p}`" for p in tr["output_paths"])
                    step.output = msg
                    for path in tr.get("output_paths", []):
                        ext = path.lower()
                        if ext.endswith(".tif") or ext.endswith(".tiff"):
                            try:
                                elem = render_raster(path, os.path.basename(path))
                                if elem:
                                    step.elements = [elem]
                            except Exception as e:
                                logger.warning(f"Failed to render raster {path}: {e}")
                        elif ext.endswith(".csv"):
                            elem = render_csv(path)
                            if elem:
                                step.elements = [elem]
                else:
                    step.output = f"❌ **Error:** {tr.get('error', 'Unknown')}"

        elif event["type"] == "text":
            final_text = event["content"]

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

    _maybe_save_paths(message.content)
    if final_text:
        _maybe_save_paths(final_text)


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


def _maybe_save_paths(text: str):
    import re
    drives = r"[A-Za-z]:"
    pattern = rf"({drives}[\\/][^\s,;]+\.(?:tif|tiff|img|dat|shp|csv))"
    for match in re.findall(pattern, text, re.IGNORECASE):
        path = match if isinstance(match, str) else match[0]
        name = os.path.splitext(os.path.basename(path))[0]
        key = f"path_{name}"[:50]
        if not _memory.get_preference(key):
            _memory.set_preference(key, path)
