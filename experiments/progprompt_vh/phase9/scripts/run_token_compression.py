"""Run at most two Phase-9 compression candidates on the 29-task development set."""

from __future__ import annotations

import functools
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import read_jsonl, sha256
from experiments.progprompt_vh.phase8 import runner
from experiments.progprompt_vh.phase9.methods import semantic_compact
from experiments.progprompt_vh.phase9.verification import semantic_compact_verifier


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase9"
RESULTS = ROOT / "results/development_compression"
LOCK_PATH = ROOT / "data/TOKEN_FINAL_LOCK.json"
DECISION_PATH = ROOT / "TOKEN_FINAL_DECISION.md"
BASELINE_PATH = (
    PROJECT_ROOT / "experiments/progprompt_vh/phase8/results/development/full_uncompressed/raw_runs.jsonl"
)
CANDIDATE_FILES = [
    ROOT / "methods/semantic_compact.py",
    ROOT / "verification/semantic_compact_verifier.py",
    ROOT / "scripts/run_token_compression.py",
]


def _bundle_hash(paths: Sequence[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _metrics(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(rows)
    return {
        "n": len(rows),
        "success": sum(int(row["final_semantic_SR"]) for row in rows),
        "macro_exec": mean(float(row["Exec"]) for row in rows),
        "avg_tokens": mean(float(row["total_tokens"]) for row in rows),
        "avg_calls": mean(float(row["total_calls"]) for row in rows),
    }


def _install_candidate(compact_schema: bool) -> None:
    runner.generate_atomic_tasks = semantic_compact.generate_atomic_tasks
    runner.generate_atomic_program = semantic_compact.generate_atomic_program
    runner.generate_repair_program = semantic_compact.generate_repair_program
    runner.verify_task_completion = functools.partial(
        semantic_compact_verifier.verify_task_completion,
        compact_schema=compact_schema,
    )


def _evaluate_candidate(
    name: str, rows: List[Dict[str, Any]], baseline_rows: List[Dict[str, Any]],
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    baseline = _metrics(baseline_rows)
    current = _metrics(rows)
    persistent_ids = {
        item["task_id"] for item in entries if item["evaluator_type"] == "persistent_state"
    }
    baseline_success = {
        row["task_id"] for row in baseline_rows
        if row["task_id"] in persistent_ids and row["final_semantic_SR"]
    }
    current_success = {row["task_id"] for row in rows if row["final_semantic_SR"]}
    persistent_regressions = sorted(baseline_success - current_success)
    token_reduction = 1.0 - current["avg_tokens"] / baseline["avg_tokens"]
    gate = {
        "success_at_least_27_of_29": current["success"] >= 27,
        "previously_successful_persistent_regressions_at_most_1": len(persistent_regressions) <= 1,
        "macro_exec_at_least_0_945": current["macro_exec"] >= 0.945,
        "token_reduction_at_least_8_percent": token_reduction >= 0.08,
    }
    return {
        "candidate": name,
        "metrics": current,
        "token_reduction_fraction": token_reduction,
        "persistent_regressions": persistent_regressions,
        "gate": gate,
        "pass": all(gate.values()),
    }


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite frozen compression artifact: {path}")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def run() -> Dict[str, Any]:
    if LOCK_PATH.exists() or DECISION_PATH.exists():
        raise RuntimeError("Phase-9 token decision is already frozen")
    entries = runner.load_development_entries()
    if len(entries) != 29:
        raise RuntimeError("Compression gate may only see the 29 development tasks")
    baseline_rows = read_jsonl(BASELINE_PATH)
    if len(baseline_rows) != 29:
        raise RuntimeError("Frozen Phase-8 Full baseline must have 29 records")

    candidates = []
    _install_candidate(compact_schema=False)
    rows_a = runner.run_matrix(
        entries=entries, methods=["HPAF-Full"], output_root=RESULTS / "candidate_a",
        phase="phase9_compression_candidate_a", representation="uncompressed",
    )
    candidates.append(_evaluate_candidate("boilerplate", rows_a, baseline_rows, entries))

    if not candidates[-1]["pass"]:
        _install_candidate(compact_schema=True)
        rows_b = runner.run_matrix(
            entries=entries, methods=["HPAF-Full"], output_root=RESULTS / "candidate_b",
            phase="phase9_compression_candidate_b", representation="uncompressed",
        )
        candidates.append(_evaluate_candidate("boilerplate_plus_compact_schema", rows_b, baseline_rows, entries))

    passing = [item for item in candidates if item["pass"]]
    adopted = passing[0]["candidate"] if passing else "phase8_uncompressed"
    baseline = _metrics(baseline_rows)
    lock = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "development_only": True,
        "long11_exposed_to_tuning": False,
        "maximum_candidates": 2,
        "candidates_run": len(candidates),
        "development_manifest_sha256": sha256(runner.DEVELOPMENT_MANIFEST),
        "baseline_source_sha256": sha256(BASELINE_PATH),
        "candidate_bundle_sha256": _bundle_hash(CANDIDATE_FILES),
        "baseline_metrics": baseline,
        "candidates": candidates,
        "adopted_prompt_variant": adopted,
        "adopted": adopted != "phase8_uncompressed",
    }
    _write_exclusive(LOCK_PATH, json.dumps(lock, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# Token Final Decision", "",
        "The gate used only the frozen 29-task development set. Long-11 was never loaded.", "",
        f"- Baseline: {baseline['success']}/29, Macro Exec {baseline['macro_exec']:.3f}, {baseline['avg_tokens']:.1f} tokens/task.",
    ]
    for item in candidates:
        metric = item["metrics"]
        lines.append(
            f"- {item['candidate']}: {metric['success']}/29, Macro Exec {metric['macro_exec']:.3f}, "
            f"{metric['avg_tokens']:.1f} tokens/task ({100*item['token_reduction_fraction']:.1f}% reduction), "
            f"gate {'PASS' if item['pass'] else 'FAIL'}."
        )
    lines += ["", f"Decision: **{'ADOPTED' if lock['adopted'] else 'REJECTED'}** (`{adopted}`).", ""]
    _write_exclusive(DECISION_PATH, "\n".join(lines))
    return lock


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
