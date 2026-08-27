from experiments.progprompt_vh.phase10.ir import topological_order, validate_ir


INVENTORY = {"apple", "fridge", "cabinet", "character"}


def _transfer(goal: str = "Move the apple from the fridge to the cabinet."):
    return {
        "id": "A1",
        "type": "TRANSFER",
        "focal_object": "apple",
        "source": "fridge",
        "target": "cabinet",
        "completion_mode": "state",
        "semantic_goal": goal,
        "depends_on": [],
    }


def test_move_prefixed_transfer_is_valid():
    ir = {"atomic_tasks": [_transfer()], "terminal_constraints": []}
    result = validate_ir(ir, INVENTORY)
    assert result.valid, result.issues
    assert result.dependency_depth == 1


def test_navigation_type_is_rejected_structurally_not_lexically():
    atomic = _transfer("Reach the cabinet.")
    atomic.update({"type": "NAVIGATION", "focal_object": "character", "target": "cabinet"})
    result = validate_ir({"atomic_tasks": [atomic], "terminal_constraints": []}, INVENTORY)
    assert not result.valid
    assert any(item.path.endswith(".type") for item in result.issues)


def test_dependency_cycle_and_unknown_inventory_are_rejected():
    first = _transfer()
    first["depends_on"] = ["A2"]
    second = dict(_transfer())
    second.update({"id": "A2", "focal_object": "pear", "depends_on": ["A1"]})
    result = validate_ir(
        {"atomic_tasks": [first, second], "terminal_constraints": []}, INVENTORY
    )
    assert not result.valid
    assert result.dependency_depth == 0
    assert any("acyclic" in item.message for item in result.issues)
    assert any("pear" in item.message for item in result.issues)


def test_stable_topological_order_uses_dependencies_not_list_as_semantics():
    a1 = _transfer()
    a2 = dict(_transfer())
    a2.update({"id": "A2", "depends_on": ["A1"]})
    assert [item["id"] for item in topological_order({"atomic_tasks": [a2, a1]})] == [
        "A1",
        "A2",
    ]


def test_coupled_atomic_uses_one_inventory_grounded_primary_focal():
    atomic = _transfer("Stage the apple and pear together in the cabinet.")
    atomic.update({"type": "MULTI_OBJECT_COUPLED", "target": "cabinet"})
    valid = validate_ir(
        {"atomic_tasks": [atomic], "terminal_constraints": []},
        INVENTORY | {"pear"},
    )
    assert valid.valid, valid.issues

    atomic["focal_object"] = "apple,pear"
    invalid = validate_ir(
        {"atomic_tasks": [atomic], "terminal_constraints": []},
        INVENTORY | {"pear"},
    )
    assert not invalid.valid
    assert any(item.path.endswith(".focal_object") for item in invalid.issues)
