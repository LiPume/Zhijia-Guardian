# 智驾卫士实现计划与 Todo

更新时间：2026-07-01

本 Todo 以 `/home/lzx/Zhijia-Guardian/docx/design.md` 的“0. 最终落地修订版”为准。

## 0. 当前固定决策

1. 开发环境直接使用 `yolo`，不再新建主环境 `car`。
2. 代码仓库：`/home/lzx/Zhijia-Guardian`。
3. 大数据根目录：`/data5/lzx_data/Zhijia-Guardian`。
4. 手工数据、真实数据 adapter、nuPlan 扰动、CARLA 闭环、极端天气 held-out 和 nuScenes 真实前视 detector 均已跑通；下一阶段做多相机/LiDAR 与多 seed 验证。
5. 主仓自建轻量诊断框架，不直接套用 SafeBench、DriveLM、carla_garage 等大仓库。
6. 外部框架后续放 `/data5/lzx_data/Zhijia-Guardian/third_party/`，主仓只写 adapter。
7. 手工样本必须是真实数据兼容的 Canonical Scenario 轻量模拟器，不允许另起玩具格式。
8. tools 和 agents 永远只读取 `ScenarioRecord` / observed view，不直接读取 nuScenes/nuPlan/CARLA 原始格式。
9. 从现在开始，每完成一个独立模块必须先跑相关验证，再提交 git commit，方便后续回溯。
10. MVP 保留显式 Pydantic DAG；只有需要人工中断恢复、持久化 checkpoint、跨进程重试或 time-travel 时才引入可选 LangGraph backend。
11. 多模态模型先作为 Visual Review sidecar 和 Direct-VLM baseline，不直接覆盖确定性根因结论。

## 0.1 当前可行性判断与路线收敛

结论：项目可行，但必须定位成“离线异常日志预诊断 + 证据链生成 + 工程师辅助排查”，不能包装成“自动完成最终事故定责”或“任意真实数据一接入就能给出根因真值”。

保留并优先推进：

- [x] Canonical Scenario schema + adapter contract：这是后续接真实数据不返工的核心。
- [x] observed view / oracle 隔离：这是保证实验可信度的第一优先级。
- [x] noisy manual benchmark：用于第一版可控根因评估，避免只做不可评价的真实数据展示。
- [x] Rule-only baseline：用于验证数据、指标和评估链路，也是 Multi-Agent 的下限。
- [x] Multi-Agent + Tools：第一版必须在 LLM 关闭时可运行，Agent 本质上是结构化诊断节点。
- [x] Streamlit 工作台：先只读 JSON 输出和实验结果，不接实时 CARLA。

需要后移或删减：

- [x] nuScenes / nuPlan 不作为第一版根因诊断主 benchmark，只做真实数据 schema smoke test 和小样本 adapter 验证。
- [x] CARLA 放到 Multi-Agent 和 UI 跑通之后再接；当前已完成 0.9.15 离线 v0.1，SafeBench 继续后移。
- [x] DriveLM / DoTA / DADA / Bench2Drive 暂不进 MVP，只作为论文扩展或报告模板参考。
- [x] 不做 SFT / RLHF / 隐层特征解释，这些会把项目从诊断产品拉偏到大模型训练。
- [x] 不承诺真实车企 NOA 私有日志，答辩时只说 schema 预留和 adapter 可扩展。

## 1. P0：仓库与环境准备

- [x] 在 `yolo` 环境补齐当前原型最小依赖：

```bash
conda activate yolo
pip install -e ".[dev]"
```

说明：当前已验证 `torch`、`cv2`、`pydantic`、`yaml`、`pytest` 可导入。`openai` 已作为 `llm` 可选依赖加入，不会重复安装 PyTorch；`shapely`、`plotly`、`langgraph`、`scikit-learn` 仍不作为 P0 强依赖。

- [x] 创建数据根目录：

```bash
mkdir -p /data5/lzx_data/Zhijia-Guardian/{datasets,outputs,models,cache,third_party}
mkdir -p /data5/lzx_data/Zhijia-Guardian/datasets/{manual_json,carla,safebench,nuplan_mini,nuscenes_mini}
mkdir -p /data5/lzx_data/Zhijia-Guardian/outputs/runs
```

- [x] 创建主仓代码目录：

```text
configs/
data/sample_scenarios/
src/schemas/
src/tools/
src/agents/
src/graph/
src/adapters/
src/utils/
experiments/baselines/
app/
prompts/
docs/
```

- [x] 新增 `configs/paths.yaml`，记录数据根目录和输出目录。
- [x] 新增 `configs/thresholds.yaml`，记录 TTC、漏检持续时间、控制延迟等阈值。
- [x] 新增 `configs/llm.yaml`，记录是否启用 LLM、模型名、温度、JSON 输出约束。
- [x] README 已说明大数据不放 git，实际位置在 `/data5/lzx_data/Zhijia-Guardian`。
- [x] `configs/llm.yaml` 第一版默认关闭 LLM：

