import importlib.util
import unittest
from pathlib import Path


def load_eval_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_agent_system.py"
    spec = importlib.util.spec_from_file_location("evaluate_agent_system", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentEvaluationTests(unittest.TestCase):
    def test_static_evaluation_exposes_core_agent_metrics(self):
        module = load_eval_module()

        report = module.run_evaluation(run_commands=False, write_files=False)

        expected = {
            "tool_coverage",
            "workflow_routing",
            "mock_workflow",
            "memory_isolation",
            "frontend_data_panel",
        }
        self.assertTrue(expected.issubset(report["metrics"]))
        self.assertGreaterEqual(report["overall_score"], 80.0)

    def test_router_evaluation_counts_expected_positive_and_negative_cases(self):
        module = load_eval_module()

        metric = module.evaluate_workflow_routing()

        self.assertEqual(metric["passed"], metric["total"])
        self.assertGreaterEqual(metric["positive_cases"], 4)
        self.assertGreaterEqual(metric["negative_cases"], 4)


if __name__ == "__main__":
    unittest.main()
