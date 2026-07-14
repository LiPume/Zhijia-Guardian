import pytest

from zhijia_guardian.adapters import generate_clean_case


def test_observed_copy_hides_oracle():
  case = generate_clean_case()
  assert case.oracle is not None
  assert case.observed_copy().oracle is None


def test_schema_rejects_message_outside_range():
  case = generate_clean_case()
  case.messages[0].mono_time = 0
  with pytest.raises(ValueError):
    case.model_validate(case.model_dump())
