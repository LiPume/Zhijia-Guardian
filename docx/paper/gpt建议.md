# 智驾卫士可落地技术借鉴与实施计划

更新时间：2026-06-25

本文件用于替换原先偏“论文/框架罗列”的建议，目标是把新苗计划书、`docx/design.md` 和现有论文资料收缩成一个能实际开发、能跑数据、能做对比指标、能展示产品原型的方案。

核心结论先写在前面：

1. 第一版不要复现端到端自动驾驶模型，也不要做“自动修复智驾模型”。第一版只做异常场景诊断工作台。
2. 先跑通 Canonical Scenario Schema、指标工具、根因诊断和可视化，再用 nuScenes mini/nuPlan mini 抽样验证真实 adapter，最后接 CARLA/SafeBench/ScenarioRunner。
3. 后续大数据、模型、仿真导出和实验结果统一放 `/data5/lzx_data/Zhijia-Guardian/`，代码仍放 `/home/lzx/Zhijia-Guardian`。
4. 当前 `repair` 环境不能直接跑实验；第一版原型直接复用 `yolo` 环境并补小包，避免重复下载 Torch，也不再新建 `car` 作为主环境。
5. 现成框架优先级调整为：先借鉴 nuScenes/nuPlan 的真实数据 schema 做 adapter contract，再用 `CARLA + ScenarioRunner` 做全链路仿真闭环，`SafeBench` 借鉴安全场景和评估框架，`DriveFuzz` 借鉴故障注入和测试 oracle，`DriveLM/Agent-Driver` 借鉴结构化推理模板，`Bench2Drive/carla_garage/TransFuser` 作为后续增强，不放进 MVP。

---

## 1. 对 design.md 的可行性修正

`design.md` 的方向基本正确：它已经把项目从“研发新自动驾驶模型”收缩到“异常场景诊断工具链”。但仍有几类内容不现实，需要在实现时降级。

| 原设计/计划书表述 | 可行性判断 | 修改后的落地版本 |
| --- | --- | --- |
| 非侵入式接入传感器原始信号、模型隐层特征、决策逻辑序列 | 对车企真实系统不现实；仿真和公开模型也不一定暴露隐层 | 第一版定义“灰盒只读日志协议”，只要求 ego 状态、GT 对象、感知输出、规划轨迹、控制指令；隐层特征设为 optional |
| 100% 适配主流异构算法架构、毫秒级对齐 | 申报书可写，工程上不可承诺 | 第一版只适配自定义 JSONL、CARLA 记录、nuScenes/nuPlan mini 的离线转换 |
| 几何原型空间诊断感知语义漂移 | 需要访问模型中间特征和大量标注原型，第一版成本高 | 第一版用 GT-object 与 perception-output 的匹配、漏检、误检、类别混淆、置信度突降来做感知诊断；原型空间作为二期增强 |
| 将隐式神经张量映射为结构化思维链 | 目前没有可靠通用方法，容易变成“编故事” | 第一版只做后验规则审计：用 TTC、碰撞、车道、制动延迟等指标解释规划/控制是否合理，不声称读取模型真实思维 |
| RLHF 自动修复流水线 | 太重，且需要被修模型和训练基础设施 | 第一版只输出 failure sample package：场景标签、错误推理、正确推理、建议补充数据；可做 SFT/DPO/RLHF-ready，不实际训练 |
| 城市 NOA 实车对比实验 | 数据和权限不可控 | 第一版使用 canonical 手工样本 + nuScenes/nuPlan 小样本 + 后续 CARLA/ScenarioRunner/SafeBench 生成带真值的可复现实验；真实车企数据只作为后续合作方向 |
| 500 个 CARLA 样本立即生成 | 在 CARLA 未安装、环境未确定前风险高 | 先手工/脚本生成 60-100 个 canonical JSON 回放样本，再抽 5 个 nuScenes/nuPlan 小样本验证真实格式，最后扩展到 20-30 个 CARLA 样本 |
| LLM 自由判断根因 | 幻觉风险高，评测不稳定 | 多 Agent 只读结构化指标；LLM 只做证据约束下的归纳和报告生成 |
| 复现 HE-Drive/ComDrive、UniAD、VAD、SparseDrive | 训练和依赖都重，不适合作为新苗 MVP | 只借鉴中间信号、轨迹评分和舒适性指标，不复现模型 |

一句话：第一版的创新不要落在“我能解释任何自动驾驶大模型内部”，而是落在“我能把异常场景日志变成有指标、有根因、有证据链、有报告、有对比实验的诊断结果”。

---

## 2. 当前环境检查结论

已检查本机 `/data5/lzx_data` 与多个 conda 环境。后续数据统一放在：

```text
/data5/lzx_data/Zhijia-Guardian/
```

原因：

1. `/data5` 总容量约 7.0T，当前可用约 1.5T。
2. `/home` 所在根分区只剩约 214G，且使用率已到 97%，不适合放 CARLA、Bench2Drive、nuPlan、视频帧和实验输出。
3. 项目代码仍放 `/home/lzx/Zhijia-Guardian`，大数据、模型、仿真导出和实验输出放 `/data5/lzx_data/Zhijia-Guardian`，用配置文件关联。

已检查 `/home/lzx/miniconda3/envs/repair`：

| 模块 | repair 环境状态 |
| --- | --- |
| Python | 3.11.15 |
| langgraph | 已安装，版本 1.2.4 |
| langchain-core / langchain-openai | 已安装 |
| openai / fastapi / pydantic | 已安装 |
| numpy / pandas | 未安装 |
| torch | 未安装 |
| streamlit | 未安装 |
| carla / srunner / leaderboard | 未安装 |
| shapely / opencv / matplotlib / plotly | 未安装 |

本机系统与硬件：

| 项目 | 状态 |
| --- | --- |
| OS | Ubuntu 22.04.5 LTS |
| GPU | 8 x RTX 4090D |
| 内存 | 125 GiB |
| 磁盘剩余 | 约 214 GiB，根分区使用率 97% |

已补充检查其他 conda 环境：

