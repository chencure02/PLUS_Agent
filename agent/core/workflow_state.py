from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid


WORKFLOW_STEPS = [
    "convert",
    "expansion",
    "leas",
    "markov",
    "neighborhood_weight",
    "cars",
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class WorkflowContext:
    thread_id: str
    user_message: str = ""
    lulc_files: list[str] = field(default_factory=list)
    driver_files: list[str] = field(default_factory=list)
    constraint_files: list[str] = field(default_factory=list)
    output_dir: str = ""
    drivers_dir: str = ""
    constraints_dir: str = ""


@dataclass
class ParameterProposal:
    step: str
    params: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class WorkflowStepState:
    name: str
    status: str = "pending"
    params: dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStepState":
        return cls(
            name=str(data.get("name", "")),
            status=str(data.get("status", "pending")),
            params=dict(data.get("params") or {}),
            missing_fields=list(data.get("missing_fields") or []),
            assumptions=list(data.get("assumptions") or []),
            warnings=list(data.get("warnings") or []),
            output_paths=list(data.get("output_paths") or []),
            artifacts=dict(data.get("artifacts") or {}),
            error=str(data.get("error", "")),
        )


@dataclass
class WorkflowState:
    thread_id: str
    workflow_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "collecting"
    current_step: str = "convert"
    requested_target_year: int | None = None
    steps: dict[str, WorkflowStepState] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        for name in WORKFLOW_STEPS:
            self.steps.setdefault(name, WorkflowStepState(name=name))

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = {name: asdict(step) for name, step in self.steps.items()}
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowState":
        steps = {
            name: WorkflowStepState.from_dict(step)
            for name, step in dict(data.get("steps") or {}).items()
        }
        return cls(
            workflow_id=str(data.get("workflow_id") or uuid.uuid4().hex),
            thread_id=str(data.get("thread_id") or ""),
            status=str(data.get("status") or "collecting"),
            current_step=str(data.get("current_step") or "convert"),
            requested_target_year=data.get("requested_target_year"),
            steps=steps,
            artifacts=dict(data.get("artifacts") or {}),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )
