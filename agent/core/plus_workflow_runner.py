from __future__ import annotations

from typing import Any

from agent.core.default_parameter_agent import DefaultParameterAgent
from agent.core.parameter_provider import format_confirmation, parse_user_overrides
from agent.core.workflow_state import (
    WORKFLOW_STEPS,
    ParameterProposal,
    WorkflowContext,
    WorkflowState,
)
from agent.tools.registry import ToolRegistry


class PLUSWorkflowRunner:
    def __init__(self, registry: ToolRegistry, parameter_provider=None):
        self.registry = registry
        self.parameter_provider = parameter_provider or DefaultParameterAgent()

    def start(self, thread_id: str, context: WorkflowContext) -> WorkflowState:
        state = WorkflowState(thread_id=thread_id)
        state.requested_target_year = _extract_requested_target_year(context.user_message)
        state.status = "collecting"
        state.touch()
        return state

    def prepare_next(self, state: WorkflowState, context: WorkflowContext) -> dict[str, Any]:
        if state.status in {"completed", "cancelled"}:
            return {
                "type": "workflow_text",
                "content": _status_text(state),
                "state": state,
            }

        if state.current_step not in WORKFLOW_STEPS:
            state.status = "completed"
            state.touch()
            return {
                "type": "workflow_completed",
                "content": "PLUS 标准模拟工作流已完成。",
                "state": state,
            }

        step = state.steps[state.current_step]
        if state.status in {"waiting_confirmation", "collecting"} and step.params:
            proposal = ParameterProposal(
                step=state.current_step,
                params=dict(step.params),
                missing_fields=list(step.missing_fields),
                assumptions=list(step.assumptions),
                warnings=list(step.warnings),
            )
        else:
            proposal = self.parameter_provider.propose(state.current_step, state, context)
            step.params = dict(proposal.params)
            step.missing_fields = list(proposal.missing_fields)
            step.assumptions = list(proposal.assumptions)
            step.warnings = list(proposal.warnings)

        if proposal.missing_fields:
            state.status = "collecting"
            step.status = "pending"
            state.touch()
            return {
                "type": "workflow_collect",
                "step": state.current_step,
                "proposal": proposal,
                "text": _missing_text(proposal),
                "state": state,
            }

        state.status = "waiting_confirmation"
        step.status = "waiting_confirmation"
        state.touch()
        return {
            "type": "workflow_confirm",
            "step": state.current_step,
            "proposal": proposal,
            "text": format_confirmation(proposal),
            "state": state,
        }

    def apply_user_reply(self, state: WorkflowState, reply: str) -> dict[str, Any]:
        raw = (reply or "").strip()
        lowered = raw.lower()
        step = state.steps[state.current_step]

        if lowered in {"cancel", "stop", "取消", "停"}:
            state.status = "cancelled"
            step.status = "skipped"
            state.touch()
            return {
                "type": "workflow_cancelled",
                "content": "已取消当前 PLUS 工作流。",
                "state": state,
            }

        if lowered in {"ok", "yes", "y", "confirm", "确认", "继续"}:
            if step.missing_fields:
                return {
                    "type": "workflow_invalid_reply",
                    "content": "当前步骤仍缺少参数：" + ", ".join(step.missing_fields),
                    "state": state,
                }
            state.status = "running"
            step.status = "running"
            state.touch()
            return {
                "type": "workflow_ready",
                "step": state.current_step,
                "params": dict(step.params),
                "state": state,
            }

        overrides = parse_user_overrides(raw)
        if not overrides:
            return {
                "type": "workflow_invalid_reply",
                "content": "没有识别到参数修改。请回复 ok、cancel，或使用 参数=新值。",
                "state": state,
            }

        step.params.update(overrides)
        step.missing_fields = [
            name for name in step.missing_fields
            if step.params.get(name) in ("", None, [])
        ]
        proposal = ParameterProposal(
            step=state.current_step,
            params=dict(step.params),
            missing_fields=list(step.missing_fields),
            assumptions=list(step.assumptions),
            warnings=list(step.warnings),
        )
        state.status = "collecting" if step.missing_fields else "waiting_confirmation"
        step.status = "pending" if step.missing_fields else "waiting_confirmation"
        state.touch()
        return {
            "type": "workflow_collect" if step.missing_fields else "workflow_confirm",
            "step": state.current_step,
            "proposal": proposal,
            "text": _missing_text(proposal) if step.missing_fields else format_confirmation(proposal),
            "state": state,
        }

    def execute_current_step(self, state: WorkflowState) -> dict[str, Any]:
        step = state.steps[state.current_step]
        tool_name = step.name
        _ensure_output_dirs(step.params)
        result = self.registry.execute(tool_name, dict(step.params))

        if not result.success:
            step.status = "failed"
            step.error = result.error
            state.status = "failed"
            state.touch()
            return {
                "type": "workflow_tool_result",
                "step": tool_name,
                "success": False,
                "result": result,
                "state": state,
            }

        step.status = "success"
        step.output_paths = list(result.output_paths)
        step.artifacts = dict(result.artifacts)
        state.artifacts.update(result.artifacts)
        _record_step_fallback_artifacts(state, tool_name, result.output_paths)
        state.current_step = _next_step(tool_name)
        state.status = "completed" if state.current_step not in WORKFLOW_STEPS else "collecting"
        state.touch()
        return {
            "type": "workflow_tool_result",
            "step": tool_name,
            "success": True,
            "result": result,
            "state": state,
        }


