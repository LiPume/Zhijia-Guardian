# CARLA 典型案例视频

- `01_perception_miss_comparison.mp4`：同一 CARLA 场景的正常感知与关键目标漏检对比。
- `02_planning_collision_risk_comparison.mp4`：同一 CARLA 场景的安全停车轨迹与碰撞风险轨迹对比。

视频为 1280x720、10 fps、H.264。红色框表示 CARLA simulation GT，绿色框表示感知输出，
黄色线表示规划轨迹，蓝色框表示 ego。右侧红点和 `FAULT ACTIVE` 表示进入故障时间段。

重新生成：

```bash
conda run -n yolo python scripts/render_carla_case_videos.py
```
