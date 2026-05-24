"""PLUS Agent - Chainlit entry point.

Usage:
    conda activate plus-agent
    cd /d path/to/PLUS_Agent
    chainlit run agent/main.py

Environment variables:
    PLUS_LLM_BACKEND  - LLM backend: claude (default), openai, deepseek, qwen-compat
    PLUS_MEMORY_DB    - SQLite database path (default: PROJECT_ROOT/data/memory.db)
    ANTHROPIC_API_KEY - Claude API key
    OPENAI_API_KEY    - OpenAI API key
    DEEPSEEK_API_KEY  - DeepSeek API key
    DASHSCOPE_API_KEY - Qwen API key
"""
import os
import sys
from pathlib import Path

# Ensure project root is on Python path so `agent` package is importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agent.config import MEMORY_DB_PATH  # noqa: E402

if not os.environ.get("PLUS_MEMORY_DB"):
    os.environ["PLUS_MEMORY_DB"] = MEMORY_DB_PATH

import agent.ui.callbacks  # noqa: E402, F401 — registers Chainlit handlers
