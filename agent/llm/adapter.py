# agent/llm/adapter.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


class LLMError(Exception):
    """Raised when LLM API calls fail."""
    pass


@dataclass
class LLMResponse:
    type: Literal["text", "tool_call", "ask_user"]
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    reasoning_content: str = ""


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        ...


def create_llm(backend: str, config: dict) -> BaseLLM:
    valid_backends = {"claude", "openai", "deepseek", "qwen"}
    if backend not in valid_backends:
        raise ValueError(
            f"Unknown LLM backend: {backend!r}. "
            f"Valid backends: {sorted(valid_backends)}"
        )
    if backend == "claude":
        from .claude_adapter import ClaudeAdapter
        return ClaudeAdapter(config)
    else:
        from .openai_compat import OpenAICompatAdapter
        return OpenAICompatAdapter(config)
