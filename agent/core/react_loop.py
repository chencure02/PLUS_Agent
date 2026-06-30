import asyncio
import json
import logging
import uuid

from agent.config import SYSTEM_PROMPT, MAX_REACT_STEPS
from agent.llm.adapter import BaseLLM
from agent.tools.registry import ToolRegistry
from agent.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Sentinel for cancellation — shared with callbacks.py
CANCEL = object()

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
    lines = [f"**{tool_name}** — 执行前确认参数：\n"]
    for name, pinfo in props.get("properties", {}).items():
        if name in _IMMUTABLE_PARAMS:
            continue
        val = user_params.get(name)
        has_default = "default" in pinfo
        using_default = has_default and val == pinfo.get("default")
        # Format value display
        if val in (None, "", []):
            display_val = "`<未设置>`"
        else:
            display_val = f"`{val}`"
        # Mark default values
        default_mark = " （默认）" if using_default else ""
        lines.append(f"- **{name}** = {display_val}{default_mark}")
    lines.append("\n回复 **ok** 继续执行，或输入 `参数=新值, ...` 修改")
    return "\n".join(lines)


class ReactLoop:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry, memory: MemoryStore):
        self.llm = llm
        self.registry = registry
        self.memory = memory

    async def run(self, user_message: str, history: list[dict], context_notes: list[str] | None = None):
        """Async generator that yields events."""
        # Build system prompt with pinned context facts
        system_content = SYSTEM_PROMPT
        if context_notes:
            system_content += "\n\n## 会话上下文（已记住的关键信息，优先参考）\n"
            for i, note in enumerate(context_notes, 1):
                system_content += f"{i}. {note}\n"

        messages = [
            {"role": "system", "content": system_content},
            *history,
            {"role": "user", "content": user_message},
        ]
        tools = self.registry.get_all_llm_format()

        # Persist this run to memory
        run_name = user_message[:80] + ("..." if len(user_message) > 80 else "")
        run_id = self.memory.save_run(run_name, [], {}, [])
        tool_step = 0

        for step_idx in range(MAX_REACT_STEPS):
            logger.info(f"ReAct step {step_idx + 1}: calling LLM...")
            response = await asyncio.to_thread(self.llm.chat, messages, tools)
            logger.info(f"ReAct step {step_idx + 1}: LLM response type={response.type}")

            if response.type == "text":
                self.memory.update_run_status(run_id, "success")
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
                        if isinstance(answers, dict) and answers.get("cancel"):
                            messages.append({"role": "user", "content": answers["message"]})
                            continue
                        tool_args.update(answers)

                    # Step 2: confirm params (skip for tools with confirm_before_execute=False)
                    if getattr(tool, "confirm_before_execute", True):
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
                        if isinstance(modifications, dict) and modifications.get("cancel"):
                            messages.append({"role": "user", "content": modifications["message"]})
                            continue
                        if modifications:
                            tool_args.update(modifications)

                    # Step 3: execute
                    logger.info(f"Executing tool: {tool_name} ...")
                    tool_step += 1
                    self.memory.save_step(run_id, tool_name, tool_step, tool_args)
                    self.memory.update_step_status(run_id, tool_step, "running")
                    result = await asyncio.to_thread(
                        self.registry.execute, tool_name, tool_args
                    )
                    if result.success:
                        self.memory.update_step_status(run_id, tool_step, "success")
                    else:
                        self.memory.update_step_status(run_id, tool_step, "failed", result.error)
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
                    assistant_msg = {
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
                    }
                    if response.reasoning_content:
                        assistant_msg["reasoning_content"] = response.reasoning_content
                    messages.append(assistant_msg)
                    messages.append({
                        "role": "tool",
                        "content": obs,
                        "tool_call_id": call_id,
                    })
                continue

        self.memory.update_run_status(run_id, "failed", f"Reached max steps ({MAX_REACT_STEPS})")
        yield {"type": "text", "content": f"Reached max steps ({MAX_REACT_STEPS})."}
