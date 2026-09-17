import subprocess
import sys
import unittest


class ImportTests(unittest.TestCase):
    def test_memory_store_imports_without_circular_dependency(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from agent.memory.store import MemoryStore; print(MemoryStore.__name__)",
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MemoryStore", result.stdout)


if __name__ == "__main__":
    unittest.main()
