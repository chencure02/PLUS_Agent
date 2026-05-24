# agent/tools/__init__.py
import subprocess
from pathlib import Path

from agent.config import PLUS_BACKEND
from .base import BaseTool, ToolResult
from .registry import ToolRegistry


def run_bat(bat_name: str, timeout: int = 600) -> tuple[int, str, str]:
    """Run a bat file from plus-backend/. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            [str(PLUS_BACKEND / bat_name)],
            cwd=str(PLUS_BACKEND),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout: {bat_name} exceeded {timeout}s"
    except Exception as e:
        return -1, "", f"Error running {bat_name}: {e}"


def write_tmp(filename: str, content: str) -> str:
    """Write a tmp file to plus-backend/. Returns full path."""
    path = PLUS_BACKEND / filename
    try:
        path.write_text(content, encoding="utf-8")
        return str(path)
    except OSError as e:
        raise IOError(f"Failed to write tmp file {filename}: {e}")
