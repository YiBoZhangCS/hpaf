"""VH-40 orchestration using the frozen Phase-8 methods and Phase-9 evaluator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    evaluate_conditions,
)
from experiments.progprompt_vh.phase7.verification.trace_evaluator import (
    evaluate_trace_goal,
)
from experiments.progprompt_vh.phase8 import runner as phase8_runner
from experiments.progprompt_vh.phase9.verification.causal_evaluator import (
    evaluate_causal_goal,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
CONFIG_PATH = ROOT / "configs/benchmark.yaml"
MANIFEST_PATH = ROOT / "data/vh40_manifest.json"
TOKEN_LOCK_PATH = ROOT / "data/TOKEN_FINAL_LOCK.json"
METHODS = list(phase8_runner.METHODS)

METHOD_IMPLEMENTATION_FILES = [
    ROOT / "runner.py",
    ROOT / "scripts/run_formal.py",
    CONFIG_PATH,
    TOKEN_LOCK_PATH,
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/llm_client.py",
    PROJECT_ROOT / "experiments/progprompt_vh/adapters/virtualhome.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/compat_client.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/execution.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/representation.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/runner.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/common.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/hpaf_flat.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/methods/hpaf_full.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/verification/llm_verifier.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/progprompt.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/methods/common.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase5/execution.py",
]
EVALUATOR_FILES = [
    PROJECT_ROOT / "experiments/progprompt_vh/phase6/verification/deterministic_evaluator.py",
    PROJECT_ROOT / "experiments/progprompt_vh/phase7/verification/trace_evaluator.py",
    ROOT / "verification/causal_evaluator.py",
]


def load_entries() -> List[Dict[str, Any]]:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]
    if len(entries) != 40 or len({item["task_id"] for item in entries}) != 40:
        raise RuntimeError("VH-40 manifest must contain 40 unique task-scene instances")
    horizons = {name: sum(item["horizon"] == name for item in entries) for name in ["Short", "Medium", "Long"]}
    if horizons != {"Short": 9, "Medium": 16, "Long": 15}:
        raise RuntimeError(f"VH-40 horizon allocation mismatch: {horizons}")
    return entries


def _score(
    final_state: Dict[str, Any], artifacts: Dict[str, Any],
    entry: Dict[str, Any], initial_graph: Dict[str, Any],
) -> Dict[str, Any]:
    evaluator_type = entry.get("evaluator_type")
    record_view = {"graph_execution_trace": artifacts["graph_execution_trace"]}
    if evaluator_type == "generic_causal_trace_state":
        return evaluate_causal_goal(record_view, entry["causal_goal"], final_state)
    if evaluator_type == "generic_trace":
        return evaluate_trace_goal(record_view, entry["trace_goal"], initial_graph)
    if evaluator_type == "persistent_state":
        return evaluate_conditions(final_state, entry["semantic_goal"]["conditions"])
    raise ValueError(f"Unsupported VH-40 evaluator type: {evaluator_type}")


def configure_frozen_runtime() -> None:
    token_lock = json.loads(TOKEN_LOCK_PATH.read_text(encoding="utf-8"))
    if token_lock.get("adopted_prompt_variant") != "phase8_uncompressed":
        raise RuntimeError("Phase-9 formal runtime only supports the frozen rejected-compression decision")
    phase8_runner.CONFIG_PATH = CONFIG_PATH
    phase8_runner.FINAL_MANIFEST = MANIFEST_PATH
    phase8_runner.IMPLEMENTATION_FILES = [*METHOD_IMPLEMENTATION_FILES, *EVALUATOR_FILES]
    phase8_runner._score = _score


def run_matrix(
    *, entries: Sequence[Dict[str, Any]], output_root: Path, phase: str,
) -> List[Dict[str, Any]]:
    configure_frozen_runtime()
    return phase8_runner.run_matrix(
        entries=entries,
        methods=METHODS,
        output_root=output_root,
        phase=phase,
        representation="uncompressed",
    )
