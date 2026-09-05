# PLUS Workflow Parameter Agent Design

## Goal

Refactor the PLUS simulation path into a deterministic workflow runner with a replaceable parameter-generation component. The first implementation ships a default parameter agent that proposes conservative parameters from the current session files and prior step outputs, then pauses before every PLUS tool execution so the user can review or edit parameters.

This design keeps the existing Chainlit UI, tool registry, ReAct chat loop, and PLUS tool wrappers. It changes the responsibility boundaries so ReAct no longer has to remember and drive the full PLUS workflow by itself.

## Scope

The first version covers the standard simulation workflow:

```text
convert -> expansion -> leas -> markov -> neighborhood_weight -> cars
```

Validation remains optional. The workflow runner should offer validation only when the user has supplied a real reference raster for the target year or explicitly asks to validate an existing simulation result.

The first parameter agent is named `DefaultParameterAgent`. It is deterministic and rule-based. It does not use a separate knowledge base, vector store, retrieval pipeline, or private tool set. Those capabilities are added later behind the same `ParameterProvider` interface.

## Non-Goals

- Do not replace Chainlit.
- Do not remove the existing ReAct loop for ordinary chat and ad hoc tool calls.
- Do not make the first parameter agent responsible for executing PLUS tools.
- Do not require the whole workflow to finish inside one user message.
- Do not introduce a knowledge base in the first version.

## Current Problem

The current system exposes each PLUS module as a callable tool and tells the LLM in the system prompt to follow the standard simulation sequence. This is flexible, but the execution order is prompt-driven. The model may stop after one tool, skip a dependency, fail to reuse a prior output, or lose the workflow state after a parameter confirmation.

The project already contains a `WorkflowEngine`, but the Chainlit message path currently runs through `ReactLoop`. The existing workflow engine is not acting as the primary controller for user-initiated PLUS simulations.

## Architecture

```text
Chainlit on_message
  |
  v
WorkflowRouter
  |
  |-- ordinary chat or ad hoc tool use --> ReactLoop
  |
  |-- full PLUS simulation intent ------> PLUSWorkflowRunner
                                            |
                                            v
                                     ParameterProvider
                                            |
                                            |-- DefaultParameterAgent
                                            |
                                            |-- future KnowledgeParameterAgent
```

### WorkflowRouter

`WorkflowRouter` decides whether a user message should continue normal ReAct chat or enter a managed PLUS workflow.

It starts or resumes a workflow when:

- the current Chainlit session already has an active workflow;
- the user explicitly asks for a complete PLUS simulation;
- the user asks to simulate or predict future land-use change and the session contains enough LULC context to begin collecting parameters;
- the user sends workflow control commands such as `继续`, `取消工作流`, `查看工作流状态`, or `重新执行上一步`.

If the message is a general question, file-browsing request, explanation request, or one-off tool request, the router leaves it on the existing ReAct path.

### PLUSWorkflowRunner

`PLUSWorkflowRunner` is the workflow state machine. It owns step order, dependency checks, user confirmation, execution, artifact recording, and resume behavior.

Responsibilities:

- create a workflow state for the current Chainlit thread;
- select the next runnable step;
- call `ParameterProvider` for that step's proposed parameters;
- render a confirmation prompt before executing the step;
- accept user edits as `key=value` overrides;
- validate required parameters and dependency artifacts;
- execute the step through `ToolRegistry`;
- store structured outputs in workflow state;
- stop with a clear error if a dependency or tool fails;
- resume the same workflow after the user sends another message.

The runner must not infer scientific defaults that belong in the parameter agent. Its job is orchestration.

### ParameterProvider Interface

Every parameter agent must implement the same boundary:

```python
class ParameterProvider:
    def propose(
        self,
        step_name: str,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        ...

    def revise(
        self,
        step_name: str,
        proposal: ParameterProposal,
        user_overrides: dict,
        state: WorkflowState,
        context: WorkflowContext,
    ) -> ParameterProposal:
        ...
```

`ParameterProposal` contains:

```python
{
    "step": "cars",
    "params": {},
    "missing_fields": [],
    "assumptions": [],
    "warnings": []
}
```

The workflow runner can display this object directly to the user. Later, a knowledge-backed parameter agent can return the same object shape without changing workflow execution.

### DefaultParameterAgent

`DefaultParameterAgent` is the first `ParameterProvider` implementation.

It proposes parameters from:

- session-level uploaded files;
- the session output directory;
- structured artifacts produced by completed workflow steps;
- years parsed from user text or file names;
- tool schema defaults already defined by each PLUS tool.

It must be conservative:

