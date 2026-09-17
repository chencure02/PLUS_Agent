# agent/tools/leas.py
import glob as glob_mod
import os
import shutil
from agent.tools.base import BaseTool, ToolResult
from agent.tools import locked_plus_backend, run_bat, write_tmp
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
        with locked_plus_backend():
            write_tmp("PLUS_LEAS.tmp", tmp)
            rc, stdout, stderr = run_bat("leas.bat")
            if rc != 0:
                return ToolResult(success=False, error=f"LEAS failed (rc={rc}): {stderr}")

            base = params["output_probability"]
            output_dir = os.path.dirname(os.path.abspath(base))
            base_name = os.path.splitext(os.path.basename(base))[0]
            outputs = []

            # Move PLUS_BACKEND-generated files to user's output directory before another job starts.
            for filename in ["accuracy_record_rf.txt", "imageminmax.txt"]:
                src = str(PLUS_BACKEND / filename)
                if os.path.exists(src):
                    dst = os.path.join(output_dir, filename)
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.move(src, dst)
                    outputs.append(dst)

            # Contribution CSVs (one per land use type)
            for src in sorted(glob_mod.glob(str(PLUS_BACKEND / "Contribution*.csv"))):
                dst = os.path.join(output_dir, os.path.basename(src))
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
                outputs.append(dst)

            # Probability bands (generated directly in output_dir by PLUS.exe)
            pattern = os.path.join(output_dir, f"{base_name}_band_*.tif")
            bands = sorted(glob_mod.glob(pattern))
            outputs.extend(bands)

        band_count = len(bands)
        contribution_tables = [o for o in outputs if "Contribution" in o]
        csv_count = len(contribution_tables)
        return ToolResult(
            success=True,
            message=f"LEAS: {band_count} probability bands, {csv_count} contribution tables generated",
            output_paths=outputs,
            artifacts={
                "probability_paths": list(bands),
                "contribution_tables": contribution_tables,
            },
        )
