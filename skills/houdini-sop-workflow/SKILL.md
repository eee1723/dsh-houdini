---
name: houdini-sop-workflow
description: 设计、构建、调试和交付 Houdini SOP 程序化网络，包括 SOP HDA 的内部几何输出。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询、工具UI/回调/打包开发，也不代替rig或Solaris领域流程。
---

# Houdini SOP Workflow

以一个正确、可观察的原型推进。新增细节前先确认主要形体和实际连接；每次检查明确输出、方法与范围。

教程驱动任务联用 `houdini-video-tutorial`：出现差异时先带着输入/目的/预期输出回看原片，
再核对自身实现，最后才查版本差异或替代；不能因一次失败宣布原生节点不可靠。

## 进入任务

程序化控制节点、场景总控或先UI后建模时按名联用houdini-parameter-ui。模型控制的含义/约束先明确；UI、绑定与SOP输出分层验证，普通赋值不要求建立总控。

HDA/OTL 的 UI、PythonModule、菜单/按钮回调、工具架和部署开发按名加载 houdini-tool-development；旧[HDA 维护入口](references/hda-maintenance.md)保留路由。涉及 SOP 几何输出时再联用本流程。普通参数赋值/改名仍直接执行并回读。

先读Host现场摘要：HIP、版本、frame、选择、候选网络与采集时间。缺失不代表空场景；需要时用scene_info/find_nodes/graph补查。用户选择会变化，快照不构成foreign修改授权。

简单、规格完整的编辑直接修改并回读。普通可调模型用几句说明目标、自选尺寸、控制和验证范围。质量敏感、外部真实性或复杂装配在大规模建图前读[质量合同](references/procedural-quality-contract.md)；外部参考会改变方案且research/web可用时实际检索，无来源就标假设。只询问会改变方案的选择，一次给有影响说明的互斥选项，不因“程序化”启动长问卷。

## 执行循环

