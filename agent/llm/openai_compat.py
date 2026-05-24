# agent/llm/openai_compat.py
import os, json
from openai import OpenAI
from .adapter import BaseLLM, LLMResponse, LLMError


class OpenAICompatAdapter(BaseLLM):
    def __init__(self, config: dict):
        # Validate required config keys
        api_key_env = config.get("api_key_env")
        if not api_key_env:
            raise ValueError(
                "Missing required config key 'api_key_env'. "
                "Set the environment variable name that holds your API key."
            )
        self.model = config.get("model")
        if not self.model:
            raise ValueError(
                "Missing required config key 'model'. "
                "Set the model name (e.g. 'gpt-4o', 'deepseek-chat')."
            )

        api_key = os.getenv(api_key_env, "")
        if not api_key:
            raise ValueError(f"Environment variable '{api_key_env}' is not set or is empty.")
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
