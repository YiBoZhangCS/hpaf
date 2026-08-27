from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .llm_client import ModernLLMClient
from .virtualhome import EvolvingGraphExecutor, local_symbolic_state


CURRENT_STATE_FEWSHOT = """You see: microwave is OFF and CLOSED, lightswitch is ON, cereal, bookshelf, book is CLOSED, bookshelf ON floor, microwave ON kitchencounterdrawer, salmon ON microwave, book INSIDE bookshelf, dishbowl INSIDE bookshelf, clothespile INSIDE bookshelf, bananas INSIDE bookshelf, box ON bookshelf, book ON kitchentable, dishbowl ON bookshelf, condimentshaker INSIDE bookshelf, box INSIDE bookshelf, character HOLD_RH book, book ON rug, cereal ON wallshelf, plate INSIDE microwave, condimentbottle INSIDE bookshelf, microwave ON kitchencounter, paper INSIDE bookshelf

assert('close' to 'mug' )
False
assert('close' to 'microwave' )
True
assert('book' is 'closed' )
True
assert('lightswitch' is 'OFF')
False
assert('book' in 'bookshelf')
True
assert('book' in 'hands')
True
assert('cereal' on 'bookshelf')
False"""

ALLOWED_ACTIONS = {
    "turnright",
    "turnleft",
    "walkforward",
    "walktowards",
    "walk",
    "run",
    "grab",
    "switchon",
    "switchoff",
    "open",
    "close",
    "lookat",
    "sit",
    "standup",
    "find",
    "turnto",
    "drink",
    "pointat",
    "watch",
    "putin",
    "putback",
}


@dataclass
class ProgramTraceEvent:
    line: str
    event: str
    success: bool
    detail: str = ""
    subgoal: str = "0"
    compiled_action: Optional[str] = None


