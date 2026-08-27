"""ProgPrompt-Compat executor with enum-constrained binary assertions."""

from __future__ import annotations

import re

from experiments.progprompt_vh.adapters.program_executor import CURRENT_STATE_FEWSHOT
from experiments.progprompt_vh.phase7.execution import Phase7GraphProgramExecutor


class Phase8GraphProgramExecutor(Phase7GraphProgramExecutor):
    """Preserve ProgPrompt control flow while constraining API output."""

    ASSERTION_MAX_TOKENS = 3

    def _state_check(self, assertion: str) -> str:
        if self.llm_client is None:
            raise RuntimeError("Assertion execution requires the shared LLM client")
        if not hasattr(self.llm_client, "generate_binary_assertion"):
            raise RuntimeError("Phase-8 binary assertion client is required")
        assert_objects = re.findall(r"\b[a-z]+", assertion)[1::2]
        state_parts = [part.strip() for part in self.local_state.split(",")]
        filtered = "You see: " + ", ".join(
            part for part in state_parts if any(obj in part for obj in assert_objects)
        )
        prompt = f"{CURRENT_STATE_FEWSHOT}\n\n{filtered}\n\n{assertion}\n"
        call = self.llm_client.generate_binary_assertion(
            prompt, max_tokens=self.ASSERTION_MAX_TOKENS
        )
        return call.output_text.strip()

