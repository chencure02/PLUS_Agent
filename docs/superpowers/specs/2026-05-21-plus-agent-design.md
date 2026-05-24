# PLUS Agent 系统设计文档

## 概述

基于 PLUS 模型（Patch-generating Land Use Simulation）的智能 Agent 系统。采用 ReAct 架构，将 PLUS 模型的 8 个功能模块封装为可调用工具，通过 LLM 驱动的对话界面，使用户能够以自然语言交互方式进行土地利用模拟。

### 设计目标

1. Agent 能通过用户提问判断调用哪个工具，运行过程中向用户确认文件及参数
2. 工具具有可扩展性，方便后续加入新工具
3. 支持端到端模拟：用户指定目标年份，Agent 引导确认数据及参数后自动完成全流程
4. 三层记忆机制：会话级、项目级、知识级
5. Conda 创建隔离环境
6. 清晰标准的目录结构
7. Chainlit 对话界面，支持工具调用可视化及栅格图预览

---

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11 |
| 对话界面 | Chainlit |
| LLM 后端 | Claude / OpenAI / DeepSeek / Qwen（多后端可切换） |
| LLM SDK | anthropic, openai, dashscope |
| 栅格预览 | Folium（主）+ Matplotlib（备用） |
| 数据存储 | SQLite |
| 环境管理 | Conda（隔离环境）+ pip（依赖管理） |
| 栅格读取 | GDAL（conda-forge 安装） |

---

## 目录结构

```
PLUS_Agent/
├── CLAUDE.md                       # 项目说明（已有）
├── requirements.txt                # pip 依赖
├── setup.bat                       # Windows 一键安装
├── setup.sh                        # Linux/Mac 一键安装
├── plus-backend/                   # PLUS 运行包（已有，不动）
│   ├── cpp/                        # PLUS.exe + DLL
│   │   └── output/                 # 部分模块默认输出目录
│   ├── *.bat                       # 8 个模块批处理脚本
│   └── PLUS_*.tmp                  # 8 个模块参数模板
├── agent/                          # Agent 系统主目录
│   ├── __init__.py
│   ├── main.py                     # Chainlit 入口
│   ├── config.py                   # 全局配置（路径、LLM 后端、默认参数）
│   ├── core/
│   │   ├── __init__.py
│   │   ├── react_loop.py           # ReAct 循环（Thought→Action→Observation）
│   │   └── workflow_engine.py      # 标准流水线引擎（端到端模拟）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py             # 工具注册中心
│   │   ├── base.py                 # BaseTool 基类
│   │   ├── convert.py              # Convert 工具
│   │   ├── expansion.py            # Expansion 工具
│   │   ├── leas.py                 # LEAS 工具
│   │   ├── markov.py               # Markov 工具
│   │   ├── linear.py               # Linear 工具
│   │   ├── cars.py                 # CARS 工具
│   │   ├── validation.py           # Validation 工具
│   │   └── diverse.py              # Diverse 工具
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── adapter.py              # BaseLLM 统一接口 + LLMResponse
│   │   └── openai_compat.py        # OpenAI 兼容适配器（OpenAI/DeepSeek/Qwen-Compat）
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py                # MemoryStore 封装
│   │   └── schema.sql              # 数据库 DDL
│   └── ui/
│       ├── __init__.py
│       ├── callbacks.py            # Chainlit 生命周期回调
│       └── renderers.py            # 结果渲染（Folium 交互地图 / Matplotlib 静态图 / 表格）
├── data/
│   └── memory.db                   # SQLite 数据库（运行时生成）
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-21-plus-agent-design.md  # 本文档
```

---

## Agent Core

### ReAct 循环

核心流程为 `Thought → Action → Observation` 三阶段循环：

