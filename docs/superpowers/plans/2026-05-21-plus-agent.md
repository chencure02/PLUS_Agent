# PLUS Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ReAct Agent system that wraps PLUS model's 8 modules as tools with a Chainlit chat UI, multi-LLM support, and SQLite memory.

**Architecture:** Layered design — LLM Adapter (Claude/OpenAI/DeepSeek/Qwen) → Agent Core (ReAct loop + Workflow engine) → Tool Registry (8 PLUS tools) → Memory Store (SQLite). Chainlit UI sits on top, rendering tool steps with Folium interactive maps and Matplotlib fallback.

**Tech Stack:** Python 3.11, Chainlit, anthropic SDK, openai SDK, Folium, Matplotlib, GDAL (conda-forge), SQLite

---

### Task 0: Environment Setup

**Files:**
- Create: `requirements.txt`
- Create: `setup.bat`
- Create: `setup.sh`

- [ ] **Step 1: Write requirements.txt**

```
chainlit>=1.0.0
openai>=1.0.0
anthropic>=0.30.0
dashscope>=1.20.0
folium>=0.17.0
matplotlib>=3.8.0
numpy>=1.26.0
pandas>=2.0.0
```

- [ ] **Step 2: Write setup.bat**

```bat
@echo off
echo Creating conda environment plus-agent...
conda create -n plus-agent python=3.11 -y
call conda activate plus-agent
echo Installing GDAL via conda-forge...
conda install -c conda-forge gdal -y
echo Installing pip dependencies...
pip install -r requirements.txt
echo Setup complete. Run: conda activate plus-agent ^&^& chainlit run agent/main.py
```

- [ ] **Step 3: Write setup.sh**

```bash
#!/bin/bash
set -e
echo "Creating conda environment plus-agent..."
conda create -n plus-agent python=3.11 -y
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate plus-agent
echo "Installing GDAL via conda-forge..."
conda install -c conda-forge gdal -y
echo "Installing pip dependencies..."
pip install -r requirements.txt
echo "Setup complete. Run: conda activate plus-agent && chainlit run agent/main.py"
```

- [ ] **Step 4: Verify setup**

Run: `conda activate plus-agent && python -c "from osgeo import gdal; import chainlit; import folium; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt setup.bat setup.sh
git commit -m "feat: add environment setup files"
```

---

### Task 1: Config Module

**Files:**
- Create: `agent/__init__.py`
- Create: `agent/config.py`

- [ ] **Step 1: Create package init**

```python
# agent/__init__.py
"""PLUS Agent - Intelligent land use simulation agent."""
```

- [ ] **Step 2: Write config.py**

```python
# agent/config.py
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUS_BACKEND = PROJECT_ROOT / "plus-backend"
CPP_DIR = PLUS_BACKEND / "cpp"
DATA_DIR = PROJECT_ROOT / "data"

LLM_BACKEND = os.getenv("PLUS_LLM_BACKEND", "claude")
LLM_CONFIG = {
    "claude": {
        "model": os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "api_key_env": "OPENAI_API_KEY",
    },
    "deepseek": {
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com/v1",
    },
    "qwen-compat": {
        "model": "qwen-max",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}

MAX_REACT_STEPS = int(os.getenv("PLUS_MAX_STEPS", "15"))
MEMORY_DB_PATH = str(DATA_DIR / "memory.db")

SYSTEM_PROMPT = """You are PLUS Agent, an intelligent assistant for land use simulation using the PLUS model (Patch-generating Land Use Simulation).

## Available Modules
You have 8 tools: convert, expansion, leas, markov, linear, cars, validation, diverse.

## Standard Workflow for Future Land Use Simulation
convert → expansion → leas → markov → cars

## Rules
1. NEVER guess file paths or parameter values. If missing, ask the user.
2. Confirm key parameters with the user before running any tool.
3. If a tool fails, report the exact error and suggest remedies.
4. All file paths MUST be absolute paths (Windows format).
5. LULC raster class codes must start from 1 and be consecutive.
6. When user asks to simulate future land use, guide them through the workflow step by step, collecting all needed data."""
```

- [ ] **Step 3: Verify config loads**

Run: `python -c "from agent.config import PROJECT_ROOT, LLM_CONFIG; print(PROJECT_ROOT); print(list(LLM_CONFIG.keys()))"`
Expected: Prints project root and `['claude', 'openai', 'deepseek', 'qwen-compat']`

- [ ] **Step 4: Commit**

```bash
git add agent/__init__.py agent/config.py
git commit -m "feat: add config module"
```

---

### Task 2: LLM Adapter Layer

**Files:**
- Create: `agent/llm/__init__.py`
- Create: `agent/llm/adapter.py`
- Create: `agent/llm/openai_compat.py`
- Create: `agent/llm/claude_adapter.py`

- [ ] **Step 1: Create package init**

```python
# agent/llm/__init__.py
from .adapter import BaseLLM, LLMResponse, create_llm
```

- [ ] **Step 2: Write base interface**

```python
# agent/llm/adapter.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class LLMResponse:
    type: Literal["text", "tool_call", "ask_user"]
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)

class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        ...

def create_llm(backend: str, config: dict) -> BaseLLM:
    if backend == "claude":
        from .claude_adapter import ClaudeAdapter
        return ClaudeAdapter(config)
    else:
        from .openai_compat import OpenAICompatAdapter
        return OpenAICompatAdapter(config)
```

- [ ] **Step 3: Write OpenAI-compatible adapter**

```python
# agent/llm/openai_compat.py
import os, json
from openai import OpenAI
from .adapter import BaseLLM, LLMResponse

class OpenAICompatAdapter(BaseLLM):
    def __init__(self, config: dict):
        api_key = os.getenv(config["api_key_env"], "")
        if not api_key:
            raise ValueError(f"Env var {config['api_key_env']} not set")
        self.client = OpenAI(api_key=api_key, base_url=config.get("base_url"))
        self.model = config["model"]

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"name": tc.function.name, "arguments": args})
            return LLMResponse(type="tool_call", tool_calls=tool_calls, content=msg.content or "")

        return LLMResponse(type="text", content=msg.content or "")
```

