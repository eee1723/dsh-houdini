# 程序化产品模型开发测试集

本目录的 7 道公开开发题用于定位 Houdini agent 在读图、整机建模、局部细节、修改后保持和交付判断上的问题。其中旋盖水瓶题还用于观察中空壳体、瓶口封合和面朝向。它们已可被开发者看到，不能当作未见题证明通用能力。

- [执行和独立评审方法](REVIEW_PROTOCOL.md)
- [案例清单](manifest.json)
- 校验：`node evaluation/product-modeling-dev-v1/scripts/validate.mjs`
- 准备隔离任务：`node evaluation/product-modeling-dev-v1/scripts/prepare-run.mjs --case task-lamp-build`

准备脚本只复制公开题面和 PNG；修改任务还必须提供上一轮实际保存的 HIP。运行时仍须将 agent 的文件访问范围限制在隔离目录；复制文件本身不构成沙箱。各案例的 `evaluator-only` 清单只供评审者读取。新测试集没有运行模型，也没有自动视觉评分；评审需从最终 HIP 独立重开取证。
