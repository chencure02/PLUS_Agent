# agent/tools/diverse.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat


class DiverseTool(BaseTool):
    name = "diverse"
    description = "Ensemble multiple simulation results into a diversity/comparison map."
    parameters = {
        "type": "object",
        "properties": {
            "image_paths": {"type": "array", "items": {"type": "string"}, "description": "Simulation result raster paths"},
            "output_path": {"type": "string", "description": "Output diversity map path"},
        },
        "required": ["image_paths", "output_path"]
    }

    def execute(self, params: dict) -> ToolResult:
        image_amount = len(params["image_paths"])
        tmp = f"<Image Amount>\n{image_amount}\n<Images Path>\n"
        tmp += "\n".join(params["image_paths"]) + "\n"
        tmp += f"<Output Path>\n{params['output_path']}\n"
        write_tmp("PLUS_Diverse.tmp", tmp)
        rc, stdout, stderr = run_bat("diverse.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Diverse failed (rc={rc}): {stderr}")
        return ToolResult(success=True, message="Diversity map generated", output_paths=[params["output_path"]])
