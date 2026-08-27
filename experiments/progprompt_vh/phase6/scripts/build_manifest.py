#!/usr/bin/env python3
"""Freeze the Phase-6 task set, semantic evaluator goals, and horizon subset."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import (
    ACTION_PATH,
    PHASE6_ROOT,
    SCENE0_INITIAL,
    build_manifest_entries,
    final_state_path,
    initial_state_path,
    sha256,
    taskset_statistics,
)


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    data_dir = PHASE6_ROOT / "data"
    manifest_path = data_dir / "task_manifest.json"
    semantic_path = data_dir / "semantic_goals.json"
    long_path = data_dir / "long_horizon_manifest.json"
    lock_path = data_dir / "protocol_lock.json"
    protected = [manifest_path, semantic_path, long_path, lock_path]
    if any(path.exists() for path in protected):
        raise FileExistsError("Refusing to overwrite an existing Phase-6 frozen artifact")

    frozen_at = datetime.now(timezone.utc).isoformat()
    entries = build_manifest_entries()
    selected = [item for item in entries if item["filter_status"] == "included"]
    manifest = {
        "schema_version": 1,
        "frozen_at": frozen_at,
        "selection_policy": [
            "official held-out task or held-out environment split",
            "ground-truth program and final-state metadata present",
            "natural-language completion reliably expressible under the shared 17-action/persistent-state ontology",
            "no direct overlap with the three released default prompt examples",
            "no filtering based on any Phase-6 method output",
        ],
        "entries": entries,
    }
    semantic = {
        "schema_version": 1,
        "frozen_at": frozen_at,
        "visibility": "final deterministic evaluator only; never supplied to TaskAgent, ProgramAgent, or online LLM verifier",
        "aggregation": "conditions within a task are conjunctive; COUNT_RELATION is one deterministic condition",
        "tasks": [
            {
                "task_id": item["task_id"],
                "task_text": item["task_text"],
                "official_split": item["official_split"],
                **item["semantic_goal"],
            }
            for item in selected
        ],
    }
    long_manifest = {
        "schema_version": 1,
        "frozen_at": frozen_at,
        "definition": "Long iff official GT action length >= 11; Short <= 5; Medium 6-10",
        "task_ids": [item["task_id"] for item in selected if item["is_long_horizon"]],
    }
    write_json(manifest_path, manifest)
    write_json(semantic_path, semantic)
    write_json(long_path, long_manifest)

    source_paths = [
        SCENE0_INITIAL,
        initial_state_path("env1"),
        initial_state_path("env2"),
        final_state_path("test_seen"),
        final_state_path("test_unseen"),
        final_state_path("test_unseen_ambiguous_goals"),
        final_state_path("env1"),
        final_state_path("env2"),
    ]
    source_hashes = {str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in source_paths}
    source_digest = hashlib.sha256(
        json.dumps(source_hashes, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    lock = {
        "task_manifest_sha256": sha256(manifest_path),
        "semantic_goals_sha256": sha256(semantic_path),
        "long_horizon_manifest_sha256": sha256(long_path),
        "action_set_sha256": sha256(ACTION_PATH),
        "dataset_sources_sha256": source_digest,
        "dataset_source_files": source_hashes,
        "phase5_raw_runs_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase5/results/raw_runs.jsonl"),
    }
    write_json(lock_path, lock)

    stats = taskset_statistics(entries)
    protocol = f"""# Phase-6 Resume-Oriented Final Benchmark Protocol

## Frozen benchmark

| Item | Value |
|---|---|
| Provider/model | ARK / `doubao-seed-2-1-pro-260628` |
| API/settings | Responses API; temperature 0; thinking disabled; max output 600 |
| Methods | ProgPrompt, HPAF-Flat, HPAF-Full |
| Final task set | {stats['n']} valid official held-out task-scene instances |
| Horizons | Short <=5; Medium 6-10; Long >=11 GT actions |
| Horizon counts | Short {stats['horizons']['Short']}; Medium {stats['horizons']['Medium']}; Long {stats['horizons']['Long']} |
| Shared actions | Frozen Phase-5 17-action graph-compatible intersection |
| Execution | Per-task official/cached initial graph; Unity scene reset and class-inventory sanity; pinned Evolving Graph per-action execution |
| Online control | Method-specific LLM verification; never sees deterministic evaluator conditions |
| Final primary score | Shared deterministic frozen semantic evaluator |
| Supplementary score | Unmodified released/Phase-5 Official SR/GCR and Exec |
| Repetitions | One formal run per task-method pair |

## Frozen hashes

| Artifact | SHA-256 |
|---|---|
| `data/task_manifest.json` | `{lock['task_manifest_sha256']}` |
| `data/semantic_goals.json` | `{lock['semantic_goals_sha256']}` |
| `data/long_horizon_manifest.json` | `{lock['long_horizon_manifest_sha256']}` |
| Phase-5 shared action set | `{lock['action_set_sha256']}` |
| Audited source-data bundle | `{lock['dataset_sources_sha256']}` |
| Immutable Phase-5 formal raw runs | `{lock['phase5_raw_runs_sha256']}` |

The manifest, semantic goals, long threshold, prompt examples, and action set are frozen before any Phase-6 method execution. Formal execution is additionally locked to the implementation hash recorded by the passing smoke marker.

## Dataset selection

The official release contains 35 held-out candidates across test_unseen, the ambiguous-goal split, env1, and env2. Tasks are excluded only when a stable method-independent semantic endpoint cannot be expressed by the shared interface/ontology. test_seen is excluded before candidacy because all ten task texts occur in train. Full decisions and reasons are stored in `DATASET_AUDIT.md` and `data/task_manifest.json`.

## Verification separation

ProgPrompt retains released assertion-level LLM state checks and recovery. HPAF-Flat calls the shared LLM verifier once after its whole-task program and does not retry. HPAF-Full pays for a fresh TaskAgent call, generates and executes each object-centric atomic against current state, calls the shared LLM verifier on post-execution symbolic observation, and permits one local repair plus one post-repair verification when `done=false`.

The online verifier receives only the current instruction, post-execution symbolic observation, relevant/available objects, and execution trace/error context. It never receives GT final states, official goal sets, frozen semantic conditions, or future atomics. Final benchmark success is recomputed independently from the frozen semantic goal file.

## Abstraction statement

VirtualHome substitutes simulator symbolic observation for real RGB-D perception while preserving HPAF's perception/grounding, alignment/precondition, interaction, and LLM verification organization. This benchmark does not claim to evaluate real visual perception.
"""
    (PHASE6_ROOT / "PROTOCOL.md").write_text(protocol, encoding="utf-8")
    print(json.dumps({"statistics": stats, "lock": lock}, indent=2))


if __name__ == "__main__":
    main()

