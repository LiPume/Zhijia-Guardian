# Experiment Tables

这些 CSV 是 [实验分析报告](../experiment_analysis_report.md) 的机器可读数据源：

- `main_results.csv`：最终主结果及 run_id/commit。
- `manual_multiseed.csv`：五个 seed 的逐次结果。
- `manual_multiseed_aggregate.csv`：mean/std/min/max。
- `real_data_results.csv`：nuScenes detector 观察，不含 fault accuracy。
- `diagnosis_latency.csv`：确定性方法端到端计算延迟。

重新导出：

```bash
conda run -n yolo python experiments/export_experiment_tables.py
```

导出脚本只读取已有 run package 和 manifest，不重新运行模型或修改结果。
