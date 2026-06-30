# CARLA 0.9.15 运行与复现

## 已验证环境

- CARLA server：0.9.15 Linux packaged release。
- Python client：PyPI `carla==0.9.15` 的 `cp310` wheel。
- ScenarioRunner：官方 tag `v0.9.15`，commit `d12d8bb`。
- 主环境：conda `yolo` / Python 3.10。
- 运行目录：`/data5/lzx_data/Zhijia-Guardian/third_party/`。

服务器压缩包自带的 Python API 只有 cp27/cp37，不能装进 Python 3.10；必须使用 PyPI
的 cp310 wheel。ScenarioRunner 原 requirements 还会降级 numpy/networkx/opencv，因此不要直接
执行 `pip install -r requirements.txt`。仓库脚本只安装缺失依赖并保留现有科学计算栈。

ScenarioRunner 0.9.15 还使用 Python 3.9 已删除的 `Element.getchildren()`。运行：

```bash
./scripts/setup_carla_runtime.sh
```

会安装兼容依赖，并以可重复、可反向校验的方式应用
`patches/scenario_runner_0.9.15_py310.patch`。重复执行不会重复修改源码。

## 启动与记录

终端一启动无渲染服务器：

```bash
./carla.sh
```

需要 CARLA RGB 相机流时使用 Xvfb 正常渲染路径；当前机器的 UE4.26
`-RenderOffScreen` 可运行仿真，但不会回调 RGB camera：

```bash
CARLA_RENDER_MODE=xvfb ./carla.sh
```

等待客户端可连接后，在终端二记录 5 条基础场景。0.9.15 在当前机器热切地图偶发 UE4
Signal 11，因此 v0.1 固定使用服务器默认的 `Town10HD_Opt`，不在同一进程中 reload world：

```bash
conda run -n yolo python scripts/record_carla_base_scenarios.py \
  --count 5 \
  --frames 80 \
  --town Town10HD_Opt \
  --seed 42 \
  --no-rendering \
  --output-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1
```

每条日志来自不同出生点，记录 ego、关键前车、合成感知、停车 rollout、VehicleControl、
map waypoint 及 sensor events。当前实测每条 26 帧。

## 故障集与评估

```bash
conda run -n yolo python scripts/generate_carla_fault_benchmark.py \
  --base-log-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1 \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_1 \
  --clean
```

5 个父场景分别派生 normal、perception miss、false positive、confidence drop、planning
collision risk、control delay，共 30 条。原始日志与 label 分目录保存，manifest 只在 labels
目录；canonical 输出位于 `canonical/scenarios.jsonl`。

```bash
conda run -n yolo python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_1/canonical/scenarios.jsonl \
  --run-id carla_fault_v0_1_multi_agent_seed42 \
  --seed 42
```

## 当前边界

- ScenarioRunner 的 `FollowLeadingVehicle_1` 已完成 actor 创建、60 秒场景树运行和碰撞判据输出；
  stock 示例没有 ego controller，因此最终状态是 TIMEOUT，不把它误记成场景成功。
- 当前故障是离线信号级注入，真实 CARLA 状态来自仿真，但注入后没有重新跑车辆动力学。
- 30 条 v0.1 上 Rule-only 与 Multi-Agent 均为满分，只能证明链路正确，不能证明方法提升。
- 下一版需要随机注入强度、边界样本、复合故障和 parent-group 隔离的 held-out split；控制
  延迟和规划故障再增加闭环重跑版本。

## 典型案例视频

真实 3D RGB 闭环案例：

```bash
CARLA_RENDER_MODE=xvfb ./carla.sh
conda run -n yolo python scripts/capture_carla_3d_case_videos.py
```

输出 `demo/03_carla_3d_normal_stop.mp4`、`demo/04_carla_3d_control_delay.mp4` 和
`demo/carla_3d_case_manifest.json`。正常案例风险出现后立即制动且无碰撞；control-delay
案例真实延迟 0.8 秒后制动并发生追尾，属于闭环动力学差异。

批量闭环 benchmark 的记录、转换和评估见
[`docs/carla_closed_loop_v0_1.md`](carla_closed_loop_v0_1.md)。

BEV 成对诊断案例：

从同一个 CARLA 父场景生成左右同步的 normal/fault 诊断视频：

```bash
conda run -n yolo python scripts/render_carla_case_videos.py
```

输出目录：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/case_videos/carla_v0_1/
  01_perception_miss_comparison.mp4
  02_planning_collision_risk_comparison.mp4
  index.json
```

BEV 视频为 1280x720、10 fps、H.264。红色框是 CARLA simulation GT，绿色框是感知输出，
黄色线是 planner trajectory，蓝色框是 ego。右侧红点及 `FAULT ACTIVE` 表示已进入 oracle
故障时间段。它是基于真实 CARLA 状态日志的 ego-centric BEV 诊断回放，不是相机视频。
