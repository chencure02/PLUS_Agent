from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXPECTED_TOOLS = {
    "convert",
    "expansion",
    "leas",
    "markov",
    "linear",
    "cars",
    "validation",
    "diverse",
    "neighborhood_weight",
    "list_files",
    "read_file",
    "search_files",
}


def build_tool_registry():
    from agent.tools.cars import CARSTool
    from agent.tools.convert import ConvertTool
    from agent.tools.diverse import DiverseTool
    from agent.tools.expansion import ExpansionTool
    from agent.tools.file_tools import ListFilesTool, ReadFileTool, SearchFilesTool
    from agent.tools.leas import LEASTool
    from agent.tools.linear import LinearTool
    from agent.tools.markov import MarkovTool
    from agent.tools.neighborhood_weight import NeighborhoodWeightTool
    from agent.tools.registry import ToolRegistry
    from agent.tools.validation import ValidationTool

    registry = ToolRegistry()
    for tool in (
        ConvertTool(),
        ExpansionTool(),
        LEASTool(),
        MarkovTool(),
        LinearTool(),
        CARSTool(),
        ValidationTool(),
        DiverseTool(),
        ListFilesTool(),
        ReadFileTool(),
        SearchFilesTool(),
        NeighborhoodWeightTool(),
    ):
        registry.register(tool)
    return registry


def metric(name: str, score: float, weight: float, status: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "score": round(float(score), 2),
        "weight": float(weight),
        "status": status,
        "details": details,
    }


def status_from_score(score: float) -> str:
    if score >= 90:
        return "pass"
    if score >= 70:
        return "warning"
    return "fail"


def evaluate_tool_coverage() -> dict[str, Any]:
    registry = build_tool_registry()
    actual = set(registry.get_all_names())
    missing = sorted(EXPECTED_TOOLS - actual)
    unexpected = sorted(actual - EXPECTED_TOOLS)
    llm_schemas = registry.get_all_llm_format()
    valid_schemas = [
        schema for schema in llm_schemas
        if schema.get("name") and schema.get("description") and schema.get("parameters", {}).get("type") == "object"
    ]
    coverage_score = len(actual & EXPECTED_TOOLS) / len(EXPECTED_TOOLS) * 70
    schema_score = len(valid_schemas) / max(len(llm_schemas), 1) * 30
    score = coverage_score + schema_score
    return metric(
        "tool_coverage",
        score,
        15,
        status_from_score(score) if not missing else "fail",
        {
            "expected_tools": len(EXPECTED_TOOLS),
            "actual_tools": len(actual),
            "valid_llm_schemas": len(valid_schemas),
            "missing": missing,
            "unexpected": unexpected,
        },
    )


def evaluate_workflow_routing() -> dict[str, Any]:
    from agent.core.workflow_router import WorkflowRouter

    router = WorkflowRouter()
    cases = [
        ("请完成PLUS土地利用模拟并预测2033年", False, True),
        ("用2003和2013数据模拟未来土地利用", False, True),
        ("请按PLUS标准流程进行土地利用模拟", False, True),
        ("我要运行PLUS完整工作流", False, True),
        ("解释一下LEAS模块的原理", False, False),
        ("帮我看看有哪些文件", False, False),
        ("只运行 convert 工具", False, False),
        ("ok", False, False),
        ("继续", True, True),
    ]
    results = []
    for text, active, expected in cases:
        actual = router.should_use_workflow(text, has_active_workflow=active)
        results.append({
            "text": text,
            "active_workflow": active,
            "expected": expected,
            "actual": actual,
            "passed": actual == expected,
        })
    passed = sum(1 for item in results if item["passed"])
    score = passed / len(results) * 100
    return {
        **metric(
            "workflow_routing",
            score,
            15,
            status_from_score(score),
            {"cases": results},
        ),
        "passed": passed,
        "total": len(results),
        "positive_cases": sum(1 for _, _, expected in cases if expected),
        "negative_cases": sum(1 for _, _, expected in cases if not expected),
    }