```
用户输入
  ↓
┌──────────────────────────────────────┐
│  ReAct Loop（agent/core/react_loop.py）│
│                                      │
│  1. 组装 messages                    │
│     系统提示 + 工具列表（JSON Schema）  │
│     + 对话历史 + 用户消息              │
│         ↓                            │
│  2. 调用 LLM: adapter.chat(messages,  │
│     tools) → LLMResponse             │
│         ↓                            │
│  3. 解析 LLMResponse:                │
│     ├── type="tool_call"              │
│     │   → 执行工具，结果作为           │
│     │     Observation 追加到 messages  │
│     │   → 回到步骤 1                  │
│     ├── type="text"                   │
│     │   → 展示给用户，等待确认/继续    │
│     │   → 用户有后续则回到步骤 1       │
│     └── type="ask_user"               │
│         → 向用户提问，等待回复         │
│         → 回到步骤 1                  │
│         ↓                            │
│  4. 终止条件：LLM 返回 final answer   │
│     且无需后续操作                     │
└──────────────────────────────────────┘
```

**关键设计决策：**

- **ask_user 机制**：LLM 不自行猜测参数，缺失信息时返回 ask_user 响应，Agent 将其路由到用户
- **最大步数限制**：15 步硬限制，防止无限循环
- **错误回传**：工具异常时，错误详情作为 Observation 回传 LLM，由 LLM 决定重试策略
- **工具列表透传**：每次 LLM 调用附带当前可用工具，注册中心新增工具自动反映

### Workflow 引擎

处理端到端模拟的独立执行器，不经过 ReAct 循环以节省 LLM 调用成本：

```
Workflow: 模拟未来土地利用（agent/core/workflow_engine.py）
  Step 1: convert   ──→ converted_start.tif, converted_end.tif
  Step 2: expansion ──→ expansion.tif
  Step 3: leas      ──→ potential_band_*.tif
  Step 4: markov    ──→ markov.csv
  Step 5: cars      ──→ simulation_xxxxx.tif
```

**设计特性：**

- 用户确认全部参数后一次性串行执行
- 每步输出进度，中间产物可追溯
- **数据校验**：每步执行前检查上一步的输出文件是否存在、栅格元数据一致性（投影/分辨率/范围）
- 任一步失败立即终止，报告失败位置及原因
- 与 ReAct 循环独立，可单独测试

---

## 工具系统

### BaseTool 基类

```python
class BaseTool:
    name: str              # convert, expansion, leas, ...
    description: str       # LLM 用于判断何时调用此工具
    parameters: dict       # JSON Schema 格式的参数定义

    def validate(params) → bool
    def execute(params) → ToolResult   # 参数写入 tmp → subprocess 调 bat → 解析产物
    def to_llm_format() → dict         # 转为 LLM function calling 格式
```

### 工具注册中心

```python
class ToolRegistry:
    _tools: dict[str, BaseTool] = {}

    def register(tool: BaseTool)
    def get_all() → list[dict]       # 获取所有工具的 LLM function 定义
    def get(name) → BaseTool
    def execute(name, params)         # 按名执行
```

新增工具只需：`class NewTool(BaseTool)` → `registry.register(NewTool())`，零侵入。

### 8 个 PLUS 模块工具

每个工具的 `execute()` 内部流程：**参数校验 → 生成 tmp 文件 → subprocess 调用 bat → 解析产物路径 → 返回 ToolResult**

| 工具 | 核心输入参数 | 产物 |
|------|-------------|------|
| `convert` | N 张 LULC 路径 + N 个输出路径 | N 张转换后栅格 |
| `expansion` | 两期 LULC 路径 + 输出变化图路径 | 1 张扩张图 |
| `leas` | 扩张图路径 + 驱动因子文件夹 + mTry/tree 数/采样率/线程数 + 输出概率图路径 | N 张概率图 + accuracy_record_rf.txt + imageminmax.txt |
| `markov` | 起始栅格 + 结束栅格 + 起始年 + 结束年 + 目标年 | markov.csv |
| `linear` | N 张历史 LULC + 预测年数 | 终端输出文本 |
| `cars` | 类型数 + LULC + 概率图列表 + 需求量(年份,各类型值) + 转换矩阵 + 邻域权重 + 斑块生成/扩张系数/邻域大小/种子比例 + 输出路径 + 约束图(可选) | 1 张模拟图 |
| `validation` | 模拟图 + 真实图 + 起始图 + IsFom 标志 + 采样率 | Kappa.csv 或 FoM.csv |
| `diverse` | N 张模拟结果 + 输出路径 | 1 张多样性图 |

