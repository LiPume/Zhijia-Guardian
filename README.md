# 智驾卫士（Zhijia-Guardian）

> 面向 openpilot-like ADS 消息流与控制链路的工具增强型多 Agent 主动因果诊断工作流。

智驾卫士不是“通用事故根因判定器”。它面向一条 openpilot-like 离线消息时间线：确定性工具先计算事实；Agent 再形成可证伪假设、选择下一项检查或 synthetic 干预、比较预测与结果；Evidence Auditor 最终限制无证据结论。

**最快复现命令：**

```bash
cd /home/lzx/Zhijia-Guardian
conda run -n Zhijia python scripts/run_agentic_demo.py --config configs/demo.yaml
```

若还没有 `Zhijia` 环境，请先阅读下一节。

## 1. 项目边界

主诊断对象包括 rlog/qlog 或兼容输入中的 `can`、`sendcan`、`carState`、`carControl`、`controlsState`、`selfdriveState`、规划相关消息、`pandaStates`、`onroadEvents`，以及消息频率、缺失、延迟、依赖和控制指令传递关系。

系统输出异常链路的 `suspected_link`；当缺少可观测证据时会输出 `insufficient_observability`、`insufficient_evidence` 或 `cannot_determine_root_cause`。只有在受控 synthetic ADSLogRecord 回放中，干预结果符合预测时，系统才允许输出 `validated_root_cause`；它只代表该**注入机制**在该合成样例中被验证，不代表真实车辆事故根因。

特别说明：**nuScenes、nuPlan、commaCarSegments 不能组成同一条真实端到端路线。**

| 层级 | 数据源 | 当前用途 |
| --- | --- | --- |
| 主诊断 | openpilot-like / commaCarSegments | 单个 route/segment 的消息、CAN、控制链路证据 |
| 辅助感知 | nuScenes | 归一化感知 evidence adapter；永不声称和主路线相同 |
| 辅助规划 | nuPlan | 归一化规划 evidence adapter；永不声称和主路线相同 |
| 因果验证 | synthetic ADSLogRecord | 受控故障注入、repair/replay、oracle-only 评估 |
| 后续后端 | CARLA | 已有 ADSLogRecord adapter，尚未接入 CARLA runtime/recorder |

## 2. 系统要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Linux（已验证） | macOS/Windows 未作为当前复现目标 |
| Conda | Miniconda 或 Anaconda | 环境名固定为 `Zhijia` |
| Python | `3.12.x` | 当前 openpilot 参考版本要求 Python 3.12 |
| Git | 支持 shallow clone | 仅真实 qlog 路径需要克隆 openpilot 参考实现 |
| 网络 | 可访问 GitHub、PyPI 镜像和 OpenPilotCI | synthetic demo 不下载日志；首次安装仍需下载依赖 |
| 磁盘 | 建议至少预留 1 GB | 本项目与最小 qlog 很小；数据根可独立放到 `/data5` |

项目依赖分层如下：

| 安装 extra | 用途 |
| --- | --- |
| `.[dev]` | pytest 与 synthetic demo 开发验证 |
| `.[openpilot]` | `pycapnp`、`zstandard`、`numpy`、`pyzmq` 和真实 rlog/qlog 读取 |
| `.[llm]` | 可选 OpenAI/DeepSeek 的受限工具选择 |

## 3. 创建环境与安装

### 3.1 推荐方式：显式创建环境

```bash
cd /home/lzx/Zhijia-Guardian
conda create -n Zhijia python=3.12 pip -y
conda run -n Zhijia python -m pip install -e '.[dev,openpilot]'
```

检查环境：

```bash
conda run -n Zhijia python --version
conda run -n Zhijia python -c "import capnp, zstandard, pydantic, zhijia_guardian; print(zhijia_guardian.__version__)"
```

预期 Python 版本为 `3.12.x`。

### 3.2 使用环境文件

`environment.yml` 也可创建同名环境：

```bash
cd /home/lzx/Zhijia-Guardian
conda env create -f environment.yml
```

若 `Zhijia` 已存在，不要重复执行 `conda env create`；改用第 3.1 节的 `pip install -e` 命令更新项目即可。

### 3.3 可选 LLM 工具选择

默认模式无需任何 API key：

```bash
export LLM_PROVIDER=none
```

