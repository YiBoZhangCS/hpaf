"""ProgPrompt-compatible executor with the released binary assertion cap."""

from __future__ import annotations

from typing import Optional

from experiments.progprompt_vh.phase5.execution import GraphProgramExecutor, ProgramTraceEvent
from experiments.progprompt_vh.adapters.virtualhome import local_symbolic_state


class Phase7GraphProgramExecutor(GraphProgramExecutor):
    """Keep Phase-6 execution semantics, correcting only assertion handling."""

    ASSERTION_MAX_TOKENS = 2

    @staticmethod
    def parse_assertion_answer(value: str) -> Optional[bool]:
        normalized = (value or "").strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        return None

    def _state_check(self, assertion: str) -> str:
        if self.llm_client is None:
            raise RuntimeError("Assertion execution requires the shared LLM client")
        import re
        from experiments.progprompt_vh.adapters.program_executor import CURRENT_STATE_FEWSHOT

        assert_objects = re.findall(r"\b[a-z]+", assertion)[1::2]
        state_parts = [part.strip() for part in self.local_state.split(",")]
        filtered = "You see: " + ", ".join(
            part for part in state_parts if any(obj in part for obj in assert_objects)
        )
        call = self.llm_client.generate(
            f"{CURRENT_STATE_FEWSHOT}\n\n{filtered}\n\n{assertion}\n",
            max_tokens=self.ASSERTION_MAX_TOKENS,
            temperature=0.0,
            stop=["\n"],
            frequency_penalty=0.0,
            seed=None,
        )
        return call.output_text.strip()

    def execute(self, program: str) -> None:
        """Mirror the released adjacent-else interpreter with normalized answers."""
        import re

        cleaned = self.clean_program(program)
        subgoal = "0"
        steps_in_subgoal = 0
        assertion_result: Optional[bool] = None

        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line or line in {"```", "```python"}:
                continue
            if line.startswith("def ") or line.startswith("return"):
                continue
            if line.startswith("#"):
                subgoal = line.split("#", 1)[1].strip() or subgoal
                steps_in_subgoal = 0
                assertion_result = None
                self.events.append(ProgramTraceEvent(line, "comment", True, subgoal=subgoal))
                continue
            if steps_in_subgoal >= 10:
                self.events.append(
                    ProgramTraceEvent(line, "step_cap", False, "official per-subgoal cap", subgoal)
                )
                continue
            if "grab('wallphone')" in line:
                self.events.append(
                    ProgramTraceEvent(line, "official_skip", True, "wallphone special case", subgoal)
                )
                continue
            if line.startswith("assert"):
                try:
                    answer = self._state_check(line)
                    assertion_result = self.parse_assertion_answer(answer)
                    self.events.append(ProgramTraceEvent(line, "assert", True, answer, subgoal))
                except Exception as exc:
                    detail = f"state check failed: {exc}"
                    assertion_result = None
                    self.error_events.append(
                        {"error_type": "llm_error", "message": detail, "line": line}
                    )
                    self.events.append(ProgramTraceEvent(line, "assert", False, detail, subgoal))
                continue

            action_line = line
            if line.lower().startswith("else:"):
                if assertion_result is True:
                    self.events.append(
                        ProgramTraceEvent(line, "recovery_skip", True, "assertion true", subgoal)
                    )
                    continue
                if assertion_result is False:
                    action_line = line.split(":", 1)[1].strip()
                else:
                    # No truth is inferred from malformed/verbose output. The
                    # released two-token contract should make this path unreachable.
                    self.events.append(
                        ProgramTraceEvent(line, "recovery_unknown", False, "non-binary assertion output", subgoal)
                    )
                    self.graph_executor.record_failed_attempt(line, "non-binary assertion output")
                    self.error_events.append(
                        {"error_type": "assertion_parse_failure", "message": "non-binary assertion output", "line": line}
                    )
                    continue
            else:
                assertion_result = None

            compiled, compile_error = self._compile_action(action_line)
            if compile_error or compiled is None:
                self._record_failed_action(action_line, compile_error or "bad action", subgoal)
                continue
            trace = self.graph_executor.execute_ground_truth_action(compiled, unity=self.unity_comm)
            steps_in_subgoal += 1
            if trace.success:
                self.local_state = local_symbolic_state(self.graph_executor.graph, include_inside=True)
                self._refresh_evaluator_augmentations()
            else:
                detail = trace.error or "Evolving Graph precondition failure"
                self.error_events.append(
                    {"error_type": "precondition_failure", "message": detail, "line": action_line}
                )
            if trace.unity_success is False:
                self.error_events.append(
                    {
                        "error_type": "simulator_error",
                        "message": trace.unity_message,
                        "line": action_line,
                    }
                )
            self.events.append(
                ProgramTraceEvent(
                    line=action_line,
                    event="action",
                    success=trace.success,
                    detail=trace.error,
                    subgoal=subgoal,
                    compiled_action=compiled,
                )
            )
