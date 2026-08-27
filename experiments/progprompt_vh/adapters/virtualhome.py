from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import PROGPROMPT_ROOT, VIRTUALHOME_SIMULATION


# The pinned VirtualHome package has broken absolute imports when installed as a
# modern package. ProgPrompt itself imports these modules by adding the
# simulation directory to sys.path, so the adapter intentionally does the same.
simulation_path = str(VIRTUALHOME_SIMULATION)
if simulation_path not in sys.path:
    sys.path.insert(0, simulation_path)

from evolving_graph import utils  # noqa: E402
from evolving_graph.environment import EnvironmentGraph  # noqa: E402
from evolving_graph.execution import ScriptExecutor  # noqa: E402
from evolving_graph.scripts import Script, parse_script_line  # noqa: E402
from unity_simulator.comm_unity import UnityCommunication  # noqa: E402

progprompt_scripts_path = str(PROGPROMPT_ROOT / "scripts")
if progprompt_scripts_path not in sys.path:
    sys.path.insert(0, progprompt_scripts_path)
from utils_aug_env import add_additional_obj_states, get_obj_ids_for_adding_states  # noqa: E402


@dataclass
class StepTrace:
    source_action: str
    parsed_action: Optional[str]
    success: bool
    error: str = ""
    unity_success: Optional[bool] = None
    unity_message: str = ""


class UnitySession:
    def __init__(self, executable: Path, port: int, no_graphics: bool = True):
        self.executable = Path(executable).resolve()
        self.port = str(port)
        self.no_graphics = no_graphics
        self.comm: Optional[UnityCommunication] = None

    def __enter__(self) -> "UnitySession":
        self.comm = UnityCommunication(
            file_name=str(self.executable),
            port=self.port,
            no_graphics=self.no_graphics,
            logging=False,
            timeout_wait=15,
        )
        if not self.comm.check_connection():
            raise RuntimeError("Unity connection check failed")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.comm is not None:
            self.comm.close()

    def reset_graph(self, scene: int = 0) -> Dict[str, Any]:
        if self.comm is None:
            raise RuntimeError("UnitySession is not active")
        if not self.comm.reset(scene):
            raise RuntimeError(f"Unity reset({scene}) failed")
        if not self.comm.add_character("Chars/Male2", initial_room="kitchen"):
            raise RuntimeError("Unity add_character failed")
        success, graph = self.comm.environment_graph()
        if not success:
            raise RuntimeError("Unity environment_graph failed")
        return graph


