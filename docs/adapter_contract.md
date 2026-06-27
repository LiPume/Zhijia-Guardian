# Adapter Contract

所有数据源 adapter 必须输出同一个 `ScenarioRecord`，tools 和 agents 不直接读取 nuScenes、nuPlan、CARLA 原始格式。

## Interface

```python
class BaseAdapter:
    def list_scenarios(self) -> list[str]:
        ...

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        ...

    def export_json(self, scenario_id: str, output_path: str) -> None:
        ...
```

## No Leakage

- 诊断入口只能读取 `ScenarioRecord.observed_view()`。
- `oracle` 只能由评估脚本读取。
- `scenario_id`、文件名、路径不得包含 `fault_type` 或 `root_module`。
- `scenario_tag`、目录名、dataset split 只能作为上下文或抽样条件，不能作为诊断答案。

## Source Fields

- `actors_gt_source`: `simulation`、`dataset_annotation`、`offline_reconstruction`、`unavailable`
- `perception.detection_source`: `model_output`、`synthetic_from_annotation`、`dataset_prediction`、`unavailable`
- `planning.trajectory_source`: `expert_future`、`offline_planner`、`perturbed_planner`、`model_prediction`、`unavailable`

只有 `offline_planner`、`perturbed_planner`、`model_prediction` 可以用于诊断 planner 输出。`expert_future` 只能作为参考轨迹。

## Vehicle Geometry

- `frames[*].ego.length` and `frames[*].ego.width` are required by the canonical model through validated defaults
  of 4.8 m and 1.9 m when the source does not provide an ego bounding box.
- Adapters with source bounding boxes, especially CARLA, must map the measured dimensions instead of relying on
  defaults.
- Actor and ego yaw use radians. Planning and collision tools compute oriented rectangle separation so adjacent
  lanes are not treated as overlapping circular footprints.
