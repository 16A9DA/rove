from __future__ import annotations

from typing import Iterable

from datasets import load_dataset

from .schema import AgentNetTask

DATASET_NAME = "xlangai/AgentNet"

# The two trajectory files split by OS; each row is one full task (instruction + traj).
TRAJECTORY_FILES = {"ubuntu": "agentnet_ubuntu_5k.jsonl", "win_mac": "agentnet_win_mac_18k.jsonl"}

# Per-task summary (system, applications, step_num, action_frequency, ...) with no
# trajectory/screenshot payload — orders of magnitude lighter than a trajectory file,
# so this is the right file to pull a large sample of for filtering/stats.
METADATA_FILE = "meta_data_merged.jsonl"


def _stream(dataset_name: str, data_files: str) -> Iterable[dict]:
    return iter(load_dataset(dataset_name, data_files=data_files, split="train", streaming=True))


def load_metadata(limit: int | None = 20, dataset_name: str = DATASET_NAME, data_files: str = METADATA_FILE) -> list[dict]:
    rows = _stream(dataset_name, data_files)
    return list(rows) if limit is None else [row for _, row in zip(range(limit), rows)]


def load_tasks(
    limit: int | None = 5,
    source: str = "ubuntu",
    dataset_name: str = DATASET_NAME,
    data_files: str | None = None,
) -> list[AgentNetTask]:
    # dataset_name="json" + a local data_files path loads a fixture instead of the Hub (tests)
    files = data_files or TRAJECTORY_FILES.get(source)
    if files is None:
        raise ValueError(f"unknown AgentNet source {source!r}, expected one of {sorted(TRAJECTORY_FILES)}")
    rows = _stream(dataset_name, files)
    raw_rows = rows if limit is None else (row for _, row in zip(range(limit), rows))
    return [AgentNetTask.from_raw(row) for row in raw_rows]
