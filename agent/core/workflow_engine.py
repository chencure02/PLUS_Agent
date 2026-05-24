from dataclasses import dataclass, field
from agent.tools.registry import ToolRegistry
from agent.memory.store import MemoryStore


@dataclass
class WorkflowStep:
    tool_name: str
    params: dict


@dataclass
class WorkflowResult:
    success: bool
    steps: list[dict] = field(default_factory=list)
    final_outputs: list[str] = field(default_factory=list)
    error: str = ""
    error_step: str = ""


class WorkflowEngine:
    def __init__(self, registry: ToolRegistry, memory: MemoryStore):
        self.registry = registry
        self.memory = memory

    def execute(self, name: str, steps: list[WorkflowStep]) -> WorkflowResult:
        """Execute sequential tool calls. Stops on first failure. Saves to memory."""
        tool_names = [s.tool_name for s in steps]
        all_params = {s.tool_name: s.params for s in steps}
        all_outputs: list[str] = []

        run_id = self.memory.save_run(name, tool_names, all_params, [])

        for i, step in enumerate(steps):
            self.memory.save_step(run_id, step.tool_name, i, step.params)
            self.memory.update_step_status(run_id, i, "running")
            result = self.registry.execute(step.tool_name, step.params)

            if result.success:
                self.memory.update_step_status(run_id, i, "success")
                all_outputs.extend(result.output_paths)
            else:
                self.memory.update_step_status(run_id, i, "failed", result.error)
                self.memory.update_run_status(run_id, "failed", result.error)
                return WorkflowResult(
                    success=False,
                    steps=[{"tool": s.tool_name, "status": "failed", "error": result.error} for s in steps[:i+1]],
                    error=result.error, error_step=step.tool_name,
                )

        self.memory.update_run_status(run_id, "success")
        return WorkflowResult(
            success=True,
            steps=[{"tool": s.tool_name, "status": "success"} for s in steps],
            final_outputs=all_outputs,
        )

    @staticmethod
    def build_standard(convert: dict, expansion: dict, leas: dict, markov: dict, cars: dict) -> list[WorkflowStep]:
        """Build the standard 5-step workflow: convert -> expansion -> leas -> markov -> cars."""
        return [
            WorkflowStep("convert", convert),
            WorkflowStep("expansion", expansion),
            WorkflowStep("leas", leas),
            WorkflowStep("markov", markov),
            WorkflowStep("cars", cars),
        ]
