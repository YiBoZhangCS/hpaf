"""Create and cryptographically freeze the VH-40 formal protocol."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase9 import runner


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
OFFICIAL_PATH = PROJECT_ROOT / "experiments/progprompt_vh/phase7/data/combined_manifest.json"
LONG_PATH = ROOT / "data/long11_manifest.json"
MANIFEST_PATH = ROOT / "data/vh40_manifest.json"
PROTOCOL_PATH = ROOT / "VH40_PROTOCOL.md"
LOCK_PATH = ROOT / "data/VH40_PROTOCOL_LOCK.json"
TOKEN_LOCK_PATH = ROOT / "data/TOKEN_FINAL_LOCK.json"
ACTION_PATH = PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"


def _bundle_hash(paths: Iterable[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite frozen artifact: {path}")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def freeze() -> Dict[str, Any]:
    if any(path.exists() for path in [MANIFEST_PATH, PROTOCOL_PATH, LOCK_PATH]):
        raise RuntimeError("VH-40 protocol is already frozen")
    token_lock = json.loads(TOKEN_LOCK_PATH.read_text(encoding="utf-8"))
    if token_lock.get("adopted_prompt_variant") != "phase8_uncompressed":
        raise RuntimeError("Unexpected token decision")
    official_payload = json.loads(OFFICIAL_PATH.read_text(encoding="utf-8"))
    long_payload = json.loads(LONG_PATH.read_text(encoding="utf-8"))
    official = []
    for source in official_payload["entries"]:
        item = dict(source)
        item.update({
            "source": item.get("source_annotation"),
            "official_or_extension": "official_source",
            "reference_horizon": int(item["gt_action_length"]),
            "task_structure": "released_program_horizon",
            "synthetic": False,
        })
        official.append(item)
    extension = [dict(item) for item in long_payload["entries"]]
    entries = [*official, *extension]
    horizons = Counter(item["horizon"] for item in entries)
    provenance = Counter(item["official_or_extension"] for item in entries)
    if len(entries) != 40 or len({item["task_id"] for item in entries}) != 40:
        raise RuntimeError("VH-40 task count/IDs invalid")
    if horizons != Counter({"Medium": 16, "Long": 15, "Short": 9}):
        raise RuntimeError(f"VH-40 horizon count invalid: {horizons}")
    if provenance != Counter({"official_source": 29, "synthetic_long_horizon_extension": 11}):
        raise RuntimeError(f"VH-40 provenance invalid: {provenance}")
    if len({item["task_text"].strip().lower() for item in entries}) != 35:
        raise RuntimeError("VH-40 unique instruction count must be 35")

    manifest = {
        "schema_version": 1,
        "name": "VirtualHome 40-Task Evaluation Suite",
        "short_name": "VH-40",
        "classification": "29 OFFICIAL-SOURCE HELD-OUT INSTANCES + 11 PRE-FROZEN SYNTHETIC LONG-HORIZON EXTENSIONS",
        "official_40_task_benchmark": False,
        "seed": 20260826,
        "task_count": 40,
        "unique_task_text_count": 35,
        "official_source_count": 29,
        "long_extension_count": 11,
        "horizon_counts": {key: horizons[key] for key in ["Short", "Medium", "Long"]},
        "method_output_used_for_selection": False,
        "formal_order": "task-major, method-minor: ProgPrompt-Compat, HPAF-Flat, HPAF-Full",
        "entries": entries,
    }
    _write_exclusive(MANIFEST_PATH, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    protocol = """# VH-40 Formal Protocol

## Dataset

VH-40 is the VirtualHome 40-Task Evaluation Suite, not an official 40-task
benchmark. It contains 29 official-source held-out task-scene instances retained
because they admit method-independent scoring, plus 11 synthetic causal
long-horizon extensions built on official VirtualHome scenes. The 29 instances
are a regression subset because they were previously observed during development;
the pre-frozen Long-11 is the only new holdout in Phase 9.

Long-11 was generated with seed `20260826`, deterministic natural-language and
causal templates, fixed 4/4/3 scene and 3/3/3/2 category allocations, first-valid
reference selection, and no method output. Every reference has 11-25 actions,
at least three causal stages, a majority of predecessor-dependent stages, complete
reference execution, and evaluator success. Exact instruction overlap against
train, test_seen, the existing 29, and Phase-8 synthetic 30 is zero.

## Methods

The fixed order is `ProgPrompt-Compat`, `HPAF-Flat`, `HPAF-Full`. ProgPrompt uses
the released three few-shots, whole-program generation, assertions with the frozen
ARK strict binary enum compatibility transport, and adjacent-else recovery. Flat
and Full use identical Phase-8 uncompressed process/alignment/precondition rules.
Full alone has TaskAgent decomposition, current-state atomic generation, online
atomic verification, and one local Retry-1. The Phase-9 compression gate rejected
both bounded candidates; no Long-11 task was exposed during tuning.

## Execution

Run exactly 40 x 3 x 1 = 120 unique task-method pairs, task-major then method-minor,
with ARK `doubao-seed-2-1-pro-260628`, Responses API, temperature 0, and thinking
disabled. SDK transport retries are infrastructure retries; HPAF Retry-1 is the
only planning retry. Completed records are never rerun. After formal start there
is no task removal, resampling, prompt/evaluator/config change, or failed-pair rerun.

## Evaluation

Persistent-state, frozen generic trace, and frozen generic ordered-event-plus-state
evaluators are selected by manifest metadata and shared by all methods. Online
verifiers do not determine final success. Primary metrics are Task SR, Macro Exec,
calls/task, and tokens/task. Report overall 40, official-source regression 29,
new Long-11, existing official Long-4, and combined Long-15 separately.
"""
    _write_exclusive(PROTOCOL_PATH, protocol)

    lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "formal_execution_started": False,
        "records_required": 120,
        "seed": 20260826,
        "manifest_sha256": sha256(MANIFEST_PATH),
        "protocol_sha256": sha256(PROTOCOL_PATH),
        "long11_manifest_sha256": sha256(LONG_PATH),
        "long11_reference_states_sha256": sha256(ROOT / "data/long11_reference_final_states.jsonl"),
        "token_final_lock_sha256": sha256(TOKEN_LOCK_PATH),
        "config_sha256": sha256(runner.CONFIG_PATH),
        "method_bundle_sha256": _bundle_hash(runner.METHOD_IMPLEMENTATION_FILES),
        "evaluator_bundle_sha256": _bundle_hash(runner.EVALUATOR_FILES),
        "action_set_sha256": sha256(ACTION_PATH),
        "method_order": runner.METHODS,
        "execution_order": "task-major, method-minor",
        "representation": "uncompressed",
    }
    _write_exclusive(LOCK_PATH, json.dumps(lock, ensure_ascii=False, indent=2) + "\n")
    return lock


if __name__ == "__main__":
    print(json.dumps(freeze(), ensure_ascii=False, indent=2))