### 工具扩展

```
agent/tools/
├── base.py          # BaseTool（不修改）
├── registry.py      # ToolRegistry（不修改）
├── convert.py       # 8 个 PLUS 工具
├── ...
└── <future>.py      # 后续新增：clip_raster, gdal_info, zonal_stats 等
```

---

## LLM 适配器层

### 统一接口

```python
class BaseLLM:
    def chat(messages: list[dict], tools: list[dict]) -> LLMResponse

class LLMResponse:
    type: Literal["text", "tool_call", "ask_user"]
    content: str
    tool_calls: list[dict] | None
```

### 适配器实现

| 适配器 | 后端 | SDK | 说明 |
|--------|------|-----|------|
| `ClaudeAdapter` | Claude API | `anthropic` | 原生 tool_use |
| `OpenAIAdapter` | OpenAI / DeepSeek / Qwen-Compat | `openai` | 统一走 function calling |

`QwenAdapter`（`dashscope` SDK）作为备选，Qwen 优先走 `OpenAIAdapter` + `qwen-compat` base_url。

### 配置切换

```python
# agent/config.py
LLM_BACKEND = "claude"    # claude | openai | deepseek | qwen-compat
LLM_CONFIG = {
    "claude": {
        "model": "claude-sonnet-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "model": "gpt-4o",
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
```

切换后端只需改环境变量或 `LLM_BACKEND` 值，Adapter 对上层（Agent Core）完全透明。

### 响应归一化

各 API 返回格式差异在适配器内部抹平，统一输出 `LLMResponse`：

```
Claude:  content_block=[text, tool_use, ...]
OpenAI:  choice.message=[content, tool_calls, ...]
DeepSeek:  choice.message=[content, tool_calls, ...]
Qwen-Compat:  output.choices[0].message=[...]
          ↓ 归一化
LLMResponse(type="text"|"tool_call"|"ask_user", content=..., tool_calls=[...])
```

---

## 记忆系统

### 三层架构

```
Layer 1: 会话记忆 — Chainlit 原生管理当前对话上下文
Layer 2: 项目记忆 — 模拟运行记录、每步详情、产物路径（SQLite）
Layer 3: 知识记忆 — 用户偏好、常用路径、对话摘要（SQLite）
```

### SQLite 表结构

```sql
-- 模拟运行记录
CREATE TABLE simulation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    workflow_json TEXT,         -- 执行的步骤列表（JSON）
    params_json TEXT,           -- 完整参数集（JSON）
    output_paths_json TEXT,     -- 产物路径列表（JSON）
    status TEXT DEFAULT 'running',  -- running | success | failed | partial
    error_message TEXT,
    duration_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 运行步骤详情
CREATE TABLE run_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES simulation_runs(id),
    tool_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    params_json TEXT,           -- 该步参数（JSON）
    tmp_content TEXT,           -- 生成的 tmp 文件内容
    output_paths_json TEXT,     -- 该步产物（JSON）
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP
);

-- 用户偏好
CREATE TABLE user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 会话摘要（长期上下文回溯）
CREATE TABLE conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT,
    key_decisions_json TEXT,    -- 本次会话的关键决策（JSON）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### MemoryStore 接口

```python
class MemoryStore(db_path: str):
    # 项目记忆
    def save_run(name, workflow, params, outputs) → int          # 返回 run_id
    def update_run_status(run_id, status, error=None)
    def save_step(run_id, tool_name, order, params, tmp, outputs)
    def get_recent_runs(limit=5) → list[dict]
    def get_run_detail(run_id) → dict                            # 含所有步骤

    # 知识记忆
    def get_preference(key) → str | None
    def set_preference(key, value)
    def get_frequent_paths() → list[str]
    def save_summary(session_id, summary, decisions)
    def get_recent_summaries(limit=3) → list[dict]