def evaluate_mock_workflow() -> dict[str, Any]:
    from agent.core.default_parameter_agent import DefaultParameterAgent
    from agent.core.plus_workflow_runner import PLUSWorkflowRunner
    from agent.core.workflow_state import WorkflowContext
    from agent.tools.base import BaseTool, ToolResult
    from agent.tools.registry import ToolRegistry

    class EvalTool(BaseTool):
        name = "eval_tool"
        description = "Evaluation fake tool"
        parameters = {"type": "object", "properties": {}, "required": []}

        def __init__(self, name: str):
            self.name = name

        def execute(self, params: dict) -> ToolResult:
            if self.name == "convert":
                paths = list(params.get("output_paths") or [])
                return ToolResult(
                    success=bool(paths),
                    message="convert ok",
                    output_paths=paths,
                    artifacts={
                        "converted_lulc_paths": paths,
                        "early_lulc": paths[0] if paths else "",
                        "late_lulc": paths[-1] if paths else "",
                    },
                    error="" if paths else "missing output_paths",
                )
            if self.name == "expansion":
                path = params.get("output_change", "")
                return ToolResult(
                    success=bool(path),
                    message="expansion ok",
                    output_paths=[path] if path else [],
                    artifacts={"expansion_raster": path} if path else {},
                    error="" if path else "missing output_change",
                )
            if self.name == "leas":
                paths = [
                    str(PROJECT_ROOT / "eval_outputs" / "leas" / "potential_band_1.tif"),
                    str(PROJECT_ROOT / "eval_outputs" / "leas" / "potential_band_2.tif"),
                ]
                return ToolResult(
                    success=True,
                    message="leas ok",
                    output_paths=paths,
                    artifacts={"probability_paths": paths},
                )
            if self.name == "markov":
                path = str(PROJECT_ROOT / "eval_outputs" / "markov" / "markov.csv")
                return ToolResult(
                    success=True,
                    message="markov ok",
                    output_paths=[path],
                    artifacts={"markov_csv": path, "yearly_demands": "1,100,200"},
                )
            if self.name == "neighborhood_weight":
                return ToolResult(
                    success=True,
                    message="neighborhood_weight ok",
                    artifacts={"neighborhood_weights": "0.3,0.7"},
                )
            if self.name == "cars":
                path = params.get("output_simulation", "")
                return ToolResult(
                    success=bool(path),
                    message="cars ok",
                    output_paths=[path] if path else [],
                    artifacts={"simulation_raster": path} if path else {},
                    error="" if path else "missing output_simulation",
                )
            return ToolResult(success=False, error=f"unexpected tool {self.name}")

    registry = ToolRegistry()
    for name in ("convert", "expansion", "leas", "markov", "neighborhood_weight", "cars"):
        registry.register(EvalTool(name))

    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = str(Path(tmpdir) / "outputs")
        context = WorkflowContext(
            thread_id="eval-thread",
            user_message="请基于2003和2013土地利用数据预测2033年",
            lulc_files=[
                str(Path(tmpdir) / "wh2003_refy.tif"),
                str(Path(tmpdir) / "wh2013_refy.tif"),
            ],
            driver_files=[str(Path(tmpdir) / "drivers" / "dem.tif")],
            output_dir=output_dir,
            drivers_dir=str(Path(tmpdir) / "drivers"),
        )
        runner = PLUSWorkflowRunner(registry, DefaultParameterAgent())
        state = runner.start("eval-thread", context)
        seen_steps = []
        missing_fields = []
        successful_steps = 0
        for _ in range(10):
            if state.status == "completed":
                break
            event = runner.prepare_next(state, context)
            seen_steps.append(event.get("step"))
            if event["type"] != "workflow_confirm":
                missing_fields.extend(event.get("proposal").missing_fields)
                break
            ready = runner.apply_user_reply(state, "ok")
            if ready["type"] != "workflow_ready":
                break
            result = runner.execute_current_step(state)
            if result.get("success"):
                successful_steps += 1
            else:
                break

    expected_steps = ["convert", "expansion", "leas", "markov", "neighborhood_weight", "cars"]
    completed = state.status == "completed"
    sequence_ok = seen_steps == expected_steps
    critical_artifacts = ["yearly_demands", "neighborhood_weights", "simulation_raster"]
    artifacts_ok = [key for key in critical_artifacts if key in state.artifacts]
    score_parts = [
        40 if completed else 0,
        30 if sequence_ok else 0,
        successful_steps / len(expected_steps) * 20,
        len(artifacts_ok) / len(critical_artifacts) * 10,
    ]
    score = sum(score_parts)
    return metric(
        "mock_workflow",
        score,
        15,
        status_from_score(score),
        {
            "completed": completed,
            "seen_steps": seen_steps,
            "successful_steps": successful_steps,
            "expected_steps": expected_steps,
            "missing_fields": missing_fields,
            "critical_artifacts_present": artifacts_ok,
        },
    )


