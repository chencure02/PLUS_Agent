import unittest

from agent.core.default_parameter_agent import DefaultParameterAgent
from agent.core.workflow_state import WorkflowContext, WorkflowState


class DefaultParameterAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = DefaultParameterAgent()
        self.context = WorkflowContext(
            thread_id="thread-a",
            user_message="请基于2003和2013土地利用预测2033年",
            lulc_files=[
                "C:/data/wh2013_refy.tif",
                "C:/data/wh2003_refy.tif",
            ],
            driver_files=["C:/data/drivers/dem.tif"],
            constraint_files=[],
            output_dir="C:/out",
            drivers_dir="C:/data/drivers",
        )

    def test_convert_proposal_sorts_lulc_by_year_and_builds_output_paths(self):
        proposal = self.agent.propose("convert", WorkflowState(thread_id="thread-a"), self.context)

        self.assertEqual(
            proposal.params["input_paths"],
            ["C:/data/wh2003_refy.tif", "C:/data/wh2013_refy.tif"],
        )
        self.assertTrue(
            proposal.params["output_paths"][0].replace("\\", "/").endswith(
                "convert/wh2003_refy_converted.tif"
            )
        )
        self.assertEqual(proposal.missing_fields, [])

    def test_markov_proposal_uses_converted_paths_and_years(self):
        state = WorkflowState(thread_id="thread-a")
        state.artifacts["converted_lulc_paths"] = [
            "C:/out/convert/wh2003_refy_converted.tif",
            "C:/out/convert/wh2013_refy_converted.tif",
        ]

        proposal = self.agent.propose("markov", state, self.context)

        self.assertEqual(proposal.params["start_map"], "C:/out/convert/wh2003_refy_converted.tif")
        self.assertEqual(proposal.params["end_map"], "C:/out/convert/wh2013_refy_converted.tif")
        self.assertEqual(proposal.params["start_year"], 2003)
        self.assertEqual(proposal.params["end_year"], 2013)
        self.assertEqual(proposal.params["predict_year"], 2033)

    def test_markov_does_not_treat_latest_historical_year_as_predict_year(self):
        context = WorkflowContext(
            thread_id="thread-a",
            user_message="请用2003和2013土地利用数据进行模拟",
            lulc_files=["C:/data/wh2003_refy.tif", "C:/data/wh2013_refy.tif"],
            output_dir="C:/out",
        )
        state = WorkflowState(thread_id="thread-a")
        state.artifacts["converted_lulc_paths"] = [
            "C:/out/convert/wh2003_refy_converted.tif",
            "C:/out/convert/wh2013_refy_converted.tif",
        ]

        proposal = self.agent.propose("markov", state, context)

        self.assertNotIn("predict_year", proposal.params)
        self.assertIn("predict_year", proposal.missing_fields)

    def test_neighborhood_weight_uses_probability_band_count(self):
        state = WorkflowState(thread_id="thread-a")
        state.artifacts["expansion_raster"] = "C:/out/expansion/expansion_landuse_1to2.tif"
        state.artifacts["probability_paths"] = [
            "C:/out/leas/potential_band_1.tif",
            "C:/out/leas/potential_band_2.tif",
            "C:/out/leas/potential_band_3.tif",
        ]

        proposal = self.agent.propose("neighborhood_weight", state, self.context)

        self.assertEqual(proposal.params["expansion_raster"], state.artifacts["expansion_raster"])
        self.assertEqual(proposal.params["num_classes"], 3)
        self.assertEqual(proposal.params["background_values"], "0,255")

    def test_leas_uses_parent_folder_when_only_driver_file_is_known(self):
        context = WorkflowContext(
            thread_id="thread-a",
            user_message="预测2033年",
            driver_files=["C:/data/drivers/dem.tif"],
            output_dir="C:/out",
        )
        state = WorkflowState(thread_id="thread-a")
        state.artifacts["expansion_raster"] = "C:/out/expansion/expansion_landuse_1to2.tif"

        proposal = self.agent.propose("leas", state, context)

        self.assertEqual(proposal.params["feature_folder"].replace("\\", "/"), "C:/data/drivers")

    def test_cars_proposal_uses_structured_artifacts_and_warns_without_constraint(self):
        state = WorkflowState(thread_id="thread-a")
        state.artifacts.update({
            "late_lulc": "C:/out/convert/wh2013_refy_converted.tif",
            "probability_paths": [
                "C:/out/leas/potential_band_1.tif",
                "C:/out/leas/potential_band_2.tif",
            ],
            "yearly_demands": "1,100,200",
            "neighborhood_weights": "0.3,0.7",
        })

        proposal = self.agent.propose("cars", state, self.context)

        self.assertEqual(proposal.params["input_classes"], 2)
        self.assertEqual(proposal.params["input_lulc"], "C:/out/convert/wh2013_refy_converted.tif")
        self.assertEqual(proposal.params["yearly_demands"], "1,100,200")
        self.assertEqual(proposal.params["neighborhood_weights"], "0.3,0.7")
        self.assertEqual(proposal.params["transition_matrix"], "1,1;1,1")
        self.assertIn("未检测到约束图", "\n".join(proposal.warnings))


if __name__ == "__main__":
    unittest.main()
