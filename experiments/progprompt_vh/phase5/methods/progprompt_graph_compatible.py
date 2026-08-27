"""ProgPrompt with unchanged examples and a frozen graph-compatible import."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.adapters.paths import PROGPROMPT_ROOT


def action_import(actions_payload: Dict[str, Any]) -> str:
    items = []
    for name in actions_payload["actions"]:
        arity = int(actions_payload["arity"][name])
        items.append(name + (" <obj>" * arity))
    return "from actions import " + ", ".join(items)


def build_prefix(
    objects: List[str], example_names: List[str], actions_payload: Dict[str, Any]
) -> str:
    train_path = PROGPROMPT_ROOT / "data/pythonic_plans/train_complete_plan_set.json"
    examples = json.loads(train_path.read_text(encoding="utf-8"))
    selected = [examples[name] for name in example_names]
    allowed = set(actions_payload["actions"])
    observed = {
        match.group(1).lower()
        for example in selected
        for match in re.finditer(r"(?m)^\s*(?:else:\s*)?([a-z]+)\s*\(", example)
        if match.group(1).lower() != "assert"
    }
    if not observed <= allowed:
        raise RuntimeError(
            f"Unchanged default example content uses actions outside frozen API: {sorted(observed - allowed)}"
        )
    prompt = f"{action_import(actions_payload)}\n\nobjects = {objects}"
    for example in selected:
        prompt += "\n\n" + example
    return prompt


def generate_progprompt_program(
    client: ModernLLMClient,
    *,
    task: str,
    objects: List[str],
    actions_payload: Dict[str, Any],
    prompt_config: Dict[str, Any],
) -> Tuple[str, LLMCall]:
    prefix = build_prefix(objects, prompt_config["prompt_examples"], actions_payload)
    function_header = f"def {'_'.join(task.split(' '))}():"
    prompt = f"{prefix}\n\n{function_header}\n\t"
    call = client.generate(
        prompt,
        max_tokens=int(prompt_config["max_tokens"]),
        temperature=float(prompt_config["temperature"]),
        stop=list(prompt_config.get("stop") or []),
        frequency_penalty=float(prompt_config.get("frequency_penalty", 0.0)),
        seed=None,
        instructions=(
            "Complete only the body of the final unfinished ProgPrompt action-DSL "
            "function in the supplied text. Output DSL body lines only: comments, "
            "available action calls, assertions, and indented else recovery calls. "
            "Do not discuss Python syntax, ask questions, use Markdown, repeat earlier "
            "functions, or emit a new def."
        ),
    )
    return call.output_text, call

