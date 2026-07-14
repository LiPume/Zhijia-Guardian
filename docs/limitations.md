# 限制

- rlog/qlog 是观测边界：缺失 topic 或 qlog 抽样会产生 `insufficient_observability`。
- 时间 gap 能支持 producer/consumer 疑似链路，但不能证明进程、网络、车辆接口或安全层为何异常。
- CAN 地址解码保持通用；具体车型 DBC 语义不属于当前 MVP。
- 离线确定性模式用于展示工具使用编排，不代表在线 LLM 推理一定提高准确率。
- Synthetic 注入用于验证 workflow 机制，不是实际车辆故障结果。
- 成功的 synthetic repair/replay 只验证该注入机制，不能将真实 openpilot 日志的 suspected link 提升为已证实根因。
- nuScenes 和 nuPlan 在具备明确对齐数据集与来源协议前，只能作为辅助 evidence contract。
- CARLA ADSLogRecord adapter 已实现，但 CARLA runtime/闭环 recorder 尚未接入。
