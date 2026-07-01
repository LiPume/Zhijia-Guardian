from __future__ import annotations

import json
import random
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from zhijia_guardian.adapters import CarlaAdapter
from zhijia_guardian.adapters.carla_adapter import CarlaLabelFile, CarlaRawEvent
from zhijia_guardian.benchmarks.carla_closed_loop import (
    _dump_model,
    _eligible_spawn_points,
    _record_case,
)
from zhijia_guardian.schemas.scenario import OracleRecord
from zhijia_guardian.utils.io import dump_scenario_jsonl


WEATHER_CASES = (
    "normal",
    "perception_confidence_drop",
    "planning_collision_risk",
    "control_delay",
)

ROOT_MODULE = {
    "normal": "none",
    "perception_confidence_drop": "perception",
    "planning_collision_risk": "planning",
    "control_delay": "control",
}


@dataclass(frozen=True)
class WeatherProfile:
    name: str
    split: str
    cloudiness: float
    precipitation: float
    precipitation_deposits: float
    wind_intensity: float
    wetness: float
    fog_density: float
    fog_distance: float
    fog_falloff: float
    sun_altitude_angle: float


WEATHER_PROFILES = (
    WeatherProfile(
        name="heavy_rain_day",
        split="train",
        cloudiness=100.0,
        precipitation=100.0,
        precipitation_deposits=90.0,
        wind_intensity=60.0,
        wetness=100.0,
        fog_density=20.0,
        fog_distance=10.0,
        fog_falloff=0.2,
        sun_altitude_angle=20.0,
    ),
    WeatherProfile(
        name="dense_fog_dawn",
        split="val",
        cloudiness=80.0,
        precipitation=20.0,
        precipitation_deposits=60.0,
        wind_intensity=20.0,
        wetness=80.0,
        fog_density=100.0,
        fog_distance=2.0,
        fog_falloff=0.1,
        sun_altitude_angle=5.0,
    ),
    WeatherProfile(
        name="night_storm",
        split="test",
        cloudiness=100.0,
        precipitation=90.0,
        precipitation_deposits=100.0,
        wind_intensity=100.0,
        wetness=100.0,
        fog_density=50.0,
        fog_distance=5.0,
        fog_falloff=0.1,
        sun_altitude_angle=-25.0,
    ),
)


