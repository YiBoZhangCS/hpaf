"""Freeze method-independent VH-40 semantic complexity before formal execution."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10_regression"
MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/vh40_manifest.json"
OUTPUT = ROOT / "VH40_SEMANTIC_COMPLEXITY.json"


def derive(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map frozen benchmark semantics, never a method output, to HPAF bins."""
    if entry["official_or_extension"] == "official_source":
        atomic_count, depth = 1, 1
        rationale = (
            "One dominant official-source semantic commitment; multiple co-target "
            "objects, when present, are one coupled commitment."
        )
    elif entry.get("category") == "cross_location_mixed":
        atomic_count, depth = 3, 3
        rationale = "Three predecessor-dependent transfer checkpoints in the frozen template."
    else:
        atomic_count, depth = 2, 2
        rationale = "Two predecessor-dependent checkpoints in the frozen causal template."
    return {
        "task_id": entry["task_id"],
        "semantic_atomic_count": atomic_count,
        "dependency_depth": depth,
        "source": "frozen_benchmark_semantics_phase10_analysis",
        "method_output_used": False,
        "rationale": rationale,
    }


def build() -> Dict[str, Any]:
    if OUTPUT.exists():
        raise RuntimeError("Refusing to overwrite frozen VH-40 semantic complexity")
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    rows: List[Dict[str, Any]] = [derive(item) for item in entries]
    atomic = Counter(item["semantic_atomic_count"] for item in rows)
    depth = Counter(item["dependency_depth"] for item in rows)
    if atomic != Counter({1: 29, 2: 9, 3: 2}):
        raise RuntimeError(f"Unexpected semantic atomic allocation: {atomic}")
    if depth != Counter({1: 29, 2: 9, 3: 2}):
        raise RuntimeError(f"Unexpected dependency-depth allocation: {depth}")
    payload = {
        "schema_version": 1,
        "name": "VH-40 frozen method-independent semantic complexity",
        "task_count": 40,
        "method_output_used": False,
        "grouping_rule": (
            "Official-source instructions are one dominant commitment; Long-11 uses "
            "the pre-frozen causal template checkpoints. Terminal constraints do not "
            "add atomics."
        ),
        "atomic_count_allocation": {str(key): value for key, value in sorted(atomic.items())},
        "dependency_depth_allocation": {str(key): value for key, value in sorted(depth.items())},
        "entries": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
