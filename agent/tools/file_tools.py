"""File browsing tools — let the Agent explore the local filesystem."""
import os
import glob as glob_mod
from pathlib import Path
from agent.tools.base import BaseTool, ToolResult


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "列出指定目录下的所有文件和子目录。可指定扩展名过滤（如 .tif）。用于浏览本地文件夹，发现可用的数据文件。"
    confirm_before_execute = False
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要列出内容的目录绝对路径"},
            "extension": {"type": "string", "description": "可选：只列出指定扩展名的文件，如 .tif .csv .txt"},
        },
        "required": ["path"]
    }

    def execute(self, params: dict) -> ToolResult:
        p = Path(params["path"])
        if not p.exists():
            return ToolResult(success=False, error=f"路径不存在：{params['path']}")
        if not p.is_dir():
            # Try parent directory
            p = p.parent
            if not p.is_dir():
                return ToolResult(success=False, error=f"不是目录：{params['path']}")

        ext = params.get("extension", "").strip().lower()
        items = []
        try:
            for entry in sorted(p.iterdir()):
                name = entry.name
                if entry.is_dir():
                    items.append(f"[DIR]  {name}/")
                elif not ext or name.lower().endswith(ext):
                    size_kb = entry.stat().st_size / 1024
                    items.append(f"       {name}  ({size_kb:.1f} KB)")
            if not items:
                msg = f"目录 `{p}` 为空" + (f"（过滤: *{ext}）" if ext else "")
            else:
                msg = f"**{p}** 的内容（{len(items)} 项）：\n" + "\n".join(items)
            return ToolResult(success=True, message=msg)
        except PermissionError:
            return ToolResult(success=False, error=f"没有权限读取：{p}")


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取文本文件内容（.txt .csv .json 等）。用于查看参数配置、模型输出表格、精度记录等。"
    confirm_before_execute = False
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要读取的文件绝对路径"},
            "max_lines": {"type": "integer", "default": 100, "description": "最多读取行数，默认 100"},
        },
        "required": ["path"]
    }

    def execute(self, params: dict) -> ToolResult:
        path = params["path"]
        if not os.path.exists(path):
            return ToolResult(success=False, error=f"文件不存在：{path}")
        if not os.path.isfile(path):
            return ToolResult(success=False, error=f"不是文件：{path}")
        max_lines = params.get("max_lines", 100)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"...（截断，共 {max_lines} 行，文件可能更大）")
                        break
                    lines.append(line.rstrip())
            content = "\n".join(lines)
            return ToolResult(success=True, message=f"**{os.path.basename(path)}** 的内容：\n```\n{content}\n```")
        except PermissionError:
            return ToolResult(success=False, error=f"没有权限读取：{path}")
        except Exception as e:
            return ToolResult(success=False, error=f"读取失败：{e}")


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "在指定目录下递归搜索匹配模式的文件（如 *.tif, wh*）。用于在大型数据目录中快速定位文件。"
    confirm_before_execute = False
    parameters = {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "搜索的根目录绝对路径"},
            "pattern": {"type": "string", "description": "文件名模式，如 *.tif, wh*, *landuse*"},
        },
        "required": ["directory", "pattern"]
    }

    def execute(self, params: dict) -> ToolResult:
        directory = params["directory"]
        pattern = params["pattern"]
        if not os.path.isdir(directory):
            return ToolResult(success=False, error=f"目录不存在：{directory}")
        try:
            matches = sorted(glob_mod.glob(
                os.path.join(directory, "**", pattern),
                recursive=True
            ))
            if not matches:
                return ToolResult(success=True, message=f"在 `{directory}` 中没有找到匹配 `{pattern}` 的文件")
            lines = []
            for m in matches[:50]:
                rel = os.path.relpath(m, directory)
                size_kb = os.path.getsize(m) / 1024
                lines.append(f"       {rel}  ({size_kb:.1f} KB)")
            msg = f"在 `{directory}` 中搜索 `{pattern}`：找到 {len(matches)} 个文件\n" + "\n".join(lines)
            if len(matches) > 50:
                msg += f"\n...（仅显示前 50 个）"
            return ToolResult(success=True, message=msg)
        except PermissionError:
            return ToolResult(success=False, error=f"没有权限搜索：{directory}")
