# 控制参数、界面与绑定设计

本页维护跨SOP/HDA/场景总控的稳定职责与接口边界。领域方法由houdini-parameter-ui维护；
资产封装/脚本/分发由houdini-tool-development维护。控制面板是参数接口，Python Panel与WebView属于其他载体。

## 职责与数据关系

| 层 | 唯一职责 | 不承担 |
|---|---|---|
| 控制定义 | 用户操作、稳定内部名、含义、单位、合法域、默认和约束 | 自动猜节点路径或控件布局 |
| UI布局 | 标签、顺序、分组、条件、组件组合 | 写业务回调或偷偷连线 |
| 应用载体 | 单节点spare或共享HDA定义的写入/恢复合同 | 把实例修改升级为定义修改 |
| 绑定 | 指定控制→指定目标的持续引用与转换 | 推断未授权目标、把按钮副作用当数据依赖 |
| 领域实现与验证 | SOP/rig/Solaris求值、最终产物与关系 | 用UI存在代替结果正确 |

“总控”是一种用途，可以放在Null、其他可编辑节点或HDA上；不新增专用总控节点类型。
单件SOP产品默认把控制放在其Geo内部，随网络一起交付；跨多个OBJ的场景总控才放在`/obj`层。
稳定内部名承担接口身份，显示标签与文件夹只影响呈现。改UI不改绑定，更换内部实现时显式迁移绑定。
控制定义记录在任务需求/计划与最终参数schema中，不建立第二份自动判完成账本。

用户控制入口通过`network_controls`在真实节点的`dsh_houdini_control` userData明确声明可读标签，随HIP保存；它是导航注解，不复制参数定义、不证明联动、不承担ownership。交付时用`present_nodes`声明控制卡片，直接从对话进入当前工程的节点和参数页，不另加原生查找菜单；不从CTRL名字、颜色或spare数量猜入口。共享控制区的排布与组件工序阅读方法见[网络交接](../skills/houdini-sop-workflow/references/network-handoff.md)。

卡片通过DSH公开Conversation投影与回复尾部插槽消费原始成功工具回执；点击只提交任务与原事件坐标，Host重读原回执，经该任务的执行端进入Bridge主线程队列。持久入口ID随节点保存，改名或同HIP重开仍可定位；历史路径不作回退。原生复制会复制入口ID，多个同ID节点存在时拒绝含糊跳转，可对复制品明确重新声明ID。若原件删除后只剩保留同ID的复制品，入口随该标识保留；ID不是节点血缘或修改ownership。

节点卡片默认只显示用途标题、一行作者明确提供的`description`与主操作，宽度上限480px；右侧独立省略号展开完整名称、说明、中文角色、真实HOM上下文、类型、路径和工程。成功反馈短暂显示在操作位置，错误完整换行展示。文件卡片继续由DSH维护，与节点卡片共用紧凑石墨色和细边缘外观；插件只在Houdini任务的语义交付表面统一外观，使用精确兼容组合中的`data-presented-file`/`data-presented-description`，不读取编译类名、不复制文件状态或覆盖错误反馈。

导航具有独立的排队取消合同：切换任务或取消点击时，尚未执行的导航票据/队列项被取消，队列恢复后不会再改变面板；已开始的主线程导航不强杀。此合同不扩展普通同步HOM修改的取消或回滚保证。实现为[节点交付Host](../src/node-delivery.ts)、[节点卡片](../client/node-delivery.js)与[导航](../houdini/python3.11libs/dsh_network_navigation.py)；原生/嵌套结果及任务路由见[Host回归](../tools/tests/node-delivery.test.mjs)、[客户端回归](../tools/tests/node-delivery-client.test.mjs)，持久入口见[HOM回归](../tools/tests/dsh-node-delivery.test.py)。

公共控制按用户操作选择，不以数量衡量程序化能力。自由输入确定用户可独立改变的量，派生尺寸/锚点供各模块共享，内部常量留在可编辑网络；需要展示派生结果时不再添加相互冲突的可写输入。
主体与附属件必须从同一当前状态求值。尺寸、姿态或接合变化时，仅隐藏失效控件不会修复模型；用户必需操作未覆盖时交付结论保留缺口。已有接口、动画和外部消费者按迁移合同处理，不因新界面更精简而删除。
领域选参与代表性验证方法只在houdini-parameter-ui的控制与绑定reference维护；候选指导不改变现有工具签名，也不宣称参数空间已完整验证。

