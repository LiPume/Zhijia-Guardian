# 智驾卫士 Zhijia Guardian

面向自动驾驶异常日志的多 Agent 离线根因诊断与证据链生成原型。

本项目不是替代工程师做最终定责，而是把自动驾驶异常复盘中的日志对齐、指标计算、异常定位、证据整理和报告生成做成可复现流程。目标是在碰撞、急刹、偏航、轨迹异常、规则违反等安全违规场景中，自动输出候选根因 Top-K、证据链和工程师可读诊断报告，辅助研发人员缩短事故排查与算法调试时间。

## 当前状态

当前仓库已经完成第一版工程原型的底座：

- Canonical `ScenarioRecord` schema，包含 `source/meta/frames/events_observed/oracle`。
- `observed_view()` 与 `oracle` 隔离，诊断路径不能读取标签。
- `ManualAdapter`、nuScenes metadata/真实六相机 YOLO adapter、nuPlan SQLite 5-scenario smoke adapter。
- 6 个 canonical demo 场景生成脚本。
- 真实数据兼容的 noisy manual 场景生成脚本。
- TTC、碰撞、感知异常、规划风险、控制延迟等指标工具。
- Rule-only baseline 和评估入口。
- Single-LLM baseline，使用去标签化的场景/指标摘要、结构化输出和 evidence 引用校验；默认关闭 API 调用。
- 显式 Pydantic 多 Agent 图，包含 metric、scene、perception、planning、control fan-out 和 root-cause fan-in；节点输入已物理移除 oracle。
- `run_id` 级实验输出目录，包含 `run_report.md`、`figures/`、`tables/`、`summary.json`、`eval.csv`、`confusion_matrix.json`、`run_meta.json`。
- versioned `diagnosis_v1`、`diagnosis_report_v1` 和 `failure_sample_v1` 输出契约，支持导出 JSON Schema。
- failure sample package，包含 `failure_samples.jsonl`、`tables/failure_samples.csv` 和 `failure_samples/{scenario_id}/failure_sample.json`。
- Streamlit 只读工作台，直接读取输出包展示指标、错误样本、BEV、timeline、agent trace 和报告。
- CARLA 0.9.15 离线故障注入、15 条 closed-loop benchmark 和 12 条极端天气 held-out benchmark，含 3D RGB 典型案例视频。
- nuScenes mini 真实道路场景六相机 YOLOv8n 推理、公开标注投影关联、距离分桶指标和无 oracle 多 Agent 诊断。
- 可选 Qwen3.7-Plus Visual Review Agent，支持纯原图 `direct_vlm` 与原图加去标签 evidence 的 `vlm_with_tools` 两条旁路实验。
- pytest 覆盖 schema、真实 adapter、图状态、复合故障时序、demo eval、manual generator 和无标签泄漏。

暂未完成的部分：

- SafeBench 官方 0.9.13 runtime 的真实 rollout；现有 0.9.15 在创建官方场景 actor 时会崩溃，主仓只保留安全 JSON adapter。
- nuScenes LiDAR/相机融合 3D detector；当前已完成六相机独立 2D YOLOv8n，不声称已做传感器融合。
- 多 seed、更多 CARLA 场景模板和自然事故外部验证。
- 真实相机/点云 detector 的雨雾夜间退化评估；当前极端天气 benchmark 使用 annotation-derived detections。

## 项目边界

本项目中的“多 Agent”指诊断 Agent，不指交通环境中的多车、多行人、多路侧设备交互智能体。第一版诊断 Agent 包括场景重建、感知诊断、规划诊断、控制诊断、根因汇总和报告生成。

当前使用显式 Pydantic DAG 编排 typed state、模块 fan-out 和根因 fan-in。LangGraph 暂不作为强依赖；当产品需要人工审核暂停/恢复、持久化 checkpoint、跨进程重试或 time-travel 时，再增加可选 backend。决策见 [docs/orchestration_decision.md](docs/orchestration_decision.md)。

本项目不做以下事情：

- 不直接判断交通事故法律责任。
- 不声称能从任意真实车端日志中自动恢复完整真值。
- 不把 nuScenes / nuPlan 的场景标签当作故障根因标签。
- 不把 LLM 当成直接猜答案的分类器。
- 不复现 UniAD、VAD、SparseDrive、TransFuser 等完整自动驾驶模型。
- 不在 MVP 阶段接 Autoware、车企 NOA 私有日志或通用隐层特征解释。

