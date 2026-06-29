# CARLA 典型案例视频

## 3D RGB 闭环案例

- `03_carla_3d_normal_stop.mp4`：CARLA RGB 追车相机，ego 及时制动，无碰撞。
- `04_carla_3d_control_delay.mp4`：相同初始条件下制动命令真实延迟 0.8 秒并发生追尾。
- `carla_3d_case_manifest.json`：风险开始、实际制动时间、最低 TTC 和碰撞结果。

两条视频直接来自 CARLA `sensor.camera.rgb`，不是 BEV 合成。录制时蓝色车辆为 ego，红色
车辆为关键前车；画面底部显示速度、间距、TTC 和制动量。

重新录制：

```bash
CARLA_RENDER_MODE=xvfb ./carla.sh
conda run -n yolo python scripts/capture_carla_3d_case_videos.py
```

## BEV 诊断案例

- `01_perception_miss_comparison.mp4`：同一 CARLA 场景的正常感知与关键目标漏检对比。
- `02_planning_collision_risk_comparison.mp4`：同一 CARLA 场景的安全停车轨迹与碰撞风险轨迹对比。

视频为 1280x720、10 fps、H.264。红色框表示 CARLA simulation GT，绿色框表示感知输出，
黄色线表示规划轨迹，蓝色框表示 ego。右侧红点和 `FAULT ACTIVE` 表示进入故障时间段。

重新生成 BEV 视频：

```bash
conda run -n yolo python scripts/render_carla_case_videos.py
```