| 环境 | Python | 体积 | Torch/CUDA | 关键已有包 | 缺口 | 判断 |
| --- | --- | ---: | --- | --- | --- | --- |
| `yolo` | 3.10.19 | 5.7G | torch 2.5.1+cu121，可用 8 张 4090D | ultralytics、opencv、numpy、pandas、scipy、matplotlib、seaborn | shapely、plotly、streamlit、langgraph、pydantic/openai | 最适合作为原型基础，不必重复下载 Torch |
| `robotwin` | 3.10.20 | 8.3G | torch 2.4.1+cu121，可用 8 张 4090D | numpy、pandas、opencv、shapely、plotly、pydantic、openai、sklearn | streamlit、langgraph、ultralytics | 数据分析底子更全，也可用 |
| `yolo_world` | 3.9.25 | 8.7G | torch 2.0.0+cu118 | ultralytics、opencv、shapely、fastapi、uvicorn | Python 偏旧、LangGraph/Streamlit 缺失 | 更适合保留给 YOLO-World，不建议主用 |
| `p2a` | 3.10.20 | 7.4G | torch 2.5.1，可用 GPU | ultralytics、opencv、sklearn、numpy、pandas | shapely、streamlit、langgraph | 可备选，但和项目关系不如 yolo 直接 |
| `repair` | 3.11.15 | 289M | 无 torch | langgraph、openai、fastapi、pydantic | numpy、pandas、opencv、streamlit、carla | 适合 LLM/Agent 服务参考，不适合指标实验 |

判断：

1. `repair` 可以作为 LLM Agent/报告生成的参考环境，但不适合直接跑自动驾驶数据、指标、Streamlit、CARLA。
2. 为避免重复下载大体积 Torch，第一版诊断原型直接基于 `yolo` 环境补小包。
3. 不建议直接污染 `repair`，也不建议一开始从零建纯净 `car` 环境下载完整 Torch。
4. CARLA/ScenarioRunner 如果和现代包冲突，再单独建轻量 CARLA 生成环境；CARLA 环境只负责导出 JSONL，诊断环境负责分析。

推荐环境策略：

| 阶段 | 环境建议 | 原因 |
| --- | --- | --- |
| 不依赖 CARLA 的诊断原型 | 直接使用 `yolo` | 已有 Torch/Ultralytics/OpenCV/pandas/scipy，不必重复下载大包 |
| 原型需补的小包 | 在 `yolo` 中补 `shapely plotly streamlit langgraph pydantic openai scikit-learn` | 这些包相对小，安装成本远低于重装 Torch |
| CARLA + ScenarioRunner | 若兼容则装到 `yolo`；若冲突则单独建 `carla` 环境 | ScenarioRunner 官方要求版本与 CARLA 对齐 |
| SafeBench 原框架 | 单独按 SafeBench 推荐的 Python 3.8 + CARLA 0.9.13 更稳 | SafeBench README 推荐该组合，直接混到现代 LangGraph 环境风险较大 |
| 如果 CARLA PythonAPI 与 LangGraph Python 版本冲突 | CARLA 数据生成与诊断服务分进程 | CARLA 进程只产出 JSONL，诊断进程读取 JSONL，避免依赖互相污染 |

---

## 3. 第一版产品定义

产品名暂定：`DriveDiag-Agent / 智驾卫士诊断工作台`

第一版不是自动驾驶模型，而是一个面向异常驾驶场景的“诊断审计层”。

### 3.1 输入

输入必须标准化为 Canonical Scenario JSON / `ScenarioRecord`，手工样本和真实 adapter 都输出同一结构：

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

1. 诊断系统、Rule-only、Multi-Agent + Tools、Single-LLM 都只能读取 `ScenarioRecord.observed_view()`。
2. `oracle` 只允许 `experiments/run_eval.py` 读取。
3. `fault_type`、`root_module`、`fault_start_time` 只能放在 `oracle` 中，不能进入诊断输入。

`source` 用于保留真实来源信息：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `dataset` | 是 | `manual_json` / `nuscenes` / `nuplan` / `carla` / `safebench` |
| `version` | 是 | 数据版本 |
| `raw_log_id` | 否 | 原始 scene/log/scenario ID |
| `raw_tokens` | 是 | 原始数据 token 外键映射，手工样本可为空 |

`meta` 最少包含：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `coordinate_frame` | 是 | `ego` 或 `world` |
| `distance_unit` | 是 | `meter` |
| `time_unit` | 是 | `second` |
| `speed_unit` | 是 | `m/s` |
| `angle_unit` | 是 | `radian` |
| `frequency_hz` | 是 | 采样频率 |
| `duration` | 是 | 场景时长 |

`frames` 是主结构，每个 frame 至少包含：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `timestamp` | 是 | 当前帧时间 |
| `ego` | 是 | ego 位置、速度、加速度、yaw、车道 |
| `actors_gt` | 是 | 离线 benchmark 可用的环境对象真值 |
| `actors_gt_source` | 是 | `simulation` / `dataset_annotation` / `offline_reconstruction` / `unavailable` |
| `perception` | 是 | `available` + `detections` |
| `planning` | 是 | `available` + `trajectory_source/trajectory/intent/target_speed` |
| `control` | 是 | `available` + steer/throttle/brake |
| `map` | 是 | `available` + lane/drivable/speed_limit |

缺字段必须显式表达 `available: false`。例如：

1. nuScenes metadata-only：`actors_gt_source=dataset_annotation`，`perception.available=false`，`planning.available=false`，`control.available=false`。
2. nuScenes synthetic detection：`perception.available=true`，但 `perception.detection_source=synthetic_from_annotation`。
3. nuPlan 原始 DB：`actors_gt_source=dataset_annotation`，`control.available=false`，`planning.trajectory_source=expert_future` 时只能作为参考轨迹。
4. nuPlan + offline/perturbed planner：`planning.trajectory_source=offline_planner` 或 `perturbed_planner`，此时才评估 planner 输出风险。
5. CARLA-like：perception/planning/control 尽量全链路可用，`actors_gt_source=simulation`。