- when multiple LULC rasters are available, sort by detected year first, then by filename;
- when no reliable year is found, ask for `start_year`, `end_year`, and `predict_year`;
- when multiple driver folders are possible, choose the active session driver upload folder and warn the user;
- when class count cannot be inferred, ask the user instead of inventing it;
- when no policy or constraint raster exists, use an empty `policy_path`;
- when no transition matrix is supplied, generate an all-allowed square matrix based on `input_classes`.

## Workflow State

`WorkflowState` is persisted per Chainlit thread.

Minimum fields:

```python
{
    "workflow_id": "uuid",
    "thread_id": "chainlit-thread-id",
    "status": "collecting|waiting_confirmation|running|failed|completed|cancelled",
    "current_step": "convert",
    "requested_target_year": 2035,
    "steps": {},
    "artifacts": {},
    "created_at": "iso-datetime",
    "updated_at": "iso-datetime"
}
```

Each step stores:

```python
{
    "name": "markov",
    "status": "pending|waiting_confirmation|running|success|failed|skipped",
    "params": {},
    "output_paths": [],
    "artifacts": {},
    "error": ""
}
```

Important artifacts:

- `converted_lulc_paths`
- `early_lulc`
- `late_lulc`
- `expansion_raster`
- `probability_paths`
- `markov_csv`
- `yearly_demands`
- `neighborhood_weights`
- `simulation_raster`
- `validation_csv`

## Default Step Parameters

### convert

Inputs:

- all session LULC `.tif` or `.tiff` files sorted by detected year;
- output paths under the session output directory.

Default output pattern:

```text
<output_dir>/convert/<input_stem>_converted.tif
```

Missing fields:

- `input_paths` when no LULC rasters exist in the session.

### expansion

Inputs:

- `early_lulc`: earliest converted LULC;
- `late_lulc`: latest converted LULC;
- `output_change`: `<output_dir>/expansion/expansion.tif`.

The step records the actual PLUS output ending in `_landuse_1to2.tif`.

Missing fields:

- `early_lulc` and `late_lulc` when fewer than two LULC rasters exist.

### leas

Inputs:

- `input_lulc`: `expansion_raster`;
- `feature_folder`: active session driver folder;
- `output_probability`: `<output_dir>/leas/potential.tif`;
- `sampling_rate`: `0.01`;
- `m_try`: `16`;
- `n_trees`: `20`;
- `thread_count`: `8`.

The step records probability bands and contribution tables separately. Probability bands become the structured artifact `probability_paths`.

Missing fields:

- `feature_folder` when no driver folder exists;
- `input_lulc` when expansion has not succeeded.

### markov

Inputs:

- `start_map`: earliest converted LULC;
- `end_map`: latest converted LULC;
- `start_year`: parsed from earliest LULC name or user message;
- `end_year`: parsed from latest LULC name or user message;
- `predict_year`: parsed from user message;
- `output_dir`: `<output_dir>/markov`.

The step records `markov.csv` and `yearly_demands`. If `yearly_demands` cannot be parsed from `markov.csv`, the workflow must stop and ask the user to provide CARS demand values.

Missing fields:

- `start_year`, `end_year`, or `predict_year` when they cannot be parsed.

### neighborhood_weight

Inputs:

- `expansion_raster`: artifact from expansion;
- `num_classes`: inferred from probability band count after LEAS, or from raster class statistics when available;
- `background_values`: `0,255`.

The step records `neighborhood_weights` as a comma-separated string.

Missing fields:

- `num_classes` when it cannot be inferred.

### cars

Inputs:

- `input_classes`: probability band count;
- `input_lulc`: latest converted LULC by default;
- `probability_paths`: LEAS probability bands;
- `output_simulation`: `<output_dir>/cars/simulation.tif`;
- `policy_path`: first session constraint raster when available, otherwise empty string;
- `neighborhood`: `3`;
- `thread_count`: `8`;
- `patch_generation`: `0.2`;
- `expansion_coefficient`: `0.2`;
- `neighborhood_weights`: artifact from neighborhood_weight;
- `transition_matrix`: all-allowed `input_classes` by `input_classes` matrix;
- `yearly_demands`: artifact from markov;
- `seed_percentage`: `0.1`.

The step records the actual PLUS output matching `simulationSimulation_*.tif` or the equivalent basename produced by the current CARS tool.

Missing fields:

- `probability_paths` when LEAS has not produced bands;
- `yearly_demands` when Markov did not provide demand values;
- `neighborhood_weights` when neighborhood_weight has not succeeded;
- `input_classes` when no band count is available.

### validation

Validation is not part of the required first workflow. The runner may offer it after CARS succeeds if a real target-year reference raster is present. The user can also trigger it later.

Default parameters:

- `simulated_map`: `simulation_raster`;
- `real_map`: user-provided reference raster;
- `start_map`: latest converted LULC used by CARS;
- `is_fom`: `0`;
- `sampling_rate`: `0.1`;
- `output_dir`: `<output_dir>/validation`.

