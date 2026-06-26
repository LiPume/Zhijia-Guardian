# 智驾卫士实现计划与 Todo

更新时间：2026-06-26

本 Todo 以 `/home/lzx/Zhijia-Guardian/docx/design.md` 的“0. 最终落地修订版”为准。

## 0. 当前固定决策

1. 开发环境直接使用 `yolo`，不再新建主环境 `car`。
2. 代码仓库：`/home/lzx/Zhijia-Guardian`。
3. 大数据根目录：`/data5/lzx_data/Zhijia-Guardian`。
4. 第一版先不接 CARLA，先用手工/脚本 JSON 样本跑通完整诊断闭环。
5. 主仓自建轻量诊断框架，不直接套用 SafeBench、DriveLM、carla_garage 等大仓库。
6. 外部框架后续放 `/data5/lzx_data/Zhijia-Guardian/third_party/`，主仓只写 adapter。
7. 手工样本必须是真实数据兼容的 Canonical Scenario 轻量模拟器，不允许另起玩具格式。
8. tools 和 agents 永远只读取 `ScenarioRecord` / observed view，不直接读取 nuScenes/nuPlan/CARLA 原始格式。
9. 从现在开始，每完成一个独立模块必须先跑相关验证，再提交 git commit，方便后续回溯。

## 0.1 当前可行性判断与路线收敛

结论：项目可行，但必须定位成“离线异常日志预诊断 + 证据链生成 + 工程师辅助排查”，不能包装成“自动完成最终事故定责”或“任意真实数据一接入就能给出根因真值”。

保留并优先推进：

- [x] Canonical Scenario schema + adapter contract：这是后续接真实数据不返工的核心。
- [x] observed view / oracle 隔离：这是保证实验可信度的第一优先级。
- [x] noisy manual benchmark：用于第一版可控根因评估，避免只做不可评价的真实数据展示。
- [x] Rule-only baseline：用于验证数据、指标和评估链路，也是 Multi-Agent 的下限。
- [ ] Multi-Agent + Tools：第一版必须在 LLM 关闭时可运行，Agent 本质上是结构化诊断节点。
- [ ] Streamlit 工作台：先只读 JSON 输出和实验结果，不接实时 CARLA。

需要后移或删减：

- [ ] nuScenes / nuPlan 不作为第一版根因诊断主 benchmark，只做真实数据 schema smoke test 和小样本 adapter 验证。
- [ ] CARLA / SafeBench 放到 Multi-Agent 和 UI 跑通之后再接，避免环境成本拖慢 MVP。
- [ ] DriveLM / DoTA / DADA / Bench2Drive 暂不进 MVP，只作为论文扩展或报告模板参考。
- [ ] 不做 SFT / RLHF / 隐层特征解释，这些会把项目从诊断产品拉偏到大模型训练。
- [ ] 不承诺真实车企 NOA 私有日志，答辩时只说 schema 预留和 adapter 可扩展。

## 1. P0：仓库与环境准备

- [x] 在 `yolo` 环境补齐当前原型最小依赖：

```bash
conda activate yolo
pip install -e ".[dev]"
```

说明：当前已验证 `torch`、`cv2`、`pydantic`、`yaml`、`pytest` 可导入。`shapely`、`plotly`、`streamlit`、`langgraph`、`openai`、`scikit-learn` 暂不作为 P0 强依赖，等对应模块开工时再装，避免环境过重。

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
- [x] Rule-only 当前入口只接收 observed view；Single-LLM、Multi-Agent 后续沿用同一约束。

## 4. P0.5：真实数据 Adapter Contract + Stub Adapters

- [x] 新增 `docs/adapter_contract.md`。
- [x] 新增 `docs/schema_mapping_nuscenes.md`。
- [x] 新增 `docs/schema_mapping_nuplan.md`。
- [ ] 新增 `docs/schema_mapping_carla.md`。
- [x] 实现 `src/adapters/nuscenes_adapter.py` 的 smoke 版本。
- [x] 实现 `src/adapters/nuplan_adapter.py` 的 smoke 版本。
- [ ] 实现 `src/adapters/carla_adapter.py`。

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
- [ ] 若后续生成危险规划轨迹，必须标注 `planning.trajectory_source=perturbed_planner`。

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
- [x] 感知漏检检测：GT 存在但 perception 缺失。
- [x] 感知误检检测：perception 存在但 GT 不存在。
- [x] 类别混淆检测：GT 类别与 detection 类别不一致。
- [x] 置信度突降检测：关键目标 confidence 下降。
- [x] 控制延迟检测：风险/规划要求制动但 brake 延迟。
- [ ] 舒适性辅助指标：acceleration、jerk、yaw rate。
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