def evaluate_memory_isolation() -> dict[str, Any]:
    from agent.core.workflow_state import WorkflowState
    from agent.memory.store import MemoryStore

    checks = []
    with tempfile.TemporaryDirectory() as tmpdir:
        memory = MemoryStore(str(Path(tmpdir) / "memory.db"))
        memory.save_summary("thread-a", "u1", "summary one", user_id="user-one", thread_id="thread-a")
        memory.save_summary("thread-a", "u2", "summary two", user_id="user-two", thread_id="thread-a")
        checks.append(memory.get_summary("thread-a", user_id="user-one")["summary"] == "summary one")
        checks.append(memory.get_summary("thread-a", user_id="user-two")["summary"] == "summary two")

        memory.set_scoped_preference("path_refy", "C:/u1/a.tif", user_id="user-one", thread_id="thread-a")
        memory.set_scoped_preference("path_refy", "C:/u1/b.tif", user_id="user-one", thread_id="thread-b")
        checks.append(memory.get_frequent_paths(user_id="user-one", thread_id="thread-a") == ["C:/u1/a.tif"])

        run_id = memory.save_run("run", ["convert"], {}, [], user_id="user-one", thread_id="thread-a")
        memory.save_step(run_id, "convert", 1, {})
        detail = memory.get_run_detail(run_id)
        checks.append(detail["user_id"] == "user-one" and detail["steps"][0]["thread_id"] == "thread-a")

        state = WorkflowState(thread_id="thread-a", status="completed")
        state.steps["cars"].status = "success"
        state.steps["cars"].output_paths = ["C:/thread-a/simulation.tif"]
        state.steps["cars"].artifacts = {"simulation_raster": "C:/thread-a/simulation.tif"}
        memory.save_workflow_run("user-one", "thread-a", state)
        memory.save_workflow_artifacts("user-one", "thread-a", state)
        checks.append(bool(memory.get_thread_artifacts("user-one", "thread-a")))
        checks.append(memory.get_thread_artifacts("user-one", "thread-b") == [])

    passed = sum(1 for item in checks if item)
    score = passed / len(checks) * 100
    return metric(
        "memory_isolation",
        score,
        10,
        status_from_score(score),
        {"passed": passed, "total": len(checks)},
    )


