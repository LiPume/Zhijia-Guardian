# 基于多智能体协作的自动驾驶可解释性诊断与优化系统设计文档

## 0. 最终落地修订版

本节是 2026-06-25 调研和环境盘点后的最终工程口径，优先级高于后文中偏申报书化、偏理想化的设计描述。后文仍保留作为背景和扩展方向，但第一版开发以本节为准。

### 0.1 一句话定位

第一版产品不是自动驾驶模型，也不是车企级云平台，而是一个**自动驾驶异常场景诊断工作台**：

```text
异常场景日志
  -> 指标工具计算客观证据
  -> 多 Agent 分模块诊断
  -> 根因归因与证据链
  -> 诊断报告、失败样本包、实验指标、Streamlit 展示
```

第一版必须证明三件事：

1. 能判断故障属于感知、规划/决策、控制中的哪一类。
2. 能定位故障从什么时候开始。
3. 能输出有指标证据支撑的根因报告。

### 0.2 当前架构可行性判断

后文提出的“五层架构”总体可行，但需要收缩边界。

| 架构层 | 原设计 | 可行性判断 | 第一版落地方式 |
| --- | --- | --- | --- |
| 数据层 | CARLA、nuPlan、nuScenes、多模态数据全接入 | 方向正确，但一开始直接上 CARLA/大数据会拖慢开发 | 先做真实数据兼容的 `manual_json`，再抽 5 个 nuScenes mini/nuPlan mini 样本验证 adapter，CARLA/SafeBench 后移 |
| 指标工具层 | TTC、碰撞、漏检、误检、轨迹偏离等 Python 工具 | 完全可行，是项目最稳的核心 | 必须优先实现，所有 Agent 结论必须引用指标证据 |
| 多智能体诊断层 | LangGraph 编排多个 Agent | 可行，但 Agent 不能自由聊天 | 用固定状态图和 Pydantic schema；模块 Agent 先用规则，LLM 只做根因归纳/报告 |
| 根因归因与报告层 | 主因、副因、证据链、优化建议 | 可行 | 用“最早异常 + 因果传递 + 风险贡献 + 证据一致性”评分 |
| 可视化与评估层 | Streamlit 工作台 | 可行 | 第一版做轨迹图、时间线、Agent 输出、报告和实验表 |

必须降级或暂缓的内容：

1. 不做“通用非侵入式读取隐层特征”。第一版只做灰盒只读日志 schema。
2. 不做“隐式神经张量转思维链”。第一版只做基于指标和规则的后验审计。
3. 不做真正 RLHF 训练。第一版只输出 SFT/DPO/RLHF-ready 的失败样本包。
4. 不复现 HE-Drive/ComDrive、UniAD、VAD、SparseDrive、TransFuser。
5. 不做真实车企 NOA 数据实验。第一版用可控仿真和可合成真值样本。

### 0.3 环境与数据路径

直接使用已有 `yolo` conda 环境作为第一版开发环境。该环境已有 Torch、Ultralytics、OpenCV、numpy、pandas、scipy、matplotlib，能访问 8 张 RTX 4090D，不再重复下载 Torch。

需要在 `yolo` 中补的小包：

```bash
conda activate yolo
pip install shapely plotly streamlit langgraph pydantic openai scikit-learn
```

项目代码位置：

```text
/home/lzx/Zhijia-Guardian
```

后续大数据、模型、仿真导出、实验结果统一放：

```text
/data5/lzx_data/Zhijia-Guardian
```

推荐数据目录：

```text
/data5/lzx_data/Zhijia-Guardian/
├── datasets/
│   ├── manual_json/
│   ├── carla/
│   ├── safebench/
│   ├── nuplan_mini/
│   └── nuscenes_mini/
├── outputs/
│   └── runs/
│       └── {run_id}/
│           ├── metrics/
│           ├── diagnoses/
│           ├── reports/
│           ├── figures/
│           ├── eval.csv
│           └── run_meta.json
├── models/
├── cache/
└── third_party/
```

仓库内只保留小样本、代码和文档，不把大数据和大仓库直接塞进 git。

### 0.4 Canonical Scenario Schema

第一版手工样本不能使用玩具格式，必须模拟真实自动驾驶数据的共同结构。所有数据源都通过 adapter 输出同一个 `ScenarioRecord`：

```text
manual_json / nuScenes / nuPlan / CARLA / SafeBench
        -> adapter
        -> Canonical Scenario JSON / ScenarioRecord
        -> tools + agents
        -> diagnosis.json / report.md
        -> evaluator only reads oracle
```

Canonical Scenario JSON 顶层结构：

```json
{
  "scenario_id": "manual_0001",
  "source": {
    "dataset": "manual_json",
    "version": "v0_1",
    "raw_log_id": null,
    "raw_tokens": {}
  },
  "meta": {
    "coordinate_frame": "world",
    "distance_unit": "meter",
    "time_unit": "second",
    "speed_unit": "m/s",
    "angle_unit": "radian",
    "frequency_hz": 10,
    "duration": 10.0
  },
  "frames": [],
  "events_observed": [],
  "oracle": {
    "visible_to_diagnosis": false
  }
}
```

硬性防泄漏规则：

1. Rule-only、Multi-Agent + Tools、Single-LLM 都只能读取 `ScenarioRecord.observed_view()`，也就是 `scenario_id/source/meta/frames/events_observed`。
2. `oracle` 是实验真值，只允许 `experiments/run_eval.py` 读取。
3. `fault_type`、`root_module`、`fault_start_time` 这类标签只能放在 `oracle` 中，严禁进入诊断输入。
4. 代码中要提供 `load_scenario_record()`、`get_observed_view()`、`load_oracle()` 三类读取接口，避免误用。
5. 必须有 `tests/test_no_label_leakage.py` 验证诊断路径不能访问 `oracle`。

`source` 字段用于保留真实来源信息和 token 映射：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `dataset` | 是 | `manual_json` / `nuscenes` / `nuplan` / `carla` / `safebench` |
| `version` | 是 | 数据版本，如 `v0_1`、`v1.0-mini` |
| `raw_log_id` | 否 | 原始日志/scene/log 标识 |
| `raw_tokens` | 是 | 原始数据 token 外键映射，手工样本可为空对象 |

`meta` 字段必须显式声明坐标系和单位：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `coordinate_frame` | 是 | `ego` 或 `world`，优先 `world` |
| `distance_unit` | 是 | 固定 `meter` |
| `time_unit` | 是 | 固定 `second` |
| `speed_unit` | 是 | 固定 `m/s` |
| `angle_unit` | 是 | 固定 `radian` |
| `frequency_hz` | 是 | 采样频率 |
| `duration` | 是 | 场景时长 |

`frames` 是主结构，每个 frame 表示一个时间戳：

```json
{
  "timestamp": 4.2,
  "ego": {
    "x": 12.4,
    "y": 8.7,
    "yaw": 0.0,
    "vx": 10.0,
    "vy": 0.0,
    "ax": -0.2,
    "length": 4.8,
    "width": 1.9,
    "lane_id": "lane_01"
  },
  "actors_gt": [],
  "actors_gt_source": "dataset_annotation",
  "perception": {
    "available": true,
    "detections": []
  },
  "planning": {
    "available": true,
    "trajectory_source": "perturbed_planner",
    "trajectory": [],
    "intent": "keep_lane",
    "target_speed": 10.0
  },
  "control": {
    "available": true,
    "steer": 0.0,
    "throttle": 0.3,
    "brake": 0.0
  },
  "map": {
    "available": true,
    "lane_id": "lane_01",
    "drivable_area": null,
    "speed_limit": 13.9
  }
}
```

缺字段必须显式表达为 `available: false`，不能靠字段缺失让下游猜：

1. 接 nuScenes metadata-only：`actors_gt_source=dataset_annotation`，`perception.available=false`，`planning.available=false`，`control.available=false`；只能做 schema smoke test、GT 目标映射和离线风险指标。
2. 接 nuScenes media + detector 或合成检测：`perception.available=true`，但 detections 必须来自实际模型输出或由 annotation 扰动生成，并记录 `perception.detection_source`。
3. 接 nuPlan 原始 DB：`actors_gt_source=dataset_annotation`，可带 tracked objects/map/context，`perception.available=false`，`control.available=false`；`planning.trajectory_source=expert_future` 时只能作为参考轨迹或环境上下文。
4. 接 nuPlan + 离线 planner/扰动轨迹：`planning.available=true`，`trajectory_source=offline_planner` 或 `perturbed_planner`，此时才可以评估 planner 输出风险。
5. 接 CARLA/SafeBench：尽量提供 perception/planning/control 全链路，`actors_gt_source=simulation`。
6. 手工样本必须覆盖上述缺字段模式。

`actors_gt` 是离线 benchmark 和仿真中可见的环境真值，不等价于真实车端天然可得数据。必须显式声明来源：

| 值 | 含义 |
| --- | --- |
| `simulation` | CARLA/SafeBench 等仿真真值 |
| `dataset_annotation` | nuScenes/nuPlan/DeepAccident 等公开数据标注 |
| `offline_reconstruction` | 车企日志离线重建或人工复盘结果 |
| `unavailable` | 没有 GT，系统退化为黑盒/灰盒诊断 |

`planning.trajectory_source` 必须显式声明：

| 值 | 含义 | 是否可用于诊断 planner 输出 |
| --- | --- | --- |
| `expert_future` | nuPlan 等数据中的人类专家未来轨迹 | 否，只能作为参考 |
| `offline_planner` | 本项目运行规则 planner/PlanTF/其他 planner 得到的轨迹 | 是 |
| `perturbed_planner` | 在真实场景骨架上扰动生成的危险轨迹 | 是 |
| `model_prediction` | 车企或模型真实输出轨迹 | 是 |
| `unavailable` | 无规划轨迹 | 否 |