```yaml
enabled: false
provider: openai
model: gpt-4o-mini
temperature: 0
json_mode: true
```

验收标准：

- [x] `conda activate yolo` 后能 `import torch, cv2, pydantic, yaml, pytest`。
- [x] `/data5/lzx_data/Zhijia-Guardian` 目录存在。
- [x] 主仓目录结构清晰，不把大数据提交进 git。

## 2. P-1：6 个 canonical demo 样本

- [x] 新增 `data/sample_scenarios/canonical_demo/`。
- [x] 写 6 个最小 demo JSON。
- [x] 每类 2 个：`perception_like_nuscenes`、`planning_like_nuplan`、`full_stack_like_carla`。
- [x] 每个 demo 都使用 `source/meta/frames/events_observed/oracle`。
- [x] 每个 demo 的 `oracle.visible_to_diagnosis=false`。

验收标准：

- [x] 6 个样本能通过 schema 校验。
- [x] 诊断入口只拿 observed view。
- [x] 评估入口才读 oracle。

## 3. P0：Canonical Scenario Schema + ManualAdapter

- [x] 实现 `src/schemas/scenario.py`。
- [x] 实现 `src/schemas/metrics.py`。
- [x] 实现 `src/schemas/diagnosis.py`。
- [x] 实现 `src/adapters/base_adapter.py`。
- [x] 实现 `src/adapters/manual_adapter.py`。
- [x] schema 使用 Pydantic，所有字段带类型、默认值和校验。
- [x] 支持读取单个 `.json` 场景和 `.jsonl` 批量场景。
- [x] 场景 schema 必须是 `ScenarioRecord`：`scenario_id/source/meta/frames/events_observed/oracle`。
- [x] 实现 `ScenarioRecord.observed_view()`，只返回诊断可见字段。
- [x] 实现 `load_oracle()`，只允许 `experiments/run_eval.py` 调用。
- [x] 增加 no-label-leakage 测试，确保诊断流程无法读取 `oracle`。

`ScenarioRecord` 顶层字段：

- [x] `scenario_id`
- [x] `source`
- [x] `meta`
- [x] `frames`
- [x] `events_observed`
- [x] `oracle`

`source` 最小字段：

- [x] `dataset`
- [x] `version`
- [x] `raw_log_id`
- [x] `raw_tokens`

`meta` 最小字段：

- [x] `coordinate_frame`
- [x] `distance_unit`
- [x] `time_unit`
- [x] `speed_unit`
- [x] `angle_unit`
- [x] `frequency_hz`
- [x] `duration`

`frames[*]` 最小字段：

- [x] `timestamp`
- [x] `ego`
- [x] `actors_gt`
- [x] `actors_gt_source`
- [x] `perception.available`
- [x] `perception.detection_source`
- [x] `perception.detections`
- [x] `planning.available`
- [x] `planning.trajectory_source`
- [x] `planning.trajectory`
- [x] `control.available`
- [x] `map.available`

字段取值约束：

- [x] `actors_gt_source` 只能是 `simulation`、`dataset_annotation`、`offline_reconstruction`、`unavailable`。
- [x] `planning.trajectory_source` 只能是 `expert_future`、`offline_planner`、`perturbed_planner`、`model_prediction`、`unavailable`。
- [x] `perception.detection_source` 只能是 `model_output`、`synthetic_from_annotation`、`dataset_prediction`、`unavailable`。
- [x] `scenario_id`、文件名、目录名不得包含 `fault_type` 或 `root_module`；允许 `manual_v0_1_000001.json`，禁止 `perception_miss_001.json`。

`oracle` 最小字段，仅评估可见：

- [x] `visible_to_diagnosis=false`
- [x] `fault_type`
- [x] `root_module`
- [x] `fault_start_time`
- [x] `fault_segment`

单位/坐标字段必须包含：

```json
{
  "coordinate_frame": "world",
  "distance_unit": "meter",
  "time_unit": "second",
  "speed_unit": "m/s",
  "angle_unit": "radian",
  "frequency_hz": 10
}
```

验收标准：

- [x] 能读取 1 个最小 demo 场景。
- [x] 缺字段时报清楚错误。
- [x] 能输出标准化内部 dict / Pydantic model。
- [x] Rule-only、Single-LLM、Multi-Agent 都只接收 observed view 或其派生 metrics；oracle 仅由 evaluator 读取。

## 4. P0.5：真实数据 Adapter Contract + Stub Adapters

- [x] 新增 `docs/adapter_contract.md`。
- [x] 新增 `docs/schema_mapping_nuscenes.md`。
- [x] 新增 `docs/schema_mapping_nuplan.md`。
- [x] 新增 `docs/output_contract.md`。
- [x] 新增 `docs/schema_mapping_carla.md`。
- [x] 实现 `src/adapters/nuscenes_adapter.py` 的 smoke 版本。
- [x] 实现 `src/adapters/nuplan_adapter.py` 的 smoke 版本。
- [x] 实现 `src/zhijia_guardian/adapters/carla_adapter.py`。

所有 adapter 必须实现：

