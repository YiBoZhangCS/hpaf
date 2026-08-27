"""ARK Responses compatibility client for binary ProgPrompt assertions."""

from __future__ import annotations

import json
import time
from typing import Optional

from experiments.progprompt_vh.adapters.llm_client import (
    LLMCall,
    LLMWallClockTimeout,
    ModernLLMClient,
)


BINARY_ASSERTION_FORMAT = {
    "type": "json_schema",
    "name": "binary_assertion",
    "strict": True,
    "schema": {"type": "string", "enum": ["True", "False"]},
}


class Phase8LLMClient(ModernLLMClient):
    """Keep normal generation unchanged and constrain assertion transport."""

    def generate_binary_assertion(self, prompt: str, *, max_tokens: int = 3) -> LLMCall:
        started = time.perf_counter()
        try:
            with self._wall_clock_limit():
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": prompt}],
                        }
                    ],
                    max_output_tokens=max_tokens,
                    temperature=0.0,
                    text={"format": BINARY_ASSERTION_FORMAT},
                    extra_body=self.extra_body,
                )
        except (LLMWallClockTimeout, Exception) as exc:
            latency_s = time.perf_counter() - started
            call = LLMCall(
                provider=self.provider,
                model=self.model,
                api_interface=self.api_interface,
                prompt=prompt,
                instructions=None,
                raw_output="",
                output_text="",
                prompt_tokens=None,
                completion_tokens=None,
                latency_s=latency_s,
                temperature=0.0,
                max_tokens=max_tokens,
                seed=None,
                stop=None,
                frequency_penalty=0.0,
                response_id=None,
                wall_clock_timeout_s=self.wall_clock_timeout_s,
                extra_body=self.extra_body,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            self.calls.append(call)
            if isinstance(exc, LLMWallClockTimeout):
                raise TimeoutError(str(exc)) from None
            raise

        latency_s = time.perf_counter() - started
        raw_output = self._extract_text(response).strip()
        decoded: Optional[str] = None
        try:
            candidate = json.loads(raw_output)
            if isinstance(candidate, str):
                decoded = candidate
        except json.JSONDecodeError:
            pass
        output_text = decoded if decoded is not None else raw_output
        usage = getattr(response, "usage", None)
        call = LLMCall(
            provider=self.provider,
            model=self.model,
            api_interface=self.api_interface,
            prompt=prompt,
            instructions=None,
            raw_output=raw_output,
            output_text=output_text.strip(),
            prompt_tokens=self._usage_value(usage, ["input_tokens", "prompt_tokens"]),
            completion_tokens=self._usage_value(usage, ["output_tokens", "completion_tokens"]),
            latency_s=latency_s,
            temperature=0.0,
            max_tokens=max_tokens,
            seed=None,
            stop=None,
            frequency_penalty=0.0,
            response_id=getattr(response, "id", None),
            wall_clock_timeout_s=self.wall_clock_timeout_s,
            extra_body=self.extra_body,
            error_type="",
            error_message="",
        )
        self.calls.append(call)
        return call

