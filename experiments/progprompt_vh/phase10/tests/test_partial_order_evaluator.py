from experiments.progprompt_vh.phase10.verification.partial_order_evaluator import (
    evaluate_partial_order_goal,
    phase9_goal_to_partial_order,
)


def _trace(*actions):
    rows = []
    for verb, first, second in actions:
        suffix = f" <{second}> (3)" if second else ""
        rows.append(
            {
                "source_action": f"<char0> [{verb}] <{first}> (2){suffix}",
                "parsed_action": "present",
                "success": True,
            }
        )
    return {"graph_execution_trace": rows}


def _phase9_cross_goal():
    return {
        "event_stages": [
            {"stage": 1, "description": "stage at waypoint", "event": {"verb": "putback", "first": "apple", "second": "table"}},
            {"stage": 2, "description": "store in intermediate", "event": {"verb": "putin", "first": "apple", "second": "fridge"}},
            {"stage": 3, "description": "retrieve", "event": {"verb": "grab", "first": "apple"}},
            {"stage": 4, "description": "restore intermediate state", "event": {"verb": "close", "first": "fridge"}},
            {"stage": 5, "description": "deliver", "event": {"verb": "putback", "first": "apple", "second": "sofa"}},
        ],
        "final_conditions": [
            {"condition": "ON(apple, sofa)", "predicate": "RELATION", "subject": "apple", "relation": "ON", "object": "sofa"},
            {"condition": "STATE(fridge, CLOSED)", "predicate": "STATE", "object": "fridge", "value": "CLOSED"},
        ],
    }


def test_terminal_close_may_follow_delivery():
    goal = phase9_goal_to_partial_order(_phase9_cross_goal(), "cross_location_mixed")
    record = _trace(
        ("putback", "apple", "table"),
        ("putin", "apple", "fridge"),
        ("grab", "apple", None),
        ("putback", "apple", "sofa"),
        ("close", "fridge", None),
    )
    score = evaluate_partial_order_goal(
        record,
        goal,
        None,
        precomputed_final_conditions={
            "ON(apple, sofa)": (True, "edge"),
            "STATE(fridge, CLOSED)": (True, "state"),
        },
    )
    assert score["final_semantic_SR"] == 1


def test_required_semantic_order_is_still_enforced():
    goal = phase9_goal_to_partial_order(_phase9_cross_goal(), "cross_location_mixed")
    record = _trace(
        ("putback", "apple", "sofa"),
        ("putback", "apple", "table"),
        ("putin", "apple", "fridge"),
        ("grab", "apple", None),
        ("close", "fridge", None),
    )
    score = evaluate_partial_order_goal(
        record,
        goal,
        None,
        precomputed_final_conditions={
            "ON(apple, sofa)": (True, "edge"),
            "STATE(fridge, CLOSED)": (True, "state"),
        },
    )
    assert score["final_semantic_SR"] == 0
    assert any(item["kind"] == "required_dependency" for item in score["semantic_missing_conditions"])


def test_parse_failure_is_not_counterfactually_repaired_offline():
    goal = phase9_goal_to_partial_order(_phase9_cross_goal(), "cross_location_mixed")
    score = evaluate_partial_order_goal(
        _trace(
            ("putback", "apple", "table"),
            ("putin", "apple", "fridge"),
            ("grab", "apple", None),
            ("putback", "apple", "sofa"),
        ),
        goal,
        None,
        precomputed_final_conditions={
            "ON(apple, sofa)": (True, "edge"),
            "STATE(fridge, CLOSED)": (True, "state"),
        },
        implementation_rejection=True,
    )
    assert score["final_semantic_SR"] == 0
    assert score["implementation_rejection"] is True

