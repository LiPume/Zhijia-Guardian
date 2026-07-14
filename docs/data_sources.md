# 数据来源

项目只在 `$ZHIJIA_DATA_ROOT/reference/openpilot` 中使用当前 openpilot 参考实现，创建方式为 depth-one、blob-filtered 克隆。adapter 通过上游 `LogReader` 兼容本地 `rlog.zst`、`qlog.zst` 和历史 `.bz2` 日志。

最小公开 smoke 输入来自 openpilot 自身 `tools/lib/tests/test_logreader.py` 当前引用的一条 OpenPilotCI qlog URL。`scripts/fetch_minimal_sample.py` 只会在显式调用时下载这一个文件。2026-07-14 获取的 `openpilotci-2019-06-13-segment3-qlog.bz2` 为 239,924 字节，独立 adapter 成功解析其中 3,707 条消息和 12 个观察到的 topic。

本仓库不会克隆 commaCarSegments、nuScenes 或 nuPlan，也绝不将它们视为同一物理控制路线。nuScenes 和 nuPlan 仅通过标明来源边界的辅助 evidence adapter 接入。