```python
class BaseAdapter:
    def list_scenarios(self) -> list[str]:
        ...

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        ...

    def export_json(self, scenario_id: str, output_path: str) -> None:
        ...
```

验收标准：

- [x] `ManualAdapter`、`NuScenesAdapter`、`NuPlanAdapter` 都能输出同一个 `ScenarioRecord`。
- [x] 不同数据源缺失字段时，字段覆盖率报告能说明应跳过的 Agent。
- [x] 所有已实现工具只依赖 Canonical Scenario，不依赖原始数据格式。

## 5. P0.6：真实数据兼容的手工/脚本合成样本

- [x] 写 `src/adapters/manual_adapter.py` 或 `scripts/generate_manual_scenarios.py`。
- [x] 生成 60-100 个 Canonical Scenario JSON，先覆盖 5 类故障和 normal。
- [x] 手工样本必须通过 Canonical Scenario Schema 生成，不允许临时字段。
- [x] 所有生成样本记录 `generation_seed`、`noise_profile`、`scenario_family`、`difficulty`。
- [x] 生成脚本支持 `--seed`、`--count`、`--output`。
- [x] 手工样本保留 `source.raw_tokens` 字段，为后续真实数据 token 映射预留位置。
- [x] `scenario_id` 和文件名统一使用无标签格式，如 `manual_v0_1_000001`。

子集目录：

```text
manual_json/
  v0_1/
    perception_like_nuscenes/
    planning_like_nuplan/
    full_stack_like_carla/
```

子集要求：

- [x] `perception_like_nuscenes`：有 ego、actors_gt、actors_gt_source、perception.detections；planning/control 为 `available=false`。
- [x] `planning_like_nuplan`：有 ego、actors_gt、actors_gt_source、map、planning.trajectory_source、planning.trajectory；perception/control 可为 `available=false`。
- [x] `full_stack_like_carla`：有 ego、actors_gt、perception、planning、control、events_observed。
- [x] 每类样本都必须模拟真实数据可能出现的字段缺失。

样本分布：

| 类别 | 目标数量 |
| --- | ---: |
| `normal` | 当前 12，后续扩展 10-20 |
| `perception_miss` | 当前 12，后续扩展 15-20 |
| `perception_false_positive` | 当前 12，后续扩展 15-20 |
| `perception_confidence_drop` | 当前 12，后续扩展 10-15 |
| `planning_collision_risk` | 当前 12，后续扩展 15-20 |
| `control_delay` | 当前 12，后续扩展 15-20 |

必须加入噪声：

- [x] 时间噪声：fault_start_time、观测异常时间、风险出现时间加入 ±0.2s 偏移。
- [x] 感知噪声：confidence 随机波动。
- [x] 目标噪声：目标位置、速度轻微偏移。
- [x] 控制噪声：brake/throttle/steer 延迟和抖动。
- [x] 复合故障：感知轻微异常 + 规划响应不足。
- [x] 边界样本：TTC 接近阈值但不一定故障。
- [x] manual v0.3：按“首次 TTC 阈值穿越”重建时序一致的 72 条样本，并在 commit `0c7e220` 刷新三方法结果。

Demo 必做三例：

- [x] 感知漏检导致追尾风险。
- [x] 误检导致幽灵刹车。
- [x] 感知正常但规划危险。

验收标准：

- [x] 所有样本能通过 schema 校验。
- [x] 每个样本的 `oracle` 有真值 `fault_type`、`root_module`、`fault_start_time`。
- [x] 传给诊断函数/Agent 的对象中不含 `oracle`。
- [x] 三个 demo 有清晰时间线和可视化轨迹。

## 6. P0.7：真实数据最小 Adapter Smoke Test

目标：已经下载 nuScenes mini 和 nuPlan mini，因此在写大量 tools/agents 前，先验证 canonical schema 能否接真实数据。

- [x] 写 `src/adapters/nuscenes_adapter.py` 的最小只读版本。
- [x] 写 `src/adapters/nuplan_adapter.py` 的最小只读版本。
- [x] nuScenes mini 抽 1 个 sample 转 `ScenarioRecord`。
- [x] nuPlan mini 抽 1 个 scene/scenario 转 `ScenarioRecord`。
- [x] 输出到 `data/sample_scenarios/real_smoke_test/`。
- [x] 不跑诊断，不计算 Fault Macro-F1，只做 schema validate、observed view 检查、字段覆盖率统计。

nuScenes smoke test 要求：

- [x] `actors_gt_source=dataset_annotation`。
- [x] 当前 metadata-only 状态下 `perception.available=false`。
- [x] `planning.available=false`。
- [x] `control.available=false`。
- [x] 不声称已经跑图像/点云 detector。

nuPlan smoke test 要求：

- [x] `actors_gt_source=dataset_annotation`。
- [x] `control.available=false`。
- [x] `planning.trajectory_source=expert_future` 或 `unavailable`。
- [x] `scenario_tag` 只能进入 `events_observed.context_tags` 或抽样条件，不能进入 `oracle`。
- [x] nuPlan 危险与安全扰动轨迹均标注 `planning.trajectory_source=perturbed_planner`，避免 provenance 直接泄漏标签。

