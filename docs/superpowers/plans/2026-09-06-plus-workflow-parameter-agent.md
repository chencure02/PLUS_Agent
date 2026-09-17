# PLUS Workflow Parameter Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first managed PLUS workflow that uses a replaceable default parameter agent and pauses for user confirmation before each tool step.

**Architecture:** Add workflow state dataclasses, a `ParameterProvider` interface, a rule-based `DefaultParameterAgent`, a `PLUSWorkflowRunner`, and a `WorkflowRouter`. Chainlit routes full simulation requests to the workflow runner while ordinary chat continues through the existing ReAct loop.

**Tech Stack:** Python 3.11, Chainlit, SQLite, existing PLUS tool registry, unittest.

**Spec:** `docs/superpowers/specs/2026-09-05-plus-workflow-parameter-agent-design.md`

## Global Constraints

- Keep Chainlit, the existing ReAct loop, current tool registry, and current PLUS wrappers.
- First version covers `convert -> expansion -> leas -> markov -> neighborhood_weight -> cars`.
- Validation is optional and not required for the first managed workflow.
- The first parameter agent is deterministic and rule-based.
- The workflow must not require the whole simulation to finish inside one user message.
- Every PLUS step must show parameters before execution and allow user edits.
- Future knowledge-backed parameter agents must be replaceable behind the same `ParameterProvider` interface.

---

### Task 1: Workflow State And Parameter Provider

**Files:**
- Create: `agent/core/workflow_state.py`
- Create: `agent/core/parameter_provider.py`
- Test: `tests/test_parameter_provider.py`

**Interfaces:**
- Produces: `WorkflowContext`, `WorkflowState`, `WorkflowStepState`, `ParameterProposal`, `ParameterProvider`, `parse_user_overrides`, `format_confirmation`.

- [ ] **Step 1: Write failing tests**

Create tests that assert:

```python
overrides = parse_user_overrides("predict_year=2035, sampling_rate=0.02, probability_paths=a.tif|b.tif")
assert overrides["predict_year"] == 2035
assert overrides["sampling_rate"] == 0.02
assert overrides["probability_paths"] == ["a.tif", "b.tif"]
```

Also assert `format_confirmation(ParameterProposal(...))` includes parameters, assumptions, warnings, and the `ok`/`cancel` guidance.

- [ ] **Step 2: Run red test**

Run: `python -m unittest tests.test_parameter_provider -v`

Expected: fails because modules do not exist.

- [ ] **Step 3: Implement state and provider primitives**

Add serializable dataclasses and helper functions. `parse_user_overrides` must support comma-separated assignments, numbers, and pipe-separated arrays.

- [ ] **Step 4: Run green test**

Run: `python -m unittest tests.test_parameter_provider -v`

Expected: pass.

---

### Task 2: Default Parameter Agent

**Files:**
- Create: `agent/core/default_parameter_agent.py`
- Test: `tests/test_default_parameter_agent.py`

**Interfaces:**
- Consumes: `ParameterProvider`, `WorkflowContext`, `WorkflowState`, `ParameterProposal`.
- Produces: `DefaultParameterAgent.propose()` and `DefaultParameterAgent.revise()`.

- [ ] **Step 1: Write failing tests**

Create tests that assert:

```python
context = WorkflowContext(
    thread_id="thread-a",
    user_message="请基于2003和2013土地利用预测2033年",
    lulc_files=["C:/data/wh2013_refy.tif", "C:/data/wh2003_refy.tif"],
    driver_files=["C:/data/drivers/dem.tif"],
    constraint_files=[],
    output_dir="C:/out",
)
proposal = DefaultParameterAgent().propose("convert", WorkflowState(thread_id="thread-a"), context)
assert proposal.params["input_paths"] == ["C:/data/wh2003_refy.tif", "C:/data/wh2013_refy.tif"]
assert proposal.params["output_paths"][0].endswith("convert/wh2003_refy_converted.tif")
```

Also test `markov`, `neighborhood_weight`, and `cars` proposals using prefilled workflow artifacts.

- [ ] **Step 2: Run red test**

Run: `python -m unittest tests.test_default_parameter_agent -v`

Expected: fails because the default parameter agent does not exist.

- [ ] **Step 3: Implement default proposals**

Implement conservative defaults for each required step. Missing scientific values must be returned in `missing_fields` rather than guessed.

- [ ] **Step 4: Run green test**

