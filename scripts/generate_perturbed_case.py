#!/usr/bin/env python3
from pathlib import Path
from zhijia_guardian.adapters import generate_clean_case, inject_perturbation, save_case_json

root = Path("/data5/lzx_data/Zhijia-Guardian")
clean = generate_clean_case()
perturbed, manifest = inject_perturbation(clean)
save_case_json(clean, root / "synthetic" / "clean_case.json")
save_case_json(perturbed, root / "perturbed" / "perturbed_case.json")
print(manifest)
