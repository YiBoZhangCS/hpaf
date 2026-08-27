from __future__ import annotations

import os
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional

import httpx
from openai import OpenAI


class LLMWallClockTimeout(BaseException):
    """Deadline exception that third-party SDK ``except Exception`` cannot swallow."""


@dataclass
class LLMCall:
    provider: str
    model: str
    api_interface: str
    prompt: str
    instructions: Optional[str]
    raw_output: str
    output_text: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    latency_s: float
    temperature: float
    max_tokens: int
    seed: Optional[int]
    stop: Optional[list[str]]
    frequency_penalty: Optional[float]
    response_id: Optional[str]
    wall_clock_timeout_s: float
    extra_body: Optional[Dict[str, Any]]
    error_type: str
    error_message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ModernLLMClient:
    """Small metered adapter around an OpenAI-compatible modern API.

    The current HPAF client already uses ``responses.create``. This benchmark
    follows that implementation instead of reviving the legacy Completion API.
    Responses has no server-side ``stop`` or ``frequency_penalty`` parameters;
    stop strings are therefore applied to returned text and that compatibility
    deviation is recorded in every call.
    """

    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 180.0,
        wall_clock_timeout_s: float = 240.0,
        extra_body: Optional[Dict[str, Any]] = None,
    ):
        self.provider = provider
        self.base_url = base_url
        self.model = model
        self.api_interface = "responses.create"
        self.wall_clock_timeout_s = wall_clock_timeout_s
        self.extra_body = extra_body
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_s,
            max_retries=2,
            http_client=httpx.Client(timeout=timeout_s, trust_env=False),
        )
        self.calls: list[LLMCall] = []

    @classmethod
    def from_env_spec(cls, spec: Dict[str, Any]) -> "ModernLLMClient":
        key_env = spec["api_key_env"]
        model_env = spec["model_env"]
        api_key = os.getenv(key_env)
        model = os.getenv(model_env) or spec.get("default_model")
        if not api_key:
            raise RuntimeError(f"Required API-key environment variable {key_env} is empty")
        if not model:
            raise RuntimeError(f"Required model environment variable {model_env} is empty")
        base_url = spec.get("base_url")
        if not base_url:
            base_url_env = spec.get("base_url_env")
            base_url = os.getenv(base_url_env) if base_url_env else None
        if not base_url:
            raise RuntimeError("LLM base URL is empty")
        return cls(
            provider=str(spec["provider"]),
            base_url=str(base_url),
            api_key=api_key,
            model=str(model),
            timeout_s=float(spec.get("timeout_s", 180.0)),
            wall_clock_timeout_s=float(spec.get("wall_clock_timeout_s", 240.0)),
            extra_body=spec.get("extra_body"),
        )

    @contextmanager
    def _wall_clock_limit(self):
        """Bound total synchronous request time, including streamed keepalives.

        ``httpx`` read timeouts measure inactivity and can therefore be kept
        alive indefinitely by a backend that emits transport events without a
        completed response. Benchmark calls run on the main thread, where a
        POSIX interval timer gives the request a reproducible total deadline.
        """

        if (
            self.wall_clock_timeout_s <= 0
            or threading.current_thread() is not threading.main_thread()
        ):
            yield
            return

        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)

        def raise_timeout(_signum, _frame):
            raise LLMWallClockTimeout(
                f"LLM call exceeded {self.wall_clock_timeout_s:.0f}s wall-clock limit"
            )

        signal.signal(signal.SIGALRM, raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, self.wall_clock_timeout_s)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0:
                signal.setitimer(signal.ITIMER_REAL, *previous_timer)

    @staticmethod
    def _extract_text(response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []) or []:
                if getattr(content, "type", None) == "output_text":
                    return str(content.text)
        raise RuntimeError("Responses API returned no output_text")

    @staticmethod
    def _usage_value(usage: Any, names: Iterable[str]) -> Optional[int]:
        if usage is None:
            return None
        for name in names:
            value = getattr(usage, name, None)
            if value is not None:
                return int(value)
            if isinstance(usage, dict) and usage.get(name) is not None:
                return int(usage[name])
        return None

    @staticmethod
    def _apply_stop(text: str, stop: Optional[list[str]]) -> str:
        if not stop:
            return text
        positions = [text.find(marker) for marker in stop if text.find(marker) >= 0]
        return text[: min(positions)] if positions else text

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        stop: Optional[list[str]] = None,
        frequency_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        instructions: Optional[str] = None,
    ) -> LLMCall:
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
                    instructions=instructions,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                    extra_body=self.extra_body,
                )
        except (LLMWallClockTimeout, Exception) as exc:
            latency_s = time.perf_counter() - started
            self.calls.append(
                LLMCall(
                    provider=self.provider,
                    model=self.model,
                    api_interface=self.api_interface,
                    prompt=prompt,
                    instructions=instructions,
                    raw_output="",
                    output_text="",
                    prompt_tokens=None,
                    completion_tokens=None,
                    latency_s=latency_s,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=seed,
                    stop=stop,
                    frequency_penalty=frequency_penalty,
                    response_id=None,
                    wall_clock_timeout_s=self.wall_clock_timeout_s,
                    extra_body=self.extra_body,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            if isinstance(exc, LLMWallClockTimeout):
                raise TimeoutError(str(exc)) from None
            raise
        latency_s = time.perf_counter() - started
        try:
            raw_output = self._extract_text(response).strip()
        except Exception as exc:
            usage = getattr(response, "usage", None)
            self.calls.append(
                LLMCall(
                    provider=self.provider,
                    model=self.model,
                    api_interface=self.api_interface,
                    prompt=prompt,
                    instructions=instructions,
                    raw_output=str(response),
                    output_text="",
                    prompt_tokens=self._usage_value(
                        usage, ["input_tokens", "prompt_tokens"]
                    ),
                    completion_tokens=self._usage_value(
                        usage, ["output_tokens", "completion_tokens"]
                    ),
                    latency_s=latency_s,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=seed,
                    stop=stop,
                    frequency_penalty=frequency_penalty,
                    response_id=getattr(response, "id", None),
                    wall_clock_timeout_s=self.wall_clock_timeout_s,
                    extra_body=self.extra_body,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )
            raise
        output_text = self._apply_stop(raw_output, stop).strip()
        usage = getattr(response, "usage", None)
        call = LLMCall(
            provider=self.provider,
            model=self.model,
            api_interface=self.api_interface,
            prompt=prompt,
            instructions=instructions,
            raw_output=raw_output,
            output_text=output_text,
            prompt_tokens=self._usage_value(usage, ["input_tokens", "prompt_tokens"]),
            completion_tokens=self._usage_value(usage, ["output_tokens", "completion_tokens"]),
            latency_s=latency_s,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            stop=stop,
            frequency_penalty=frequency_penalty,
            response_id=getattr(response, "id", None),
            wall_clock_timeout_s=self.wall_clock_timeout_s,
            extra_body=self.extra_body,
            error_type="",
            error_message="",
        )
        self.calls.append(call)
        return call