更准确的定位是：

> 面向自动驾驶异常日志的多 Agent 协同离线诊断与证据链生成系统。

## 为什么可行

这个 idea 可行，但前提是范围要收敛清楚。

可行的部分是：把自动驾驶复盘流程拆成统一 schema、确定性指标工具、模块化诊断 Agent、证据链和报告输出。这个方向工程上能落地，也能跑出数据和对比指标，因为 manual perturbation 和 CARLA 故障注入可以提供已知 oracle，用于计算 Fault Macro-F1、Root Cause Top-1、Fault Start Time MAE、Evidence Coverage 和 Hallucination Rate。SafeBench 原生输出缺少完整模块日志，只作为降级 adapter 候选。

不适合直接承诺的部分是：仅靠 nuScenes 或 nuPlan 直接证明根因诊断效果。nuScenes 更适合验证感知相关 schema 和 annotation 映射；nuPlan 更适合验证规划场景骨架、地图、ego future 和 scenario tag 的读取。它们本身不是“带系统故障根因标签”的诊断数据集，所以第一版只能把它们作为真实数据接入 smoke test 和可视化/字段覆盖验证。

最终产品的合理 MVP 是：

1. 工程师选择一个异常场景 JSON 或 adapter 转换后的 `ScenarioRecord`。
2. 系统计算 TTC、碰撞、漏检、误检、规划碰撞、控制延迟等 metrics。
3. 模块 Agent 只基于 observed view 和 evidence 输出结构化诊断。
4. Root Cause Agent 汇总候选根因 Top-K。
5. Report Agent 生成带 evidence_id 的报告。
6. Evaluator 只在离线实验中读取 `oracle` 计算指标。

## 核心输入输出

第一版系统输入不是原始车企全量日志，而是 adapter 转换后的统一结构化日志 `ScenarioRecord`。

### 输入

`ScenarioRecord` 的核心结构如下：

```json
{
  "scenario_id": "manual_v0_1_000001",
  "source": {
    "dataset": "manual_json",
    "version": "v0_1",
    "raw_log_id": "full_stack_like_carla",
    "raw_tokens": {},
    "generation": {
      "generation_seed": 42,
      "noise_profile": "v0_1_moderate"
    }
  },
  "meta": {
    "coordinate_frame": "world",
    "distance_unit": "meter",
    "time_unit": "second",
    "speed_unit": "m/s",
    "angle_unit": "radian",
    "frequency_hz": 2.0,
    "duration": 5.0
  },
  "frames": [],
  "events_observed": [],
  "oracle": {
    "visible_to_diagnosis": false,
    "fault_type": "control_delay",
    "root_module": "control",
    "fault_start_time": 2.54
  }
}
```

诊断系统只能读取 `observed_view()`，其中不包含 `oracle`。`oracle` 只能由 `experiments/run_eval.py` 在评估时读取。

### 输出

每次实验输出到：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/
```

目录结构：

```text
metrics/              # 每个场景的指标 evidence
diagnoses/            # 每个场景的结构化诊断结果
reports/              # 每个场景的 Markdown 报告，内嵌图链接
figures/              # BEV、timeline、confusion matrix SVG
tables/               # errors.csv、leaderboard.csv
failure_samples/      # 每个故障/错误场景的 failure_sample.json
run_report.md         # 一次实验的总览报告
artifacts_manifest.json
eval.csv              # 场景级评估结果
failure_samples.jsonl # 可回流的失败样本总表
summary.json          # 汇总指标
confusion_matrix.json # 混淆矩阵
run_meta.json         # run_id、method、dataset、seed、git_commit 等复现信息
```

## 真实数据兼容策略

手工样本不是另起一套玩具格式，而是 canonical schema 的轻量模拟器。后续真实数据只通过 adapter 进入同一个 `ScenarioRecord`。

```text
nuScenes / nuPlan / CARLA / SafeBench / manual_json
        |
        v
adapter
        |
        v
Canonical ScenarioRecord
        |
        v
metrics + agents
        |
        v
diagnosis.json / report.md
        |
        v
