---
name: houdini-sop-workflow
description: 设计、构建、修改和交付可编辑的Houdini SOP程序化网络。适用于建模、散布、属性、VEX、曲线成形、模块装配和SOP动画；按任务读取构造方法、控制和观察资料。纯场景查询直接用工具；HDA界面、回调、打包、rig和Solaris使用对应领域技能。
---

# Houdini SOP Workflow

围绕用户要求建立可继续修改的SOP网络与HIP。根据任务选择表示、构建顺序和检查方法；简单编辑直接执行，复杂模型可以分模块推进。普通资产用节点网络，用户需要共享节点类型或工具时再封装HDA。

## 要求与构造

读取相关现场、原始要求和参考资料，明确要交付的形体、部件、控制与细节。`houdini_product`可按需记录复杂要求、修订和测量覆盖；定义不作为执行前提，也不代替观察最终结果。对会改变构造的未知选择询问用户，能查到的事实自行读取。

尺寸与关系使用共享来源，避免部件各自维护一套常量。新资产从源使用米制值与世界Y-up（X宽、Y高、Z深）；`modeling_dimensions`提供原始单位到场景值的换算。已有工程按实际单位与坐标适配。尺寸、厚度、间隙共同换算，最后检查实际输出。

默认同层逻辑模块；需要稳定公共接口、独立替换或导出时使用Subnet。陌生节点读`node_info`，未知动词读`verb_help`；用`build_module`或一批动词组合完成相关操作，直接消费执行结果和参数诊断。`None`保留空输入槽。

## 按需资料

| 当前问题 | 资料 |
|---|---|
| 要求、部件、状态与产品质量 | [质量合同](references/procedural-quality-contract.md) |
| 表示选择、原生源、曲线、表面与细节 | [建模方法](references/modeling-methods.md) |
| 可编辑的转轴、滑轨、重复、管线和附着构造 | [构造模板](references/procedural-recipes.md) |
| 模块输入输出、共享控制、装配关系 | [模块合同](references/module-quality-contracts.md) |
| 小批构建、修改与检查语法 | [SOP patterns](references/sop-patterns.md#9-小模块构建与检查-fast-path) |
| Boolean、拓扑、坐标、控制恢复与图像范围 | [执行与观察边界](references/execution-checkpoints.md) |
| 节点网络分组和交接布局 | [网络交接](references/network-handoff.md) |
| 用户明确要求多作者组件协作 | [组件协作](references/module-design-collaboration.md) |

参数界面使用`houdini-parameter-ui`，骨架或FK使用`houdini-rig-animation-workflow`，材质与正式渲染使用`houdini-solaris-karma-workflow`。教程任务从`houdini-video-tutorial`读取来源与目标；HDA/回调/工具打包使用`houdini-tool-development`。

## 观察与修改

按用户目标选择检查，观察能直接回答当前问题的输出。`verify_network`检查明确输出的计算与非空状态；表面完整性通过`geo_piece_stats(..., inspect=True, integrity_only=True)`显式读取。接合、数量、物理尺寸用相应几何检查；参数行为用`test_controls`执行代表性状态，并消费恢复结果。检查范围与结果一同报告。

`render_view`用于整体与局部观察。结合实际图像判断比例、漏件、接点和细节，数值测量与视觉各自说明能证明什么。能力或图片不可用时指出具体缺口。控制图像对照使用固定取景及覆盖所测状态的包络。

某个方法持续失败时缩小问题、读取错误或更换方法。修改参数、接线、源码、身份或拓扑后更新受影响的检查，保留其他有效工作。细节应有构造用途并跟随共享表面或局部坐标，不以面数或节点数代替质量。

## 交付与继续修改

非平凡资产保留清楚的最终输出，例如`OUT_ASSET`。Subnet/HDA公共接口用原生Output明确发布；最终交付包括可打开的HIP、有效控制与用户要求的文件。检查最后修改后的相关输出、保存实际文件，并按用户要求呈现。

复杂要求可以用`houdini_product(action="review")`查看保存、测量覆盖和具体回执；它是事实视图。未观察到的细节和视觉结果由作者继续核对。续接时读取原要求、已有输出和新增需求，按实际变更修订与继续构建。
