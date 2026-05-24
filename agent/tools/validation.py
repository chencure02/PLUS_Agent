# agent/tools/validation.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
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
        write_tmp("PLUS_Validation.tmp", tmp)
        rc, stdout, stderr = run_bat("validate.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Validation failed (rc={rc}): {stderr}")
        name = "FoM.csv" if is_fom else "Kappa.csv"
        return ToolResult(success=True, message=f"Validation ({'FoM' if is_fom else 'Kappa'}) complete", output_paths=[str(PLUS_BACKEND / name)])