```

### 典型使用场景

| 场景 | 调用 |
|------|------|
| 用户："和上次一样参数再跑一次" | `get_recent_runs(1)` → 取出参数 → 确认后执行 |
| 用户："我的数据在 D:/data" | `set_preference("data_root", "D:/data")` |
| 新会话启动 | `get_recent_runs(3)` + `get_frequent_paths()` → 展示上下文卡片 |

---

## 对话界面（Chainlit）

### 界面布局

- **对话区**：LLM 与用户的标准对话流
- **工具调用卡片**：每个工具调用渲染为可折叠的 `cl.Step`，含参数摘要、状态图标、耗时、产物文件列表
- **产物展示**：栅格图 → Folium 交互地图（OSM 底图 + 栅格叠加），fallback → Matplotlib 静态配色图；CSV → 表格渲染；文件 → 下载链接
- **设置面板**（右上角）：LLM 后端切换、API Key 填写、运行历史浏览
- **启动欢迎**：读取 `MemoryStore` 展示最近运行记录和常用路径

### Chainlit 集成

```python
# agent/ui/callbacks.py
@cl.on_chat_start
async def on_chat_start():
    # 初始化 MemoryStore，加载最近运行记录
    # 发送欢迎消息（含上下文卡片）

@cl.on_message
async def on_message(message: cl.Message):
    # 构造 messages，调用 ReAct 循环
    # 每步工具调用通过 cl.Step 渲染：
    #   async with cl.Step(name="LEAS") as step:
    #       step.input = params_json
    #       result = registry.execute(tool_name, params)
    #       step.output = format_output(result)
    #       for elem in result.elements:
    #           step.elements.append(elem)
    # 返回最终结果给用户
```

### 栅格图预览

- **主方案（Folium）**：GDAL 读取 TIFF → 下采样 + 配色 → Folium 生成 HTML（OSM 底图 + 栅格叠加层）→ Chainlit `cl.Element` 嵌入 iframe。支持缩放、平移。
- **备用方案（Matplotlib）**：GDAL 读取 → Matplotlib 配色谱渲染 → PNG → Chainlit `cl.Image` 直接显示。大图时自动降采样。

---

## 环境配置

### 安装流程

GDAL 在 Windows 上 pip 安装需编译 C++ 扩展，因此采用 conda 安装 GDAL + pip 安装其余依赖的策略：

```bash
conda create -n plus-agent python=3.11 -y
conda activate plus-agent
conda install -c conda-forge gdal -y
pip install -r requirements.txt
```

### requirements.txt

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

### 一键脚本

提供 `setup.bat`（Windows）和 `setup.sh`（Linux/Mac），自动完成以上三步。

---

## 数据流总览

```
┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ 用户输入   │───→│ Chainlit UI   │───→│  ReAct Loop  │───→│  LLM Adapter │
│          │    │ (callbacks)  │    │ (react_loop) │    │ (openai/     │
│          │    │              │    │              │    │  anthropic)  │
└──────────┘    └──────────────┘    └──────┬───────┘    └──────────────┘
                                           │
                         ┌─────────────────┼─────────────────┐
                         ↓                 ↓                  ↓
                  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                  │ Tool Registry│  │   Workflow   │  │ Memory Store │
                  │  (8 tools)   │  │   Engine     │  │  (SQLite)    │
                  └──────┬───────┘  └──────┬───────┘  └──────────────┘
                         │                 │
                         ↓                 ↓
                  ┌──────────────────────────────────────┐
                  │         PLUS 运行包 (plus-backend/)    │
                  │  写入 tmp → subprocess 调用 bat →   │
                  │  PLUS.exe 执行 → 解析产物            │
                  └──────────────────────────────────────┘
```

---

## 待定项（后续迭代）

- 多个模拟结果的同时可视化对比
- 工具执行进度的实时流式推送
- 模拟参数推荐（基于历史运行记录）

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-05-21 | 初始版本 |
