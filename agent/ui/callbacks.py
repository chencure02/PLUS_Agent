import os
import asyncio
import logging

import chainlit as cl
from chainlit.input_widget import Select, TextInput

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
_registry: ToolRegistry | None = None
_MAX_HISTORY = 20


def _build_loop(backend: str, api_key_env: str, model: str, base_url: str | None = None):
    """Build a ReactLoop with the given LLM config."""
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
    cfg = {"model": model, "api_key_env": "_PLUS_USER_API_KEY"}
    if base_url:
        cfg["base_url"] = base_url
    os.environ.setdefault("_PLUS_USER_API_KEY", os.environ.get(api_key_env, ""))
    llm = create_llm(backend, cfg)
    _loop = ReactLoop(llm, _registry, _memory)


@cl.on_chat_start
async def on_chat_start():
    backend = LLM_BACKEND
    cfg = LLM_CONFIG.get(backend, LLM_CONFIG["claude"])
    _build_loop(backend, cfg["api_key_env"], cfg["model"], cfg.get("base_url"))
    cl.user_session.set("history", [])

    # Settings panel: gear icon in the UI
    await cl.ChatSettings([
        Select(
            id="backend",
            label="模型后端",
            values=["claude", "openai", "deepseek", "qwen"],
            initial_value=backend,
        ),
        TextInput(
            id="api_key",
            label="API Key（留空则使用 .env 配置）",
            initial="",
        ),
    ]).send()

    runs = _memory.get_recent_runs(3)
    paths = _memory.get_frequent_paths()
    welcome = "你好！我是 **PLUS Agent**，基于 PLUS 模型的土地利用模拟助手。\n\n"
    welcome += "右上角齿轮 ⚙ 可切换模型和配置 API Key。\n\n"
    if runs:
        welcome += "### 最近运行\n"
        for r in runs:
            icon = "✅" if r["status"] == "success" else "❌"
            welcome += f"- {icon} **{r['name']}** ({r['created_at'][:10]})\n"
    if paths:
        welcome += f"\n已保存的路径：{', '.join(paths[:3])}\n"
    await cl.Message(content=welcome).send()


@cl.on_settings_update
async def on_settings_update(settings):
    # Chainlit 2.x passes settings as a single dict
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


def _parse_modifications(raw: str, props: dict) -> dict:
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
                    msg = "✅ Using: " + ", ".join(f"`{k}={v}`" for k, v in modifications.items())
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

    history.append({"role": "user", "content": message.content})
    if final_text:
        history.append({"role": "assistant", "content": final_text})
        await cl.Message(content=final_text).send()

    if len(history) > _MAX_HISTORY:
        history = history[-_MAX_HISTORY:]
    cl.user_session.set("history", history)

    _maybe_save_paths(message.content)
    if final_text:
        _maybe_save_paths(final_text)


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
