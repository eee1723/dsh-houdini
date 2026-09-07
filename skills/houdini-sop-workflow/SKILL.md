---
name: houdini-sop-workflow
description: 设计、构建、调试和交付 Houdini SOP 程序化网络。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询，也不代替rig或Solaris领域流程。
---

# Houdini SOP Workflow

以一个正确、可观察的原型推进。新增细节前先确认主要形体和实际连接；每次检查明确输出、方法与范围。

## 进入任务

先读Host现场摘要：HIP、版本、frame、选择、候选网络与采集时间。缺失不代表空场景；需要时用scene_info/find_nodes/graph补查。用户选择会变化，快照不构成foreign修改授权。

简单、规格完整的编辑直接修改并回读。普通可调模型用几句说明目标、自选尺寸、控制和验证范围。质量敏感、外部真实性或复杂装配在大规模建图前读[质量合同](references/procedural-quality-contract.md)；外部参考会改变方案且research/web可用时实际检索，无来源就标假设。只询问会改变方案的选择，一次给有影响说明的互斥选项，不因“程序化”启动长问卷。

## 执行循环

1. **方法与原型**：选择曲线/截面/开放表面/实体/实例等表示。集中关键控制，建立named anchors/local frames和稳定piece身份。明确模块输入、输出、属性class与不变量；多模块装配读[模块合同](references/module-quality-contracts.md)。
2. **当前节点知识**：用node_info(实际parent,type,parm_filter=...)只读当前操作需要的参数与operation_card；默认24项，先缩小filter再提高limit，避免扫描无关类型。filter是字面子串，空匹配先去掉filter重查，不因空卡创建一批probe。visible=false用search_tab_entries；未知签名先verb_help。
3. **骨架门**：只建代理体/中心线/主要截面，查世界位置、尺寸、方向和主连接。视觉交付已在范围内且GUI可用时，尽早看可辨认的整体或明确侧向图。主要比例/位置错误先修骨架，不进入细化。
4. **模块门**：一个build_module对应可独立cook的小模块和明确非空output；空CTRL/helper用tab_create。先验证单元再复制。检查实际表面/截面、封口意图、法线/属性与尺寸；闭合、共享边方向一致和朝外分别查，Normal不修顶点序。消费validation/cook_details，warning清理或解释。
5. **关系门**：每完成一个模块就和相邻模块集成检查。独立表面用适用的interfaces距离，融合Polygon才用共享拓扑。距离不等于有符号插入，bbox对称不等于几何镜像；接地覆盖每个要求的足部。没有可靠方法就保留unverified。
6. **参数门**：代表性控制测响应和需保持的不变量，再恢复。优先test_controls；范围/容差来自设计，不能观察失败后扩大窗口凑pass；耦合控制再测一个边界组合，滑条范围不等于有效参数域。修测试需独立理由与新样本/解析关系。只测bbox变化不证明连接或整个参数域。
7. **交付门**：集成后verify_network(parent,output=实际交付SOP)，最后一次相关修改后刷新必要统计、关系和图像。布局、恢复frame/selection/visibility、设sop_set_output，再保存。未命名HIP用有授权路径及当前HIP校验的scene_save_as；保存失败不能宣称完整交付。

模块与关系循环推进，不等所有细节完成才检查装配。此处骨架是代理形体，不是KineFX rig；几何父子/FK转rig skill。

## 执行与恢复

- build_module声明name/type/parms/inputs/output；None表示空输入槽。跨subnet使用Object Merge或明确端口。connect(src,dst,index)直接替换既有输入；Merge先断后接会前移丢分支，消费inputs_after。set_parms保持strict，不能以strict=False绕过构建失败。
- 组合构建声明required_outputs检查必需分支；preflight多项错误一次修正，保留node_info的components/usage_notes。最终分支保留语义primitive组，方便关系检查和局部取景。
- tab_create返回hou.Node；list_parms/read_parms返回list。菜单用token/set_value，菜单表达式用{expression,language}；普通数值字符串是HScript表达式，VEX在snippet内；tuple表达式用组件字段。见[fast path](references/sop-patterns.md#9-小模块构建与检查-fast-path)。
- 看transaction最终状态：同一exec后方失败可以撤销前方成功的build_module。先确认相关identity/存活输出；撤销过的打标缺失不是生成器无效证据，不沿用被回滚依赖；不熟悉的回读另开query，避免尾部格式化错误撤销构建。
- 同一模块边界连续两次失败，回到最后有效输出做最小单变量诊断或换方法；不反复全文重建多个未知模块，不catch mutation/cook异常后继续。
- 保留小状态摘要：当前输出/身份、未过关系、最新证据frame/时间、受影响修改；只重验受影响检查。

## 观察与关键方法

- geo_piece_stats默认按连接性或指定身份属性统计局部extent/面积；inspect=True观察命名primitive组的Polygon边界/边连通/非流形和basis下extent；shell_orientation保留有向体积条件。半径用到轴的欧氏距离，轴向投影不是半径。observed仅量测，分组切口可有意开放。
- geo_attrib_stats读驱动属性；geo_point_spacing全扫有序点弦长，不证明表面关系。test_controls的point_mean/面积可观察局部形变；位移指标要求稳定唯一id_attrib及相同面连接。数量参数测确切piece数/身份，native/packed不靠P-only。
- Copy to Points承担实例变换，模板orient/scale与原型局部轴需一致；Copy/Merge明确属性class和传播。带状物用有面积截面，非刚性成形通常先作用中心线/低维结构再生成厚度。细节见[方法参考](references/sop-patterns.md)。
- 每图绑定问题和部件。render_view(EXPLICIT_SOP,focus_group=...,isolate=...,projection='orthographic')用于局部观察；空组不能换整图冒充特写。返回framing.bounds可固定跨参数A/B，方向/分辨率/coverage也需一致。
- 消费render_view.check/render_check；空白、近黑、错误目标、严重裁切不通过。按media.inspection选择读图路由；先描述可见事实，再定位疑点，以对应几何/视角逐项核销。遮挡不等于缺件，无地面参照不能看图断言接地；勿整表pass。
- 用户屏幕异常才用viewport_screenshot；保留持久__dsh_houdini_*服务。纯网络交付或无GUI不强制追图，视觉未验证则明确报告。
- 动画至少两个相隔帧的实际几何/固定构图图像证据；A/B同framing_frame且覆盖帧包络。完全静止/方向错误是反例；细微审美无法裁定交给用户播放判断，不无限追图。

## 完成范围

最终显式输出非空、无error，warning已处理；单元与核心关系有对应实际输出证据；控制集中且代表性扰动/恢复通过。未测控制、unsupported、外部真实性、视觉不确定分别报告，不能用todo completed补证或把部分测量写成全部pass。关键控制不能靠重复改多个VEX常量维护。

普通收尾不自动委派；用户要求或具体疑点才快速review，复用已有工具事实与图像。不再登记delivery合同。
