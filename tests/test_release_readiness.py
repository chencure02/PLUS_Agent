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

    def test_readme_includes_workflow_example_gallery(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        workflow_images = [
            "docs/assets/workflow/01-chat-overview.png",
            "docs/assets/workflow/02-data-check.png",
            "docs/assets/workflow/03-parameter-review.png",
            "docs/assets/workflow/04-workflow-result.png",
        ]

        self.assertIn("## Usage Walkthrough", readme)
        for image_path in workflow_images:
            self.assertTrue((PROJECT_ROOT / image_path).exists(), image_path)
            self.assertIn(image_path, readme)


if __name__ == "__main__":
    unittest.main()
