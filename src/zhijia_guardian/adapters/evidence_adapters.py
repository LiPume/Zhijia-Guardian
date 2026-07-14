"""Adapters for auxiliary evidence; they never assert a shared physical route."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from zhijia_guardian.schema.models import AuxiliaryEvidenceBundle, Evidence
from zhijia_guardian.tools.evidence import create_evidence


def _load_bundle(path: str | Path, dataset: Literal["nuscenes", "nuplan"], role: Literal["perception_evidence_adapter", "planning_evidence_adapter"]) -> AuxiliaryEvidenceBundle:
  raw = json.loads(Path(path).read_text(encoding="utf-8"))
  observations = raw.get("observations", {})
  evidence = [create_evidence(item.get("kind", "adapter_observation"), item.get("summary", "Auxiliary adapter observation."), f"{dataset}_evidence_adapter",
    topic=item.get("topic"), metrics=item.get("metrics", observations), limitations=item.get("limitations", [])) for item in raw.get("evidence", [{"metrics": observations}])]
  for item in evidence:
    item.source_scope, item.source_dataset = "auxiliary", dataset
  return AuxiliaryEvidenceBundle(bundle_id=raw.get("bundle_id", f"{dataset}-auxiliary"), source_dataset=dataset, role=role, same_route_as_primary=False,
    source_reference=raw.get("source_reference"), evidence=evidence,
    limitations=["This auxiliary dataset is not asserted to be the same physical route as the primary openpilot-like case.", *raw.get("limitations", [])])


def load_nuscenes_perception_evidence(path: str | Path) -> AuxiliaryEvidenceBundle:
  return _load_bundle(path, "nuscenes", "perception_evidence_adapter")


def load_nuplan_planning_evidence(path: str | Path) -> AuxiliaryEvidenceBundle:
  return _load_bundle(path, "nuplan", "planning_evidence_adapter")