1. **方法与原型**：选择曲线/截面/开放表面/实体/实例等表示。集中关键控制，建立named anchors/local frames和稳定piece身份。明确模块输入、输出、属性class与不变量；多模块装配读[模块合同](references/module-quality-contracts.md)。
2. **当前节点知识**：当前模块按不同type集中读node_info；消费operation_card.decisions及不受filter影响的operation_parameters，先决定表示/封口/选择范围/执行层级再build。同版本静态卡可复用，Shelf值和动态菜单仍以实际节点为准。普通参数默认24项；filter是字面子串，空匹配先去掉filter，不为找参数创建一批probe。visible=false用search_tab_entries；未知签名先verb_help。
3. **骨架门**：复杂装配先用低成本整体代理确定尺度、方向、接口和共享控制，再选择当前风险或质量最关键的模块。视觉交付已在范围内且GUI可用时，尽早看整体或明确侧向图；主要比例/接口未定不精雕独立零件。用户只要单个部件时不扩建整物。
4. **模块门**：把当前焦点模块当作独立的局部交付任务，不只是一个代码批次：明确相关原始要求、输入/局部坐标、输出、必须看清的细节和局部完成条件，按[聚焦与交接](references/module-quality-contracts.md#模块聚焦与交接)推进。一个模块可用多个小build_module，空CTRL/helper用tab_create；先验证单元及附属件连接再复制。检查实际表面/截面、封口、法线/属性与尺寸；闭合、共享边方向一致和朝外分别查，Normal不修顶点序。消费validation/cook_details，不为清warning丢掉部件身份；局部条件满足或遇到明确依赖阻塞就回到集成，不无限堆细节。
5. **集成关系门**：局部通过与集成通过分开记录。先核对必需部件实际进入最终输出（非空组/身份及基数），再测复制/变换后的实例接口；上游模块健康不能发现下游Switch漏件。独立表面用适用的interfaces，融合Polygon才用共享拓扑；顶点对最小距离不能证明无穿插，距离不等于插入深度。接地逐足检查；合法装配间隙按任务判断，没有可靠方法保留unverified。
6. **参数门**：代表性控制测响应和需保持的不变量，再恢复。先读test_controls的control_summary/status/reason，results=[]不等于通过；range覆盖基准与扰动，delta是变化。范围来自设计，耦合控制再测边界组合；判据错需独立理由并复跑，不能改窗口凑pass。bbox变化不证明连接、刚体变换或整个参数域。
7. **交付门**：普通geo只需明确最终SOP，sop_set_output(末端)设置display/render，再verify_network(parent,output=末端)，不创建也不要求Output节点。只有subnet/HDA的公共交付边界才用sop_set_output(末端,output_index=0)接原生Output，并verify_network(parent,output=末端,output_index=0)；多出口逐口声明，内部Null/旗标不替代公共端口。不要把“逐层发布”扩成每个普通geo都建Output；已有显式出口保持其消费者合同，不擅自删除。最后一次相关修改后刷新统计、关系及颜色/材质之后的交付图像。布局、恢复frame/selection及无关visibility，再保存；未命名HIP须有授权路径及当前HIP校验。内部调试仅切旗标，不重接公共端口。

整体代理→聚焦模块→局部验收→集成复验循环推进，不等所有细节完成才装配。模块是接口/验收边界，不强制每个模块一个subnet；用户要求独立子网时遵守，否则按耦合度选择同层分支或容器。默认同一作者顺序聚焦，不自动启动子agent；简单单参编辑不建模块表。此处骨架是代理形体，不是KineFX rig；几何父子/FK转rig skill。

## 执行与恢复

- build_module声明name/type/parms/inputs/output；None表示空输入槽。跨subnet使用Object Merge或明确端口。connect(src,dst,index)直接替换既有输入；Merge先断后接会前移丢分支，消费inputs_after。set_parms保持strict，不能以strict=False绕过构建失败。
- 组合构建声明required_outputs检查必需分支；preflight多项错误一次修正，保留components/菜单set_value。设置尚未决定时用dry_run集中读operation_advisories再构建；已明确时不强制双调用。advisories只提示缺少显式选择，不改默认值，也不证明选择正确。最终分支保留语义primitive组。
- tab_create返回hou.Node；list_parms/read_parms返回list。菜单用token/set_value，菜单表达式用{expression,language}；普通数值字符串是HScript表达式，VEX在snippet内；tuple表达式用组件字段。见[fast path](references/sop-patterns.md#9-小模块构建与检查-fast-path)。
- 更新已有spare默认值用create_spare_parms(update_defaults={name:literal})，当前值另用set_parms；两者回读分开。不支持的参数按verb_help边界报告，不因猜错HOM方法而断言环境不支持。
- 可独立cook/验收的构建批次分别提交exec；一个焦点模块可以跨多个已提交批次，引用存活输出后另做集成，不可分的修改仍保持同批原子性。看transaction最终状态：同一exec后方失败会撤销前方可撤销修改，不沿用被回滚依赖；陌生回读另开query，模块返回直接使用已知validation，避免尾部格式化错误撤销构建。
- 局部源码改动先read_parms(names=[代码字段])取得当前原文和hash，再用set_parms的literal patch；全部锚点/次数在本节点本批写入前验证，不能静默忽略0命中。跨节点不共享此预检，仍按模块/exec恢复；详见[fast path](references/sop-patterns.md#9-小模块构建与检查-fast-path)。
- 同一模块边界连续两次失败，回到最后有效输出做最小单变量诊断或换方法；不反复全文重建多个未知模块，不catch mutation/cook异常后继续。比较实际输入、参数回读、选择成员及输出，不用总数相同推导选择失效；换方法成功不能证明原生节点有bug。
- 节点替换前记录输入、输出消费者及参数引用；删除结果中的受影响连接必须回读并显式重接。
  同名新节点不继承旧接线/控制证据；对最终OUT做控制扰动，避免孤立形变节点和旁路控制。
- 填充、镜像、细分后检查表面面积、边界与重复覆盖。闭合Polygon已可为面，不能再填一层后仅按
  点数/cook通过；geo_piece_stats(inspect=True)的平面闭壳/重合边界诊断是风险线索，不自动认证实体有效。
- 已通过的独立模块及时保存，不把所有持久化推迟到最后；未知高成本循环先隔离验证，超时不等于原生方法有缺陷。
- 保留小状态摘要：当前输出/身份、未过关系、最新证据frame/时间、受影响修改；只重验受影响检查。

## 观察与关键方法

- geo_piece_stats默认按连接性或指定身份属性统计局部extent/面积；inspect=True观察命名primitive组的Polygon边界/边连通/非流形和basis下extent；shell_orientation保留有向体积条件。半径用到轴的欧氏距离，轴向投影不是半径。observed仅量测，分组切口可有意开放。
- geo_attrib_stats读驱动属性；复制前用unique=True检查模板P/id的精确tuple唯一性及预期基数，bbox不变不能排除重叠复制。geo_point_spacing只测有序点弦长。test_controls位移/变换误差要求稳定唯一id_attrib和相同面连接；选中件及其附属件查同一预期变换，未选中件查identity，见[模块合同](references/module-quality-contracts.md)。混合网格点均值不是设计中心，native/packed不靠P-only。
- Copy to Points承担实例变换，模板orient/scale与原型局部轴需一致；Copy/Merge明确属性class和传播。带状物用有面积截面，非刚性成形通常先作用中心线/低维结构再生成厚度。细节见[方法参考](references/sop-patterns.md)。
- 需要选择基础成形方法、局部倒角/分组或高细节细化时读[建模方法与细节预算](references/modeling-methods.md)。优先让原生SOP承担成形/复制，VEX承担锚点、属性和必要的自定义算法；不用纯VEX比例或节点数评分，但不能因调试失败悄悄放弃用户指定的方法/结构。用户要求多agent模块协作时读[并行设计、单作者执行](references/module-design-collaboration.md)，没有可用的受限设计子agent入口就保持单作者，不借allow_foreign或共享身份绕过ownership。
- 每图绑定问题和部件。render_view用focus_group/isolate选关注范围；full保证完整入镜，detail仅允许画框裁切，不允许近远裁面切断。framing_bounds在full中不是局部ROI。A/B同时复用framing.bounds和framing.depth_bounds（全部渲染内容）及方向/画幅/模式；深度或完整构图越界零渲染失败，不漂移相机。普通预览不必创建正式相机调用camera_fit。
- 消费render_view.check（pixels兼容别名）与framing.depth_check；看到断口先排除深度裁切，不能用拓扑pass或不同条件的图确诊着色问题。空白、近黑、错误目标不通过；detail有意裁框仍须读图确认所需局部可辨认。直接查看工具结果中的原生图像附件，先描述事实再核销疑点；遮挡不等于缺件，无地面参照不能断言接地。
- 用户屏幕异常才用viewport_screenshot；保留持久__dsh_houdini_*服务。纯网络交付或无GUI不强制追图，视觉未验证则明确报告。
- 动画至少两个相隔帧的实际几何/固定构图图像证据；A/B同framing_frame且覆盖帧包络。完全静止/方向错误是反例；细微审美无法裁定交给用户播放判断，不无限追图。

## 完成范围

最终显式输出非空、无error，warning已处理；单元与核心关系有对应实际输出证据；控制集中且代表性扰动/恢复通过。未测控制、unsupported、外部真实性、视觉不确定分别报告，不能用todo completed补证或把部分测量写成全部pass。关键控制不能靠重复改多个VEX常量维护。

收尾由当前作者完成输出、关系和控制检查，复用已有工具事实与原生图像；核心未验证项如实保留。
