# agent/tools/cars.py
import os, glob
from agent.tools.base import BaseTool, ToolResult
from agent.tools import run_plus_job


class CARSTool(BaseTool):
    name = "cars"
    description = "Core simulation module: CA-based patch-generating simulation. Combines LEAS probability maps, Markov demand, transition rules, and constraints to simulate future LULC."
    parameters = {
        "type": "object",
        "properties": {
            "input_classes": {"type": "integer", "description": "Number of land use types (matches probability band count)"},
            "input_lulc": {"type": "string", "description": "Start year LULC raster path (usually the early-year converted LULC)"},
            "probability_paths": {"type": "array", "items": {"type": "string"}, "description": "LEAS probability band paths, one per class"},
            "output_simulation": {"type": "string", "description": "Output simulation result path (actual output will be named <basename>Simulation_1.tif)"},
            "policy_path": {"type": "string", "default": "", "description": "Optional constraint map path (e.g. water protection). Empty string = no constraint."},
            "neighborhood": {"type": "integer", "default": 3, "description": "Neighborhood window size"},
            "thread_count": {"type": "integer", "default": 8},
            "patch_generation": {"type": "number", "default": 0.2, "description": "Patch generation threshold (0-1)"},
            "expansion_coefficient": {"type": "number", "default": 0.2, "description": "Expansion coefficient (0-1)"},
            "neighborhood_weights": {"type": "string", "description": "Comma-separated weights per class"},
            "transition_matrix": {"type": "string", "description": "NxN matrix, rows separated by semicolons, 1=allow 0=forbid. E.g. '1,1,1;0,1,0;1,1,1'"},
            "yearly_demands": {"type": "string", "description": "Demand string: '1,demand_c1,demand_c2,...' (first number always 1)"},
            "seed_percentage": {"type": "number", "default": 0.1, "description": "Random seed percentage for patch generation"},
        },
        "required": ["input_classes", "input_lulc", "probability_paths", "output_simulation", "neighborhood_weights", "transition_matrix", "yearly_demands"]
    }

    def execute(self, params: dict) -> ToolResult:
        matrix_str = params["transition_matrix"].replace(";", "\n")
        tmp = (
            f"<Input classes>\n{params['input_classes']}\n"
            f"<Input LULC>\n{params['input_lulc']}\n"
            f"<Input Probability Folder>\n" + "\n".join(params["probability_paths"]) + "\n"
            f"<Output simulation>\n{params['output_simulation']}\n"
            f"<Input Policy>\n{params.get('policy_path', '')}\n"
            f"<Input Neighborhood>\n{params.get('neighborhood', 3)}\n"
            f"<How many years>\n1\n"
            f"<Input thread count>\n{params.get('thread_count', 8)}\n"
            f"<Patch generation>\n{params.get('patch_generation', 0.2)}\n"
            f"<Expansion coefficient>\n{params.get('expansion_coefficient', 0.2)}\n"
            f"<Neighborhood Weight>\n{params['neighborhood_weights']}\n"
            f"<Transition matrix>\n{matrix_str}\n"
            f"<Years and corresponding demands>\n{params['yearly_demands']}\n"
            f"<Percentage of seeds>\n{params.get('seed_percentage', 0.1)}\n"
            f"<Development type exist>\n0\n<Development type>\n0\n<Development weight>\n0.5\n"
        )
        rc, stdout, stderr = run_plus_job("PLUS_CARS.tmp", tmp, "cars.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"CARS failed (rc={rc}): {stderr}")

        out_dir = os.path.dirname(params["output_simulation"]) or "."
        out_dir = os.path.abspath(out_dir)
        base = os.path.splitext(os.path.basename(params["output_simulation"]))[0]
        matches = sorted(glob.glob(os.path.join(out_dir, f"{base}Simulation_*.tif")))
        if matches and os.path.exists(matches[0]):
            return ToolResult(
                success=True,
                message="CARS simulation complete",
                output_paths=[matches[0]],
                artifacts={"simulation_raster": matches[0]},
            )
        return ToolResult(success=False, error=f"CARS: no output file found matching {out_dir}/{base}Simulation_*.tif")
