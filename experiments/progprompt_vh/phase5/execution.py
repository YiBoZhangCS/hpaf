"""Shared graph-compatible Phase-5 program interpreter."""

from __future__ import annotations

import copy
import random
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from experiments.progprompt_vh.adapters.llm_client import ModernLLMClient
from experiments.progprompt_vh.adapters.program_executor import CURRENT_STATE_FEWSHOT
from experiments.progprompt_vh.adapters.virtualhome import (
    EvolvingGraphExecutor,
    add_additional_obj_states,
    local_symbolic_state,
)


@dataclass
class ProgramTraceEvent:
    line: str
    event: str
    success: bool
    detail: str = ""
    subgoal: str = "0"
    compiled_action: Optional[str] = None


def symbolic_state_snapshot(graph: Dict[str, Any]) -> str:
    """One shared compact state representation for Flat and Hierarchical."""
    agents = [node for node in graph["nodes"] if node["class_name"] == "character"]
    if not agents:
        return local_symbolic_state(graph, include_inside=True)
    agent = agents[0]
    class_by_id = {node["id"]: node["class_name"] for node in graph["nodes"]}
    rooms = [
        class_by_id.get(edge["to_id"], str(edge["to_id"]))
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and edge["relation_type"] == "INSIDE"
    ]
    held = [
        class_by_id.get(edge["to_id"], str(edge["to_id"]))
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and "HOLD" in edge["relation_type"]
    ]
    header = (
        f"Character room={rooms[0] if rooms else 'unknown'}; "
        f"states={sorted(agent.get('states', []))}; holds={sorted(held)}."
    )
    nearby_ids = {
        edge["to_id"]
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and edge["relation_type"] == "CLOSE"
    }
    nearby_ids.update(
        edge["from_id"]
        for edge in graph["edges"]
        if edge["to_id"] == agent["id"] and edge["relation_type"] == "CLOSE"
    )
    nearby_ids.update(
        edge["to_id"]
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and "HOLD" in edge["relation_type"]
    )
    room_ids = {
        node["id"] for node in graph["nodes"] if node.get("category") == "Rooms"
    }
    nearby_ids.difference_update(room_ids)
    connected_relations = {
        f'{class_by_id.get(edge["from_id"], edge["from_id"])} '
        f'{edge["relation_type"]} '
        f'{class_by_id.get(edge["to_id"], edge["to_id"])}'
        for edge in graph["edges"]
        if edge["relation_type"] in {"INSIDE", "ON"}
        and edge["to_id"] in nearby_ids
        and class_by_id.get(edge["from_id"]) != "character"
    }
    nearby = local_symbolic_state(graph, include_inside=True).strip()
    connected = "; ".join(sorted(connected_relations)) or "none"
    return (
        f"{header} Nearby visible graph: {nearby or 'none.'} "
        f"One-hop INSIDE/ON relations connected to nearby objects: {connected}."
    )