验收标准：

- [x] 两个真实样本都能通过 schema 校验。
- [x] 两个真实样本的 observed view 不包含 `oracle`。
- [x] 输出字段覆盖率报告，说明哪些 Agent 会自动跳过。

## 7. P1：指标工具层

实现文件：

- [x] `src/tools/ttc.py`
- [x] `src/tools/collision.py`
- [x] `src/tools/perception_eval.py`
- [x] `src/tools/planning_eval.py`
- [x] `src/tools/control_eval.py`

具体指标：

- [x] TTC 曲线、min TTC、TTC violation 起止时间。
- [x] ego 与目标最小距离。
- [x] 规划轨迹与障碍物 bbox/轨迹碰撞检测。
- [x] 车辆碰撞几何使用带长宽/yaw 的矩形间距，不再用会误伤相邻车道的圆形包络近似。
- [x] 感知漏检检测：GT 存在但 perception 缺失。
- [x] 感知误检检测：perception 存在但 GT 不存在。
- [x] 类别混淆检测：GT 类别与 detection 类别不一致。
- [x] 置信度突降检测：关键目标 confidence 下降。
- [x] 控制延迟检测：风险/规划要求制动但 brake 延迟。
- [x] 舒适性辅助指标：acceleration、jerk、yaw rate。
- [x] 每个指标发现都生成结构化 evidence。

Evidence 格式：

```json
{
  "evidence_id": "E_TTC_001",
  "metric_name": "min_ttc",
  "value": 0.92,
  "threshold": 1.5,
  "time": 4.6,
  "supports": ["planning_collision_risk", "control_delay"],
  "description": "min TTC below threshold"
}
```

验收标准：

- [x] 对每个场景输出 `metrics.json`。
- [x] 指标工具不依赖 LLM。
- [x] 每个指标都有单元测试或至少 demo 验证样例。
- [x] 每条 evidence 有唯一 `evidence_id`。

## 8. P1：Rule-only baseline

- [x] 实现 `experiments/baselines/rule_only.py`。
- [x] 用固定规则直接输出故障类型、根因模块、故障开始时间。
- [x] 实现 `experiments/metrics.py`。
- [x] 实现 `experiments/run_eval.py`。
- [x] `experiments/run_eval.py` 是唯一读取 `oracle` 的评估入口。
- [x] 支持 `--method`、`--dataset`、`--run-id`、`--seed`、`--config`。
- [x] 每次实验输出到 `/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/`。
- [x] 每次实验写入 `run_meta.json`。

`run_meta.json` 字段：

- [x] `run_id`
- [x] `method`
- [x] `dataset`
- [x] `threshold_config`
- [x] `llm_config`
- [x] `git_commit`
- [x] `seed`
- [x] `created_at`

评估指标：

- [x] Fault Accuracy。
- [x] Fault Macro-F1。
- [x] Root Cause Top-1 Accuracy。
- [x] Module-level Accuracy。
- [x] Fault Start Time MAE。
- [x] Fault Start Time Coverage。
- [x] Fault Start Time MAE @ Correct Fault。
- [x] Fault Start Time Coverage @ Correct Fault。
- [x] Evidence Coverage。
- [x] Evidence Correctness。
- [x] Hallucination Rate。

报告质量指标公式：

```text
Evidence Coverage = 有 evidence_id 支撑的结论数 / 总结论数
Evidence Correctness = 被引用证据中 supports 覆盖结论标签且 contradicts 不包含结论标签的证据数 / 被引用证据总数
Hallucination Rate = 无 evidence_id 支撑、evidence_id 不存在、或全部被引用证据均不支持/反驳该结论的结论数 / 总结论数
```

验收标准：

- [x] 能对 60-100 个手工样本跑出 CSV。
- [x] 能输出混淆矩阵。
- [x] Rule-only 作为后续多 Agent 的下限。
- [x] 重复相同 seed 和配置能得到相同结果。

## 9. P2：Multi-Agent + Tools 诊断流程

说明：当前已先实现无额外依赖的纯规则 `diagnosis_graph.py`，后续如确实需要再替换/包一层 LangGraph。第一版不强制安装 `langgraph`。

框架 commit `838ba17` 已将顺序函数升级为显式 Pydantic DAG。当前图已满足 fan-out/fan-in、
条件跳过、完整 trace 和 oracle 隔离需求，暂不为“使用框架”而额外引入 LangGraph 依赖。
决策与迁移门槛见 `docs/orchestration_decision.md`。

实现文件：

- [x] `src/zhijia_guardian/agents/scene_agent.py`
- [x] `src/zhijia_guardian/agents/metric_agent.py`
- [x] `src/zhijia_guardian/agents/perception_agent.py`
- [x] `src/zhijia_guardian/agents/planning_agent.py`
- [x] `src/zhijia_guardian/agents/control_agent.py`
- [x] `src/zhijia_guardian/agents/root_cause_agent.py`
- [x] `src/zhijia_guardian/agents/report_agent.py`
- [x] `src/zhijia_guardian/graph/diagnosis_graph.py`
- [x] `scripts/inspect_diagnosis_graph.py`

