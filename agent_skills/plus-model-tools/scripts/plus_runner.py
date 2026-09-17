from __future__ import annotations

import argparse
import csv
import glob
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path


_PLUS_LOCK = threading.Lock()


@dataclass(frozen=True)
class ModuleSpec:
    tmp_filename: str
    bat_filename: str


@dataclass
class PlusJobResult:
    success: bool
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    message: str = ""
    output_paths: list[str] = field(default_factory=list)


MODULE_SPECS: dict[str, ModuleSpec] = {
    "convert": ModuleSpec("PLUS_Convert.tmp", "convert.bat"),
    "expansion": ModuleSpec("PLUS_Expansion.tmp", "expansion.bat"),
    "leas": ModuleSpec("PLUS_LEAS.tmp", "leas.bat"),
    "markov": ModuleSpec("PLUS_Markov.tmp", "markov.bat"),
    "cars": ModuleSpec("PLUS_CARS.tmp", "cars.bat"),
    "linear": ModuleSpec("PLUS_Linear.tmp", "linear.bat"),
    "diverse": ModuleSpec("PLUS_Diverse.tmp", "diverse.bat"),
    "validation": ModuleSpec("PLUS_Validation.tmp", "validate.bat"),
}


def ensure_ascii_path(path: Path) -> None:
    text = str(path.resolve())
    if any(ord(ch) > 127 for ch in text):
        raise ValueError(f"PLUS backend path must be ASCII-only: {text}")


def _lines(*parts: object) -> str:
    return "\n".join(str(part) for part in parts) + "\n"


