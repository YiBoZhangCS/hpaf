#!/usr/bin/env python3
"""Replay all saved Phase-6 assertion prompts through the corrected cap."""

from __future__ import annotations

import json
from collections import Counter

from experiments.progprompt_vh.phase7.dataset import PHASE6_ROOT, PHASE7_ROOT
from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor
from experiments.progprompt_vh.phase7.runner import load_config
from experiments.progprompt_vh.phase6.runner import make_client


RAW = PHASE6_ROOT / "results/raw_runs.jsonl"
OUT = PHASE7_ROOT / "results/assertion_contract_audit/raw_calls.jsonl"


def saved_assertions():
    for line in RAW.read_text(encoding="utf-8").splitlines():
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
                "phase6_output": call["output_text"],
            }


def main() -> None:
    saved = list(saved_assertions())
    if len(saved) != 152 or len({item["audit_id"] for item in saved}) != 152:
        raise RuntimeError("Expected exactly 152 saved Phase-6 assertions")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                existing[item["audit_id"]] = item
    client = make_client(load_config())
    for index, item in enumerate(saved, 1):
        if item["audit_id"] in existing:
            continue
        call = client.generate(
            item["prompt"], max_tokens=2, temperature=0.0, stop=["\n"],
            frequency_penalty=0.0, seed=None, instructions=None,
        )
        parsed = Phase7GraphProgramExecutor.parse_assertion_answer(call.output_text)
        result = {
            **item,
            "phase7_output": call.output_text,
            "strict_binary": parsed is not None,
            "parsed_boolean": parsed,
            "call": call.to_dict(),
        }
        with OUT.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        existing[item["audit_id"]] = result
        print(f"ASSERTION {index}/152 binary={parsed is not None}", flush=True)

    rows = [existing[item["audit_id"]] for item in saved]
    strict = sum(item["strict_binary"] for item in rows)
    counts = Counter(item["phase7_output"].strip() for item in rows)
    report = [
        "# Phase-7 Assertion Contract Audit", "",
        "All 152 immutable Phase-6 assertion prompts were replayed before confirmatory execution using the released-compatible two-token cap, unchanged prompt, no extra reasoning instruction, and no fallback call.", "",
        f"- Strict binary: **{strict}/152 ({100*strict/152:.1f}%)**.",
        f"- Non-binary: **{152-strict}/152**.",
        f"- Output counts: `{dict(counts)}`.",
        "- Parser unit cases: whitespace/newline/case variants normalize; explanatory text remains invalid.",
        "- These compatibility calls are audit overhead and are excluded from benchmark cost.", "",
    ]
    (PHASE7_ROOT / "ASSERTION_CONTRACT_AUDIT.md").write_text("\n".join(report), encoding="utf-8")
    print(json.dumps({"strict": strict, "total": 152, "counts": counts}, indent=2))


if __name__ == "__main__":
    main()