流程：

```text
parse_scenario
  -> calculate_metrics
  -> perception_diagnosis
  -> planning_diagnosis
  -> control_diagnosis
  -> root_cause_analysis
  -> report_generation
  -> failure_sample_builder
```

要求：

- [x] 每个 Agent 输入输出都是 JSON/Pydantic。
- [x] 模块 Agent 先用规则，不依赖 LLM。
- [x] MVP 的 Root Cause Agent 固定使用 evidence + 时序因果规则；不接自由式 LLM，避免把不可复现输出混入主方法。
- [x] MVP 的 Report Agent 使用确定性模板；LLM 报告仅保留为可选实验，不作为第一版验收项。
- [x] 无证据时必须输出 `uncertain` 或 `skipped`，不能硬猜。
- [x] 第一版默认 LLM 关闭，Multi-Agent + Tools 必须在纯规则模式下可运行。
- [x] 模块 Agent 严禁读取 `oracle`。
- [x] 图初始化从 `observed_view()` 重建 ScenarioRecord，传给 Agent 的对象中 `oracle=None`、`source.generation={}`。
- [x] 图状态显式记录 `metrics/module_diagnoses/trace/executed_nodes/diagnosis`。
- [x] Perception/Planning/Control 构成 fan-out，Root Cause 构成 fan-in，并校验依赖和执行顺序。
- [x] 预计算 metrics 与 scenario ID 不一致时直接拒绝执行。
- [x] 完成 LangGraph 引入评审：当前不新增依赖，保留可选 backend 迁移边界。
- [ ] 出现人工审核暂停/恢复需求时，实现 LangGraph checkpoint + interrupt 原型。
- [ ] 若增加 LangGraph backend，必须与 Pydantic DAG 在冻结数据上做 `diagnosis_v1` parity test。

验收标准：

- [x] 每个场景输出 `diagnosis.json` 和 `report.md`。
- [x] 每个场景输出 BEV SVG 和 evidence timeline SVG。
- [x] 每次 run 输出 `run_report.md`、`artifacts_manifest.json`、`tables/errors.csv`、`tables/leaderboard.csv`。
- [x] Agent 每一步结果可以在 Streamlit 中展示。
- [x] 报告中每个结论能反查到 metrics evidence。
- [x] 每个 claim 都有 `claim_id` 和 `evidence_ids`。
- [x] Planning Agent 相邻车道误报回归已覆盖：control-delay/normal 不再被轨迹圆形包络误判为 planning risk。
- [x] 框架级测试覆盖 oracle 隔离、缺字段 skip、trace 顺序和“上游根因 + 下游控制延迟”复合故障。
- [x] commit `838ba17` 回归：manual v0.3 72 条与 CARLA closed-loop 15 条的 Accuracy/Macro-F1/Root Top-1 均保持 1.0000。
- [x] `diagnosis_v1`、`diagnosis_report_v1` 和 `failure_sample_v1` 输出契约已固定，并可导出 JSON Schema。
- [x] 新增 `visual_review_v1`：固定原图哈希、采样帧、模型信息、视觉观察和无 oracle/annotation 边界。

当前 72 个 manual v0.3 样本结果（seed 42，commit `0c7e220`）：

| 方法 | Fault Accuracy | Macro-F1 | Root Top-1 | Time Coverage | Time MAE@Correct | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Single-LLM / DeepSeek V4 Pro | 0.9861 | 0.9861 | 0.9861 | 0.8167 | 0.3333 | 0.6250 | 0.1271 |
| Rule-only | 0.9028 | 0.9066 | 0.9028 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |

说明：Multi-Agent 的满分是可控 synthetic benchmark 上的机制验证，不代表自然事故泛化。
Single-LLM 分类准确，但幻觉率仍高于 0.10 目标，产品默认保持 LLM 关闭。

## 10. P2：Single-LLM baseline

- [x] 实现 `src/zhijia_guardian/baselines/single_llm.py`，CLI 保留在 `experiments/run_eval.py`。
- [x] 输入为场景摘要 + 指标摘要。
- [x] 输入只能来自 observed view 和 metrics，不能包含 `oracle`。
- [x] API 输入删除 metrics 的 `supports`、`contradicts` 和自由文本描述，避免规则标签提示答案。
- [x] 输出同样的 `diagnosis.json` 格式。
- [x] 与 Rule-only、Multi-Agent + Tools 统一评估。
- [x] 默认关闭 LLM，CLI 必须显式传 `--enable-llm`；测试使用注入式假客户端，不伪造真实 API 实验结果。
- [x] API key 只从配置指定的环境变量读取；OpenAI 使用 `OPENAI_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`，均不落盘到实验输出、不进 Git。
- [x] 新增 `configs/llm_deepseek.yaml`，支持 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。
- [x] DeepSeek 使用 Chat Completions `json_object`，本地 Pydantic 校验，不伪装成 OpenAI Responses 原生 schema。
- [x] API 实验支持 `--resume`，逐场景复用已完成输出，避免中断后重复计费。
- [x] DeepSeek 真实 5 样本 smoke test 已完成：Accuracy 0.4000、Root Top-1 0.6000、Hallucination Rate 0.1467。
- [x] DeepSeek 在 manual v0.3 正式 72 样本完成评估：Accuracy/Macro-F1 0.9861，Evidence Correctness 0.6250，Hallucination Rate 0.1271。