class PlusBackendRunner:
    """Reusable abstraction for writing PLUS tmp files and running bat modules."""

    def __init__(self, plus_backend: str | Path, timeout: int = 600, require_ascii_path: bool = True):
        self.plus_backend = Path(plus_backend).resolve()
        self.timeout = timeout
        if require_ascii_path:
            ensure_ascii_path(self.plus_backend)
        if not self.plus_backend.exists():
            raise FileNotFoundError(f"plus-backend not found: {self.plus_backend}")

    def tmp_path(self, filename: str) -> Path:
        return self.plus_backend / filename

    def write_tmp(self, filename: str, content: str) -> Path:
        path = self.tmp_path(filename)
        path.write_text(content, encoding="utf-8")
        return path

    def read_tmp(self, filename: str) -> str:
        return self.tmp_path(filename).read_text(encoding="utf-8", errors="replace")

    def run_bat(self, bat_filename: str) -> PlusJobResult:
        bat_path = self.plus_backend / bat_filename
        try:
            completed = subprocess.run(
                [str(bat_path)],
                cwd=str(self.plus_backend),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,
            )
            return PlusJobResult(
                success=completed.returncode == 0,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        except subprocess.TimeoutExpired as exc:
            return PlusJobResult(success=False, returncode=-1, stderr=f"Timeout after {self.timeout}s: {exc}")
        except OSError as exc:
            return PlusJobResult(success=False, returncode=-1, stderr=f"Failed to run {bat_filename}: {exc}")

    def run_job(self, module: str, tmp_content: str) -> PlusJobResult:
        spec = MODULE_SPECS[module]
        with _PLUS_LOCK:
            self.write_tmp(spec.tmp_filename, tmp_content)
            return self.run_bat(spec.bat_filename)

    def run_convert(self, input_paths: list[str], output_paths: list[str]) -> PlusJobResult:
        tmp = build_convert_tmp(input_paths, output_paths)
        result = self.run_job("convert", tmp)
        if not result.success:
            result.message = f"Convert failed with return code {result.returncode}"
            return result
        missing = [path for path in output_paths if not Path(path).exists()]
        result.success = not missing
        result.output_paths = output_paths
        result.message = "Converted rasters" if not missing else f"Missing outputs: {missing}"
        return result

    def run_expansion(self, early_lulc: str, late_lulc: str, output_change: str) -> PlusJobResult:
        tmp = build_expansion_tmp(early_lulc, late_lulc, output_change)
        result = self.run_job("expansion", tmp)
        if not result.success:
            result.message = f"Expansion failed with return code {result.returncode}"
            return result
        actual = expected_expansion_output(output_change)
        fallback = Path(output_change)
        output = actual if actual.exists() else fallback if fallback.exists() else None
        result.success = output is not None
        result.output_paths = [str(output)] if output else []
        result.message = "Expansion map generated" if output else f"Expansion output not found: {actual}"
        return result

    def run_linear(self, predict_amount: int, image_paths: list[str]) -> PlusJobResult:
        tmp = build_linear_tmp(predict_amount, image_paths)
        result = self.run_job("linear", tmp)
        result.message = result.stdout[:2000] if result.success else f"Linear failed with return code {result.returncode}"
        return result

    def run_diverse(self, image_paths: list[str], output_path: str) -> PlusJobResult:
        tmp = build_diverse_tmp(image_paths, output_path)
        result = self.run_job("diverse", tmp)
        result.output_paths = [output_path] if result.success else []
        result.message = "Diversity map generated" if result.success else f"Diverse failed with return code {result.returncode}"
        return result


def build_convert_tmp(input_paths: list[str], output_paths: list[str]) -> str:
    if len(input_paths) != len(output_paths) or not input_paths:
        raise ValueError("convert requires the same non-zero number of input_paths and output_paths")
    return _lines(
        "<Input number>",
        len(input_paths),
        "<Input LULC series>",
        *input_paths,
        "<Output LULC series>",
        *output_paths,
    )


def build_expansion_tmp(early_lulc: str, late_lulc: str, output_change: str) -> str:
    return _lines(
        "<Input number>",
        2,
        "<Input LULC series>",
        early_lulc,
        late_lulc,
        "<Output change>",
        output_change,
    )


def build_leas_tmp(
    input_lulc: str,
    feature_folder: str,
    output_probability: str,
    sampling_rate: float = 0.01,
    m_try: int = 16,
    n_trees: int = 20,
    thread_count: int = 8,
) -> str:
    return _lines(
        "<Input LULC>",
        input_lulc,
        "<Input Featrue folder>",
        feature_folder,
        "<Output probability>",
        output_probability,
        "<Is net exit?>",
        0,
        "<Input sampling rate>",
        sampling_rate,
        "<mTry>",
        m_try,
        "<Input the number of trees>",
        n_trees,
        "<Is balance?>",
        0,
        "<Input thread count>",
        thread_count,
        "<High precision>",
        0,
        "<Update Number>",
        0,
        "<Update Variable>",
        0,
    )


def build_markov_tmp(start_map: str, end_map: str, start_year: int, end_year: int, predict_year: int) -> str:
    return _lines(
        "<StartMap>",
        start_map,
        "<EndMap>",
        end_map,
        "<Start Year>",
        start_year,
        "<End Year>",
        end_year,
        "<Predict Year>",
        predict_year,
    )


def build_cars_tmp(
    input_classes: int,
    input_lulc: str,
    probability_paths: list[str],
    output_simulation: str,
    neighborhood_weights: str,
    transition_matrix: str,
    yearly_demands: str,
    policy_path: str = "",
    neighborhood: int = 3,
    thread_count: int = 8,
    patch_generation: float = 0.2,
    expansion_coefficient: float = 0.2,
    seed_percentage: float = 0.1,
) -> str:
    matrix = transition_matrix.replace(";", "\n")
    return _lines(
        "<Input classes>",
        input_classes,
        "<Input LULC>",
        input_lulc,
        "<Input Probability Folder>",
        *probability_paths,
        "<Output simulation>",
        output_simulation,
        "<Input Policy>",
        policy_path,
        "<Input Neighborhood>",
        neighborhood,
        "<How many years>",
        1,
        "<Input thread count>",
        thread_count,
        "<Patch generation>",
        patch_generation,
        "<Expansion coefficient>",
        expansion_coefficient,
        "<Neighborhood Weight>",
        neighborhood_weights,
        "<Transition matrix>",
        matrix,
        "<Years and corresponding demands>",
        yearly_demands,
        "<Percentage of seeds>",
        seed_percentage,
        "<Development type exist>",
        0,
        "<Development type>",
        0,
        "<Development weight>",
        0.5,
    )


def build_validation_tmp(
    simulated_map: str,
    real_map: str,
    start_map: str,
    is_fom: int = 0,
    sampling_rate: float = 0.1,
) -> str:
    return _lines(
        "<IsFom>",
        is_fom,
        "<Sampling rate>",
        sampling_rate,
        "<Simulated Map>",
        simulated_map,
        "<Real Map>",
        real_map,
        "<Start Map>",
        start_map,
    )


def build_linear_tmp(predict_amount: int, image_paths: list[str]) -> str:
    return _lines(
        "<Image Amount>",
        len(image_paths),
        "<Predict Amount>",
        predict_amount,
        "<Images Path>",
        *image_paths,
    )


def build_diverse_tmp(image_paths: list[str], output_path: str) -> str:
    return _lines(
        "<Image Amount>",
        len(image_paths),
        "<Images Path>",
        *image_paths,
        "<Output Path>",
        output_path,
    )


def expected_expansion_output(output_change: str) -> Path:
    path = Path(output_change)
    return path.with_name(f"{path.stem}_landuse_1to2.tif").resolve()


def expected_cars_outputs(output_simulation: str) -> list[str]:
    path = Path(output_simulation).resolve()
    pattern = str(path.with_name(f"{path.stem}Simulation_*.tif"))
    return sorted(glob.glob(pattern))


def move_if_exists(src: Path, dst: Path) -> str | None:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))
    return str(dst)


