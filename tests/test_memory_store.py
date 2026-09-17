import tempfile
import unittest
from pathlib import Path

from agent.core.workflow_state import WorkflowState
from agent.memory.store import MemoryStore


class MemoryStoreScopingTests(unittest.TestCase):
    def make_store(self, tmpdir: str) -> MemoryStore:
        return MemoryStore(str(Path(tmpdir) / "memory.db"))

    def test_save_summary_updates_existing_session_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = self.make_store(tmpdir)

            memory.save_summary(
                "thread-a",
                title="old title",
                summary="old summary",
                messages=[{"role": "user", "content": "old"}],
            )
            memory.save_summary(
                "thread-a",
                title="new title",
                summary="new summary",
                messages=[{"role": "user", "content": "new"}],
            )

            summary = memory.get_summary("thread-a")
            self.assertIsNotNone(summary)
            self.assertEqual(summary["title"], "new title")
            self.assertEqual(summary["summary"], "new summary")
            self.assertEqual(len(memory.get_recent_summaries()), 1)

    def test_summaries_are_scoped_by_user_and_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = self.make_store(tmpdir)

            memory.save_summary(
                "thread-a",
                title="u1",
                summary="summary from user one",
                user_id="user-one",
                thread_id="thread-a",
            )
            memory.save_summary(
                "thread-a",
                title="u2",
                summary="summary from user two",
                user_id="user-two",
                thread_id="thread-a",
            )

            self.assertEqual(
                memory.get_summary("thread-a", user_id="user-one")["summary"],
                "summary from user one",
            )
            self.assertEqual(
                memory.get_summary("thread-a", user_id="user-two")["summary"],
                "summary from user two",
            )
            self.assertEqual(
                memory.get_recent_summaries(user_id="user-one")[0]["title"],
                "u1",
            )

    def test_scoped_preferences_do_not_cross_users_or_threads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = self.make_store(tmpdir)

            memory.set_scoped_preference(
                "path_refy",
                "C:/u1/thread-a/refy.tif",
                user_id="user-one",
                thread_id="thread-a",
            )
            memory.set_scoped_preference(
                "path_refy",
                "C:/u1/thread-b/refy.tif",
                user_id="user-one",
                thread_id="thread-b",
            )
            memory.set_scoped_preference(
                "path_refy",
                "C:/u2/thread-a/refy.tif",
                user_id="user-two",
                thread_id="thread-a",
            )

            self.assertEqual(
                memory.get_scoped_preference(
                    "path_refy", user_id="user-one", thread_id="thread-a"
                ),
                "C:/u1/thread-a/refy.tif",
            )
            self.assertEqual(
                memory.get_scoped_preference(
                    "path_refy", user_id="user-one", thread_id="thread-b"
                ),
                "C:/u1/thread-b/refy.tif",
            )
            self.assertEqual(
                memory.get_frequent_paths(user_id="user-one", thread_id="thread-a"),
                ["C:/u1/thread-a/refy.tif"],
            )

    def test_run_and_step_records_keep_user_thread_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = self.make_store(tmpdir)

            run_id = memory.save_run(
                "simulate 2035",
                ["convert"],
                {"target": 2035},
                [],
                user_id="user-one",
                thread_id="thread-a",
            )
            memory.save_step(run_id, "convert", 1, {"lulc": "C:/refy.tif"})

            detail = memory.get_run_detail(run_id)
            self.assertEqual(detail["user_id"], "user-one")
            self.assertEqual(detail["thread_id"], "thread-a")
            self.assertEqual(detail["steps"][0]["user_id"], "user-one")
            self.assertEqual(detail["steps"][0]["thread_id"], "thread-a")
            self.assertEqual(len(memory.get_recent_runs(user_id="user-one")), 1)
            self.assertEqual(len(memory.get_recent_runs(user_id="user-two")), 0)

    def test_workflow_artifacts_are_persisted_per_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            memory = self.make_store(tmpdir)
            state = WorkflowState(thread_id="thread-a", status="completed")
            state.steps["cars"].status = "success"
            state.steps["cars"].output_paths = ["C:/runs/thread-a/Simulation_1.tif"]
            state.steps["cars"].artifacts = {
                "simulation_raster": "C:/runs/thread-a/Simulation_1.tif",
                "yearly_demands": "1,100,200",
            }

            memory.save_workflow_run("user-one", "thread-a", state)
            memory.save_workflow_artifacts("user-one", "thread-a", state)

            artifacts = memory.get_thread_artifacts("user-one", "thread-a")
            file_paths = {item["path"] for item in artifacts if item["path"]}
            value_items = {
                item["artifact_key"]: item["value_json"]
                for item in artifacts
                if item["artifact_type"] == "value"
            }
            self.assertIn("C:/runs/thread-a/Simulation_1.tif", file_paths)
            self.assertEqual(value_items["yearly_demands"], '"1,100,200"')
            self.assertEqual(memory.get_thread_artifacts("user-one", "thread-b"), [])


if __name__ == "__main__":
    unittest.main()