## User Confirmation Flow

Before each step executes, Chainlit shows:

```text
即将执行：cars

参数:
- input_classes = 6
- input_lulc = C:/...
- probability_paths = [...]
- neighborhood_weights = 0.1,0.2,...
- yearly_demands = 1,...

假设:
- 使用最新一期 LULC 作为 CARS 起始图。

警告:
- 未检测到约束图，policy_path 将为空。

回复 ok 执行。
回复 参数=新值 修改，例如 predict_year=2035。
回复 cancel 取消工作流。
```

If the user edits parameters, the runner calls `ParameterProvider.revise`, revalidates the proposal, and shows the updated confirmation. The step is executed only after the user replies `ok`.

## Resume Behavior

The workflow must not depend on a single long ReAct turn. A user may leave after any confirmation prompt or tool result and continue later.

Resume rules:

- `waiting_confirmation`: re-show the pending step parameters;
- `failed`: show failed step, error, and available commands;
- `running`: prevent duplicate execution of the same step;
- `completed`: return normal chat unless the user asks to inspect outputs or start another workflow.

## Relationship With ReAct

ReAct remains available for:

- ordinary conversation;
- explaining PLUS concepts;
- helping users locate files;
- ad hoc one-tool calls;
- explaining workflow results after each step;
- summarizing failures and suggestions.

The managed workflow does not rely on ReAct to decide the next step. It may ask the LLM to explain a completed step in user-friendly language, but the runner owns the state transition.

## Future Knowledge-Backed Parameter Agent

The later `KnowledgeParameterAgent` plugs into the same `ParameterProvider` interface. It may use:

- a PLUS tutorial knowledge base;
- raster metadata inspection tools;
- CSV statistics tools;
- historical project parameter examples;
- policy or scenario templates;
- model-specific validation rules.

It still returns `ParameterProposal`. The workflow runner, UI confirmation, tool execution, and artifact storage do not need to change.

## Error Handling

- Missing required parameters put the workflow into `collecting` state.
- Failed tool execution puts the workflow into `failed` state and records the tool error.
- Failed artifact extraction stops the workflow before downstream steps.
- Parameter edits that fail type parsing are rejected before the tool runs.
- If a step output file is missing, downstream steps are blocked.
- If `plus-backend` path contains unsupported characters for the PLUS executable, show a path-specific error before launching a long workflow.

## Implementation Shape

New files:

- `agent/core/workflow_state.py`: dataclasses for workflow state, steps, proposals, and context.
- `agent/core/parameter_provider.py`: `ParameterProvider` interface and default parsing helpers.
- `agent/core/default_parameter_agent.py`: deterministic first parameter agent.
- `agent/core/plus_workflow_runner.py`: workflow state machine.
- `agent/core/workflow_router.py`: routes messages between managed workflow and ReAct.

Modified files:

- `agent/ui/callbacks.py`: call `WorkflowRouter` before `ReactLoop`; render step confirmations and workflow results.
- `agent/memory/schema.sql`: add workflow state persistence tables or JSON state records.
- `agent/memory/store.py`: add workflow save/load/update helpers.
- `agent/tools/base.py`: optionally extend `ToolResult` with structured `artifacts`.
- `agent/tools/markov.py`: expose parsed `yearly_demands` as a structured artifact.
- `agent/tools/leas.py`: expose probability bands and contribution CSVs as structured artifacts.
- `agent/tools/neighborhood_weight.py`: expose `neighborhood_weights` as a structured artifact.
- `agent/tools/cars.py`: expose `simulation_raster` as a structured artifact.

## Testing Strategy

- Unit test `DefaultParameterAgent` with synthetic session contexts.
- Unit test year parsing from filenames and user messages.
- Unit test transition matrix generation for class counts 1, 2, and 6.
- Unit test parameter edit parsing for strings, numbers, arrays, and cancel commands.
- Unit test workflow state transitions with fake tools.
- Unit test that CARS cannot run before Markov and neighborhood_weight artifacts exist.
- Integration test the full workflow with mocked `ToolRegistry.execute` results.
- Manual Chainlit test with one small uploaded dataset to verify confirmation prompts appear before every step.

## Success Criteria

- A user can start a standard PLUS simulation in one message and continue across multiple confirmation replies.
- The user sees proposed parameters before every PLUS tool execution.
- The user can modify parameters before each step runs.
- The workflow resumes from its saved state instead of restarting after every message.
- CARS receives `yearly_demands` and `neighborhood_weights` from structured artifacts, not from LLM memory.
- ReAct remains available for normal chat and ad hoc tool use.
- A future knowledge-backed parameter agent can replace `DefaultParameterAgent` without changing `PLUSWorkflowRunner`.