验收标准：

- [x] 已在相同 72 样本、seed 42、commit `0c7e220` 上完成 v0.3 三方法结果对比。
- [x] 新增 `experiments/compare_runs.py`，输出 comparison CSV/JSON/Markdown 并校验场景集合一致。
- [x] 能统计 hallucination rate；无效 evidence 引用已有自动测试。

## 11. P3：Streamlit 工作台

实现文件：

- [x] `app/streamlit_app.py`
- [x] `src/zhijia_guardian/workbench/run_loader.py`
- [x] `docs/workbench.md`

页面功能：

- [x] 场景选择。
- [x] 轨迹/BEV 图。
- [x] evidence timeline。
- [x] Agent 诊断链路。
- [x] 根因排序。
- [x] 诊断报告。
- [x] 实验结果表。

验收标准：

- [x] 三个 demo 能在界面完整展示。
- [x] 点击一个场景能看到指标、根因和报告。
- [x] 页面不依赖 CARLA 实时运行，只读 JSON 输出。

## 12. P3：失败样本包

- [x] 实现 `src/zhijia_guardian/experiments/failure_sample_builder.py` 对应工具函数。
- [x] 输出 `failure_samples/{scenario_id}/failure_sample.json`。
- [x] 输出 `failure_samples.jsonl`。
- [x] 输出 `tables/failure_samples.csv`。

字段：

- [x] `scenario_id`
- [x] `predicted_fault_type`
- [x] `predicted_root_module`
- [x] `predicted_fault_start_time`
- [x] `evidence`
- [x] `wrong_reasoning`
- [x] `correct_reasoning`
- [x] `tags`
- [x] `recommended_data`
- [x] `regression_test_config`
- [x] `scenario_record_hash`

验收标准：

- [x] 每个故障场景都能生成可回流样本。
- [x] 可用于后续 SFT/DPO/RLHF，不实际训练。

## 13. P4：nuScenes / nuPlan 小样本真实数据接入

- [x] 优先测试 nuScenes mini 下载/读取链路。
- [x] 已知 `https://www.nuscenes.org/data/v1.0-mini.tgz` 可 HEAD 访问，大小约 3.88GiB/3.97GB；不要误以为能只下载 5 个独立小文件。
- [x] 已下载完整 `v1.0-mini.tgz` 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/`。
- [x] 已只解出 metadata 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini/`，不解图像/点云媒体文件。
- [x] 已确认 metadata 表：10 个 scene、404 个 sample、31206 条 sample_data/ego_pose、18538 条 sample_annotation。
- [x] 已测试 nuPlan AWS/S3 下载链路，`motional-nuplan` S3 源站可直接访问。
- [x] 已下载 nuPlan mini DB：`/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/raw/nuplan-v1.1_mini.zip`，大小 `8550100030` bytes。
- [x] 已下载 nuPlan maps：`/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/raw/nuplan-maps-v1.0.zip`，大小 `971557640` bytes。
- [x] 已对 nuPlan mini DB 和 maps 执行 `unzip -t`，均无压缩错误。
- [x] 已抽检 nuPlan mini：zip 内含 64 个 SQLite `.db`；样本 DB 表包括 `ego_pose`、`lidar_pc`、`lidar_box`、`track`、`scene`、`scenario_tag`、`traffic_light_status`。
- [x] 暂不下载 nuPlan mini sensor blobs；单个相机/激光 zip 往往几十 GB，MVP 先使用结构化 DB + maps。
- [x] 当前 metadata-only 阶段无需安装 `nuscenes-devkit`，已在 mapping 文档记录；后续若用官方 API/媒体再安装。
- [x] 扩展 `src/adapters/nuscenes_adapter.py`：从 1 个 smoke sample 扩到 5 个 sample。
- [x] 当前 metadata-only 阶段输出 `perception.available=false`；若生成 synthetic detections，必须写 `perception.detection_source=synthetic_from_annotation`。
- [x] 扩展 `src/adapters/nuplan_adapter.py`：从 1 个 smoke scene/scenario 扩到 5 个 scenario。
- [x] nuPlan adapter 中 `scenario_tag` 只能进入 `events_observed.context_tags` 或抽样条件，不能作为诊断 fault label；`control.available=false`，`planning.trajectory_source` 必须明确。
- [x] 更新 `docs/schema_mapping_nuscenes.md` 和 `docs/schema_mapping_nuplan.md` 的实际字段覆盖情况。

验收标准：

