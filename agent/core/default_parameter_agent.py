from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from agent.core.parameter_provider import ParameterProvider
from agent.core.workflow_state import ParameterProposal, WorkflowContext, WorkflowState


class DefaultParameterAgent(ParameterProvider):
    """Rule-based first parameter provider for the managed PLUS workflow."""

    def propose(
        self,
        step_name: str,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        handler = getattr(self, f"_propose_{step_name}", None)
        if handler is None:
            return ParameterProposal(
                step=step_name,
                missing_fields=[step_name],
                warnings=[f"暂不支持自动生成 `{step_name}` 的参数。"],
            )
        return handler(state, context)

    def _propose_convert(self, state: WorkflowState, context: WorkflowContext) -> ParameterProposal:
        lulc_files = _sort_paths_by_year(context.lulc_files)
        output_paths = [
            _join(context.output_dir, "convert", f"{Path(path).stem}_converted.tif")
            for path in lulc_files
        ]
        missing = [] if lulc_files else ["input_paths"]
        return ParameterProposal(
            step="convert",
            params={"input_paths": lulc_files, "output_paths": output_paths},
            missing_fields=missing,
            assumptions=["按文件名中的年份从早到晚排序 LULC 栅格。"] if len(lulc_files) > 1 else [],
        )

    def _propose_expansion(self, state: WorkflowState, context: WorkflowContext) -> ParameterProposal:
        lulc_files = _workflow_lulc_paths(state, context)
        params: dict[str, Any] = {
            "output_change": _join(context.output_dir, "expansion", "expansion.tif"),
        }
        missing = []
        if len(lulc_files) >= 2:
            params["early_lulc"] = lulc_files[0]
            params["late_lulc"] = lulc_files[-1]
        else:
            missing.extend(["early_lulc", "late_lulc"])
        return ParameterProposal(
            step="expansion",
            params=params,
            missing_fields=missing,
            assumptions=["使用最早和最晚两期 LULC 生成扩张变化图。"] if not missing else [],
        )

    def _propose_leas(self, state: WorkflowState, context: WorkflowContext) -> ParameterProposal:
        feature_folder = context.drivers_dir or _common_parent(context.driver_files)
        params: dict[str, Any] = {
            "input_lulc": state.artifacts.get("expansion_raster", ""),
            "feature_folder": feature_folder,
            "output_probability": _join(context.output_dir, "leas", "potential.tif"),
            "sampling_rate": 0.01,
            "m_try": 16,
            "n_trees": 20,
            "thread_count": 8,
        }
        missing = []
        if not params["input_lulc"]:
            missing.append("input_lulc")
        if not feature_folder:
            missing.append("feature_folder")
        return ParameterProposal(step="leas", params=params, missing_fields=missing)

    def _propose_markov(self, state: WorkflowState, context: WorkflowContext) -> ParameterProposal:
        lulc_files = _workflow_lulc_paths(state, context)
        params: dict[str, Any] = {
            "output_dir": _join(context.output_dir, "markov"),
        }
        missing = []
        start_year = end_year = None
        if len(lulc_files) >= 2:
            start_map = lulc_files[0]
            end_map = lulc_files[-1]
            params["start_map"] = start_map
            params["end_map"] = end_map
            start_year = _first_year(start_map)
            end_year = _first_year(end_map)
            if start_year:
                params["start_year"] = start_year
            if end_year:
                params["end_year"] = end_year
        else:
            missing.extend(["start_map", "end_map"])

        predict_year = state.requested_target_year or _target_year(context.user_message, end_year)
        if predict_year:
            params["predict_year"] = predict_year
        for field, value in {
            "start_year": start_year,
            "end_year": end_year,
            "predict_year": predict_year,
        }.items():
            if not value:
                missing.append(field)

        return ParameterProposal(step="markov", params=params, missing_fields=_dedupe(missing))

    def _propose_neighborhood_weight(
        self,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        probability_paths = list(state.artifacts.get("probability_paths") or [])
        num_classes = len(probability_paths)
        params: dict[str, Any] = {
            "expansion_raster": state.artifacts.get("expansion_raster", ""),
            "background_values": "0,255",
        }
        missing = []
        if params["expansion_raster"]:
            pass
        else:
            missing.append("expansion_raster")
        if num_classes:
            params["num_classes"] = num_classes
        else:
            missing.append("num_classes")
        return ParameterProposal(step="neighborhood_weight", params=params, missing_fields=missing)

    def _propose_cars(self, state: WorkflowState, context: WorkflowContext) -> ParameterProposal:
        probability_paths = list(state.artifacts.get("probability_paths") or [])
        input_classes = len(probability_paths)
        policy_path = context.constraint_files[0] if context.constraint_files else ""
        params: dict[str, Any] = {
            "input_classes": input_classes if input_classes else "",
            "input_lulc": state.artifacts.get("late_lulc") or _last_lulc(state, context),
            "probability_paths": probability_paths,
            "output_simulation": _join(context.output_dir, "cars", "simulation.tif"),
            "policy_path": policy_path,
            "neighborhood": 3,
            "thread_count": 8,
            "patch_generation": 0.2,
            "expansion_coefficient": 0.2,
            "neighborhood_weights": state.artifacts.get("neighborhood_weights", ""),
            "transition_matrix": _transition_matrix(input_classes) if input_classes else "",
            "yearly_demands": state.artifacts.get("yearly_demands", ""),
            "seed_percentage": 0.1,
        }
        required = [
            "input_classes",
            "input_lulc",
            "probability_paths",
            "neighborhood_weights",
            "transition_matrix",
            "yearly_demands",
        ]
        missing = [field for field in required if params.get(field) in ("", [], None)]
        warnings = [] if policy_path else ["未检测到约束图，policy_path 将为空。"]
        assumptions = ["使用最新一期 LULC 作为 CARS 起始图。"] if params["input_lulc"] else []
        return ParameterProposal(
            step="cars",
            params=params,
            missing_fields=missing,
            assumptions=assumptions,
            warnings=warnings,
        )


def _join(root: str, *parts: str) -> str:
    return str(Path(root or ".").joinpath(*parts))


def _workflow_lulc_paths(state: WorkflowState, context: WorkflowContext) -> list[str]:
    paths = list(state.artifacts.get("converted_lulc_paths") or [])
    if paths:
        return _sort_paths_by_year(paths)
    return _sort_paths_by_year(context.lulc_files)


def _last_lulc(state: WorkflowState, context: WorkflowContext) -> str:
    paths = _workflow_lulc_paths(state, context)
    return paths[-1] if paths else ""


def _sort_paths_by_year(paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda path: (_first_year(path) or 9999, path.lower()))


def _first_year(text: str) -> int | None:
    for match in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text):
        return int(match)
    return None


def _target_year(message: str, end_year: int | None = None) -> int | None:
    years = [int(year) for year in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", message)]
    if not years:
        return None
    if end_year is not None:
        future = [year for year in years if year > end_year]
        return max(future) if future else None
    return max(years)


def _common_parent(paths: list[str]) -> str:
    if not paths:
        return ""
    if len(paths) == 1:
        return str(Path(paths[0]).parent)
    return os.path.commonpath([str(Path(path).parent) for path in paths])


def _transition_matrix(input_classes: int) -> str:
    row = ",".join("1" for _ in range(input_classes))
    return ";".join(row for _ in range(input_classes))


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
