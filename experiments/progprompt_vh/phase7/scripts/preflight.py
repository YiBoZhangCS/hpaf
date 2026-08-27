#!/usr/bin/env python3
"""Offline Phase-7 preflight; never opens a network or Unity session."""

from __future__ import annotations

import json
from pathlib import Path

from experiments.progprompt_vh.phase7.dataset import PHASE7_ROOT, build_manifests
from experiments.progprompt_vh.phase7.methods.common import PROGRAM_AGENT_RULES
from experiments.progprompt_vh.phase7.runner import implementation_sha256, verify_protocol_lock
from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor


def main() -> None:
    lock = verify_protocol_lock()
    data = build_manifests()
    parser_cases = {
        "True": True, "True\n": True, "true": True,
        "False": False, "False\n": False, "false": False,
        "explanation": None,
    }
    parser_ok = all(Phase7GraphProgramExecutor.parse_assertion_answer(k) is v for k, v in parser_cases.items())
    forbidden = ["microwave_chicken", "chicken", "garbagecan", "fridge", "test_unseen::", "env1::", "env2::", "STATE(", "RELATION("]
    prompt_hits = [marker for marker in forbidden if marker.lower() in PROGRAM_AGENT_RULES.lower()]
    output = {
        "mode": "offline preflight only",
        "network_calls": 0,
        "unity_calls": 0,
        "protocol_lock_verified": True,
        "implementation_sha256": implementation_sha256(),
        "set_sizes": {name: len(data[name]) for name in ["regression", "confirmatory", "combined"]},
        "confirmatory_trace_goals": len([item for item in data["confirmatory"] if item["evaluator_type"] == "generic_trace"]),
        "synthetic_tasks": 0,
        "assertion_parser_unit_tests": parser_ok,
        "generic_prompt_forbidden_marker_hits": prompt_hits,
        "external_execution_status": "BLOCKED_BY_SECURITY_APPROVAL",
        "blocker": "The environment rejected outbound ARK requests carrying frozen simulator task/state prompts; no formal smoke or benchmark record was created.",
    }
    if not parser_ok or prompt_hits:
        raise RuntimeError(json.dumps(output))
    path = PHASE7_ROOT / "PHASE7_PREFLIGHT.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

