from __future__ import annotations

from typing import Any, Dict, Set, Tuple


def _conditions(graph: Dict[str, Any]) -> Tuple[Set[str], Set[str]]:
    """Match ProgPrompt's class-collapsed relation/state set construction."""
    object_ids = {node["id"]: node["class_name"] for node in graph["nodes"]}
    relations = {
        f'{object_ids[edge["from_id"]]} {edge["relation_type"]} '
        f'{object_ids[edge["to_id"]]}'
        for edge in graph["edges"]
    }
    object_states = {
        f'{node["class_name"]} {state}'
        for node in graph["nodes"]
        for state in node["states"]
    }
    return relations, object_states


def evaluate_task(
    final_state: Dict[str, Any],
    ground_truth_final_state: Dict[str, Any],
    initial_state: Dict[str, Any],
    exec_ratio: float,
) -> Dict[str, Any]:
    """Exact set formulas used by ``progprompt-vh/scripts/run_eval.py::eval``.

    The official raw name ``PSR`` is retained. The benchmark also exposes the
    same value as ``GCR`` because the paper names this formula Goal Conditions
    Recall.
    """
    relations_in, object_states_in = _conditions(initial_state)
    relations, object_states = _conditions(final_state)
    relations_gt, object_states_gt = _conditions(ground_truth_final_state)

    missing_relations = (relations_gt - relations_in) - (relations - relations_in)
    missing_states = (object_states_gt - object_states_in) - (
        object_states - object_states_in
    )
    goal_relations = relations_gt - relations_in
    goal_states = object_states_gt - object_states_in
    goal_count = len(goal_relations) + len(goal_states)
    if goal_count == 0:
        raise ZeroDivisionError("Official evaluator has no definition for zero goal conditions")

    unsatisfied_count = len(missing_relations) + len(missing_states)
    psr = 1.0 - (unsatisfied_count / goal_count)

    unchanged_missing_relations = (relations_gt & relations_in) - relations
    unchanged_missing_states = (object_states_gt & object_states_in) - object_states
    unchanged_total = len(relations_gt & relations_in) + len(object_states_gt & object_states_in)
    if unchanged_total == 0:
        raise ZeroDivisionError("Official evaluator has no definition for zero unchanged conditions")
    precision = 1.0 - (
        (len(unchanged_missing_relations) + len(unchanged_missing_states))
        / unchanged_total
    )

    return {
        "PSR": psr,
        "GCR": psr,
        "SR": int(psr == 1.0),
        "Precision": precision,
        "Exec": exec_ratio,
        "goal_condition_count": goal_count,
        "unsatisfied_goal_condition_count": unsatisfied_count,
        "missing_goal_relations": sorted(missing_relations),
        "missing_goal_states": sorted(missing_states),
    }

