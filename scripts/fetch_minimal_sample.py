#!/usr/bin/env python3
"""Download exactly one upstream OpenPilotCI qlog smoke sample; no route collection."""
from pathlib import Path
from urllib.request import urlretrieve
import os

URL = "https://commadataci.blob.core.windows.net/openpilotci/0375fdf7b1ce594d/2019-06-13--08-32-25/3/qlog.bz2"
root = Path(os.environ.get("ZHIJIA_DATA_ROOT", "/data5/lzx_data/Zhijia-Guardian")) / "raw" / "openpilot"
root.mkdir(parents=True, exist_ok=True)
target = root / "openpilotci-2019-06-13-segment3-qlog.bz2"
if not target.exists():
  urlretrieve(URL, target)
print(target, target.stat().st_size)
