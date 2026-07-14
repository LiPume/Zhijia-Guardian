import pytest

from zhijia_guardian.adapters.openpilot_adapter import load_openpilot_log


def test_real_log_requires_explicit_reference_or_is_skipped():
  with pytest.raises(RuntimeError, match="OPENPILOT_ROOT"):
    load_openpilot_log("missing.rlog.zst", openpilot_root="/does/not/exist")