- [x] 5 个真实 nuScenes sample 可以转成 `ScenarioRecord`。
- [x] 5 个真实 nuPlan scenario 可以转成 `ScenarioRecord`。
- [x] 不改 tools/agents 即可进入 schema validate、可视化、基础风险指标流程。
- [x] 若未解图像/点云媒体，不宣称完成真实感知模型评估。
- [x] 缺失 planning/control 时自动跳过 Planning/Control Agent 或输出 unavailable。

## 14. P5：CARLA + ScenarioRunner 接入

- [x] 在 `/data5/lzx_data/Zhijia-Guardian/third_party/` 下准备 CARLA 0.9.15/ScenarioRunner v0.9.15。
- [x] ScenarioRunner 官方 `FollowLeadingVehicle_1` 完成 actor、场景树和 criteria smoke；stock 无 ego controller，结果为 TIMEOUT，不宣称 scenario success。
- [x] 写 `src/zhijia_guardian/adapters/carla_adapter.py`，oracle 仅从独立 label 目录显式合并。
- [x] 记录 ego、objects、合成 perception、停车 rollout、control、map 和 sensor events。
- [x] 转换成统一 ScenarioRecord JSONL。
- [x] 实现离线信号级故障注入：删除检测框、注入假目标、置信度下降、规划轨迹扰动、控制延迟。
- [x] 完成 1 组 control-delay 闭环动力学 demo：正常制动无碰撞，延迟 0.8 秒后发生追尾，并保存 RGB 视频和 manifest。
- [x] 把 control-delay 闭环扩到 5 个出生点，并实现 planning fault 闭环重跑；共 15 条，normal 5/5 无碰撞，两类 fault 10/10 碰撞。
- [x] CARLA v0.2 增加随机强度、边界样本、复合故障和 parent-group held-out split；50 条全量与 10 条隔离 test 均完成评估。
- [x] CARLA extreme-weather v0.1：重雨、浓雾、夜间风暴按天气整组划分，共 12 条真实 rollout。
- [x] 极端天气 held-out test：Multi-Agent Macro-F1 1.0000，Rule-only 0.3750；明确当前只验证诊断机制，不声称视觉 detector 天气鲁棒性。

验收标准：

- [x] 导出 5 个真实仿真父场景并派生 30 个 v0.1 场景。
- [x] CARLA 场景可复用同一套指标和 Agent；Rule/Multi-Agent 都完成统一评估。
- [x] 不要求 CARLA 实时接入 Streamlit，当前输出可由工作台离线读取。
- [x] 明确 v0.1 两种方法均满分只是集成测试结果，不作为多智能体提升证据。
- [x] 闭环 v0.1 完成全量与 parent-isolated test：Multi-Agent Macro-F1 1.0000，Rule-only 0.5556。
- [x] 极端天气 benchmark 的 normal 3/3 无碰撞，三类 fault 9/9 产生碰撞，train/val/test 天气互斥。
- [ ] 录制极端天气 RGB/点云，并接冻结 detector，形成真正的视觉天气退化 benchmark。

## 15. P5：SafeBench 子集 adapter

- [x] 研究 SafeBench 输出格式：planning `records.pkl` 只有 ego/criteria，不含 actors、planner output 和 control command。
- [x] 写 `src/zhijia_guardian/adapters/safebench_adapter.py`，只读严格 JSON export，不在诊断进程加载 pickle。
- [x] 选择官方 `human` scenario 1 / route 4 的 10 条 Town05 配置做兼容性实测。
- [x] 新增 `scripts/export_safebench_records.py` 和 `docs/schema_mapping_safebench.md`，固定降级字段映射。
- [x] 修正无模块证据时的根因输出：返回 `uncertain`，不再错误默认为 `normal`。

验收标准：

- [ ] 至少 10 个真实 SafeBench rollout 可以进入诊断流程：当前 0.9.15 在创建官方 actor 时 UE4 `SIGSEGV`，不伪造完成状态。
- [x] 不改 SafeBench 内核，只在主仓提供 export/adapter 和运行时兼容性记录。
- [x] 明确 SafeBench 原生输出不能做本项目 `root_module` 真值评估；完整根因链继续使用 CARLA 0.9.15 recorder。

## 16. P6：后续真实数据扩展

