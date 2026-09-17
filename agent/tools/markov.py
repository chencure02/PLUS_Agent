import csv
import os
import shutil
from agent.tools.base import BaseTool, ToolResult
from agent.tools import locked_plus_backend, run_bat, write_tmp
from agent.config import CPP_DIR


class MarkovTool(BaseTool):
    name = "markov"
    description = "Predict future land use demand using Markov chain. Output: markov.csv (moved to output dir). The result message includes the demand string for CARS (format: 1,demand_c1,demand_c2,...)."
    parameters = {
        "type": "object",
        "properties": {
            "start_map": {"type": "string", "description": "Start year LULC raster path"},
            "end_map": {"type": "string", "description": "End year LULC raster path"},
            "start_year": {"type": "integer", "description": "Start year (e.g. 2003)"},
            "end_year": {"type": "integer", "description": "End year (e.g. 2013)"},
            "predict_year": {"type": "integer", "description": "Target prediction year (e.g. 2033)"},
            "output_dir": {"type": "string", "description": "Output directory for markov.csv (use the path from [输出目录])"},
        },
        "required": ["start_map", "end_map", "start_year", "end_year", "predict_year", "output_dir"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = (
            f"<StartMap>\n{params['start_map']}\n"
            f"<EndMap>\n{params['end_map']}\n"
            f"<Start Year>\n{params['start_year']}\n"
            f"<End Year>\n{params['end_year']}\n"
            f"<Predict Year>\n{params['predict_year']}\n"
        )
        output_dir = os.path.abspath(params["output_dir"])
        os.makedirs(output_dir, exist_ok=True)
        dst = os.path.join(output_dir, "markov.csv")

        with locked_plus_backend():
            write_tmp("PLUS_Markov.tmp", tmp)
            rc, stdout, stderr = run_bat("markov.bat")
            if rc != 0:
                return ToolResult(success=False, error=f"Markov failed (rc={rc}): {stderr}")

            src = str(CPP_DIR / "output" / "markov.csv")
            if not os.path.exists(src):
                return ToolResult(success=False, error=f"Markov output not found at {src}")

            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)

        demand_str = self._extract_demand(dst, params["predict_year"])

        msg = f"Markov prediction for {params['predict_year']} complete."
        if demand_str:
            msg += f"\nCARS yearly_demands = `{demand_str}`"
        artifacts = {"markov_csv": dst}
        if demand_str:
            artifacts["yearly_demands"] = demand_str
        return ToolResult(success=True, message=msg, output_paths=[dst], artifacts=artifacts)

    @staticmethod
    def _extract_demand(csv_path: str, predict_year: int) -> str | None:
        """Parse markov.csv [Predict amount] section, find the row matching predict_year,
        and return a CARS-compatible demand string: '1,val1,val2,...'"""
        if not os.path.exists(csv_path):
            return None
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                in_predict = False
                for row in reader:
                    if not row:
                        continue
                    # Detect [Predict amount] section
                    if row[0].strip().startswith("[Predict"):
                        in_predict = True
                        continue
                    if in_predict and row[0].strip().startswith("["):
                        break  # reached next section
                    if in_predict:
                        try:
                            year = int(float(row[0]))
                        except (ValueError, IndexError):
                            continue
                        if year == predict_year:
                            # Format: 1,demand_c1,demand_c2,...
                            values = [str(int(float(v))) for v in row[1:]]
                            return "1," + ",".join(values)
            return None
        except Exception:
            return None
