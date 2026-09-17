from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import re

from agent.core.workflow_state import ParameterProposal, WorkflowContext, WorkflowState


class ParameterProvider(ABC):
    @abstractmethod
    def propose(
        self,
        step_name: str,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        ...

    def revise(
        self,
        step_name: str,
        proposal: ParameterProposal,
        user_overrides: dict[str, Any],
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        merged = dict(proposal.params)
        merged.update(user_overrides)
        return ParameterProposal(
            step=step_name,
            params=merged,
            missing_fields=[
                field for field in proposal.missing_fields
                if field not in user_overrides or user_overrides[field] in ("", None, [])
            ],
            assumptions=list(proposal.assumptions),
            warnings=list(proposal.warnings),
        )


def parse_user_overrides(text: str) -> dict[str, Any]:
    """Parse `key=value` edits from a confirmation reply."""
    chunks = re.split(r",\s*(?=[A-Za-z_][A-Za-z0-9_]*\s*=)", text.strip())
    overrides: dict[str, Any] = {}
    for chunk in chunks:
        if not chunk.strip() or "=" not in chunk:
            continue
        key, raw_value = chunk.split("=", 1)
        key = key.strip()
        if not key:
            continue
        overrides[key] = _coerce_value(raw_value.strip())
    return overrides


def format_confirmation(proposal: ParameterProposal) -> str:
    lines = [f"即将执行：{proposal.step}", "", "参数:"]
    if proposal.params:
        for key, value in proposal.params.items():
            lines.append(f"- {key} = `{_format_value(value)}`")
    else:
        lines.append("- `<无>`")

    if proposal.missing_fields:
        lines.extend(["", "缺失参数:"])
        lines.extend(f"- {field}" for field in proposal.missing_fields)

    if proposal.assumptions:
        lines.extend(["", "假设:"])
        lines.extend(f"- {item}" for item in proposal.assumptions)

    if proposal.warnings:
        lines.extend(["", "警告:"])
        lines.extend(f"- {item}" for item in proposal.warnings)

    lines.extend([
        "",
        "回复 ok 执行。",
        "回复 参数=新值 修改，例如 predict_year=2035。",
        "多个列表值可用 | 分隔，例如 probability_paths=a.tif|b.tif。",
        "回复 cancel 取消工作流。",
    ])
    return "\n".join(lines)


def _coerce_value(raw: str) -> Any:
    if "|" in raw:
        return [item.strip() for item in raw.split("|") if item.strip()]
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"[-+]?\d+", raw):
        return int(raw)
    if re.fullmatch(r"[-+]?\d+\.\d+", raw):
        return float(raw)
    return raw


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(str(item) for item in value)
    return str(value)