- [x] nuPlan mini：真实场景骨架 + 成对 perturbed planner 规划风险诊断；5 个父 scene/10 个样本，且不把 `scenario_tag` 当 fault label。
- [x] nuScenes mini metadata-only schema/annotation 映射。
- [x] 选择性解出 404 张真实 `CAM_FRONT` 关键帧；在 5 个 scene/202 帧上运行官方 YOLOv8n。
- [x] 实现 3D annotation 相机投影、2D IoU 关联、`NuScenesVisionAdapter` 和无 oracle 诊断入口。
- [x] 真实前视结果：annotation recall 0.4706、key actor recall 0.5391、detection precision 0.7248、matched class accuracy 0.9290。
- [x] 5 个真实片段均生成多 Agent 报告；Planning/Control 自动 skip，不计算伪造的 Fault Macro-F1。
- [x] 真实数据暴露并修复置信度自然波动误诊；manual v0.3、CARLA weather、closed-loop 回归保持 1.0000 Macro-F1。
- [x] 实现 Qwen3.7-Plus Visual Review Agent：`direct_vlm` 与 `vlm_with_tools` 两种模式。
- [x] 5 个真实片段均完成 prepare-only 输入校验，每段均匀抽 8 帧，未调用 API。
- [ ] 配置 `DASHSCOPE_API_KEY` 后各跑 1 个 direct/tools smoke，检查 token、延迟、JSON 合规和视觉幻觉。
- [ ] 增加人工视觉复核表后，比较 Direct-VLM、VLM+Tools 和当前 YOLO+Tools 的真实场景 usefulness。
- [ ] nuScenes 多相机/LiDAR 3D detector：替换当前单前视 COCO detector，并做距离分桶召回。
- [ ] DeepAccident mini：调研下载 20 个 accident/normal 场景，作为事故检测和 failure sample adapter 候选。
- [ ] DoTA/DADA：只作为 accident/anomaly 时间定位补充，不作为 root_module 诊断主数据。
- [ ] DriveLM：借鉴图式问答模板，不作为第一版主数据集。
- [ ] Bench2Drive/carla_garage：作为论文增强，不进入 MVP。

## 17. 暂缓事项

- [ ] 不复现 HE-Drive/ComDrive。
- [ ] 不复现 UniAD/VAD/SparseDrive/TransFuser。
- [ ] 不接 Autoware。
- [ ] 不做 RLHF 真训练。
- [ ] 不承诺真实车企 NOA 数据。
- [ ] 不做通用隐层特征解释。

## 18. 第一版最终交付物

- [x] 可运行代码仓库。
- [x] 60-100 个手工/脚本 JSON 场景。
- [x] 至少 3 个高质量 Demo。
- [x] 指标工具层。
- [x] Rule-only baseline。
- [x] Single-LLM baseline 代码、统一评估、防泄漏测试与真实 72 样本 DeepSeek API 结果。
- [x] Multi-Agent + Tools 主方法。
- [x] 实验结果 CSV。
- [x] 混淆矩阵和对比表。
- [x] BEV、timeline、confusion matrix 静态 SVG。
- [x] `run_report.md` 和 `errors.csv` 输出包。
- [x] Streamlit 工作台。
- [x] 自动诊断报告。
- [x] failure sample package。
- [x] failure sample 与诊断报告的版本化格式、oracle 边界和 JSON Schema。
- [x] 数据格式文档。
- [ ] 软著/答辩可用说明材料。

## 19. 第一版完成定义

当满足以下条件时，MVP 才算完成：

- [x] 在 `yolo` 环境下，一条命令能跑完整评估。
- [x] 三个 demo 在 Streamlit 中可展示。
- [x] 诊断报告中的每个结论都有 evidence。
- [x] Rule-only、Single-LLM、Multi-Agent + Tools 三组结果能通过统一 comparison 包对比。
- [x] 测试集有 Macro-F1、Root Cause Top-1、Time MAE、Evidence Coverage、Hallucination Rate。
- [x] 大数据和输出都落在 `/data5/lzx_data/Zhijia-Guardian`。
- [x] 通过 `tests/test_no_label_leakage.py`，证明诊断路径不能读取 `oracle`。

## 20. 开源项目式运行规范

后续代码必须做到像常见开源仓库一样可复现、可阅读、可一键运行。

- [x] `README.md` 提供环境安装、数据准备、生成样本、跑评估、启动 Streamlit 的命令。
- [ ] 所有核心逻辑在 `src/`，不把业务逻辑写死在 notebook。
- [ ] 所有脚本只做 CLI 入口，放在 `scripts/` 或 `experiments/`。
- [ ] 所有配置放在 `configs/`，不在代码中硬编码阈值、路径、LLM 开关。
- [x] 所有实验输出必须有 `run_id`。
- [x] 所有随机过程必须有 seed。
- [x] 所有数据读取必须区分 observed view 和 `oracle`。
- [x] 单元测试至少覆盖 schema、指标工具、无标签泄漏。

推荐命令形态：

```bash
conda activate yolo

python scripts/generate_manual_scenarios.py \
  --output /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_1 \
  --count 100 \
  --seed 42

python experiments/run_eval.py \
  --method rule_only \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_1 \
  --run-id 20260625_v0_1_rule \
  --seed 42

python experiments/run_eval.py \
  --method multi_agent_tools \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_1 \
  --run-id 20260625_v0_1_multi_agent \
  --seed 42

export OPENAI_API_KEY='your-api-key'
python experiments/run_eval.py \
  --method single_llm \
  --dataset /data5/lzx_data/Zhijia-Guardian/datasets/manual_json/v0_1 \
  --run-id 20260627_v0_1_single_llm \
  --seed 42 \
  --enable-llm \
  --limit 5

streamlit run app/streamlit_app.py
```