class GraphProgramExecutor:
    """Execute all three methods against one frozen primitive-action set."""

    def __init__(
        self,
        initial_graph: Dict[str, Any],
        *,
        actions_payload: Dict[str, Any],
        llm_client: Optional[ModernLLMClient],
        unity_comm=None,
        seed: int = 0,
        state_check_max_tokens: int = 600,
    ):
        self.graph_executor = EvolvingGraphExecutor(initial_graph)
        self.allowed_actions = set(actions_payload["actions"])
        self.arity = {key: int(value) for key, value in actions_payload["arity"].items()}
        if self.allowed_actions != set(self.arity):
            raise ValueError("Action names and arity map differ")
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
        graph = self.graph_executor.graph
        agent_ids = {
            node["id"] for node in graph["nodes"] if node["class_name"] == "character"
        }
        close_ids = {
            edge["to_id"]
            for edge in graph["edges"]
            if edge["from_id"] in agent_ids and edge["relation_type"] == "CLOSE"
        }
        close_candidates = [item for item in ids if item in close_ids]
        if close_candidates:
            return self.random.choice(close_candidates)
        current_rooms = {
            edge["to_id"]
            for edge in graph["edges"]
            if edge["from_id"] in agent_ids and edge["relation_type"] == "INSIDE"
        }
        same_room = {
            edge["from_id"]
            for edge in graph["edges"]
            if edge["relation_type"] == "INSIDE" and edge["to_id"] in current_rooms
        }
        same_room_candidates = [item for item in ids if item in same_room]
        if same_room_candidates:
            return self.random.choice(same_room_candidates)
        return self.random.choice(ids)

    def _compile_action(self, line: str) -> tuple[Optional[str], Optional[str]]:
        call = re.fullmatch(r"\s*([a-z]+)\s*\((.*)\)\s*", line.lower())
        if not call:
            return None, "bad action syntax"
        action, arguments_text = call.groups()
        if action not in self.allowed_actions:
            return None, f"unsupported action: {action}"
        arguments = re.findall(r"['\"]([a-z0-9_]+)['\"]", arguments_text)
        if len(arguments) != self.arity[action]:
            return None, f"bad arity for {action}: expected {self.arity[action]}, got {len(arguments)}"

        if self.arity[action] == 0:
            return f"<char0> [{action}]", None
        if self.arity[action] == 2:
            held_ids = self._held_ids()
            source_ids = [item for item in self._class_ids(arguments[0]) if item in held_ids]
            target_ids = self._class_ids(arguments[1])
            if not source_ids:
                return None, f"object not in hand: {arguments[0]}"
            if not target_ids:
                return None, f"object not found: {arguments[1]}"
            source_id = self._select_id(source_ids)
            target_id = self._select_id(target_ids)
            return (
                f"<char0> [{action}] <{arguments[0]}> ({source_id}) "
                f"<{arguments[1]}> ({target_id})",
                None,
            )

        ids = self._class_ids(arguments[0])
        if not ids:
            return None, f"object not found: {arguments[0]}"
        if action in {"find", "walk", "run"}:
            self.found_id = self._select_id(ids)
            selected = self.found_id
        else:
            selected = self._select_id(ids)
        return f"<char0> [{action}] <{arguments[0]}> ({selected})", None

    def _state_check(self, assertion: str) -> str:
        if self.llm_client is None:
            raise RuntimeError("Assertion execution requires the shared LLM client")
        assert_objects = re.findall(r"\b[a-z]+", assertion)[1::2]
        state_parts = [part.strip() for part in self.local_state.split(",")]
        filtered = "You see: " + ", ".join(
            part for part in state_parts if any(obj in part for obj in assert_objects)
        )
        call = self.llm_client.generate(
            f"{CURRENT_STATE_FEWSHOT}\n\n{filtered}\n\n{assertion}\n",
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
        if "unsupported action" in lowered:
            return "unsupported_action"
        if "bad action" in lowered or "bad arity" in lowered:
            return "parse_failure"
        if "not found" in lowered:
            return "nonexistent_object"
        if "not in hand" in lowered or "when executing" in lowered:
            return "precondition_failure"
        return "execution_error"

    def _record_failed_action(self, line: str, detail: str, subgoal: str) -> None:
        self.graph_executor.record_failed_attempt(line, detail)
        self.error_events.append(
            {"error_type": self._error_type(detail), "message": detail, "line": line}
        )
        self.events.append(ProgramTraceEvent(line, "action", False, detail, subgoal))

    def _refresh_evaluator_augmentations(self) -> None:
        """Apply released HEATED/WASHED rules to a full evaluator-only snapshot.

        The pinned helper accepts an arbitrary graph but the released execution
        path passes only agent-visible nodes. That makes WASHED unreachable when
        faucet and sink contents are not simultaneously visible. Phase 5 keeps
        native Evolving Graph state clean and updates only the same persistent
        evaluator replacement map used by ``final_graph``.
        """
        snapshot = copy.deepcopy(self.graph_executor.graph)
        self.graph_executor.nodes_with_additional_states = add_additional_obj_states(
            snapshot,
            self.graph_executor.additional_state_ids,
            self.graph_executor.nodes_with_additional_states,
        )

    def execute(self, program: str) -> None:
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
                    assertion_result = "true" in answer.lower()
                    self.events.append(ProgramTraceEvent(line, "assert", True, answer, subgoal))
                except Exception as exc:
                    detail = f"state check failed: {exc}"
                    assertion_result = False
                    self.error_events.append(
                        {"error_type": "llm_error", "message": detail, "line": line}
                    )
                    self.events.append(ProgramTraceEvent(line, "assert", False, detail, subgoal))
                continue

            action_line = line
            if line.lower().startswith("else:"):
                if assertion_result is None:
                    self._record_failed_action(line, "recovery branch without preceding assertion", subgoal)
                    continue
                if assertion_result:
                    self.events.append(
                        ProgramTraceEvent(line, "recovery_skip", True, "assertion true", subgoal)
                    )
                    continue
                action_line = line.split(":", 1)[1].strip()
            else:
                assertion_result = None

            compiled, compile_error = self._compile_action(action_line)
            if compile_error or compiled is None:
                self._record_failed_action(action_line, compile_error or "bad action", subgoal)
                continue
            trace = self.graph_executor.execute_ground_truth_action(compiled, unity=self.unity_comm)
            steps_in_subgoal += 1
            if trace.success:
                self.local_state = local_symbolic_state(
                    self.graph_executor.graph, include_inside=True
                )
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

    def artifacts(self) -> Dict[str, Any]:
        return {
            "final_state": self.final_graph,
            "Exec": self.exec_ratio,
            "program_length": self.program_length,
            "compiled_virtualhome_actions": self.compiled_actions,
            "execution_trace": [asdict(event) for event in self.events],
            "graph_execution_trace": [asdict(item) for item in self.graph_executor.trace],
            "execution_errors": list(self.error_events),
        }