手工样本和文件名不得泄漏标签。`scenario_id` 统一使用 `manual_v0_1_000001`、`nuplan_mini_000001` 这种无故障名格式；路径目录只能表达数据形态，如 `planning_like_nuplan`，不能写成 `perception_miss_001.json` 或 `control_delay_003.json`。

`oracle` 只给评估使用：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `visible_to_diagnosis` | 是 | 固定 `false` |
| `fault_type` | 是 | 真值故障类型 |
| `root_module` | 是 | 真值根因模块 |
| `fault_start_time` | 是 | 真值故障开始时间 |
| `fault_segment` | 否 | 真值故障时间段 |
| `notes` | 否 | 标注说明 |

每个场景输出：

| 输出 | 内容 |
| --- | --- |
| `metrics.json` | TTC、最小距离、碰撞风险、漏检/误检、轨迹偏离、控制延迟 |
| `diagnosis.json` | 预测故障类型、预测根因模块、预测故障时间、置信度、证据链 |
| `report.md` | 工程师可读诊断报告 |
| `failure_sample.json` | 可回流的失败样本包 |

诊断输出中可以预测 `predicted_fault_type`、`predicted_root_module`、`predicted_fault_start_time`，但不能把真值标签复制进去。

### 0.5 第一版故障类型

先固定 5 类，后续再扩展：

| 类型 | 模块 | 定义 |
| --- | --- | --- |
| `perception_miss` | 感知 | GT 中存在关键目标，但感知输出持续缺失 |
| `perception_false_positive` | 感知 | GT 中不存在目标，但感知输出持续出现虚假障碍物 |
| `perception_confidence_drop` | 感知 | 关键目标置信度异常下降并影响下游风险判断 |
| `planning_collision_risk` | 规划/决策 | 规划轨迹与障碍物冲突，或低 TTC 下仍保持危险轨迹 |
| `control_delay` | 控制 | 风险已出现或规划已要求制动，但控制输出延迟/不足 |

测试集必须保留一部分 `normal` 场景，用于评估误报率。

### 0.6 是否套用线上代码的决定

已调研 CARLA、ScenarioRunner、SafeBench、DriveFuzz、DriveLM、Agent-Driver、DiaVio、DVCA、carla_garage 等方向。结论是：**不直接套一个线上仓库作为主工程**。

原因：

1. SafeBench/ScenarioRunner 适合做场景执行和安全评测，但没有我们需要的感知-规划-控制根因报告链。
2. DriveFuzz 适合找 bug，不适合直接做诊断报告；环境也偏旧。
3. DriveLM/Agent-Driver 是驾驶推理/驾驶控制方向，不是事故后诊断工具。
4. DiaVio 更接近事故/违规诊断，但核心是 crash DSL、责任判定和碰撞类型分类，不覆盖我们要做的模块级根因定位。
5. DVCA 思路很贴近“组件级归因”，但它依赖仿真中的理想组件替换，第一版可以借鉴反事实思想，不适合作为主代码底座。

最终工程策略：

```text
主仓自建轻量诊断框架
  + 借鉴 SafeBench / ScenarioRunner 的场景组织和评估
  + 借鉴 DriveFuzz 的故障注入和 oracle
  + 借鉴 DriveLM 的图式推理模板
  + 借鉴 DiaVio 的结构化事故描述思想
  + 后续用 adapter 接 CARLA/SafeBench 输出
```

外部大仓库如需使用，放在：

```text
/data5/lzx_data/Zhijia-Guardian/third_party/
```

本仓库只写 adapter，不复制大仓库源码。

### 0.7 最终代码结构

建议主仓结构：

```text
Zhijia-Guardian/
├── README.md
├── configs/
│   ├── dataset.yaml
│   ├── thresholds.yaml
│   └── llm.yaml
├── data/
│   ├── sample_scenarios/
│   └── README.md
├── src/
│   ├── schemas/
│   │   ├── scenario.py
│   │   ├── metrics.py
│   │   └── diagnosis.py
│   ├── tools/
│   │   ├── ttc.py
│   │   ├── collision.py
│   │   ├── perception_eval.py
│   │   ├── planning_eval.py
│   │   └── control_eval.py
│   ├── agents/
│   │   ├── parser_agent.py
│   │   ├── metric_agent.py
│   │   ├── perception_agent.py
│   │   ├── planning_agent.py
│   │   ├── control_agent.py
│   │   ├── root_cause_agent.py
│   │   └── report_agent.py
│   ├── graph/
│   │   └── diagnosis_graph.py
│   ├── adapters/
│   │   ├── base_adapter.py
│   │   ├── manual_adapter.py
│   │   ├── nuscenes_stub_adapter.py
│   │   ├── nuplan_stub_adapter.py
│   │   ├── carla_stub_adapter.py
│   │   ├── nuscenes_adapter.py
│   │   ├── nuplan_adapter.py
│   │   ├── carla_adapter.py
│   │   └── safebench_adapter.py
│   └── utils/
├── experiments/
│   ├── run_eval.py
│   ├── baselines/
│   │   ├── rule_only.py
│   │   └── single_llm.py
│   └── metrics.py
├── app/
│   └── streamlit_app.py
├── prompts/
├── scripts/
│   ├── generate_manual_scenarios.py
│   └── run_demo.sh
├── tests/
│   ├── test_schema.py
│   ├── test_metrics.py
│   └── test_no_label_leakage.py
├── docs/
│   ├── adapter_contract.md
│   ├── schema_mapping_nuscenes.md
│   ├── schema_mapping_nuplan.md
│   └── schema_mapping_carla.md
└── docx/
```

代码规范：

1. `src/` 是唯一业务代码入口，避免把核心逻辑散落在 notebook 或临时脚本里。
2. `scripts/` 只做命令行入口，内部调用 `src/`。
3. `experiments/run_eval.py` 是统一评估入口，必须支持 `--method`、`--dataset`、`--run-id`、`--config`。
4. 所有输出写入 `/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/`。
5. 所有随机生成样本必须设置 seed，并把 seed 写入 `run_meta.json`。
6. 测试至少覆盖 schema 校验、指标工具和“诊断流程无法读取 oracle”。

### 0.8 Adapter Contract

所有 adapter 必须实现统一接口，tools 和 agents 永远不直接读取 nuScenes/nuPlan/CARLA 原始格式：

```python
class BaseAdapter:
    def list_scenarios(self) -> list[str]:
        ...

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        ...

    def export_json(self, scenario_id: str, output_path: str) -> None:
        ...
```

Adapter 输出关系：

```text
ManualAdapter        -> ScenarioRecord
NuScenesAdapter      -> ScenarioRecord
NuPlanAdapter        -> ScenarioRecord
CarlaAdapter         -> ScenarioRecord
SafeBenchAdapter     -> ScenarioRecord
```

第一版先实现 `ManualAdapter` 和三个 stub：

1. `NuScenesStubAdapter`：模拟 nuScenes 的 token、sample、sample_annotation、ego_pose 映射。
2. `NuPlanStubAdapter`：模拟 nuPlan 的 scenario、ego state、tracked objects、map、planner trajectory 映射。
3. `CarlaStubAdapter`：模拟 CARLA 的 ego、actors、sensor/perception、planner/control、collision/lane invasion 事件。

真实数据兼容性文档：

1. `docs/adapter_contract.md`
2. `docs/schema_mapping_nuscenes.md`
3. `docs/schema_mapping_nuplan.md`
4. `docs/schema_mapping_carla.md`

调研结论：

