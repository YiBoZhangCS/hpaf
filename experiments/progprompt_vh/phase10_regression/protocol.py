"""Identity and integrity checks for the Phase-10R frozen regression protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from experiments.progprompt_vh.adapters.paths import PROJECT_ROOT
from experiments.progprompt_vh.phase6.dataset import sha256
from experiments.progprompt_vh.phase8 import runner as phase8_runner
from experiments.progprompt_vh.phase10 import runner as phase10_runner
from experiments.progprompt_vh.phase10.scripts.freeze_method import (
    LOCK as METHOD_LOCK,
    verify_method_freeze,
)


ROOT = PROJECT_ROOT / "experiments/progprompt_vh/phase10_regression"
MANIFEST = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/vh40_manifest.json"
PHASE9_LOCK = PROJECT_ROOT / "experiments/progprompt_vh/phase9/data/VH40_PROTOCOL_LOCK.json"
COMPLEXITY = ROOT / "VH40_SEMANTIC_COMPLEXITY.json"
LOCK = ROOT / "PHASE10R_PROTOCOL_LOCK.json"
CONFIG = PROJECT_ROOT / "experiments/progprompt_vh/phase10/configs/benchmark.yaml"
METHODS = ["ProgPrompt-Compat", "HPAF-Flat", "HPAF-Full"]


def bundle_hash(paths: Iterable[Path]) -> str:
    payload = [(str(path.relative_to(PROJECT_ROOT)), sha256(path)) for path in paths]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def load_entries() -> List[Dict[str, Any]]:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))["entries"]
    if len(entries) != 40 or len({item["task_id"] for item in entries}) != 40:
        raise RuntimeError("VH-40 must contain exactly 40 unique tasks")
    source_counts = {
        "official_source": sum(item["official_or_extension"] == "official_source" for item in entries),
        "synthetic_long_horizon_extension": sum(
            item["official_or_extension"] == "synthetic_long_horizon_extension"
            for item in entries
        ),
    }
    horizons = {
        name: sum(item["horizon"] == name for item in entries)
        for name in ("Short", "Medium", "Long")
    }
    if source_counts != {"official_source": 29, "synthetic_long_horizon_extension": 11}:
        raise RuntimeError(f"VH-40 provenance mismatch: {source_counts}")
    if horizons != {"Short": 9, "Medium": 16, "Long": 15}:
        raise RuntimeError(f"VH-40 horizon mismatch: {horizons}")
    return entries


def load_complexity() -> Dict[str, Dict[str, Any]]:
    payload = json.loads(COMPLEXITY.read_text(encoding="utf-8"))
    rows = payload["entries"]
    if payload.get("method_output_used") is not False or len(rows) != 40:
        raise RuntimeError("Frozen semantic complexity is invalid")
    result = {item["task_id"]: item for item in rows}
    if set(result) != {item["task_id"] for item in load_entries()}:
        raise RuntimeError("Semantic complexity task IDs do not match VH-40")
    return result


def current_identity() -> Dict[str, Any]:
    method = verify_method_freeze()
    phase9 = json.loads(PHASE9_LOCK.read_text(encoding="utf-8"))
    manifest_hash = sha256(MANIFEST)
    if manifest_hash != phase9["manifest_sha256"]:
        raise RuntimeError("VH-40 manifest differs from its Phase-9 frozen hash")
    entries = load_entries()
    load_complexity()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ark = config["llm"]["ark"]
    if (
        config["llm"]["active_provider"] != "ark"
        or ark["default_model"] != "doubao-seed-2-1-pro-260628"
        or config["llm"]["temperature"] != 0.0
        or ark.get("extra_body") != {"thinking": {"type": "disabled"}}
    ):
        raise RuntimeError("Phase-10 frozen ARK backend identity mismatch")
    phase10_runner.configure_runtime()
    runtime_implementation = phase8_runner.implementation_sha256()
    return {
        "phase10_method_freeze_sha256": sha256(METHOD_LOCK),
        "method_sha256": method["method_sha256"],
        "prompt_sha256": method["prompt_sha256"],
        "evaluator_sha256": method["evaluator_sha256"],
        "config_sha256": method["config_sha256"],
        "manifest_sha256": manifest_hash,
        "phase9_manifest_lock_sha256": sha256(PHASE9_LOCK),
        "complexity_sha256": sha256(COMPLEXITY),
        "runtime_implementation_sha256": runtime_implementation,
        "task_count": len(entries),
        "backend": "ARK",
        "model": "doubao-seed-2-1-pro-260628",
        "api_interface": "responses.create",
        "temperature": 0.0,
        "thinking": "disabled",
    }


def verify_protocol_lock() -> Dict[str, Any]:
    if not LOCK.exists():
        raise RuntimeError("Phase-10R protocol lock is absent")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    current = current_identity()
    current.update(
        {
            "orchestration_sha256": sha256(ROOT / "scripts/run_formal.py"),
            "protocol_code_sha256": sha256(ROOT / "protocol.py"),
        }
    )
    mismatch = {
        key: {"expected": lock.get(key), "actual": value}
        for key, value in current.items()
        if lock.get(key) != value
    }
    if mismatch:
        raise RuntimeError(f"Phase-10R frozen identity mismatch: {json.dumps(mismatch)}")
    if (
        lock.get("records_required") != 120
        or lock.get("method_order") != METHODS
        or lock.get("execution_order") != "task-major, method-minor"
    ):
        raise RuntimeError("Phase-10R matrix shape/order mismatch")
    return lock
