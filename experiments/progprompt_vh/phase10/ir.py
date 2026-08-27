"""Structured Semantic Atomic Task IR and semantic validation.

The validator deliberately does not classify semantics from lexical prefixes.
In particular, ``Move object from A to B`` is a valid TRANSFER commitment.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


ALLOWED_ATOMIC_TYPES = frozenset(
    {
        "TRANSFER",
        "STATE_CHANGE",
        "PROCESS",
        "MULTI_OBJECT_COUPLED",
        "INTERACTION",
    }
)
COMPLETION_MODES = frozenset({"state", "process"})
TERMINAL_PREDICATES = frozenset({"STATE", "RELATION"})


@dataclass(frozen=True)
class ValidationIssue:
    category: str
    path: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "category": self.category,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: Tuple[ValidationIssue, ...]
    dependency_depth: int

    @property
    def schema_invalid(self) -> bool:
        return any(item.category == "schema" for item in self.issues)

    @property
    def semantic_invalid(self) -> bool:
        return any(item.category == "semantic" for item in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "schema_invalid": self.schema_invalid,
            "semantic_invalid": self.semantic_invalid,
            "dependency_depth": self.dependency_depth,
            "issues": [item.to_dict() for item in self.issues],
        }


def parse_ir_json(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse a strict JSON object, tolerating only surrounding whitespace."""
    try:
        value = json.loads(text.strip())
    except (TypeError, json.JSONDecodeError) as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(value, dict):
        return None, "top-level TaskAgent value must be an object"
    return value, None


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _cycle_and_depth(tasks: Sequence[Mapping[str, Any]]) -> Tuple[bool, int]:
    clean = [item for item in tasks if isinstance(item, Mapping)]
    ids = {item.get("id") for item in clean if _text(item.get("id"))}
    parents = {
        item["id"]: [
            dep for dep in item.get("depends_on", []) if _text(dep) and dep in ids
        ]
        for item in clean
        if item.get("id") in ids and isinstance(item.get("depends_on"), list)
    }
    state: Dict[str, int] = {}
    memo: Dict[str, int] = {}

    def visit(node: str) -> int:
        if state.get(node) == 1:
            raise RuntimeError("cycle")
        if state.get(node) == 2:
            return memo[node]
        state[node] = 1
        depth = 1
        for parent in parents.get(node, []):
            depth = max(depth, visit(parent) + 1)
        state[node] = 2
        memo[node] = depth
        return depth

    try:
        depth = max((visit(node) for node in parents), default=0)
    except RuntimeError:
        return True, 0
    return False, depth


def dependency_depth(ir: Mapping[str, Any]) -> int:
    tasks = ir.get("atomic_tasks", [])
    if not isinstance(tasks, list):
        return 0
    cycle, depth = _cycle_and_depth(tasks)
    return 0 if cycle else depth


