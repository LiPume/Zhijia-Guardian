# 快速开始

运行：

```bash
conda run -n Zhijia python scripts/run_agentic_demo.py --config configs/demo.yaml
```

该命令只需要项目依赖，并将全部 artifact 写入配置的外部数据根目录。只有在设置 `OPENPILOT_ROOT` 并提供明确的本地 rlog/qlog 路径后，才使用 `scripts/inspect_openpilot_log.py` 解析真实日志。
