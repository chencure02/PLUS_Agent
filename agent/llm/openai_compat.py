# agent/llm/openai_compat.py
import os, json
from openai import OpenAI
from .adapter import BaseLLM, LLMResponse, LLMError


class OpenAICompatAdapter(BaseLLM):
    def __init__(self, config: dict):
        self.model = config.get("model")
        if not self.model:
            raise ValueError(
                "Missing required config key 'model'. "
                "Set the model name (e.g. 'gpt-4o', 'deepseek-chat')."
            )

        # Prefer direct api_key, fall back to env var
        api_key = config.get("api_key") or os.getenv(config.get("api_key_env", ""), "")
        if not api_key:
            raise ValueError(
                "No API key provided. Set it via the settings panel or environment variable."
            )
        self.client = OpenAI(api_key=api_key, base_url=config.get("base_url"))
        self.max_tokens = int(config.get("max_tokens", 4096))

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise LLMError(f"OpenAI-compatible API call failed: {e}") from e

        msg = response.choices[0].message

        reasoning = getattr(msg, "reasoning_content", "") or ""

        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({"name": tc.function.name, "arguments": args})
            return LLMResponse(type="tool_call", tool_calls=tool_calls, content=msg.content or "", reasoning_content=reasoning)

        return LLMResponse(type="text", content=msg.content or "", reasoning_content=reasoning)