如需测试受限的 DeepSeek 路由，只安装可选依赖并在 shell 设置密钥；不要把密钥写入仓库：

```bash
conda run -n Zhijia python -m pip install -e '.[llm]'
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY='你的密钥'
export LLM_MODEL=deepseek-chat
```

DeepSeek 只接收 topic 名称并调用 `select_specialists`；它不读取消息 payload、oracle 或报告结论。缺少密钥或请求失败时会自动退化为离线确定性路由。

## 4. 配置数据根目录

所有数据、上游参考实现与运行产物都在 Git 仓库之外：

```bash
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
mkdir -p "$ZHIJIA_DATA_ROOT"/{reference,raw/openpilot,processed,synthetic,perturbed,outputs,cache}
```

默认配置文件是 [configs/demo.yaml](configs/demo.yaml)：

```yaml
data_root: /data5/lzx_data/Zhijia-Guardian
llm_provider: none
max_agent_rounds: 3
max_tool_calls: 30
injection:
  type: sendcan_gap
  topic: sendcan
  start_s: 4.0
  end_s: 5.2
```

可以复制该文件并修改 `data_root`、注入类型或时间窗；支持的 synthetic 注入有：

```text
sendcan_gap
topic_delay
perception_dropout
planner_gap
perception_and_sendcan_gap
```

## 5. 最快可复现路径：synthetic 主动诊断 demo

该路径**不需要下载 openpilot、rlog、视频、nuScenes、nuPlan 或 CARLA**。

```bash
cd /home/lzx/Zhijia-Guardian
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
export LLM_PROVIDER=none
conda run -n Zhijia python scripts/run_agentic_demo.py --config configs/demo.yaml
```

demo 会执行：

```text
clean openpilot-like ADSLogRecord
→ 注入 sendcan gap
→ 消息/CAN/控制/安全工具取证
→ hypothesis board
→ 按信息增益/成本选择 repair
→ counterfactual replay
→ validation
→ Evidence Auditor
→ 结构化报告
```

预期终端包含：

```text
最终结论: validated_root_cause / carControl -> sendcan
```

输出目录：

```text
$ZHIJIA_DATA_ROOT/outputs/synthetic-openpilot-perturbed/
├── diagnosis.json
├── evidence.jsonl
├── agent_trace.json
├── hypotheses.json
├── interventions.json
├── decision_board.json
├── report.md
└── failure_sample_package/manifest.json
```

其中 `validated_root_cause` 仅针对这个 synthetic 注入样例有效。

## 6. 真实 openpilot qlog smoke：下载位置与步骤

当前项目提供一个最小、公开、官方测试中使用的 qlog smoke 数据源：