class EvolvingGraphExecutor:
    def __init__(self, initial_graph: Dict[str, Any]):
        self.initial_graph = copy.deepcopy(initial_graph)
        self.graph = copy.deepcopy(initial_graph)
        self.name_equivalence = utils.load_name_equivalence()
        self.executor = ScriptExecutor(EnvironmentGraph(self.graph), self.name_equivalence)
        self.trace: List[StepTrace] = []
        self.executable_steps = 0
        self.total_steps = 0
        self.additional_state_ids = get_obj_ids_for_adding_states(self.graph)
        self.nodes_with_additional_states: Dict[int, Dict[str, Any]] = {}

    @staticmethod
    def _without_character_prefix(action: str) -> str:
        stripped = action.strip()
        if stripped.startswith("<char0>"):
            return stripped[len("<char0>") :].strip()
        return stripped

    def execute_ground_truth_action(
        self,
        action: str,
        unity: Optional[UnityCommunication] = None,
    ) -> StepTrace:
        self.total_steps += 1
        unity_success: Optional[bool] = None
        unity_message = ""
        if unity is not None:
            try:
                unity_success, message = unity.render_script(
                    [action], recording=False, skip_animation=True, find_solution=True
                )
                unity_message = str(message)
            except Exception as exc:  # Unity is diagnostic; graph drives metrics.
                unity_success = False
                unity_message = str(exc)

        try:
            parsed = parse_script_line(self._without_character_prefix(action), 0)
        except Exception as exc:
            trace = StepTrace(action, None, False, str(exc), unity_success, unity_message)
            self.trace.append(trace)
            return trace

        success, final_state, _ = self.executor.execute(Script([parsed]))
        error = "" if success else self.executor.info.get_error_string()
        if success:
            self.executable_steps += 1
            self.graph = final_state.to_dict()
            # Match the released runner's ordering: rebuild the native graph
            # executor before augmentation adds evaluator-only USED/HEATED/
            # WASHED states that are absent from VirtualHome's State enum.
            self.executor = ScriptExecutor(EnvironmentGraph(self.graph), self.name_equivalence)
            agent_ids = [
                node["id"] for node in self.graph["nodes"] if node["class_name"] == "character"
            ]
            if agent_ids:
                partial_graph = utils.get_visible_nodes(self.graph, agent_id=agent_ids[0])
                self.nodes_with_additional_states = add_additional_obj_states(
                    partial_graph,
                    self.additional_state_ids,
                    self.nodes_with_additional_states,
                )
        trace = StepTrace(
            source_action=action,
            parsed_action=str(parsed),
            success=bool(success),
            error=error,
            unity_success=unity_success,
            unity_message=unity_message,
        )
        self.trace.append(trace)
        return trace

    @property
    def exec_ratio(self) -> float:
        return self.executable_steps / self.total_steps if self.total_steps else 0.0

    def record_failed_attempt(self, source_action: str, error: str) -> StepTrace:
        self.total_steps += 1
        trace = StepTrace(source_action, None, False, error)
        self.trace.append(trace)
        return trace

    def final_graph(self) -> Dict[str, Any]:
        graph = copy.deepcopy(self.graph)
        replacements = self.nodes_with_additional_states
        for index, node in enumerate(graph["nodes"]):
            if node["id"] in replacements:
                graph["nodes"][index] = copy.deepcopy(replacements[node["id"]])
        return graph


def available_object_classes(graph: Dict[str, Any]) -> List[str]:
    """Stable counterpart of ProgPrompt's ``list(set(class_names))``."""
    return sorted({node["class_name"] for node in graph["nodes"]})


def local_symbolic_state(graph: Dict[str, Any], include_inside: bool = True) -> str:
    """Reproduce the agent-local text state used for ProgPrompt assertions."""
    agents = [node for node in graph["nodes"] if node["class_name"] == "character"]
    if not agents:
        return ""
    agent = agents[0]
    room_ids = [
        edge["to_id"]
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and edge["relation_type"] == "INSIDE"
    ]
    room_name = next(
        (
            node["class_name"]
            for node in graph["nodes"]
            if room_ids and node["id"] == room_ids[0]
        ),
        "",
    )
    held_ids = {
        edge["to_id"]
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and "HOLD" in edge["relation_type"]
    }
    held_classes = sorted(
        node["class_name"] for node in graph["nodes"] if node["id"] in held_ids
    )

    partial_graph = utils.get_visible_nodes(graph, agent_id=agent["id"])
    close_ids = {
        edge["to_id"]
        for edge in graph["edges"]
        if edge["from_id"] == agent["id"] and edge["relation_type"] == "CLOSE"
    }
    close_nodes = [node for node in partial_graph["nodes"] if node["id"] in close_ids]
    close_classes = {node["class_name"] for node in close_nodes}
    close_id_to_class = {
        node["id"]: node["class_name"]
        for node in close_nodes
        if node["class_name"] != room_name
    }

    parts: set[str] = set()
    for node in graph["nodes"]:
        if node["class_name"] not in close_classes:
            continue
        if node["states"]:
            parts.add(f'{node["class_name"]} is {" and ".join(node["states"])}')
        else:
            parts.add(node["class_name"])
    excluded_relations = {"CLOSE", "FACING"}
    if not include_inside:
        excluded_relations.add("INSIDE")
    for edge in graph["edges"]:
        if (
            edge["from_id"] in close_id_to_class
            and edge["to_id"] in close_id_to_class
            and edge["relation_type"] not in excluded_relations
        ):
            parts.add(
                f'{close_id_to_class[edge["from_id"]]} {edge["relation_type"]} '
                f'{close_id_to_class[edge["to_id"]]}'
            )
    text = ", ".join(sorted(parts)) + "."
    if held_classes:
        text += f' You have {", ".join(held_classes)}.'
    return text
