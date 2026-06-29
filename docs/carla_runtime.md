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
