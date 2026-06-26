# nuScenes Mini Mapping

当前实现：`src/zhijia_guardian/adapters/nuscenes_adapter.py`

数据位置：

```text
/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini/
```

## Minimal Join

| nuScenes table | Canonical field |
| --- | --- |
| `sample` | scenario/sample source token |
| `scene` | `source.raw_log_id` |
| `sample_data(channel=LIDAR_TOP, is_key_frame=true)` | frame anchor |
| `ego_pose` | `frames[*].ego` |
| `sample_annotation` | `frames[*].actors_gt` |
| `instance -> category` | actor id and actor type |

## Current Boundary

- 当前只使用 metadata，不解图像、点云、雷达媒体。
- 当前 metadata-only 实现不依赖 `nuscenes-devkit`；后续若使用官方 API、解媒体或运行 detector 再安装。
- 本地 mini metadata 可列出 404 个 `sample`，当前 smoke test/export 默认抽前 5 个 sample。
- `perception.available=false`
- `planning.available=false`
- `control.available=false`
- `actors_gt_source=dataset_annotation`
- 5 个 smoke sample 均可转成单帧 `ScenarioRecord`，可运行 schema validate、BEV/基础风险指标流程。

若后续运行 detector，必须把检测输出写入 `perception.detections`，并设置 `perception.detection_source=model_output`。若用 annotation 扰动生成检测结果，必须设置 `perception.detection_source=synthetic_from_annotation`。
