#!/usr/bin/env python3
"""Replay saved development assertions through the constrained interface."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml

from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor
from experiments.progprompt_vh.phase8.compat_client import (
    BINARY_ASSERTION_FORMAT,
    Phase8LLMClient,
)


ROOT = Path(__file__).resolve().parents[1]
PHASE6_RAW = ROOT.parent / "phase6/results/raw_runs.jsonl"
OUT = ROOT / "results/baseline_compat/raw_calls.jsonl"


def saved_assertions():
    for line in PHASE6_RAW.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["method"] != "ProgPrompt":
            continue
        ordinal = 0
        for call in row["llm_call_records"]:
            if call["call_role"] != "assertion_verification":
                continue
            ordinal += 1
            yield {
                "audit_id": f"{row['task_id']}::{ordinal}",
                "task_id": row["task_id"],
                "ordinal": ordinal,
                "prompt": call["prompt"],
            }


def main() -> None:
    config = yaml.safe_load((ROOT / "configs/benchmark.yaml").read_text())
    client = Phase8LLMClient.from_env_spec(config["llm"]["ark"])
    saved = list(saved_assertions())
    if len(saved) != 152 or len({item["audit_id"] for item in saved}) != 152:
        raise RuntimeError("Expected 152 unique Phase-6 development assertions")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["audit_id"]] = row

    for index, item in enumerate(saved, 1):
        if item["audit_id"] in existing:
            continue
        call = client.generate_binary_assertion(item["prompt"], max_tokens=3)
        parsed = Phase7GraphProgramExecutor.parse_assertion_answer(call.output_text)
        row = {
            **item,
            "raw_transport_output": call.raw_output,
            "normalized_output": call.output_text,
            "strict_binary": parsed is not None,
            "parsed_boolean": parsed,
            "request_text_format": BINARY_ASSERTION_FORMAT,
            "call": call.to_dict(),
        }
        with OUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        existing[item["audit_id"]] = row
        print(f"ASSERTION {index}/152 binary={parsed is not None}", flush=True)

    rows = [existing[item["audit_id"]] for item in saved]
    strict = sum(item["strict_binary"] for item in rows)
    rate = strict / len(rows)
    counts = Counter(item["normalized_output"] for item in rows)
    report = [
        "# ProgPrompt-Compat Final Binary Interface",
        "",
        "ARK Responses structured output was capability-tested before implementation. The endpoint accepted a strict JSON-schema string enum with values `True` and `False`.",
        "",
        "The released state-check prompt is unchanged. Phase 8 constrains only the modern API transport, uses a three-token cap sufficient for the JSON string, decodes that transport, and then accepts only exact normalized `True` or `False`. There is no reasoning instruction, semantic fallback, second call, or substring inference.",
        "",
        f"- Development assertions: **{strict}/{len(rows)} ({100 * rate:.1f}%) strict binary**.",
        f"- Normalized output counts: `{dict(counts)}`.",
        "- Method label: **ProgPrompt-Compat**.",
        "- Interpretation: ProgPrompt adapted to the modern Responses backend with a binary-constrained assertion interface matching the original method's intended True/False state-check contract.",
        "",
        f"Gate (`>=95%`): **{'PASS' if rate >= 0.95 else 'FAIL'}**.",
    ]
    (ROOT / "BASELINE_COMPAT_FINAL.md").write_text("\n".join(report) + "\n")
    if rate < 0.95:
        raise RuntimeError(f"Binary compatibility gate failed: {strict}/{len(rows)}")
    print(json.dumps({"strict": strict, "total": len(rows), "rate": rate, "counts": counts}, indent=2))


if __name__ == "__main__":
    main()

