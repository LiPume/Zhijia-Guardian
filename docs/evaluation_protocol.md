# 最小评估协议

这是一组用于防止工作流退化成固定 DAG 的小型 synthetic evaluator，不是论文级 benchmark，也不衡量真实 openpilot route 的根因准确率。

## 当前矩阵

Evaluator 在 workflow 结束后才读取 synthetic manifest；workflow 内部仍只接收 oracle-free `DiagnosticCase`。当前四个可控故障为：

```text
perception_dropout          modelV2 -> longitudinalPlan
planner_gap                 longitudinalPlan -> carControl
sendcan_gap                 carControl -> sendcan
perception_and_sendcan_gap  两条竞争直接异常链路
```

每个 case 运行两种、使用同一组确定性工具的策略：

| 策略 | 行为 |
| --- | --- |
| `adaptive` | Message Flow evidence 触发 CAN、控制与 safety 后续检查 |
| `fixed` | 只要 topic 存在，就依次调用所有候选 specialist |

命令：

```bash
cd /home/lzx/Zhijia-Guardian
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
conda run -n Zhijia python scripts/evaluate_synthetic_matrix.py
```

输出为 `$ZHIJIA_DATA_ROOT/outputs/synthetic-matrix-evaluation.json`，不提交 Git。

## 当前可复现结果

在 2026-07-14 的当前实现中：

| 策略 | case 数 | 注入位置 Top-1 | finding evidence 完整率 | 平均工具调用 |
| --- | ---: | ---: | ---: | ---: |
| adaptive | 4 | 1.00 | 1.00 | 22.25 |
| fixed | 4 | 1.00 | 1.00 | 27.00 |

这只说明 adaptive routing 在这四个自有、可控合成案例上少调用了工具而未降低 location 命中；不能据此声称多 Agent 优于 pipeline，也不能外推到真实车辆。

## 尚未完成的评估

- 加入 delay、stale、CAN burst、安全阻断、观测缺失与更多多故障样例；
- 增加规则 first-match 与“动态路由但无竞争假设”基线；
- 消融 Evidence Auditor；
- 度量拒答质量、错误强结论率、置信度 ECE/Brier、时延与多故障区分；
- 对真实 qlog/rlog 仅报告覆盖、稳定性和可观测性，不构造根因 accuracy。
