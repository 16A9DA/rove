# AgentNet integration

## What AgentNet is

[`xlangai/AgentNet`](https://huggingface.co/datasets/xlangai/AgentNet) is a public Hugging
Face dataset of 22.6K human-annotated computer-use tasks across Windows, macOS, and Ubuntu
(~200GB total, MIT licensed). It ships as three JSONL files plus split zip archives of PNG
screenshots (not needed by this integration — see below):

* `agentnet_ubuntu_5k.jsonl` / `agentnet_win_mac_18k.jsonl` — one JSON object per task:
  `task_id`, `instruction`, `natural_language_task`, `actual_task`, `task_completed`,
  `alignment_score`, `efficiency_score`, `task_difficulty`, `domain`, and `traj` — a list of
  steps. Each step has `index`, `image` (a screenshot filename) and a `value` dict with
  `code` (a literal `pyautogui.*`/`computer.*` call string, e.g.
  `"pyautogui.click(x=0.377, y=0.193)"`), `action` (a natural-language narration of that
  call), `observation`, `thought`, `reflection`, `last_step_correct`, `last_step_redundant`.
* `meta_data_merged.jsonl` — one lightweight summary row per task (`system`, `release`,
  `applications`, `websites`, `step_num`, `screen_width`/`height`, `complexity`,
  `action_frequency`, ...), no trajectory or screenshot payload.

These field names were read directly off the live dataset (`curl`-ed byte ranges of the
actual JSONL files and the Hub's file-listing API) while building this integration, not
assumed from the dataset card.

## Why Rove uses it

Rove's agent loop (`backend/app/agents/`) drives `click`/`type`/`keypress`/`scroll` through
a `ComputerController`. AgentNet is a large, independently-collected sample of what those
same primitives look like across real desktop tasks — useful as reference/eval data for
Rove's computer-use layer without touching the agent runtime itself.

## What we extract

Only the JSONL trajectory text — never the screenshot archives (200GB of split zips), which
this integration doesn't download or reference beyond the filename already present in each
step. From each step, `evaluation/agentnet/parser.py` parses the `code` string (via
`ast.literal_eval`, never `eval()`/`exec()` — it's untrusted external text) into a
`RoveAction` (`evaluation/agentnet/schema.py`):

```json
{"action": "click", "target": {"description": "Click on the GIMP application icon..."}, "coordinate": {"x": 0.377, "y": 0.193}}
```

`action` is one of `click | type | keypress | hotkey | scroll | drag | move | wait | finish
| unsupported`. `target.description` is the step's natural-language `action` narration —
the closest thing AgentNet has to a semantic element label, since it has no verified
UI-element/accessibility labels. `coordinate` is kept as dataset-specific fallback
information, never the primary field, per Rove's own controller-independent action design.
Anything that doesn't parse (unrecognized function, malformed code, a missing `code` field)
normalizes to `action: "unsupported"` with a `reason`, rather than raising — a single bad
row shouldn't fail a whole evaluation run.

## What we are NOT using this for yet

* No training or fine-tuning. No PyTorch added by this integration (`datasets` itself has
  no torch dependency).
* No new computer-use model.
* Doesn't replace or touch `AgentRuntime`, `AnthropicProvider`/`OpenAIProvider`, or any
  `ComputerController`.
* Doesn't run Rove against AgentNet tasks yet — `pipeline.run_evaluation()` only loads,
  normalizes, and reports statistics. Actually replaying a task against a live
  `BrowserController`/`NativeComputerController` (and scoring the result) is future work,
  once there's a reason to benchmark Rove's own agent this way.

## How this can later become training data

`NormalizedStep`/`RoveAction` already are the shape a supervised fine-tuning or preference
dataset would need (instruction + semantic action sequence), decoupled from AgentNet's raw
`pyautogui` call syntax. If Rove ever trains a computer-use model, this module is where the
raw-to-normalized conversion already lives — the missing pieces would be a training loop and
a model, both explicitly out of scope here.

## Loading a subset without downloading 200GB

`evaluation/agentnet/loader.py` uses `datasets.load_dataset(..., streaming=True)`, which
opens the Hub files as a lazy iterator — `load_tasks(limit=5)` only ever pulls 5 rows over
the wire, not the whole multi-GB trajectory file. `load_metadata()` reads
`meta_data_merged.jsonl` instead, which is orders of magnitude lighter (no trajectory
payload) and a better source for a larger filtering/stats sample.

## Running it locally

```
cd backend
.venv/bin/python -m evaluation.agentnet --limit 5 --source ubuntu
```

Prints the stats JSON (`num_tasks`, `num_steps`, `completion_rate`, `avg_steps_per_task`,
`action_counts`, `unsupported_count`) for a 5-task streamed subset. `--source win_mac` pulls
from the Windows/macOS trajectory file instead. First run is slower (tens of seconds) while
`datasets` resolves the Hub file; later rows stream faster.

Programmatically:

```python
from evaluation.agentnet import run_evaluation

report = run_evaluation(limit=5, source="ubuntu")
report.stats.to_dict()          # summary counts
report.normalized["<task_id>"]  # list[NormalizedStep] for one task
```

## Limitations

* `target.description` is narration text generated by whatever model produced the AgentNet
  trajectory, not a verified ground-truth UI label — treat it as a useful proxy, not ground
  truth.
* The `code` parser covers the pyautogui/`computer.*` surface observed in the dataset
  (click family, moveTo/dragTo, write, press, hotkey, scroll, wait, terminate). Anything
  outside that normalizes to `unsupported` rather than guessing.
* No screenshot/image loading — `image` is kept only as a filename reference.
* `load_tasks()`'s streaming-then-take approach still walks the file from the start each
  call; there's no persistent cursor/offset yet for resuming a large sweep across runs.
