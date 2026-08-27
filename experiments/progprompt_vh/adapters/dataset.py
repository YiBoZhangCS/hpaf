from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .paths import PROGPROMPT_ROOT


# The final-state JSONL files do not contain task identifiers. The official
# runner positionally zips them with tasks collected through unsorted
# os.listdir(). These explicit orders reproduce the release checkout's intended
# pairing and, for test_unseen, exactly match paper Table II.
TASK_ORDERS = {
    "test_unseen": [
        "watch tv",
        "turn off light",
        "brush teeth",
        "throw away apple",
        "make toast",
        "eat chips on the sofa",
        "put salmon in the fridge",
        "wash the plate",
        "bring coffeepot and cupcake to the coffee table",
        "microwave salmon",
    ],
    "test_seen": [
        "wash the rug in washing machine",
        "put all the cutlery in the sink",
        "throw away the lime",
        "put the wine glass in the kitchen cabinet",
        "put the candle on the living room shelf",
        "listen to radio",
        "bring pillow to the sofa",
        "open window",
        "cut apple",
        "wash mug",
    ],
}


@dataclass(frozen=True)
class TaskRecord:
    task: str
    source_file: str
    subgoals: Dict[str, List[str]]
    ground_truth_actions: List[str]
    final_state: Dict[str, Any]
    final_state_index: int

    @property
    def ground_truth_action_length(self) -> int:
        return len(self.ground_truth_actions)

    @property
    def difficulty_bucket(self) -> str:
        length = self.ground_truth_action_length
        if 0 <= length <= 5:
            return "Short"
        if 6 <= length <= 10:
            return "Medium"
        if 11 <= length <= 18:
            return "Long"
        return "OutOfRange"


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def load_task_records(test_set: str = "test_unseen") -> List[TaskRecord]:
    task_rows: Dict[str, tuple[str, Dict[str, List[str]], List[str]]] = {}
    split_dir = PROGPROMPT_ROOT / "data" / test_set
    for path in sorted(split_dir.glob("*.json")):
        for row in _read_jsonl(path):
            if len(row) != 1:
                raise ValueError(f"Expected one task per JSONL row in {path}")
            task, subgoals = next(iter(row.items()))
            actions = [action for group in subgoals.values() for action in group]
            task_rows[task] = (path.name, subgoals, actions)

    final_state_path = (
        PROGPROMPT_ROOT / "data" / "final_states" / f"final_states_{test_set}.json"
    )
    final_states = list(_read_jsonl(final_state_path))
    task_order = TASK_ORDERS.get(test_set)
    if task_order is None:
        raise ValueError(f"No audited positional final-state mapping for {test_set}")
    if len(task_rows) != len(final_states) or set(task_rows) != set(task_order):
        raise ValueError(
            f"Task/final-state/order mismatch for {test_set}: "
            f"tasks={len(task_rows)}, final_states={len(final_states)}"
        )

    return [
        TaskRecord(
            task=task,
            source_file=task_rows[task][0],
            subgoals=subgoals,
            ground_truth_actions=actions,
            final_state=final_states[index],
            final_state_index=index,
        )
        for index, task in enumerate(task_order)
        for _, subgoals, actions in [task_rows[task]]
    ]