evaluator reads oracle only
```

当前三类 manual subset：

- `perception_like_nuscenes`：有 ego、actors_gt、perception detections，planning/control 可缺失。
- `planning_like_nuplan`：有 ego、actors_gt、map、planning trajectory，perception/control 可缺失。
- `full_stack_like_carla`：有 ego、actors_gt、perception、planning、control、events_observed。

真实数据边界：

- `actors_gt_source` 必须标注来源，可选 `simulation`、`dataset_annotation`、`offline_reconstruction`、`unavailable`。
- `planning.trajectory_source` 必须标注来源，可选 `expert_future`、`offline_planner`、`perturbed_planner`、`model_prediction`、`unavailable`。
- nuScenes metadata-only 阶段不声称完成图像/点云 detector 评估。
- nuPlan 的 `scenario_tag` 只能作为上下文或抽样条件，不能作为 `fault_type` 或 `root_module`。

## 架构

```text
数据适配层
  -> 统一日志 Schema 层
  -> 指标工具层
  -> 多 Agent 诊断层
  -> 报告与评估层
```

多 Agent 诊断层采用显式 fan-out/fan-in 图：

```text
Metric Agent -> Scene Agent ------------------+
             -> Perception Agent --+          |
             -> Planning Agent ----+-> Root Cause Agent
             -> Control Agent -----+          |
```

完整状态、oracle 隔离和测试方法见 [docs/multi_agent_graph.md](docs/multi_agent_graph.md)。

### 数据适配层

负责把不同来源的数据统一转换为 `ScenarioRecord`。当前已有：

- `ManualAdapter`
- `NuScenesAdapter`，metadata 5-sample smoke 版本
- `NuPlanAdapter`，SQLite 5-scenario smoke 版本
- nuPlan planning perturbation benchmark，基于真实 scene 生成 5 对 opaque benign/collision 轨迹样本

### 指标工具层

第一版诊断判断主要来自确定性工具，不依赖 LLM。

已实现工具：

- TTC 曲线、min TTC、TTC violation。
- ego 与关键目标最小距离。
- 规划轨迹与障碍物 bbox 碰撞检测。
- 感知漏检、误检、类别混淆、置信度突降。
- 控制延迟检测。
- comfort 指标：acceleration、jerk、yaw rate。
- evidence coverage / correctness / hallucination rate 计算。

待补充工具：

- route progress、lane deviation、规则违反的更完整实现。

### 多 Agent 诊断层

第一版要避免“多个大模型自由聊天”。Agent 应该是结构化模块：

| Agent | 输入 | 输出 |
| --- | --- | --- |
| Scene Agent | observed frames、events、map | 异常时间线 |
| Metric Agent | ScenarioRecord observed view | metrics evidence |
| Perception Agent | perception evidence | 感知诊断 |
| Planning Agent | planning evidence、TTC、collision | 规划诊断 |
| Control Agent | control evidence、ego response | 控制诊断 |
| Root Cause Agent | 各模块诊断结果 | 候选根因 Top-K |
| Report Agent | 候选根因、evidence | 工程师报告 |

模块 Agent 第一版应保持纯规则可运行。LLM 默认关闭，后续只在 Root Cause Agent 和 Report Agent 中作为可选证据组织工具。

## 快速开始

当前建议直接使用已有 `yolo` 环境。

```bash
cd /home/lzx/Zhijia-Guardian
conda activate yolo
pip install -e ".[dev]"
```

需要运行 Single-LLM 时再安装小型可选依赖，不会重复安装 PyTorch：

```bash
pip install -e ".[dev,llm]"
```

最短启动方式：

```bash
./backend.sh
./frontend.sh
```

其中 `backend.sh` 默认生成/刷新手工样本并跑 rule-only、Multi-Agent + Tools 两组输出；`frontend.sh` 会启动只读 Streamlit 工作台。Single-LLM 默认不运行，避免意外产生 API 费用。

CARLA 0.9.15 已接入独立离线链路。运行时和数据都放在 `/data5`，不会进入 Git：

```bash
./scripts/setup_carla_runtime.sh
./carla.sh
```

另开终端记录真实仿真基础日志并生成 30 条故障集：

```bash
conda run -n yolo python scripts/record_carla_base_scenarios.py \
  --count 5 --frames 80 --town Town10HD_Opt --seed 42 --no-rendering \
  --output-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1