`planning.trajectory_source` 可选值：`expert_future`、`offline_planner`、`perturbed_planner`、`model_prediction`、`unavailable`。只有后三类中的 `offline_planner`、`perturbed_planner`、`model_prediction` 可用于诊断 planner 输出；`expert_future` 只能作为参考。

`scenario_id`、文件名和路径不得泄漏标签。允许 `manual_v0_1_000001.json`、`planning_like_nuplan/`；不允许 `perception_miss_001.json`、`control_delay_003.json`。

`oracle` 只给评估使用：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `visible_to_diagnosis` | 是 | 固定 `false` |
| `fault_type` | 是 | 真值故障类型 |
| `root_module` | 是 | 真值根因模块 |
| `fault_start_time` | 是 | 真值故障开始时间 |
| `fault_segment` | 否 | 真值故障时间段 |

第一版不要强依赖图片/LiDAR 原始数据。图片可以作为展示增强，不作为诊断必要输入。

### 3.2 输出

每个场景输出四类结果：

| 输出文件 | 内容 |
| --- | --- |
| `metrics.json` | TTC、最小距离、碰撞风险、漏检/误检、轨迹偏离、控制延迟等指标 |
| `diagnosis.json` | 预测故障类型、预测根因模块、预测故障开始时间、置信度、证据链 |
| `report.md` | 工程师可读诊断报告 |
| `failure_sample.json` | 可回流的数据包：标签、错误链、正确链、优化建议 |

诊断输出只能写预测值，例如 `predicted_fault_type`、`predicted_root_module`、`predicted_fault_start_time`，不能把 `oracle` 复制到输出中。

### 3.3 第一版故障类型

先固定 5 类，不要一开始扩到十几类：

| 类型 | 模块 | 定义 |
| --- | --- | --- |
| `perception_miss` | 感知 | GT 中存在关键目标，但感知输出持续缺失 |
| `perception_false_positive` | 感知 | GT 中不存在目标，但感知输出持续出现虚假障碍物 |
| `perception_confidence_drop` | 感知 | 关键目标未消失但置信度异常下降，并影响下游风险判断 |
| `planning_collision_risk` | 规划/决策 | 规划轨迹与障碍物区域重叠，或低 TTC 下仍保持危险轨迹 |
| `control_delay` | 控制 | 规划/风险已要求制动或转向，但控制输出延迟或不足 |

可选增加一个 `normal` 类，用于评估误报率。建议测试集中保留 10%-20% 正常场景，否则产品会变成“见什么都诊断为故障”。

---

## 4. 推荐借鉴框架与使用方式

### 4.1 CARLA + ScenarioRunner：第一优先级，跑最小闭环

用途：

1. 搭仿真世界。
2. 定义前车急刹、横穿行人、静止障碍物、cut-in、雨夜等场景。
3. 运行基础 ego agent，例如 CARLA BehaviorAgent/BasicAgent。
4. 记录 ego、object、planner/control 输出，转换成我们的 JSONL。

为什么比一开始上 SafeBench 更稳：

1. ScenarioRunner 是 CARLA 官方场景执行框架。
2. 官方文档明确要求 ScenarioRunner 版本与 CARLA 版本匹配，便于排错。
3. 可以先写少量自定义场景，不必理解完整 SafeBench 训练/评估体系。

落地方式：

1. 先安装 CARLA 0.9.16 或与本机 PythonAPI 匹配的版本。
2. 安装对应版本 ScenarioRunner。
3. 跑通官方示例。
4. 加一个 recorder/adapter，把仿真状态导出为本项目 schema。
5. 再做故障注入。

### 4.2 SafeBench：第二优先级，借场景库和安全评价框架

SafeBench 的价值很高，但不建议第一天就把它作为主代码底座改。

可借鉴：

1. safety-critical scenario 的组织方式。
2. perception/control evaluation 的分层思路。
3. scenario policy / ego policy / evaluation 的模块划分。
4. 并行跑多个场景的机制。
5. 碰撞、越界、路线完成度等安全指标。

需要注意：

1. SafeBench 官方 README 推荐 Ubuntu 20.04/22.04、Python 3.8、CARLA 0.9.13。
2. 该版本组合和现代 LangGraph/Streamlit 环境可能冲突。
3. 因此更推荐先把 SafeBench 当作“外部场景生产器”，让它输出日志，我们的系统读日志诊断。

本项目使用方式：

```text
SafeBench/ScenarioRunner 负责生成危险场景和基础评估
            ↓
adapter 转换为统一 scenario JSONL
            ↓
智驾卫士计算诊断指标与根因
            ↓
Streamlit 展示报告和对比实验
```

### 4.3 DriveFuzz：只借鉴思想，不直接作为第一版代码

DriveFuzz 很贴近“发现自动驾驶 bug”，但工程环境偏旧：论文/仓库使用 Ubuntu 18.04、Python 3.6.9，并且涉及 Autoware。

可借鉴：

1. 反馈驱动 fuzzing：改变天气、目标位置、速度、行人行为、遮挡等。
2. driving quality metrics：急刹、碰撞、越线、交通规则违反。
3. test oracle：定义“什么情况下算错”。
4. 把场景变异和故障发现分开设计。

不建议第一版照搬：

1. Autoware 依赖重。
2. Python 和系统版本太旧。
3. 我们的第一目标不是自动找 bug，而是诊断已有 bug 的根因。

落地迁移：

| DriveFuzz 概念 | 本项目迁移 |
| --- | --- |
| scenario mutation | 故障注入器：删除检测框、注入假目标、延迟 brake、扰动规划轨迹 |
| test oracle | TTC 阈值、碰撞、车道偏离、误检/漏检、控制延迟 |
| driving quality metrics | 诊断证据和实验指标 |
| bug finding | 异常样本生成与诊断测试集构造 |

### 4.4 DriveLM：借鉴图式问答和报告结构

DriveLM 的核心价值不是直接拿来做诊断，而是它把驾驶任务拆成 perception、prediction、planning、behavior、motion 等具有逻辑依赖的图式问答。

本项目可迁移为诊断问题图：

