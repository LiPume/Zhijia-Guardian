# nuScenes Mini Mapping

当前有两个实现：

- `src/zhijia_guardian/adapters/nuscenes_adapter.py`：metadata-only smoke。
- `src/zhijia_guardian/adapters/nuscenes_vision_adapter.py`：真实 `CAM_FRONT` + YOLO 连续片段。

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

## Metadata Smoke Boundary

- 当前只使用 metadata，不解图像、点云、雷达媒体。
- 当前 metadata-only 实现不依赖 `nuscenes-devkit`；后续若使用官方 API、解媒体或运行 detector 再安装。
- 本地 mini metadata 可列出 404 个 `sample`，当前 smoke test/export 默认抽前 5 个 sample。
- `perception.available=false`
- `planning.available=false`
- `control.available=false`
- `actors_gt_source=dataset_annotation`
- 5 个 smoke sample 均可转成单帧 `ScenarioRecord`，可运行 schema validate、BEV/基础风险指标流程。

## Real Vision Mapping

真实视觉 v0.1 已解出 404 张 `CAM_FRONT` 关键帧，并从 5 个 scene 选择 202 帧运行冻结 YOLOv8n：

| Source | Canonical field |
| --- | --- |
| YOLO class/confidence/2D box | `perception.detections[*].type/confidence/bbox_xyxy` |
| projected nuScenes 3D annotation | `actors_gt[*].sensor_bbox_xyxy` |
| IoU association | `matched_gt_id/association_iou` |
| unmatched 2D detection | `matched_gt_id=null`, `x/y=null` |
| detector provenance | `perception.detection_source=model_output` |

Annotation 只用于公开数据离线关联和评测，不作为 fault/root oracle。完整结果与边界见
[nuscenes_real_yolo_v0_1.md](nuscenes_real_yolo_v0_1.md)。若用 annotation 扰动生成检测结果，仍必须设置
`perception.detection_source=synthetic_from_annotation`，不能冒充模型输出。
