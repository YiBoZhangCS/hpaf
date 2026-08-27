#!/usr/bin/env python3
"""Run regression then confirmatory exactly once under the frozen protocol."""

from __future__ import annotations

import json

from experiments.progprompt_vh.phase7.dataset import PHASE7_ROOT
from experiments.progprompt_vh.phase7.runner import implementation_sha256, run_matrix, verify_protocol_lock


def main() -> None:
    lock = verify_protocol_lock()
    smoke_path = PHASE7_ROOT / "results/smoke/PASSED.json"
    if not smoke_path.exists():
        raise RuntimeError("Formal run blocked: regression-only smoke has not passed")
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke.get("protocol_lock") != lock or smoke.get("implementation_sha256") != implementation_sha256():
        raise RuntimeError("Formal run blocked: smoke does not match frozen protocol/implementation")

    regression = run_matrix(
        "regression", PHASE7_ROOT / "results/regression", "regression_formal"
    )
    if len(regression) != 60:
        raise RuntimeError("Regression formal matrix incomplete")
    confirmatory = run_matrix(
        "confirmatory", PHASE7_ROOT / "results/confirmatory", "confirmatory_formal"
    )
    if len(confirmatory) != 27:
        raise RuntimeError("Confirmatory formal matrix incomplete")
    print(json.dumps({"regression_records": 60, "confirmatory_records": 27}, indent=2))


if __name__ == "__main__":
    main()

