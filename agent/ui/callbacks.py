import os
import asyncio
import logging

import chainlit as cl

from agent.config import LLM_BACKEND, LLM_CONFIG
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
from agent.memory import MemoryStore
from agent.core.react_loop import ReactLoop
from agent.ui.renderers import render_raster, render_csv

logger = logging.getLogger(__name__)

_loop: ReactLoop | None = None
_memory: MemoryStore | None = None
_MAX_HISTORY = 20  # max messages to keep in conversation history


def _init():
    global _loop, _memory
    if _loop is not None:
        return
    db_path = os.environ.get("PLUS_MEMORY_DB", "data/memory.db")
    _memory = MemoryStore(db_path)
    registry = ToolRegistry()
    registry.register(ConvertTool())
    registry.register(ExpansionTool())
    registry.register(LEASTool())
    registry.register(MarkovTool())
    registry.register(LinearTool())
    registry.register(CARSTool())
    registry.register(ValidationTool())
    registry.register(DiverseTool())
    cfg = LLM_CONFIG.get(LLM_BACKEND, LLM_CONFIG["claude"])
    llm = create_llm(LLM_BACKEND, cfg)
    _loop = ReactLoop(llm, registry, _memory)


@cl.on_chat_start
async def on_chat_start():
    _init()
    # Initialize per-session conversation history
    cl.user_session.set("history", [])

    runs = _memory.get_recent_runs(3)
    paths = _memory.get_frequent_paths()
    welcome = "Hello! I'm **PLUS Agent**, your land use simulation assistant.\n\n"
    if runs:
        welcome += "### Recent Runs\n"
        for r in runs:
            icon = "✅" if r["status"] == "success" else "❌"
            welcome += f"- {icon} **{r['name']}** ({r['created_at'][:10]})\n"
    if paths:
        welcome += f"\n**Saved paths:** {', '.join(paths[:3])}\n"
    welcome += f"\nLLM backend: `{LLM_BACKEND}`"
    await cl.Message(content=welcome).send()


def _parse_param_value(raw: str, param_type: str):
    """Convert user text input to the expected parameter type."""
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


def _parse_modifications(raw: str, props: dict) -> dict:
    """Parse user modifications like 'n_trees=50, sampling_rate=0.02'.
    Returns dict of {param: value} or empty dict for 'ok'."""
    raw = raw.strip().lower()
    if raw in ("ok", "confirm", "yes", "y", ""):
        return {}
    result = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip()
        val = val.strip()
        pinfo = props.get("properties", {}).get(key, {})
        param_type = pinfo.get("type", "string")
        try:
            result[key] = _parse_param_value(val, param_type)
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse {key}={val} as {param_type}")
    return result


@cl.on_message
async def on_message(message: cl.Message):
    _init()

    # Retrieve conversation history from this session
    history = cl.user_session.get("history", [])

    final_text = ""
    async for event in _loop.run(message.content, history):
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
            res = await cl.AskUserMessage(
                content=event["text"],
                timeout=600,
            ).send()
            modifications = {}
            if res and res["output"]:
                tool = _loop.registry.get(event["tool"])
                props = tool.parameters if tool else {}
                modifications = _parse_modifications(res["output"], props)
                if modifications:
                    msg = "✅ Using: " + ", ".join(
                        f"`{k}={v}`" for k, v in modifications.items()
                    )
                else:
                    msg = "✅ Proceeding with current parameters."
                await cl.Message(content=msg).send()
            await event["queue"].put(modifications)

        elif event["type"] == "tool_result":
            tr = event["result"]
            async with cl.Step(name=tr["tool"]) as step:
                step.input = str(tr.get("params", {}))
                if tr["success"]:
                    msg = f"✅ {tr.get('message', '')}"
                    if tr.get("output_paths"):
                        msg += "\n\n**Outputs:**\n" + "\n".join(
                            f"- `{p}`" for p in tr["output_paths"]
                        )
                    step.output = msg
                    for path in tr.get("output_paths", []):
                        ext = path.lower()
                        if ext.endswith(".tif") or ext.endswith(".tiff"):
                            try:
                                elem = await asyncio.to_thread(
                                    render_raster, path, os.path.basename(path)
                                )
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

    # Save this turn to conversation history
    history.append({"role": "user", "content": message.content})
    if final_text:
        history.append({"role": "assistant", "content": final_text})
        await cl.Message(content=final_text).send()

    # Trim history to avoid context overflow
    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    cl.user_session.set("history", history)

    # Remember paths the user mentioned
    _maybe_save_paths(message.content)
    if final_text:
        _maybe_save_paths(final_text)


def _maybe_save_paths(text: str):
    """Auto-detect and save file paths the user mentions."""
    import re
    drives = r"[A-Za-z]:"
    pattern = rf"({drives}[\\/][^\s,;]+\.(?:tif|tiff|img|dat|shp|csv))"
    for match in re.findall(pattern, text, re.IGNORECASE):
        path = match if isinstance(match, str) else match[0]
        name = os.path.splitext(os.path.basename(path))[0]
        key = f"path_{name}"[:50]
        if not _memory.get_preference(key):
            _memory.set_preference(key, path)
