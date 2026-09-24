---
name: houdini-sop-workflow
description: 设计、构建、调试和交付 Houdini SOP 程序化网络，包括 SOP HDA 的内部几何输出。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询、工具UI/回调/打包开发，也不代替rig或Solaris领域流程。
---

# Houdini SOP Workflow

以一个正确、可观察的原型推进。新增细节前先确认主要形体和实际连接；每次检查明确输出、方法与范围。

教程驱动任务联用 `houdini-video-tutorial`：出现差异时先带着输入/目的/预期输出回看原片，
再核对自身实现，最后才查版本差异或替代；不能因一次失败宣布原生节点不可靠。

## 进入任务

程序化控制节点、场景总控或先UI后建模时按名联用houdini-parameter-ui。模型控制的含义/约束先明确；UI、绑定与SOP输出分层验证，普通赋值不要求建立总控。可调、网络清楚、独立保存默认交付普通网络与HIP；只有用户明确需要HDA/OTL、共享节点类型或安装分发时才进入资产封装，不因“可复用/独立保存”自行升级交付形式。

HDA/OTL 的 UI、PythonModule、菜单/按钮回调、工具架和部署开发按名加载 houdini-tool-development，并按需读取其HDA维护reference。涉及 SOP 几何输出时再联用本流程。普通参数赋值/改名仍直接执行并回读。

先读Host现场摘要：HIP、版本、frame、选择、候选网络与采集时间。缺失不代表空场景；需要时用scene_info/find_nodes/graph补查。用户选择会变化，快照不构成foreign修改授权。

简单、规格完整的编辑直接修改并回读。普通可调模型用几句说明目标、自选尺寸、控制和验证范围。质量敏感、外部真实性或复杂装配在大规模建图前读[质量合同](references/procedural-quality-contract.md)；外部参考会改变方案且research/web可用时实际检索，无来源就标假设。只询问会改变方案的选择，一次给有影响说明的互斥选项，不因“程序化”启动长问卷。

## 执行循环

