"""Control-time LLM verifier; deliberately blind to benchmark goal files."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from experiments.progprompt_vh.adapters.llm_client import LLMCall, ModernLLMClient
from experiments.progprompt_vh.phase6.methods.common import parse_json_object


STAGES = {"perception", "alignment", "interaction", "verification", "none"}


def verify_task_completion(
    client: ModernLLMClient,
    *,
    task: str,
    current_symbolic_observation: str,
    relevant_objects: List[str],
    execution_context: Dict[str, Any],
    llm_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], LLMCall, Optional[str]]:
    prompt = f"""You are the online HPAF execution verifier for VirtualHome.

Judge whether the CURRENT TASK is complete using only the post-execution symbolic
observation and execution context below. Do not assume an action succeeded merely
because it was generated. Do not request future work outside the current task.
Persistent states/relations in the observation are evidence; a successful trace
may support that an event occurred, but never invent an unseen object or state.
Object-class names can refer to multiple simulator instances. For a singular or
otherwise unspecified object request, a successful interaction with one instance
plus a matching observed outcome is sufficient; another same-class instance that
retains an opposite state is not a contradiction. Require every instance only
when the task explicitly says all/every/both.

Return strict JSON only:
{{"done":true,"reason":"short explanation","failure_stage":"perception|alignment|interaction|verification|none","regeneration_hint":"short repair suggestion"}}

CURRENT TASK:
{task}

POST-EXECUTION SYMBOLIC OBSERVATION:
{current_symbolic_observation}

RELEVANT/AVAILABLE OBJECT CLASSES:
{json.dumps(relevant_objects)}

CURRENT EXECUTION CONTEXT:
{json.dumps(execution_context, ensure_ascii=False)}
"""
    call = client.generate(
        prompt,
        max_tokens=int(llm_config["max_tokens"]),
        temperature=float(llm_config["temperature"]),
        seed=llm_config.get("seed"),
        instructions="Return only the strict JSON object requested by the online verifier protocol.",
    )
    parsed, error = parse_json_object(call.output_text)
    if error or parsed is None:
        return {
            "done": False,
            "reason": error or "verifier output parse failure",
            "failure_stage": "verification",
            "regeneration_hint": "Re-establish the current task outcome and expose clear post-execution evidence.",
        }, call, error
    done = parsed.get("done")
    reason = parsed.get("reason")
    stage = str(parsed.get("failure_stage", "")).lower()
    hint = parsed.get("regeneration_hint")
    if not isinstance(done, bool) or not isinstance(reason, str) or stage not in STAGES or not isinstance(hint, str):
        error = "verifier JSON fields violate the frozen schema"
        return {
            "done": False,
            "reason": error,
            "failure_stage": "verification",
            "regeneration_hint": "Re-establish the current task outcome and expose clear post-execution evidence.",
        }, call, error
    return {
        "done": done,
        "reason": reason.strip(),
        "failure_stage": stage,
        "regeneration_hint": hint.strip(),
    }, call, None
