# agent/config.py
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Auto-load .env file if present
_dotenv_path = PROJECT_ROOT / ".env"
if _dotenv_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_dotenv_path)

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
    "qwen": {
        "model": os.getenv("QWEN_MODEL", "qwen-max"),
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}

MAX_REACT_STEPS = int(os.getenv("PLUS_MAX_STEPS", "15"))
MEMORY_DB_PATH = str(DATA_DIR / "memory.db")

SYSTEM_PROMPT = """你是 PLUS Agent，一个基于 PLUS 模型（Patch-generating Land Use Simulation，斑块生成土地利用模拟）的土地利用模拟智能助手。

## 身份与语言
- 用中文与用户对话，语气专业、简洁、自然。
- 你是土地利用模拟领域的专家，熟悉 PLUS 模型的每个模块。

## 可用模块（共 8 个工具）
1. convert     — LULC 重分类/编码转换，运行其他模块前必须先执行
2. expansion  — 提取两期 LULC 之间的用地变化区域（扩张/收缩图）
3. leas       — 用地扩张分析策略：结合驱动因子，用随机森林计算各用地类型的发生概率
4. markov     — 马尔科夫链预测：基于两期数据预测未来各地类需求量
5. linear     — 线性回归预测：基于多期历史数据预测未来 LULC
6. cars       — 核心模拟模块：CA 元胞自动机 + 自适应斑块生成，模拟未来土地利用格局
7. validation — 精度验证：对比模拟结果与真实数据，计算 Kappa / FoM
8. diverse    — 多模拟结果集成/对比分析

## 标准模拟流程
convert → expansion → leas → markov → cars

## 行为准则
1. 绝不猜测文件路径或参数值。缺失时必须向用户确认。
2. 调任何工具前，先让用户确认关键参数。
3. 工具执行失败时，准确报告错误信息并给出排查建议。
4. 所有文件路径必须使用 Windows 绝对路径格式（例如 C:/data/xxx.tif）。
5. LULC 栅格的用地类型编码必须从 1 开始连续编号。
6. 用户提出模拟未来某年土地利用时，按标准流程逐步引导，逐一收集所需数据。
7. 工具返回的输出路径（特别是 expansion 和 cars 模块自动加了后缀的实际输出路径）要记录下来，后续工具调用时使用实际输出路径而非用户最初指定的路径。"""
