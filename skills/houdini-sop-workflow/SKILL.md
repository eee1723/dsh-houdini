---
name: houdini-sop-workflow
description: 设计、构建、修改和交付可编辑的Houdini SOP程序化网络。用于建模、散布、曲线成形、属性、VEX和SOP动画。纯场景查询直接用工具；HDA工具、rig、COP和Solaris使用对应领域技能。
---

# Houdini SOP Workflow

## 构造分工

交付形体、关系与性能符合要求，用户能继续修改的网络。先确定用户要改的路径、截面、源部件与局部工序；参数面板或可改源码不能替代这些入口。已有工程保留有效结构，只改相关部分。

| 构造职责 | 普通可编辑建模的默认方法 |
|---|---|
| 标准实体、封口、厚化、复制、局部加工 | 原生SOP承担成形：Box/Tube、Revolve、Sweep、PolyExtrude、Copy等；批量组合相关节点 |
| 锚点、布局、轮廓、中心线、方向、身份和属性规律 | 原生Curve/Line/Circle等能清楚表达时直接使用；不易表达的规律用VEX输出中间数据，再接成形节点 |
| 已有几何的自定义形变、属性计算 | VEX处理相应数据，保留输入形体和所需编辑入口 |

**直接生成网格的例外：**所需自定义拓扑/对应关系超出适用原生方法、必须使用专用库，或同等输出下已测得计算瓶颈时，可用VEX/Python或混合构造。数量多、公式复杂、熟悉代码或少写节点，本身不是重写标准成形的理由。性能看构建、计算、验证与后续修改总成本，不按节点数或Wrangle比例评分。

用户明确指定实现方式时遵从要求；教程已明确的方法沿[视频复现协议](../houdini-video-tutorial/references/reconstruction.md)，未规定部分再按这里选择。接口调用失败先查实际输入、模式和参数，不能据此认定原生方法不适用。

## 当前问题与资料

只读当前构造或疑点对应的小节。组合方法在下表资料中；精确参数、默认值和版本行为读`node_info(parent,type_name)`，现有参数读`list_parms`/`read_parms`，动词签名读`verb_help`。

| 当前决策 | 资料或入口 |
|---|---|
| 路径、截面、重复源如何组合 | [建模方法](references/modeling-methods.md#1-从表示和构造选方法) |
| 大量复制前验源；闭合却反向；同源错误扩散 | [源构件与成形检查](references/modeling-methods.md#源构件与成形检查)；Revolve先读`node_info(parent,'revolve')`的方向说明 |
| 倒角、细节、表面表示 | [局部操作](references/modeling-methods.md#2-选择先于倒角与局部操作)、[分层细化](references/modeling-methods.md#3-一个模块分层细化)、[表面表示](references/modeling-methods.md#表面表示与外观制作) |
| 转轴、滑轨、重复、管线、附着 | [构造模板](references/procedural-recipes.md) |
| 模块接口、共享控制与关系检查 | [模块合同](references/module-quality-contracts.md) |
| 所声称性质该测什么；图像与统计冲突 | [质量与检查选择](references/procedural-quality-contract.md) |
| 批量建网、VEX参数、属性传播 | [SOP patterns](references/sop-patterns.md) |
| Boolean、坐标、恢复、图像范围或代码文件依赖 | [执行与观察边界](references/execution-checkpoints.md) |
| 用户明确要求组件文件交换 | [模块文件与复用](references/module-design-collaboration.md) |

参数界面、骨架、图像数据制作、材质渲染分别按名加载`houdini-parameter-ui`、`houdini-rig-animation-workflow`、`houdini-cop-workflow`、`houdini-solaris-karma-workflow`；HDA/回调/打包使用`houdini-tool-development`。

## 构建、观察与继续修改

读取相关现场、要求和参考，复杂任务用DSH已有计划记录。尺寸、厚度、间隙和连接基准共享来源；新资产使用米制与Y-up，`modeling_dimensions`可换算原始单位，已有工程按现场适配。同层模块默认沿数据流组织；稳定公共接口或独立替换需要时再用Subnet。

围绕一个可观察单元，用`build_module`或一批动词组合构建；`None`保留空输入槽。大量复用前先验证源，发现公共源/函数错误时检查受影响消费者，方法见上表。原生节点同样需要正确输入与输出核对。

按目标选择证据：`verify_network`检查明确输出的计算与非空；`geo_piece_stats(..., inspect=True, integrity_only=True)`观察选定表面；`test_controls`执行所需代表性控制状态并报告恢复。局部组通过不扩展为整个模块通过，unsupported或超预算保留未验证。

用`render_view`的实际图像检查比例、漏件、接点与细节；疑点回到对应部件定位，A/B对照固定取景。未取得成功识图就报告视觉未验证。修改参数、接线或拓扑后只更新受影响检查；保留其他有效工作。

## 交付

非平凡资产保留明确最终输出，如`OUT_ASSET`；Subnet/HDA用原生Output发布公共接口。检查最后修改后的相关输出，再保存实际HIP并说明有效控制和未验证范围。仅要代码或说明时按请求交付。

用户接手新资产或多支路网络时，按名加载`houdini-network-handoff`组织入口、分组和文件交付；小改动不必重排整网。续接时结合原要求、已有输出和新增需求继续。
