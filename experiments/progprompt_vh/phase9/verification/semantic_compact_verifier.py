"""Verifier prompt candidates that preserve Phase-8 evidence and completion rules."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import parse_json_object


STAGES = {"perception", "alignment", "interaction", "process", "verification"}


def _failure(error: str) -> Dict[str, Any]:
    return {"done": False, "failure_stage": "verification", "regeneration_hint": error}


def verify_task_completion(
    client: ModernLLMClient, *, atomic_task: Dict[str, Any],
    current_symbolic_observation: str, relevant_objects: List[str],
    execution_context: Dict[str, Any], llm_config: Dict[str, Any], compact: bool,
    compact_schema: bool = False,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    del compact
    schema = (
        '{"done":true} OR {"done":false,"failure_stage":"perception|alignment|interaction|process|verification","regeneration_hint":"actionable hint"}'
        if compact_schema
        else '{"done":true,"reason":"evidence","failure_stage":"none","regeneration_hint":""} OR the same fields with done=false and an actionable hint'
    )
    prompt = f"""HPAF online verifier for the current VirtualHome task. Judge only
current symbolic state and current-attempt trace/errors; no evaluator, GT, final
graph, future atomic, or score. An emitted action counts only when trace success is
true. Persistent state/relation proves state mode. For process mode require completed
process/interaction evidence, including a terminal operation for a closed lifecycle;
activation alone is insufficient. Infer mode from task text only when mode=infer.
JSON only: {schema}
TASK CONTRACT: {json.dumps(atomic_task, ensure_ascii=False)}
STATE: {current_symbolic_observation}
RELEVANT CLASSES: {json.dumps(relevant_objects)}
ATTEMPT: {json.dumps(execution_context, ensure_ascii=False)}"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["verifier_max_tokens"] if compact_schema else llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]), seed=llm_config.get("seed"),
        instructions="Return only the requested strict online-verifier JSON object.",
    )
    parsed, error = parse_json_object(call.output_text)
    if error or parsed is None:
        return _failure(error or "verifier output parse failure"), call, error
    done = parsed.get("done")
    if not isinstance(done, bool):
        error = "verifier done must be boolean"
        return _failure(error), call, error
    if done:
        if compact_schema and set(parsed) != {"done"}:
            error = "successful compact verifier output must contain only done"
            return _failure(error), call, error
        if not compact_schema:
            if (
                not isinstance(parsed.get("reason"), str)
                or str(parsed.get("failure_stage", "")).lower() != "none"
                or not isinstance(parsed.get("regeneration_hint"), str)
            ):
                error = "verbose verifier success fields violate schema"
                return _failure(error), call, error
        return {"done": True}, call, None
    stage = str(parsed.get("failure_stage", "")).lower()
    hint = parsed.get("regeneration_hint")
    if stage not in STAGES or not isinstance(hint, str) or not hint.strip():
        error = "verifier failure fields violate schema"
        return _failure(error), call, error
    return {"done": False, "failure_stage": stage, "regeneration_hint": hint.strip()}, call, None

