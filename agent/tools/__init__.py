# agent/tools/__init__.py
from contextlib import contextmanager
import subprocess
import threading
from pathlib import Path

from agent.config import PLUS_BACKEND
from .base import BaseTool, ToolResult
from .registry import ToolRegistry

_PLUS_JOB_LOCK = threading.Lock()


@contextmanager
def locked_plus_backend():
    """Serialize access to PLUS's shared working directory and tmp files."""
    with _PLUS_JOB_LOCK:
        yield


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


def run_plus_job(
    tmp_filename: str,
    tmp_content: str,
    bat_name: str,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """Write a PLUS tmp file and run the matching bat file as one serialized job."""
    with locked_plus_backend():
        write_tmp(tmp_filename, tmp_content)
        return run_bat(bat_name, timeout=timeout)
