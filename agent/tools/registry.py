# agent/tools/registry.py
from .base import BaseTool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_all_llm_format(self) -> list[dict]:
        return [t.to_llm_format() for t in sorted(self._tools.values(), key=lambda t: t.name)]

    def get_all_names(self) -> list[str]:
        return sorted(self._tools.keys())

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def execute(self, name: str, params: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"Unknown tool: {name}")
        if not tool.validate(params):
            return ToolResult(success=False, error=f"Invalid params for {name}")
        return tool.execute(params)
