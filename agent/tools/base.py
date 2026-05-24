# agent/tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from copy import deepcopy


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

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if ABC in cls.__bases__:
            return
        if not cls.name:
            raise TypeError(f"{cls.__name__} must define a non-empty 'name' class attribute")

    def validate(self, params: dict) -> bool:
        required = self.parameters.get("required", [])
        return all(k in params for k in required)

    @abstractmethod
    def execute(self, params: dict) -> ToolResult:
        ...

    def to_llm_format(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": deepcopy(self.parameters),
        }
