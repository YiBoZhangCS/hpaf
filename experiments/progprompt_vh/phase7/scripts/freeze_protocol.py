#!/usr/bin/env python3
"""Freeze Phase-7 prompts, manifests, evaluator, and implementation inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase7.dataset import PHASE7_ROOT, build_manifests, sha256, write_expansion_audit
from experiments.progprompt_vh.phase7.methods.common import PROGRAM_AGENT_RULES
from experiments.progprompt_vh.phase7.runner import implementation_sha256


FORBIDDEN_PROMPT_MARKERS = [
    "microwave_chicken", "chicken", "garbagecan", "fridge", "test_unseen::",
    "env1::", "env2::", "STATE(", "RELATION(", "final_semantic_SR",
]


def main() -> None:
    data = build_manifests()
    write_expansion_audit(data)
    lowered = PROGRAM_AGENT_RULES.lower()
    hits = [marker for marker in FORBIDDEN_PROMPT_MARKERS if marker.lower() in lowered]
    if hits:
        raise RuntimeError(f"Task-specific/evaluator marker in frozen prompt: {hits}")

    prompt_sources = [
        PHASE7_ROOT / "methods/common.py",
        PHASE7_ROOT / "methods/hpaf_flat.py",
        PHASE7_ROOT / "methods/hpaf_full.py",
        PHASE7_ROOT / "execution.py",
    ]
    prompt_lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "prompt_freeze_before_smoke_and_formal": True,
        "program_agent_rules_sha256": hashlib.sha256(PROGRAM_AGENT_RULES.encode()).hexdigest(),
        "source_sha256": {str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in prompt_sources},
        "forbidden_markers": FORBIDDEN_PROMPT_MARKERS,
        "forbidden_hits": hits,
        "flat_and_full_share_exact_rules": True,
    }
    prompt_path = PHASE7_ROOT / "data/prompt_lock.json"
    prompt_path.write_text(json.dumps(prompt_lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_hashes = {
        name: sha256(PHASE7_ROOT / "data" / f"{name}_manifest.json")
        for name in ["regression", "confirmatory", "combined"]
    }
    lock = {
        "schema_version": 1,
        "frozen_at": prompt_lock["frozen_at"],
        "prompt_lock_sha256": sha256(prompt_path),
        "manifest_sha256": manifest_hashes,
        "dataset_stats_sha256": sha256(PHASE7_ROOT / "data/dataset_stats.json"),
        "trace_evaluator_sha256": sha256(PHASE7_ROOT / "verification/trace_evaluator.py"),
        "action_set_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase5/data/graph_supported_actions.json"),
        "config_sha256": sha256(PHASE7_ROOT / "configs/benchmark.yaml"),
        "implementation_sha256": implementation_sha256(),
        "phase6_manifest_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase6/data/task_manifest.json"),
        "phase6_semantic_goals_sha256": sha256(PROJECT_ROOT / "experiments/progprompt_vh/phase6/data/semantic_goals.json"),
        "set_sizes": {name: len(data[name]) for name in ["regression", "confirmatory", "combined"]},
        "synthetic_tasks": 0,
    }
    lock_path = PHASE7_ROOT / "data/protocol_lock.json"
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(lock, indent=2))


if __name__ == "__main__":
    main()
