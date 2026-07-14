from pathlib import Path

import pytest

from zhijia_guardian.adapters.openpilot_adapter import load_openpilot_log


DATA_ROOT = Path("/data5/lzx_data/Zhijia-Guardian")
LOG = DATA_ROOT / "raw/openpilot/openpilotci-2019-06-13-segment3-qlog.bz2"
ROOT = DATA_ROOT / "reference/openpilot"


@pytest.mark.skipif(not (LOG.exists() and ROOT.exists()), reason="official one-segment qlog smoke sample/reference is not available under external data root")
def test_official_qlog_smoke_parse():
  case = load_openpilot_log(LOG, openpilot_root=ROOT)
  assert not case.source.is_synthetic
  assert len(case.messages) > 100
  assert "carState" in {message.topic for message in case.messages}