conda run -n yolo python scripts/generate_carla_fault_benchmark.py \
  --base-log-dir /data5/lzx_data/Zhijia-Guardian/datasets/carla/base_v0_1 \
  --output-root /data5/lzx_data/Zhijia-Guardian/datasets/carla/fault_benchmark_v0_1 \
  --clean
```

完整安装、兼容补丁、运行限制和复现命令见 [docs/carla_runtime.md](docs/carla_runtime.md)。

生成两条 CARLA 典型案例视频：

```bash
conda run -n yolo python scripts/render_carla_case_videos.py
```

输出位于 `/data5/lzx_data/Zhijia-Guardian/outputs/case_videos/carla_v0_1/`，包括感知漏检和
规划碰撞风险两组成对回放。仓库内可直接查看的副本位于 [`demo/`](demo/)。

录制真正的 CARLA 3D RGB 闭环案例：

```bash
CARLA_RENDER_MODE=xvfb ./carla.sh
conda run -n yolo python scripts/capture_carla_3d_case_videos.py
```

输出为 `demo/03_carla_3d_normal_stop.mp4` 和 `demo/04_carla_3d_control_delay.mp4`。

生成 6 个 canonical demo：

```bash
python scripts/generate_canonical_demo.py
```

生成真实数据 smoke test：

```bash
python scripts/run_real_smoke_test.py
```

生成 nuPlan 真实场景轨迹扰动集：

```bash
python scripts/generate_nuplan_perturbation.py --pairs 5 --seed 42 --clean
```

运行 nuScenes 真实前视图 detector 和无标签诊断：

```bash
conda run -n yolo python scripts/run_nuscenes_yolo_benchmark.py --clean

conda run -n yolo python experiments/run_diagnosis.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_v0_1/canonical/scenarios.jsonl \
  --run-id nuscenes_real_yolo_v0_1_multi_agent \
  --method multi_agent_tools
```

该入口不会读取或伪造 oracle，因此只输出诊断假设，不生成 Accuracy/F1。详细结果、投影关联方式和
限制见 [docs/nuscenes_real_yolo_v0_1.md](docs/nuscenes_real_yolo_v0_1.md)，H.264 视频位于
[`demo/real_nuscenes/`](demo/real_nuscenes/)。

运行 nuScenes 六相机真实场景 detector、距离分桶评估和同步视频：

```bash
conda run -n yolo python scripts/run_nuscenes_multicamera_benchmark.py --clean

conda run -n yolo python experiments/run_diagnosis.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/yolo_multicam_v0_2/canonical/scenarios.jsonl \
  --run-id nuscenes_real_multicam_v0_2_multi_agent \
  --method multi_agent_tools
```

默认抽取两个真实 scene 的六路相机，共 12 个 canonical 片段。结果说明见
[docs/nuscenes_real_multicam_v0_2.md](docs/nuscenes_real_multicam_v0_2.md)，H.264 六视角视频位于
[`demo/real_nuscenes_multicam/`](demo/real_nuscenes_multicam/)。

让 Qwen3.7-Plus 直接复核真实原始帧：

```bash
# 不调用 API，只检查每个场景选中的 8 张原图和哈希
conda run -n yolo python experiments/run_visual_review.py \
  --prepare-only --mode direct_vlm \
  --run-id nuscenes_real_qwen37_direct_v0_1_prepare

# 配置 DASHSCOPE_API_KEY 后，先只调用 1 个场景
conda run -n yolo python experiments/run_visual_review.py \
  --enable-vlm --limit 1 --mode direct_vlm \
  --run-id nuscenes_real_qwen37_direct_v0_1
```

该结果按 `visual_review_v1` 保存为旁路输出，默认不参与确定性 Root Cause 排序。两种实验模式和
能力边界见 [docs/qwen_visual_review.md](docs/qwen_visual_review.md)。

生成当前 noisy manual benchmark：

```bash
python scripts/generate_manual_scenarios.py \
  --version v0_3 \
  --output /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --count 72 \
  --seed 42 \
  --clean
