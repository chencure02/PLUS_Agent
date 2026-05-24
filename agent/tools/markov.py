# agent/tools/markov.py
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
from agent.config import CPP_DIR


class MarkovTool(BaseTool):
    name = "markov"
    description = "Predict future land use demand quantities using Markov chain. Input: start/end LULC + years. Output: markov.csv with predicted per-class demands."
    parameters = {
        "type": "object",
        "properties": {
            "start_map": {"type": "string", "description": "Start year LULC raster path"},
            "end_map": {"type": "string", "description": "End year LULC raster path"},
            "start_year": {"type": "integer", "description": "Start year (e.g. 2003)"},
            "end_year": {"type": "integer", "description": "End year (e.g. 2013)"},
            "predict_year": {"type": "integer", "description": "Target prediction year (e.g. 2033)"},
        },
        "required": ["start_map", "end_map", "start_year", "end_year", "predict_year"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = f"<StartMap>\n{params['start_map']}\n<EndMap>\n{params['end_map']}\n<Start Year>\n{params['start_year']}\n<End Year>\n{params['end_year']}\n<Predict Year>\n{params['predict_year']}\n"
        write_tmp("PLUS_Markov.tmp", tmp)
        rc, stdout, stderr = run_bat("markov.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"Markov failed (rc={rc}): {stderr}")
        output = str(CPP_DIR / "output" / "markov.csv")
        return ToolResult(success=True, message=f"Markov prediction for {params['predict_year']} complete", output_paths=[output])