- [ ] **Step 4: Write Claude adapter**

```python
# agent/llm/claude_adapter.py
import os
from anthropic import Anthropic
from .adapter import BaseLLM, LLMResponse

class ClaudeAdapter(BaseLLM):
    def __init__(self, config: dict):
        api_key = os.getenv(config["api_key_env"], "")
        if not api_key:
            raise ValueError(f"Env var {config['api_key_env']} not set")
        self.client = Anthropic(api_key=api_key)
        self.model = config["model"]

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        system = None
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m.get("content", "")})

        kwargs = {"model": self.model, "messages": api_messages, "max_tokens": 4096}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [{
                "name": t["name"], "description": t["description"],
                "input_schema": t["parameters"],
            } for t in tools]

        response = self.client.messages.create(**kwargs)

        tool_calls = []
        text_content = ""
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append({"name": block.name, "arguments": block.input})
            elif block.type == "text":
                text_content += block.text

        if tool_calls:
            return LLMResponse(type="tool_call", tool_calls=tool_calls, content=text_content)
        return LLMResponse(type="text", content=text_content)
```

- [ ] **Step 5: Test adapter creation**

Run: `python -c "from agent.llm import create_llm; from agent.config import LLM_CONFIG; a = create_llm('deepseek', LLM_CONFIG['deepseek']); print(type(a).__name__)"`
Expected: `OpenAICompatAdapter`

- [ ] **Step 6: Commit**

```bash
git add agent/llm/
git commit -m "feat: add LLM adapter layer (Claude + OpenAI compat)"
```

---

### Task 3: Tool Base + Registry + Helpers

**Files:**
- Create: `agent/tools/__init__.py`
- Create: `agent/tools/base.py`
- Create: `agent/tools/registry.py`

- [ ] **Step 1: Write package init with bat helpers**

```python
# agent/tools/__init__.py
import subprocess
from pathlib import Path
from agent.config import PLUS_BACKEND

def run_bat(bat_name: str, timeout: int = 600) -> tuple[int, str, str]:
    """Run a bat file from plus-backend/. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        [str(PLUS_BACKEND / bat_name)], cwd=str(PLUS_BACKEND),
        capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, result.stdout, result.stderr

def write_tmp(filename: str, content: str) -> str:
    """Write a tmp file to plus-backend/. Returns full path."""
    path = PLUS_BACKEND / filename
    path.write_text(content, encoding="utf-8")
    return str(path)
```

- [ ] **Step 2: Write BaseTool and ToolResult**

```python
# agent/tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class ToolResult:
    success: bool
    message: str = ""
    output_paths: list[str] = field(default_factory=list)
    error: str = ""

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict = {}

    def validate(self, params: dict) -> bool:
        required = self.parameters.get("required", [])
        return all(k in params for k in required)

    @abstractmethod
    def execute(self, params: dict) -> ToolResult:
        ...

    def to_llm_format(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}
```

- [ ] **Step 3: Write ToolRegistry**

```python
# agent/tools/registry.py
from .base import BaseTool, ToolResult

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_all_llm_format(self) -> list[dict]:
        return [t.to_llm_format() for t in self._tools.values()]

    def get_all_names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"Unknown tool: {name}")
        if not tool.validate(params):
            return ToolResult(success=False, error=f"Invalid params for {name}")
        return tool.execute(params)
```

- [ ] **Step 4: Test registry**

Run:
```python
from agent.tools.base import BaseTool, ToolResult
from agent.tools.registry import ToolRegistry

class DummyTool(BaseTool):
    name = "dummy"; description = "test"
    parameters = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    def execute(self, params): return ToolResult(success=True, message="ok")

reg = ToolRegistry(); reg.register(DummyTool())
assert reg.execute("dummy", {"x": 1}).success
assert not reg.execute("nonexistent", {}).success
assert not reg.execute("dummy", {}).success
print("Registry tests passed")
```

- [ ] **Step 5: Commit**

```bash
git add agent/tools/
git commit -m "feat: add tool base, registry, and bat helpers"
```

---

### Task 4: Memory Store

**Files:**
- Create: `agent/memory/__init__.py`
- Create: `agent/memory/schema.sql`
- Create: `agent/memory/store.py`

- [ ] **Step 1: Create package init**

```python
# agent/memory/__init__.py
from .store import MemoryStore
```

- [ ] **Step 2: Write SQL schema**

```sql
-- agent/memory/schema.sql
CREATE TABLE IF NOT EXISTS simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    workflow_json TEXT,
    params_json TEXT,
    output_paths_json TEXT,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    duration_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES simulation_runs(id),
    tool_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    params_json TEXT,
    tmp_content TEXT,
    output_paths_json TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT,
    key_decisions_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 3: Write MemoryStore**

```python
# agent/memory/store.py
import json, sqlite3, os
from datetime import datetime
from pathlib import Path

class MemoryStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        schema = Path(__file__).parent / "schema.sql"
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema.read_text())

    def save_run(self, name: str, workflow: list, params: dict, outputs: list[str]) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO simulation_runs (name, workflow_json, params_json, output_paths_json, status) VALUES (?,?,?,?,'running')",
                (name, json.dumps(workflow), json.dumps(params), json.dumps(outputs))
            )
            return cur.lastrowid

    def update_run_status(self, run_id: int, status: str, error: str = None, duration: float = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE simulation_runs SET status=?, error_message=?, duration_seconds=? WHERE id=?",
                (status, error, duration, run_id)
            )

    def save_step(self, run_id: int, tool_name: str, order: int, params: dict,
                  tmp: str = None, outputs: list[str] = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO run_steps (run_id, tool_name, step_order, params_json, tmp_content, output_paths_json, status) VALUES (?,?,?,?,?,?,'pending')",
                (run_id, tool_name, order, json.dumps(params), tmp, json.dumps(outputs or []))
            )

    def update_step_status(self, run_id: int, order: int, status: str, error: str = None):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE run_steps SET status=?, error_message=?, finished_at=? WHERE run_id=? AND step_order=?",
                (status, error, now, run_id, order)
            )
            conn.execute(
                "UPDATE run_steps SET started_at=? WHERE run_id=? AND step_order=? AND started_at IS NULL",
                (now, run_id, order)
            )

    def get_recent_runs(self, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM simulation_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run_detail(self, run_id: int) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM simulation_runs WHERE id=?", (run_id,)).fetchone()
            if not run:
                return {}
            steps = conn.execute(
                "SELECT * FROM run_steps WHERE run_id=? ORDER BY step_order", (run_id,)
            ).fetchall()
            result = dict(run)
            result["steps"] = [dict(s) for s in steps]
            return result

    def get_preference(self, key: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT value FROM user_preferences WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_preference(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?,?,?)",
                (key, value, datetime.now().isoformat())
            )

    def get_frequent_paths(self) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT value FROM user_preferences WHERE key LIKE '%_path' OR key LIKE '%_folder' ORDER BY updated_at DESC LIMIT 10"
            ).fetchall()
            return [r[0] for r in rows]

    def save_summary(self, session_id: str, summary: str, decisions: list[dict]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO conversation_summaries (session_id, summary, key_decisions_json) VALUES (?,?,?)",
                (session_id, summary, json.dumps(decisions))
            )

    def get_recent_summaries(self, limit: int = 3) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM conversation_summaries ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
```

- [ ] **Step 4: Test memory store**

Run: `python -c "from agent.memory import MemoryStore; from agent.config import MEMORY_DB_PATH; m = MemoryStore(MEMORY_DB_PATH); rid = m.save_run('test', ['convert'], {}, []); m.update_run_status(rid, 'success'); assert len(m.get_recent_runs()) >= 1; m.set_preference('data_path', '/test/path'); assert m.get_preference('data_path') == '/test/path'; print('Memory tests passed')"`

- [ ] **Step 5: Commit**

```bash
git add agent/memory/
git commit -m "feat: add memory store with SQLite"
```

---

### Task 5: PLUS Tools (all 8)

**Files:**
- Create: `agent/tools/convert.py`
- Create: `agent/tools/expansion.py`
- Create: `agent/tools/leas.py`
- Create: `agent/tools/markov.py`
- Create: `agent/tools/linear.py`
- Create: `agent/tools/cars.py`
- Create: `agent/tools/validation.py`
- Create: `agent/tools/diverse.py`

- [ ] **Step 1: Write Convert tool**

```python
# agent/tools/convert.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat

class ConvertTool(BaseTool):
    name = "convert"
    description = "Reclassify LULC rasters to PLUS-compatible format. MUST run first before any other module. Input: N input raster paths + N output paths."
    parameters = {
        "type": "object",
        "properties": {
            "input_paths": {"type": "array", "items": {"type": "string"}, "description": "Input LULC raster absolute paths"},
            "output_paths": {"type": "array", "items": {"type": "string"}, "description": "Output converted raster absolute paths (same count as input)"},
        },
        "required": ["input_paths", "output_paths"]
    }

    def validate(self, params: dict) -> bool:
        return len(params.get("input_paths", [])) == len(params.get("output_paths", [])) and len(params["input_paths"]) > 0

    def execute(self, params: dict) -> ToolResult:
        n = len(params["input_paths"])
        tmp = f"<Input number>\n{n}\n<Input LULC series>\n"
        tmp += "\n".join(params["input_paths"]) + "\n"
        tmp += "<Output LULC series>\n" + "\n".join(params["output_paths"]) + "\n"
        write_tmp("PLUS_Convert.tmp", tmp)
        rc, stdout, stderr = run_bat("convert.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Convert failed (rc={rc}): {stderr}")
        return ToolResult(success=True, message=f"Converted {n} rasters", output_paths=params["output_paths"])
```

- [ ] **Step 2: Write Expansion tool**

```python
# agent/tools/expansion.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat

class ExpansionTool(BaseTool):
    name = "expansion"
    description = "Extract land use change areas between two LULC rasters (early vs late year). Output: expansion change map."
    parameters = {
        "type": "object",
        "properties": {
            "early_lulc": {"type": "string", "description": "Early-year LULC raster absolute path"},
            "late_lulc": {"type": "string", "description": "Late-year LULC raster absolute path"},
            "output_change": {"type": "string", "description": "Output expansion map absolute path"},
        },
        "required": ["early_lulc", "late_lulc", "output_change"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<Input number>\n2\n<Input LULC series>\n{params['early_lulc']}\n{params['late_lulc']}\n<Output change>\n{params['output_change']}\n"
        write_tmp("PLUS_Expansion.tmp", tmp)
        rc, stdout, stderr = run_bat("expansion.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Expansion failed (rc={rc}): {stderr}")
        return ToolResult(success=True, message="Expansion map generated", output_paths=[params["output_change"]])
```

- [ ] **Step 3: Write Markov tool**

```python
# agent/tools/markov.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
from agent.config import CPP_DIR

class MarkovTool(BaseTool):
    name = "markov"
    description = "Predict future land use demand quantities using Markov chain. Input: start/end LULC + years. Output: markov.csv with predicted per-class demands."
    parameters = {
        "type": "object",
        "properties": {
            "start_map": {"type": "string", "description": "Start year LULC raster path"},
            "end_map": {"type": "string", "description": "End year LULC raster path"},
            "start_year": {"type": "integer", "description": "Start year (e.g. 2003)"},
            "end_year": {"type": "integer", "description": "End year (e.g. 2013)"},
            "predict_year": {"type": "integer", "description": "Target prediction year (e.g. 2033)"},
        },
        "required": ["start_map", "end_map", "start_year", "end_year", "predict_year"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<StartMap>\n{params['start_map']}\n<EndMap>\n{params['end_map']}\n<Start Year>\n{params['start_year']}\n<End Year>\n{params['end_year']}\n<Predict Year>\n{params['predict_year']}\n"
        write_tmp("PLUS_Markov.tmp", tmp)
        rc, stdout, stderr = run_bat("markov.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Markov failed (rc={rc}): {stderr}")
        output = str(CPP_DIR / "output" / "markov.csv")
        return ToolResult(success=True, message=f"Markov prediction for {params['predict_year']} complete", output_paths=[output])
```

- [ ] **Step 4: Write Linear tool**

```python
# agent/tools/linear.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat

class LinearTool(BaseTool):
    name = "linear"
    description = "Predict future LULC using linear regression on multi-year historical data. Output: text printed to terminal (no file)."
    parameters = {
        "type": "object",
        "properties": {
            "image_amount": {"type": "integer", "description": "Number of historical LULC rasters"},
            "predict_amount": {"type": "integer", "description": "Number of years to predict"},
            "image_paths": {"type": "array", "items": {"type": "string"}, "description": "Historical LULC raster paths (chronological order)"},
        },
        "required": ["image_amount", "predict_amount", "image_paths"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<Image Amount>\n{params['image_amount']}\n<Predict Amount>\n{params['predict_amount']}\n<Images Path>\n"
        tmp += "\n".join(params["image_paths"]) + "\n"
        write_tmp("PLUS_Linear.tmp", tmp)
        rc, stdout, stderr = run_bat("linear.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Linear failed (rc={rc}): {stderr}")
        return ToolResult(success=True, message=f"Linear prediction result:\n{stdout}")
```

- [ ] **Step 5: Write LEAS tool**

```python
# agent/tools/leas.py
import os
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
from agent.config import PLUS_BACKEND

class LEASTool(BaseTool):
    name = "leas"
    description = "Land Expansion Analysis Strategy. Uses Random Forest with driving factors to generate per-class land use occurrence probability maps. Input: expansion map + driving factors folder + RF parameters."
    parameters = {
        "type": "object",
        "properties": {
            "input_lulc": {"type": "string", "description": "Expansion extraction result path (expansion module output)"},
            "feature_folder": {"type": "string", "description": "Driving factors folder path (contains elevation, slope, distance rasters, etc.)"},
            "output_probability": {"type": "string", "description": "Output probability basename (e.g. C:/out/potential.tif — will generate potential_band_1.tif, potential_band_2.tif, ...)"},
            "sampling_rate": {"type": "number", "default": 0.01, "description": "Random Forest sampling rate"},
            "m_try": {"type": "integer", "default": 16, "description": "Features sampled per tree"},
            "n_trees": {"type": "integer", "default": 20, "description": "Number of Random Forest trees"},
            "thread_count": {"type": "integer", "default": 8, "description": "Parallel threads"},
        },
        "required": ["input_lulc", "feature_folder", "output_probability"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = (
            f"<Input LULC>\n{params['input_lulc']}\n"
            f"<Input Feature folder>\n{params['feature_folder']}\n"
            f"<Output probability>\n{params['output_probability']}\n"
            f"<Is net exit?>\n0\n"
            f"<Input sampling rate>\n{params.get('sampling_rate', 0.01)}\n"
            f"<mTry>\n{params.get('m_try', 16)}\n"
            f"<Input the number of trees>\n{params.get('n_trees', 20)}\n"
            f"<Is balance?>\n0\n"
            f"<Input thread count>\n{params.get('thread_count', 8)}\n"
            f"<High precision>\n0\n<Update Number>\n0\n<Update Variable>\n0\n"
        )
        write_tmp("PLUS_LEAS.tmp", tmp)
        rc, stdout, stderr = run_bat("leas.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"LEAS failed (rc={rc}): {stderr}")

        base = params["output_probability"]
        dir_name = os.path.dirname(base)
        base_name = os.path.splitext(os.path.basename(base))[0]
        outputs = [
            str(PLUS_BACKEND / "accuracy_record_rf.txt"),
            str(PLUS_BACKEND / "imageminmax.txt"),
        ]
        for i in range(1, 20):
            p = os.path.join(dir_name, f"{base_name}_band_{i}.tif")
            if os.path.exists(p):
                outputs.append(p)
            else:
                break
        return ToolResult(success=True, message=f"LEAS: {len(outputs)-2} probability bands generated", output_paths=outputs)
```

- [ ] **Step 6: Write CARS tool**

```python
# agent/tools/cars.py
import os, glob
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat

class CARSTool(BaseTool):
    name = "cars"
    description = "Core simulation module: CA-based patch-generating simulation. Combines LEAS probability maps, Markov demand, transition rules, and constraints to simulate future LULC. Input: all simulation parameters."
    parameters = {
        "type": "object",
        "properties": {
            "input_classes": {"type": "integer", "description": "Number of land use types (matches probability band count)"},
            "input_lulc": {"type": "string", "description": "Start year LULC raster path (usually the early-year converted LULC)"},
            "probability_paths": {"type": "array", "items": {"type": "string"}, "description": "LEAS probability band paths, one per class"},
            "output_simulation": {"type": "string", "description": "Output simulation result path (e.g. C:/out/simulation.tif — actual output will be simulation_N.tif)"},
            "policy_path": {"type": "string", "default": "", "description": "Optional constraint map path (e.g. water protection). Empty string = no constraint."},
            "neighborhood": {"type": "integer", "default": 3, "description": "Neighborhood window size"},
            "thread_count": {"type": "integer", "default": 8},
            "patch_generation": {"type": "number", "default": 0.2, "description": "Patch generation threshold (0-1)"},
            "expansion_coefficient": {"type": "number", "default": 0.2, "description": "Expansion coefficient (0-1)"},
            "neighborhood_weights": {"type": "string", "description": "Comma-separated weights per class, e.g. '0.033,0.072,0.215,0.449,0.028,0.131,0.072'"},
            "transition_matrix": {"type": "string", "description": "NxN transition matrix. Rows separated by semicolons, values comma-separated. 1=allow, 0=forbid. E.g. '1,1,1;0,1,0;1,1,1'"},
            "yearly_demands": {"type": "string", "description": "Demand string: '1,demand_c1,demand_c2,...' (first number always 1; values from Markov output)"},
            "seed_percentage": {"type": "number", "default": 0.1, "description": "Random seed percentage for patch generation"},
        },
        "required": ["input_classes", "input_lulc", "probability_paths", "output_simulation", "neighborhood_weights", "transition_matrix", "yearly_demands"]
    }

    def execute(self, params: dict) -> ToolResult:
        matrix_str = params["transition_matrix"].replace(";", "\n")
        tmp = (
            f"<Input classes>\n{params['input_classes']}\n"
            f"<Input LULC>\n{params['input_lulc']}\n"
            f"<Input Probability Folder>\n" + "\n".join(params["probability_paths"]) + "\n"
            f"<Output simulation>\n{params['output_simulation']}\n"
            f"<Input Policy>\n{params.get('policy_path', '')}\n"
            f"<Input Neighborhood>\n{params.get('neighborhood', 3)}\n"
            f"<How many years>\n1\n"
            f"<Input thread count>\n{params.get('thread_count', 8)}\n"
            f"<Patch generation>\n{params.get('patch_generation', 0.2)}\n"
            f"<Expansion coefficient>\n{params.get('expansion_coefficient', 0.2)}\n"
            f"<Neighborhood Weight>\n{params['neighborhood_weights']}\n"
            f"<Transition matrix>\n{matrix_str}\n"
            f"<Years and corresponding demands>\n{params['yearly_demands']}\n"
            f"<Percentage of seeds>\n{params.get('seed_percentage', 0.1)}\n"
            f"<Development type exist>\n0\n<Development type>\n0\n<Development weight>\n0.5\n"
        )
        write_tmp("PLUS_CARS.tmp", tmp)
        rc, stdout, stderr = run_bat("cars.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"CARS failed (rc={rc}): {stderr}")

        out_dir = os.path.dirname(params["output_simulation"])
        base = os.path.splitext(os.path.basename(params["output_simulation"]))[0]
        matches = glob.glob(os.path.join(out_dir, f"{base}_*.tif"))
        actual = matches[0] if matches else params["output_simulation"]
        return ToolResult(success=True, message="CARS simulation complete", output_paths=[actual])
```

- [ ] **Step 7: Write Validation tool**

```python
# agent/tools/validation.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
from agent.config import PLUS_BACKEND

class ValidationTool(BaseTool):
    name = "validation"
    description = "Validate simulation accuracy: compare simulated vs real LULC. Computes Kappa coefficient or FoM (Figure of Merit)."
    parameters = {
        "type": "object",
        "properties": {
            "is_fom": {"type": "integer", "default": 0, "description": "0=Kappa, 1=FoM"},
            "sampling_rate": {"type": "number", "default": 0.1},
            "simulated_map": {"type": "string", "description": "Simulated LULC raster path (CARS output)"},
            "real_map": {"type": "string", "description": "Real reference LULC raster path"},
            "start_map": {"type": "string", "description": "Simulation start year LULC raster path"},
        },
        "required": ["simulated_map", "real_map", "start_map"]
    }

    def execute(self, params: dict) -> ToolResult:
        is_fom = params.get("is_fom", 0)
        tmp = (
            f"<IsFom>\n{is_fom}\n"
            f"<Sampling rate>\n{params.get('sampling_rate', 0.1)}\n"
            f"<Simulated Map>\n{params['simulated_map']}\n"
            f"<Real Map>\n{params['real_map']}\n"
            f"<Start Map>\n{params['start_map']}\n"
        )
        write_tmp("PLUS_Validation.tmp", tmp)
        rc, stdout, stderr = run_bat("validate.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Validation failed (rc={rc}): {stderr}")
        name = "FoM.csv" if is_fom else "Kappa.csv"
        return ToolResult(success=True, message=f"Validation ({'FoM' if is_fom else 'Kappa'}) complete", output_paths=[str(PLUS_BACKEND / name)])
```

- [ ] **Step 8: Write Diverse tool**

```python
# agent/tools/diverse.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat

class DiverseTool(BaseTool):
    name = "diverse"
    description = "Ensemble multiple simulation results into a diversity/comparison map."
    parameters = {
        "type": "object",
        "properties": {
            "image_amount": {"type": "integer", "description": "Number of simulation results to ensemble"},
            "image_paths": {"type": "array", "items": {"type": "string"}, "description": "Simulation result raster paths"},
            "output_path": {"type": "string", "description": "Output diversity map path"},
        },
        "required": ["image_amount", "image_paths", "output_path"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<Image Amount>\n{params['image_amount']}\n<Images Path>\n"
        tmp += "\n".join(params["image_paths"]) + "\n"
        tmp += f"<Output Path>\n{params['output_path']}\n"
        write_tmp("PLUS_Diverse.tmp", tmp)
        rc, stdout, stderr = run_bat("diverse.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Diverse failed (rc={rc}): {stderr}")
        return ToolResult(success=True, message="Diversity map generated", output_paths=[params["output_path"]])
```

- [ ] **Step 9: Test all tools instantiate**

Run:
```python
from agent.tools.convert import ConvertTool
from agent.tools.expansion import ExpansionTool
from agent.tools.leas import LEASTool
from agent.tools.markov import MarkovTool
from agent.tools.linear import LinearTool
from agent.tools.cars import CARSTool
from agent.tools.validation import ValidationTool
from agent.tools.diverse import DiverseTool

for cls in [ConvertTool, ExpansionTool, LEASTool, MarkovTool, LinearTool, CARSTool, ValidationTool, DiverseTool]:
    t = cls()
    assert t.name
    assert t.description
    assert t.parameters
    print(f"  {t.name}: OK ({len(t.parameters.get('properties', {}))} params)")
print("All tools OK")
```

- [ ] **Step 10: Commit**

```bash
git add agent/tools/convert.py agent/tools/expansion.py agent/tools/leas.py agent/tools/markov.py agent/tools/linear.py agent/tools/cars.py agent/tools/validation.py agent/tools/diverse.py
git commit -m "feat: add all 8 PLUS module tools"
```

---

### Task 6: ReAct Loop

**Files:**
- Create: `agent/core/__init__.py`
- Create: `agent/core/react_loop.py`

- [ ] **Step 1: Create package init**

```python
# agent/core/__init__.py
from .react_loop import ReactLoop
```

- [ ] **Step 2: Write ReAct loop**

```python
# agent/core/react_loop.py
from agent.config import SYSTEM_PROMPT, MAX_REACT_STEPS
from agent.llm.adapter import BaseLLM
from agent.tools.registry import ToolRegistry
from agent.memory.store import MemoryStore

class ReactLoop:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry, memory: MemoryStore):
        self.llm = llm
        self.registry = registry
        self.memory = memory

    async def run(self, user_message: str, history: list[dict]) -> dict:
        """Execute one ReAct turn.
        Returns: {'type': 'text'|'tool_call', 'content': str, 'tool_results': [...]}
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message},
        ]
        tools = self.registry.get_all_llm_format()
        all_tool_results = []

        for step in range(MAX_REACT_STEPS):
            response = self.llm.chat(messages, tools)

            if response.type == "text":
                return {"type": "text", "content": response.content, "tool_results": all_tool_results}

            if response.type == "tool_call":
                for tc in response.tool_calls:
                    result = self.registry.execute(tc["name"], tc["arguments"])
                    tr = {
                        "tool": tc["name"], "params": tc["arguments"],
                        "success": result.success, "message": result.message,
                        "output_paths": result.output_paths, "error": result.error,
                    }
                    all_tool_results.append(tr)
                    obs = (
                        f"Tool '{tc['name']}' executed.\n"
                        f"Success: {result.success}\n"
                        f"Message: {result.message}\n"
                    )
                    if result.output_paths:
                        obs += f"Output files: {', '.join(result.output_paths)}\n"
                    if result.error:
                        obs += f"Error: {result.error}\n"
                    # Append tool call and result to messages for multi-turn
                    messages.append({"role": "assistant", "content": None,
                                     "tool_calls": [{"name": tc["name"], "arguments": tc["arguments"]}]})
                    messages.append({"role": "tool", "content": obs,
                                     "tool_call_id": tc["name"]})
                continue

        return {"type": "text", "content": f"Reached max steps ({MAX_REACT_STEPS}). Please simplify.", "tool_results": all_tool_results}
```

- [ ] **Step 3: Test ReAct loop with a mock LLM**

Run:
```python
import asyncio
from agent.llm.adapter import BaseLLM, LLMResponse
from agent.tools.registry import ToolRegistry
from agent.tools.base import BaseTool, ToolResult
from agent.memory import MemoryStore
from agent.core.react_loop import ReactLoop
from agent.config import MEMORY_DB_PATH

class MockLLM(BaseLLM):
    def chat(self, msgs, tools):
        return LLMResponse(type="text", content="mock says: I received " + msgs[-1]["content"])

class EchoTool(BaseTool):
    name = "echo"; description = "Echo back"
    parameters = {"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]}
    def execute(self, params): return ToolResult(success=True, message=params["msg"])

reg = ToolRegistry(); reg.register(EchoTool())
mem = MemoryStore(MEMORY_DB_PATH)
loop = ReactLoop(MockLLM(), reg, mem)

result = asyncio.run(loop.run("hello", []))
assert result["type"] == "text"
assert "hello" in result["content"]
print("ReAct loop test passed:", result["content"])
```

- [ ] **Step 4: Commit**

```bash
git add agent/core/__init__.py agent/core/react_loop.py
git commit -m "feat: add ReAct loop"
```

---

### Task 7: Workflow Engine

**Files:**
- Create: `agent/core/workflow_engine.py`

- [ ] **Step 1: Write Workflow engine**

```python
# agent/core/workflow_engine.py
from dataclasses import dataclass, field
from agent.tools.registry import ToolRegistry
from agent.memory.store import MemoryStore

@dataclass
class WorkflowStep:
    tool_name: str
    params: dict

@dataclass
class WorkflowResult:
    success: bool
    steps: list[dict] = field(default_factory=list)
    final_outputs: list[str] = field(default_factory=list)
    error: str = ""
    error_step: str = ""

class WorkflowEngine:
    def __init__(self, registry: ToolRegistry, memory: MemoryStore):
        self.registry = registry
        self.memory = memory

    def execute(self, name: str, steps: list[WorkflowStep]) -> WorkflowResult:
        """Execute sequential tool calls. Stops on first failure. Saves to memory."""
        tool_names = [s.tool_name for s in steps]
        all_params = {s.tool_name: s.params for s in steps}
        all_outputs: list[str] = []

        run_id = self.memory.save_run(name, tool_names, all_params, [])

        for i, step in enumerate(steps):
            self.memory.save_step(run_id, step.tool_name, i, step.params)
            self.memory.update_step_status(run_id, i, "running")
            result = self.registry.execute(step.tool_name, step.params)

            if result.success:
                self.memory.update_step_status(run_id, i, "success")
                all_outputs.extend(result.output_paths)
            else:
                self.memory.update_step_status(run_id, i, "failed", result.error)
                self.memory.update_run_status(run_id, "failed", result.error)
                return WorkflowResult(
                    success=False,
                    steps=[{"tool": step.tool_name, "status": "failed", "error": result.error}],
                    error=result.error, error_step=step.tool_name,
                )

        self.memory.update_run_status(run_id, "success")
        return WorkflowResult(
            success=True,
            steps=[{"tool": s.tool_name, "status": "success"} for s in steps],
            final_outputs=all_outputs,
        )

    @staticmethod
    def build_standard(convert: dict, expansion: dict, leas: dict, markov: dict, cars: dict) -> list[WorkflowStep]:
        """Build the standard 5-step workflow: convert → expansion → leas → markov → cars."""
        return [
            WorkflowStep("convert", convert),
            WorkflowStep("expansion", expansion),
            WorkflowStep("leas", leas),
            WorkflowStep("markov", markov),
            WorkflowStep("cars", cars),
        ]
```

- [ ] **Step 2: Update core/__init__.py**

```python
# agent/core/__init__.py
from .react_loop import ReactLoop
from .workflow_engine import WorkflowEngine, WorkflowStep, WorkflowResult
```

- [ ] **Step 3: Verify import**

Run: `python -c "from agent.core import ReactLoop, WorkflowEngine, WorkflowStep; print('Core OK')"`
Expected: `Core OK`

- [ ] **Step 4: Commit**

```bash
git add agent/core/
git commit -m "feat: add workflow engine for end-to-end simulation"
```

---

### Task 8: UI Renderers

**Files:**
- Create: `agent/ui/__init__.py`
- Create: `agent/ui/renderers.py`

- [ ] **Step 1: Create package init**

```python
# agent/ui/__init__.py
from .renderers import render_raster, render_csv, render_text
```

- [ ] **Step 2: Write renderers**

```python
# agent/ui/renderers.py
import os, tempfile
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from osgeo import gdal
import folium
from folium.raster_layers import ImageOverlay
import chainlit as cl

LULC_COLORS = ['#000000', '#FF0000', '#00FF00', '#0000FF', '#FFFF00',
               '#FF00FF', '#00FFFF', '#808080', '#FFA500', '#A52A2A']


def render_raster(tif_path: str, title: str = "") -> cl.Element:
    """Render GeoTIFF as Folium interactive map. Fallback: Matplotlib static image."""
    if not os.path.exists(tif_path):
        return cl.Text(content=f"[File not found: {os.path.basename(tif_path)}]")
    try:
        return _render_folium(tif_path, title)
    except Exception as e:
        try:
            return _render_matplotlib(tif_path, title)
        except Exception:
            return cl.Text(content=f"[Raster: {os.path.basename(tif_path)}]")


def _render_folium(tif_path: str, title: str) -> cl.Element:
    ds = gdal.Open(tif_path)
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray()
    gt = ds.GetGeoTransform()
    minx, maxy = gt[0], gt[3]
    maxx = minx + gt[1] * ds.RasterXSize
    miny = maxy + gt[5] * ds.RasterYSize
    ds = None

    m = folium.Map(location=[(miny + maxy) / 2, (minx + maxx) / 2],
                   zoom_start=10, tiles="OpenStreetMap")

    scale = max(1, min(data.shape) // 2000)
    if scale > 1:
        data = data[::scale, ::scale]

    unique = np.unique(data)
    n = len(unique)
    colors = LULC_COLORS[:n] if n <= len(LULC_COLORS) else ['#%06X' % (i * 123457) for i in range(n)]
    cmap = ListedColormap(colors)
    bounds = list(unique) + [unique[-1] + 1]
    norm = BoundaryNorm(bounds, cmap.N)
    colored = (cmap(norm(data))[:, :, :3] * 255).astype(np.uint8)

    ImageOverlay(colored, [[miny, minx], [maxy, maxx]], opacity=0.6).add_to(m)
    folium.LayerControl().add_to(m)

    return cl.Html(content=m.get_root().render(), name=title or os.path.basename(tif_path))


def _render_matplotlib(tif_path: str, title: str) -> cl.Element:
    ds = gdal.Open(tif_path)
    data = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    scale = max(1, min(data.shape) // 2000)
    if scale > 1:
        data = data[::scale, ::scale]

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(data, cmap='tab10', interpolation='nearest')
    plt.colorbar(im, ax=ax, label='Class')
    ax.set_title(title or os.path.basename(tif_path))
    ax.axis('off')
    plt.tight_layout()

    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    fig.savefig(tmp.name, dpi=100)
    plt.close(fig)
    return cl.Image(path=tmp.name, name=title or "Raster Preview")


def render_csv(csv_path: str) -> cl.Element:
    """Render CSV as formatted text table."""
    if not os.path.exists(csv_path):
        return cl.Text(content=f"[File not found: {os.path.basename(csv_path)}]")
    import pandas as pd
    df = pd.read_csv(csv_path)
    return cl.Text(content=f"```\n{df.to_string()}\n```", language="text")


def render_text(text: str, title: str = "") -> cl.Text:
    """Render plain text."""
    return cl.Text(content=text, name=title)
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from agent.ui.renderers import render_raster, render_csv, render_text; print('Renderers OK')"`
Expected: `Renderers OK`

- [ ] **Step 4: Commit**

```bash
git add agent/ui/__init__.py agent/ui/renderers.py
git commit -m "feat: add UI renderers (Folium + Matplotlib + CSV)"
```

---

### Task 9: Chainlit Callbacks + Main Entry

**Files:**
- Create: `agent/ui/callbacks.py`
- Create: `agent/main.py`

- [ ] **Step 1: Write callbacks**

```python
# agent/ui/callbacks.py
import os
import chainlit as cl
from agent.config import LLM_BACKEND, LLM_CONFIG
from agent.llm.adapter import create_llm
from agent.tools.registry import ToolRegistry
from agent.tools.convert import ConvertTool
from agent.tools.expansion import ExpansionTool
from agent.tools.leas import LEASTool
from agent.tools.markov import MarkovTool
from agent.tools.linear import LinearTool
from agent.tools.cars import CARSTool
from agent.tools.validation import ValidationTool
from agent.tools.diverse import DiverseTool
from agent.memory import MemoryStore
from agent.core.react_loop import ReactLoop
from agent.ui.renderers import render_raster, render_csv

_loop: ReactLoop | None = None
_memory: MemoryStore | None = None

def _init():
    global _loop, _memory
    if _loop is not None:
        return
    db_path = os.environ.get("PLUS_MEMORY_DB", "data/memory.db")
    _memory = MemoryStore(db_path)
    registry = ToolRegistry()
    registry.register(ConvertTool())
    registry.register(ExpansionTool())
    registry.register(LEASTool())
    registry.register(MarkovTool())
    registry.register(LinearTool())
    registry.register(CARSTool())
    registry.register(ValidationTool())
    registry.register(DiverseTool())
    cfg = LLM_CONFIG.get(LLM_BACKEND, LLM_CONFIG["claude"])
    llm = create_llm(LLM_BACKEND, cfg)
    _loop = ReactLoop(llm, registry, _memory)


@cl.on_chat_start
async def on_chat_start():
    _init()
    runs = _memory.get_recent_runs(3)
    paths = _memory.get_frequent_paths()
    welcome = "Hello! I'm **PLUS Agent**, your land use simulation assistant.\n\n"
    if runs:
        welcome += "### Recent Runs\n"
        for r in runs:
            icon = "✅" if r["status"] == "success" else "❌"
            welcome += f"- {icon} **{r['name']}** ({r['created_at'][:10]})\n"
    if paths:
        welcome += f"\n**Saved paths:** {', '.join(paths[:3])}\n"
    welcome += f"\nLLM backend: `{LLM_BACKEND}`"
    await cl.Message(content=welcome).send()


@cl.on_message
async def on_message(message: cl.Message):
    _init()
    result = await _loop.run(message.content, [])

    if result["type"] == "text" and result["content"]:
        await cl.Message(content=result["content"]).send()

    for tr in result.get("tool_results", []):
        async with cl.Step(name=tr["tool"]) as step:
            step.input = str(tr.get("params", {}))
            if tr["success"]:
                msg = f"✅ {tr.get('message', '')}"
                if tr.get("output_paths"):
                    msg += "\n\n**Outputs:**\n" + "\n".join(f"- `{p}`" for p in tr["output_paths"])
                step.output = msg
                for path in tr.get("output_paths", []):
                    ext = path.lower()
                    if ext.endswith(".tif") or ext.endswith(".tiff"):
                        elem = render_raster(path, os.path.basename(path))
                        if elem:
                            step.elements = [elem]
                    elif ext.endswith(".csv"):
                        elem = render_csv(path)
                        if elem:
                            step.elements = [elem]
            else:
                step.output = f"❌ **Error:** {tr.get('error', 'Unknown')}"
```

- [ ] **Step 2: Write main entry point**

```python
# agent/main.py
"""PLUS Agent - Chainlit entry point.

Usage:
    conda activate plus-agent
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
from agent.config import MEMORY_DB_PATH

if not os.environ.get("PLUS_MEMORY_DB"):
    os.environ["PLUS_MEMORY_DB"] = MEMORY_DB_PATH

import agent.ui.callbacks  # noqa: E402, F401 — registers Chainlit handlers
```

- [ ] **Step 3: Verify Chainlit discovers the app**

Run: `chainlit run agent/main.py --help 2>&1 | head -5`
Expected: Shows Chainlit usage help

- [ ] **Step 4: Commit**

```bash
git add agent/ui/callbacks.py agent/main.py
git commit -m "feat: add Chainlit callbacks and main entry point"
```

---

### Task 10: Integration Verification

- [ ] **Step 1: Verify all imports work end-to-end**

Run:
```python
import os
os.environ["PLUS_MEMORY_DB"] = "data/test_memory.db"

from agent.config import PROJECT_ROOT, LLM_BACKEND, LLM_CONFIG
from agent.llm import create_llm
from agent.tools.registry import ToolRegistry
from agent.tools.convert import ConvertTool
from agent.tools.expansion import ExpansionTool
from agent.tools.leas import LEASTool
from agent.tools.markov import MarkovTool
from agent.tools.linear import LinearTool
from agent.tools.cars import CARSTool
from agent.tools.validation import ValidationTool
from agent.tools.diverse import DiverseTool
from agent.memory import MemoryStore
from agent.core import ReactLoop
from agent.ui.renderers import render_raster, render_csv, render_text

registry = ToolRegistry()
for tool_cls in [ConvertTool, ExpansionTool, LEASTool, MarkovTool, LinearTool, CARSTool, ValidationTool, DiverseTool]:
    registry.register(tool_cls())
    print(f"  Registered: {tool_cls.name}")

names = registry.get_all_names()
assert len(names) == 8, f"Expected 8 tools, got {len(names)}"
print(f"All {len(names)} tools registered: {names}")

llm_format = registry.get_all_llm_format()
assert len(llm_format) == 8
print(f"LLM format: {len(llm_format)} tool definitions")

print("Integration verification PASSED")
```

- [ ] **Step 2: Clean up test DB**

Run: `rm -f data/test_memory.db` (or `del data\test_memory.db` on Windows)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: integration verification"
```

---

## Post-Implementation Checklist

- [ ] Run `setup.bat` / `setup.sh` to verify clean setup
- [ ] Set `ANTHROPIC_API_KEY` (or other LLM key) and start `chainlit run agent/main.py`
- [ ] Test: "list available tools" → should show all 8
- [ ] Test: "I want to simulate land use for 2033" → should ask for files step by step
- [ ] Test: Tool step cards render with Folium maps for .tif outputs
- [ ] Test: Memory persists — restart app, should see recent runs in welcome message