| 文件 | 来源 | 体积（当前样例） | 下载后位置 |
| --- | --- | ---: | --- |
| `openpilotci-2019-06-13-segment3-qlog.bz2` | [OpenPilotCI 单 qlog](https://commadataci.blob.core.windows.net/openpilotci/0375fdf7b1ce594d/2019-06-13--08-32-25/3/qlog.bz2) | 约 236 KB | `$ZHIJIA_DATA_ROOT/raw/openpilot/` |

不要手动复制 URL；运行脚本即可只下载该单一文件：

```bash
cd /home/lzx/Zhijia-Guardian
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
conda run -n Zhijia python scripts/fetch_minimal_sample.py
```

该 qlog 是日志解析 smoke 样例，经过 qlog 抽样，可能没有 `can` / `sendcan` 等完整控制 topic；它不能替代完整 route 诊断数据。

### 6.1 获取 openpilot 参考实现

真实日志读取需要外部参考实现。下列脚本会进行 depth-one、blob-filtered 克隆，并初始化读取 cereal schema 所需的 `opendbc` 子模块：

```bash
cd /home/lzx/Zhijia-Guardian
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
bash scripts/setup_openpilot_reference.sh
export OPENPILOT_ROOT="$ZHIJIA_DATA_ROOT/reference/openpilot"
```

参考实现位于 `$ZHIJIA_DATA_ROOT/reference/openpilot/`，不属于本仓库，也不会被提交。脚本会复用已有目录；不需要安装完整 openpilot 车端栈。

### 6.2 解析官方最小 qlog

```bash
cd /home/lzx/Zhijia-Guardian
export ZHIJIA_DATA_ROOT=/data5/lzx_data/Zhijia-Guardian
export OPENPILOT_ROOT="$ZHIJIA_DATA_ROOT/reference/openpilot"

conda run -n Zhijia python scripts/inspect_openpilot_log.py \
  "$ZHIJIA_DATA_ROOT/raw/openpilot/openpilotci-2019-06-13-segment3-qlog.bz2" \
  --openpilot-root "$OPENPILOT_ROOT"
```

当前样例的预期摘要约为：`3707` 条消息、`239.99` 秒、包含 `carState`、`carControl`、`controlsState` 等 12 个 topic。

### 6.3 使用自己的单段 rlog/qlog

只下载你明确需要的单个公开或自有 `rlog.zst`、`qlog.zst`、`.bz2` 日志文件；不要下载视频，除非研究问题确实需要图像。将文件放在：

```text
$ZHIJIA_DATA_ROOT/raw/openpilot/
```

然后替换日志路径执行：

```bash
conda run -n Zhijia python scripts/inspect_openpilot_log.py \
  "$ZHIJIA_DATA_ROOT/raw/openpilot/你的日志.rlog.zst" \
  --openpilot-root "$OPENPILOT_ROOT"
```

目前 CLI 的真实日志入口用于解析和 topic 检查；完整主动故障注入/repair 验证只在可控 synthetic ADSLogRecord 中执行。真实日志缺少可控基线时，系统不会修改日志，也不会生成 `validated_root_cause`。

## 7. commaCarSegments、nuScenes、nuPlan 与 CARLA 数据策略

- **commaCarSegments：** 当前不自动下载数据集。只在后续需要时选择一个明确 segment，放入 `$ZHIJIA_DATA_ROOT/raw/openpilot/`，并通过同一 openpilot adapter 解析。禁止 clone 或批量下载整个集合。
- **nuScenes：** 当前只提供辅助感知 evidence adapter contract；不需要下载 nuScenes 才能运行 demo。它不与主 route 拼接。
- **nuPlan：** 当前只提供辅助规划 evidence adapter contract；不需要下载 nuPlan 才能运行 demo。它不与主 route 拼接。
- **CARLA：** 当前提供无 runtime 依赖的 `CarlaADSLogAdapter` 输入契约；没有 CARLA 安装或闭环 recorder 的复现要求。

## 8. 测试与验收

完整运行：

```bash
cd /home/lzx/Zhijia-Guardian
conda run -n Zhijia pytest -q
```

当前测试覆盖 schema、证据审计、真实 qlog smoke（数据存在时）、辅助 evidence adapter、synthetic 主动验证、感知/规划/底层故障族、歧义场景的信息增益选择和 CARLA-compatible record adapter。

在没有下载官方 qlog/参考实现的机器上，真实日志 smoke test 会以明确原因跳过；synthetic 核心测试不会跳过。

## 9. 常见问题

| 现象 | 处理方式 |
| --- | --- |
| `ModuleNotFoundError: capnp` | 重新执行 `conda run -n Zhijia python -m pip install -e '.[dev,openpilot]'` |
| 找不到 `opendbc` | 执行 `bash scripts/setup_openpilot_reference.sh`，它会初始化 `opendbc_repo` |
| `OPENPILOT_ROOT is required` | `export OPENPILOT_ROOT="$ZHIJIA_DATA_ROOT/reference/openpilot"`，或向检查脚本传入 `--openpilot-root` |
| qlog 缺少 CAN/sendcan | 这是 qlog 抽样或日志本身的可观测性限制；换用包含相应 topic 的单段 rlog，不要补造数据 |
| 没有 LLM key | 设置 `LLM_PROVIDER=none`；所有 demo 和测试均可离线运行 |
| 输出进入 Git 状态 | 检查是否使用了 `$ZHIJIA_DATA_ROOT`；`data/`、`outputs/`、日志、模型和 `.env` 已被 `.gitignore` 排除 |

## 10. Agent 架构与进一步阅读

- [Agent 逻辑架构](docs/agent_logic_architecture.md)
- [设计说明](docs/design.md)
- [主动因果工作流](docs/active_causal_workflow.md)
- [数据来源](docs/data_sources.md)
- [限制](docs/limitations.md)
- [旧版重校准说明](docs/legacy_recalibration.md)
