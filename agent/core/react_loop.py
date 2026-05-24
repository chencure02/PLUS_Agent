import asyncio
import json
import logging
import uuid

from agent.config import SYSTEM_PROMPT, MAX_REACT_STEPS
from agent.llm.adapter import BaseLLM
from agent.tools.registry import ToolRegistry
from agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Parameters that are hardcoded per CLAUDE.md "任何时候都不做改动"
# These are never shown to the user and never configurable
_IMMUTABLE_PARAMS = {
    "is_net_exit", "is_balance", "high_precision",
    "update_number", "update_variable",
    "how_many_years",
    "development_type_exist", "development_type", "development_weight",
}


def _build_confirm_text(tool_name: str, props: dict, user_params: dict) -> str:
    """Build a readable parameter summary for user confirmation."""
    required = props.get("required", [])
    lines = [f"**{tool_name}** — review parameters before execution:\n"]
    for name, pinfo in props.get("properties", {}).items():
        if name in _IMMUTABLE_PARAMS:
            continue
        val = user_params.get(name)
        is_required = name in required
        has_default = "default" in pinfo
        marker = "[required]" if is_required else "[optional]"
        # Indicate source: user-specified or using default
        source = " (default)" if (has_default and val == pinfo.get("default")) else ""
        display_val = f"`{val}`" if val not in (None, "", []) else "`<not set>`"
        lines.append(f"- {marker} **{name}**: {display_val}{source}  — {pinfo.get('description', '')[:80]}")
    lines.append("\nReply **ok** to proceed, or specify changes like `param=value, ...`")
    return "\n".join(lines)


class ReactLoop:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry, memory: MemoryStore):
        self.llm = llm
        self.registry = registry
        self.memory = memory

    async def run(self, user_message: str, history: list[dict]):
        """Async generator that yields events:
        {'type':'tool_result', 'result':{...}}       — tool executed
        {'type':'ask_params', 'tool':..., ...}        — need required params from user
        {'type':'confirm_params', 'tool':..., ...}    — confirm/modify all params before execution
        {'type':'text', 'content':...}                — final text response
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]
        tools = self.registry.get_all_llm_format()

        for step_idx in range(MAX_REACT_STEPS):
            logger.info(f"ReAct step {step_idx + 1}: calling LLM...")
            response = await asyncio.to_thread(self.llm.chat, messages, tools)
            logger.info(f"ReAct step {step_idx + 1}: LLM response type={response.type}")

            if response.type == "text":
                yield {"type": "text", "content": response.content}
                return

            if response.type == "tool_call":
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = dict(tc["arguments"])

                    tool = self.registry.get(tool_name)
                    if tool is None:
                        logger.warning(f"Unknown tool: {tool_name}, skipping")
                        continue

                    props = tool.parameters
                    required = props.get("required", [])

                    # Step 1: collect missing REQUIRED params
                    missing = []
                    for p in required:
                        val = tool_args.get(p)
                        if val is None or val == "" or val == []:
                            missing.append({
                                "name": p,
                                "type": props.get("properties", {}).get(p, {}).get("type", "string"),
                                "description": props.get("properties", {}).get(p, {}).get("description", ""),
                            })

                    if missing:
                        queue: asyncio.Queue = asyncio.Queue()
                        yield {
                            "type": "ask_params",
                            "tool": tool_name,
                            "missing": missing,
                            "params": tool_args,
                            "queue": queue,
                        }
                        answers = await queue.get()
                        tool_args.update(answers)

                    # Step 2: confirm ALL configurable params (including defaults)
                    # Build a set of all configurable params
                    all_configurable = {
                        k for k in props.get("properties", {})
                        if k not in _IMMUTABLE_PARAMS
                    }
                    # Merge defaults that the LLM didn't set
                    for name, pinfo in props.get("properties", {}).items():
                        if name in _IMMUTABLE_PARAMS:
                            continue
                        if tool_args.get(name) in (None, "", []):
                            default = pinfo.get("default")
                            if default is not None:
                                tool_args[name] = default

                    confirm_queue: asyncio.Queue = asyncio.Queue()
                    confirm_text = _build_confirm_text(tool_name, props, tool_args)
                    yield {
                        "type": "confirm_params",
                        "tool": tool_name,
                        "text": confirm_text,
                        "params": dict(tool_args),
                        "queue": confirm_queue,
                    }
                    modifications = await confirm_queue.get()
                    if modifications:
                        tool_args.update(modifications)

                    # Step 3: execute
                    logger.info(f"Executing tool: {tool_name} ...")
                    result = await asyncio.to_thread(
                        self.registry.execute, tool_name, tool_args
                    )
                    logger.info(f"Tool {tool_name} done: success={result.success}")
                    tr = {
                        "tool": tool_name, "params": tool_args,
                        "success": result.success, "message": result.message,
                        "output_paths": result.output_paths, "error": result.error,
                    }
                    yield {"type": "tool_result", "result": tr}

                    obs = (
                        f"Tool '{tool_name}' executed.\n"
                        f"Success: {result.success}\n"
                        f"Message: {result.message}\n"
                    )
                    if result.output_paths:
                        obs += f"Output files: {', '.join(result.output_paths)}\n"
                    if result.error:
                        obs += f"Error: {result.error}\n"

                    call_id = f"call_{uuid.uuid4().hex[:12]}"
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args, ensure_ascii=False),
                            }
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "content": obs,
                        "tool_call_id": call_id,
                    })
                continue

        yield {"type": "text", "content": f"Reached max steps ({MAX_REACT_STEPS})."}
