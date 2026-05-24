# agent/llm/claude_adapter.py
import os
from anthropic import Anthropic
from .adapter import BaseLLM, LLMResponse, LLMError


class ClaudeAdapter(BaseLLM):
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
                "Set the model name (e.g. 'claude-sonnet-4-20250514')."
            )

        api_key = os.getenv(api_key_env, "")
        if not api_key:
            raise ValueError(f"Environment variable '{api_key_env}' is not set or is empty.")
        self.client = Anthropic(api_key=api_key)
        self.max_tokens = int(config.get("max_tokens", 4096))

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        system = None
        api_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            elif m["role"] == "assistant" and m.get("tool_calls"):
                content_blocks = []
                if m.get("content"):
                    content_blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    func = tc.get("function", tc)
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"call_{func['name']}"),
                        "name": func["name"],
                        "input": func["arguments"] if isinstance(func["arguments"], dict) else {},
                    })
                api_messages.append({"role": "assistant", "content": content_blocks})
            elif m["role"] == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }]
                })
            else:
                api_messages.append({"role": m["role"], "content": m.get("content", "")})

        kwargs = {"model": self.model, "messages": api_messages, "max_tokens": self.max_tokens}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [{
                "name": t["name"], "description": t["description"],
                "input_schema": t["parameters"],
            } for t in tools]

        try:
            response = self.client.messages.create(**kwargs)
        except Exception as e:
            raise LLMError(f"Claude API call failed: {e}") from e

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