1. nuScenes 官方 schema 是 token/foreign-key 关系型结构，关键表包括 `scene`、`sample`、`sample_data`、`ego_pose`、`sample_annotation` 等，适合优先验证感知诊断 adapter。
2. nuPlan 更适合规划/决策诊断。官方下载页仍要求账号和同意 Terms of Use，但 AWS Open Data Registry 同时登记了公开 S3 bucket `motional-nuplan`；2026-06-26 已实测 S3 源站直链可用。
3. 2026-06-26 已下载 nuPlan mini 结构化数据到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/raw/`：`nuplan-v1.1_mini.zip` 为 `8550100030` bytes，`nuplan-maps-v1.0.zip` 为 `971557640` bytes，`nuplan_mini_sensor.txt` 为 `2622` bytes。
4. `nuplan-v1.1_mini.zip` 和 `nuplan-maps-v1.0.zip` 均已通过 `unzip -t` 完整性校验。nuPlan mini zip 内含 64 个 `data/cache/mini/*.db` SQLite 数据库，未压缩合计约 14.35GB；maps zip 内含 `maps/nuplan-maps-v1.0.json` 和 4 个城市的 `map.gpkg`。第一版不全量解压，只抽样 DB 做 adapter 验证。
5. 已抽检两个 DB。`2021.10.05.07.10.04_veh-52_01442_01802.db` 包含表：`log`、`ego_pose`、`camera`、`image`、`lidar`、`lidar_pc`、`lidar_box`、`track`、`category`、`scene`、`scenario_tag`、`traffic_light_status`，计数为 `scene=19`、`ego_pose=36197`、`lidar_pc=7200`、`lidar_box=46449`、`track=348`、`scenario_tag=7119`、`traffic_light_status=4030`。最小 DB `2021.10.11.07.12.18_veh-50_00211_00304.db` 约 6.1MB，计数为 `scene=6`、`ego_pose=9493`、`lidar_pc=1860`、`lidar_box=7634`、`track=107`、`scenario_tag=1838`、`traffic_light_status=673`。
6. nuPlan adapter 的最小 join 路径：`scene -> lidar_pc(scene_token)` 得到场景帧序列；`lidar_pc.ego_pose_token -> ego_pose` 得到 ego 全局位姿和速度；`lidar_box.lidar_pc_token -> track -> category` 得到 tracked actors；`scenario_tag.lidar_pc_token` 得到事件标签；`traffic_light_status.lidar_pc_token` 得到红绿灯状态；`scene.roadblock_ids` 和 maps manifest/GPKG 后续用于车道与可行驶区域。
7. nuPlan 不等价于车端全链路日志，不天然提供被测系统的规划输出和控制指令。第一版真实 nuPlan adapter 必须写明 `planning.trajectory_source`：`expert_future` 只作参考，`offline_planner`/`perturbed_planner`/`model_prediction` 才能用于诊断 planner 输出；不能把 `scenario_tag` 当成诊断真值输入。mini sensor blobs 单个相机/激光 zip 往往几十 GB，当前阶段暂不下载，只保留 `nuplan_mini_sensor.txt` 清单。
8. CARLA/SafeBench 最适合全链路，但环境复杂，不作为第一个真实数据接入目标。
9. `https://www.nuscenes.org/data/v1.0-mini.tgz` 已验证 HEAD 可访问，返回 `content-length=4167696325`，约 3.88GiB/3.97GB；它是完整 mini 包，不是 5 个小文件，因此 P4 只写下载/抽样脚本，真实下载时放到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/`。
10. 2026-06-25 已实际下载 `v1.0-mini.tgz` 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/`，并只解出 metadata 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini/`；metadata 目录约 32MB，未解出图像、雷达和激光雷达媒体文件。
11. 实测 mini metadata 包含 13 张 JSON 表：`scene`、`sample`、`sample_data`、`ego_pose`、`sample_annotation`、`instance`、`category`、`calibrated_sensor`、`sensor`、`log`、`map`、`attribute`、`visibility`。记录数为：10 个 scene、404 个 key sample、31206 条 sample_data/ego_pose、18538 条 sample_annotation。
12. nuScenes adapter 的最小 join 路径：`scene.first_sample_token -> sample.next` 得到时间序列；`sample_data(sample_token, is_key_frame=true, channel=LIDAR_TOP) -> ego_pose` 得到 ego 全局位姿；`sample_annotation(sample_token) -> instance -> category` 得到 actor GT 和类别；`sample_data -> calibrated_sensor -> sensor` 得到 12 路传感器通道。
13. 公开数据里真正接近“有事故/异常标签”的候选是 DeepAccident、DoTA/DADA、SafeBench/DriveFuzz。DeepAccident 是 CARLA 合成的 V2X accident/normal 数据，提供多视角 RGB、LiDAR 和标签，适合后续 P4.5 做事故检测和多模态失败样本；DoTA/DADA 是真实视频事故/异常数据，有 temporal/spatial/category annotation，但没有自动驾驶系统内部感知/规划/控制日志，不能直接做 root_module 诊断；SafeBench/DriveFuzz 更适合生成带 oracle 的闭环失败样本。
14. 因此第一版不再把 nuPlan/nuScenes 当作 fault-label 数据集，而是把它们作为真实数据 schema smoke test 和指标迁移验证；真正用于诊断 F1/根因 Top-1 的数据来自 manual perturbation、CARLA/SafeBench/DriveFuzz，或后续 DeepAccident mini。

### 0.9 MVP 开发顺序

第一阶段先不接 CARLA，先跑通 canonical 小闭环：

```text
6 个 canonical demo 场景
  -> ScenarioRecord schema
  -> ManualAdapter
  -> stub adapters
  -> P0.7 真实数据最小 adapter smoke test
  -> 三类 manual subset
  -> 指标工具
  -> Rule-only baseline
  -> LangGraph 多 Agent
  -> Single-LLM baseline
  -> 对比实验
  -> Streamlit Demo
```

第二阶段做真实数据兼容性验证：

```text
nuScenes mini / nuPlan mini
  -> 官方格式读取
  -> 抽 5 个 sample/scenario
  -> adapter 输出 ScenarioRecord
  -> 不改 tools/agents 即可跑 perception-like / planning-like 诊断
```

第三阶段再接仿真：

```text
CARLA + ScenarioRunner / SafeBench
  -> 导出统一 ScenarioRecord JSONL
  -> 故障注入
  -> 20-30 个仿真样本起步，稳定后扩到 100-300 个
  -> 与第一阶段共用同一套诊断工具和评估脚本
```

第四阶段再考虑 Bench2Drive/carla_garage/TransFuser，作为论文增强，不进入第一版。

### 0.10 第一版验收指标

| 指标 | 目标 |
| --- | ---: |
| 故障分类 Macro-F1 | >= 0.80 |
| 根因 Top-1 Accuracy | >= 0.75 |
| 故障时间定位 MAE | <= 0.6s |
| 报告证据覆盖率 | >= 0.85 |
| 幻觉率 | <= 0.10 |
| 单场景平均诊断时间 | <= 60s |

### 0.11 Evidence 与报告质量计算

指标工具输出的每条证据都必须有唯一 `evidence_id`：

```json
{
  "evidence_id": "E_TTC_001",
  "metric_name": "min_ttc",
  "value": 0.92,
  "threshold": 1.5,
  "time": 4.6,
  "status": "violation",
  "supports": ["planning_collision_risk", "control_delay"],
  "contradicts": ["normal"],
  "description": "min TTC below threshold while ego remains close to front object"
}
```

正常或不确定场景也必须能被证据表达。例如 `min_ttc >= threshold`、`no_collision=true`、`brake_response_normal=true` 这类证据应写成：

```json
{
  "evidence_id": "E_TTC_010",
  "metric_name": "min_ttc",
  "value": 4.8,
  "threshold": 1.5,
  "time": 4.6,
  "status": "normal",
  "supports": ["normal"],
  "contradicts": ["planning_collision_risk", "control_delay"],
  "description": "min TTC stays above threshold"
}
```

报告和诊断中的每个结论必须引用 evidence：

```json
{
  "claim_id": "C_001",
  "claim": "车辆在低 TTC 条件下未及时制动",
  "predicted_fault_type": "control_delay",
  "evidence_ids": ["E_TTC_001", "E_BRAKE_002"]
}
```

可计算指标定义：

```text
Evidence Coverage = 有 evidence_id 支撑的结论数 / 总结论数
Evidence Correctness = 被引用证据中 supports 覆盖结论标签且 contradicts 不包含结论标签的证据数 / 被引用证据总数
Hallucination Rate = 无 evidence_id 支撑、evidence_id 不存在、或全部被引用证据均不支持/反驳该结论的结论数 / 总结论数
```

人工评分可以作为补充，但不能替代上述自动指标。

### 0.12 LLM 默认关闭

第一版默认 `configs/llm.yaml`：

```yaml
enabled: false
provider: openai
model: gpt-4o-mini
temperature: 0
json_mode: true
```

实验开关：

1. Rule-only baseline：不使用 LLM。
2. Multi-Agent + Tools：模块诊断不使用 LLM，报告生成可选 LLM；默认关闭。
3. Single-LLM baseline：单独开启 LLM，只用于 baseline 对比。

这样做是为了先保证纯规则系统可复现，再评估 LLM 对报告质量和幻觉率的影响。

### 0.13 手工样本必须加噪声

手工/脚本样本不能过于干净，否则 Rule-only 会被设计得过强，无法体现多 Agent 的稳定性。样本生成必须加入：

| 噪声类型 | 做法 |
| --- | --- |
| 时间噪声 | 故障触发、观测异常、风险出现时间加入 ±0.2s 随机偏移 |
| 感知噪声 | confidence 随机波动，非故障帧也允许小幅抖动 |
| 目标噪声 | 目标位置、速度加入小幅高斯扰动 |
| 控制噪声 | brake/throttle/steer 加入延迟和抖动 |
| 复合故障 | 感知轻微异常 + 规划响应不足 |
| 边界样本 | TTC 接近阈值但不一定故障，避免阈值规则一把梭 |

样本 metadata 必须记录：

```json
{
  "generation_seed": 42,
  "noise_profile": "v0_1_moderate",
  "scenario_family": "front_brake",
  "difficulty": "boundary"
}
```

手工样本分为三个子集：

```text
manual_json/
  v0_1/
    perception_like_nuscenes/
    planning_like_nuplan/
    full_stack_like_carla/
```

1. `perception_like_nuscenes`：有 ego、actors_gt、perception detections，不要求 planning/control。
2. `planning_like_nuplan`：有 ego、tracked actors、map、planned trajectory，不强调 perception/control。
3. `full_stack_like_carla`：有 ego、actors_gt、perception、planning、control、collision/lane events。

### 0.14 Run ID 与可复现实验

每次实验输出目录：

```text
/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/
├── metrics/
├── diagnoses/
├── reports/
├── figures/
├── eval.csv
└── run_meta.json
```

`run_meta.json` 必须包含：

```json
{
  "run_id": "20260625_zhijia_v0_1_rule",
  "method": "rule_only",
  "dataset": "manual_json_v0_1",
  "threshold_config": "configs/thresholds.yaml",
  "llm_config": "configs/llm.yaml",
  "git_commit": "...",
  "seed": 42,
  "created_at": "2026-06-25T20:00:00+08:00"
}
```

### 0.15 2026-06-30 工程验证状态

当前原型已经完成 Canonical schema、nuScenes/nuPlan adapter、nuPlan 成对规划扰动、CARLA
离线故障注入、CARLA closed-loop、三类诊断方法和 Streamlit 工作台。manual benchmark 已升级
到 v0.3：先生成完整物理时序，再按 TTC 首次跌破阈值确定风险时刻，感知/规划根因必须早于
下游控制异常。

72 条 manual v0.3、seed 42、commit `0c7e220` 的正式结果：

| 方法 | Macro-F1 | Root Top-1 | Time MAE@Correct | Evidence Correctness | Hallucination Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Multi-Agent + Tools | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 0.0000 |
| Single-LLM / DeepSeek V4 Pro | 0.9861 | 0.9861 | 0.3333 | 0.6250 | 0.1271 |
| Rule-only | 0.9066 | 0.9028 | 0.0000 | 1.0000 | 0.0000 |

这个结果只证明模块分诊和时序根因排序能处理受控复合故障，不代表自然事故泛化。Single-LLM
虽分类准确，但幻觉率未达到 0.10 目标，因此产品默认保持 LLM 关闭。下一阶段优先做
SafeBench/更多 CARLA 模板和多 seed held-out 验证，不把精力投入 Root Cause/Report Agent 的
自由式 LLM 调用。

---

## 1. 项目名称

基于多智能体协作的自动驾驶可解释性诊断与优化研究

系统原型名称建议：

**DriveDiag-Agent：自动驾驶异常场景多智能体诊断工作台**

---

## 2. 项目定位

本项目不直接研发一套新的自动驾驶模型，也不替代车企原有智驾系统，而是构建一个面向自动驾驶异常场景的**可解释性诊断与安全审计工具链**。

系统目标是：输入一个自动驾驶场景的 observed view，包括车辆状态、感知结果、规划轨迹、控制指令、环境信息和可见事件上下文，系统自动完成异常阶段定位、故障类型识别、根因归因、证据链生成和诊断报告输出。事故/异常标签只能作为 evaluation oracle，由评估脚本读取，不能进入诊断输入。

项目第一阶段应收缩为一个可验证 MVP：

> 基于 CARLA 构造带有真值标签的异常驾驶场景，使用 LangGraph 编排多个诊断 Agent，结合 Python 指标工具计算 TTC、碰撞风险、轨迹偏离、感知漏检等指标，最终输出结构化根因诊断报告，并在测试集上评估故障分类 F1、根因 Top-1 准确率和故障时间定位误差。

---

## 3. 核心问题定义

### 3.1 业务痛点

自动驾驶系统在复杂场景中发生异常时，传统排查方式通常依赖人工查看日志、回放视频、逐帧对齐传感器和轨迹信息。这种方式存在三个问题：

第一，事故原因难以快速定位。异常可能来自感知漏检、误检、规划轨迹错误、控制响应延迟，也可能是多个模块耦合导致。

第二，模型内部过程难以解释。端到端模型或多模态大模型驱动的自动驾驶系统往往只输出轨迹或控制指令，中间推理过程不透明。

第三，诊断结果难以反哺优化。即使人工找到了问题，也需要重新整理样本、标注失效原因、构造训练数据，闭环周期长。

### 3.2 技术目标

本项目希望解决的问题不是“车怎么自动开”，而是：

> 当自动驾驶系统开得不对时，如何判断它为什么错、错在哪一层、什么时候开始错、依据是什么、后续应该怎么修。

具体任务包括：

1. 异常场景解析：读取车辆状态、目标信息、轨迹、控制指令和环境条件。
2. 故障时间定位：判断异常最早出现在哪个时间段。
3. 故障类型识别：判断故障属于感知、规划、决策、控制或复合故障。
4. 根因归因：给出主要原因、次要原因和证据。
5. 可解释报告生成：输出工程师可读的事故诊断病历。
6. 数据闭环生成：将失败案例转化为后续训练/回归测试样本。

---

## 4. 系统总体架构

系统采用五层架构：

```text
数据层
  ↓
指标工具层
  ↓
多智能体诊断层
  ↓
根因归因与报告层
  ↓
可视化与评估层
```

### 4.1 数据层

数据层负责接入或生成异常驾驶场景。第一版先用真实数据兼容的 Canonical Scenario JSON 跑通闭环，再用 nuScenes mini/nuPlan mini 的 5 个离线样本校验 adapter，最后再扩展 CARLA/ScenarioRunner/SafeBench 的仿真闭环。

数据层输入包括：

1. ego vehicle 状态：位置、速度、加速度、朝向、控制指令。
2. 周围目标信息：车辆、行人、障碍物的位置、速度、类别、置信度。
3. 感知输出：检测框、类别、置信度、目标轨迹。
4. 规划输出：未来轨迹点、候选轨迹、目标车道、制动/变道策略。
5. 控制输出：方向盘角、油门、刹车、加速度。
6. 环境上下文：天气、光照、道路类型、交通灯、限速、地图信息。
7. 评估 oracle：故障类型、故障开始时间、主要责任模块，仅 `experiments/run_eval.py` 可读，不能进入诊断输入。

### 4.2 指标工具层

指标工具层不依赖大模型，全部由 Python 函数计算，保证诊断有客观证据。

核心指标工具包括：

1. TTC 计算工具：计算 ego 车与前方目标的 Time-to-Collision。
2. 最小距离工具：计算车辆与障碍物的最小距离。
3. 碰撞检测工具：判断规划轨迹是否与障碍物轨迹相交。
4. 车道偏离工具：判断轨迹是否离开可行驶区域。
5. 急加速/急刹工具：计算加速度和 jerk，判断舒适性异常。
6. 感知漏检工具：比较真值目标和感知目标，判断是否漏检关键目标。
7. 感知误检工具：判断模型是否检测出不存在的目标。
8. 类别混淆工具：判断目标类别是否与真值不一致。
9. 置信度异常工具：检测关键目标置信度是否突然下降。
10. 时间线对齐工具：将感知、规划、控制异常对齐到统一时间轴。

### 4.3 多智能体诊断层

多智能体诊断层采用 LangGraph 编排，不采用自由聊天式 Agent。每个 Agent 都是一个明确的诊断节点，必须基于指标工具输出结构化结果。

核心 Agent 包括：

1. Scenario Parser Agent：场景解析智能体。
2. Metric Calculator Agent：指标计算智能体。
3. Perception Diagnosis Agent：感知诊断智能体。
4. Planning Diagnosis Agent：规划/决策诊断智能体。
5. Control Diagnosis Agent：控制诊断智能体。
6. Root Cause Agent：根因归因智能体。
7. Report Agent：诊断报告生成智能体。
8. Data Generation Agent：失败样本构造智能体。

### 4.4 根因归因与报告层

该层负责综合多 Agent 的诊断结果，形成最终结论：

1. 故障主因：最可能导致异常的模块。
2. 故障副因：参与放大异常的其他模块。
3. 故障时间线：异常从哪一秒开始，如何逐步扩散。
4. 证据链：每个判断对应的指标、日志和场景信息。
5. 修复建议：建议补充什么数据、修改什么阈值、增强什么场景训练。
6. 样本标签：生成可用于后续训练或回归测试的数据标签。

### 4.5 可视化与评估层

该层用于展示系统结果和跑实验指标。建议第一阶段用 Streamlit 实现。

界面包括：

1. 场景选择区：选择测试场景和故障类型。
2. 场景回放区：展示视频帧、BEV 视图或轨迹图。
3. 风险时间线：展示 TTC、速度、置信度、规划风险随时间变化。
4. Agent 诊断链路：展示各 Agent 的输入、输出和证据。
5. 根因排序：展示各故障类型的置信度分数。
6. 诊断报告：自动生成工程师可读报告。
7. 实验评估：展示不同方法的 Accuracy、F1、Top-1、时间误差等指标。

---

## 5. 技术选型

### 5.1 Agent 编排框架

主框架：LangGraph
辅助组件：LangChain

分工如下：

| 技术                  | 用途                                   |
| ------------------- | ------------------------------------ |
| LangGraph           | 负责多 Agent 状态图、节点编排、条件跳转、状态保存         |
| LangChain           | 负责 LLM 调用、PromptTemplate、工具封装、RAG 检索 |
| Pydantic            | 负责 Agent 输出结构化校验                     |
| Python              | 负责指标计算和故障判断工具                        |
| Streamlit           | 负责快速构建可视化工作台                         |
| FastAPI             | 后续作为系统后端接口                           |
| SQLite / JSONL      | 保存场景数据、指标结果和诊断报告                     |
| pandas / numpy      | 数据处理                                 |
| OpenCV              | 视频帧处理                                |
| matplotlib / plotly | 轨迹、风险曲线、时间线可视化                       |

### 5.2 为什么采用 LangGraph

本项目不是普通问答系统，而是一个状态化、多步骤、可审计的诊断流程。每个节点都要保留输入、指标、证据和结论。LangGraph 适合显式定义流程图，例如：

```text
Scenario Parser
    ↓
Metric Calculator
    ↓
Perception Diagnosis
    ↓
Planning Diagnosis
    ↓
Control Diagnosis
    ↓
Root Cause Analysis
    ↓
Report Generation
```

因为 nuScenes/nuPlan 已经下载，真实数据最小验证必须提前到 P0.7，不等到 P4：

```text
P0.7 real smoke test
  -> nuScenes mini 抽 1 个 sample 转 ScenarioRecord
  -> nuPlan mini 抽 1 个 scene/scenario 转 ScenarioRecord
  -> 输出 data/sample_scenarios/real_smoke_test/
  -> 只做 schema validate、observed_view 检查和字段覆盖率
  -> 不跑诊断、不计算 fault F1
```

第一版实验分成两条线：

1. 真实数据适配线：nuScenes/nuPlan 只证明 canonical schema、adapter、基础风险指标和可视化能跑通；不声称它们自带系统故障根因。
2. 可诊断评估线：manual/perturbed/CARLA/SafeBench/DeepAccident 这类有故障注入、事故标签或仿真 oracle 的数据用于计算 Fault Macro-F1、Root Cause Top-1、Time MAE、Evidence Coverage。

这样论文和答辩时可以讲清楚：真实公开数据用于验证“接得上真实世界格式”，可控故障数据用于验证“诊断是否准确”。

如果直接用普通 LangChain Agent，流程可能变成一个大模型自由判断，容易出现证据链不稳定、步骤不可控、报告不可复现的问题。

---

## 6. 数据集设计

### 6.1 第一阶段：CARLA 仿真数据

CARLA 用于构造带有真值标签的异常场景。因为项目需要评估“诊断是否准确”，必须有明确真值，而真实事故数据通常难以获取、难以标注，也涉及安全和隐私问题。

CARLA 中可以构造以下场景：

| 场景类型      | 故障注入方式          | 真值标签    |
| --------- | --------------- | ------- |
| 前车急刹      | 删除前方车辆检测框       | 感知漏检    |
| 路边广告牌     | 注入虚假车辆检测框       | 感知误检    |
| 雨夜行人      | 降低行人目标置信度       | 感知置信度异常 |
| 静止施工车     | 规划轨迹未避让障碍物      | 规划故障    |
| 低 TTC 未刹车 | 延迟制动控制指令        | 决策/控制故障 |
| 变道失败      | 规划轨迹压线或进入不可行驶区域 | 规划故障    |
| 路口冲突      | 未对交叉车辆进行风险评估    | 决策故障    |

不建议第一阶段直接生成 500 个 CARLA 样本。MVP 先用 60-100 个真实数据兼容的 manual/perturbed canonical 样本跑通诊断闭环，再用 20-30 个 CARLA/SafeBench 场景验证全链路。500 个样本作为后续扩展目标：

| 类型     | 样本数 |
| ------ | --: |
| 感知漏检   | 100 |
| 感知误检   | 100 |
| 置信度异常  | 100 |
| 规划轨迹危险 | 100 |
| 控制响应延迟 | 100 |

数据划分：

| 集合       |  比例 | 样本数 |
| -------- | --: | --: |
| 训练/规则调参集 | 60% | 300 |
| 验证集      | 20% | 100 |
| 测试集      | 20% | 100 |

### 6.2 第二阶段：nuPlan 规划场景骨架

nuPlan 用于验证系统能否接入真实规划 benchmark 的场景结构、ego 轨迹、目标轨迹、地图和红绿灯上下文。它不天然提供“被测 planner 的输出”，也没有控制指令，因此不能直接作为 planner/root-cause fault label 数据集。

P0.7 中 nuPlan 只做：

1. SQLite -> Canonical ScenarioRecord 的 smoke test。
2. `scene/lidar_pc/ego_pose/lidar_box/track/category` 到 frames/ego/actors 的映射。
3. `scenario_tag` 到 `events_observed.context_tags` 的映射。
4. `traffic_light_status` 和 map roadblock 到上下文字段的映射。
5. `planning.trajectory_source=expert_future` 时仅作为参考轨迹或 expert baseline，不计算 planner fault F1。

只有当额外运行离线 planner 或生成扰动轨迹后，才做规划风险诊断：

1. `planning.trajectory_source=offline_planner`：评估规则 planner、PlanTF 或其他 planner 的输出。
2. `planning.trajectory_source=perturbed_planner`：在真实 nuPlan 场景骨架上注入危险轨迹，用 oracle 评估诊断能力。
3. `planning.trajectory_source=model_prediction`：后续车企真实模型输出，可直接进入诊断。

2026-06-26 实测结论：

1. 已能直接从 `motional-nuplan` S3 源站下载 `nuplan-v1.1_mini.zip` 和 `nuplan-maps-v1.0.zip`，不需要先等浏览器手动下载。
2. mini 数据库是 SQLite 关系型结构，核心表可直接映射到 canonical `frames.ego`、`frames.actors_gt`、`events_observed` 和 `map`。
3. nuPlan 的真实数据没有车端控制命令，也不天然保存被测规划器输出；第一版 adapter 应将 `control.available=false`，并将 `planning.trajectory_source` 标注为 `expert_future`、`offline_planner`、`perturbed_planner` 或 `unavailable`。
4. `scenario_tag` 只能作为场景类型和抽样条件，不能作为诊断 Agent 的 fault label 输入；需要诊断标签时另放 evaluation/oracle。

### 6.3 第三阶段：nuScenes 感知数据

nuScenes 用于验证真实感知数据 schema 和 annotation 映射。当前已下载完整 mini tgz，但只解出 metadata，因此现阶段不能声称已经能“用图像/点云跑检测器并比较输出”。

metadata-only 阶段可做：

1. scene/sample/sample_data/ego_pose/sample_annotation 映射。
2. actors_gt 映射，`actors_gt_source=dataset_annotation`。
3. 时序结构、坐标系和传感器通道映射。
4. perception-like schema smoke test，`perception.available=false`。

要做真正感知诊断，有两条可选路径：

1. 从已下载 tgz 中选择性解出 5 个 sample 的相机/点云媒体，运行 YOLO/3D detector，得到 `perception.detections` 后与 annotation 比较。
2. 不解媒体，先基于 annotation 扰动生成 synthetic detections，明确记录 `perception.detection_source=synthetic_from_annotation`，用于验证漏检/误检/置信度下降工具链。

第一版先走第二条，保证可复现；第一条作为 P4 真实感知增强。

### 6.4 第四阶段：事故/异常数据候选

调研后，不存在一个“同时有真实传感器、被测 planner 输出、控制指令、fault_type、root_module、fault_start_time”的理想公开数据集。更现实的选择是分层使用：

| 数据集/框架 | 可用价值 | 局限 | 项目用法 |
| --- | --- | --- | --- |
| DeepAccident | CARLA 合成 accident/normal，含多视角 RGB、LiDAR、V2X 和标签，mini 有 20 个场景 | 合成数据，不天然有本项目模块根因 | P4.5 下载 mini，做 accident detection / failure sample adapter |
| SafeBench | CARLA 安全关键场景和评价平台 | 需要跑 CARLA，环境重 | P5 生成闭环失败样本和 oracle |
| DriveFuzz | 可发现 Autoware/Behavior Agent misbehavior，输出测试用例和 bug metadata | 复现实验环境重 | 借鉴故障注入、test oracle 和失败样本结构 |
| DoTA/DADA | 真实驾驶视频事故/异常，含时间/空间/类别标注 | 没有自动驾驶内部日志，不能直接做 root_module | 可作为 accident/anomaly 时间定位补充，不作为 MVP 主数据 |

### 6.5 第五阶段：DriveLM / BDD-X 解释数据

该阶段作为增强，不放在第一版 MVP 中。

用途：

1. 评价诊断报告是否符合人类理解。
2. 训练或测试驾驶行为解释能力。
3. 构造“场景问题—推理链—诊断答案”样本。

---

## 7. 数据格式设计

### 7.1 场景样本 JSONL 格式

每一行表示一个异常场景：

```json
{
  "scenario_id": "carla_0001",
  "source": {
    "dataset": "carla",
    "version": "scenario_runner_v0_1",
    "raw_log_id": "Town05_front_brake_0001",
    "raw_tokens": {}
  },
  "meta": {
    "coordinate_frame": "world",
    "distance_unit": "meter",
    "time_unit": "second",
    "speed_unit": "m/s",
    "angle_unit": "radian",
    "frequency_hz": 10,
    "duration": 10.0
  },
  "frames": [],
  "events_observed": [],
  "oracle": {
    "visible_to_diagnosis": false,
    "fault_type": "perception_miss",
    "root_module": "perception",
    "fault_start_time": 4.2,
    "fault_segment": [4.2, 5.1]
  }
}
```

注意：`oracle` 只允许评估脚本读取，诊断流程、Rule-only、Single-LLM 和 Multi-Agent + Tools 均只能读取 `ScenarioRecord.observed_view()`。

### 7.2 ego 状态格式

```json
{
  "timestamp": 4.2,
  "x": 12.4,
  "y": 8.7,
  "yaw": 1.57,
  "vx": 12.8,
  "vy": 0.1,
  "acceleration": -0.2,
  "lane_id": "lane_03"
}
```

### 7.3 目标对象格式

```json
{
  "timestamp": 4.2,
  "object_id": "veh_001",
  "class": "vehicle",
  "x": 24.1,
  "y": 8.9,
  "vx": 0.0,
  "vy": 0.0,
  "length": 4.5,
  "width": 1.8,
  "is_key_object": true
}
```

### 7.4 感知输出格式

```json
{
  "timestamp": 4.2,
  "detected_objects": [
    {
      "track_id": "det_001",
      "class": "vehicle",
      "confidence": 0.21,
      "x": 24.3,
      "y": 8.8,
      "length": 4.4,
      "width": 1.9
    }
  ]
}
```

### 7.5 规划轨迹格式

```json
{
  "timestamp": 4.2,
  "trajectory": [
    {"t": 0.0, "x": 12.4, "y": 8.7},
    {"t": 0.5, "x": 18.2, "y": 8.7},
    {"t": 1.0, "x": 24.0, "y": 8.8}
  ],
  "planner_intent": "keep_lane",
  "target_speed": 12.0
}
```

### 7.6 控制输出格式

```json
{
  "timestamp": 4.2,
  "steer": 0.02,
  "throttle": 0.35,
  "brake": 0.00
}
```

### 7.7 诊断输出格式

```json
{
  "scenario_id": "carla_0001",
  "predicted_fault_type": "perception_miss",
  "root_cause_module": "perception",
  "fault_start_time_pred": 4.4,
  "confidence": 0.86,
  "evidence": [
    {
      "time": 4.2,
      "type": "confidence_drop",
      "description": "front vehicle confidence dropped from 0.82 to 0.21"
    },
    {
      "time": 4.6,
      "type": "ttc_violation",
      "description": "TTC decreased below 1.5s while brake command remained 0"
    }
  ],
  "recommendation": "Add rainy-night stationary vehicle samples and strengthen perception confidence calibration."
}
```

---

## 8. 故障类型体系

第一阶段建议定义 7 类故障：

| 编号 | 故障类型                       | 所属模块 | 描述           |
| -- | -------------------------- | ---- | ------------ |
| P1 | perception_miss            | 感知   | 关键目标未被检测到    |
| P2 | perception_false_positive  | 感知   | 检测出不存在的障碍物   |
| P3 | perception_class_confusion | 感知   | 目标类别识别错误     |
| P4 | perception_confidence_drop | 感知   | 关键目标置信度异常下降  |
| D1 | planning_collision_risk    | 规划   | 规划轨迹与障碍物冲突   |
| D2 | decision_late_brake        | 决策   | TTC 过低但未及时制动 |
| C1 | control_delay              | 控制   | 控制指令延迟或响应不足  |

后续可扩展：

1. prediction_error：周围车辆轨迹预测错误。
2. rule_violation：交通规则违反。
3. lane_change_risk：危险变道。
4. over_conservative：过度保守。
5. multi_factor_failure：复合故障。

---

## 9. 指标工具设计

### 9.1 TTC 计算

TTC 用于衡量碰撞紧迫程度。

输入：

1. ego 车位置、速度。
2. 前方目标位置、速度。
3. ego 与目标的相对距离。
4. 相对速度。

输出：

1. 每个时间戳的 TTC。
2. TTC 最小值。
3. TTC 低于阈值的时间段。
4. 是否触发 TTC violation。

诊断逻辑：

如果 TTC 低于阈值，但规划轨迹仍保持原速度或控制指令未制动，则可能存在决策/控制问题。

### 9.2 碰撞风险检测

输入：

1. ego 规划轨迹。
2. 障碍物位置和尺寸。
3. 障碍物未来轨迹。

输出：

1. 是否碰撞。
2. 最近碰撞时间。
3. 最近距离。
4. 关联障碍物 ID。

诊断逻辑：

如果规划轨迹与障碍物发生空间重叠，则规划模块存在风险。

### 9.3 感知漏检检测

输入：

1. ground truth object。
2. detected object。
3. IoU / 距离匹配阈值。
4. 置信度阈值。

输出：

1. 漏检目标列表。
2. 是否漏检关键目标。
3. 漏检开始时间。
4. 漏检持续时间。

诊断逻辑：

如果关键目标在真值中存在，但感知输出中长时间缺失，则判定为感知漏检。

### 9.4 感知误检检测

输入：

1. detected object。
2. ground truth object。
3. 匹配阈值。

输出：

1. 误检目标列表。
2. 误检位置。
3. 误检持续时间。
4. 是否影响规划。

诊断逻辑：

如果不存在真实目标，但感知输出持续出现障碍物，并导致规划减速或绕行，则判定为感知误检导致的规划异常。

### 9.5 置信度异常检测

输入：

1. 目标置信度时间序列。
2. 目标距离。
3. 遮挡状态。
4. 天气信息。

输出：

1. 置信度突降点。
2. 置信度均值和方差。
3. 异常持续时间。

诊断逻辑：

如果关键目标在距离较近且无遮挡情况下置信度突然下降，可能说明感知模型在该场景下出现语义漂移。

### 9.6 轨迹偏离检测

输入：

1. ego 规划轨迹。
2. 可行驶区域地图。
3. 车道边界。

输出：

1. 是否偏离可行驶区域。
2. 偏离距离。
3. 偏离时间段。

诊断逻辑：

如果规划轨迹离开可行驶区域，则判定规划异常。

### 9.7 控制响应检测

输入：

1. 规划期望动作。
2. 实际控制指令。
3. ego 实际运动状态。

输出：

1. 制动延迟。
2. 加速度偏差。
3. 方向控制偏差。
4. 控制响应时间。

诊断逻辑：

如果规划已要求减速，但控制指令延迟执行，则判定为控制响应异常。

---

## 10. Agent 设计

### 10.1 Scenario Parser Agent

职责：

1. 读取 JSONL 场景数据。
2. 解析 ego、object、perception、planning、control 信息。
3. 检查数据完整性。
4. 将数据转换为统一内部状态。

输入：

```json
{
  "scenario_path": "data/scenarios/carla_0001.json"
}
```

输出：

```json
{
  "scenario_id": "carla_0001",
  "duration": 10.0,
  "available_signals": [
    "ego_states",
    "objects",
    "perception_outputs",
    "planning_outputs",
    "control_outputs"
  ],
  "data_quality": "valid"
}
```

### 10.2 Metric Calculator Agent

职责：

1. 调用 TTC、碰撞、漏检、误检、轨迹偏离等工具。
2. 生成统一指标表。
3. 输出风险时间线。

输出示例：

```json
{
  "min_ttc": 0.92,
  "ttc_violation_start": 4.6,
  "collision_risk": true,
  "perception_miss_start": 4.2,
  "planning_collision_start": 4.8,
  "control_delay": 0.6
}
```

### 10.3 Perception Diagnosis Agent

职责：

1. 判断是否存在感知漏检、误检、类别混淆、置信度异常。
2. 给出感知层故障分数。
3. 输出证据链。

判断逻辑：

1. 如果关键目标在真值中存在，但感知输出缺失，则提高漏检分数。
2. 如果目标置信度突然下降，并且随后规划未及时避让，则提高感知诱发型故障分数。
3. 如果误检目标导致不必要减速，则判定为误检诱发规划异常。

输出示例：

```json
{
  "module": "perception",
  "fault_detected": true,
  "fault_type": "perception_miss",
  "fault_score": 0.82,
  "fault_start_time": 4.2,
  "evidence": [
    "Ground truth front vehicle exists at 4.2s",
    "Perception output does not contain matched vehicle from 4.2s to 5.0s",
    "TTC drops below safety threshold after the miss"
  ]
}
```

### 10.4 Planning Diagnosis Agent

职责：

1. 判断规划轨迹是否安全。
2. 判断规划是否对感知风险做出合理响应。
3. 判断是否违反车道、碰撞、TTC 等约束。

输出示例：

```json
{
  "module": "planning",
  "fault_detected": true,
  "fault_type": "planning_collision_risk",
  "fault_score": 0.64,
  "fault_start_time": 4.8,
  "evidence": [
    "Planned trajectory intersects with obstacle region at 5.1s",
    "Planner intent remains keep_lane despite TTC violation"
  ]
}
```

### 10.5 Control Diagnosis Agent

职责：

1. 比较规划意图与控制输出。
2. 判断是否存在制动延迟、方向响应不足。
3. 判断控制层是否放大了风险。

输出示例：

```json
{
  "module": "control",
  "fault_detected": false,
  "fault_type": null,
  "fault_score": 0.18,
  "evidence": [
    "Brake command rises after planner deceleration request",
    "Control delay is within acceptable threshold"
  ]
}
```

### 10.6 Root Cause Agent

职责：

1. 综合感知、规划、控制 Agent 的结果。
2. 判断主因和副因。
3. 生成根因排序。
4. 输出最终诊断标签。

根因评分可综合：

1. 故障开始时间：越早出现的异常越可能是根因。
2. 因果传递关系：上游异常是否导致下游异常。
3. 风险贡献度：该异常对碰撞风险的贡献。
4. 证据一致性：多个指标是否支持同一结论。

输出示例：

```json
{
  "root_cause": "perception_miss",
  "root_module": "perception",
  "top_causes": [
    {"cause": "perception_miss", "score": 0.82},
    {"cause": "planning_late_response", "score": 0.41},
    {"cause": "control_delay", "score": 0.18}
  ],
  "fault_start_time_pred": 4.2,
  "causal_chain": [
    "front vehicle missed by perception at 4.2s",
    "risk not recognized by planning module at 4.6s",
    "TTC dropped below threshold at 4.6s",
    "collision risk appeared at 5.1s"
  ]
}
```

### 10.7 Report Agent

职责：

1. 将结构化诊断结果转化为自然语言报告。
2. 报告必须引用具体证据。
3. 禁止无证据推断。
4. 输出工程师可读的事故诊断病历。

报告模板：

```text
场景编号：
异常类型：
主要根因：
故障开始时间：
关键证据：
1.
2.
3.

故障传播链：
感知阶段 →
规划阶段 →
控制阶段 →
最终风险

优化建议：
1.
2.
3.
```

### 10.8 Data Generation Agent

第一阶段可以只做简单版本。

职责：

1. 将故障案例转换为训练样本。
2. 生成场景标签。
3. 生成错误推理链和正确推理链。
4. 输出 JSONL 数据包。

输出示例：

```json
{
  "scenario_id": "carla_0001",
  "failure_case": {
    "wrong_reasoning": "The road ahead is clear, so keep lane and maintain speed.",
    "correct_reasoning": "A stationary vehicle exists ahead. The perception module missed it, and TTC is below the safety threshold. The vehicle should decelerate immediately."
  },
  "tags": [
    "rainy_night",
    "stationary_vehicle",
    "perception_miss",
    "late_brake"
  ]
}
```

---

## 11. LangGraph 状态设计

### 11.1 全局状态

```python
class DiagnosisState(TypedDict):
    scenario_id: str
    scenario_data: dict
    metrics: dict
    perception_result: dict
    planning_result: dict
    control_result: dict
    root_cause_result: dict
    report: str
    generated_sample: dict
    errors: list
```

### 11.2 图结构

```text
START
  ↓
parse_scenario
  ↓
calculate_metrics
  ↓
perception_diagnosis
  ↓
planning_diagnosis
  ↓
control_diagnosis
  ↓
root_cause_analysis
  ↓
report_generation
  ↓
data_generation
  ↓
END
```

### 11.3 条件分支

后续可以加入条件边：

1. 如果数据缺失，则进入 data_quality_warning。
2. 如果没有感知输出，则跳过 perception_diagnosis，仅做黑盒诊断。
3. 如果没有控制输出，则跳过 control_diagnosis。
4. 如果根因置信度低于阈值，则进入 human_review。
5. 如果诊断完成，则进入 report_generation。

---

## 12. MVP 实现路线

### 12.1 第一阶段：数据与格式打通

目标：

先不接大模型，先把场景数据和指标跑通。

任务：

1. 确定统一 JSONL 数据格式。
2. 用 CARLA 生成基础场景。
3. 记录 ego 状态、目标状态、规划轨迹、控制指令。
4. 实现故障注入模块。
5. 生成 100 个样本进行测试。

交付物：

1. data/scenarios/*.jsonl
2. scripts/generate_carla_scenarios.py
3. scripts/inject_faults.py
4. data_schema.md

### 12.2 第二阶段：指标工具实现

目标：

实现可计算证据。

任务：

1. 实现 TTC 计算。
2. 实现碰撞风险检测。
3. 实现感知漏检/误检检测。
4. 实现轨迹偏离检测。
5. 实现控制响应检测。
6. 输出统一 metrics.json。

交付物：

1. src/tools/ttc.py
2. src/tools/collision.py
3. src/tools/perception_eval.py
4. src/tools/planning_eval.py
5. src/tools/control_eval.py

### 12.3 第三阶段：Agent 流程实现

目标：

用 LangGraph 串联诊断流程。

任务：

1. 实现 Scenario Parser Agent。
2. 实现 Metric Calculator Agent。
3. 实现 Perception Diagnosis Agent。
4. 实现 Planning Diagnosis Agent。
5. 实现 Control Diagnosis Agent。
6. 实现 Root Cause Agent。
7. 实现 Report Agent。

交付物：

1. src/agents/
2. src/graph/diagnosis_graph.py
3. prompts/
4. /data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/reports/

### 12.4 第四阶段：可视化工作台

目标：

让系统能在答辩时展示。

任务：

1. 场景选择。
2. 轨迹图展示。
3. TTC 曲线展示。
4. 置信度曲线展示。
5. Agent 诊断过程展示。
6. 最终报告展示。
7. 实验指标表展示。

交付物：

1. app/streamlit_app.py
2. demo_cases/
3. figures/

### 12.5 第五阶段：实验评估

目标：

证明系统有效。

任务：

1. 构造测试集。
2. 实现 baseline。
3. 跑对比实验。
4. 统计指标。
5. 生成实验表格和图。

交付物：

1. experiments/run_eval.py
2. results/metrics.csv
3. results/summary.md
4. figures/comparison.png

---

## 13. Baseline 设计

为了证明多智能体系统有价值，至少设置三个 baseline。

### 13.1 Rule-only Baseline

只使用固定规则判断。

例如：

1. TTC < 1.5s 且 brake = 0，则判断为决策/控制故障。
2. 真值目标存在但检测目标不存在，则判断为感知漏检。
3. 规划轨迹与障碍物相交，则判断为规划故障。

优点：可解释。
缺点：难以处理复合故障。

### 13.2 Single-LLM Baseline

将场景摘要和指标一次性输入一个 LLM，让它直接输出诊断报告。

优点：实现简单。
缺点：容易忽略证据，输出不稳定。

### 13.3 Ours Multi-Agent + Tools

使用多 Agent 分模块诊断，并调用指标工具生成证据。

预期优势：

1. 模块诊断更清晰。
2. 根因链路更完整。
3. 报告证据覆盖率更高。
4. 对复合故障更稳定。

---

## 14. 实验指标

### 14.1 故障分类指标

用于评价系统能否识别故障类型。

指标：

1. Accuracy
2. Macro-F1
3. Precision
4. Recall

类别：

1. perception_miss
2. perception_false_positive
3. perception_confidence_drop
4. planning_collision_risk
5. decision_late_brake
6. control_delay

### 14.2 根因识别指标

用于评价系统能否找到主因。

指标：

1. Root Cause Top-1 Accuracy
2. Root Cause Top-3 Accuracy
3. Module-level Accuracy

例如真实主因是感知漏检，系统预测为感知模块，则模块级正确；预测为具体的 perception_miss，则类型级正确。

### 14.3 时间定位指标

用于评价系统能否定位故障开始时间。

指标：

1. Fault Start Time MAE
2. Detection Delay
3. Fault Segment IoU

例如真实故障开始时间为 4.2s，系统预测为 4.5s，则误差为 0.3s。

### 14.4 证据质量指标

用于评价报告是否有依据。

指标：

1. Evidence Coverage：有 `evidence_id` 支撑的结论数 / 总结论数。
2. Evidence Correctness：被引用证据中 `supports` 覆盖结论标签且 `contradicts` 不包含结论标签的证据数 / 被引用证据总数。
3. Hallucination Rate：无 `evidence_id` 支撑、`evidence_id` 不存在、或全部被引用证据均不支持/反驳该结论的结论数 / 总结论数。
4. Human Score：人工评分报告是否清楚、有用、可信。

### 14.5 系统效率指标

用于评价系统是否具备工程可用性。

指标：

1. Average Diagnosis Time
2. Token Cost
3. Tool Execution Time
4. Report Generation Time

---

## 15. 预期实验表格

最终论文或答辩中可以展示如下表格：

| 方法         | Fault Macro-F1 | Root Cause Top-1 | Time MAE(s) | Evidence Coverage | Hallucination Rate |
| ---------- | -------------: | ---------------: | ----------: | ----------------: | -----------------: |
| Rule-only  |           0.68 |             0.61 |        0.82 |              0.74 |               0.00 |
| Single-LLM |           0.72 |             0.65 |        1.14 |              0.58 |               0.21 |
| Ours       |           0.84 |             0.79 |        0.45 |              0.91 |               0.06 |

注意：上表中的数值是设计目标示例，真实实验需要跑完后填写。

---

## 16. 系统目录结构

建议代码仓库结构如下：

```text
Zhijia-Guardian/
├── README.md
├── configs/
│   ├── dataset.yaml
│   ├── thresholds.yaml
│   └── llm.yaml
├── data/
│   ├── sample_scenarios/
│   └── README.md
├── src/
│   ├── schemas/
│   │   ├── scenario.py
│   │   ├── metrics.py
│   │   └── diagnosis.py
│   ├── tools/
│   │   ├── ttc.py
│   │   ├── collision.py
│   │   ├── perception_eval.py
│   │   ├── planning_eval.py
│   │   └── control_eval.py
│   ├── agents/
│   │   ├── parser_agent.py
│   │   ├── metric_agent.py
│   │   ├── perception_agent.py
│   │   ├── planning_agent.py
│   │   ├── control_agent.py
│   │   ├── root_cause_agent.py
│   │   ├── report_agent.py
│   │   └── failure_sample_builder.py
│   ├── graph/
│   │   └── diagnosis_graph.py
│   ├── adapters/
│   │   ├── manual_adapter.py
│   │   ├── carla_adapter.py
│   │   └── safebench_adapter.py
│   └── utils/
│       ├── io.py
│       ├── visualization.py
│       └── logging.py
├── prompts/
│   ├── perception_diagnosis.md
│   ├── planning_diagnosis.md
│   ├── root_cause.md
│   └── report.md
├── experiments/
│   ├── run_eval.py
│   ├── baselines/
│   │   ├── rule_only.py
│   │   └── single_llm.py
│   └── metrics.py
├── app/
│   └── streamlit_app.py
├── scripts/
│   ├── generate_manual_scenarios.py
│   └── run_demo.sh
├── tests/
│   ├── test_schema.py
│   ├── test_metrics.py
│   └── test_no_label_leakage.py
└── docx/
```

注意：大数据、模型、实验输出不放仓库内，统一放 `/data5/lzx_data/Zhijia-Guardian`。实验输出必须使用 `/data5/lzx_data/Zhijia-Guardian/outputs/runs/{run_id}/`。

---

## 17. Prompt 设计原则

### 17.1 总原则

所有 Agent 的 Prompt 必须遵守：

1. 只能基于输入指标和证据判断。
2. 不允许编造未提供的数据。
3. 输出必须是 JSON。
4. 每个结论必须对应 evidence。
5. 如果证据不足，必须输出 uncertain。
6. 不允许直接给最终根因，除非当前 Agent 是 Root Cause Agent。

### 17.2 感知 Agent Prompt 核心模板

```text
你是自动驾驶感知诊断 Agent。
你的任务是根据 ground truth、perception outputs 和指标工具结果，判断是否存在感知层故障。

你必须检查：
1. 是否存在关键目标漏检。
2. 是否存在误检。
3. 是否存在类别混淆。
4. 是否存在置信度异常下降。
5. 感知异常是否发生在规划/控制异常之前。

你只能使用输入中的证据。
输出 JSON：
{
  "fault_detected": true/false,
  "fault_type": "...",
  "fault_score": 0-1,
  "fault_start_time": number/null,
  "evidence": [],
  "uncertainty": "..."
}
```

### 17.3 规划 Agent Prompt 核心模板

```text
你是自动驾驶规划/决策诊断 Agent。
你的任务是根据规划轨迹、TTC、碰撞检测、车道偏离和环境信息判断规划是否存在异常。

你必须检查：
1. 规划轨迹是否与障碍物冲突。
2. 是否在 TTC 过低时仍保持危险轨迹。
3. 是否偏离可行驶区域。
4. 是否存在过度保守或过度激进行为。
5. 规划异常是否由上游感知异常诱发。

输出 JSON。
```

### 17.4 根因 Agent Prompt 核心模板

```text
你是自动驾驶根因归因 Agent。
你会收到感知、规划、控制三个模块的诊断结果。
你的任务是判断主因和副因。

判断原则：
1. 更早发生且能解释后续异常的模块优先作为根因。
2. 如果感知异常导致规划错误，主因应偏向感知。
3. 如果感知正常但规划轨迹危险，主因应偏向规划。
4. 如果规划正确但执行失败，主因应偏向控制。
5. 如果证据不足，必须输出 uncertain。

输出 JSON。
```

---

## 18. 可视化设计

### 18.1 首页

功能：

1. 选择数据源：CARLA / nuPlan / nuScenes。
2. 选择场景 ID。
3. 选择 baseline 或多 Agent 方法。
4. 点击“开始诊断”。

### 18.2 场景回放页

展示：

1. ego 车辆轨迹。
2. 周围目标轨迹。
3. 规划轨迹。
4. 碰撞点或风险区域。
5. 故障发生时间点。

### 18.3 时间线页

展示：

1. TTC 曲线。
2. 关键目标置信度曲线。
3. ego 速度曲线。
4. brake 指令曲线。
5. 风险事件标注。

### 18.4 Agent 过程页

展示：

1. Scenario Parser 输出。
2. Metric Calculator 输出。
3. Perception Agent 结论。
4. Planning Agent 结论。
5. Control Agent 结论。
6. Root Cause Agent 结论。

### 18.5 报告页

展示：

1. 诊断摘要。
2. 根因排序。
3. 故障传播链。
4. 关键证据。
5. 优化建议。
6. 导出 PDF / Markdown。

---

## 19. 答辩 Demo 设计

建议准备 3 个典型案例。

### 案例 1：感知漏检导致追尾风险

故事线：

1. 雨夜场景中，前方静止车辆存在。
2. 感知模块在 4.2s 开始漏检前车。
3. 规划模块误以为前方道路可通行，保持车道和速度。
4. TTC 在 4.6s 降至安全阈值以下。
5. 系统诊断根因为感知漏检，规划响应不足为次因。

展示重点：

1. 置信度曲线下降。
2. 目标漏检证据。
3. TTC 曲线。
4. 根因链路。

### 案例 2：误检导致幽灵刹车

故事线：

1. 道路前方无真实障碍物。
2. 感知模块误检出静止车辆。
3. 规划模块触发急刹。
4. 系统诊断根因为感知误检。

展示重点：

1. 真值中无障碍物。
2. 感知输出中出现虚假目标。
3. brake 指令突然升高。

### 案例 3：感知正常但规划危险

故事线：

1. 前方障碍物被正确识别。
2. 感知置信度正常。
3. 规划轨迹仍穿过障碍物区域。
4. 系统诊断根因为规划轨迹风险，而非感知故障。

展示重点：

1. 感知正确。
2. 规划轨迹与障碍物冲突。
3. 系统能够区分“感知错”和“规划错”。

---

## 20. 项目创新点包装

### 创新点 1：从“自动驾驶模型开发”转向“自动驾驶诊断审计”

现有工作多关注如何提升驾驶模型性能，本项目关注模型出错后的解释、归因和修复建议，定位为智驾系统的诊断层和安全审计层。

### 创新点 2：基于分级可观测的本地化灰盒诊断

系统不要求获取车企源码、模型权重和原始训练数据，而是通过最小只读诊断接口读取运行日志、感知输出、规划轨迹和控制指令，在本地完成诊断。

### 创新点 3：多智能体协作的模块化根因归因

系统将复杂故障拆解为感知、规划、控制等模块，由不同 Agent 分别诊断，再由 Root Cause Agent 进行全局归因，提升诊断过程的可解释性和可复现性。

### 创新点 4：工具增强的可解释诊断

系统不让 LLM 直接猜原因，而是调用 TTC、碰撞检测、轨迹偏离、漏检检测等指标工具，用客观证据支撑诊断结论。

### 创新点 5：故障案例到训练样本的闭环转化

系统不仅输出事故报告，还将失败案例转化为结构化训练样本、场景标签和正确/错误推理对，为后续模型优化提供数据基础。

---

## 21. 风险与解决方案

### 风险 1：CARLA 搭建成本高

解决方案：

第一阶段可以先用自构造 JSON 场景数据模拟，不依赖完整 CARLA 渲染。先跑通诊断流程，再接入 CARLA。

### 风险 2：nuPlan / nuScenes 数据较大

解决方案：

先使用 mini 版本或抽样场景，只选取 50-100 个场景做验证，不做大规模训练。已下载的 nuPlan mini 结构化 DB 约 8.55GB、maps 约 0.97GB；sensor blobs 单包几十 GB，P4 阶段明确不下载。

### 风险 3：LLM 诊断幻觉

解决方案：

1. 所有 Agent 输出必须绑定 evidence。
2. 没有证据时输出 uncertain。
3. 最终报告中区分“确定结论”和“可能原因”。
4. 通过 Evidence Coverage 和 Hallucination Rate 评价报告质量。

### 风险 4：故障类型过多导致系统难做

解决方案：

MVP 只做 5 类故障：

1. 感知漏检。
2. 感知误检。
3. 置信度异常。
4. 规划轨迹危险。
5. 控制响应延迟。

### 风险 5：商业化被质疑车企不给数据

解决方案：

统一改成“本地化灰盒诊断”表述。系统不要求车企上传数据或开放权重，只在车企本地通过只读接口运行。第一阶段用公开数据和仿真验证技术可行性。

---

## 22. 开发排期

### 第 1-2 周：需求收缩与数据格式

1. 确定故障类型体系。
2. 设计 JSONL 数据格式。
3. 构造 20 个手工测试场景。
4. 实现数据读取和可视化雏形。

### 第 3-4 周：指标工具

1. 实现 TTC。
2. 实现碰撞检测。
3. 实现感知漏检/误检检测。
4. 实现控制延迟检测。
5. 输出 metrics.json。

### 第 5-6 周：LangGraph 多 Agent

1. 实现诊断图。
2. 实现 Perception Agent。
3. 实现 Planning Agent。
4. 实现 Root Cause Agent。
5. 实现 Report Agent。

### 第 7-8 周：CARLA 故障注入

1. 生成基础场景。
2. 注入故障。
3. 生成 200-500 个样本。
4. 跑自动诊断。

### 第 9-10 周：对比实验

1. Rule-only baseline。
2. Single-LLM baseline。
3. Multi-Agent + Tools。
4. 统计 F1、Top-1、时间定位误差。

### 第 11-12 周：可视化与答辩材料

1. Streamlit 工作台。
2. Demo 案例。
3. 实验表格。
4. 项目汇报 PPT。
5. 论文/软著材料整理。

---

## 23. 第一版可交付成果

第一版系统应至少交付：

1. 一个可运行的 Streamlit 诊断界面。
2. 100-500 个带真值标签的异常场景。
3. 5 类故障诊断能力。
4. 3 个完整 Demo 案例。
5. 一张对比实验表。
6. 一套自动生成的诊断报告。
7. 一份技术文档和数据格式说明。
8. 一份可用于软著的代码仓库。

---

## 24. 项目最终验收标准

### 24.1 功能验收

系统能够完成：

1. 读取异常场景。
2. 计算风险指标。
3. 识别故障类型。
4. 定位故障开始时间。
5. 生成根因链路。
6. 输出可解释报告。
7. 展示可视化时间线。

### 24.2 指标验收

建议目标：

| 指标                |     目标 |
| ----------------- | -----: |
| 故障分类 Macro-F1     | ≥ 0.80 |
| 根因 Top-1 Accuracy | ≥ 0.75 |
| 故障时间定位 MAE        | ≤ 0.6s |
| 报告证据覆盖率           | ≥ 0.85 |
| 幻觉率               | ≤ 0.10 |
| 单场景平均诊断时间         |  ≤ 60s |

### 24.3 展示验收

答辩时能够展示：

1. 一个感知漏检案例。
2. 一个误检幽灵刹车案例。
3. 一个规划错误案例。
4. 每个案例有时间线、指标证据、Agent 诊断过程和最终报告。

---

## 25. 一句话总结

本项目第一阶段应做成一个“自动驾驶异常场景诊断工作台”：基于 CARLA 构造有真值标签的异常场景，用 LangGraph 编排多智能体诊断流程，用 Python 工具计算 TTC、碰撞、漏检、误检、轨迹偏离等客观指标，最终输出可解释根因报告，并通过故障分类 F1、根因 Top-1 准确率和故障时间定位误差证明系统有效。

项目不要一开始追求完整车企级平台，而应先证明三件事：

1. 系统能诊断出故障属于哪一类；
2. 系统能定位故障从什么时候开始；
3. 系统能给出有证据链的解释报告。

只要这三件事成立，你的新苗项目就从概念变成了可落地原型。