1. **方法与原型**：以人工易接手和构建/cook/修改/验证的整体效率选择曲线/截面/开放表面/实体/实例等表示，按需混合原生SOP与VEX。涉及重复资产、VEX职责划分或构造选型时，先读[建模方法](references/modeling-methods.md#1-从表示和构造选方法)。重复资产必须走Copy，保留独立可替换源；VEX按功能与输入输出拆分，不能把整个多功能模块塞进一个Wrangle。集中关键控制，建立named anchors/local frames和稳定piece身份。正式新建的普通Houdini资产从首个骨架/源开始就采用世界Y-up（X宽、Y高、Z深），控制名、表达式、模板点、局部验证和最终输出保持同一轴向；不要先默认Z-up建完再在根部补旋转。只有旧工程修复或确有独立局部坐标理由的模块才允许声明local Z-up，并在稳定根输出之前用一个显式适配器转换，不能让用户靠`OUT_ASSET`之后的旁路Transform纠正。模块化默认先表达为同层的逻辑模块：源、局部处理、放置/复制、检查点输出保持相邻，父装配只消费稳定输出；容器是可选实现，不因“模块”自动创建subnet/HDA。明确模块输入、输出、属性class与不变量；多模块装配读[模块合同](references/module-quality-contracts.md)。
2. **当前节点知识**：当前模块按不同type集中读node_info；消费operation_card.decisions及不受filter影响的operation_parameters，先决定表示/封口/选择范围/执行层级再build。同版本静态卡可复用，Shelf值和动态菜单仍以实际节点为准。普通参数默认24项；filter是字面子串，空匹配先去掉filter，不为找参数创建一批probe。visible=false用search_tab_entries；未知签名先verb_help。
3. **骨架门**：复杂装配先用低成本整体代理确定尺度、方向、接口和共享控制，再选择当前风险或质量最关键的模块。GUI可用且用户未禁止时，骨架/首个可辨原型一形成就用render_view看整体或明确侧向图并实际查看原生图像附件，不能等全部建完才第一次预览；仅交付网络/HIP不豁免。主要比例/接口未定不精雕独立零件。用户只要单个部件时不扩建整物。
4. **模块门**：把当前焦点模块当作独立的局部交付任务，不只是一个代码批次：明确相关原始要求、输入/局部坐标、输出、必须看清的细节和局部完成条件，按[聚焦与交接](references/module-quality-contracts.md#模块聚焦与交接)推进。一个模块可用多个小build_module，空CTRL/helper用tab_create；先验证单元及附属件连接再复制。同层模块用稳定`OUT_<MODULE>`检查点供父装配消费，不让父级接到内部Merge/Group等实现节点；简单短链可省略该检查点。私有细节归模块，跨两个模块的螺栓、销钉、焊缝等连接件归最低共同装配层，不能让任一叶模块隐藏读取兄弟路径。检查实际表面/截面、封口、法线/属性与尺寸；闭合、共享边方向一致和朝外分别查，Normal不修顶点序。实体贯穿孔须证明实体壳合同、沿声明孔轴的中心线无遮挡，并用沿轴视图确认开口；有意交付开放板面时改验开放表面/边界合同，不能套用闭合实体门。消费validation/cook_details，不为清warning丢掉部件身份；局部条件满足或遇到明确依赖阻塞就回到集成，不无限堆细节。
5. **集成关系门**：局部通过与集成通过分开记录。按需求和当前控制状态先导出期望成员/基数，再独立核对最终输出；不能从“实际幸存了什么”反推期望集合。之后测复制/变换后的实例接口；上游模块健康不能发现下游Switch漏件。计数、组、拓扑或输出身份变化时重新评估需测接口，旧状态合同不覆盖新增件。独立表面用适用的interfaces，融合Polygon才用共享拓扑；顶点对最小距离不能证明无穿插，距离不等于插入深度，容差内近邻/无穿插不证明实际承托；支撑任务须说明并验证接触面或连接件。接地按已声明的世界up轴逐足检查；默认Houdini地面为XZ且`Y=0`，不能因为局部模型以Z为高度就把`min Z=0`写成世界接地。合法装配间隙按任务判断，没有可靠方法保留unverified。
6. **参数门**：代表性控制测响应和需保持的不变量，再恢复。先读test_controls的control_summary/status/reason，results=[]不等于通过；range覆盖基准与扰动，delta是变化。静态interfaces只有在其选择和基数覆盖基准及每个扰动状态时才能复用；当前API无法表达变化成员全集时，拆成有明确范围且可恢复的受支持检查并保留限制，不能用固定子集声称全覆盖。范围来自设计，耦合控制再测边界组合；判据错需独立理由并复跑，不能改窗口凑pass。bbox变化不证明连接、刚体变换或整个参数域。
7. **交付门**：简单普通geo可直接以明确末端SOP交付；用户要继续编辑的非平凡程序化资产应在根层建立稳定`OUT_ASSET` Null，由它消费最终组装结果、语义观察色和必要的local→world坐标适配，设置display/render，并用verify_network显式验证。它是稳定消费者接口，不是原生公共端口；不要在每条短链后机械加Null。同层逻辑模块按需建立`OUT_<MODULE>` Null，父装配只消费它。只有subnet/HDA的公共交付边界才用sop_set_output(内部`OUT_<MODULE>`,output_index=0)接原生Output，并verify_network(parent,output=内部输出,output_index=0)；多出口逐口声明，内部Null/旗标不替代公共端口。已有显式出口保持其消费者合同，不擅自删除。用户要求或复杂装配需要观察区分时，按稳定`part`/piece身份赋予克制且可辨认的组件`Cd`；同组件保持一致、相邻组件避免近似色，不用随机色或材质网络代替身份组，且不得覆盖用户已有材质/颜色合同。新建或实质扩展的非平凡网络在功能验证后按[网络交接布局](references/network-handoff.md)建立语义Network Box并执行comfortable handoff，其中稳定最终输出应进入output分组；组件与技术阶段都需可见时，先建立并布局source/template-copy/output叶子角色框，再用一层组件大框包含这些小框；这是Network Box展示层级，不是Subnet。单节点/短直链、维护/探针、foreign网络、用户明确不要布局或不受支持项可跳过并说明。最后一次相关修改后刷新统计、关系及颜色/材质之后的交付图像；最终世界姿态必须用声明轴向和带地面/轴参照的证据检查，无地面参照的自动取景图不能证明接地。恢复frame/selection及无关visibility，再保存；未命名HIP须有授权路径及当前HIP校验。内部调试仅切旗标，不重接公共端口。

整体代理→聚焦模块→局部验收→集成复验循环推进，不等所有细节完成才装配。模块是接口/验收边界，不强制每个模块一个subnet；普通单作者任务默认使用同层逻辑模块，Subnet只在用户明确要求层级、模块已有稳定少量公共端口、根网络明显失控、需要独立复用/导出/替换或组件作者时采用。连续曲面、跨模块Boolean、强耦合求解、短链和接口仍频繁变化时保持同层，不为显得专业而嵌套。Subnet内部必须使用相对引用或公共输入/参数，禁止保留工作区/OBJ绝对控制路径；普通同层模块也优先相对兄弟引用，为未来移动/导出留边界。默认同一作者顺序聚焦，不自动启动子agent；简单单参编辑不建模块表。此处骨架是代理形体，不是KineFX rig；几何父子/FK转rig skill。

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
- 平铺模块提升为Subnet不原地折叠或删除已验证网络：先记录输入、输出消费者、控制与接口，建立并验证候选公共输出，再切消费者；用户手改或证据不完整时保留旧分支。模块容器变化不自动授权HDA升级或component导出。

## 观察与关键方法

- geo_piece_stats默认按连接性或指定身份属性统计局部extent/面积；inspect=True观察命名primitive组的Polygon边界/边连通/非流形和basis下extent；shell_orientation保留有向体积条件。半径用到轴的欧氏距离，轴向投影不是半径。observed仅量测，分组切口可有意开放。
- geo_attrib_stats读驱动属性；复制前用unique=True检查模板P/id的精确tuple唯一性及预期基数，bbox不变不能排除重叠复制。geo_point_spacing只测有序点弦长。test_controls位移/变换误差要求稳定唯一id_attrib和相同面连接；选中件及其附属件查同一预期变换，未选中件查identity，见[模块合同](references/module-quality-contracts.md)。混合网格点均值不是设计中心，native/packed不靠P-only。
- Copy to Points承担实例变换，模板orient/scale与原型局部轴需一致；Copy/Merge明确属性class和传播。带状物用有面积截面，非刚性成形通常先作用中心线/低维结构再生成厚度。细节见[方法参考](references/sop-patterns.md)。
- 需要选择基础成形方法、局部倒角/分组或高细节细化时读[建模方法与细节预算](references/modeling-methods.md)。不要用纯VEX比例或节点数评分，也不能因调试失败悄悄放弃用户指定的方法/结构。用户要求多agent模块协作时读[模块协作](references/module-design-collaboration.md)：显式可用的component_delegate走独立工程候选，否则仅并行设计或单作者；不借allow_foreign或共享身份绕过ownership。
- 跨OBJ汇总实际装配时显式处理Object Merge坐标空间；要保留场景放置就使用`Into This Object`等价模式，local-space合并只在有意忽略OBJ变换时成立。用于关系或渲染的代理必须让合并bbox与源world bbox一致并处理warning，否则proxy不是交付物证据。
- 每图绑定问题和部件。render_view用focus_group/isolate选关注范围；full保证完整入镜，detail仅允许画框裁切，不允许近远裁面切断。framing_bounds在full中不是局部ROI。A/B同时复用framing.bounds和framing.depth_bounds（全部渲染内容）及方向/画幅/模式；深度或完整构图越界零渲染失败，不漂移相机。普通预览不必创建正式相机调用camera_fit。
- 消费render_view.check（pixels兼容别名）与framing.depth_check；看到断口先排除深度裁切，不能用拓扑pass或不同条件的图确诊着色问题。空白、近黑、错误目标不通过；detail有意裁框仍须读图确认所需局部可辨认。直接查看工具结果中的原生图像附件，先描述事实再核销疑点；遮挡不等于缺件，无地面参照不能断言接地。
- viewport_screenshot用于用户视口或参数界面的实际显示验收；模型本体优先render_view(明确最终SOP)，复用版本原生低成本后端与持久__dsh_houdini_*服务。两者默认managed，把验证图放进`$HIP/dsh-visual-checks/<run-id>/`；只有用户明确要交付路径或隔离测试自管目的地时才传`output_policy='explicit'`，不得为方便把agent预览散放HIP根目录。原型和最后一次相关修改后各检查必要视角，关键接口看局部，不对每次无关调用重复追图。纯查询/改名/无可见变化的维护不强制预览；无GUI、预览/识图失败或用户明确禁止时报告具体限制与视觉未验证，不默认改走Karma。未请求成品图片不是省略建模视觉验证的理由。
- 动画至少两个相隔帧的实际几何/固定构图图像证据；A/B同framing_frame且覆盖帧包络。完全静止/方向错误是反例；细微审美无法裁定交给用户播放判断，不无限追图。

## 完成范围

最终显式输出非空、无error，warning已处理；单元与核心关系有对应实际输出证据；控制集中且代表性扰动/恢复通过。带锁扣、铰链、密封或其他机械接口的产品，最后一轮控制测试需逐项声明关键接口，对可测者实际检查适用的`interfaces`；若现有距离/轴向方法不能表达某项关系，就把它明确列为未验证，不能拿bbox或零件一起移动代替。缺少当前状态必需成员/关系覆盖时以partial/incomplete开头；报告参数和场景事实，不在没有证据时臆测是用户或GUI改动。未测控制、unsupported、外部真实性、视觉不确定分别报告，不能用todo completed补证或把部分测量写成全部pass。关键控制不能靠重复改多个VEX常量维护。

近看交付的Polygon产品件，在关键源模块成形后及最后一次几何修改后的最终输出上运行`geo_piece_stats(...,inspect=True,integrity_only=True)`；最终输出这一次不传`group`，再按部件组定位风险。非流形边、零面积面、零长度边或完全重复面不因cook无warning、整体bbox正确或反复出图而消失；不同部件间的重合面只有整件检查才可能发现，局部组通过不能写成整件零风险。先定位到出问题的源模块再修，无法修复则按实际影响报告部分完成。开放的连接端可有意留下边界边，须按声明的接口解释，不把所有开放边一概判错。超预算/非Polygon保持unverified；几何完整性通过也不证明接点、造型或视觉正确。最后一次影响几何的修改会使旧的表面、接口和控制结果失效；最后一轮`test_controls`仍失败时，不得报告全部控制通过，除非同一最终输出的对应case已重测通过。

给用户交付时先说模型在哪里打开、能改什么、实际检查了什么、哪些地方仍是示意或没查；把`healthy/warning-free`说成“模型能正常算出，未发现报错”，把`restored`说成“试改参数后能回到原样”。精确节点名、数值和错误留在简短的技术补充中，不能为了好懂而省掉影响结果的失败。

收尾由当前作者完成输出、关系和控制检查，复用已有工具事实与原生图像；核心未验证项如实保留。
