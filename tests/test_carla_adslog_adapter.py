import json

from zhijia_guardian.adapters import load_carla_adslog_record


def test_carla_compatible_adslog_adapter_has_no_runtime_dependency(tmp_path):
  path = tmp_path / "carla_adslog.json"
  path.write_text(json.dumps({"case_id": "carla-small", "route_id": "Town01/route-1", "records": [
    {"timestamp_s": 0.0, "topic": "perceptionEvidence", "payload_summary": {"leadVisible": True}},
    {"timestamp_s": 0.1, "topic": "longitudinalPlan", "payload_summary": {"aTarget": 0.2}},
    {"timestamp_s": 0.2, "topic": "carControl", "payload_summary": {"actuators": {"accel": 0.2}}},
  ]}))
  case = load_carla_adslog_record(path)
  assert case.source.stack == "carla"
  assert case.source.is_synthetic
  assert [item.topic for item in case.messages] == ["perceptionEvidence", "longitudinalPlan", "carControl"]
