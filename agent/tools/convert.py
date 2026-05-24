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
