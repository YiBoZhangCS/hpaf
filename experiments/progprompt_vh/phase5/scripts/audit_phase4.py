#!/usr/bin/env python3
"""Offline, multi-label failure audit for the immutable Phase-4 pilot.

This script reads Phase-4 artifacts and writes only inside ``phase5``.  It does
not call an LLM, execute a new method, or alter/re-score the Phase-4 records.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[4]
PHASE4_RAW = ROOT / "experiments/progprompt_vh/results/raw_runs.jsonl"
PHASE5 = ROOT / "experiments/progprompt_vh/phase5"
OUT_CSV = PHASE5 / "results/failure_taxonomy.csv"
OUT_MD = PHASE5 / "FAILURE_AUDIT.md"

CATEGORY_META = {
    "A_benchmark_goal_artifact": (
        "Official-only missing conditions are demonstration endpoint artifacts.",
        "Yes: Phase 5 retains official scores and adds a pre-frozen semantic evaluator.",
    ),
    "B_decomposition_granularity_error": (
        "A first-level atomic task is navigation, retrieval, positioning, or a prerequisite-only open/close step.",
        "Yes: TaskAgent is restricted to verifiable semantic state transitions.",
    ),
    "C_impossible_or_unrepresentable_goal": (
        "An atomic instruction asks for waiting or an event/effect with no persistent graph predicate.",
        "Partly: illegal decompositions are rejected; unavoidable task-level ambiguities are frozen and disclosed.",
    ),
    "D_unsupported_action": (
        "A generated primitive is outside the Evolving Graph-compatible shared API.",
        "Yes: all Phase-5 prompts and the executor share a source-audited action set.",
    ),
    "E_action_precondition_failure": (
        "A supported action fails a graph precondition such as proximity, hand occupancy, container state, facing, or room.",
        "Yes: generic precondition guidance, current state, verification, and Retry-1 address it; failures remain possible.",
    ),
    "F_verification_false_negative": (
        "A recorded verifier result is false although every recorded condition detail is satisfied.",
        "Yes: Phase 5 uses a deterministic frozen-condition verifier.",
    ),
    "G_verified_but_stopped": (
        "The atomic goal verified true but boundary_executable/can_continue stopped the task.",
        "Yes: verified=True is the continuation gate; Exec is diagnostic only.",
    ),
    "H_legitimate_planning_failure": (
        "Official failure with a non-artifact goal missing and no detected implementation/evaluator/decomposition issue.",
        "No special-case fix: it remains a planning failure in the controlled comparison.",
    ),
    "I_stale_state_generation_error": (
        "A Phase-4 Static run emitted an action contradicted by state changed by an earlier independently generated atomic program.",
        "Yes: Static is removed; Hierarchical generation always receives current state.",
    ),
    "J_recovery_parser_error": (
        "A ProgPrompt else-recovery line was misparsed as an action named 'else'.",
        "Yes: Phase-5 interpreter preserves and explicitly parses assertion/recovery branches.",
    ),
}

UNSUPPORTED_NAMES = {"walktowards", "puton", "use", "wash"}
GRANULARITY_RE = re.compile(
    r"^(locate|find|walk|navigate|move|position|open|close|bring\b.*\bto\b.*\barea)",
    re.IGNORECASE,
)
UNREPRESENTABLE_RE = re.compile(
    r"\b(wait|toasting process|brush teeth|eat the chips|watch the television|watch tv|rinse)\b",
    re.IGNORECASE,
)
STALE_STATE_RE = re.compile(
    r"\b(is not closed|is not open|is not off|is not on|is sitting)\b",
    re.IGNORECASE,
)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def atomic_texts(record: Dict[str, Any]) -> List[str]:
    result = []
    for item in record.get("atomic_tasks") or []:
        if isinstance(item, dict):
            result.append(str(item.get("task", "")))
        else:
            result.append(str(item))
    return result


def is_artifact_relation(relation: str) -> bool:
    parts = relation.split()
    if len(parts) != 3:
        return False
    subject, predicate, obj = parts
    if predicate == "CLOSE":
        return True
    if predicate.startswith("HOLD") and subject == "character":
        return True
    if predicate == "INSIDE" and (subject == "character" or obj.endswith("room")):
        return True
    return False


def error_evidence(record: Dict[str, Any], predicate) -> List[str]:
    evidence = []
    for error in record.get("errors") or []:
        line = str(error.get("line", ""))
        message = str(error.get("message", ""))
        if predicate(line, message, error):
            evidence.append(f"{line}: {message}".strip(": "))
    return evidence


def unsupported_action_name(line: str, message: str) -> str:
    match = re.match(r"\s*([a-z]+)\s*\(", line.lower())
    name = match.group(1) if match else ""
    if name in UNSUPPORTED_NAMES:
        return name
    unknown = re.search(r'Unknown action "([A-Z_]+)"', message)
    if unknown and unknown.group(1).lower() in UNSUPPORTED_NAMES:
        return unknown.group(1).lower()
    return ""


def classify(record: Dict[str, Any]) -> List[Tuple[str, str]]:
    labels: List[Tuple[str, str]] = []
    sr = int(record.get("SR", 0))
    missing_relations = list(record.get("missing_goal_relations") or [])
    missing_states = list(record.get("missing_goal_states") or [])

    if (
        sr == 0
        and (missing_relations or missing_states)
        and not missing_states
        and all(is_artifact_relation(item) for item in missing_relations)
    ):
        labels.append(
            (
                "A_benchmark_goal_artifact",
                "Official missing set contains only endpoint artifacts: "
                + " | ".join(missing_relations[:4]),
            )
        )

    granular = [text for text in atomic_texts(record) if GRANULARITY_RE.search(text.strip())]
    if granular:
        labels.append(
            (
                "B_decomposition_granularity_error",
                "First-level prerequisite task(s): " + " | ".join(granular[:3]),
            )
        )

    unrepresentable = [
        text for text in atomic_texts(record) if UNREPRESENTABLE_RE.search(text)
    ]
    if unrepresentable:
        labels.append(
            (
                "C_impossible_or_unrepresentable_goal",
                "No stable graph-level completion for: " + " | ".join(unrepresentable[:2]),
            )
        )

    unsupported = error_evidence(
        record, lambda line, message, _: bool(unsupported_action_name(line, message))
    )
    if unsupported:
        labels.append(("D_unsupported_action", " | ".join(unsupported[:2])))

    preconditions = error_evidence(
        record,
        lambda line, message, error: (
            error.get("error_type") == "precondition_failure"
            and not unsupported_action_name(line, message)
            and "atomic" not in message.lower()
        ),
    )
    if preconditions:
        labels.append(("E_action_precondition_failure", " | ".join(preconditions[:2])))

    false_negatives = []
    verified_but_stopped = []
    for verification in record.get("atomic_verifications") or []:
        details = verification.get("condition_details") or []
        if (
            verification.get("verified") is False
            and details
            and all(detail.get("satisfied") is True for detail in details)
        ):
            false_negatives.append(
                str((verification.get("atomic_task") or {}).get("task", "unknown atomic"))
            )
        if verification.get("verified") is True and (
            verification.get("can_continue") is False
            or verification.get("boundary_executable") is False
        ):
            verified_but_stopped.append(
                f"{(verification.get('atomic_task') or {}).get('task', 'unknown atomic')} "
                f"(boundary_executable={verification.get('boundary_executable')}, "
                f"can_continue={verification.get('can_continue')})"
            )
    if false_negatives:
        labels.append(("F_verification_false_negative", " | ".join(false_negatives)))
    if verified_but_stopped:
        labels.append(("G_verified_but_stopped", " | ".join(verified_but_stopped)))

    stale = error_evidence(
        record,
        lambda _line, message, _error: (
            record.get("method") == "HPAF-Decomp-Static"
            and bool(STALE_STATE_RE.search(message))
        ),
    )
    if stale:
        labels.append(("I_stale_state_generation_error", " | ".join(stale[:2])))

    parser = error_evidence(
        record,
        lambda line, message, _error: (
            line.strip().lower().startswith("else:")
            and "hallucinated action: else" in message.lower()
        ),
    )
    if parser:
        labels.append(("J_recovery_parser_error", " | ".join(parser[:2])))

    detected_nonlegitimate = {name for name, _ in labels}
    if sr == 0 and not detected_nonlegitimate.intersection(
        {
            "A_benchmark_goal_artifact",
            "B_decomposition_granularity_error",
            "C_impossible_or_unrepresentable_goal",
            "D_unsupported_action",
            "E_action_precondition_failure",
            "F_verification_false_negative",
            "G_verified_but_stopped",
            "I_stale_state_generation_error",
            "J_recovery_parser_error",
        }
    ):
        missing = (missing_states + missing_relations)[:4]
        labels.append(
            (
                "H_legitimate_planning_failure",
                "Non-artifact official goals remained missing: " + " | ".join(missing),
            )
        )
    return labels


def csv_rows(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for record in records:
        for category, evidence in classify(record):
            rows.append(
                {
                    "failure_category": category,
                    "task": record["task"],
                    "method": record["method"],
                    "phase4_sr": record["SR"],
                    "phase4_gcr": record["GCR"],
                    "example_trace": evidence,
                    "phase5_design_addresses_it": CATEGORY_META[category][1],
                }
            )
    return rows


def render_markdown(records: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> str:
    counts = Counter(row["failure_category"] for row in rows)
    tasks: Dict[str, set] = defaultdict(set)
    methods: Dict[str, set] = defaultdict(set)
    examples: Dict[str, str] = {}
    for row in rows:
        category = row["failure_category"]
        tasks[category].add(row["task"])
        methods[category].add(row["method"])
        examples.setdefault(category, row["example_trace"])

    lines = [
        "# Phase-4 Failure Audit",
        "",
        "This is an offline, read-only, multi-label diagnosis of the 30 immutable "
        "Phase-4 records. Counts are affected-record counts per category, so columns "
        "are not mutually exclusive and do not sum to 30. Phase-4 metrics are not modified.",
        "",
        "## Taxonomy",
        "",
        "| Failure category | Count | Affected tasks | Affected methods | Example trace | Phase-5 response |",
        "|---|---:|---|---|---|---|",
    ]
    for category in CATEGORY_META:
        example = examples.get(category, "No matching Phase-4 record")
        lines.append(
            "| {category} | {count} | {tasks} | {methods} | {example} | {response} |".format(
                category=category,
                count=counts.get(category, 0),
                tasks="; ".join(sorted(tasks.get(category, set()))) or "—",
                methods="; ".join(sorted(methods.get(category, set()))) or "—",
                example=example.replace("|", "/"),
                response=CATEGORY_META[category][1].replace("|", "/"),
            )
        )
    lines += [
        "",
        "## Audit rules",
        "",
        "- `benchmark_goal_artifact` is conservative: a failed official score is tagged "
        "only when every missing condition is CLOSE, character holding/location, or an "
        "object's demonstration-specific room containment; missing task-object states or "
        "relations prevent this label.",
        "- `unsupported_action` excludes `else:`. That is a recovery-interpreter defect, "
        "reported separately as `recovery_parser_error`.",
        "- `verification_false_negative` uses the saved verification and condition-detail "
        "records only; it does not reinterpret or change an old score.",
        "- `legitimate_planning_failure` is deliberately residual: official SR=0 and none "
        "of the detected artifact/implementation/decomposition conditions applies.",
        "",
        "## Integrity",
        "",
        f"Input: `{PHASE4_RAW.relative_to(ROOT)}` ({len(records)} records).",
        "The audit script writes only Phase-5 artifacts and makes no API calls.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    records = read_jsonl(PHASE4_RAW)
    if len(records) != 30:
        raise RuntimeError(f"Expected exactly 30 Phase-4 records, found {len(records)}")
    pairs = {(record["task"], record["method"]) for record in records}
    if len(pairs) != 30:
        raise RuntimeError("Phase-4 input contains duplicate task/method pairs")
    rows = csv_rows(records)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    OUT_MD.write_text(render_markdown(records, rows), encoding="utf-8")
    print(f"audited_records={len(records)} taxonomy_rows={len(rows)}")
    print(f"wrote={OUT_CSV.relative_to(ROOT)}")
    print(f"wrote={OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