Run: `python -m unittest tests.test_default_parameter_agent -v`

Expected: pass.

---

### Task 3: Workflow Runner And Structured Artifacts

**Files:**
- Create: `agent/core/plus_workflow_runner.py`
- Modify: `agent/tools/base.py`
- Modify: `agent/tools/markov.py`
- Modify: `agent/tools/leas.py`
- Modify: `agent/tools/neighborhood_weight.py`
- Modify: `agent/tools/cars.py`
- Test: `tests/test_plus_workflow_runner.py`

**Interfaces:**
- Consumes: `ToolRegistry`, `DefaultParameterAgent`, workflow dataclasses.
- Produces: `PLUSWorkflowRunner.start()`, `PLUSWorkflowRunner.prepare_next()`, `PLUSWorkflowRunner.apply_user_reply()`, `PLUSWorkflowRunner.execute_current_step()`, structured `ToolResult.artifacts`.

- [ ] **Step 1: Write failing tests**

Use fake tools that return `ToolResult(success=True, output_paths=[...], artifacts={...})`. Assert the runner:

```python
state = runner.start("thread-a", context)
event = runner.prepare_next(state, context)
assert event["type"] == "workflow_confirm"
assert event["step"] == "convert"
```

Then confirm `convert`, execute it, and assert the next confirmation step is `expansion`. Also assert CARS is blocked until `yearly_demands` and `neighborhood_weights` artifacts exist.

- [ ] **Step 2: Run red test**

Run: `python -m unittest tests.test_plus_workflow_runner -v`

Expected: fails because runner does not exist.

- [ ] **Step 3: Extend `ToolResult`**

Add `artifacts: dict = field(default_factory=dict)` while preserving existing callers.

- [ ] **Step 4: Add structured artifacts to PLUS tools**

Return `yearly_demands`, `probability_paths`, `contribution_tables`, `neighborhood_weights`, and `simulation_raster` where available.

- [ ] **Step 5: Implement runner**

Implement step order, dependency checks, confirmation preparation, confirmation handling, execution, artifact recording, and completion messages.

- [ ] **Step 6: Run green test**

Run: `python -m unittest tests.test_plus_workflow_runner -v`

Expected: pass.

---

### Task 4: Memory Persistence And Router

**Files:**
- Create: `agent/core/workflow_router.py`
- Modify: `agent/memory/schema.sql`
- Modify: `agent/memory/store.py`
- Test: `tests/test_workflow_router.py`

**Interfaces:**
- Produces: `WorkflowRouter.should_start_workflow()`, workflow save/load helpers on `MemoryStore`.

- [ ] **Step 1: Write failing tests**

Assert full simulation phrases route to workflow, ordinary chat routes to ReAct, and active workflow state routes back to workflow.

- [ ] **Step 2: Run red test**

Run: `python -m unittest tests.test_workflow_router -v`

Expected: fails because router/persistence helpers do not exist.

- [ ] **Step 3: Add persistence**

Create a `workflow_states` table keyed by `thread_id` and add JSON save/load/delete helpers.

- [ ] **Step 4: Implement router**

Use explicit workflow commands and conservative phrase matching for full simulation intent.

- [ ] **Step 5: Run green test**

Run: `python -m unittest tests.test_workflow_router -v`

Expected: pass.

---

### Task 5: Chainlit Integration

**Files:**
- Modify: `agent/ui/callbacks.py`
- Test: existing unit tests plus manual startup/import check.

**Interfaces:**
- Consumes: `WorkflowRouter`, `PLUSWorkflowRunner`.
- Preserves: existing upload handling, data panel rendering, settings handling, and ReAct fallback.

- [ ] **Step 1: Add workflow context creation**

After upload/session synchronization, build `WorkflowContext` from `session_files`, `out_dir`, and current user text.

- [ ] **Step 2: Route before ReAct**

If router selects workflow, process the current message through `PLUSWorkflowRunner` and return without invoking `ReactLoop`.

- [ ] **Step 3: Render workflow confirmations**

Use Chainlit `AskUserMessage` to show the proposal, accept `ok`, `cancel`, or `key=value` overrides, and loop until the step either executes or waits for missing fields.

- [ ] **Step 4: Render workflow tool results**

Reuse existing raster and CSV renderers for workflow outputs.

- [ ] **Step 5: Run verification**

Run:

```text
python -m unittest discover -s tests -v
python -m compileall agent tests
```

Expected: tests and compile checks pass.
