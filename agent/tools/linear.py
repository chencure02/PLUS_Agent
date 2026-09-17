# agent/tools/linear.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import run_plus_job


class LinearTool(BaseTool):
    name = "linear"
    description = "Predict future LULC using linear regression on multi-year historical data. Output: text printed to terminal (no file)."
    parameters = {
        "type": "object",
        "properties": {
            "predict_amount": {"type": "integer", "description": "Number of years to predict"},
            "image_paths": {"type": "array", "items": {"type": "string"}, "description": "Historical LULC raster paths (chronological order)"},
        },
        "required": ["predict_amount", "image_paths"]
    }

    def execute(self, params: dict) -> ToolResult:
        image_amount = len(params["image_paths"])
        tmp = f"<Image Amount>\n{image_amount}\n<Predict Amount>\n{params['predict_amount']}\n<Images Path>\n"
        tmp += "\n".join(params["image_paths"]) + "\n"
        rc, stdout, stderr = run_plus_job("PLUS_Linear.tmp", tmp, "linear.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Linear failed (rc={rc}): {stderr}")
        output = stdout[:2000] + ("...(truncated)" if len(stdout) > 2000 else "")
        return ToolResult(success=True, message=f"Linear prediction result:\n{output}")
