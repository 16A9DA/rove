import json

from evaluation.agentnet.loader import load_metadata, load_tasks
from evaluation.agentnet.normalize import normalize_task, normalize_tasks
from evaluation.agentnet.parser import parse_code
from evaluation.agentnet.pipeline import run_evaluation
from evaluation.agentnet.schema import AgentNetTask
from evaluation.agentnet.stats import compute_stats

TASK_ROWS = [
    {
        "task_id": "task-1",
        "instruction": "Open GIMP and load a picture.",
        "task_completed": True,
        "domain": "feasible",
        "traj": [
            {
                "index": 0,
                "image": "shot0.png",
                "value": {"code": "pyautogui.click(x=0.018, y=0.508)", "action": "Click the GIMP icon.", "observation": "desktop"},
            },
            {
                "index": 1,
                "image": "shot1.png",
                "value": {"code": "pyautogui.write(message='pikachu.jpeg')", "action": "Type the filename.", "observation": "open dialog"},
            },
            {
                "index": 2,
                "image": "shot2.png",
                "value": {"code": "pyautogui.press('enter')", "action": "Confirm the dialog.", "observation": "dialog"},
            },
            {
                "index": 3,
                "image": "shot3.png",
                "value": {
                    "code": "pyautogui.moveTo(x=0.364, y=0.42)\npyautogui.dragTo(x=0.508, y=0.425, button='left')",
                    "action": "Drag the layer.",
                    "observation": "canvas",
                },
            },
            {
                "index": 4,
                "image": "shot4.png",
                "value": {"code": "pyautogui.hotkey(['ctrl', 's'])", "action": "Save.", "observation": "canvas"},
            },
            {"index": 5, "image": "shot5.png", "value": {"code": "computer.terminate(status='success')", "action": "Done.", "observation": "canvas"}},
        ],
    },
    {
        "task_id": "task-2",
        "instruction": "An infeasible task.",
        "task_completed": False,
        "domain": "infeasible",
        "traj": [
            {"index": 0, "image": "s0.png", "value": {"code": "pyautogui.rightClick(x=0.1, y=0.2)", "action": "Right click.", "observation": "x"}},
            {"index": 1, "image": "s1.png", "value": {"code": "not_a_real_call(", "action": "Malformed.", "observation": "x"}},
            {"index": 2, "image": "s2.png", "value": {"code": "some.unknown_call(x=1)", "action": "Unknown function.", "observation": "x"}},
            {"index": 3, "image": "s3.png", "value": {"action": "Missing code entirely.", "observation": "x"}},
        ],
    },
]

METADATA_ROWS = [
    {"task_id": "task-1", "system": "Ubuntu", "step_num": 6, "action_frequency": {"click": 1, "write": 1, "press": 1, "terminate": 1}},
    {"task_id": "task-2", "system": "Ubuntu", "step_num": 4, "action_frequency": {"rightClick": 1}},
]


def _write_jsonl(tmp_path, name, rows) -> str:
    path = tmp_path / name
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return str(path)


# ---- loading ----------------------------------------------------------------


def test_load_tasks_from_local_fixture(tmp_path) -> None:
    fixture = _write_jsonl(tmp_path, "tasks.jsonl", TASK_ROWS)

    tasks = load_tasks(limit=None, dataset_name="json", data_files=fixture)

    assert [t.task_id for t in tasks] == ["task-1", "task-2"]
    assert tasks[0].instruction == "Open GIMP and load a picture."
    assert tasks[0].task_completed is True
    assert len(tasks[0].steps) == 6


def test_load_tasks_respects_limit(tmp_path) -> None:
    fixture = _write_jsonl(tmp_path, "tasks.jsonl", TASK_ROWS)

    tasks = load_tasks(limit=1, dataset_name="json", data_files=fixture)

    assert len(tasks) == 1
    assert tasks[0].task_id == "task-1"


def test_load_tasks_unknown_source_raises() -> None:
    try:
        load_tasks(source="not-a-real-os")
    except ValueError as exc:
        assert "not-a-real-os" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_load_metadata_from_local_fixture(tmp_path) -> None:
    fixture = _write_jsonl(tmp_path, "meta.jsonl", METADATA_ROWS)

    rows = load_metadata(limit=None, dataset_name="json", data_files=fixture)

    assert [r["task_id"] for r in rows] == ["task-1", "task-2"]
    assert rows[0]["action_frequency"]["click"] == 1


# ---- action normalization ----------------------------------------------------


