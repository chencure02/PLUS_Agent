# agent/tools/expansion.py
import os

from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat


class ExpansionTool(BaseTool):
    name = "expansion"
    description = "Extract land use change areas between two LULC rasters (early vs late year). Output: expansion change map (actual filename will have _landuse_1to2 suffix appended)."
    parameters = {
        "type": "object",
        "properties": {
            "early_lulc": {"type": "string", "description": "Early-year LULC raster absolute path"},
            "late_lulc": {"type": "string", "description": "Late-year LULC raster absolute path"},
            "output_change": {"type": "string", "description": "Output expansion map absolute path (actual output will be named <basename>_landuse_1to2.tif)"},
        },
        "required": ["early_lulc", "late_lulc", "output_change"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<Input number>\n2\n<Input LULC series>\n{params['early_lulc']}\n{params['late_lulc']}\n<Output change>\n{params['output_change']}\n"
        write_tmp("PLUS_Expansion.tmp", tmp)
        rc, stdout, stderr = run_bat("expansion.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Expansion failed (rc={rc}): {stderr}")

        # PLUS.exe renames output: expansion.tif → expansion_landuse_1to2.tif
        out_dir = os.path.dirname(params["output_change"]) or "."
        base = os.path.splitext(os.path.basename(params["output_change"]))[0]
        actual = os.path.join(os.path.abspath(out_dir), f"{base}_landuse_1to2.tif")
        if os.path.exists(actual):
            return ToolResult(success=True, message="Expansion map generated", output_paths=[actual])
        # Fallback: check if the original path exists
        if os.path.exists(params["output_change"]):
            return ToolResult(success=True, message="Expansion map generated", output_paths=[params["output_change"]])
        return ToolResult(success=False, error=f"Expansion output not found: expected {actual}")

