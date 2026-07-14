from zhijia_guardian.adapters import generate_clean_case, inject_perturbation
from zhijia_guardian.workflow import run_diagnostic_workflow


def test_perception_case_skips_irrelevant_can_control_and_safety_agents():
  clean = generate_clean_case()
  case, _ = inject_perturbation(clean, kind="perception_dropout")
  _, state = run_diagnostic_workflow(case, intervention_reference=clean)
  trace_agents = {item.agent for item in state.trace}
  assert "message_flow_agent" in trace_agents
  assert "can_diagnostic_agent" not in trace_agents
  assert "control_link_agent" not in trace_agents
  assert "safety_vehicle_interface_agent" not in trace_agents


def test_sendcan_case_routes_to_transport_control_and_safety_follow_ups():
  clean = generate_clean_case()
  case, _ = inject_perturbation(clean, kind="sendcan_gap")
  _, state = run_diagnostic_workflow(case, intervention_reference=clean)
  trace_agents = {item.agent for item in state.trace}
  assert {"can_diagnostic_agent", "control_link_agent", "safety_vehicle_interface_agent"} <= trace_agents
