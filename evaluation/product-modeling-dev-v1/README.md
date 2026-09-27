# 程序化产品模型开发测试集

本目录的 12 道公开开发题用于定位 Houdini agent 在读图、整机建模、局部细节、修改后保持和交付判断上的问题。其中旋盖水瓶题观察中空壳体和面朝向；台钳题观察直线滑动，收纳盒与折叠手机支架观察铰链开合，手摇卷线盘观察真实轴孔与旋转传动，USB台式风扇区分护网的有意闭环与电源线的自由端。它们已可被开发者看到，不能当作未见题证明通用能力。

- [执行和独立评审方法](REVIEW_PROTOCOL.md)
- [案例清单](manifest.json)
- [评审侧阶段结论与可迁移证据索引（2026-09-26）](evaluator-only/stage-2026-09-26.md)：已完成开发试验的范围、缺口与接续入口，不交给建模作者。
- [下一轮单作者试验配置（评审侧）](evaluator-only/next-round-run-config.md)：固定输入、版本与预算，逐次保留中断/最终交付及独立重开证据，不交给建模作者。
- 校验：`node evaluation/product-modeling-dev-v1/scripts/validate.mjs`
- 准备隔离任务：`node evaluation/product-modeling-dev-v1/scripts/prepare-run.mjs --case task-lamp-build`
- 评审侧校验结果：`node evaluation/product-modeling-dev-v1/scripts/validate-review.mjs <评审结果.json>`

准备脚本只复制公开题面和 PNG；修改任务还必须提供上一轮实际保存的 HIP。运行时仍须将 agent 的文件访问范围限制在隔离目录；复制文件本身不构成沙箱。各案例及本目录的 `evaluator-only` 内容只供评审者读取。12 题尚未完成全量模型评测；已运行的输入/构造干预与厂家产品迁移试验见阶段索引，不能代替全量结果。本测试集没有自动视觉评分，评审需从最终 HIP 独立重开取证。