## 9. P2：LangGraph 多 Agent 诊断流程

实现文件：

- [ ] `src/agents/parser_agent.py`
- [ ] `src/agents/metric_agent.py`
- [ ] `src/agents/perception_agent.py`
- [ ] `src/agents/planning_agent.py`
- [ ] `src/agents/control_agent.py`
- [ ] `src/agents/root_cause_agent.py`
- [ ] `src/agents/report_agent.py`
- [ ] `src/graph/diagnosis_graph.py`

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

- [ ] 每个 Agent 输入输出都是 JSON/Pydantic。
- [ ] 模块 Agent 先用规则，不依赖 LLM。
- [ ] Root Cause Agent 可以调用 LLM，但必须只基于 evidence。
- [ ] Report Agent 可以调用 LLM，但输出中必须区分确定结论和不确定结论。
- [ ] 无证据时必须输出 `uncertain`，不能硬猜。
- [ ] 第一版默认 LLM 关闭，Multi-Agent + Tools 必须在纯规则模式下可运行。
- [ ] 模块 Agent 严禁读取 `oracle`。

验收标准：

- [ ] 每个场景输出 `diagnosis.json` 和 `report.md`。
- [ ] Agent 每一步结果可以在 Streamlit 中展示。
- [ ] 报告中每个结论能反查到 metrics evidence。
- [ ] 每个 claim 都有 `claim_id` 和 `evidence_ids`。

## 10. P2：Single-LLM baseline

- [ ] 实现 `experiments/baselines/single_llm.py`。
- [ ] 输入为场景摘要 + 指标摘要。
- [ ] 输入只能来自 observed view 和 metrics，不能包含 `oracle`。
- [ ] 输出同样的 `diagnosis.json` 格式。
- [ ] 与 Rule-only、Multi-Agent + Tools 统一评估。

验收标准：

- [ ] 能比较 Single-LLM 是否更容易漏证据或产生幻觉。
- [ ] 能统计 hallucination rate。

## 11. P3：Streamlit 工作台

实现文件：

- [ ] `app/streamlit_app.py`

页面功能：

- [ ] 场景选择。
- [ ] 轨迹/BEV 图。
- [ ] TTC、速度、confidence、brake 时间线。
- [ ] Agent 诊断链路。
- [ ] 根因排序。
- [ ] 诊断报告。
- [ ] 实验结果表。

验收标准：

- [ ] 三个 demo 能在界面完整展示。
- [ ] 点击一个场景能看到指标、根因和报告。
- [ ] 页面不依赖 CARLA 实时运行，只读 JSON 输出。

## 12. P3：失败样本包

- [ ] 实现 `src/agents/failure_sample_builder.py` 或对应工具函数。
- [ ] 输出 `failure_sample.json`。

字段：

- [ ] `scenario_id`
- [ ] `predicted_fault_type`
- [ ] `predicted_root_module`
- [ ] `predicted_fault_start_time`
- [ ] `evidence`
- [ ] `wrong_reasoning`
- [ ] `correct_reasoning`
- [ ] `tags`
- [ ] `recommended_data`
- [ ] `regression_test_config`
- [ ] `scenario_record_hash`

验收标准：

- [ ] 每个故障场景都能生成可回流样本。
- [ ] 可用于后续 SFT/DPO/RLHF，不实际训练。

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
- [ ] 在 P0.7 通过后，安装或记录 `nuscenes-devkit` 依赖。
- [ ] 扩展 `src/adapters/nuscenes_adapter.py`：从 1 个 smoke sample 扩到 5 个 sample。
- [ ] 当前 metadata-only 阶段输出 `perception.available=false`；若生成 synthetic detections，必须写 `perception.detection_source=synthetic_from_annotation`。
- [ ] 扩展 `src/adapters/nuplan_adapter.py`：从 1 个 smoke scene/scenario 扩到 5 个 scenario。
- [ ] nuPlan adapter 中 `scenario_tag` 只能进入 `events_observed.context_tags` 或抽样条件，不能作为诊断 fault label；`control.available=false`，`planning.trajectory_source` 必须明确。
- [ ] 更新 `docs/schema_mapping_nuscenes.md` 和 `docs/schema_mapping_nuplan.md` 的实际字段覆盖情况。

