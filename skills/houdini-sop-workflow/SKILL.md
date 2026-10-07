---
name: houdini-sop-workflow
description: 设计、构建、修改和交付可编辑的Houdini SOP程序化网络。适用于建模、散布、属性、VEX、曲线成形、模块装配和SOP动画；按任务读取构造方法、控制和观察资料。纯场景查询直接用工具；HDA界面、回调、打包、rig和Solaris使用对应领域技能。
---

# Houdini SOP Workflow

## 目标与选择优先级

交付形体与关系正确、达到所需效果和性能、用户能继续修改的SOP网络与HIP。显式要求和已有工程的有效结构优先；简单编辑只改相关部分。

普通可编辑建模默认优先原生SOP承担标准成形与组合，VEX承担布局、属性和自定义算法。保留用户预期会改的路径、截面、源部件与局部工序；只有参数面板或可修改源码，不等于这些编辑入口已经存在。任务需要紧密耦合的自定义算法或专用库、目标超出适用原生方法，或相同输出下测得计算性能不足时，可以采用VEX/Python或混合表示，仍保留所需编辑入口和可检查输出。用户明确指定实现方式时按其要求执行。

效率比较构建、计算、验证和后续修改的总成本。节点数、Wrangle比例和代码长度不是目标；不为凑原生比例拆碎算法，也不只为少写节点而重写标准成形。具体选择见[表示与组合方法](references/modeling-methods.md#1-从表示和构造选方法)。

## 要求与构造

读取相关现场、原始要求和参考资料，明确要交付的形体、部件、控制与细节。复杂要求用DSH已有计划或工作区文件记录；结合原始资料与实际输出推进。对会改变构造的未知选择询问用户，能查到的事实自行读取。

尺寸与关系使用共享来源，避免部件各自维护一套常量。新资产从源使用米制值与世界Y-up（X宽、Y高、Z深）；`modeling_dimensions`提供原始单位到场景值的换算。已有工程按实际单位与坐标适配。尺寸、厚度、间隙共同换算，最后检查实际输出。

按实际编辑职责划分数据流；同一产品的不同部件可以使用不同表示，通过共享尺寸和连接关系装配。需要复用代码文件时，按[外部代码依赖](references/execution-checkpoints.md#外部代码依赖)处理实际加载和交付；普通建模不需要先建立外部构建脚本。

默认同层逻辑模块；需要稳定公共接口、独立替换或导出时使用Subnet。`node_info(parent,type_name)`查询创建前的类型卡，现有节点的参数用`list_parms`/`read_parms`；未知动词读`verb_help`。用`build_module`或一批动词组合完成相关操作，直接消费执行结果和参数诊断。`None`保留空输入槽。

## 按需资料

| 当前问题 | 资料 |
|---|---|
| 要求、控制名称与实际结构该如何验证 | [质量与检查选择](references/procedural-quality-contract.md) |
| 原生/VEX取舍、曲线/表面/细节构造 | [建模方法与诊断](references/modeling-methods.md) |
| 图中疑似漏件、脱离或断口，统计却通过 | [观察冲突的处理](references/procedural-quality-contract.md#观察冲突的处理) |
| 可编辑的转轴、滑轨、重复、管线和附着构造 | [构造模板](references/procedural-recipes.md) |
| 模块输入输出、共享控制、装配关系 | [模块合同](references/module-quality-contracts.md) |
| 小批构建、修改与检查语法 | [SOP patterns](references/sop-patterns.md#9-小模块构建与检查-fast-path) |
| Boolean、拓扑、坐标、控制恢复与图像范围 | [执行与观察边界](references/execution-checkpoints.md) |
| 节点入口、分组说明和交接布局 | 按名加载houdini-network-handoff |
| 用户明确要求多作者组件协作 | [组件协作](references/module-design-collaboration.md) |

参数界面使用`houdini-parameter-ui`，骨架或FK使用`houdini-rig-animation-workflow`，材质与正式渲染使用`houdini-solaris-karma-workflow`。教程任务从`houdini-video-tutorial`读取来源与目标；HDA/回调/工具打包使用`houdini-tool-development`。

## 观察与修改

按用户目标选择检查，观察能直接回答当前问题的输出。`verify_network`检查明确输出的计算与非空状态；表面完整性通过`geo_piece_stats(..., inspect=True, integrity_only=True)`显式读取。接合、数量、物理尺寸用相应几何检查；需要验证参数系统行为时用`test_controls`执行代表性状态并消费恢复结果，单次定值修改可直接回读相关输出。检查范围与结果一同报告。

控制名称和结构描述表达了什么，就检查对应的实际性质；能调值、有几何响应、表面闭合各自只证明一部分。拿不准测什么时读[检查与所声称的性质](references/procedural-quality-contract.md#检查与所声称的性质)。警告按下游影响处理，保留有用的部件身份、分组与方向信息，见[属性传播](references/sop-patterns.md#4-属性传播)。

`render_view`用于整体与局部观察。结合实际图像判断比例、漏件、接点和细节；有疑点时检查对应部件或关系，不以整体尺寸变化、控制点存在或计算通过代替。能力或图片不可用时指出具体缺口。控制图像对照使用固定取景及覆盖所测状态的包络。

某个方法持续失败时缩小问题、读取错误或更换方法。修改参数、接线、源码、身份或拓扑后更新受影响的检查，保留其他有效工作。细节应有构造用途并跟随共享表面或局部坐标，不以面数或节点数代替质量。

## 交付与继续修改

非平凡资产保留清楚的最终输出，例如`OUT_ASSET`。Subnet/HDA公共接口用原生Output明确发布。工程交付检查最后修改后的相关输出并保存实际HIP，说明有效控制；仅索要代码或说明时按请求提供，不额外包装工程。

用户接手新增资产、示例或多支路网络时，按名加载houdini-network-handoff，主动交付实际入口并按需要组织框与说明；不复制领域外的交接流程。文件与图片路径见其[文件交付](../houdini-network-handoff/references/file-delivery.md)。

结合本次操作回执、实际文件和图像核对要求。未观察到的细节与视觉结果由作者继续核对。续接时读取原要求、已有输出和新增需求，按实际变更继续构建。
