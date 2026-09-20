"""Check whether the repository is safe to publish on GitHub."""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    ".env.example",
    "docs/installation.md",
    "docs/architecture.md",
    "docs/privacy.md",
    "docs/assets/upload-preview.png",
    "docs/assets/leas-preview.png",
    "docs/assets/cars-preview.png",
    "docs/assets/workflow/01-chat-overview.png",
    "docs/assets/workflow/02-data-check.png",
    "docs/assets/workflow/03-parameter-review.png",
    "docs/assets/workflow/04-workflow-result.png",
]

FORBIDDEN_TRACKED_PATTERNS = [
    ".env",
    ".env.*",
    ".chainlit/*.db",
    "data/*.db",
    "workspaces/**",
    "outputs/**",
    "contest_staging/**",
    "public/geoscene/*.png",
    "*.zip",
    "*.7z",
    "*.rar",
    "plus-backend/cpp/*.exe",
    "plus-backend/cpp/*.dll",
    "plus-backend/cpp/output/**",
    "plus-backend/*.tmp",
    "plus-backend/Contribution*.csv",
    "plus-backend/TrainData*.csv",
    "plus-backend/TransitionMatrix_*.csv",
    "plus-backend/FitFormula.csv",
    "plus-backend/FoM.csv",
    "plus-backend/Kappa.csv",
    "plus-backend/PredictDemand.csv",
    "plus-backend/accuracy_record_rf.txt",
    "plus-backend/imageminmax.txt",
    "plus-backend/*.model",
]

SECRET_VALUE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|"
    r"ANTHROPIC_API_KEY\s*=\s*.+|"
    r"OPENAI_API_KEY\s*=\s*.+|"
    r"DEEPSEEK_API_KEY\s*=\s*.+|"
    r"DASHSCOPE_API_KEY\s*=\s*.+)",
    re.IGNORECASE,
)


def _tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def is_forbidden_tracked(path: str) -> bool:
    if path == ".env.example":
        return False
    return any(fnmatch.fnmatch(path, pattern) for pattern in FORBIDDEN_TRACKED_PATTERNS)


def _has_secret_values(env_example: Path) -> bool:
    if not env_example.exists():
        return False
    for line in env_example.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if SECRET_VALUE_PATTERN.search(stripped):
            return True
    return False


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    issues: list[str] = []

    for rel_path in REQUIRED_FILES:
        if not (root / rel_path).exists():
            issues.append(f"Missing required public repository file: {rel_path}")

    try:
        tracked = _tracked_files(root)
    except subprocess.CalledProcessError as exc:
        return [f"Unable to inspect git tracked files: {exc}"]

    for rel_path in tracked:
        if is_forbidden_tracked(rel_path):
            issues.append(f"Forbidden file is tracked by git: {rel_path}")

    env_example = root / ".env.example"
    if _has_secret_values(env_example):
        issues.append(".env.example appears to contain a real secret value")

    return issues


def main() -> int:
    issues = check_repository(Path(__file__).resolve().parents[1])
    if issues:
        print("Release readiness check failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Release readiness check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