验收标准：

- [ ] 5 个真实 nuScenes sample 可以转成 `ScenarioRecord`。
- [ ] 5 个真实 nuPlan scenario 可以转成 `ScenarioRecord`。
- [ ] 不改 tools/agents 即可进入 schema validate、可视化、基础风险指标流程。
- [ ] 若未解图像/点云媒体，不宣称完成真实感知模型评估。
- [ ] 缺失 planning/control 时自动跳过 Planning/Control Agent 或输出 unavailable。

## 14. P5：CARLA + ScenarioRunner 接入

- [ ] 在 `/data5/lzx_data/Zhijia-Guardian/third_party/` 下准备 CARLA/ScenarioRunner。
- [ ] 先跑通官方示例。
- [ ] 写 `src/adapters/carla_adapter.py`。
- [ ] 记录 ego、objects、规划轨迹、控制输出。
- [ ] 转换成统一 ScenarioRecord JSONL。
- [ ] 实现故障注入：删除检测框、注入假目标、置信度下降、规划轨迹扰动、控制延迟。

验收标准：

- [ ] 导出 20-30 个 CARLA 场景。
- [ ] CARLA 场景可复用同一套指标和 Agent。
- [ ] 不要求 CARLA 实时接入 Streamlit，先离线回放。

## 15. P5：SafeBench 子集 adapter

- [ ] 研究 SafeBench 输出格式。
- [ ] 写 `src/adapters/safebench_adapter.py`。
- [ ] 选择少量 perception/control 场景。
- [ ] 转换成统一 ScenarioRecord JSONL。

验收标准：

- [ ] 至少 10 个 SafeBench 场景可以进入诊断流程。
- [ ] 不改 SafeBench 内核，只写 adapter。

## 16. P6：后续真实数据扩展

- [ ] nuPlan mini：真实场景骨架 + offline/perturbed planner 规划风险诊断，不把 `scenario_tag` 当 fault label。
- [ ] nuScenes mini：metadata-only 先做 schema/annotation 映射；若要真实感知评估，选择性解出 5 个 sample 媒体并运行 detector。
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

- [ ] 可运行代码仓库。
- [ ] 60-100 个手工/脚本 JSON 场景。
- [ ] 至少 3 个高质量 Demo。
- [ ] 指标工具层。
- [ ] Rule-only baseline。
- [ ] Single-LLM baseline。
- [ ] Multi-Agent + Tools 主方法。
- [ ] 实验结果 CSV。
- [ ] 混淆矩阵和对比表。
- [ ] Streamlit 工作台。
- [ ] 自动诊断报告。
- [ ] failure sample package。
- [ ] 数据格式文档。
- [ ] 软著/答辩可用说明材料。

## 19. 第一版完成定义

当满足以下条件时，MVP 才算完成：

- [ ] 在 `yolo` 环境下，一条命令能跑完整评估。
- [ ] 三个 demo 在 Streamlit 中可展示。
- [ ] 诊断报告中的每个结论都有 evidence。
- [ ] Rule-only、Single-LLM、Multi-Agent + Tools 三组结果能对比。
- [ ] 测试集有 Macro-F1、Root Cause Top-1、Time MAE、Evidence Coverage、Hallucination Rate。
- [ ] 大数据和输出都落在 `/data5/lzx_data/Zhijia-Guardian`。
- [ ] 通过 `tests/test_no_label_leakage.py`，证明诊断路径不能读取 `oracle`。

## 20. 开源项目式运行规范

后续代码必须做到像常见开源仓库一样可复现、可阅读、可一键运行。

- [ ] `README.md` 提供环境安装、数据准备、生成样本、跑评估、启动 Streamlit 的命令。
- [ ] 所有核心逻辑在 `src/`，不把业务逻辑写死在 notebook。
- [ ] 所有脚本只做 CLI 入口，放在 `scripts/` 或 `experiments/`。
- [ ] 所有配置放在 `configs/`，不在代码中硬编码阈值、路径、LLM 开关。
- [ ] 所有实验输出必须有 `run_id`。
- [ ] 所有随机过程必须有 seed。
- [ ] 所有数据读取必须区分 observed view 和 `oracle`。
- [ ] 单元测试至少覆盖 schema、指标工具、无标签泄漏。

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

streamlit run app/streamlit_app.py
```
