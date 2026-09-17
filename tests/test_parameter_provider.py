import unittest

from agent.core.parameter_provider import format_confirmation, parse_user_overrides
from agent.core.workflow_state import ParameterProposal


class ParameterProviderTests(unittest.TestCase):
    def test_parse_user_overrides_converts_scalars_and_pipe_arrays(self):
        overrides = parse_user_overrides(
            "predict_year=2035, sampling_rate=0.02, "
            "probability_paths=a.tif|b.tif, note=keep text"
        )

        self.assertEqual(overrides["predict_year"], 2035)
        self.assertEqual(overrides["sampling_rate"], 0.02)
        self.assertEqual(overrides["probability_paths"], ["a.tif", "b.tif"])
        self.assertEqual(overrides["note"], "keep text")

    def test_parse_user_overrides_preserves_commas_inside_values_without_assignment(self):
        overrides = parse_user_overrides(
            "neighborhood_weights=0.1,0.2,0.7, transition_matrix=1,1;0,1"
        )

        self.assertEqual(overrides["neighborhood_weights"], "0.1,0.2,0.7")
        self.assertEqual(overrides["transition_matrix"], "1,1;0,1")

    def test_format_confirmation_includes_params_assumptions_warnings_and_guidance(self):
        proposal = ParameterProposal(
            step="cars",
            params={"input_classes": 3, "policy_path": ""},
            assumptions=["使用最新一期 LULC 作为 CARS 起始图。"],
            warnings=["未检测到约束图，policy_path 将为空。"],
        )

        text = format_confirmation(proposal)

        self.assertIn("即将执行：cars", text)
        self.assertIn("input_classes", text)
        self.assertIn("使用最新一期", text)
        self.assertIn("未检测到约束图", text)
        self.assertIn("回复 ok 执行", text)
        self.assertIn("回复 cancel 取消工作流", text)


if __name__ == "__main__":
    unittest.main()
