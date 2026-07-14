from zhijia_guardian.workflow.llm import resolve_llm_mode


def test_offline_llm_mode_is_default(monkeypatch):
  monkeypatch.delenv("LLM_PROVIDER", raising=False)
  assert resolve_llm_mode().active is False
