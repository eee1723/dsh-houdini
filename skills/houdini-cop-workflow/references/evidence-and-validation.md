# 来源、边界与维护验收

本页只在维护/验证 skill 时加载。整体工作流为 candidate；具名连接、ImageLayer 观察/差值、
控制恢复和单通道浮点文件路径有 H21.0.440/H22.0.368 隔离机制回归，入口
`tools/tests/dsh-cop-contracts.test.py`（项目源码测试，不随 skill 引用加载）。
其中官方接口+本机复现支持窄范围 E2，不代表原教程修复、未见自然任务或新 session 采用已通过。
来源访问日期：2026-09-10；在线页标注 Houdini 22.0。未覆盖节点/模式需本机帮助与隔离实验确认。
原始视频/工程/trace 只作为用户授权的分析依据，不将内容、路径、目标数值或实例配方打包。

## 关键 claim / provenance

| Claim / 为什么改变决策 | Source | 适用与反例 | Validation |
|---|---|---|---|
| 图层通道、Type Info 与元数据端口不是同一概念；不能由类型兼容推导语义正确 | [Glossary](https://www.sidefx.com/docs/houdini/copernicus/glossary.html) | COP 图层；不用于推断旧 COP2 接口 | 同型错口仍可 cook 的反例 + 正确驱动响应 |
| 采样位置与尺寸参考分开；HSV 的不同辅助输入不等价 | [Noise](https://www.sidefx.com/docs/houdini/nodes/cop/fractalnoise.html)、[HSV](https://www.sidefx.com/docs/houdini/nodes/cop/hsv.html) | 当前节点模式；不是固定跨版本索引 | 两版本端口回读与单因素测试 |
| 图像/纹理空间及窗口不同 | [Spaces](https://www.sidefx.com/docs/houdini/copernicus/spaces.html) | 非方形/裁切/几何接口；不假定统一映射 | 非方形方向图和裁切后像素对应 |
| Cache 可保留旧图；输出默认尺寸不强制覆盖显式尺寸 | [Cache](https://www.sidefx.com/docs/houdini/nodes/cop/cache.html)、[ROP](https://www.sidefx.com/docs/houdini/nodes/cop/rop_image.html) | 缓存/导出；旧快照可能是合法意图 | 分层尺寸/新鲜度及读回测试 |
| Signed/offset 法线与消费方式有关 | [Normals](https://www.sidefx.com/docs/houdini/copernicus/normals.html) | 法线接口；编码不证明坐标基底相同 | 已知法线编码往返与材质消费 |
| Compiled cook 不适用于模拟 | [Cooking](https://www.sidefx.com/docs/houdini/copernicus/cooking.html) | H22 文档边界；不推导总是更快 | 静态结果比较与反馈场景的路线选择 |

原生读取接口依据 [CopNode](https://www.sidefx.com/docs/houdini/hom/hou/CopNode.html) 与
[ImageLayer](https://www.sidefx.com/docs/houdini/hom/hou/ImageLayer.html)。回归覆盖错误坐标口仍可cook、
正确驱动响应、动态undef、错误名/索引零连线写、ownership/Gate/回滚、多通道/整数、预算/Manual、
扰动失败恢复与恢复失败拒绝，以及最终浮点文件和隔离自建HIP重开；不是全COP API资格认证。
关系测量、证据失效、早期预览的自然任务采用仍是
单任务审计与项目执行合同支持的候选流程；艺术目标与数学不变量分开，不升级为固定美学阈值。
版本升级、runtime 与页面冲突或字段缺失时重新核对这些原页；更细字段仍由 runtime/节点卡维护。

## 可执行验收矩阵

在隔离新场景执行，不连接 live；不加载用户 HIP，不调用收费模型，不修改冻结 benchmark。
HOM 操作仍经项目 Bridge 主线程执行边界；按项目 development 的隔离 H21/H22 测试方法运行。
每项保留实际版本、节点/端口、参数、输出/文件证据和清理结果；下表是完整行为验收目标，
上述机制回归不核销模型选择、完整原任务和视觉判断。

| 用例 | 应观察到的决策/结果 |
|---|---|
| 原失败机制 | 坐标接 metadata 仍 cook 时拒绝语义通过；区分增量层和最终层，错误差值不触发资产调参 |
| 未见同族正例 | 非方形图像的坐标变换→遮罩→颜色合成与导出；检查两维坐标、混合关系和逐文件读回，不复用教程配方 |
| 相邻反例 | 只解析 COP 视频不加载构建 skill；仅用已有贴图渲染不加载 COP；单参数编辑不强制建预览场景 |
| 领域内反例 | 保持旧 COP2 不静默迁移；反馈模拟不走静态 compiled 路线；无需平铺的裁切图不强制接缝测试 |
| H21/H22 | parent-aware Tab、模式/端口、多输出引用、动态参数、数据观察、导出一致或明确分支；不可用记 unsupported |
| 失败恢复 | 控制扰动中途失败后恢复参数/keys/frame 并验证重新求值；缓存掩盖、无法恢复和重复失败均不误报成功 |
| 证据新鲜度 | 修改上游或交付尺寸后旧统计不能出现在最终完成声明中；只复验受影响门 |
| 条件区域与量程 | 相同全图均值但区域错位的遮罩不能通过；改变上游极值后重验覆盖/过渡，不沿用旧阈值的语义结论 |
| 文件与最终交付 | 非默认源输出→正确文件层；负值/HDR 编码、色彩转换和解码误差；获授权隔离重开后依赖可用 |
| 自然触发/效率 | 新 session 的 catalog 与资源可读；按阶段读取，不预载全部 workflow；记录首次正确 checkpoint、失败与重复探测 |

结构门：skill-creator 的 quick_validate、治理 audit --strict、npm run docs:check、npm test，
以及 npm pack --dry-run 的注册/资源检查。它们不证明上表模型行为、GPU 或视觉通过。
验收缺口只在 docs/handoff.md 的活动事项维护；临时结果留会话/CI，不在本页追加测试流水。
回滚用 Git 中本次精确 diff；保留用户其他修改，不删除整个 skills 或回退不相关文件。
