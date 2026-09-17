import tempfile
import unittest
from pathlib import Path

from agent.core.workflow_router import WorkflowRouter
from agent.core.workflow_state import WorkflowState
from agent.memory.store import MemoryStore


class WorkflowRouterTests(unittest.TestCase):
    def test_full_simulation_request_routes_to_workflow(self):
        router = WorkflowRouter()

        self.assertTrue(router.should_use_workflow("请完成PLUS土地利用模拟并预测2033年"))
        self.assertTrue(router.should_use_workflow("用2003和2013数据模拟未来土地利用"))
        self.assertTrue(router.should_use_workflow("请按PLUS标准流程进行土地利用模拟"))

    def test_ordinary_chat_routes_to_react(self):
        router = WorkflowRouter()

        self.assertFalse(router.should_use_workflow("解释一下LEAS模块的原理"))
        self.assertFalse(router.should_use_workflow("帮我看看有哪些文件"))

    def test_active_workflow_routes_back_to_workflow(self):
        router = WorkflowRouter()

        self.assertTrue(router.should_use_workflow("继续", has_active_workflow=True))

    def test_control_reply_without_active_workflow_does_not_start_workflow(self):
        router = WorkflowRouter()

        self.assertFalse(router.should_use_workflow("ok", has_active_workflow=False))

    def test_memory_store_round_trips_workflow_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "memory.db")
            memory = MemoryStore(db_path)
            state = WorkflowState(thread_id="thread-a", current_step="markov")
            state.artifacts["yearly_demands"] = "1,100,200"

            memory.save_workflow_state(state)
            loaded = memory.load_workflow_state("thread-a")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.current_step, "markov")
            self.assertEqual(loaded.artifacts["yearly_demands"], "1,100,200")

            memory.delete_workflow_state("thread-a")
            self.assertIsNone(memory.load_workflow_state("thread-a"))


if __name__ == "__main__":
    unittest.main()