class ProgramExecutor:
    """ProgPrompt-compatible interpreter backed by Evolving Graph."""

    def __init__(
        self,
        initial_graph: Dict[str, Any],
        *,
        llm_client: Optional[ModernLLMClient],
        unity_comm=None,
        seed: int = 0,
        state_check_max_tokens: int = 128,
    ):
        self.graph_executor = EvolvingGraphExecutor(initial_graph)
        self.llm_client = llm_client
        self.unity_comm = unity_comm
        self.random = random.Random(seed)
        self.state_check_max_tokens = state_check_max_tokens
        self.found_id: Optional[int] = None
        self.local_state = local_symbolic_state(initial_graph, include_inside=False)
        self.events: List[ProgramTraceEvent] = []
        self.error_events: List[Dict[str, str]] = []

    @staticmethod
    def clean_program(program: str) -> str:
        text = (program or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("def "):
            lines = lines[1:]
        return "\n".join(line[1:] if line.startswith("\t") else line for line in lines)

    def _class_ids(self, class_name: str) -> List[int]:
        return [
            node["id"]
            for node in self.graph_executor.graph["nodes"]
            if node["class_name"] == class_name
        ]

    def _held_ids(self) -> set[int]:
        agent_ids = {
            node["id"]
            for node in self.graph_executor.graph["nodes"]
            if node["class_name"] == "character"
        }
        return {
            edge["to_id"]
            for edge in self.graph_executor.graph["edges"]
            if edge["from_id"] in agent_ids and "HOLD" in edge["relation_type"]
        }

    def _select_id(self, ids: List[int]) -> int:
        if len(ids) == 1:
            return ids[0]
        if self.found_id in ids:
            return int(self.found_id)
        return self.random.choice(ids)

    def _compile_action(self, line: str) -> tuple[Optional[str], Optional[str]]:
        truncated = line.split(")")[0]
        tokens = re.findall(r"\b[a-z]+", truncated)
        if not tokens:
            return None, "bad action"
        action = tokens[0]
        if action not in ALLOWED_ACTIONS:
            return None, f"hallucinated action: {action}"

        if len(tokens) == 3 and "put" in action:
            held_ids = self._held_ids()
            first_ids = [item for item in self._class_ids(tokens[1]) if item in held_ids]
            second_ids = self._class_ids(tokens[2])
            if not first_ids:
                return None, f"object not in hand: {tokens[1]}"
            if not second_ids:
                return None, f"object not found: {tokens[2]}"
            first_id = self._select_id(first_ids)
            second_id = self._select_id(second_ids)
            return (
                f"<char0> [{action}] <{tokens[1]}> ({first_id}) "
                f"<{tokens[2]}> ({second_id})",
                None,
            )

        if len(tokens) == 2 and action not in {"find", "walk"}:
            ids = self._class_ids(tokens[1])
            if not ids:
                return None, f"object not found: {tokens[1]}"
            selected = self._select_id(ids)
            return f"<char0> [{action}] <{tokens[1]}> ({selected})", None

        if len(tokens) == 2:
            ids = self._class_ids(tokens[1])
            if not ids:
                return None, f"object not found: {tokens[1]}"
            self.found_id = self.random.choice(ids)
            return f"<char0> [{action}] <{tokens[1]}> ({self.found_id})", None

        if len(tokens) == 1:
            return f"<char0> [{action}]", None
        return None, "bad action"

    def _state_check(self, assertion: str) -> str:
        if self.llm_client is None:
            raise RuntimeError("Assertion execution requires the shared LLM client")
        assert_objects = re.findall(r"\b[a-z]+", assertion)[1::2]
        state_parts = [part.strip() for part in self.local_state.split(",")]
        filtered_state = "You see: " + ", ".join(
            part for part in state_parts if any(obj in part for obj in assert_objects)
        )
        prompt = f"{CURRENT_STATE_FEWSHOT}\n\n{filtered_state}\n\n{assertion}\n"
        # Legacy ProgPrompt used max_tokens=2. Modern reasoning-capable Responses
        # accounts reasoning inside the output budget and needs enough room to
        # expose the one-word answer.
        call = self.llm_client.generate(
            prompt,
            max_tokens=self.state_check_max_tokens,
            temperature=0.0,
            stop=["\n"],
            frequency_penalty=0.0,
            seed=None,
        )
        return call.output_text.strip()

    @staticmethod
    def _error_type(detail: str) -> str:
        lowered = detail.lower()
        if "hallucinated action" in lowered or "bad action" in lowered:
            return "hallucinated_action"
        if "not found" in lowered:
            return "nonexistent_object"
        if "not in hand" in lowered or "when executing" in lowered:
            return "precondition_failure"
        if "parse" in lowered or "syntax" in lowered:
            return "parse_failure"
        return "execution_error"

    def _record_failed_action(self, line: str, detail: str, subgoal: str) -> None:
        self.graph_executor.record_failed_attempt(line, detail)
        error_type = self._error_type(detail)
        self.error_events.append({"error_type": error_type, "message": detail, "line": line})
        self.events.append(ProgramTraceEvent(line, "action", False, detail, subgoal))

    def execute(self, program: str) -> None:
        cleaned = self.clean_program(program)
        subgoal = "0"
        steps_in_subgoal = 0
        last_assert: Optional[str] = None
        check_state = ""

        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line or line in {"```", "```python"}:
                continue
            if line.startswith("def ") or line.startswith("return"):
                continue
            if "#" in line:
                subgoal = line.split("#", 1)[1].strip() or subgoal
                steps_in_subgoal = 0
                self.events.append(ProgramTraceEvent(line, "comment", True, subgoal=subgoal))
                continue
            if steps_in_subgoal > 10:
                self.events.append(
                    ProgramTraceEvent(line, "step_cap", False, "official per-subgoal cap", subgoal)
                )
                continue
            if "grab('wallphone')" in line:
                self.events.append(
                    ProgramTraceEvent(line, "official_skip", True, "wallphone special case", subgoal)
                )
                continue
            if "assert" in line:
                last_assert = line
                try:
                    check_state = self._state_check(line)
                    self.events.append(
                        ProgramTraceEvent(line, "assert", True, check_state, subgoal)
                    )
                except Exception as exc:
                    detail = f"state check failed: {exc}"
                    self.error_events.append(
                        {"error_type": "llm_error", "message": detail, "line": line}
                    )
                    self.events.append(ProgramTraceEvent(line, "assert", False, detail, subgoal))
                    check_state = "False"
                continue

            action_line = line
            if last_assert is not None:
                if "true" in check_state.lower() and "else:" in action_line:
                    self.events.append(
                        ProgramTraceEvent(action_line, "recovery_skip", True, check_state, subgoal)
                    )
                    continue
                if "false" in check_state.lower() and "else:" in action_line:
                    action_line = action_line.split(": ", 1)[-1].strip()
                elif "false" in check_state.lower():
                    # Preserve the released interpreter's extra state query on
                    # the next non-recovery action after a false assertion.
                    try:
                        check_state = self._state_check(action_line)
                    except Exception:
                        check_state = "False"

            compiled, compile_error = self._compile_action(action_line)
            if compile_error or compiled is None:
                self._record_failed_action(action_line, compile_error or "bad action", subgoal)
                continue

            trace = self.graph_executor.execute_ground_truth_action(
                compiled,
                unity=self.unity_comm,
            )
            steps_in_subgoal += 1
            if trace.success:
                self.local_state = local_symbolic_state(
                    self.graph_executor.graph, include_inside=True
                )
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

    @property
    def final_graph(self) -> Dict[str, Any]:
        return self.graph_executor.final_graph()

    @property
    def exec_ratio(self) -> float:
        return self.graph_executor.exec_ratio

    @property
    def program_length(self) -> int:
        return self.graph_executor.total_steps

    @property
    def compiled_actions(self) -> List[str]:
        return [event.compiled_action for event in self.events if event.compiled_action]
