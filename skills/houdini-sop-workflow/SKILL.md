---
name: houdini-sop-workflow
description: 设计、构建、调试和交付 Houdini SOP 程序化网络，包括 SOP HDA 的内部几何输出。用于建模、散布、Copy to Points、属性传递、VEX成形、Sweep/PolyWire、Merge和SOP动画；尤其涉及多模块空间关系、可调控制、局部几何/拓扑、cook warning或视觉取证时。不用于纯场景查询、工具UI/回调/打包开发，也不代替rig或Solaris领域流程。
---

# Houdini SOP Workflow

Agent负责理解参考、选择构造和读图诊断；把共享尺寸、接合轮廓、运动关系和重复几何交给Houdini数据流维护。先做一个能证实最危险构造的局部原型，再扩展成整件；每次检查明确输出、方法与范围。

教程驱动任务联用 `houdini-video-tutorial`：出现差异时先带着输入/目的/预期输出回看原片，
再核对自身实现，最后才查版本差异或替代；不能因一次失败宣布原生节点不可靠。

## 进入任务

程序化控制节点、场景总控或先UI后建模时按名联用houdini-parameter-ui。模型控制的含义/约束先明确；UI、绑定与SOP输出分层验证，普通赋值不要求建立总控。可调、网络清楚、独立保存默认交付普通网络与HIP；只有用户明确需要HDA/OTL、共享节点类型或安装分发时才进入资产封装，不因“可复用/独立保存”自行升级交付形式。

HDA/OTL 的 UI、PythonModule、菜单/按钮回调、工具架和部署开发按名加载 houdini-tool-development，并按需读取其HDA维护reference。涉及 SOP 几何输出时再联用本流程。普通参数赋值/改名仍直接执行并回读。

先读Host现场摘要：HIP、版本、frame、选择、候选网络与采集时间。缺失不代表空场景；需要时用scene_info/find_nodes/graph补查。任务给出毫米、厘米或米尺寸时，先读scene_info().unit_length_meters并换算建模数值；口头声明“1单位=1厘米”不会改变HIP的单位设置。用户选择会变化，快照不构成foreign修改授权。

简单、规格完整的编辑直接修改并回读。复杂产品复用已有prose/todo，简记四项：外形与必需细节、谁连接/跟随谁、用户真正要改的独立量、最不确定的构造及其验证办法；Agent从图片和短要求提取，不要求用户先写零件清单。标明尺寸/图片冲突与假设，只询问会改变方案的选择。质量敏感、外部真实性或复杂装配读[质量合同](references/procedural-quality-contract.md)；外部参考会改变方案且research/web可用时实际检索，无来源不声称真实规格。

