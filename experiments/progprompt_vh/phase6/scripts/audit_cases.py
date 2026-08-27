#!/usr/bin/env python3
"""Build lossless chronological evidence timelines for the Phase-6 case audit.

This script is deliberately offline: it reads the immutable formal run records,
replays their already-grounded Evolving Graph actions from the frozen initial
graphs, and emits every stored API request/output plus every graph-state delta.
It never calls an LLM or Unity and never changes an experiment result.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from experiments.progprompt_vh.phase5.evaluation.official_evaluator import evaluate_task
from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor, symbolic_state_snapshot
from experiments.progprompt_vh.phase6.dataset import (
    ACTION_PATH,
    PHASE6_ROOT,
    graph_sha256,
    load_final_graph,
    load_initial_graph,
)
from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import evaluate_conditions


RUNS = PHASE6_ROOT / "results/runs"
AUDIT_ROOT = PHASE6_ROOT / "audits"
MANIFEST_PATH = PHASE6_ROOT / "data/task_manifest.json"
SEMANTIC_PATH = PHASE6_ROOT / "data/semantic_goals.json"

CASE_FILES = {
    "case1_collect_4_fruits_full_timeline.md": [
        "progprompt__test_unseen_ambiguous_goals_collect_4_fruits_such_as_apple_banana_etc_in_the_dishbowl.json",
        "hpaf_flat__test_unseen_ambiguous_goals_collect_4_fruits_such_as_apple_banana_etc_in_the_dishbowl.json",
        "hpaf_full__test_unseen_ambiguous_goals_collect_4_fruits_such_as_apple_banana_etc_in_the_dishbowl.json",
    ],
    "case2_book_to_sofa_full_timeline.md": [
        "progprompt__env1_bring_my_book_to_the_sofa.json",
        "hpaf_flat__env1_bring_my_book_to_the_sofa.json",
        "hpaf_full__env1_bring_my_book_to_the_sofa.json",
        "progprompt__env2_bring_my_book_to_the_sofa.json",
        "hpaf_flat__env2_bring_my_book_to_the_sofa.json",
        "hpaf_full__env2_bring_my_book_to_the_sofa.json",
    ],
    "case3_microwave_chicken_full_timeline.md": [
        "progprompt__env1_microwave_chicken.json",
        "hpaf_flat__env1_microwave_chicken.json",
        "hpaf_full__env1_microwave_chicken.json",
    ],
}

CASE_TITLES = {
    "case1_collect_4_fruits_full_timeline.md": "Case 1 — collect 4 fruits in the dishbowl",
    "case2_book_to_sofa_full_timeline.md": "Case 2 — bring my book to the sofa (env1 and env2)",
    "case3_microwave_chicken_full_timeline.md": "Case 3 — microwave chicken",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fenced(value: Any, language: str = "text") -> List[str]:
    if value is None:
        text = "<null>"
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return [f"````{language}", text, "````", ""]


def graph_signature(graph: Dict[str, Any]) -> Tuple[Dict[int, Tuple[str, Tuple[str, ...]]], set[Tuple[int, str, int, str, str]]]:
    classes = {node["id"]: node["class_name"] for node in graph["nodes"]}
    nodes = {
        node["id"]: (node["class_name"], tuple(sorted(node.get("states", []))))
        for node in graph["nodes"]
    }
    edges = {
        (
            edge["from_id"],
            classes.get(edge["from_id"], "<?>"),
            edge["to_id"],
            classes.get(edge["to_id"], "<?>"),
            edge["relation_type"],
        )
        for edge in graph["edges"]
    }
    return nodes, edges


def edge_text(edge: Tuple[int, str, int, str, str]) -> str:
    from_id, from_class, to_id, to_class, relation = edge
    return f"{from_class}#{from_id} {relation} {to_class}#{to_id}"


def graph_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, List[str]]:
    before_nodes, before_edges = graph_signature(before)
    after_nodes, after_edges = graph_signature(after)
    node_changes = []
    for node_id in sorted(set(before_nodes) | set(after_nodes)):
        old = before_nodes.get(node_id)
        new = after_nodes.get(node_id)
        if old != new:
            old_text = "<missing>" if old is None else f"{old[0]}#{node_id} states={list(old[1])}"
            new_text = "<missing>" if new is None else f"{new[0]}#{node_id} states={list(new[1])}"
            node_changes.append(f"{old_text} -> {new_text}")
    return {
        "node_state_changes": node_changes,
        "removed_edges": [edge_text(edge) for edge in sorted(before_edges - after_edges)],
        "added_edges": [edge_text(edge) for edge in sorted(after_edges - before_edges)],
    }


def replay_transitions(
    record: Dict[str, Any],
    entry: Dict[str, Any],
    actions_payload: Dict[str, Any],
    semantic_conditions: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    initial_graph = load_initial_graph(entry)
    if graph_sha256(initial_graph) != record["initial_state_sha256"]:
        raise RuntimeError(f"Initial graph hash mismatch: {record['task_id']}/{record['method']}")
    executor = GraphProgramExecutor(
        initial_graph,
        actions_payload=actions_payload,
        llm_client=None,
        unity_comm=None,
        seed=0,
    )
    transitions = []
    for index, expected in enumerate(record["graph_execution_trace"], 1):
        before = executor.final_graph
        if expected["parsed_action"] is None:
            actual = executor.graph_executor.record_failed_attempt(
                expected["source_action"], expected["error"]
            )
        else:
            actual = executor.graph_executor.execute_ground_truth_action(expected["source_action"])
            if actual.success:
                executor._refresh_evaluator_augmentations()
        if bool(actual.success) != bool(expected["success"]):
            raise RuntimeError(
                f"Replay success mismatch at {record['task_id']}/{record['method']} action {index}"
            )
        if (actual.error or "") != (expected["error"] or ""):
            raise RuntimeError(
                f"Replay error mismatch at {record['task_id']}/{record['method']} action {index}: "
                f"{actual.error!r} != {expected['error']!r}"
            )
        after = executor.final_graph
        transitions.append(
            {
                "ordinal": index,
                "source_action": expected["source_action"],
                "parsed_action": expected["parsed_action"],
                "success": expected["success"],
                "error": expected["error"],
                "delta": graph_delta(before, after),
            }
        )

    semantic = evaluate_conditions(executor.final_graph, semantic_conditions)
    official = evaluate_task(
        final_state=executor.final_graph,
        ground_truth_final_state=load_final_graph(entry),
        initial_state=initial_graph,
        exec_ratio=executor.exec_ratio,
    )
    if semantic["final_semantic_SR"] != record["final_semantic_SR"]:
        raise RuntimeError(f"Replay semantic SR mismatch: {record['task_id']}/{record['method']}")
    if official["SR"] != record["official_SR"] or abs(official["Exec"] - record["Exec"]) > 1e-12:
        raise RuntimeError(f"Replay official/Exec mismatch: {record['task_id']}/{record['method']}")
    if len(transitions) != len([event for event in record["execution_trace"] if event["event"] == "action"]):
        raise RuntimeError(f"Action trace length mismatch: {record['task_id']}/{record['method']}")
    validation = {
        "initial_graph_sha256": graph_sha256(initial_graph),
        "action_count": len(transitions),
        "replay_exec": executor.exec_ratio,
        "recorded_exec": record["Exec"],
        "replay_semantic_sr": semantic["final_semantic_SR"],
        "recorded_semantic_sr": record["final_semantic_SR"],
        "replay_official_sr": official["SR"],
        "recorded_official_sr": record["official_SR"],
        "reconstructed_final_symbolic_observation": symbolic_state_snapshot(executor.final_graph),
    }
    return transitions, validation


def request_metadata(call: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "call_role": call["call_role"],
        "broad_role": call["broad_role"],
        "provider": call["provider"],
        "model": call["model"],
        "api_interface": call["api_interface"],
        "temperature": call["temperature"],
        "max_tokens": call["max_tokens"],
        "seed": call["seed"],
        "stop": call["stop"],
        "frequency_penalty": call["frequency_penalty"],
        "extra_body": call["extra_body"],
        "wall_clock_timeout_s": call["wall_clock_timeout_s"],
        "response_id": call["response_id"],
        "latency_s": call["latency_s"],
        "error_type": call["error_type"],
        "error_message": call["error_message"],
    }


class TimelineWriter:
    def __init__(self, record: Dict[str, Any], transitions: Sequence[Dict[str, Any]]):
        self.record = record
        self.transitions = list(transitions)
        self.call_index = 0
        self.action_index = 0
        self.event_index = 0
        self.lines: List[str] = []

    def marker(self, label: str) -> None:
        self.event_index += 1
        self.lines += [f"### T{self.event_index:03d} — {label}", ""]

    def api_call(self, expected_role: str) -> Dict[str, Any]:
        call = self.record["llm_call_records"][self.call_index]
        self.call_index += 1
        if call["call_role"] != expected_role:
            raise RuntimeError(
                f"Expected {expected_role}, got {call['call_role']} at call {self.call_index}"
            )
        self.marker(f"API call {self.call_index}: `{call['call_role']}`")
        self.lines += ["Request/response metadata:", ""] + fenced(request_metadata(call), "json")
        self.lines += ["API `instructions` (complete):", ""] + fenced(call.get("instructions"))
        self.lines += ["API prompt/input (complete):", ""] + fenced(call["prompt"])
        self.lines += ["Raw model output (complete):", ""] + fenced(call["raw_output"])
        self.lines += ["Parsed `output_text` used by the runtime:", ""] + fenced(call["output_text"])
        total = call["prompt_tokens"] + call["completion_tokens"]
        self.lines += [
            f"Tokens: prompt={call['prompt_tokens']}, completion={call['completion_tokens']}, total={total}.",
            "",
        ]
        return call

    def observation(self, label: str, value: str) -> None:
        self.marker(label)
        self.lines += fenced(value)

    def comment(self, event: Dict[str, Any]) -> None:
        self.marker(f"Program comment/subgoal: `{event['line']}`")

    def assertion(self, event: Dict[str, Any], call: Dict[str, Any]) -> None:
        decision = "true" in call["output_text"].lower()
        self.marker(f"Assertion runtime decision: `{event['line']}`")
        self.lines += [
            f"- Parsed gate: `{decision}` (`'true' in output_text.lower()`).",
            f"- Trace API-success flag: `{event['success']}` (this means the call completed, not that the assertion was true).",
            f"- Trace detail/output_text: `{event['detail']}`",
            f"- Subgoal: `{event['subgoal']}`",
            "",
        ]

    def recovery(self, event: Dict[str, Any]) -> None:
        self.marker(f"Recovery control event: `{event['line']}`")
        self.lines += [
            f"- Event: `{event['event']}`",
            f"- Success: `{event['success']}`",
            f"- Detail: `{event['detail']}`",
            f"- Subgoal: `{event['subgoal']}`",
            "",
        ]

    def action(self, event: Dict[str, Any]) -> None:
        transition = self.transitions[self.action_index]
        self.action_index += 1
        if (event.get("compiled_action") or event["line"]) != transition["source_action"]:
            raise RuntimeError(
                f"Action alignment mismatch: {(event.get('compiled_action') or event['line'])!r} "
                f"!= {transition['source_action']!r}"
            )
        self.marker(f"Action {self.action_index}: `{event['line']}`")
        self.lines += [
            f"- Subgoal: `{event['subgoal']}`",
            f"- Compiled action: `{event.get('compiled_action')}`",
            f"- Parsed graph action: `{transition['parsed_action']}`",
            f"- Success: `{event['success']}`",
            f"- Error/detail: `{event['detail']}`",
            "",
            "Complete deterministic graph-state delta:",
            "",
        ]
        delta = transition["delta"]
        if not any(delta.values()):
            self.lines += ["- No graph state/relation change.", ""]
            return
        for heading, key, prefix in [
            ("Node state changes", "node_state_changes", "~"),
            ("Removed relations", "removed_edges", "-"),
            ("Added relations", "added_edges", "+"),
        ]:
            values = delta[key]
            if values:
                self.lines += [f"{heading}:", ""]
                self.lines += [f"- `{prefix} {value}`" for value in values]
                self.lines += [""]

    def execution_events(self, events: Iterable[Dict[str, Any]], assertion_calls: bool = False) -> None:
        for event in events:
            if event["event"] == "comment":
                self.comment(event)
            elif event["event"] == "assert":
                if not assertion_calls:
                    raise RuntimeError("Unexpected assertion outside ProgPrompt")
                call = self.api_call("assertion_verification")
                self.assertion(event, call)
            elif event["event"] == "action":
                self.action(event)
            else:
                self.recovery(event)

    def finish(self) -> None:
        if self.call_index != len(self.record["llm_call_records"]):
            raise RuntimeError(
                f"Unconsumed API calls for {self.record['task_id']}/{self.record['method']}: "
                f"{self.call_index}/{len(self.record['llm_call_records'])}"
            )
        if self.action_index != len(self.transitions):
            raise RuntimeError(
                f"Unconsumed action transitions for {self.record['task_id']}/{self.record['method']}: "
                f"{self.action_index}/{len(self.transitions)}"
            )


def render_record(
    record: Dict[str, Any],
    entry: Dict[str, Any],
    transitions: Sequence[Dict[str, Any]],
    validation: Dict[str, Any],
) -> str:
    lines = [
        f"## {record['task_id']} — {record['method']}",
        "",
        f"Source run: `results/runs/{Path(record['_source_path']).name}`  ",
        f"Source SHA-256: `{record['_source_sha256']}`  ",
        f"Run id: `{record['run_id']}`  ",
        f"Run timestamp: `{record['timestamp']}`",
        "",
        "### Recorded outcome",
        "",
        f"- Semantic SR/GCR: `{record['final_semantic_SR']}` / `{record['semantic_GCR']}`",
        f"- Official SR/GCR: `{record['official_SR']}` / `{record['official_GCR']}`",
        f"- Exec: `{record['Exec']}`",
        f"- Online done: `{record['final_online_done']}`",
        f"- Error type: `{record['error_type']}`",
        f"- Error message: `{record['error_message']}`",
        "",
        "Frozen semantic evaluation details:",
        "",
        *fenced(record["semantic_condition_details"], "json"),
        "### Chronological timeline",
        "",
    ]
    writer = TimelineWriter(record, transitions)
    if record["method"] == "ProgPrompt":
        writer.api_call("whole_program_generation")
        writer.execution_events(record["execution_trace"], assertion_calls=True)
    elif record["method"] == "HPAF-Flat":
        writer.observation("Initial symbolic observation", record["flat_initial_observation"])
        writer.api_call("flat_program_agent")
        writer.execution_events(record["execution_trace"])
        final_output = record["online_verification_outputs"][0]
        writer.observation("Post-execution symbolic observation", final_output["observation"])
        writer.api_call("flat_verifier")
    elif record["method"] == "HPAF-Full":
        writer.api_call("task_agent")
        online_iter = iter(record["online_verification_outputs"])
        for atomic in record["atomic_records"]:
            atomic_id = atomic["atomic_task"]["id"]
            writer.observation(
                f"Atomic {atomic_id} initial symbolic observation",
                atomic["initial_observation"],
            )
            writer.api_call("atomic_program_agent")
            writer.execution_events(atomic["initial_execution_trace"])
            first_output = next(online_iter)
            writer.observation(
                f"Atomic {atomic_id} post-execution symbolic observation",
                first_output["observation"],
            )
            writer.api_call("atomic_verifier")
            if atomic["retry_used"]:
                writer.api_call("repair_program_agent")
                writer.execution_events(atomic["repair_execution_trace"])
                repair_output = next(online_iter)
                writer.observation(
                    f"Atomic {atomic_id} post-repair symbolic observation",
                    repair_output["observation"],
                )
                writer.api_call("post_repair_verifier")
        try:
            next(online_iter)
            raise RuntimeError("Unconsumed online verifier output")
        except StopIteration:
            pass
    else:
        raise ValueError(record["method"])
    writer.finish()
    lines += writer.lines

    role_calls = Counter(call["call_role"] for call in record["llm_call_records"])
    role_tokens = Counter(
        {
            role: sum(
                call["prompt_tokens"] + call["completion_tokens"]
                for call in record["llm_call_records"]
                if call["call_role"] == role
            )
            for role in role_calls
        }
    )
    lines += [
        "### Final reconstructed state and validation",
        "",
        "Final symbolic observation reconstructed from the frozen initial graph and exact stored graph actions:",
        "",
        *fenced(validation["reconstructed_final_symbolic_observation"]),
        "Replay validation:",
        "",
        *fenced(validation, "json"),
        "Recorded errors:",
        "",
        *fenced(record["errors"], "json"),
        "### Token/call ledger",
        "",
        "| Role | Calls | Tokens |",
        "|---|---:|---:|",
    ]
    for role in sorted(role_calls, key=lambda item: next(i for i, call in enumerate(record["llm_call_records"]) if call["call_role"] == item)):
        lines.append(f"| {role} | {role_calls[role]} | {role_tokens[role]} |")
    lines += [
        f"| **Total** | **{record['total_calls']}** | **{record['total_tokens']}** |",
        "",
        f"Aggregate prompt/completion tokens: `{record['total_prompt_tokens']}` / `{record['total_completion_tokens']}`.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    by_task = {entry["task_id"]: entry for entry in manifest["entries"]}
    semantic = json.loads(SEMANTIC_PATH.read_text(encoding="utf-8"))
    semantic_by_task = {item["task_id"]: item["conditions"] for item in semantic["tasks"]}
    actions_payload = json.loads(ACTION_PATH.read_text(encoding="utf-8"))
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)

    evidence_manifest: Dict[str, Any] = {
        "mode": "offline deterministic replay of immutable formal records",
        "llm_calls_made": 0,
        "unity_calls_made": 0,
        "source_files": {},
        "output_files": {},
    }
    for output_name, filenames in CASE_FILES.items():
        output = AUDIT_ROOT / output_name
        lines = [
            f"# {CASE_TITLES[output_name]} — complete chronological evidence",
            "",
            "This is a lossless rendering of the stored formal run evidence. Every API",
            "prompt/input, raw model output, parsed runtime output, action, assertion/",
            "verifier decision, per-call token count, and deterministic graph-state delta",
            "is shown in runtime order. State deltas are offline reconstructions from the",
            "frozen initial graph plus the exact stored grounded action IDs; replayed Exec,",
            "Semantic SR, and Official SR are required to match the immutable record.",
            "",
        ]
        for filename in filenames:
            source = RUNS / filename
            record = json.loads(source.read_text(encoding="utf-8"))
            record["_source_path"] = str(source)
            record["_source_sha256"] = sha256(source)
            entry = by_task[record["task_id"]]
            transitions, validation = replay_transitions(
                record,
                entry,
                actions_payload,
                semantic_by_task[record["task_id"]],
            )
            lines.append(render_record(record, entry, transitions, validation))
            evidence_manifest["source_files"][str(source.relative_to(PHASE6_ROOT))] = sha256(source)
        output.write_text("\n".join(lines), encoding="utf-8")
        evidence_manifest["output_files"][str(output.relative_to(PHASE6_ROOT))] = sha256(output)

    manifest_output = AUDIT_ROOT / "evidence_manifest.json"
    manifest_output.write_text(json.dumps(evidence_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence_manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
