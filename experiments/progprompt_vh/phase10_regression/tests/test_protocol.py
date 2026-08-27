import json

from experiments.progprompt_vh.phase10_regression.build_complexity import derive
from experiments.progprompt_vh.phase10_regression.protocol import (
    load_complexity,
    load_entries,
)
from experiments.progprompt_vh.phase10_regression.scripts.run_formal import _enrich


def test_vh40_identity_and_complexity_allocations():
    entries = load_entries()
    complexity = load_complexity()
    assert len(entries) == len(complexity) == 40
    assert sum(item["official_or_extension"] == "official_source" for item in entries) == 29
    assert sum(item["horizon"] == "Long" for item in entries) == 15


def test_complexity_is_benchmark_semantic_not_method_dynamic():
    official = {
        "task_id": "official",
        "official_or_extension": "official_source",
    }
    crossloc = {
        "task_id": "crossloc",
        "official_or_extension": "synthetic_long_horizon_extension",
        "category": "cross_location_mixed",
    }
    assert derive(official)["semantic_atomic_count"] == 1
    assert derive(crossloc)["dependency_depth"] == 3
    assert not derive(crossloc)["method_output_used"]


def test_record_enrichment_preserves_raw_and_adds_parsed_output():
    entry = load_entries()[0]
    complexity = load_complexity()[entry["task_id"]]
    core = {
        "method": "HPAF-Full",
        "error_type": "",
        "error_message": "",
        "taskagent_parse_success": True,
        "taskagent_validator_rejected": False,
        "atomic_records": [
            {"atomic_task": {"id": "A1"}, "dependencies_ready": []}
        ],
        "llm_call_records": [
            {"output_text": json.dumps({"done": True}), "raw_output": "raw"}
        ],
    }
    enriched = _enrich(core, entry, complexity)
    assert enriched["instruction"] == entry["task_text"]
    assert enriched["evaluator_type"] == entry["evaluator_type"]
    assert enriched["llm_call_records"][0]["parsed_output"] == {"done": True}
    assert enriched["validator_result"]["valid"]
    assert enriched["current_ready_nodes"] == [
        {"atomic_id": "A1", "dependencies_ready": []}
    ]