def record_carla_weather_benchmark(
    output_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 2000,
    town: str = "Town10HD_Opt",
    seed: int = 42,
    fixed_delta_seconds: float = 0.1,
    max_frames: int = 80,
    lead_distance: float = 18.0,
    target_speed: float = 7.0,
    control_delay: float = 0.8,
    planning_fault_start: float = 0.5,
    perception_fault_start: float = 0.5,
    no_rendering: bool = False,
    clean: bool = False,
) -> dict:
    try:
        import carla
    except ImportError as exc:
        raise RuntimeError("carla==0.9.15 is required to record weather scenarios") from exc

    output_root = Path(output_root)
    log_dir = output_root / "raw" / "logs"
    label_dir = output_root / "raw" / "labels"
    canonical_dir = output_root / "canonical"
    if clean and output_root.exists():
        shutil.rmtree(output_root)
    for path in (log_dir, label_dir, canonical_dir):
        path.mkdir(parents=True, exist_ok=True)

    client = carla.Client(host, port)
    client.set_timeout(30.0)
    world = client.get_world()
    if not world.get_map().name.endswith(f"/{town}"):
        raise RuntimeError(
            f"CARLA is running {world.get_map().name}; start a fresh server on {town}"
        )
    spawn_points = _eligible_spawn_points(world.get_map(), lead_distance)
    random.Random(seed).shuffle(spawn_points)
    if not spawn_points:
        raise RuntimeError("no spawn point supports the requested lead distance")
    spawn_transform = spawn_points[0]

    original_settings = world.get_settings()
    original_weather = world.get_weather()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = fixed_delta_seconds
    settings.no_rendering_mode = no_rendering
    world.apply_settings(settings)

    rows = []
    scenario_index = 0
    try:
        for profile in WEATHER_PROFILES:
            weather = _carla_weather(carla, profile)
            world.set_weather(weather)
            for _ in range(3):
                world.tick()
            for case_name in WEATHER_CASES:
                scenario_index += 1
                scenario_id = f"carla_wx_v0_1_{scenario_index:06d}"
                raw_log, outcome = _record_case(
                    carla,
                    world,
                    spawn_transform,
                    scenario_id,
                    case_name,
                    fixed_delta_seconds=fixed_delta_seconds,
                    max_frames=max_frames,
                    lead_distance=lead_distance,
                    target_speed=target_speed,
                    control_delay=control_delay,
                    planning_fault_start=planning_fault_start,
                    perception_fault_start=perception_fault_start,
                )
                raw_log.frames[0].events.insert(
                    0,
                    CarlaRawEvent(
                        event_type="weather_context",
                        description=f"CARLA extreme weather profile: {profile.name}",
                        attributes={
                            "profile": profile.name,
                            "precipitation": profile.precipitation,
                            "wetness": profile.wetness,
                            "fog_density": profile.fog_density,
                            "sun_altitude_angle": profile.sun_altitude_angle,
                        },
                    ),
                )
                log_path = log_dir / f"{scenario_index:06d}.json"
                label_path = label_dir / f"{scenario_id}.label.json"
                _dump_model(raw_log, log_path)
                _dump_model(
                    CarlaLabelFile(
                        scenario_id=scenario_id,
                        oracle=OracleRecord(
                            visible_to_diagnosis=False,
                            fault_type=case_name,
                            root_module=ROOT_MODULE[case_name],
                            fault_start_time=outcome["fault_start_time"],
                            notes=f"CARLA weather benchmark case: {case_name}",
                        ),
                    ),
                    label_path,
                )
                rows.append(
                    {
                        "scenario_id": scenario_id,
                        "weather_profile": profile.name,
                        "split": profile.split,
                        "case": case_name,
                        "outcome": outcome,
                        "log_file": str(log_path.relative_to(output_root)),
                        "label_file": str(label_path.relative_to(output_root)),
                    }
                )
    finally:
        world.set_weather(original_weather)
        world.apply_settings(original_settings)

    manifest = {
        "dataset": "carla_extreme_weather_v0_1",
        "carla_version": client.get_server_version(),
        "map": world.get_map().name,
        "seed": seed,
        "num_scenarios": len(rows),
        "cases": list(WEATHER_CASES),
        "weather_profiles": [asdict(profile) for profile in WEATHER_PROFILES],
        "fixed_delta_seconds": fixed_delta_seconds,
        "control_delay_seconds": control_delay,
        "planning_fault_start_seconds": planning_fault_start,
        "perception_fault_start_seconds": perception_fault_start,
        "perception_contract": (
            "Synthetic annotation-derived detections; weather does not degrade the detector unless the "
            "perception_confidence_drop case is active."
        ),
        "split_policy": "weather_profile_holdout",
        "scenarios": rows,
    }
    (label_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    adapter = CarlaAdapter(log_dir, label_dir)
    records = {scenario_id: adapter.load_scenario(scenario_id) for scenario_id in adapter.list_scenarios()}
    dump_scenario_jsonl(records.values(), canonical_dir / "scenarios.jsonl")
    for split in ("train", "val", "test"):
        split_ids = [row["scenario_id"] for row in rows if row["split"] == split]
        dump_scenario_jsonl(
            [records[scenario_id] for scenario_id in split_ids],
            canonical_dir / "splits" / f"{split}.jsonl",
        )
    return manifest


def _carla_weather(carla, profile: WeatherProfile):
    weather = carla.WeatherParameters()
    for field, value in asdict(profile).items():
        if field in {"name", "split"}:
            continue
        setattr(weather, field, value)
    return weather
