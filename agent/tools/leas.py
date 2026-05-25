# agent/tools/leas.py
import glob as glob_mod
import os
from agent.tools.base import BaseTool, ToolResult
from agent.tools import write_tmp, run_bat
from agent.config import PLUS_BACKEND


class LEASTool(BaseTool):
    name = "leas"
    description = "Land Expansion Analysis Strategy. Uses Random Forest with driving factors to generate per-class land use occurrence probability maps and Contribution*.csv factor importance tables. Input: expansion map + driving factors folder + RF parameters."
    parameters = {
        "type": "object",
        "properties": {
            "input_lulc": {"type": "string", "description": "Expansion extraction result path (expansion module output)"},
            "feature_folder": {"type": "string", "description": "Driving factors folder path (contains elevation, slope, distance rasters, etc.)"},
            "output_probability": {"type": "string", "description": "Output probability basename (e.g. C:/out/potential.tif — will generate potential_band_1.tif, potential_band_2.tif, ...)"},
            "sampling_rate": {"type": "number", "default": 0.01, "description": "Random Forest sampling rate"},
            "m_try": {"type": "integer", "default": 16, "description": "Features sampled per tree"},
            "n_trees": {"type": "integer", "default": 20, "description": "Number of Random Forest trees"},
            "thread_count": {"type": "integer", "default": 8, "description": "Parallel threads"},
        },
        "required": ["input_lulc", "feature_folder", "output_probability"]
    }

    def execute(self, params: dict) -> ToolResult:
        tmp = (
            f"<Input LULC>\n{params['input_lulc']}\n"
            f"<Input Featrue folder>\n{params['feature_folder']}\n"
            f"<Output probability>\n{params['output_probability']}\n"
            f"<Is net exit?>\n0\n"
            f"<Input sampling rate>\n{params.get('sampling_rate', 0.01)}\n"
            f"<mTry>\n{params.get('m_try', 16)}\n"
            f"<Input the number of trees>\n{params.get('n_trees', 20)}\n"
            f"<Is balance?>\n0\n"
            f"<Input thread count>\n{params.get('thread_count', 8)}\n"
            f"<High precision>\n0\n<Update Number>\n0\n<Update Variable>\n0\n"
        )
        write_tmp("PLUS_LEAS.tmp", tmp)
        rc, stdout, stderr = run_bat("leas.bat")
        if rc != 0:
            return ToolResult(success=False, error=f"LEAS failed (rc={rc}): {stderr}")

        base = params["output_probability"]
        dir_name = os.path.dirname(base) or "."
        dir_name = os.path.abspath(dir_name)
        base_name = os.path.splitext(os.path.basename(base))[0]
        outputs = []

        # Accuracy and normalization records
        for f in [str(PLUS_BACKEND / "accuracy_record_rf.txt"), str(PLUS_BACKEND / "imageminmax.txt")]:
            if os.path.exists(f):
                outputs.append(f)

        # Probability bands
        pattern = os.path.join(dir_name, f"{base_name}_band_*.tif")
        bands = sorted(glob_mod.glob(pattern))
        outputs.extend(bands)

        # Driving factor contribution CSVs (one per land use type)
        for f in sorted(glob_mod.glob(str(PLUS_BACKEND / "Contribution*.csv"))):
            if os.path.exists(f):
                outputs.append(f)

        band_count = len(bands)
        csv_count = len([o for o in outputs if "Contribution" in o])
        return ToolResult(success=True, message=f"LEAS: {band_count} probability bands, {csv_count} contribution tables generated", output_paths=outputs)