多Agent的公共/派生/局部参数归属、接口修订与用户手改保护见[组件协作设计](component-collaboration.md)。
该路线以普通subnet/spare和原生数据依赖交付，不要求HDA；设计计划不扩大当前绑定工具或ownership范围。

## 支持的推进顺序

- 从零且控制目标明确：意图/约束→核心控制与最小UI→网络和绑定→实际输出验证→完善布局。
- 技术路线不明确：最小可行模型→找出稳定控制→UI/绑定→集成验证。
- 已有场景总控：明确用户想集中完成的操作→有界扫描相关节点/参数及现有表达式/动画→选择或抽象控制→UI/绑定→回归。
- 仅调整界面：读取原参数身份/绑定→修改呈现→确认绑定与旧状态未变。

不规定固定先后顺序；界面、绑定和模型按依赖小步迭代。总高度/单级高度/数量等约束需指定自由输入与派生量，不能让互相冲突的控制同时独立生效。
持续控制优先使用参数引用；导出、缓存或重建是显式动作，沿用工具开发的回调与副作用合同。

## 实施计划与完成门

| 阶段 | 工作范围 | 完成依据 |
|---|---|---|
| 共享知识与路由 | 参数界面skill承接UI参考/画廊，工具开发维护HDA/脚本/交付 | 注册/资源/索引一致，普通赋值不误路由为设计任务 |
| 单节点应用 | 共用layout展开，spare追加与预览，拒绝同名覆盖，保留旧值/表达式/keys/locks | Null/已有控制节点、失败恢复与双版本测试 |
| 独立绑定 | 明确源/目标、直接与线性数值引用，预览计划/hash、驱动覆盖显式化、失败恢复 | 普通正例、旧驱动/锁定/循环/过期拒绝、实际目标响应 |
| 两种顺序验收 | 从零控制驱动模型；既有网络扫描后接总控 | 参数、绑定表达式及最终SOP输出分别验证；GUI与自然任务独立报告 |

这是能力实施顺序，当前未完成动作仅在docs/handoff.md滚动维护。不能由文档存在认定代码/部署/自然任务已通过。

## 当前实施边界

parameter_ui是不依赖HDA的统一只读界面入口；create_spare_parms与hda_set_interface共用组件展开。
`mode`组件把稳定menu token映射为按需显示的原生参数区，`string_type='node'`使用NodeReference选择；组件只组织界面，不生成业务绑定或回调。高级交互的用途与原生参考见[艺术家界面](../skills/houdini-parameter-ui/references/artist-ui-patterns.md)。
spare的layout默认追加，与HDA整组重建分开。已有spare默认值更新用update_defaults；HDA增量编辑用edits。
bind_controls首版只接受明确数值源与目标以及线性scale/offset，不接管任意已有表达式网络。
未指定的场景参数不自动变为总控目标；单次allow_foreign只用于用户明确的目标，服务节点不豁免。
布局、参数读取和绑定回读各自不能证明业务产物正确；领域输出验证继续使用现有cook/verify_network/test_controls合同。
公共控制先检查默认关系，再逐项观察相关实体响应，最后对相互制约的控制选择代表性组合边界，并包含附属件、应保持的量与真实接口；恢复参数及输出后再验最终外观。仅整体bbox变化不证明联动与接合，有限case不证明全部参数范围。

实现入口为[src/skill.ts](../src/skill.ts)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)、
[参数UI](../houdini/python3.11libs/dsh_parameter_ui.py)、[绑定](../houdini/python3.11libs/dsh_control_bindings.py)；
具体签名、版本、限额和未支持范围以[工具设计](tool-design.md)为准。
文档门为npm run docs:check，HOM在隔离H21/H22执行[控制回归](../tools/tests/dsh-parameter-controls.test.py)及原有UI/执行边界回归；
少量自由控制通过派生锚点驱动主体/附属件的正反例见[控制设计回归](../tools/tests/dsh-control-design.test.py)，覆盖单项、组合、漏联动与状态恢复。
机制测试不证明GUI或自然任务泛化，验证记录留在会话/CI，不追加到本页。