def topological_order(ir: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return stable topological order; declaration order breaks ready-node ties."""
    tasks = list(ir.get("atomic_tasks", []))
    result: List[Dict[str, Any]] = []
    completed: set[str] = set()
    while len(result) < len(tasks):
        ready = [
            item
            for item in tasks
            if item["id"] not in completed
            and set(item.get("depends_on", [])) <= completed
        ]
        if not ready:
            raise ValueError("atomic dependency graph is cyclic or unresolved")
        item = ready[0]
        result.append(dict(item))
        completed.add(item["id"])
    return result


def validate_ir(ir: Any, inventory: Iterable[str]) -> ValidationResult:
    """Validate schema, inventory grounding, DAG integrity, and commitment shape."""
    issues: List[ValidationIssue] = []
    available = {str(item) for item in inventory}
    if not isinstance(ir, dict):
        issue = ValidationIssue("schema", "$", "IR must be a JSON object")
        return ValidationResult(False, (issue,), 0)

    tasks = ir.get("atomic_tasks")
    terminals = ir.get("terminal_constraints")
    if not isinstance(tasks, list) or not tasks:
        issues.append(
            ValidationIssue("schema", "atomic_tasks", "must be a non-empty list")
        )
        tasks = []
    elif len(tasks) > 6:
        issues.append(
            ValidationIssue("schema", "atomic_tasks", "must contain at most 6 items")
        )
    if not isinstance(terminals, list):
        issues.append(
            ValidationIssue("schema", "terminal_constraints", "must be a list")
        )
        terminals = []

    ids: List[str] = []
    for index, item in enumerate(tasks):
        path = f"atomic_tasks[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue("schema", path, "must be an object"))
            continue
        atomic_id = item.get("id")
        atomic_type = item.get("type")
        focal = item.get("focal_object")
        source = item.get("source")
        target = item.get("target")
        mode = item.get("completion_mode")
        goal = item.get("semantic_goal")
        depends = item.get("depends_on")

        if not _text(atomic_id):
            issues.append(ValidationIssue("schema", f"{path}.id", "must be non-empty text"))
        else:
            ids.append(str(atomic_id))
        if atomic_type not in ALLOWED_ATOMIC_TYPES:
            issues.append(
                ValidationIssue(
                    "schema",
                    f"{path}.type",
                    f"must be one of {sorted(ALLOWED_ATOMIC_TYPES)}",
                )
            )
        if not _text(focal):
            issues.append(
                ValidationIssue("schema", f"{path}.focal_object", "must be non-empty text")
            )
        elif focal not in available:
            issues.append(
                ValidationIssue("schema", f"{path}.focal_object", f"not in scene inventory: {focal}")
            )
        for field, value in (("source", source), ("target", target)):
            if value is not None and not _text(value):
                issues.append(ValidationIssue("schema", f"{path}.{field}", "must be text or null"))
            elif isinstance(value, str) and value not in available:
                issues.append(
                    ValidationIssue("schema", f"{path}.{field}", f"not in scene inventory: {value}")
                )
        if mode not in COMPLETION_MODES:
            issues.append(
                ValidationIssue("schema", f"{path}.completion_mode", "must be state or process")
            )
        if not _text(goal):
            issues.append(
                ValidationIssue("schema", f"{path}.semantic_goal", "must be non-empty text")
            )
        if not isinstance(depends, list) or any(not _text(dep) for dep in depends):
            issues.append(
                ValidationIssue("schema", f"{path}.depends_on", "must be a list of atomic IDs")
            )

        # Structural semantic checks: no word-prefix classification is used.
        if atomic_type == "TRANSFER" and target is None:
            issues.append(
                ValidationIssue("semantic", path, "TRANSFER requires a target commitment")
            )
        if atomic_type in {"TRANSFER", "STATE_CHANGE"} and mode == "process":
            issues.append(
                ValidationIssue("semantic", path, f"{atomic_type} requires state completion")
            )
        if atomic_type in {"PROCESS", "INTERACTION"} and mode == "state":
            issues.append(
                ValidationIssue("semantic", path, f"{atomic_type} requires process completion")
            )

    if len(ids) != len(set(ids)):
        issues.append(ValidationIssue("schema", "atomic_tasks", "atomic IDs must be unique"))
    valid_ids = set(ids)
    for index, item in enumerate(tasks):
        if not isinstance(item, dict) or not isinstance(item.get("depends_on"), list):
            continue
        atomic_id = item.get("id")
        for dep in item["depends_on"]:
            if dep not in valid_ids:
                issues.append(
                    ValidationIssue(
                        "schema",
                        f"atomic_tasks[{index}].depends_on",
                        f"unknown dependency: {dep}",
                    )
                )
            if dep == atomic_id:
                issues.append(
                    ValidationIssue(
                        "schema",
                        f"atomic_tasks[{index}].depends_on",
                        "self-dependency is forbidden",
                    )
                )

    cycle, depth = _cycle_and_depth(tasks)
    if cycle:
        issues.append(ValidationIssue("schema", "atomic_tasks", "dependency graph must be acyclic"))

    for index, item in enumerate(terminals):
        path = f"terminal_constraints[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue("schema", path, "must be an object"))
            continue
        predicate = item.get("predicate")
        if predicate not in TERMINAL_PREDICATES:
            issues.append(
                ValidationIssue("schema", f"{path}.predicate", "must be STATE or RELATION")
            )
        if not _text(item.get("semantic_goal")):
            issues.append(
                ValidationIssue("schema", f"{path}.semantic_goal", "must be non-empty text")
            )
        if predicate == "STATE":
            obj, value = item.get("object"), item.get("value")
            if not _text(obj) or obj not in available:
                issues.append(
                    ValidationIssue("schema", f"{path}.object", f"not in scene inventory: {obj}")
                )
            if not _text(value):
                issues.append(ValidationIssue("schema", f"{path}.value", "must be non-empty text"))
        elif predicate == "RELATION":
            for field in ("subject", "object"):
                value = item.get(field)
                if not _text(value) or value not in available:
                    issues.append(
                        ValidationIssue("schema", f"{path}.{field}", f"not in scene inventory: {value}")
                    )
            if not _text(item.get("relation")):
                issues.append(
                    ValidationIssue("schema", f"{path}.relation", "must be non-empty text")
                )

    return ValidationResult(not issues, tuple(issues), 0 if cycle else depth)


_OLD_FORBIDDEN = re.compile(r"^\s*(locate|find|walk|navigate|move|position)\b", re.I)


def old_phase9_validation(payload: Any, inventory: Iterable[str]) -> ValidationResult:
    """Faithfully reproduce the Phase-9 TaskAgent validator for offline audit."""
    issues: List[ValidationIssue] = []
    available = set(inventory)
    if not isinstance(payload, dict):
        return ValidationResult(
            False, (ValidationIssue("schema", "$", "TaskAgent value is not an object"),), 0
        )
    atomics = payload.get("atomic_tasks")
    if not isinstance(atomics, list) or not 1 <= len(atomics) <= 6:
        return ValidationResult(
            False,
            (ValidationIssue("schema", "atomic_tasks", "must contain 1-6 items"),),
            0,
        )
    for expected_id, item in enumerate(atomics, 1):
        path = f"atomic_tasks[{expected_id - 1}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue("schema", path, "is not an object"))
            continue
        instruction = item.get("instruction")
        manipulated = item.get("manipulated_object")
        target = item.get("target_object")
        mode = item.get("completion_mode")
        intent = item.get("process_intent")
        if item.get("id") != expected_id or not _text(instruction):
            issues.append(ValidationIssue("schema", path, "invalid id/instruction"))
        elif _OLD_FORBIDDEN.match(instruction):
            issues.append(ValidationIssue("semantic", path, "forbidden navigation task"))
        if manipulated not in available:
            issues.append(ValidationIssue("schema", path, f"manipulated object unavailable: {manipulated}"))
        if target is not None and target not in available:
            issues.append(ValidationIssue("schema", path, f"target unavailable: {target}"))
        if mode not in COMPLETION_MODES:
            issues.append(ValidationIssue("schema", path, "invalid completion_mode"))
        if mode == "process" and not _text(intent):
            issues.append(ValidationIssue("schema", path, "process_intent is required"))
        if mode == "state" and intent is not None:
            issues.append(ValidationIssue("schema", path, "state process_intent must be null"))
    return ValidationResult(not issues, tuple(issues), len(atomics))


def project_phase9_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Project legacy saved output for a validator-only compatibility audit.

    The projection is not a replacement TaskAgent and is never executed. It moves
    legacy close-only atomics into terminal constraints and supplies only the
    structure that Phase 9 could represent; dependencies remain unspecified.
    """
    atomics: List[Dict[str, Any]] = []
    terminals: List[Dict[str, Any]] = []
    for item in payload.get("atomic_tasks", []):
        instruction = str(item.get("instruction", "")).strip()
        focal = item.get("manipulated_object")
        target = item.get("target_object")
        lower = instruction.lower()
        if lower.startswith("close ") and focal:
            terminals.append(
                {
                    "predicate": "STATE",
                    "object": focal,
                    "value": "CLOSED",
                    "semantic_goal": instruction,
                }
            )
            continue
        process_terms = ("wash", "heat", "cook", "toast", "brew", "run ", "microwave")
        if any(term in lower for term in process_terms):
            atomic_type = "PROCESS"
            mode = "process"
        elif lower.startswith("watch ") or lower.startswith("sit "):
            atomic_type = "INTERACTION"
            mode = "process"
        elif target is not None:
            atomic_type = "TRANSFER"
            mode = "state"
        elif lower.startswith(("turn ", "open ")):
            atomic_type = "STATE_CHANGE"
            mode = "state"
        else:
            atomic_type = "PROCESS"
            mode = "process"
        atomics.append(
            {
                "id": f"A{len(atomics) + 1}",
                "type": atomic_type,
                "focal_object": focal,
                "source": None,
                "target": target,
                "completion_mode": mode,
                "semantic_goal": instruction,
                "depends_on": [],
            }
        )
    return {"atomic_tasks": atomics, "terminal_constraints": terminals}