厂家照片与尺寸图决定复杂多件产品的构造时，首次改场景前在工作区写一份不超过八项的简短核验表：每项记录原图位置、所属部件、外形/孔距/厚度/数量/运动关系等事实类型、已核对/估计/冲突及将检查的输出、部件和状态。由当前作者提取，不要求用户填写。尺寸线端点要落实到实际部件，不能因数字相近就转给外轮廓；重复件先核数量再复制。同图不同裁切不算独立佐证，模型自述“再次确认”也不增加证据。若关键事实仍无法从材料核对，保持未验证并只针对会改变构造的歧义询问。详见[质量合同](references/procedural-quality-contract.md#最小合同)。

单个SOP资产先建Geo，再在该Geo内建`CTRL`并集中尺寸/姿态参数；
同层节点用相对参数引用。只有用户明确要跨多个OBJ统一控制时，
才在`/obj`放场景总控。不要为了“先做参数UI”把单件模型的控制器
留在Geo外。

电缆、管线等长曲线默认先做可检查的开放中心线（VEX可生成点和polyline），
在转弯与自由端保持切向平顺，再让原生Sweep用input 0路径、内建圆截面和
明确端盖生成实体；直接在VEX里逐环手写闭管时须有具体理由，并验证
相邻截面方向、末端、整壳朝向及动态状态。

## 执行循环

1. **构造选择**：先读[建模方法](references/modeling-methods.md#1-从表示和构造选方法)，选择能观察中间结果的表示：原生源，或VEX点/线/截面接原生SOP成形；重复资产保留独立源并用Copy，VEX按功能与输入输出拆分。共享尺寸、轴/frame和piece身份只有一个来源；新建且需贴合的壳、边框、盖面从同一接合轮廓派生，独立外部资产则适配明确接口，不能只分别调到看似接近。少量主控驱动这些来源，派生量留在网络。新建资产从首个源使用世界Y-up（X宽、Y高、Z深）；旧工程/必要局部坐标的适配在稳定输出之前完成。多模块读[模块合同](references/module-quality-contracts.md)，默认同层逻辑模块，不因模块化自动建Subnet/HDA。
2. **有效设置**：按当前模块不同type集中读node_info的operation_card、operation_parameters和构建返回的operation_advisories，先选表示/模式、封口和选择范围；缺少显式选择与模式/输入语义风险两类提示都要处理。分段/精度等模式相关参数要核对当前模式；写入后观察实际轮廓、截面或拓扑响应，值能回读不代表生效。操作卡同版本可复用，动态菜单以现场为准；filter空匹配先去掉filter，visible=false用search_tab_entries，未知签名先verb_help，不批量建probe猜参数。
3. **原型门**：复杂装配只用低成本整体代理定尺度、方向和接口，随后先做失败会迫使换构造或改接口的最高风险局部。首个可辨原型用render_view查看原生图像：整体回答比例，局部回答预先声明的风险。GUI可用且用户未禁止时，不等全件完成才首看；单部件请求不扩成整件。比例未定不精雕，危险局部未通过不复制铺开；正确原型及时保存。
4. **局部闭环**：按[聚焦与交接](references/module-quality-contracts.md#模块聚焦与交接)明确输入、输出、必需细节和局部完成条件，小批build_module并消费validation/cook_details。Boolean先查源的Solid/Surface前提、接缝和朝向，再查实际切除/融合效果；不能把菜单正确、最终Null无warning或Normal着色当成形正确。实体通孔先在最终Polygon部件上用geo_check_interfaces的axis_passage查声明孔轴；有图纸孔径时，再用bore_clearance按被穿透板厚区间查声明半径的空域，并看闭合壳、孔壁与沿轴视图。带铰耳/凸台的整件包围盒不是板厚；后续增材后重新查最终输出。有意开放表面改用边界合同。每张关键近景先写实际形态是否符合预期及不确定项；若有缺陷，修一个原因再刷新受影响证据。看不清就换观察范围，不据整体可辨认核销局部。局部通过即集成；依赖阻塞回到装配协调，同一边界两次失败按恢复规则换方法。
5. **集成关系门**：局部通过与集成通过分开记录。按需求和当前控制状态先导出期望成员/基数，再独立核对最终输出；不能从“实际幸存了什么”反推期望集合。最终Polygon组的独立重复件可用geo_check_interfaces的component_count核对声明基数，再检查各处位置/接口；上游模块健康不能发现下游Switch漏件。计数、组、拓扑或输出身份变化时重新评估需测接口，旧状态合同不覆盖新增件。独立表面用适用的interfaces，融合Polygon才用共享拓扑；顶点对最小距离不能证明无穿插，距离不等于插入深度。普通产品模型先查可见组件、接点及开合/滑动状态没有明显悬空、穿插、错位或脱节；支撑处至少有可信的接触面或连接件。用户明确要求真实传动或承载时，再逐段核对驱动件→连接件→从动件的实体接合；孔道、共轴或同步运动不证明传力，缺少可测接合时报告示意或未验证。接地按已声明的世界up轴逐足检查；默认Houdini地面为XZ且`Y=0`，不能因为局部模型以Z为高度就把`min Z=0`写成世界接地。合法装配间隙按任务判断，没有可靠方法保留unverified。
6. **参数门**：每个交付控制测实际响应和需保持的不变量，再恢复；关联控制另选代表性组合。有保持、释放或复位含义时，列出操作后的控制值并检查释放驱动输入后的状态，不能用一直按住时或预设快照代替保持关系。先读test_controls的control_summary/status/reason，results=[]不等于通过；range覆盖基准与扰动，delta是变化。顶层interfaces只放所有状态都应成立的不变量；合盖基准接触用baseline_interfaces，开盖分离等扰动专属关系放在对应case的interfaces，不因接触在开盖时正确断开就删去所有关系。若现有方法仍无法表达某项关系，拆成有明确范围且可恢复的检查并保留限制，不能用固定子集声称全覆盖。范围来自设计，耦合控制再测边界组合；判据错需独立理由并复跑，不能改窗口凑pass。bbox变化不证明连接、刚体变换或整个参数域。
7. **交付门**：简单普通geo可直接以明确末端SOP交付；用户要继续编辑的非平凡程序化资产应在根层建立稳定`OUT_ASSET` Null，由它消费最终组装结果、语义观察色和必要的local→world坐标适配，设置display/render，并用verify_network显式验证。它是稳定消费者接口，不是原生公共端口；不要在每条短链后机械加Null。同层逻辑模块按需建立`OUT_<MODULE>` Null，父装配只消费它。只有subnet/HDA的公共交付边界才用sop_set_output(内部`OUT_<MODULE>`,output_index=0)接原生Output，并verify_network(parent,output=内部输出,output_index=0)；多出口逐口声明，内部Null/旗标不替代公共端口。已有显式出口保持其消费者合同，不擅自删除。用户要求或复杂装配需要观察区分时，按稳定`part`/piece身份赋予克制且可辨认的组件`Cd`；同组件保持一致、相邻组件避免近似色，不用随机色或材质网络代替身份组，且不得覆盖用户已有材质/颜色合同。新建或实质扩展的非平凡网络在功能验证后按[网络交接布局](references/network-handoff.md)建立语义Network Box并执行comfortable handoff，其中稳定最终输出应进入output分组；组件与技术阶段都需可见时，先建立并布局source/template-copy/output叶子角色框，再用一层组件大框包含这些小框；这是Network Box展示层级，不是Subnet。单节点/短直链、维护/探针、foreign网络、用户明确不要布局或不受支持项可跳过并说明。最后一次相关修改后刷新统计、关系及颜色/材质之后的交付图像；最终世界姿态必须用声明轴向和带地面/轴参照的证据检查，无地面参照的自动取景图不能证明接地。恢复frame/selection及无关visibility，再保存；未命名HIP须有授权路径及当前HIP校验。内部调试仅切旗标，不重接公共端口。

整体代理→危险局部→集成→下一局部循环推进。容器、跨模块连接件归属及相对引用按[模块合同](references/module-quality-contracts.md)；不把容器层次当质量。默认同一作者顺序聚焦，不自动启动子agent；简单单参编辑不建模块表。此处骨架是代理形体，不是KineFX rig；几何父子/FK转rig skill。

## 执行与恢复

- 自写旋转矩阵先用非零角验证pivot不动及离轴点方向，再复制/接入整机；活动件控制须在最终输出复查与固定承接件的接点，整件bbox响应不证明连接。组、状态及失败边界见[模块合同](references/module-quality-contracts.md#控制契约改变什么什么必须不变)。
- build_module声明name/type/parms/inputs/output；None表示空输入槽。跨subnet使用Object Merge或明确端口。connect(src,dst,index)直接替换既有输入；Merge先断后接会前移丢分支，消费inputs_after。set_parms保持strict，不能以strict=False绕过构建失败。
- 组合构建声明required_outputs检查必需分支；preflight多项错误一次修正，保留components/菜单set_value。设置尚未决定时用dry_run集中读operation_advisories再构建；已明确时不强制双调用。advisories提示缺少显式选择或模式/输入语义风险，不改默认值，也不证明选择正确；已显式设参不消除语义风险。最终分支保留语义primitive组。
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

用户给出物理尺寸时，先核对图纸端点所属零件与尺寸性质，再将少量决定构造的外形尺寸
用最终零件primitive组的`geo_check_interfaces(method='physical_extent')`声明毫米值、轴和误差；
最后一次几何修改后复验，失败不能由健康cook或整件包围盒覆盖。该检查不证实图纸归属或组完整。
整体包络另读最终`verify_network.geometry.bbox_size`与`bbox_size_sop_local_mm`，
计入OBJ变换；bbox_min/max是端点，不能单独当跨度。

声称“轴穿过铰耳”等真实通孔时，在复制/装配前先检查单个闭合零件的孔道；
最终同一SOP中的完整闭合实体组可用`geo_check_interfaces(method='solid_overlap')`
查轴与铰耳是否占据同一空间，再分别查同轴与孔壁间隙。活动状态在
`test_controls`各case中复查；组开放或只截了部分壳体时保留unverified，
不能把零交集单独说成已穿孔。

最终显式输出非空、无error，warning已处理；单元与核心关系有对应实际输出证据；控制集中且代表性扰动/恢复通过。完成核验表时把每项的实际检查路径与交付SOP逐字比对，临时输出或最后相关修改前的结果只能记未验证；记录对应状态、结果引用或固定图像，未执行项也保留。带锁扣、铰链、密封或其他接口的产品，最后一轮控制测试逐项声明任务要求的可见连接、对齐与状态转换，对可测者检查适用的`interfaces`；不能拿bbox或零件一起移动代替。用户明确要求真实密封、受力或传动时另验相应物理/功能关系；普通设计模型不因这些未请求的性能未验证而判失败，有意的柔性几何预压可作为结构示意，但不得把相交体积写成已测密封压力。缺少当前状态必需成员/关系覆盖时以partial/incomplete开头；报告参数和场景事实，不在没有证据时臆测是用户或GUI改动。未测控制、unsupported、外部真实性、视觉不确定分别报告，不能用todo completed补证或把部分测量写成全部pass。关键控制不能靠重复改多个VEX常量维护。

近看交付的Polygon产品件，关键源模块成形后用`geo_piece_stats(...,inspect=True,integrity_only=True)`局部检查；最后一次几何修改后的`verify_network(output='OUT_ASSET')`已自动给出整件`surface_integrity`，成功观察时不重复调用同一整件快检。若它提示风险或unverified，再按部件组定位、复查源模块与最终输出。非流形、零面积、零长度、重复面和反向闭壳不因cook无warning或出图而消失；开放边须按接口解释，不能一概判破面。整件几何检查也不证明接点、造型或视觉正确。最后一次修改使旧的关系/控制/图像证据失效；最后一轮`test_controls`仍失败时，不得报告全部控制通过，除非同一最终输出的对应case已重测通过。

给用户交付时先说模型在哪里打开、能改什么、实际检查了什么、哪些地方仍是示意或没查；把`healthy/warning-free`说成“模型能正常算出，未发现报错”，把`restored`说成“试改参数后能回到原样”。精确节点名、数值和错误留在简短的技术补充中，不能为了好懂而省掉影响结果的失败。

收尾由当前作者完成输出、关系和控制检查，复用已有工具事实与原生图像；核心未验证项如实保留。
