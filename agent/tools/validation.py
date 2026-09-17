# agent/tools/validation.py
import os
import shutil

from agent.tools.base import BaseTool, ToolResult
from agent.tools import locked_plus_backend, run_bat, write_tmp
from agent.config import PLUS_BACKEND


class ValidationTool(BaseTool):
    name = "validation"
    description = "Validate simulation accuracy: compare simulated vs real LULC. Computes Kappa coefficient or FoM (Figure of Merit)."
    parameters = {
        "type": "object",
        "properties": {
            "is_fom": {"type": "integer", "default": 0, "description": "0=Kappa, 1=FoM"},
            "sampling_rate": {"type": "number", "default": 0.1},
            "simulated_map": {"type": "string", "description": "Simulated LULC raster path (CARS output)"},
            "real_map": {"type": "string", "description": "Real reference LULC raster path"},
            "start_map": {"type": "string", "description": "Simulation start year LULC raster path"},
            "output_dir": {"type": "string", "description": "Output directory for validation CSV (use the path from [输出目录])"},
        },
        "required": ["simulated_map", "real_map", "start_map"]
    }

    def execute(self, params: dict) -> ToolResult:
        is_fom = params.get("is_fom", 0)
        tmp = (
            f"<IsFom>\n{is_fom}\n"
            f"<Sampling rate>\n{params.get('sampling_rate', 0.1)}\n"
            f"<Simulated Map>\n{params['simulated_map']}\n"
            f"<Real Map>\n{params['real_map']}\n"
            f"<Start Map>\n{params['start_map']}\n"
        )
        name = "FoM.csv" if is_fom else "Kappa.csv"
        output_dir = os.path.abspath(params.get("output_dir") or os.path.dirname(params["simulated_map"]) or ".")
        os.makedirs(output_dir, exist_ok=True)
        dst = os.path.join(output_dir, name)

        with locked_plus_backend():
            write_tmp("PLUS_Validation.tmp", tmp)
            rc, stdout, stderr = run_bat("validate.bat")
            if rc != 0:
                return ToolResult(success=False, error=f"Validation failed (rc={rc}): {stderr}")
            src = str(PLUS_BACKEND / name)
            if not os.path.exists(src):
                return ToolResult(success=False, error=f"Validation output not found at {src}")
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
        return ToolResult(
            success=True,
            message=f"Validation ({'FoM' if is_fom else 'Kappa'}) complete",
            output_paths=[dst],
            artifacts={"validation_csv": dst},
        )