```text
Q1: 关键目标在 GT 中是否存在？
Q2: 感知输出是否识别到该目标？
Q3: 该目标是否造成低 TTC 或碰撞风险？
Q4: 规划轨迹是否避让该目标？
Q5: 控制指令是否及时制动/转向？
Q6: 最早异常发生在哪个模块？
Q7: 主因、次因和证据分别是什么？
```

第一版使用方式：

1. 不训练 DriveLM。
2. 不依赖 DriveLM 数据集。
3. 只借它的 graph-style reasoning 模板来设计 Report Agent 和 Root Cause Agent 的 prompt。

### 4.5 Agent-Driver：借鉴“工具库 + 记忆 + 推理引擎”，不做驾驶控制

Agent-Driver 用 LLM 调度工具、记忆和推理来做自动驾驶。本项目不能照抄它去输出轨迹，而应改成诊断。

迁移关系：

| Agent-Driver | 智驾卫士 |
| --- | --- |
| tool library | TTC、collision、miss detection、control delay 等指标工具 |
| cognitive memory | 历史故障案例库、阈值配置、规则知识库 |
| reasoning engine | Root Cause Agent |
| trajectory planning | 不做控制，只做诊断报告 |

### 4.6 carla_garage / TransFuser：第二阶段被诊断对象

carla_garage 是 CARLA Leaderboard 2.0 starter kit，包含 TransFuser++、expert driver、evaluation 和训练/评估代码。

可借鉴：

1. 作为后续更像论文的被测对象。
2. 使用其可视化/benchmark 脚本。
3. 用 TransFuser++ 或 PDM-Lite 产生更复杂规划输出。

不放进第一版原因：

1. 完整评估对 GPU/时间要求高。
2. 仓库依赖复杂。
3. 当前产品先要证明诊断链路，不是证明端到端驾驶能力。

### 4.7 Bench2Drive：第三阶段 benchmark，不做 MVP 主线

Bench2Drive 是基于 CARLA 的闭环多能力评测 benchmark，价值很高，但工程成本高。

根据 carla_garage 说明，Bench2Drive 包含 220 条短路线，每条含一个 safety-critical scenario；用 8 张 2080Ti 评估 TF++ 约需 4 小时。我们机器 GPU 足够，但磁盘和环境准备仍是成本。

使用建议：

1. 论文/答辩里作为二期 benchmark。
2. 第一版只借鉴它的“多能力评估”分类思想。
3. 等我们的 schema、指标、报告稳定后，再跑 Bench2Drive 子集。

### 4.8 nuPlan / nuScenes：第二阶段真实数据验证

nuPlan：

