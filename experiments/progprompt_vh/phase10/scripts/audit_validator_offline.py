"""Revalidate saved Phase-9 TaskAgent outputs without making LLM calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.adapters.virtualhome import available_object_classes
from experiments.progprompt_vh.phase6.dataset import load_initial_graph, read_jsonl
from experiments.progprompt_vh.phase10.ir import (
    old_phase9_validation,
    parse_ir_json,
    project_phase9_payload,
    validate_ir,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10"
RAW = PROJECT_ROOT / "experiments/progprompt_vh/phase9/results/formal/raw_runs.jsonl"
MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/vh40_manifest.json"
REPORT = ROOT / "VALIDATOR_OFFLINE_AUDIT.md"
DETAIL = ROOT / "results/validator_offline_audit.json"


def build() -> Dict[str, Any]:
    entries = {
        item["task_id"]: item
        for item in json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    }
    full_rows = [item for item in read_jsonl(RAW) if item["method"] == "HPAF-Full"]
    if len(full_rows) != 40:
        raise RuntimeError(f"Expected 40 saved HPAF-Full records, found {len(full_rows)}")
    results: List[Dict[str, Any]] = []
    for row in full_rows:
        raw_output = row.get("taskagent_raw_output")
        payload, parse_error = parse_ir_json(raw_output or "")
        inventory = available_object_classes(load_initial_graph(entries[row["task_id"]]))
        if parse_error or payload is None:
            old = None
            new = None
        else:
            old = old_phase9_validation(payload, inventory)
            projection = project_phase9_payload(payload)
            new = validate_ir(projection, inventory)
        results.append(
            {
                "task_id": row["task_id"],
                "task": row["task"],
                "phase9_error_type": row.get("error_type", ""),
                "parse_error": parse_error,
                "old": old.to_dict() if old else None,
                "new": new.to_dict() if new else None,
                "legacy_projection": project_phase9_payload(payload) if payload else None,
                "raw_output": raw_output,
            }
        )
    old_rejected = sum(item["old"] is None or not item["old"]["valid"] for item in results)
    new_rejected = sum(item["new"] is None or not item["new"]["valid"] for item in results)
    fixed = [
        item for item in results
        if item["old"] is not None
        and not item["old"]["valid"]
        and item["new"] is not None
        and item["new"]["valid"]
    ]
    return {
        "source": str(RAW.relative_to(PROJECT_ROOT)),
        "llm_calls": 0,
        "saved_outputs": len(results),
        "old_validator_rejected": old_rejected,
        "new_validator_rejected": new_rejected,
        "old_false_rejection_fixed": len(fixed),
        "schema_invalid": sum(
            item["new"] is None or item["new"]["schema_invalid"] for item in results
        ),
        "semantic_invalid": sum(
            item["new"] is not None and item["new"]["semantic_invalid"] for item in results
        ),
        "parse_invalid": sum(item["parse_error"] is not None for item in results),
        "fixed_task_ids": [item["task_id"] for item in fixed],
        "results": results,
        "projection_scope": (
            "Validator-only compatibility projection of the legacy Phase-9 schema; "
            "it is not executed and does not infer missing dependency semantics."
        ),
    }


def markdown(audit: Dict[str, Any]) -> str:
    lines = [
        "# Phase-10 Validator Offline Audit",
        "",
        "This audit uses only the 40 TaskAgent outputs saved in Phase 9; LLM/API calls: **0**. "
        "Because those outputs predate Structured Atomic Task IR, each successfully parsed legacy object is passed through a validator-only compatibility projection. The projection moves close-only items to terminal constraints but does not invent dependency edges and is never executed.",
        "",
        "## Result",
        "",
        "| Measure | Count |",
        "|---|---:|",
        f"| Saved TaskAgent outputs | {audit['saved_outputs']} |",
        f"| Old validator rejected | {audit['old_validator_rejected']} |",
        f"| New validator rejected | {audit['new_validator_rejected']} |",
        f"| Old false rejection fixed | {audit['old_false_rejection_fixed']} |",
        f"| JSON parse-invalid | {audit['parse_invalid']} |",
        f"| Schema-invalid after projection | {audit['schema_invalid']} |",
        f"| Semantic-invalid after projection | {audit['semantic_invalid']} |",
        "",
        "## Fixed false rejections",
        "",
        "The old validator rejected a lexical prefix. The new validator accepts the same dominant semantic commitment structurally as `TRANSFER`; it never applies `if \"move\" in text: reject` logic.",
        "",
        "| Task | Phase-9 legal transfer text | Old | New |",
        "|---|---|---|---|",
    ]
    by_id = {item["task_id"]: item for item in audit["results"]}
    for task_id in audit["fixed_task_ids"]:
        item = by_id[task_id]
        payload = json.loads(item["raw_output"])
        move = next(
            atomic["instruction"]
            for atomic in payload["atomic_tasks"]
            if atomic["instruction"].lstrip().lower().startswith("move ")
        )
        lines.append(f"| `{task_id}` | {move} | reject | accept |")
    lines.extend(
        [
            "",
            "All four are Long-11 transfer cases (`s0_01`, `s1_05`, `s2_09`, and Long-11 item `s2_11`). They were implementation rejections, not navigation-only tasks.",
            "",
            "## Validator boundary",
            "",
            "The Phase-10 validator checks JSON/schema shape, the five allowed atomic types, scene-inventory grounding, non-empty semantic goals, dependency references, and DAG acyclicity. Navigation is rejected structurally because `NAVIGATION` is not an allowed type and because each allowed type carries a state/process commitment. Surface words such as *move*, *walk*, or *position* are not semantic classifiers.",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def main() -> Dict[str, Any]:
    if REPORT.exists() or DETAIL.exists():
        raise RuntimeError("Refusing to overwrite Phase-10 validator audit artifacts")
    audit = build()
    _write_exclusive(DETAIL, json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    _write_exclusive(REPORT, markdown(audit))
    return {key: value for key, value in audit.items() if key != "results"}


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=2))

