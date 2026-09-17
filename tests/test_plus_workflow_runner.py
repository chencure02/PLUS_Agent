import unittest
import tempfile
from pathlib import Path

from agent.core.default_parameter_agent import DefaultParameterAgent
from agent.core.plus_workflow_runner import PLUSWorkflowRunner
from agent.core.workflow_state import WorkflowContext, WorkflowState
from agent.tools.base import BaseTool, ToolResult
from agent.tools.registry import ToolRegistry


class FakeTool(BaseTool):
    name = "fake"
    description = "fake"
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name, output_paths=None, artifacts=None):
        self.name = name
        self._output_paths = output_paths or [f"C:/out/{name}.tif"]
        self._artifacts = artifacts or {}

    def execute(self, params):
        return ToolResult(
            success=True,
            message=f"{self.name} ok",
            output_paths=list(self._output_paths),
            artifacts=dict(self._artifacts),
        )


class AssertingConvertTool(FakeTool):
    def __init__(self):
        super().__init__("convert")

    def execute(self, params):
        for output_path in params["output_paths"]:
            if not Path(output_path).parent.exists():
                return ToolResult(success=False, error=f"missing parent: {output_path}")
        return ToolResult(
            success=True,
            message="convert ok",
            output_paths=list(params["output_paths"]),
            artifacts={"converted_lulc_paths": list(params["output_paths"])},
        )


class PLUSWorkflowRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.output_dir = str(Path(self.tmpdir.name) / "out")

    def _registry(self):
        registry = ToolRegistry()
        registry.register(FakeTool(
            "convert",
            output_paths=[
                "C:/out/convert/wh2003_refy_converted.tif",
                "C:/out/convert/wh2013_refy_converted.tif",
            ],
            artifacts={
                "converted_lulc_paths": [
                    "C:/out/convert/wh2003_refy_converted.tif",
                    "C:/out/convert/wh2013_refy_converted.tif",
                ],
                "early_lulc": "C:/out/convert/wh2003_refy_converted.tif",
                "late_lulc": "C:/out/convert/wh2013_refy_converted.tif",
            },
        ))
        registry.register(FakeTool(
            "expansion",
            output_paths=["C:/out/expansion/expansion_landuse_1to2.tif"],
            artifacts={"expansion_raster": "C:/out/expansion/expansion_landuse_1to2.tif"},
        ))
        return registry

    def _full_registry(self):
        registry = self._registry()
        registry.register(FakeTool(
            "leas",
            output_paths=[
                "C:/out/leas/potential_band_1.tif",
                "C:/out/leas/potential_band_2.tif",
            ],
            artifacts={
                "probability_paths": [
                    "C:/out/leas/potential_band_1.tif",
                    "C:/out/leas/potential_band_2.tif",
                ],
            },
        ))
        registry.register(FakeTool(
            "markov",
            output_paths=["C:/out/markov/markov.csv"],
            artifacts={"markov_csv": "C:/out/markov/markov.csv", "yearly_demands": "1,100,200"},
        ))
        registry.register(FakeTool(
            "neighborhood_weight",
            output_paths=[],
            artifacts={"neighborhood_weights": "0.3,0.7"},
        ))
        registry.register(FakeTool(
            "cars",
            output_paths=["C:/out/cars/simulationSimulation_1.tif"],
            artifacts={"simulation_raster": "C:/out/cars/simulationSimulation_1.tif"},
        ))
        return registry

    def _context(self):
        return WorkflowContext(
            thread_id="thread-a",
            user_message="请基于2003和2013土地利用预测2033年",
            lulc_files=["C:/data/wh2013_refy.tif", "C:/data/wh2003_refy.tif"],
            driver_files=["C:/data/drivers/dem.tif"],
            output_dir=self.output_dir,
            drivers_dir="C:/data/drivers",
        )

    def test_confirms_executes_and_advances_from_convert_to_expansion(self):
        runner = PLUSWorkflowRunner(self._registry(), DefaultParameterAgent())
        state = runner.start("thread-a", self._context())

        event = runner.prepare_next(state, self._context())
        self.assertEqual(event["type"], "workflow_confirm")
        self.assertEqual(event["step"], "convert")

        ready = runner.apply_user_reply(state, "ok")
        self.assertEqual(ready["type"], "workflow_ready")

        result = runner.execute_current_step(state)
        self.assertEqual(result["type"], "workflow_tool_result")
        self.assertEqual(state.steps["convert"].status, "success")
        self.assertEqual(state.current_step, "expansion")
        self.assertIn("converted_lulc_paths", state.artifacts)

        next_event = runner.prepare_next(state, self._context())
        self.assertEqual(next_event["type"], "workflow_confirm")
        self.assertEqual(next_event["step"], "expansion")

    def test_cars_is_blocked_until_required_artifacts_exist(self):
        runner = PLUSWorkflowRunner(self._registry(), DefaultParameterAgent())
        state = WorkflowState(thread_id="thread-a", current_step="cars")
        state.artifacts.update({
            "late_lulc": "C:/out/convert/wh2013_refy_converted.tif",
            "probability_paths": ["C:/out/leas/potential_band_1.tif"],
        })

        event = runner.prepare_next(state, self._context())

        self.assertEqual(event["type"], "workflow_collect")
        self.assertEqual(event["step"], "cars")
        self.assertIn("yearly_demands", event["proposal"].missing_fields)
        self.assertIn("neighborhood_weights", event["proposal"].missing_fields)

        reply = runner.apply_user_reply(state, "ok")
        self.assertEqual(reply["type"], "workflow_invalid_reply")
        self.assertIn("缺少参数", reply["content"])

    def test_prepare_next_preserves_existing_waiting_confirmation_params(self):
        runner = PLUSWorkflowRunner(self._registry(), DefaultParameterAgent())
        state = runner.start("thread-a", self._context())
        runner.prepare_next(state, self._context())
        action = runner.apply_user_reply(
            state,
            "output_paths=C:/custom/early.tif|C:/custom/late.tif",
        )
        self.assertEqual(action["type"], "workflow_confirm")

        resumed = runner.prepare_next(state, self._context())

        self.assertEqual(resumed["proposal"].params["output_paths"], [
            "C:/custom/early.tif",
            "C:/custom/late.tif",
        ])

    def test_start_does_not_save_two_historical_years_as_target_year(self):
        runner = PLUSWorkflowRunner(self._registry(), DefaultParameterAgent())
        context = WorkflowContext(
            thread_id="thread-a",
            user_message="请用2003和2013土地利用数据进行模拟",
            lulc_files=["C:/data/wh2003_refy.tif", "C:/data/wh2013_refy.tif"],
            output_dir=self.output_dir,
        )

        state = runner.start("thread-a", context)

        self.assertIsNone(state.requested_target_year)

    def test_full_fake_workflow_reaches_completed_with_structured_artifacts(self):
        runner = PLUSWorkflowRunner(self._full_registry(), DefaultParameterAgent())
        state = runner.start("thread-a", self._context())
        seen_steps = []

        while state.status != "completed":
            event = runner.prepare_next(state, self._context())
            self.assertEqual(event["type"], "workflow_confirm")
            seen_steps.append(event["step"])
            ready = runner.apply_user_reply(state, "ok")
            self.assertEqual(ready["type"], "workflow_ready")
            result = runner.execute_current_step(state)
            self.assertTrue(result["success"], result["result"].error)

        self.assertEqual(seen_steps, [
            "convert",
            "expansion",
            "leas",
            "markov",
            "neighborhood_weight",
            "cars",
        ])
        self.assertEqual(state.artifacts["yearly_demands"], "1,100,200")
        self.assertEqual(state.artifacts["neighborhood_weights"], "0.3,0.7")
        self.assertEqual(state.artifacts["simulation_raster"], "C:/out/cars/simulationSimulation_1.tif")

    def test_execute_current_step_creates_parent_dirs_for_output_path_lists(self):
        registry = ToolRegistry()
        registry.register(AssertingConvertTool())
        runner = PLUSWorkflowRunner(registry, DefaultParameterAgent())
        state = runner.start("thread-a", self._context())
        runner.prepare_next(state, self._context())
        runner.apply_user_reply(state, "ok")

        result = runner.execute_current_step(state)

        self.assertTrue(result["success"], result["result"].error)


if __name__ == "__main__":
    unittest.main()