1. 适合规划/决策诊断。
2. 有真实规划 benchmark、simulation framework、metrics。
3. 全量超过 1,300 小时驾驶数据，不适合一开始下载全量。
4. 官方下载页仍要求账号和同意条款；但 AWS Open Data Registry 登记了公开 S3 bucket `motional-nuplan`，2026-06-26 已实测 S3 源站直链可下载。
5. 已下载 `nuplan-v1.1_mini.zip` 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuplan_mini/raw/`，大小 `8550100030` bytes；已下载 `nuplan-maps-v1.0.zip`，大小 `971557640` bytes；已下载 `nuplan_mini_sensor.txt`，大小 `2622` bytes。mini zip 和 maps zip 均已通过 `unzip -t`。
6. mini zip 内含 64 个 `data/cache/mini/*.db` SQLite 数据库，未压缩合计约 14.35GB；抽检样本 DB 包含 `log`、`ego_pose`、`lidar_pc`、`lidar_box`、`track`、`category`、`scene`、`scenario_tag`、`traffic_light_status` 等表。当前不下载 mini sensor blobs，因为单个相机/激光 zip 往往几十 GB，MVP 先用结构化 DB + maps。
7. nuPlan 不天然提供被测系统规划轨迹和控制命令；第一版 `nuplan_adapter` 只能把 expert future trajectory 或离线 planner 输出映射到 `planning.trajectory`，否则应显式 `planning.available=false`、`control.available=false`。
8. `scenario_tag` 可用于抽样和事件上下文，不能作为诊断 Agent 的 fault label 输入。

nuScenes：

1. 适合感知诊断。
2. 可以评估漏检、误检、类别混淆、置信度异常。
3. 不适合第一版做大规模训练。
4. `https://www.nuscenes.org/data/v1.0-mini.tgz` 已能 HEAD 访问，大小约 4.0GB；它不是 5 个小文件，而是完整 mini 包。第一版实现下载/抽样脚本，抽 5 个 sample 转成 ScenarioRecord 验证格式。
5. 2026-06-25 已下载 mini 包到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/raw/v1.0-mini.tgz`，实际大小 `4167696325` bytes；只解出 metadata 到 `/data5/lzx_data/Zhijia-Guardian/datasets/nuscenes_mini/extracted/v1.0-mini/`。
6. 实测 metadata 记录数：`scene=10`、`sample=404`、`sample_data=31206`、`ego_pose=31206`、`sample_annotation=18538`、`instance=911`、`category=23`、`sensor=12`。
7. 最小可用映射：`scene -> sample` 生成 frames，`sample_data(LIDAR_TOP) -> ego_pose` 生成 ego，`sample_annotation -> instance -> category` 生成 actors_gt；planning/control 在 nuScenes-like 场景中显式设为 `available=false`。

真实数据接入顺序建议：

1. P0.7 先做真实数据最小 adapter smoke test：nuScenes mini 抽 1 个 sample，nuPlan mini 抽 1 个 scene/scenario，只做 schema validate 和 observed view 检查。
2. 再接 nuScenes mini：当前 metadata-only 只能验证 schema/annotation 映射；真正图像/点云感知要么选择性解 5 个 sample 媒体并跑 detector，要么先用 annotation 扰动生成 synthetic detections。
3. 再接 nuPlan mini：验证 planning-like canonical schema 和 SQLite adapter；`scenario_tag` 只是上下文，`expert_future` 只是参考轨迹。
4. 最后接 CARLA/SafeBench/DriveFuzz：全链路和带 oracle 的失败样本最好，但环境最重。

有事故/异常标签的数据集调研结论：

| 数据集/框架 | 实际可用点 | 不能做什么 | 决策 |
| --- | --- | --- | --- |
| DeepAccident | CARLA 合成 accident/normal，含多视角 RGB、LiDAR、V2X、标签，mini 有 20 个场景 | 不天然给本项目的 root_module | P4.5 作为事故检测和 failure sample adapter 候选 |
| DoTA/DADA | 真实驾驶事故/异常视频，有时间/空间/类别标注 | 没有感知/规划/控制内部日志 | 只做 accident/anomaly 时间定位补充 |
| SafeBench | 安全关键场景、CARLA 闭环评估 | 需要安装 CARLA，工程重 | P5 生成带 oracle 的闭环失败样本 |
| DriveFuzz | 有 test oracle、bug metadata、失败测试用例思想 | 复现实验环境重 | 借鉴故障注入和失败样本结构 |

结论：nuScenes/nuPlan 支持“真实格式能跑”，不支持“天然故障诊断真值”；诊断指标必须依靠 manual perturbation、仿真、fuzzing 或事故数据集另建 oracle。

### 4.9 HE-Drive.pdf 的实际价值

本目录中的 `HE-Drive.pdf` 实际标题是 `ComDrive: Comfort-Oriented End-to-End Autonomous Driving`。它不是诊断论文，而是舒适性导向的端到端驾驶系统。

可借鉴：

1. 轨迹评分分为 safety cost 和 comfort cost。
2. 舒适性指标可包括纵向/横向加速度、jerk、方向盘角速度、曲率变化。
3. VLM 不直接驾驶，只动态调整 rule-based scorer 权重；这个思想可迁移为“LLM 不直接下诊断结论，只在指标证据范围内组织解释”。
4. 多候选轨迹 scoring 的思路可用于 Planning Diagnosis：判断规划是否选了风险更高或更不舒适的轨迹。

不建议复现：

1. sparse perception、DDPM motion planner、VLM-guided scorer 都太重。
2. 它解决的是“开得更舒适”，不是“错了以后如何诊断”。
3. 第一版只把 comfort/risk 指标纳入工具层。

---

## 5. 数据集与样本构造方案

### 5.1 MVP-0：真实数据兼容的手工/脚本合成 JSON 场景

目的：不依赖 CARLA，先证明诊断流程正确；但手工样本必须通过 Canonical Scenario Schema 生成，不允许临时字段。

样本数：60-100 个。

目录分三类：

```text
manual_json/
  v0_1/
    perception_like_nuscenes/
    planning_like_nuplan/
    full_stack_like_carla/
```

三类样本含义：

| 子集 | 模拟对象 | 必须有 | 可缺失 |
| --- | --- | --- | --- |
| `perception_like_nuscenes` | nuScenes | ego、actors_gt、actors_gt_source、perception.detections | planning/control |
| `planning_like_nuplan` | nuPlan | ego、actors_gt、actors_gt_source、map、planning.trajectory_source、planning.trajectory | perception/control |
| `full_stack_like_carla` | CARLA/车企日志 | ego、actors_gt、perception、planning、control、events | 尽量不缺 |

组成建议：

| 类别 | 样本数 |
| --- | ---: |
| normal | 10 |
| perception_miss | 15-20 |
| perception_false_positive | 15-20 |
| perception_confidence_drop | 10-15 |
| planning_collision_risk | 15-20 |
| control_delay | 15-20 |

样本必须加入噪声和边界情况，避免 Rule-only baseline 因数据太干净而虚高：

| 噪声/难度 | 做法 |
| --- | --- |
| 时间噪声 | 故障触发、观测异常、风险出现时间加入 ±0.2s 随机偏移 |
| 感知噪声 | confidence 随机波动，非故障帧也允许小幅抖动 |
| 目标噪声 | 目标位置、速度加入小幅高斯扰动 |
| 控制噪声 | brake/throttle/steer 加入延迟和抖动 |
| 复合故障 | 感知轻微异常 + 规划响应不足 |
| 边界样本 | TTC 接近阈值但不一定故障 |

这些样本不是最终论文实验，但可以保证：

1. schema 可用。
2. 指标工具可用。
3. Root Cause Agent 不胡说。
4. Streamlit 能展示。
5. baseline/eval 脚本能跑通。
6. 后续真实 adapter 输出同一个 ScenarioRecord，不需要重写 tools/agents。

### 5.2 MVP-1：CARLA + ScenarioRunner / BehaviorAgent

目的：生成带仿真过程和真值的异常场景。

建议场景：

| 场景 | 故障注入 | 标签 |
| --- | --- | --- |
| 前车急刹 | 删除/降低前车检测 | `perception_miss` / `confidence_drop` |
| 静止施工车 | 规划轨迹不避让 | `planning_collision_risk` |
| 幽灵车辆 | 注入不存在目标 | `perception_false_positive` |
| 雨夜行人 | 降低行人置信度 | `perception_confidence_drop` |
| 路口冲突 | 风险目标存在但规划不减速 | `planning_collision_risk` |
| 低 TTC 未刹车 | 延迟 brake 输出 0.5-1.0s | `control_delay` |

样本数目标：

| 阶段 | 数量 |
| --- | ---: |
| 跑通期 | 20-30 |
| 第一轮实验 | 100 |
| 答辩/论文图表 | 200-500 |

### 5.3 MVP-2：SafeBench 场景子集

目的：让实验不只是自己手写场景，增加说服力。

做法：

1. 在独立 SafeBench 环境跑 perception/control 场景。
2. 不先改 SafeBench 内核。
3. 写 adapter 把输出转为本项目 JSONL。
4. 用同一套诊断工具评估。

### 5.4 第二阶段：nuPlan mini / nuScenes mini

用途：

1. nuPlan mini：验证规划/决策诊断指标能迁移到真实关系型数据；控制链路缺失时显式 `control.available=false`。
2. nuScenes mini：验证感知漏检、误检、类别混淆诊断。
3. DriveLM：用于报告模板和问答式解释评估，不作为主数据集。

---

## 6. 指标工具确定

第一版指标必须全部可由 Python 确定性计算，不能依赖 LLM 猜。

| 工具 | 输入 | 输出 | 用途 |
| --- | --- | --- | --- |
| TTC | ego/object 位置速度 | 每帧 TTC、min TTC、violation 时间段 | 判断碰撞紧迫度 |
| min distance | ego/object bbox | 最小距离、最近目标 | 风险证据 |
| collision check | 规划轨迹、障碍物 bbox/轨迹 | 是否相交、碰撞时间 | 规划风险 |
| lane/drivable check | 轨迹、可行驶区域/车道 | 是否越界、偏离距离 | 规划异常 |
| miss detection | GT、感知输出 | 漏检目标、开始时间、持续时间 | 感知漏检 |
| false positive detection | GT、感知输出 | 误检目标、影响时段 | 幽灵障碍 |
| class confusion | GT 类别、感知类别 | 混淆目标、混淆矩阵 | 感知语义错误 |
| confidence drop | 目标置信度序列 | 突降点、持续时长 | 感知置信度异常 |
| control delay | 风险/规划要求、brake/steer 输出 | 延迟秒数、响应不足 | 控制故障 |
| comfort risk | ego acceleration/jerk/yaw-rate | 急加减速、jerk、横向不适 | 参考 ComDrive 的舒适性诊断 |

阈值初始建议：

| 指标 | 初始阈值 | 说明 |
| --- | ---: | --- |
| TTC violation | < 1.5s | 城市场景可调 |
| near miss | min distance < 1.0m | 取决于 bbox |
| perception miss | 连续缺失 >= 0.5s | 避免单帧误差 |
| false positive | 持续 >= 0.5s 且影响规划 | 避免无影响误检 |
| confidence drop | 下降超过 0.5 或低于 0.3 | 需按模型标定 |
| control delay | > 0.5s | 制动场景 |
| jerk high | > 5 m/s^3 | 舒适性参考阈值 |

阈值不应写死在代码里，应放 `configs/thresholds.yaml`。

---

## 7. 多智能体流程确定

不要做自由聊天式 Agent。每个 Agent 都是固定节点，输入输出都是结构化 JSON。

推荐流程：

```text
Scenario Parser
  -> Metric Calculator
  -> Perception Diagnosis
  -> Planning Diagnosis
  -> Control Diagnosis
  -> Root Cause Analysis
  -> Report Generation
  -> Failure Sample Builder
```

各 Agent 分工：

| Agent | 是否需要 LLM | 说明 |
| --- | --- | --- |
| Scenario Parser | 不需要 | 读取和校验 schema |
| Metric Calculator | 不需要 | 调用 Python 工具 |
| Perception Diagnosis | 可先不用 | 规则 + 指标即可 |
| Planning Diagnosis | 可先不用 | 规则 + 指标即可 |
| Control Diagnosis | 可先不用 | 规则 + 指标即可 |
| Root Cause Analysis | 默认不用 LLM，可选开启 | 综合模块结果，必须 evidence-bound |
| Report Generation | 默认不用 LLM，可选开启 | 生成自然语言报告，必须引用 evidence_id |
| Failure Sample Builder | 可先不用 LLM | 输出 JSONL 数据包 |

这能形成两个版本：

1. `Rule-only`：完全不用 LLM，作为 baseline。
2. `Multi-Agent + Tools`：各模块结构化诊断，默认不使用 LLM，作为 ours。

LLM 默认配置：

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

---

## 8. 对比实验设计

### 8.1 Baseline

至少做 3 个方法：

| 方法 | 描述 | 意义 |
| --- | --- | --- |
| Rule-only | 固定规则直接判断故障类型 | 可解释、稳定，是下限 |
| Single-LLM | 把场景摘要和指标一次性给 LLM | 验证自由 LLM 容易漏证据/幻觉 |
| Ours: Multi-Agent + Tools | 指标工具 + 模块 Agent + 根因 Agent + 报告 Agent，默认不使用 LLM | 主方法 |

可选增加：

| 方法 | 描述 |
| --- | --- |
| Tools + Flat Classifier | 指标向量 + sklearn 分类器 |
| Ablation: no evidence check | 去掉证据约束，看幻觉率变化 |

### 8.2 实验指标

故障分类：

1. Accuracy
2. Macro-F1
3. Precision / Recall
4. Confusion Matrix

根因识别：

1. Root Cause Top-1 Accuracy
2. Module-level Accuracy
3. Top-3 Accuracy（样本足够多时）

时间定位：

1. Fault Start Time MAE
2. Detection Delay
3. Fault Segment IoU

报告质量：

每条 evidence 必须有唯一 ID：

```json
{
  "evidence_id": "E_TTC_001",
  "metric_name": "min_ttc",
  "value": 0.92,
  "threshold": 1.5,
  "time": 4.6,
  "supports": ["planning_collision_risk", "control_delay"]
}
```

报告结论必须引用 evidence：

```json
{
  "claim": "车辆在低 TTC 条件下未及时制动",
  "evidence_ids": ["E_TTC_001", "E_BRAKE_002"]
}
```

指标定义：

1. Evidence Coverage = 有 `evidence_id` 支撑的结论数 / 总结论数。
2. Evidence Correctness = 被引用证据中 `supports` 覆盖结论标签且 `contradicts` 不包含结论标签的证据数 / 被引用证据总数。
3. Hallucination Rate = 无 `evidence_id` 支撑、`evidence_id` 不存在、或全部被引用证据均不支持/反驳该结论的结论数 / 总结论数。
4. Human Score：人工清晰度/可信度评分，可用于答辩展示。

效率：

1. Average Diagnosis Time
2. Tool Execution Time
3. LLM Token Cost
4. Report Generation Time

### 8.3 预期结果写法

不要在文档里提前填假的实验数值。答辩前可以放目标值，但论文/报告必须区分“目标”和“实测”。

建议目标：

| 指标 | 第一版目标 |
| --- | ---: |
| Fault Macro-F1 | >= 0.80 |
| Root Cause Top-1 | >= 0.75 |
| Time MAE | <= 0.6s |
| Evidence Coverage | >= 0.85 |
| Hallucination Rate | <= 0.10 |
| 单场景诊断时间 | <= 60s |

---

## 9. 代码组织建议

不要把 SafeBench、ScenarioRunner、carla_garage 这些大仓库直接复制进 `Zhijia-Guardian`。更规范的方式：

1. 外部框架独立 clone 到 `/data5/lzx_data/Zhijia-Guardian/third_party/`，避免占用根分区。
2. 本项目代码仓库只保留 adapter、schema、指标工具、Agent、可视化和实验脚本。
3. 用配置文件记录外部框架路径和数据根目录。
4. 所有大数据、仿真导出、模型权重、报告产物默认写入 `/data5/lzx_data/Zhijia-Guardian/`。

建议数据目录：

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

每次实验必须写入 `run_meta.json`：

```json
{
  "run_id": "20260625_zhijia_v0_1_rule",
  "method": "rule_only",
  "dataset": "manual_json_v0_1",
  "threshold_config": "configs/thresholds.yaml",
  "llm_config": "configs/llm.yaml",
  "git_commit": "...",
  "seed": 42
}
```

建议项目结构：

```text
Zhijia-Guardian/
├── README.md
├── configs/
│   ├── thresholds.yaml
│   ├── dataset.yaml
│   └── llm.yaml
├── data/
│   ├── sample_scenarios/        # 小样本可放仓库，便于演示和测试
│   └── README.md                # 说明大数据实际在 /data5/lzx_data/Zhijia-Guardian
├── src/
│   ├── schemas/
│   ├── tools/
│   ├── agents/
│   ├── graph/
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

第一轮真正要写的核心代码：

1. `src/schemas/scenario.py`
2. `src/adapters/base_adapter.py`
3. `src/adapters/manual_adapter.py`
4. `src/adapters/*_stub_adapter.py`
5. `src/tools/ttc.py`
6. `src/tools/collision.py`
7. `src/tools/perception_eval.py`
8. `src/tools/control_eval.py`
9. `src/agents/*`
10. `experiments/run_eval.py`
11. `app/streamlit_app.py`

Adapter contract：

```python
class BaseAdapter:
    def list_scenarios(self) -> list[str]:
        ...

    def load_scenario(self, scenario_id: str) -> ScenarioRecord:
        ...

    def export_json(self, scenario_id: str, output_path: str) -> None:
        ...
```

所有 tools 和 agents 只读取 `ScenarioRecord`，不直接读取 nuScenes/nuPlan/CARLA 原始数据。

---

## 10. 开发排期

### P-1：6 个 canonical demo 样本

目标：

1. 按 Canonical Scenario Schema 写 6 个最小 demo。
2. 每类 2 个：perception-like、planning-like、full-stack-like。
3. 每个 demo 都包含 `source/meta/frames/events_observed/oracle`。

验收：

1. 6 个样本能通过 schema 校验。
2. 诊断入口只拿 observed view，评估入口才读 oracle。

### P0：Canonical schema + ManualAdapter

目标：

1. 实现 `ScenarioRecord`。
2. 实现 `BaseAdapter` 和 `ManualAdapter`。
3. 所有 tools/agents 只接收 `ScenarioRecord` 或 observed view。

验收：

1. `manual_json` 能通过 adapter 输出 ScenarioRecord。
2. 不同字段缺失时可用 `available=false` 表达。

### P0.5：真实数据 adapter contract + stub adapters

目标：

1. 新增 `docs/adapter_contract.md`。
2. 新增 `docs/schema_mapping_nuscenes.md`。
3. 新增 `docs/schema_mapping_nuplan.md`。
4. 新增 `docs/schema_mapping_carla.md`。
5. 实现 `NuScenesStubAdapter`、`NuPlanStubAdapter`、`CarlaStubAdapter`。

验收：

1. manual_json、nuscenes_stub、nuplan_stub、carla_stub 都能输出同一个 ScenarioRecord。
2. 不同数据源缺失字段时，诊断流程能自动跳过对应 Agent。

### P0.6：三类 manual subset

目标：

1. 生成 `perception_like_nuscenes`。
2. 生成 `planning_like_nuplan`。
3. 生成 `full_stack_like_carla`。

验收：

1. 三类样本都能跑 schema + adapter + 可视化。
2. 每类都模拟真实数据可能出现的字段缺失。

### P0.7：真实数据最小 adapter smoke test

目标：

1. nuScenes mini 抽 1 个 sample 转 `ScenarioRecord`。
2. nuPlan mini 抽 1 个 scene/scenario 转 `ScenarioRecord`。
3. 输出到 `data/sample_scenarios/real_smoke_test/`。
4. 不跑诊断，只做 schema validate、observed view 检查、字段覆盖率统计。

验收：

1. nuScenes 输出 `actors_gt_source=dataset_annotation`、`perception.available=false`、`planning.available=false`、`control.available=false`。
2. nuPlan 输出 `actors_gt_source=dataset_annotation`、`control.available=false`，`scenario_tag` 只进入 context/events，不进入 oracle。
3. `oracle` 不存在或仅由 eval fixture 单独提供，诊断入口不能读取。

### P1：指标工具和 Rule-only baseline

目标：

1. TTC、最小距离、碰撞检测。
2. 感知漏检/误检/置信度突降。
3. 控制延迟。
4. 输出 `metrics.json`。

验收：

1. 60-100 个 JSON 样本跑通。
2. Rule-only baseline 有 F1/Top-1/MAE。

### P2：LangGraph 多 Agent 和报告

目标：

1. LangGraph 诊断图。
2. 模块 Agent 输出 JSON。
3. Root Cause Agent。
4. Report Agent。

验收：

1. 每个场景输出 `diagnosis.json` 和 `report.md`。
2. Single-LLM baseline 和 Ours 可比较。

### P3：Streamlit 产品原型

目标：

1. 场景选择。
2. 轨迹回放/BEV 图。
3. TTC/置信度/brake 时间线。
4. Agent 证据链。
5. 报告导出。

验收：

1. 3 个 Demo 案例完整可演示。
2. 评估表格可显示。

### P4：接 nuScenes mini 或 nuPlan mini

目标：

1. 优先接 nuScenes mini，抽 5 个 sample 验证 perception-like adapter。
2. 接 nuPlan mini，抽 5 个 scenario 验证 planning-like SQLite adapter。
3. 输出统一 ScenarioRecord。

验收：

1. 真实数据样本不改 tools/agents 即可进入流程。
2. 输出 `schema_mapping_*` 的字段覆盖情况。

### P5：CARLA/ScenarioRunner 或 SafeBench 接入

目标：

1. 优先在 `yolo` 中尝试安装 CARLA PythonAPI 和 ScenarioRunner 依赖。
2. 如果 CARLA 版本冲突，则单独建 `carla` 生成环境，只负责导出 JSONL。
3. 跑通官方示例。
4. 导出 20-30 个 CARLA 场景。
5. 接入故障注入。

验收：

1. CARLA 场景转成统一 ScenarioRecord。
2. 与手工样本共用同一套诊断工具。

### P6：扩展实验和答辩材料

目标：

1. 生成 100-300 个样本。
2. 跑 baseline 对比。
3. 出图表。
4. 整理软著/论文/答辩材料。

验收：

1. 有实验 CSV。
2. 有对比表和混淆矩阵。
3. 有 3 个高质量 Demo。

---

## 11. 答辩 Demo 固定三例

### Demo 1：感知漏检导致追尾风险

证据链：

1. GT 前车存在。
2. 感知输出连续缺失前车。
3. TTC 下降到阈值以下。
4. 规划未及时避让或控制未制动。
5. 根因：`perception_miss`，次因：规划/控制响应不足。

### Demo 2：误检导致幽灵刹车

证据链：

1. GT 前方无障碍物。
2. 感知输出持续出现虚假目标。
3. brake 指令突然升高或规划速度下降。
4. 无真实碰撞风险。
5. 根因：`perception_false_positive`。

### Demo 3：感知正常但规划危险

证据链：

1. GT 障碍物存在。
2. 感知正确识别。
3. 规划轨迹与障碍物 bbox 相交。
4. 控制按规划执行。
5. 根因：`planning_collision_risk`，不是感知问题。

这三个案例足够说明产品价值：不仅能发现异常，还能区分“感知错”“规划错”“控制错”。

---

## 12. 新苗计划书中的表述如何落地包装

计划书里原本有较强的创新措辞，实现时建议这样转译：

| 计划书概念 | 落地包装 |
| --- | --- |
| 算法结构描述协议 | 统一诊断日志 schema + optional adapter |
| 非侵入式接入 | 本地灰盒只读接口，不上传权重/源码 |
| 感知层原型诊断 | 第一版为 GT/感知匹配诊断；二期再做特征原型空间 |
| 结构化思维链审计 | 基于指标和安全规则的后验因果链审计 |
| RLHF 数据生成 | SFT/DPO/RLHF-ready failure sample package |
| 以诊代采 | 用诊断结果筛选高价值失败样本，生成回归测试/训练标签 |
| 多智能体协作 | LangGraph 固定状态图 + evidence-bound Agent |
| 车企级云平台 | 第一版 Streamlit 本地工作台，后续 FastAPI/权限/部署 |

这样既保留申报书的研究叙事，又不会在工程上承诺做不到的东西。

---

## 13. 最终推荐路线

### 必做

1. 统一 JSONL schema。
2. 100 个可跑的异常/正常样本。
3. TTC、碰撞、漏检、误检、控制延迟等指标工具。
4. Rule-only、Single-LLM、Multi-Agent + Tools 三组对比。
5. Streamlit 工作台。
6. 三个完整 Demo。
7. 证据约束诊断报告。

### 应做

1. CARLA + ScenarioRunner 跑通 20-30 个仿真样本。
2. 故障注入器。
3. SafeBench 子集 adapter。
4. 失败样本包输出。

### 暂缓

1. Autoware。
2. Bench2Drive 全量。
3. TransFuser/UniAD/VAD/SparseDrive 复现。
4. 几何原型空间特征诊断。
5. RLHF 真训练。
6. 真实车企 NOA 数据。

---

## 14. 参考来源

本次调研使用的主要来源：

1. SafeBench 官网：https://safebench.github.io/
2. SafeBench GitHub：https://github.com/trust-ai/SafeBench
3. DriveFuzz GitHub：https://github.com/dk-kling/drivefuzz
4. CARLA ScenarioRunner GitHub：https://github.com/carla-simulator/scenario_runner
5. CARLA Leaderboard GitHub：https://github.com/carla-simulator/leaderboard
6. CARLA 官方快速开始文档：https://carla.readthedocs.io/en/latest/start_quickstart/
7. carla_garage GitHub：https://github.com/autonomousvision/carla_garage
8. DriveLM GitHub：https://github.com/OpenDriveLab/DriveLM
9. Agent-Driver arXiv：https://arxiv.org/html/2311.10813v4
10. nuPlan devkit GitHub：https://github.com/motional/nuplan-devkit
11. Bench2Drive-VL GitHub：https://github.com/Thinklab-SJTU/Bench2Drive-VL
12. 本地计划书：`/home/lzx/Zhijia-Guardian/docx/paper/杭州电子科技大学-34-基于多智能体协作的自动驾驶可解释性诊断与优化研究.pdf`
13. 本地论文：`/home/lzx/Zhijia-Guardian/docx/paper/HE-Drive.pdf`，实际内容为 ComDrive 舒适性端到端驾驶论文

---

## 15. 一句话执行原则

先把“异常日志 -> 指标证据 -> 多 Agent 根因 -> 报告 -> 对比指标 -> 产品界面”这条链跑通，再接更大的自动驾驶框架。不要让 CARLA、Autoware、Bench2Drive、端到端模型训练这些重工程反过来拖死第一版产品。
