"""Generic evaluator for causally ordered trace events and final graph state."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Tuple

from experiments.progprompt_vh.phase6.verification.deterministic_evaluator import (
    condition_satisfied,
)
from experiments.progprompt_vh.phase7.verification.trace_evaluator import (
    successful_actions,
)


def _matches(action: Mapping[str, Any], pattern: Mapping[str, Any]) -> bool:
    verbs = pattern.get("verbs", [pattern.get("verb")])
    allowed = {str(item).lower() for item in verbs if item is not None}
    if allowed and str(action.get("verb", "")).lower() not in allowed:
        return False
    for field in ["first", "second"]:
        expected = pattern.get(field)
        if expected is not None and str(action.get(field, "")).lower() != str(expected).lower():
            return False
    return True


def _ordered_stage_results(
    actions: Sequence[Mapping[str, Any]], stages: Sequence[Mapping[str, Any]]
) -> Tuple[List[Dict[str, Any]], bool]:
    cursor = 0
    details: List[Dict[str, Any]] = []
    for stage in stages:
        alternatives = stage.get("any_of") or [stage["event"]]
        match = None
        for index in range(cursor, len(actions)):
            if any(_matches(actions[index], pattern) for pattern in alternatives):
                match = dict(actions[index])
                cursor = index + 1
                break
        details.append(
            {
                "kind": "ordered_event_stage",
                "stage": stage.get("stage"),
                "description": stage.get("description", ""),
                "expected": alternatives,
                "satisfied": match is not None,
                "evidence": match,
            }
        )
        if match is None:
            for remaining in stages[len(details) :]:
                details.append(
                    {
                        "kind": "ordered_event_stage",
                        "stage": remaining.get("stage"),
                        "description": remaining.get("description", ""),
                        "expected": remaining.get("any_of") or [remaining["event"]],
                        "satisfied": False,
                        "evidence": None,
                    }
                )
            return details, False
    return details, True


def evaluate_causal_goal(
    record: Dict[str, Any],
    goal: Dict[str, Any],
    final_graph: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate one frozen generic causal template without method declarations."""
    if str(goal.get("kind", "")).upper() != "ORDERED_EVENTS_AND_STATE":
        raise ValueError(f"Unsupported Phase-9 causal goal: {goal.get('kind')}")

    actions = successful_actions(record)
    details, ordered_ok = _ordered_stage_results(actions, goal["event_stages"])
    for condition in goal.get("final_conditions", []):
        satisfied, evidence = condition_satisfied(final_graph, condition)
        details.append(
            {
                "kind": "final_state_condition",
                "condition": condition,
                "satisfied": satisfied,
                "evidence": evidence,
            }
        )

    satisfied_count = sum(int(item["satisfied"]) for item in details)
    success = ordered_ok and satisfied_count == len(details)
    return {
        "final_semantic_SR": int(success),
        "semantic_GCR": satisfied_count / len(details),
        "semantic_goal_condition_count": len(details),
        "semantic_satisfied_condition_count": satisfied_count,
        "semantic_condition_details": details,
        "semantic_missing_conditions": [item for item in details if not item["satisfied"]],
    }