```

运行 Rule-only baseline：

```bash
python experiments/run_eval.py \
  --method rule_only \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_rule_seed42 \
  --seed 42
```

运行 Multi-Agent + Tools：

```bash
python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_multi_agent_seed42 \
  --seed 42
```

检查单个场景的图拓扑和 Agent 执行轨迹：

```bash
python scripts/inspect_diagnosis_graph.py \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --scenario-id manual_v0_3_000001
```

运行 Single-LLM 前，在本机 shell 配置密钥。不要把密钥写入 YAML 或提交到 Git：

```bash
export OPENAI_API_KEY='your-api-key'
# 使用兼容服务时可选：export OPENAI_BASE_URL='https://example.com/v1'

python experiments/run_eval.py \
  --method single_llm \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_single_llm_smoke5_seed42 \
  --seed 42 \
  --enable-llm \
  --limit 5
```

也可以通过启动脚本做 5 样本连通性验证：

```bash
RUN_SINGLE_LLM=1 SINGLE_LLM_LIMIT=5 ./backend.sh
```

当前仓库也提供 DeepSeek 官方 OpenAI-compatible 接口配置。项目根目录 `.env` 已被 Git 忽略：

```dotenv
DEEPSEEK_API_KEY='your-api-key'
DEEPSEEK_BASE_URL='https://api.deepseek.com'
DEEPSEEK_MODEL=deepseek-v4-pro
```

```bash
python experiments/run_eval.py \
  --method single_llm \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_3 \
  --run-id manual_v0_3_single_llm_deepseek_v4_pro_seed42 \
  --llm-config configs/llm_deepseek.yaml \
  --enable-llm \
  --resume
```

DeepSeek 使用 Chat Completions `json_object`，返回值再由本地 Pydantic 严格校验。`--resume` 会复用 run 目录中已经完成的逐场景 metrics/diagnosis，避免 API 中断后重复调用和计费。通过启动脚本运行时设置 `LLM_CONFIG=configs/llm_deepseek.yaml`。

Single-LLM 只接收 `observed_view()` 派生的聚合摘要，以及去掉 `supports`、`contradicts` 和自由文本描述后的 metrics。模型输出中的每条 claim 必须引用 `evidence_id`；不存在或不支持结论的引用会计入 hallucination rate。完整设计见 [docs/single_llm_baseline.md](docs/single_llm_baseline.md)。

运行测试：

```bash
python -m pytest
```

启动只读工作台：

```bash
streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=8501
```

## 当前实验结果

完整实验流程、五 seed 稳定性、时序因果消融、CARLA/nuPlan/nuScenes 分层结果、延迟和有效性威胁见
[docs/完整实验分析报告.md](docs/完整实验分析报告.md)。机器可读表格位于
[`docs/tables/`](docs/tables/)。

三种方法已在完全相同的 72 个 manual v0.3 场景、seed 42 和 commit `0c7e220` 上完成统一评估：

| 方法 | Fault Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Single-LLM / DeepSeek V4 Pro | 0.9861 | 0.9861 | 0.9861 | 0.8167 | 0.3333 | 0.6250 | 0.1271 |
| Rule-only | 0.9028 | 0.9066 | 0.9028 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |

正式比较输出位于 `/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_3_seed42/`，包含 `comparison.csv`、`comparison.json` 和 `comparison.md`。生成命令：

```bash
python experiments/compare_runs.py \
  /data5/lzx_data/Zhijia-Guardian/outputs/runs/manual_v0_3_rule_seed42 \
  /data5/lzx_data/Zhijia-Guardian/outputs/runs/manual_v0_3_single_llm_deepseek_v4_pro_seed42 \
  /data5/lzx_data/Zhijia-Guardian/outputs/runs/manual_v0_3_multi_agent_seed42 \
  --output-dir /data5/lzx_data/Zhijia-Guardian/outputs/comparisons/manual_v0_3_seed42
