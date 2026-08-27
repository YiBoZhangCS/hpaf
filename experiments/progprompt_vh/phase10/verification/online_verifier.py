"""Phase-10 process-aware online verifier, blind to benchmark gold.

The Phase-8 behavior is retained, but both verbose success and failure schemas
state the allowed ``failure_stage`` values explicitly. This removes an observed
prompt/schema ambiguity without weakening output validation.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import parse_json_object


STAGES = {"perception", "alignment", "interaction", "process", "verification", "none"}


def _failure(error: str) -> Dict[str, Any]:
    return {
        "done": False,
        "failure_stage": "verification",
        "regeneration_hint": error,
    }


def verifier_schema(*, compact: bool) -> str:
    if compact:
        return (
            '{"done":true} OR, only on failure, '
            '{"done":false,"failure_stage":"perception|alignment|interaction|process|verification",'
            '"regeneration_hint":"short actionable hint"}'
        )
    return (
        '{"done":true,"reason":"short evidence","failure_stage":"none",'
        '"regeneration_hint":""} OR '
        '{"done":false,"reason":"short evidence","failure_stage":'
        '"perception|alignment|interaction|process|verification",'
        '"regeneration_hint":"short actionable hint"}'
    )


def verify_task_completion(
    client: ModernLLMClient,
    *,
    atomic_task: Dict[str, Any],
    current_symbolic_observation: str,
    relevant_objects: List[str],
    execution_context: Dict[str, Any],
    llm_config: Dict[str, Any],
    compact: bool,
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the online HPAF verifier for one current VirtualHome task.
Judge completion only from the current symbolic observation and current-attempt
trace/errors. Never read or infer an external evaluator, GT program, final graph,
future atomic, or score. Do not treat a generated action as successful unless the
trace says it succeeded. Persistent relations/states are evidence for state mode.

For `completion_mode=process`, require evidence that the requested process or
interaction completed. Merely activating/starting it is not completion. When the
operation reasonably requires a closed lifecycle, require its terminal operation;
for an interaction event, require a successful matching interaction. Do not invent
unsupported time or hidden effects. If mode is `infer`, classify from the task text.

Return strict JSON only: {verifier_schema(compact=compact)}
On failure, `failure_stage` must be exactly one of the five displayed enum values;
put any action-specific detail only in `reason` or `regeneration_hint`.

CURRENT TASK CONTRACT: {json.dumps(atomic_task, ensure_ascii=False)}
CURRENT STATE: {current_symbolic_observation}
RELEVANT OBJECT CLASSES: {json.dumps(relevant_objects)}
CURRENT ATTEMPT CONTEXT: {json.dumps(execution_context, ensure_ascii=False)}
"""
    max_tokens = int(
        llm_config["verifier_max_tokens"] if compact else llm_config["max_tokens"]
    )
    call = client.generate(
        prompt,
        max_tokens=max_tokens,
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
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
        if compact and set(parsed) != {"done"}:
            error = "successful compact verifier output must contain only done"
            return _failure(error), call, error
        if not compact:
            reason = parsed.get("reason")
            stage = str(parsed.get("failure_stage", "")).lower()
            hint = parsed.get("regeneration_hint")
            if not isinstance(reason, str) or stage != "none" or not isinstance(hint, str):
                error = "verbose verifier success fields violate schema"
                return _failure(error), call, error
        return {"done": True}, call, None

    stage = str(parsed.get("failure_stage", "")).lower()
    hint = parsed.get("regeneration_hint")
    if stage not in STAGES - {"none"} or not isinstance(hint, str) or not hint.strip():
        error = "verifier failure fields violate schema"
        return _failure(error), call, error
    return {
        "done": False,
        "failure_stage": stage,
        "regeneration_hint": hint.strip(),
    }, call, None