def extract_markov_demand(csv_path: str | Path, predict_year: int) -> str | None:
    path = Path(csv_path)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
        reader = csv.reader(stream)
        in_predict = False
        for row in reader:
            if not row:
                continue
            first = row[0].strip()
            if first.startswith("[Predict"):
                in_predict = True
                continue
            if in_predict and first.startswith("["):
                break
            if not in_predict:
                continue
            try:
                year = int(float(first))
            except ValueError:
                continue
            if year == predict_year:
                values = [str(int(float(value))) for value in row[1:] if value.strip()]
                return "1," + ",".join(values)
    return None


def calculate_neighborhood_weights(
    expansion_raster: str | Path,
    num_classes: int,
    background_values: str = "0,255",
) -> str:
    import numpy as np
    from osgeo import gdal

    bg_values = {int(value.strip()) for value in background_values.split(",") if value.strip()}
    dataset = gdal.Open(str(expansion_raster))
    if dataset is None:
        raise ValueError(f"Cannot open raster: {expansion_raster}")
    data = dataset.GetRasterBand(1).ReadAsArray()
    dataset = None
    flat = data.ravel()
    valid = [int(value) for value in flat if int(value) not in bg_values]
    total = len(valid)
    if total == 0:
        raise ValueError("Expansion raster has no valid pixels after excluding background values")
    counts = {class_id: 0 for class_id in range(1, num_classes + 1)}
    for value in valid:
        if value in counts:
            counts[value] += 1
    weights = [counts[class_id] / total for class_id in range(1, num_classes + 1)]
    return ",".join(f"{weight:.6f}" for weight in weights)


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Run PLUS backend modules via tmp files and bat files.")
    parser.add_argument("--plus-backend", required=True, help="Path to plus-backend")
    parser.add_argument("--timeout", type=int, default=600)
    sub = parser.add_subparsers(dest="command", required=True)

    convert = sub.add_parser("convert", help="Write PLUS_Convert.tmp and run convert.bat")
    convert.add_argument("--input-path", action="append", required=True, dest="input_paths")
    convert.add_argument("--output-path", action="append", required=True, dest="output_paths")

    show_tmp = sub.add_parser("show-convert-tmp", help="Print the tmp content for convert without running PLUS")
    show_tmp.add_argument("--input-path", action="append", required=True, dest="input_paths")
    show_tmp.add_argument("--output-path", action="append", required=True, dest="output_paths")

    args = parser.parse_args()

    if args.command == "show-convert-tmp":
        print(build_convert_tmp(args.input_paths, args.output_paths), end="")
        return 0

    runner = PlusBackendRunner(args.plus_backend, timeout=args.timeout)
    if args.command == "convert":
        result = runner.run_convert(args.input_paths, args.output_paths)
        print(result.message)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return 0 if result.success else 1

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(_cli())