```

v0.3 先生成物理时序，再按 TTC 首次跌破阈值确定风险时刻；上游感知/规划故障必须早于下游控制异常。Rule-only 的 7 条错误全部是把复合故障的下游 `control_delay` 当成根因，Multi-Agent 用模块分诊和时序因果排序恢复了上游根因。Single-LLM 分类接近满分，但 Evidence Correctness 仅 0.6250、Hallucination Rate 为 0.1271，因此不能只用分类准确率声称报告可信。完整定义见 [docs/manual_benchmark_v0_3.md](docs/manual_benchmark_v0_3.md)。

CARLA v0.1 已在 5 条真实仿真基础日志上派生 30 条离线信号级故障样本：

| 方法 | Fault Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Rule-only | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

比较输出位于 `/data5/lzx_data/Zhijia-Guardian/outputs/comparisons/carla_fault_v0_1_seed42/`。
两种方法都满分说明 v0.1 注入与规则仍一一对应；它是 CARLA 数据链路集成测试，不是多智能体
优越性证据。

CARLA v0.2-riskfix 已加入随机强度、边界正常样本、时序复合故障和 parent-group 隔离 split，并
修正历史版本将最低 TTC 时刻误作控制延迟起点的问题。正式 commit `e6fe4b8` 的结果为：

| 方法 | Fault Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Multi-Agent w/o temporal | 0.8000 | 0.8056 | 0.8000 | 1.0000 | 0.0000 |
| Rule-only | 0.8000 | 0.8056 | 0.8000 | 1.0000 | 0.0000 |

完全隔离的 10 条 test parent 得到相同结果。Rule-only 和无时序消融的错误全部来自将上游感知故障误判为
下游 control delay；Multi-Agent 的时序根因排序正确恢复了上游根因。该结果证明的是受控复合
故障上的协作机制价值，不代表自然事故上的普遍提升。完整定义见
[docs/carla_benchmark_v0_2.md](docs/carla_benchmark_v0_2.md)。

CARLA closed-loop v0.1 进一步实际重跑了 5 个父场景的 normal、control-delay 和
planning-fault，共 15 条真实动力学日志。正式 commit `80bacf9`：

| 方法 | Fault Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Rule-only | 0.6667 | 0.5556 | 0.6667 | 1.0000 | 0.0000 |

5 条 normal 均无碰撞，5 条控制延迟和 5 条危险规划均产生真实碰撞。Rule-only 将 planning
fault 误判为 control delay；Multi-Agent 根据危险规划早于控制失效的时间关系恢复根因。完整
定义见 [docs/carla_closed_loop_v0_1.md](docs/carla_closed_loop_v0_1.md)。

CARLA extreme-weather v0.1 在重雨、浓雾和夜间风暴中各实跑 normal、感知置信度下降、危险规划和
控制延迟，共 12 条轨迹；`night_storm` 作为完整 held-out test：

| 方法 | Full Macro-F1 | Held-out Macro-F1 | Root Top-1 | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| Rule-only | 0.3750 | 0.3750 | 0.5000 | 1.0000 | 0.0000 |

规则方法把感知/规划上游故障误判为下游控制延迟；多 Agent 根据更早出现的模块证据恢复根因。
当前检测结果来自仿真标注，只能证明诊断机制兼容这些天气上下文，不能声称真实视觉模型具备
极端天气鲁棒性。数据生成命令和限制见
[docs/carla_extreme_weather_v0_1.md](docs/carla_extreme_weather_v0_1.md)。

nuScenes real CAM_FRONT + YOLO v0.1 在 5 个真实道路 scene 的 202 张关键帧上得到：annotation
recall `0.4706`、50 米内较大关键目标 recall `0.5391`、detection precision `0.7248`、匹配目标
类别准确率 `0.9290`。多 Agent 对 5 个片段都给出 `perception_miss` 主导的诊断假设，Planning 和
Control Agent 因真实字段缺失而跳过。由于 nuScenes 没有系统故障根因 oracle，这组结果不计算
Fault Macro-F1，也不声称“5/5 诊断正确”。完整说明见
[docs/nuscenes_real_yolo_v0_1.md](docs/nuscenes_real_yolo_v0_1.md)。

nuScenes six-camera YOLO v0.2 在 2 个真实道路 scene 的 486 张关键帧上进一步得到：annotation
recall `0.4845`、关键目标 recall `0.5525`、detection precision `0.7174`、匹配类别准确率
`0.9420`。距离分桶 recall 从 0-20m 的 `0.7261` 降至 40m+ 的 `0.2782`，说明诊断证据受真实
感知距离退化显著影响。12 个“场景×相机”片段均进入同一多 Agent 链路；该结果仍无 fault oracle，
不计算根因准确率。完整说明见
[docs/nuscenes_real_multicam_v0_2.md](docs/nuscenes_real_multicam_v0_2.md)。

注意：旧 manual v0.2 结果仍是 commit `48f0578` 的历史可复现结果。commit `0c7e220` 已完成
manual v0.3 重建和三方法刷新；当前结果不再混用旧 oracle 与新的首次 TTC 风险时间定义。

## 评估指标

诊断准确性：

- Fault Accuracy
- Fault Macro-F1
- Root Cause Top-1 Accuracy
- Module-level Accuracy
- Fault Start Time MAE
- Fault Start Time Coverage
- Fault Start Time MAE @ Correct Fault
- Fault Start Time Coverage @ Correct Fault

报告可信度：

- Evidence Coverage = 有 evidence_id 支撑的 claim 数 / 总 claim 数
- Hallucination Rate = 无 evidence_id 支撑或 evidence 不支持的 claim 数 / 总 claim 数
- Evidence Correctness = 被引用 evidence 中与 claim 一致的比例

效率指标：

- 单场景指标计算耗时。
- 报告生成耗时。
- 工程师需要继续查看的日志字段数量。

## 与已有工作的关系

DVCA、ACAV 等工作更偏仿真内嵌因果分析，通常需要重新运行 ADS、替换组件或修改消息流。本项目不直接挑战这类方法的严格因果性，而是关注更工程化的问题：

> 当异常日志已经存在时，如何在不重新运行完整仿真的情况下，快速生成候选根因、证据链和工程师可读报告？

与 Apollo / Autoware 等 debug 工具相比，本项目不是只做日志回放，而是在统一日志 schema 之上增加自动化指标计算、模块异常检查、候选根因排序、证据链组织和失败样本沉淀。

与直接使用 LLM 分析日志相比，本项目把确定性指标工具放在第一位。LLM 只能读取 evidence 和 observed summary，不能读取 oracle，也不能生成无证据 claim。

## 路线图

短期必须完成：

- 补齐 lane deviation / route progress / 规则违反等指标。
- 固化 Multi-Agent + Tools 的错误分析和阈值配置。
- 完善 `diagnosis.json`、`report.md` 和 claim/evidence 反查。
- 做固定 seed 的 100+ noisy manual test split。
- 打磨 Streamlit 工作台的筛选、错误样本复盘、failure sample 浏览和输出包浏览。

中期增强：

- Single-LLM baseline，用于对比 hallucination 和 evidence coverage。
- nuScenes / nuPlan 从 1 个 smoke sample 扩到 5 个样本。
- [已完成 v0.1] CARLA 离线日志生成、canonical adapter 与信号级故障注入。

暂缓：

- CARLA 实时闭环控制。
- SafeBench 大规模接入。
- DriveLM / DoTA / DADA / Bench2Drive 等扩展数据集。
- RLHF、SFT 或通用隐层特征解释。

## Git 规范

从现在开始，每完成一个相对独立模块就提交一次 commit。推荐节奏：

1. schema / adapter / dataset generator / metrics / baseline / agents / UI 分模块提交。
2. 每次提交前至少运行相关测试。
3. commit message 用动宾结构，例如 `Build rule-only diagnosis baseline`。
4. 大数据、模型权重、实验输出不进 git，统一放 `/data5/lzx_data/Zhijia-Guardian`。

## 目录结构

```text
configs/                 # 阈值、路径、LLM 开关
docs/                    # adapter contract 与真实数据字段映射
docs/output_contract.md  # 实验输出规范
docs/workbench.md        # Streamlit 工作台说明
docx/                    # 计划书、设计文档、todo
experiments/             # 实验 CLI 和 baseline 入口
scripts/                 # 数据生成与 smoke test 脚本
src/zhijia_guardian/     # 核心代码
tests/                   # pytest 测试
/data5/lzx_data/...      # 大数据和实验输出，不提交 git
```

## 复现实验备注

本仓库根目录的 `data/` 被 `.gitignore` 忽略，样例数据需要通过脚本重新生成。真实数据和实验输出默认放在 `/data5/lzx_data/Zhijia-Guardian`，不要提交到 git。
