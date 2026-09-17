import json
import unittest

from agent.ui.callbacks import _build_resume_context_notes


class ResumeContextTests(unittest.TestCase):
    def test_resume_context_includes_summary_messages_and_decisions(self):
        summary = {
            "summary": "用户正在做 2035 年土地利用模拟。",
            "messages_json": json.dumps(
                [
                    {"role": "user", "content": "请模拟 2035 年土地利用"},
                    {"role": "assistant", "content": "已进入 PLUS 标准工作流"},
                ],
                ensure_ascii=False,
            ),
            "key_decisions_json": json.dumps(
                [{"path_note": "CARS 模拟结果: C:/runs/Simulation_1.tif"}],
                ensure_ascii=False,
            ),
        }

        notes = _build_resume_context_notes(summary)
        joined = "\n".join(notes)

        self.assertIn("[恢复会话摘要]", joined)
        self.assertIn("2035 年土地利用模拟", joined)
        self.assertIn("[恢复会话最近消息]", joined)
        self.assertIn("用户: 请模拟 2035 年土地利用", joined)
        self.assertIn("助手: 已进入 PLUS 标准工作流", joined)
        self.assertIn("CARS 模拟结果: C:/runs/Simulation_1.tif", joined)


if __name__ == "__main__":
    unittest.main()
