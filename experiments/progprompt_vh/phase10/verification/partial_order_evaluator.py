"""Method-independent semantic DAG evaluator.

Reference programs establish feasibility and a horizon only. Success is defined
by semantic events, required dependency edges, terminal constraints, and final
persistent goals; incidental reference total order is not scored.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
    for field in ("first", "second"):
        expected = pattern.get(field)
        if expected is not None and str(action.get(field, "")).lower() != str(expected).lower():
            return False
    return True


def _patterns(event: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return list(event.get("any_of") or [event["event"]])


def validate_partial_order_goal(goal: Mapping[str, Any]) -> None:
    if str(goal.get("kind", "")).upper() != "SEMANTIC_DAG_AND_STATE":
        raise ValueError(f"Unsupported Phase-10 semantic goal: {goal.get('kind')}")
    events = goal.get("semantic_events")
    edges = goal.get("required_dependency_edges")
    if not isinstance(events, list) or not events:
        raise ValueError("semantic_events must be non-empty")
    if not isinstance(edges, list):
        raise ValueError("required_dependency_edges must be a list")
    ids = [item.get("id") for item in events]
    if any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("semantic event IDs must be unique non-empty strings")
    known = set(ids)
    indegree = {item: 0 for item in ids}
    children: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        before, after = edge.get("before"), edge.get("after")
        if before not in known or after not in known or before == after:
            raise ValueError(f"invalid semantic dependency edge: {edge}")
        children[before].append(after)
        indegree[after] += 1
    queue = deque(item for item in ids if indegree[item] == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(ids):
        raise ValueError("required semantic dependency graph must be acyclic")


def _topological_ids(goal: Mapping[str, Any]) -> List[str]:
    ids = [item["id"] for item in goal["semantic_events"]]
    indegree = {item: 0 for item in ids}
    children: Dict[str, List[str]] = defaultdict(list)
    for edge in goal["required_dependency_edges"]:
        children[edge["before"]].append(edge["after"])
        indegree[edge["after"]] += 1
    ready = deque(item for item in ids if indegree[item] == 0)
    result: List[str] = []
    while ready:
        item = ready.popleft()
        result.append(item)
        for child in children[item]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    return result


def _candidate_indices(
    actions: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]
) -> Dict[str, List[int]]:
    return {
        event["id"]: [
            index
            for index, action in enumerate(actions)
            if any(_matches(action, pattern) for pattern in _patterns(event))
        ]
        for event in events
    }


def _causal_assignment(
    actions: Sequence[Mapping[str, Any]], goal: Mapping[str, Any]
) -> Optional[Dict[str, int]]:
    """Find distinct action evidence satisfying only required DAG edges."""
    events = {item["id"]: item for item in goal["semantic_events"]}
    order = _topological_ids(goal)
    candidates = _candidate_indices(actions, list(events.values()))
    parents: Dict[str, List[str]] = defaultdict(list)
    for edge in goal["required_dependency_edges"]:
        parents[edge["after"]].append(edge["before"])
    assignment: Dict[str, int] = {}
    used: set[int] = set()

    def search(position: int) -> bool:
        if position == len(order):
            return True
        event_id = order[position]
        lower_bound = max((assignment[parent] for parent in parents[event_id]), default=-1)
        for index in candidates[event_id]:
            if index in used or index <= lower_bound:
                continue
            assignment[event_id] = index
            used.add(index)
            if search(position + 1):
                return True
            used.remove(index)
            assignment.pop(event_id, None)
        return False

    return dict(assignment) if search(0) else None


def _independent_assignment(
    actions: Sequence[Mapping[str, Any]], goal: Mapping[str, Any]
) -> Dict[str, int]:
    """Assign available distinct evidence for informative failure accounting."""
    candidates = _candidate_indices(actions, goal["semantic_events"])
    result: Dict[str, int] = {}
    used: set[int] = set()
    for event in goal["semantic_events"]:
        for index in candidates[event["id"]]:
            if index not in used:
                result[event["id"]] = index
                used.add(index)
                break
    return result


def _offline_condition_result(
    condition: Mapping[str, Any],
    final_graph: Optional[Dict[str, Any]],
    precomputed: Optional[Mapping[str, Tuple[bool, Any]]],
) -> Tuple[bool, Any]:
    key = str(condition.get("condition", ""))
    if final_graph is not None:
        return condition_satisfied(final_graph, dict(condition))
    if precomputed is None or key not in precomputed:
        raise ValueError(f"No final graph or precomputed result for {key}")
    return precomputed[key]


def evaluate_partial_order_goal(
    record: Dict[str, Any],
    goal: Dict[str, Any],
    final_graph: Optional[Dict[str, Any]],
    *,
    precomputed_final_conditions: Optional[Mapping[str, Tuple[bool, Any]]] = None,
    implementation_rejection: bool = False,
) -> Dict[str, Any]:
    """Evaluate semantic partial-order success from trace plus terminal graph state."""
    validate_partial_order_goal(goal)
    actions = successful_actions(record)
    causal = _causal_assignment(actions, goal)
    assignment = causal if causal is not None else _independent_assignment(actions, goal)
    event_by_id = {item["id"]: item for item in goal["semantic_events"]}
    details: List[Dict[str, Any]] = []

    for event in goal["semantic_events"]:
        index = assignment.get(event["id"])
        details.append(
            {
                "kind": "semantic_event",
                "id": event["id"],
                "description": event.get("description", ""),
                "expected": _patterns(event),
                "satisfied": index is not None,
                "evidence": dict(actions[index]) if index is not None else None,
            }
        )
    for edge in goal["required_dependency_edges"]:
        before, after = edge["before"], edge["after"]
        satisfied = (
            before in assignment
            and after in assignment
            and assignment[before] < assignment[after]
        )
        details.append(
            {
                "kind": "required_dependency",
                "before": before,
                "after": after,
                "satisfied": satisfied,
                "evidence": {
                    "before_ordinal": actions[assignment[before]]["ordinal"] if before in assignment else None,
                    "after_ordinal": actions[assignment[after]]["ordinal"] if after in assignment else None,
                },
            }
        )

    for kind, conditions in (
        ("terminal_constraint", goal.get("terminal_constraints", [])),
        ("final_persistent_goal", goal.get("final_conditions", [])),
    ):
        for condition in conditions:
            satisfied, evidence = _offline_condition_result(
                condition, final_graph, precomputed_final_conditions
            )
            details.append(
                {
                    "kind": kind,
                    "condition": condition,
                    "satisfied": bool(satisfied),
                    "evidence": evidence,
                }
            )

    semantic_ok = causal is not None and all(item["satisfied"] for item in details)
    success = semantic_ok and not implementation_rejection
    if implementation_rejection:
        details.append(
            {
                "kind": "implementation_rejection",
                "satisfied": False,
                "evidence": "TaskAgent parse/validation failure with zero executed actions is not counterfactually repaired offline.",
            }
        )
    satisfied_count = sum(int(item["satisfied"]) for item in details)
    return {
        "final_semantic_SR": int(success),
        "semantic_GCR": satisfied_count / len(details) if details else 0.0,
        "semantic_goal_condition_count": len(details),
        "semantic_satisfied_condition_count": satisfied_count,
        "semantic_condition_details": details,
        "semantic_missing_conditions": [item for item in details if not item["satisfied"]],
        "partial_order_assignment": {
            event_id: actions[index]["ordinal"] for event_id, index in assignment.items()
        },
        "implementation_rejection": implementation_rejection,
    }


def phase9_goal_to_partial_order(
    causal_goal: Mapping[str, Any], category: str
) -> Dict[str, Any]:
    """Convert a frozen Phase-9 template from reference order to task semantics."""
    stages = list(causal_goal["event_stages"])
    semantic_stages = [
        item
        for item in stages
        if str((item.get("event") or {}).get("verb", "")).lower() != "close"
    ]
    events = [
        {
            "id": f"E{item['stage']}",
            "description": item.get("description", ""),
            **({"any_of": item["any_of"]} if item.get("any_of") else {"event": item["event"]}),
        }
        for item in semantic_stages
    ]
    ids = [item["id"] for item in events]
    edges: List[Dict[str, str]] = []
    if category == "causal_multi_object" and len(ids) >= 4:
        edges.extend(
            [
                {"before": ids[0], "after": ids[2]},
                {"before": ids[1], "after": ids[2]},
                {"before": ids[2], "after": ids[3]},
            ]
        )
    else:
        edges.extend(
            {"before": before, "after": after}
            for before, after in zip(ids, ids[1:])
        )
    conditions = list(causal_goal.get("final_conditions", []))
    terminals = [
        item for item in conditions if str(item.get("predicate", "")).upper() == "STATE"
    ]
    persistent = [
        item for item in conditions if str(item.get("predicate", "")).upper() != "STATE"
    ]
    goal = {
        "kind": "SEMANTIC_DAG_AND_STATE",
        "semantic_events": events,
        "required_dependency_edges": edges,
        "terminal_constraints": terminals,
        "final_conditions": persistent,
        "reference_program_role": "feasibility_and_horizon_only",
    }
    validate_partial_order_goal(goal)
    return goal


def semantic_dependency_depth(goal: Mapping[str, Any]) -> int:
    validate_partial_order_goal(goal)
    parents: Dict[str, List[str]] = defaultdict(list)
    for edge in goal["required_dependency_edges"]:
        parents[edge["after"]].append(edge["before"])
    memo: Dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in memo:
            memo[node] = 1 + max((depth(parent) for parent in parents[node]), default=0)
        return memo[node]

    return max(depth(item["id"]) for item in goal["semantic_events"])

