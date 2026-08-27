#!/usr/bin/env python3
"""Quarantine Phase-4 records invalidated by a closed-loop verifier bug.

This is deliberately narrow and idempotence-protected. It keeps valid
ProgPrompt/Static rows, saves every removed row as evidence, and leaves the
runner to execute exactly one valid ClosedLoop trial per task afterward.
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.progprompt_vh.adapters.paths import RESULTS_ROOT


def main() -> None:
    raw_path = RESULTS_ROOT / "raw_runs.jsonl"
    diagnostics = RESULTS_ROOT / "diagnostics"
    diagnostic_path = diagnostics / "phase4_pre_verifier_fix_invalid_runs.jsonl"
    if diagnostic_path.exists():
        raise RuntimeError(f"Refusing to run twice: {diagnostic_path} already exists")

    rows = [
        json.loads(line)
        for line in raw_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    invalid = [
        row
        for row in rows
        if row["method"] == "HPAF-Decomp-ClosedLoop" or "SR" not in row
    ]
    retained = [row for row in rows if row not in invalid]
    if len(rows) != 28 or len(invalid) != 10 or len(retained) != 18:
        raise RuntimeError(
            f"Unexpected Phase-4 shape: all={len(rows)} invalid={len(invalid)} "
            f"retained={len(retained)}"
        )

    diagnostics.mkdir(parents=True, exist_ok=True)
    diagnostic_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in invalid),
        encoding="utf-8",
    )
    replacement = raw_path.with_suffix(".jsonl.repaired")
    replacement.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in retained),
        encoding="utf-8",
    )
    replacement.replace(raw_path)
    print(
        json.dumps(
            {
                "retained_valid_records": len(retained),
                "quarantined_invalid_records": len(invalid),
                "diagnostic_path": str(diagnostic_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
