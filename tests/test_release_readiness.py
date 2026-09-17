import unittest
from pathlib import Path

from scripts.check_release_readiness import check_repository, is_forbidden_tracked


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTest(unittest.TestCase):
    def test_repository_is_ready_for_public_github(self):
        issues = check_repository(PROJECT_ROOT)

        self.assertEqual([], issues)

    def test_env_template_is_allowed_but_real_env_files_are_blocked(self):
        self.assertFalse(is_forbidden_tracked(".env.example"))
        self.assertTrue(is_forbidden_tracked(".env"))
        self.assertTrue(is_forbidden_tracked(".env.local"))


if __name__ == "__main__":
    unittest.main()
