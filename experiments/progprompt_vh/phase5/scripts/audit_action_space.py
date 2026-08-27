#!/usr/bin/env python3
"""Source audit and freeze the Phase-5 graph-compatible primitive action set."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Set


ROOT = Path(__file__).resolve().parents[4]
PHASE5 = ROOT / "experiments/progprompt_vh/phase5"
PLANNERS = ROOT / "experiments/progprompt_vh/methods/planners.py"
SCRIPTS = ROOT / "third_party/virtualhome/src/virtualhome/simulation/evolving_graph/scripts.py"
EXECUTION = ROOT / "third_party/virtualhome/src/virtualhome/simulation/evolving_graph/execution.py"
PHASE4_RAW = ROOT / "experiments/progprompt_vh/results/raw_runs.jsonl"
OUT_JSON = PHASE5 / "data/graph_supported_actions.json"
OUT_MD = PHASE5 / "ACTION_SPACE_AUDIT.md"


def official_actions() -> List[str]:
    module = ast.parse(PLANNERS.read_text(encoding="utf-8"))
    value = None
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ACTION_IMPORT"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            break
    if not isinstance(value, str):
        raise RuntimeError("Could not extract Phase-4 official ACTION_IMPORT")
    payload = value.split("import", 1)[1]
    return [item.strip().split()[0] for item in payload.split(",")]


def enum_actions() -> List[str]:
    module = ast.parse(SCRIPTS.read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == "Action":
            names = []
            for item in node.body:
                if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name):
                    names.append(item.targets[0].id.lower())
            return names
    raise RuntimeError("Could not extract Action enum")


def dispatched_actions() -> List[str]:
    text = EXECUTION.read_text(encoding="utf-8")
    match = re.search(r"_action_executors\s*=\s*\{(.*?)\n\s*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("Could not extract ScriptExecutor dispatch table")
    return sorted(set(item.lower() for item in re.findall(r"Action\.([A-Z_]+)\s*:", match.group(1))))


def observed_phase4_violations(supported: Set[str]) -> Dict[str, List[str]]:
    affected: Dict[str, set] = {}
    with PHASE4_RAW.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            for error in record.get("errors") or []:
                source = str(error.get("line", ""))
                match = re.match(r"\s*([a-z]+)\s*\(", source.lower())
                if not match:
                    continue
                action = match.group(1)
                if action != "else" and action not in supported:
                    affected.setdefault(action, set()).add(
                        f'{record["task"]} / {record["method"]}'
                    )
    return {name: sorted(values) for name, values in sorted(affected.items())}


def main() -> None:
    official = official_actions()
    enum = enum_actions()
    dispatch = dispatched_actions()
    supported = sorted(set(official) & set(enum) & set(dispatch))
    expected = [
        "close", "drink", "find", "grab", "lookat", "open", "pointat",
        "putback", "putin", "run", "sit", "standup", "switchoff",
        "switchon", "turnto", "walk", "watch",
    ]
    if supported != expected:
        raise RuntimeError(f"Unexpected audited intersection: {supported}")

    payload = {
        "name": "GRAPH_SUPPORTED_ACTIONS",
        "derivation": "intersection(ProgPrompt official import, Evolving Graph Action enum, ScriptExecutor dispatch)",
        "actions": supported,
        "arity": {
            "close": 1, "drink": 1, "find": 1, "grab": 1, "lookat": 1,
            "open": 1, "pointat": 1, "putback": 2, "putin": 2, "run": 1,
            "sit": 1, "standup": 0, "switchoff": 1, "switchon": 1,
            "turnto": 1, "walk": 1, "watch": 1,
        },
        "source_commits": {
            "progprompt_vh": "56e65510747dff809c1b0bac9318508da9d9a2d4",
            "virtualhome": "f84ee28a75b23318ee1bf652862b1c993269cd06",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(OUT_JSON.read_bytes()).hexdigest()
    violations = observed_phase4_violations(set(supported))
    official_only = sorted(set(official) - set(supported))
    graph_only = sorted(set(dispatch) - set(official))

    lines = [
        "# Phase-5 Action-Space Audit",
        "",
        "Phase 5 freezes one primitive API for all three methods. It is the exact "
        "intersection of the released ProgPrompt import, the pinned VirtualHome "
        "Evolving Graph `Action` enum, and `ScriptExecutor._action_executors`.",
        "",
        "## Source comparison",
        "",
        f"- ProgPrompt official import ({len(official)}): `{', '.join(official)}`",
        f"- Evolving Graph enum ({len(enum)}): `{', '.join(sorted(enum))}`",
        f"- Evolving Graph dispatch ({len(dispatch)}): `{', '.join(dispatch)}`",
        f"- Frozen intersection ({len(supported)}): `{', '.join(supported)}`",
        "",
        "Official-import actions rejected by the graph executor: "
        f"`{', '.join(official_only)}`. Graph-only actions withheld from HPAF for "
        f"baseline fairness: `{', '.join(graph_only)}`.",
        "",
        "## Phase-4 observed violations",
        "",
        "| Action | Affected Phase-4 task/method records |",
        "|---|---|",
    ]
    for action, pairs in violations.items():
        lines.append(f"| `{action}` | {'; '.join(pairs)} |")
    lines += [
        "",
        "The `else:` recovery parsing failures are not primitive-action violations "
        "and are reported separately in the failure audit.",
        "",
        "## Representative parser/dispatch check",
        "",
        "Static source inspection is decisive at this pinned commit: an action must "
        "both parse to an `Action` member and have a dispatch entry. The intersection "
        "therefore excludes `turnright`, `turnleft`, `walkforward`, and `walktowards`; "
        "Phase-4 traces independently confirm `WALKTOWARDS` reaches `UnknownExecutor`.",
        "No planning API was called for this audit.",
        "",
        "## Frozen artifact",
        "",
        f"- File: `{OUT_JSON.relative_to(ROOT)}`",
        f"- SHA-256: `{digest}`",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"graph_supported_actions={len(supported)}")
    print(f"action_set_sha256={digest}")
    print(f"wrote={OUT_JSON.relative_to(ROOT)}")
    print(f"wrote={OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