def test_parse_click() -> None:
    action = parse_code("pyautogui.click(x=0.377, y=0.193)", "Click the button")

    assert action.action == "click"
    assert action.click_type == "single"
    assert action.coordinate == {"x": 0.377, "y": 0.193}
    assert action.target == {"description": "Click the button"}


def test_parse_double_and_right_click() -> None:
    assert parse_code("pyautogui.doubleClick(x=0.1, y=0.2)", None).click_type == "double"
    assert parse_code("pyautogui.rightClick(x=0.1, y=0.2)", None).click_type == "right"


def test_parse_write() -> None:
    action = parse_code("pyautogui.write(message='hello')", "Type hello")
    assert action.action == "type"
    assert action.text == "hello"


def test_parse_press() -> None:
    action = parse_code("pyautogui.press('enter')", None)
    assert action.action == "keypress"
    assert action.keys == ["enter"]


def test_parse_hotkey() -> None:
    action = parse_code("pyautogui.hotkey(['ctrl', 'o'])", None)
    assert action.action == "hotkey"
    assert action.keys == ["ctrl", "o"]


def test_parse_move_then_drag_becomes_one_drag_action() -> None:
    code = "pyautogui.moveTo(x=0.364, y=0.42)\npyautogui.dragTo(x=0.508, y=0.425, button='left')"
    action = parse_code(code, "Drag it")

    assert action.action == "drag"
    assert action.coordinate == {"from": {"x": 0.364, "y": 0.42}, "to": {"x": 0.508, "y": 0.425}}


def test_parse_scroll_and_wait_and_terminate() -> None:
    assert parse_code("pyautogui.scroll(-5)", None).action == "scroll"
    assert parse_code("computer.wait()", None).action == "wait"

    finished = parse_code("computer.terminate(status='success')", None)
    assert finished.action == "finish"
    assert finished.success is True

    failed = parse_code("computer.terminate(status='failure')", None)
    assert failed.success is False


# ---- malformed / unsupported actions -----------------------------------------


def test_parse_missing_code_is_unsupported() -> None:
    action = parse_code(None, "Missing code entirely.")
    assert action.action == "unsupported"
    assert action.reason == "missing code"
    assert action.target == {"description": "Missing code entirely."}


def test_parse_malformed_code_is_unsupported() -> None:
    action = parse_code("not_a_real_call(", "Malformed.")
    assert action.action == "unsupported"
    assert "unparseable code" in action.reason


def test_parse_unknown_function_is_unsupported() -> None:
    action = parse_code("some.unknown_call(x=1)", "Unknown function.")
    assert action.action == "unsupported"
    assert action.reason == "unsupported function: unknown_call"


def test_normalize_task_covers_every_step_without_raising(tmp_path) -> None:
    fixture = _write_jsonl(tmp_path, "tasks.jsonl", TASK_ROWS)
    tasks = load_tasks(limit=None, dataset_name="json", data_files=fixture)

    steps = normalize_task(tasks[1])  # the task full of malformed/unsupported actions

    assert len(steps) == 4
    assert [s.action.action for s in steps] == ["click", "unsupported", "unsupported", "unsupported"]


# ---- evaluation statistics ----------------------------------------------------


def test_compute_stats(tmp_path) -> None:
    fixture = _write_jsonl(tmp_path, "tasks.jsonl", TASK_ROWS)
    tasks = load_tasks(limit=None, dataset_name="json", data_files=fixture)
    normalized = normalize_tasks(tasks)

    stats = compute_stats(tasks, normalized)

    assert stats.num_tasks == 2
    assert stats.num_steps == 10
    assert stats.completed_tasks == 1
    assert stats.completion_rate == 0.5
    assert stats.unsupported_count == 3
    assert stats.action_counts["click"] == 2  # task-1's click + task-2's rightClick
    assert stats.to_dict()["num_tasks"] == 2


def test_run_evaluation_end_to_end(tmp_path, monkeypatch) -> None:
    fixture = _write_jsonl(tmp_path, "tasks.jsonl", TASK_ROWS)
    monkeypatch.setattr("evaluation.agentnet.pipeline.load_tasks", lambda limit, source: load_tasks(limit=limit, dataset_name="json", data_files=fixture))

    report = run_evaluation(limit=None, source="ubuntu")

    assert report.stats.num_tasks == 2
    assert "task-1" in report.normalized


def test_agent_net_task_from_raw_tolerates_missing_traj() -> None:
    task = AgentNetTask.from_raw({"task_id": "x", "instruction": "hi"})
    assert task.steps == []
    assert task.task_completed is None