def _missing_text(proposal: ParameterProposal) -> str:
    lines = [f"`{proposal.step}` 还缺少以下参数："]
    lines.extend(f"- {field}" for field in proposal.missing_fields)
    lines.extend(["", "请回复 参数=值；多个参数可用逗号分隔。回复 cancel 可取消工作流。"])
    return "\n".join(lines)


def _status_text(state: WorkflowState) -> str:
    if state.status == "completed":
        return "PLUS 标准模拟工作流已完成。"
    if state.status == "cancelled":
        return "当前 PLUS 工作流已取消。"
    return f"当前 PLUS 工作流状态：{state.status}，当前步骤：{state.current_step}。"


def _next_step(current: str) -> str:
    try:
        idx = WORKFLOW_STEPS.index(current)
    except ValueError:
        return ""
    next_idx = idx + 1
    if next_idx >= len(WORKFLOW_STEPS):
        return ""
    return WORKFLOW_STEPS[next_idx]


def _record_step_fallback_artifacts(
    state: WorkflowState,
    tool_name: str,
    output_paths: list[str],
) -> None:
    if tool_name == "convert" and output_paths:
        state.artifacts.setdefault("converted_lulc_paths", list(output_paths))
        state.artifacts.setdefault("early_lulc", output_paths[0])
        state.artifacts.setdefault("late_lulc", output_paths[-1])
    elif tool_name == "expansion" and output_paths:
        state.artifacts.setdefault("expansion_raster", output_paths[0])
    elif tool_name == "cars" and output_paths:
        state.artifacts.setdefault("simulation_raster", output_paths[0])


def _extract_requested_target_year(message: str) -> int | None:
    import re

    years = [int(year) for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", message or "")]
    if len(years) == 1 or len(years) >= 3:
        return max(years)
    return None


def _ensure_output_dirs(params: dict[str, Any]) -> None:
    from pathlib import Path

    for key, value in params.items():
        if key == "output_dir" and isinstance(value, str) and value:
            Path(value).mkdir(parents=True, exist_ok=True)
        elif key.startswith("output") and isinstance(value, str) and value:
            Path(value).parent.mkdir(parents=True, exist_ok=True)
        elif key.startswith("output") and isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item:
                    Path(item).parent.mkdir(parents=True, exist_ok=True)