def evaluate_frontend_data_panel() -> dict[str, Any]:
    main_py = (PROJECT_ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    auth_js = (PROJECT_ROOT / "public" / "auth.js").read_text(encoding="utf-8")
    geoscene = (PROJECT_ROOT / "public" / "elements" / "GeoSceneRaster.jsx").read_text(encoding="utf-8")
    checks = {
        "catalog_endpoint": "/plus/data-catalog" in main_py,
        "preview_endpoint": "/plus/data-preview/{file_id}" in main_py,
        "thread_scoped_catalog": "_current_request_thread_id" in main_py and "_thread_workspace_root" in main_py,
        "frontend_fetches_catalog": "/plus/data-catalog" in auth_js and "withThreadParam" in auth_js,
        "frontend_fetches_preview": "/plus/data-preview/" in auth_js,
        "geoscene_sdk_loaded": "https://js.geoscene.cn/4.32/" in auth_js and "https://js.geoscene.cn/4.32/" in geoscene,
        "csv_preview_supported": "renderTablePreview" in auth_js and "pd.read_csv" in main_py,
        "raster_preview_supported": "MediaLayer" in auth_js and "GeoSceneRaster" in geoscene,
    }
    passed = sum(1 for value in checks.values() if value)
    score = passed / len(checks) * 100
    return metric(
        "frontend_data_panel",
        score,
        5,
        status_from_score(score),
        {"passed": passed, "total": len(checks), "checks": checks},
    )


def run_command(name: str, command: list[str], weight: float) -> dict[str, Any]:
    started = datetime.now()
    try:
        proc = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        output = proc.stdout or ""
        score = 100.0 if proc.returncode == 0 else 0.0
        test_count = None
        match = re.search(r"Ran (\d+) tests?", output)
        if match:
            test_count = int(match.group(1))
        return metric(
            name,
            score,
            weight,
            "pass" if proc.returncode == 0 else "fail",
            {
                "command": " ".join(command),
                "exit_code": proc.returncode,
                "duration_seconds": round((datetime.now() - started).total_seconds(), 2),
                "test_count": test_count,
                "tail": "\n".join(output.strip().splitlines()[-20:]),
            },
        )
    except subprocess.TimeoutExpired as exc:
        return metric(
            name,
            0,
            weight,
            "fail",
            {
                "command": " ".join(command),
                "duration_seconds": round((datetime.now() - started).total_seconds(), 2),
                "tail": f"Timed out after {exc.timeout} seconds.",
            },
        )


def calculate_overall(metrics: dict[str, dict[str, Any]]) -> float:
    total_weight = sum(item["weight"] for item in metrics.values())
    if not total_weight:
        return 0.0
    weighted = sum(item["score"] * item["weight"] for item in metrics.values())
    return round(weighted / total_weight, 2)


def grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def run_evaluation(run_commands: bool = True, write_files: bool = True) -> dict[str, Any]:
    metrics = {
        "tool_coverage": evaluate_tool_coverage(),
        "workflow_routing": evaluate_workflow_routing(),
        "mock_workflow": evaluate_mock_workflow(),
        "memory_isolation": evaluate_memory_isolation(),
        "frontend_data_panel": evaluate_frontend_data_panel(),
    }
    if run_commands:
        py = sys.executable
        metrics.update({
            "unit_tests": run_command("unit_tests", [py, "-m", "unittest", "discover", "-s", "tests", "-v"], 20),
            "compile_check": run_command("compile_check", [py, "-m", "compileall", "agent", "tests"], 8),
            "app_import": run_command("app_import", [py, "-c", "from agent.main import app; print('main import OK')"], 7),
            "memory_migration": run_command(
                "memory_migration",
                [py, "-c", "from agent.memory.store import MemoryStore; MemoryStore('data/memory.db'); print('memory migration OK')"],
                5,
            ),
        })

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(PROJECT_ROOT),
        "overall_score": calculate_overall(metrics),
        "metrics": metrics,
        "limitations": [
            "This automatic evaluation does not call a real LLM backend.",
            "This automatic evaluation does not run PLUS.exe on real GeoTIFF datasets.",
            "Raster visual quality is checked by static integration signals, not by browser screenshots.",
        ],
    }
    report["grade"] = grade(report["overall_score"])
    if write_files:
        write_report_files(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# PLUS Agent Evaluation Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Project: `{report['project_root']}`",
        f"- Overall score: **{report['overall_score']} / 100**",
        f"- Grade: **{report['grade']}**",
        "",
        "## Metrics",
        "",
        "| Metric | Weight | Score | Status | Key result |",
        "|---|---:|---:|---|---|",
    ]
    for name, item in report["metrics"].items():
        details = item["details"]
        key_result = ""
        if "passed" in details and "total" in details:
            key_result = f"{details['passed']}/{details['total']} checks passed"
        elif "exit_code" in details:
            key_result = f"exit {details['exit_code']}"
            if details.get("test_count") is not None:
                key_result += f", {details['test_count']} tests"
        elif name == "tool_coverage":
            key_result = f"{details['actual_tools']}/{details['expected_tools']} tools, {details['valid_llm_schemas']} valid schemas"
        elif name == "workflow_routing":
            key_result = f"{item['passed']}/{item['total']} routing cases"
        elif name == "mock_workflow":
            key_result = f"{details['successful_steps']}/6 steps, completed={details['completed']}"
        lines.append(f"| `{name}` | {item['weight']:.0f} | {item['score']:.2f} | {item['status']} | {key_result} |")

    lines.extend([
        "",
        "## Notes",
        "",
    ])
    for note in report["limitations"]:
        lines.append(f"- {note}")
    lines.extend([
        "",
        "## Next Manual Evals",
        "",
        "- Use one fixed sample dataset and run the real workflow end to end.",
        "- Measure parameter confirmation friction: number of user edits per workflow and failed-step recovery rate.",
        "- Compare simulated raster against validation data with Kappa/FoM where ground truth exists.",
        "- Browser-test the data panel with screenshots for map rendering and CSV preview layout.",
    ])
    return "\n".join(lines) + "\n"


def write_report_files(report: dict[str, Any]) -> dict[str, str]:
    out_dir = PROJECT_ROOT / "evaluation_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"agent_eval_{stamp}.json"
    md_path = out_dir / f"agent_eval_{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    report["output_files"] = {"json": str(json_path), "markdown": str(md_path)}
    return report["output_files"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate PLUS Agent deterministic capabilities.")
    parser.add_argument("--no-commands", action="store_true", help="Skip subprocess health checks.")
    parser.add_argument("--no-files", action="store_true", help="Do not write report files.")
    args = parser.parse_args()
    report = run_evaluation(run_commands=not args.no_commands, write_files=not args.no_files)
    print(render_markdown(report))
    if report.get("output_files"):
        print("Report files:")
        for kind, path in report["output_files"].items():
            print(f"- {kind}: {path}")
    return 0 if report["overall_score"] >= 70 else 1


if __name__ == "__main__":
    raise SystemExit(main())
