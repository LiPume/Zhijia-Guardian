from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import Field

from zhijia_guardian.agents.control_agent import run_control_agent
from zhijia_guardian.agents.metric_agent import run_metric_agent
from zhijia_guardian.agents.perception_agent import run_perception_agent
from zhijia_guardian.agents.planning_agent import run_planning_agent
from zhijia_guardian.agents.root_cause_agent import run_root_cause_agent
from zhijia_guardian.agents.scene_agent import run_scene_agent
from zhijia_guardian.agents.types import ModuleDiagnosis, StrictModel
from zhijia_guardian.schemas.diagnosis import AgentStepRecord, DiagnosisRecord
from zhijia_guardian.schemas.metrics import MetricsRecord
from zhijia_guardian.schemas.scenario import ScenarioRecord


ModuleRunner = Callable[[ScenarioRecord, MetricsRecord], ModuleDiagnosis]


class GraphNodeSpec(StrictModel):
    name: str
    stage: Literal["prepare", "fan_out", "fan_in"]
    depends_on: tuple[str, ...] = ()


class DiagnosisGraphState(StrictModel):
    scenario: ScenarioRecord
    metrics: MetricsRecord | None = None
    trace: list[AgentStepRecord] = Field(default_factory=list)
    module_diagnoses: dict[str, ModuleDiagnosis] = Field(default_factory=dict)
    diagnosis: DiagnosisRecord | None = None
    executed_nodes: list[str] = Field(default_factory=list)


class DiagnosisGraph:
    """Deterministic fan-out/fan-in graph for evidence-grounded diagnosis agents."""

    NODE_SPECS = (
        GraphNodeSpec(name="metric_agent", stage="prepare"),
        GraphNodeSpec(name="scene_agent", stage="prepare", depends_on=("metric_agent",)),
        GraphNodeSpec(name="perception_agent", stage="fan_out", depends_on=("metric_agent",)),
        GraphNodeSpec(name="planning_agent", stage="fan_out", depends_on=("metric_agent",)),
        GraphNodeSpec(name="control_agent", stage="fan_out", depends_on=("metric_agent",)),
        GraphNodeSpec(
            name="root_cause_agent",
            stage="fan_in",
            depends_on=(
                "scene_agent",
                "perception_agent",
                "planning_agent",
                "control_agent",
            ),
        ),
    )

    MODULE_NODES: tuple[tuple[str, ModuleRunner], ...] = (
        ("perception", run_perception_agent),
        ("planning", run_planning_agent),
        ("control", run_control_agent),
    )

    def describe(self) -> list[dict[str, object]]:
        return [node.model_dump(mode="json") for node in self.NODE_SPECS]

    def initialize_state(
        self,
        scenario: ScenarioRecord,
        metrics: MetricsRecord | None = None,
    ) -> DiagnosisGraphState:
        observed_scenario = ScenarioRecord.model_validate(scenario.observed_view())
        if observed_scenario.oracle is not None or observed_scenario.source.generation:
            raise AssertionError("diagnosis graph state must not contain oracle or generation labels")
        if metrics is not None and metrics.scenario_id != observed_scenario.scenario_id:
            raise ValueError(
                f"metrics scenario_id {metrics.scenario_id} does not match {observed_scenario.scenario_id}"
            )
        return DiagnosisGraphState(scenario=observed_scenario, metrics=metrics)

    def invoke(
        self,
        scenario: ScenarioRecord,
        metrics: MetricsRecord | None = None,
    ) -> DiagnosisGraphState:
        state = self.initialize_state(scenario, metrics)
        self._run_metric_node(state)
        self._run_scene_node(state)
        for module_name, runner in self.MODULE_NODES:
            self._run_module_node(state, module_name, runner)
        self._run_root_node(state)
        self._validate_complete(state)
        return state

    @staticmethod
    def _run_metric_node(state: DiagnosisGraphState) -> None:
        if state.metrics is None:
            state.metrics, step = run_metric_agent(state.scenario)
        else:
            step = AgentStepRecord(
                agent_name="metric_agent",
                status="completed",
                summary=f"Received precomputed metrics with {len(state.metrics.evidence)} evidence records.",
                evidence_ids=[item.evidence_id for item in state.metrics.evidence],
                output={"num_evidence": len(state.metrics.evidence), "precomputed": True},
            )
        state.trace.append(step)
        state.executed_nodes.append("metric_agent")

    @staticmethod
    def _run_scene_node(state: DiagnosisGraphState) -> None:
        metrics = _require_metrics(state)
        state.trace.append(run_scene_agent(state.scenario, metrics))
        state.executed_nodes.append("scene_agent")

    @staticmethod
    def _run_module_node(
        state: DiagnosisGraphState,
        module_name: str,
        runner: ModuleRunner,
    ) -> None:
        metrics = _require_metrics(state)
        diagnosis = runner(state.scenario, metrics)
        if diagnosis.module_name != module_name:
            raise ValueError(
                f"{module_name}_agent returned module_name={diagnosis.module_name}"
            )
        state.module_diagnoses[module_name] = diagnosis
        state.trace.append(_module_step(diagnosis))
        state.executed_nodes.append(f"{module_name}_agent")

    @staticmethod
    def _run_root_node(state: DiagnosisGraphState) -> None:
        metrics = _require_metrics(state)
        missing = [name for name, _ in DiagnosisGraph.MODULE_NODES if name not in state.module_diagnoses]
        if missing:
            raise RuntimeError(f"root_cause_agent cannot run before module agents: {missing}")
        modules = [state.module_diagnoses[name] for name, _ in DiagnosisGraph.MODULE_NODES]
        state.diagnosis = run_root_cause_agent(
            state.scenario,
            metrics,
            modules,
            state.trace,
        )
        state.trace = list(state.diagnosis.agent_trace)
        state.executed_nodes.append("root_cause_agent")

    @classmethod
    def _validate_complete(cls, state: DiagnosisGraphState) -> None:
        expected = [node.name for node in cls.NODE_SPECS]
        if state.executed_nodes != expected:
            raise RuntimeError(
                f"diagnosis graph execution order mismatch: {state.executed_nodes} != {expected}"
            )
        if state.metrics is None or state.diagnosis is None:
            raise RuntimeError("diagnosis graph completed without metrics or diagnosis")
        trace_names = [step.agent_name for step in state.diagnosis.agent_trace]
        if trace_names != expected:
            raise RuntimeError(f"agent trace order mismatch: {trace_names} != {expected}")


def _require_metrics(state: DiagnosisGraphState) -> MetricsRecord:
    if state.metrics is None:
        raise RuntimeError("metric_agent must run before downstream agents")
    return state.metrics


def _module_step(module: ModuleDiagnosis) -> AgentStepRecord:
    return AgentStepRecord(
        agent_name=f"{module.module_name}_agent",
        status=module.status,
        summary=module.summary,
        evidence_ids=module.evidence_ids,
        output={
            "predicted_fault_type": module.predicted_fault_type,
            "predicted_root_module": module.predicted_root_module,
            "score": module.score,
            "confidence": module.confidence,
            "start_time": module.start_time,
        },
    )


DEFAULT_DIAGNOSIS_GRAPH = DiagnosisGraph()


def run_diagnosis_graph(
    scenario: ScenarioRecord,
    metrics: MetricsRecord | None = None,
) -> tuple[MetricsRecord, DiagnosisRecord]:
    state = DEFAULT_DIAGNOSIS_GRAPH.invoke(scenario, metrics)
    return _require_metrics(state), state.diagnosis  # type: ignore[return-value]
