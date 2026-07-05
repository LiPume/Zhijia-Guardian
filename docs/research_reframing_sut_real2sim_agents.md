# 数据、被测系统与 Agent 边界修订

日期：2026-07-05

## 1. 结论

项目仍然可行，但研究问题必须从“给任意公开视频做自动驾驶根因诊断”收敛为：

> 对一个明确、版本冻结、能够记录 perception/planning/control 中间输出的被测自动驾驶系统，基于模块
> 证据和时序依赖进行离线故障定位；真实公开数据负责校准场景分布与验证接口，CARLA/nuPlan 闭环负责
> 生成可控故障和反事实真值。

三个直接结论：

1. nuScenes/nuPlan 没有原车 ADS 的故障标签和完整模块输出，不能据此评价原车根因诊断准确率。
2. 另跑一个 YOLO 不能“修好原车”。它要么是被测 perception SUT，要么是 reference monitor；两种角色必须分开。
3. 当前 Multi-Agent 本质是固定的模块化诊断图。它不是准确率提升的充分条件，必须与逻辑等价的单体流程比较。

## 2. 公共数据并非都“正确”，但通常没有系统故障真值

nuScenes 的 20 秒片段被挑选来覆盖多样、复杂和意外交通行为，并提供六相机、LiDAR、Radar 与 3D
annotation；它的主要任务是 detection/tracking 等感知评测，不提供采集车辆内部 perception、planner、
controller 的故障链。[nuScenes 官方说明](https://www.nuscenes.org/nuscenes)、
[nuScenes 论文](https://arxiv.org/abs/1903.11027)

nuPlan 来自大规模人类驾驶日志，贡献是 planner 闭环协议、reactive agents 和规划指标。日志中的 expert
future 不是“被测 planner 的错误输出”，但可以运行自己的 planner 后形成真正的 planning SUT。
[nuPlan 论文](https://arxiv.org/abs/2106.11810)

DoTA 和 DADA-2000 确实包含真实事故/异常视频，并有时间、空间或事故类别标签，但没有原车自动驾驶栈的
中间输出，因此适合评价事故发现和时间定位，不适合直接评价 `root_module`。
[DoTA 论文](https://arxiv.org/abs/2004.03044)、
[DADA-2000 论文](https://arxiv.org/abs/1904.12634)

DeepAccident、RiskBench 和 SafeBench 提供仿真事故、安全关键场景或风险对象。它们能补充事故后果和风险
识别，但“撞车”仍不自动等于“感知模块故障”；只有注入位置或 SUT 模块日志存在时，才能给模块根因。
[DeepAccident 论文](https://arxiv.org/abs/2304.01168)、
[RiskBench 论文](https://arxiv.org/abs/2312.01659)、
[SafeBench 官方场景](https://safebench.github.io/scenarios.html)

因此，公开数据应分三种用途：

| 数据 | 合理用途 | 不能直接声称 |
| --- | --- | --- |
| nuScenes | perception SUT benchmark、真实分布、正常误报率 | 原车系统根因诊断 |
| nuPlan | 真实规划上下文、运行新 planner、闭环规划指标 | expert future 是故障输出 |
| DoTA/DADA | anomaly/accident 时间与类别 | 内部 perception/planning/control 根因 |
| CARLA/SafeBench | 可控闭环、模块故障注入、反事实 | 完全代表真实世界频率 |
| DeepAccident/RiskBench | 风险识别、事故后果、外部验证 | 无注入信息时的内部模块根因 |

## 3. 五种 provenance 与三种诊断模式

后续 schema 和报告必须同时记录以下 provenance：

1. **World Reference**：仿真 actor truth、公开 annotation 或人工离线重建。在声明为白盒离线模式时可供
   诊断工具读取；真实车端通常没有。
2. **System Under Test**：真正被诊断的 perception/planner/controller 输出。
3. **Reference Monitor**：离线参考模型或独立规则，只能生成差异证据。
4. **Diagnosis System**：tools + 模块诊断 + 根因聚合，不重新驾驶车辆，也不替换 SUT 输出。
5. **Fault Oracle**：`fault_type/root_module/fault_start_time` 与注入 manifest，只允许 evaluator 读取。

这解决了一个容易混淆的问题：`actors_gt` 和故障答案不是同一种真值。离线 perception benchmark 可以用
annotation 判断 SUT 漏检，但 diagnosis 仍不能看到“漏检就是本样本标签”或注入模块名称。

产品必须按数据覆盖声明诊断模式：

| 模式 | 可见信息 | 能力边界 |
| --- | --- | --- |
| 白盒离线 | world reference + SUT 全栈输出 | 可做漏检/误检与跨模块根因 |
| 灰盒栈内 | SUT perception/planning/control，无 world truth | 可做模块一致性、时序传播和健康监控，不能证明未观测目标漏检 |
| 黑盒事件 | ego、最终控制、碰撞/接管等事件 | 可做异常阶段和候选原因，通常应输出 `uncertain` 而非精确模块根因 |

当前 nuScenes YOLO v0.1/v0.2 应解释为：冻结 YOLO 是公开数据上的 perception SUT，annotation 是
white-box world reference。
它没有使用采集车辆原始 detector 输出，所以结论只针对 YOLO，不针对 Motional 的采集车。

若未来同时有原车 detection 和离线 reference detection，可以计算：

- SUT 与 annotation/offline reconstruction 的 miss/FP/class discrepancy；
- SUT 与 reference model 的 disagreement；
- disagreement 是否在事故前持续出现；
- 下游 planner/control 是否响应了 SUT 的错误输出。

reference 更准确只说明它是一个离线反事实或复核信号，不代表在线原车已经被修复，也不能用 reference
输出覆盖 SUT 日志。

## 4. CARLA 不应“照抄视频”，而应做分布校准后的闭环实例化

真实到仿真的可落地方式分两层：

1. 从 nuScenes/nuPlan 提取 ego speed、相对速度、headway、TTC、actor density、横向偏移、道路曲率、
   遮挡/目标尺寸、天气和昼夜等场景描述符。
2. 用 CARLA ScenarioRunner/OpenSCENARIO 模板实例化统计相近的 following、cut-in、crossing、turning
   场景，并保存 real source token 与 sim 参数映射。

CARLA 地图、车辆动力学和渲染不可能与真实日志逐像素一致，所以必须报告 profile coverage 和 real-to-sim
gap。ScenarioRunner recorder 可在场景结束后查询 actor、control、加速度等信息并计算自定义指标，适合
保存统一的闭环诊断输入。[ScenarioRunner Metrics 官方文档](https://scenario-runner.readthedocs.io/en/latest/metrics_module/)

安全测试研究也普遍采用“运行完整 SUT，再注入或搜索故障”的方式。AVFI 在传感器输入、神经网络与输出
延迟处注入故障；DriveFuzz 在完整 ADS 上变异场景，并用交通规则 oracle 搜索违规；SafeBench 将场景模板
与多种生成策略组合。这些思路比直接修改最终 JSON 更接近本项目下一阶段。
[AVFI 论文](https://saurabhjha.one/pubs/DSN18b/paper.pdf)、
[DriveFuzz 论文](https://seulbae-security.github.io/pubs/drivefuzz-ccs22.pdf)、
[SafeBench 论文](https://arxiv.org/abs/2206.09682)

## 5. 下一版参考 SUT

建议先做可控且轻量的模块栈，不直接复现 Autoware 或大模型端到端驾驶：

```text
CARLA RGB + Depth/LiDAR
  -> frozen perception SUT
  -> tracked objects
  -> simple trajectory planner
  -> PID controller
  -> CARLA vehicle
```

CARLA actor truth 记录为 `world_reference`，只在白盒诊断和 evaluator 中使用。SUT perception 必须读取
传感器帧，planner 必须输出实际执行轨迹，controller 必须输出实际控制命令。每个父场景先跑 healthy，
再只改变一个故障变量运行 paired fault：

- sensor input：丢帧、遮挡、噪声、延迟；
- perception output：漏检、假目标、track swap、stale detection；
- planning output：stale trajectory、危险偏移、停止线违规；
- control/actuator：brake delay、饱和、命令丢失。

危险交通参与者属于 external hazard，不应自动标成 SUT fault。故障 oracle 来自注入 manifest；碰撞、急刹
和越线是后果。关闭注入后重跑同一 seed，比较首次输出分歧和违规是否消失，才能形成更强的因果标签。

## 6. Agent 到底有没有必要

> 2026-07-05 后续修订：本节对旧架构的判断仍成立，但新的 Agent 定义已扩展为 hypothesis、主动取证、
> Critic、Counterfactual、Optimization 和 Validation 闭环，详见 `docs/agent_redefinition_v2.md`。

当前实现不是开放式 Agent。`DiagnosisGraph` 固定执行 Metric、Scene、Perception、Planning、Control、Root
Cause；模块内部仍是确定性 evidence scoring。因此它已经接近“一整套写死流程”，只是把不同模块分成
有 typed contract 的节点。

这种拆分有四个合理价值：

1. nuScenes 缺 planning/control 时可以按模块明确 skip，而不是把缺失当正常。
2. 模块只看自己的 evidence，降低下游强信号覆盖上游根因的风险。
3. fan-in 能使用 perception -> planning -> control 的依赖和首次异常时间排序传播链。
4. 新增 localization、prediction、sensor-health 模块时可以保持输出契约和审计 trace。

但这些价值不自动意味着准确率更高。当前 Rule-only 不含同等时序因果逻辑，属于较弱基线。必须新增
`monolithic_causal_pipeline`，让它与 Multi-Agent 共享完全相同的 tools、阈值、模块证据和时序排序，
只去掉 Agent/DAG 封装：

- 若两者准确率相同，论文贡献应写“模块化、可审计、可扩展”，不能写“多 Agent 提高准确率”。
- 若字段缺失、复合故障、模块扩展时 Multi-Agent 更稳定，才可把收益归因于模块隔离与协作。
- LangGraph 只解决 checkpoint、interrupt/resume、重试等工程问题，不是诊断效果来源。

相关的自动驾驶模块化故障诊断研究也强调局部模块、统一诊断状态、依赖图聚合和状态感知，而不是让多个
大模型自由讨论。其依赖分析通过沿组件图回溯，区分上游故障与下游传播。
[Modular Fault Diagnosis Framework for Complex Autonomous Driving Systems](https://arxiv.org/abs/2411.09643)

## 7. 受控自由度

第一版允许的“Agent 自由度”只有：

- 根据字段覆盖选择/跳过模块工具；
- 根据 evidence conflict 触发额外一致性检查；
- 低置信度时输出 `uncertain`；
- 只有在预注册条件满足时调用 Visual Review/VLM；
- Root Cause 节点在 Top-K 候选中按依赖和时间排序。

禁止：自由更改阈值、调用任意外部数据、填补缺失字段、覆盖 SUT 输出、无 evidence 猜根因。所有路由必须
写入 trace，并在相同输入下可复现。

## 8. 实验主线调整

新的优先级是：

1. SUT provenance schema 与可诊断性分级。
2. 真实 profile 提取与 CARLA 轻量参考 SUT smoke。
3. healthy/faulty paired rollout 与 counterfactual oracle。
4. 逻辑等价 monolith baseline 和 Agent 必要性消融。
5. 扩大 real-calibrated CARLA 父场景与真实事故事件定位外部验证。
6. 最后再做 nuScenes 3D detector、Qwen 规模实验和 LangGraph 工程增强。

这一调整保留现有 Canonical Schema、tools、Agent、报告和 Streamlit，大部分代码不需要推倒重来；真正要
替换的是数据 provenance、CARLA SUT 输入来源和实验主张。
