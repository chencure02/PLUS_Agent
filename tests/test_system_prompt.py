import unittest

from agent.config import SYSTEM_PROMPT


class SystemPromptTests(unittest.TestCase):
    def test_prompt_keeps_full_plus_simulation_under_managed_workflow(self):
        self.assertIn("管理式 PLUS 工作流", SYSTEM_PROMPT)
        self.assertIn("PLUSWorkflowRunner", SYSTEM_PROMPT)
        self.assertIn("不要在 ReAct 中自行串联完整标准流程", SYSTEM_PROMPT)
        self.assertIn(
            "convert → expansion → leas → markov → neighborhood_weight → cars",
            SYSTEM_PROMPT,
        )
        self.assertIn("结构化产物", SYSTEM_PROMPT)
        self.assertNotIn("主动询问用户是否需要计算邻域权重", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
