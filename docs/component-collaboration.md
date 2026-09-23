# 多 Agent 组件建模与节点网络交付

本页是程序化建模重要优化方向的唯一长期设计：独立上下文、独立Houdini作者、普通subnet/节点片段交换和单作者装配。
维护职责、接口边界、实施依赖和验收标准；当前动作/验证缺口只在[交接H-05](handoff.md#h-05-组件协作与质量成本plincxev)滚动维护。
设计方向已确定；显式组件委派、独立worker、普通subnet往返与输出接线替换已有候选实现，完整工作包/依赖迁移和自然任务质量成本闭环尚未完成。
实际入口与限制以[词表](tool-design.md)和本页当前范围为准；设计说明不是启用指令或live操作授权。

## 目标与非目标

- 主Agent聚焦整体计算、共享控制、锚点和组件间衔接；组件Agent独立细化、看图、调试并验证自己的模块。
- 交付可直接进入修改的普通SOP subnet，支持有明确边界的同层节点网络；不要求制作、安装或维护自定义HDA定义。
- 总装HIP保留程序化网络，调参由Houdini原生数据依赖求值，不需要再次调用LLM。
- 减少主上下文携带的局部历史，同时检验最终质量和主/子总成本；不以Agent数量、面数或局部pass证明收益。

不建设同HIP多作者抢写、任意场景合并、无限子任务递归、自动几何代码合并或制造级正确性认证。
不删除既有HDA工具，也不禁止原生节点内部采用HDA实现；本路线不发布新的自定义HDA库，未知第三方定义依赖需明确拒绝或另行授权。
简单编辑、单部件任务默认单作者；连续曲面、跨模块Boolean或强耦合求解未稳定时不强拆，重复实例不逐个派作者。

## 当前基础与开放边界

component_export/component_import首版仅支持自包含、根输入未连接的普通SOP subnet，固定同构建、显式公共输出，合同可声明公共输入槽位inputs，
拒绝已知外部依赖/自定义HDA/回调；不支持同层集合、外部文件打包或自动候选接纳。component_replace迁移预览锁定的输出接线，保留旧网络；已连接输入、公共参数值/keys及其外部表达式消费者仅在显式migration计划声明时迁移，未声明拒绝。trusted=True必须明确确认原生档案可信，
不能将子作者返回的路径/hash当安全批准。静态扫描不证明任意代码安全或完整依赖闭包，自动子作者导入尚不可启用。
传输文件用hash固定字节，导入后只返回candidate；几何/接口/视觉验收仍需另做，不代表C1完整完成。

schema-2片段由Houdini原生保存/载入完整节点数据；自定义交换快照只镜像节点/接线清单及根spare公共参数，不另存全部内部值/参数模板。
依赖扫描仍检查引用通道、NodeReference、回调和类型来源；带表达式的NodeReference按实际求值目标查包含关系，原生间接输入按所属subnet/槽位记录。
内部Ramp保留在原生档案中，公共Ramp和替换预览仍以basis/keys/values表达，不能通过删除Ramp或改建模型来迁就传输。
导入验证公共接口、网络健康及明确输出；这些不证明内部任意代码安全或全部几何语义。完整节点数据等价由原生往返回归覆盖常见节点，不声称通用艺术正确性。
schema-1片段明确拒绝并要求从源subnet导出新文件，旧文件/HIP不修改。component_replace的手改检测仍保留内部状态指纹，不因交换快照精简而缩小；plan失配按侧命名原因：old手改（保留的本地分叉）、candidate被改、消费者接线变化或身份重建，不再只报泛化stale。
component_import在本session登记候选的module_id/revision/sha256 provenance；component_replace可用expected_contract把接纳钉在指定修订上，迟到旧修订与无provenance候选明确拒绝；provenance不跨Bridge重启，重启后带expected_contract的替换安全侧拒绝。修订使哪些候选过期的传播仍在工作包/任务文本层，机制层只提供接纳门。

正式锁定DSH的可续跑provider仅提供seed；独立源码候选扩展prepareContinuable的cwd，由Session创建持久化、冷恢复保留。
异步准备优先复用agent/pre-step，在首个模型请求/工具派发前等待绑定并flush；收件箱接受任务不等于执行端就绪。
该候选尚未进入兼容清单或安装运行态。确定性profile→两子任务→worker→片段导入→总控恢复已有测试入口；真实任务、文件/进程工具全路径隔离和正式发布资格仍待验收，不修改node_modules、伪造父身份或复制续跑状态机。

显式Host插件component-host注册component_delegate(task)、component_status()、component_wait(timeoutSeconds=30)与component_stop(childId)，不挂到默认安装/启动路线。这四个是父任务顶层Host工具，不属于Houdini动词目录；组件子任务不会获得它们，`verb_help`也不解析它们。status只取一次快照，后续用wait在Host API内等待状态变化及原生子任务消息，不反复轮询status/文件。Host在子任务首消息中同时列出可用顶层工具与动词边界，参数绑定错误返回精确签名后应直接消费，不把失败调用当发现机制。
status只读返回全局容量、本作者child/worker快照及权威workspace/HIP，既不派工也不判定完成；liveSceneState未观察时，磁盘HIP的大小/mtime不能证明live worker是否已有未保存修改。主作者须等待原生子任务完成通知再核对交付，不以快照或文件轮询替代等待。
worker就绪后意外退出、stdin失效或子作者被pre-step闸阻断时，Host向父作者发一次notice短报（父闲followup唤醒、父忙steer，按worker与原因去重；父已销毁只记日志）；显式停止、空闲释放和就绪前启动失败不产生短报，前者由component_stop回执承载、后者由delegate同步拒绝。
stop的`stopped`只表示受管进程已退出；`ok`与`checkpoint=saved`才表示空闲检查点已保存。异常回收返回`checkpoint=unknown`和原始错误，保留文件但不能将其视为已验证交付。
委派上限、进程内存/线程、GUI后端、超时、Python/Houdini路径和worker根目录都由Host配置；子作者没有自选端口/路径授权。
Host仅保留当前自有worker句柄和关联，不承担原生子任务队列。主任务正常完成一轮并转空闲后，Host给30秒续接窗口；若主子均仍空闲，只通过自有监管器STOP保存检查点并释放worker。新一轮开始会取消尚未发出的STOP，活跃子任务不被自动终止；主任务被销毁时也只释放空闲自有worker。停止失败记为检查点未知，不把进程退出冒充保存成功；已释放子任务不自动重启或重放，修订需重新委派。Host重启后不重开/收养旧worker；原任务恢复明确拒绝。
组件作者要求实际受限文件后端和workspace-write；工具执行限定建模、受限文件、技能、todo和父子消息，拒绝自行调用shell/任意job/再委派。
总装与worker工作区必须在平台临时目录之外，因为DSH允许workspace-write任务共同写平台临时目录；独立cwd不取消该原有例外。
文件工具越界有独立反例；Bridge中的Python和进程Job不是恶意代码的文件系统安全沙箱，不以此宣称任意代码隔离。
跨worker渲染单槽已实现：共享registry下render.lock的OS级FileLease（进程死即释放），render_view/render_frame进入时非阻塞取槽，被占即快速拒绝并建议改走houdini_job_submit；进程内可重入（render_view内部render_frame不自冲突），无registry的单执行端路线不取槽、由Bridge主线程队列串行。当前尚未实现结构化全局约束校验；接口修订失效的传播仍在任务文本层，机制层只有接纳门，主作者自行核对版本，不以本地句柄登记证明艺术/关系正确。
Host给子作者的简报先附权威workspace与固定`workspace/component.hip`，再附父作者文本；权威事实覆盖父简报中自称由Host分配的workspace/HIP/绝对导出目录，片段只写当前`$HIP`目录。子作者交付须给出component_export返回的完整绝对文件名、hash和合同；父作者按该文件名核对并导入，不从自己的`$HIP`猜子目录。scene_save保存原处；render_view是houdini_exec内动词，GUI可用时局部视觉义务须实看原生图像，headless可按授权尝试有界render_frame，否则明确未验证。该提示不能证明主作者完整传递了原始要求，冲突仍需追问，不替代结构化接口校验。

| 能力 | 当前事实 | 本设计新增的闭环 |
|---|---|---|
| 多执行端 | 显式共享Host、每任务精确绑定、每端单作者，默认入口仍单实例 | 受控创建子任务、worker和独立工作区，首条建模消息前绑定落盘 |
| 隔离执行 | 自有进程限额、隔离环境与新场景可信builder检查入口 | 常驻组件作者生命周期、工作包、发布与失败处理 |
| 节点/参数 | 创建、连接、spare参数、数值绑定、公共输出和质量检查 | 节点片段导入身份、依赖闭包、接口迁移和候选替换 |
| 图像 | 当前render_view要求GUI；headless另走render_frame | 子作者可用的完整图像反馈与资源调度，不把传输当语义验收 |
| 恢复 | 同runtime回执/部分状态观察 | 跨进程身份恢复尚未闭环；初版崩溃暂停，不自动重放未知修改 |

执行端登记/租约/代际的唯一说明是[多实例与任务恢复](multi-instance.md)，现役保证以[执行契约](execution-contract.md)为准。
普通subagent/fork配置不等于已获得独立Houdini写入能力。当前[设计协作协议](../skills/houdini-sop-workflow/references/module-design-collaboration.md)
默认仍限并行设计、单作者执行；用户显式选择且component_delegate实际可用时才走独立组件候选，不借allow_foreign或共享session身份绕过。

## 角色与执行所有权

| 角色 | 负责 | 不允许 |
|---|---|---|
| 主Agent | 用户合同、整体比例、确定性解算、接口与依赖、总控、装配和最终验收 | 接管子工程、默认重写组件内部实现、以子作者自评代替实测 |
| 组件Agent | 自身模块的表示/细节/局部参数、构建、观察、恢复和提交 | 修改主/兄弟工程、扩大公共参数域、偷改接口或已发布片段 |
| Host协调层 | 原生DSH子任务生命周期、工作区/执行端绑定、资源准入、文件发布与回执关联 | 调用HOM、凭模型给出的端口或路径授予权限、建立第二套可写完成账本 |
| 各端Bridge | 自己Houdini主线程队列、当前作者身份、动词/Gate/事务与观察 | 跨进程继承节点权限、在HTTP线程执行HOM |

一组件任务在执行期独占一个worker；不同进程可并行，单进程HOM仍串行。主Agent是总装唯一作者，子作者自行做局部验证；不新增独立评审Agent。
组件来源ID/hash用于追溯而非权限。受控导入创建的新节点登记为主作者的新identity；不迁移子作者注册表，不凭节点tag认领既有内容。
导入触发的原生初始化后代需有有界创建证据；延迟创建、未知回调或无法确认的后代保持未授权并阻断需要其权限的操作。

## 控制与接口合同

### 参数分工与解算

| 层 | 决定者 | 规则 |
|---|---|---|
| 全局自由参数 | 主Agent | 尺度、姿态、轮径等共享量只有一个维护源，明确单位/合法域 |
| 派生量与接口 | 主Agent发布，组件可提案 | 锚点frame、安装面、配合截面、容差和运动包络由确定性依赖计算 |
| 局部公开参数 | 组件Agent设计 | 胎槽、焊道、砖缝等局部控制由主Agent选取提升到总控；不复制全部局部参数 |
| 内部实现参数 | 组件Agent | 保留可编辑网络，不将每个采样分段都变成全局控制 |

主Agent定义数学关系及独立/派生量，由SOP/VEX/表达式执行，不靠重复心算或在多个代码串复制共享常量。
先处理欠约束/过约束和合法域，再生成锚点；初版不承诺通用约束求解器。强循环依赖合并模块或显式解算，不允许隐藏cook环。
局部参数一旦改变外包络、接口位置/孔径/安装面或邻接间隙，就必须进入接口协商，不能继续当私有细节。
UI载体与绑定机制沿用[控制参数设计](parameter-controls.md)；一般非线性几何依赖由领域网络表达，不扩大bind_controls的线性合同。

### 最小工作包

主Agent保留全部原始要求；每个子作者接收相关需求与依赖闭包，不复制整段主历史，也不能只收到主Agent的完成摘要。
机器可校验合同是唯一输入事实，提示词是可读投影；schema和工具名称在实现时确定，不把以下概念字段冒充现有API参数。

| 内容 | 必需边界 |
|---|---|
| 身份/版本 | 模块ID、合同schema/revision/hash、需求来源引用、受影响依赖修订 |
| 参考/质量 | 相关用户原话与参考、假设、LOD/观察距离、必需细节、允许简化和停止条件 |
| 空间 | 单位、轴向、手性、角度单位、局部坐标与local→assembly变换约定，禁止重复施加变换 |
| 接口 | 输入/输出槽位、稳定anchor ID/frame、实际接收面/截面、容差、允许间隙、禁止区和运动包络 |
| 控制 | 自由/派生/局部量、共享来源、默认与合法域、验证case和需保持的不变量 |
| 数据 | 只读邻接代理/表面及hash、属性class/type、稳定部件身份、材质槽、公开参数稳定内部名 |
| 资源/交付 | 组件输出范围、允许依赖、几何/cook/图像/模型预算、证据引用及未支持项 |

只给bbox或一个锚点不足以表达配合；接口须包含需要检查的真实表面、方向、截面与覆盖范围。
构建可以共享设计锚点，验收必须读取最终交付几何，不能以两个设计坐标相等自证连接。
缺信息时先回报可行性/局部参数建议；需要改变接口时提交提案，主Agent确认新修订后使受影响候选过期。
迟到结果、已撤销工作包或旧邻接版本不得自动接纳；通知和重做只作用于依赖它的模块。

## 普通节点片段交付

### 默认subnet与同层网络

默认组件根为普通SOP subnet，内部是完整可编辑节点/VEX，spare参数在组件根或明确CTRL，内部采用相对引用。
组件外部依赖仅经声明的公共输入和受控参数绑定；不得保留worker绝对路径、全局Python变量或相邻组件的猜测路径。
subnet须连接实际原生Output，多出口逐槽声明；内部Null/display flag不替代公共端口。普通geo仍仅设实际末端显示/渲染，不强制增加Output。

同层网络同样允许，但交付须枚举根节点集合、完整成员、CTRL、输入/输出接线和参数依赖；网络框不是成员/权限证据。
初期先通过subnet端到端验收，再启用同层片段。不得默默折叠用户手改网络、用HDA替代或把源码存在当作可调节点交付。

### 序列化与依赖

候选底层采用SideFX的saveItemsToFile/loadItemsFromFile保存/载入节点片段；它们是序列化能力，不是权限、原子导入或依赖完整性保证。
加载可能成功但报告warning，禁止ignore_load_warnings静默洗绿。实现须经受控动词/Bridge入口，不能让作者直接raw调用绕过守卫。
依据：[SideFX节点序列化](https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html#serialization)。

片段包包含节点数据、版本化接口/依赖manifest、必要文件及hash、有限验证引用；源HIP由组件工作区保留，不合并到主HIP。
发布修订只用于固定传输字节，不创建HDA类型版本或永久定义库。几何缓存可用于代理/预览，不能代替程序化网络。
依赖必须移入最终工程受管资源路径并回读验证，不能依赖可清理的worker目录；不复制所有子任务历史/缓存。
首版限定同一精确Houdini构建内交换，分别在H21/H22验收；跨版本交换在有迁移测试前拒绝，不自动转换节点类型。
拒绝未声明自定义定义、任意外部脚本/回调/文件副作用；内置HDA节点按目标版本解析，不导出成新的自定义库。
hash只证明内容固定，subnet不锁定也不等于安全；序列化片段可能含可执行表达式或Python节点，受控进程不构成恶意代码安全沙箱。

## 导入更新与用户编辑保护

1. 子作者在自己的staging写完并验证后发布不可变片段；Host固定同一份字节与依赖hash，防半写、路径穿越、别名和校验后替换。
2. 主作者显式接收模块/合同修订，在自身新建隔离staging容器导入；不覆盖同名既有网络，不载入/清空/merge主HIP。
3. 确认创建identity、依赖、内部相对引用、spare参数/表达式/keys、公共输出和局部非空，再显式接入共享控制/锚点。
4. 在实际装配变换下查部件成员/基数、接口、控制响应和图像；候选未通过不切换正式消费者。
5. 提交前复核旧模块identity、结构/参数/接线指纹及候选hash；有用户/GUI修改或外部消费者变化则停止自动替换，plan失配按漂移侧命名返回。
6. 记录全部外部导线、参数消费者及用户公开值/表达式/keys；按稳定接口ID显式迁移后切换。机制已落地为component_replace的显式migration计划：输出接线总是迁移，已连接根输入须逐槽映射（inputs，JSON传输的槽位键接受数字字符串并归一为整数槽位），公共参数值/keys与外部表达式消费者按参数名迁移（public_parms声明元组名，逐通道完整迁移——通道级声明被拒并指向元组名，绝不静默丢失其余通道），未声明的输入/消费者/引用形态拒绝，失败逆序恢复。接口删除/改名/类型变化须迁移计划，不能按位置猜。带表达式的keyframe、keyframed消费者与跨组件引用仍拒绝。
7. 复读新接线与实际最终输出；失败恢复已记录的接线/控制并保留旧模块。恢复不完整则停止，不能宣称原子成功。

总装的内部手改视为本地分叉：默认保留并请求合并策略，不全文覆盖、不把“最新片段”当成更高权限。
输入/输出两次提交间存在并发GUI改动的风险；首版要求明确编辑窗口和提交前后检查，不宣称已拦截所有GUI写入。
旧模块身份/动态引用无法可靠核对时拒绝自动更新，允许保留两个候选供显式选择；不自动推断任意Python表达式消费者。
Houdini Undo只保证其支持的场景编辑；外部文件/回调不在保证内。headless失败不得套用GUI事务承诺。

### 检查点与历史体量

最终HIP面向当前装配，不堆积每轮尝试。最多保留当前候选和一次待确认回退副本作为默认工作策略；未决失败证据不自动淘汰。
历史修订主要在任务目录，保留规则按可恢复性与用户需求明确，不能形成无限版本库。不得删除用户手改分叉、其他作者内容或未归档的唯一产物。
清理前列出精确候选及外部引用/恢复影响，用户确认后仅清理已知自有节点/文件；超出暂存限额时暂停发布而不是静默删除旧成果。
总装保存/重开应能在停止所有worker后独立求值，不要求发布目录、源HIP或临时脚本仍在线。

## Worker与子任务生命周期

优先一个共享Host、一个总装执行端和两个独立GUI worker；第一版不动态扩到任意并发。
Host负责子任务workspace、HIP路径、偏好/包/缓存/临时目录隔离、固定版本与启动限额；不由子作者自行开进程或改注册配置。
单纯spawn通常仍继承部分父上下文/工作区，必须验证并适配，而非提示它“不要碰父目录”。

启动顺序必须有闸：预留child身份/独立cwd→创建child并可接受任务→pre-step等待自有worker、核对HIP/版本/代际、领取写入预留→持久化绑定并flush→才允许首个模型请求/工具执行。
收件箱接受与就绪分别表达，失败必须在模型准入前拒绝；首次模型消息应包含绑定事实。普通UI选端仍限idle，不能直接把该检查放宽为任意运行任务可换目标。
精确DSH版本若无目录准备能力，先完成受控provider适配与兼容验证；禁止spawn后竞速补绑定、fork父执行端绑定或回退到固定端口。
模块子任务优先fresh上下文且可续跑；Host接入原生子任务/消息/回执机制，不复制账号、不建立第二个Agent队列或状态真相源。

每进程主线程消费自己的队列，CPU/内存/渲染/模型并发分别限额；多SOP内部线程不能和worker数一起无限相乘。
Bridge预检拒绝常见的`os.walk`/`Path.walk`/`Path.rglob`及递归`Path.glob('**/...')`目录遍历，保留静态非递归`Path.glob('*.hip')`；直接`glob`调用也拒绝，以免无界源文件搜索占住GUI主线程。源码检查应在Houdini外用有界文件工具完成。静态预检不是任意Python可抢占的执行沙箱，已在运行中的HOM/未知请求仍按回执和检查点边界处理。
共享渲染资源单槽即registry根render.lock租约（见上节机制）；其余数值限额来自目标机器实测与显式配置，不把开发机配置写成发行默认。
GUI用于复用现有render_view闭环；后续hython池须补低成本render_frame预览、图像交付与非GUI失败策略，不能静默跳过局部看图。
许可证、驱动、UI后端与目标版本分别验证；配置失败/资源不足明确排队或暂停，不借用用户其他Houdini进程。

取消先停止新派工并区分已执行/执行中/未知；原生HOM不能任意抢占。只回收经进程句柄确认的自有worker树，不因心跳超时杀进程。
同runtime未知请求先查回执；崩溃暂停，保留工作包/产物与证据。自动重开和ownership持久恢复是后续能力，不能凭tag自动续跑。
worker退出不意味着组件完成；总装不受单组件失败影响，已发布且已接纳的片段保持可用。

## 实施依赖与完成门

以下是稳定的实施顺序和验收责任，不是第二张滚动待办表；完成后原位维护实际保证，不追加进度日志或通过记录。
现有H-01/03的版本、隔离执行与绑定边界是前提；H-04/06承担真实输出判据；H-08承担需求来源和依赖变化。
不必等待所有远期自动恢复完成才做离线片段验证，但未闭环能力必须保持拒绝/暂停。

| 阶段 | 工作包 | 完成门与负例 |
|---|---|---|
| C1 节点片段往返 | 合同schema、导出/导入受控入口、普通subnet、依赖与身份登记；无LLM | 两独立工程片段导入第三工程，改名/参数/多出口/共享控制有效；同名、缺依赖、旧hash、路径别名、加载warning、失败残留均有反例；关闭worker后重开总装可用 |
| C2 执行隔离与启动闸 | 独立child/workspace/GUI worker，复用registry/router和资源限制 | 第一条HOM前绑定落盘；错目标/代际/flush失败零派发；子作者不能写父/兄弟节点或目录，停止只影响自有端；不复制账号或启动重复Host |
| C3 两组件建模闭环 | 主Agent合同解算、局部工作包与可续跑子作者、代理/中期/终版接纳 | 各自构建和图像反馈；主作者只接纳已测片段，最终成员、变换后实际表面接口及共享参数扰动/恢复有证据；不回灌整段子历史 |
| C4 变更与失败恢复 | 修订失效传播、候选切换、用户手改保护、检查点与清理 | 旧稿迟到拒绝；内部手改/新增外部引用阻断覆盖；失败保旧、未知请求不重做、崩溃暂停；公开参数/keys/消费者迁移与恢复失败反例 |
| C5 质量与成本验收 | 固定模型/版本/信息/视角的三组对照与简单任务反例 | 分别对比单作者整体、单作者模块聚焦、多作者独立进程；固定总预算比质量、固定验收质量比总成本，记录重复运行分布、用户纠正与集成返工 |

首个夹具选两个接口稳定的组件，先验证共享尺寸/安装面的联动，再扩到多模块。夹具只用于开发回归，不进入[产品模型评测](benchmark-design.md)的未见题，也不以训练过的例子证明泛化。
默认/边界case从实际输出测响应和不变量，最后一次修改后刷新验证；有局部pass仍需总装成员/关系门，不支持表示保留unverified。
艺术细节需整体与可辨局部图像的语义判断；图片送达、像素非零、面数增加都不是质量分数。
模型预算含主/子输入、输出、缓存和重复请求，另记合同规模、峰值上下文、启动/排队/cook/渲染耗时与资源峰值。
缓存读取不等于独立文本或账单；总费用按实际provider计费口径另算，不以主会话变短宣称总费用下降。

## 源码接入与验证入口

以下是现有接入点，不表示新能力已存在。新增模块/动词/schema必须在实现时进入架构索引与唯一词表；不在设计文档虚列可调用工具。

| 范围 | 现有实现 | 验证基础与需补覆盖 |
|---|---|---|
| 组件委派 | [component-host](../src/component-host.ts)、[supervisor](../tools/component-worker.py)、[worker](../houdini/python3.11libs/dsh_component_worker.py) | [真实DSH链路](../tools/tests/dsh-component-loop.test.py)、[双worker/GUI预览](../tools/tests/dsh-component-worker.test.py)；真实模型/恢复全路径仍待验 |
| Host生命周期/绑定 | [executor-host](../src/executor-host.ts)、[routing](../src/executor-routing.ts)、[controller](../src/executor-controller.ts)、[execution-state](../src/execution-state.ts) | [路由](../tools/tests/executor-routing.test.mjs)、[绑定](../tools/tests/executor-binding.test.mjs)；补child启动闸/目录隔离/迟到结果 |
| worker/登记 | [registry](../houdini/python3.11libs/dsh_executor_registry.py)、[worker限额](../houdini/python3.11libs/dsh_worker_limits.py)、[隔离环境](../tools/houdini_test_environment.py)、[隔离执行](../tools/isolated-houdini-check.py) | [双执行端](../tools/tests/dsh-multi-executor.test.py)、[限额](../tools/tests/dsh-worker-limits.test.py)；补GUI作者/退出/预览资源 |
| 节点片段 | [片段合同](../houdini/python3.11libs/dsh_component_contracts.py)、[Bridge](../houdini/python3.11libs/dsh_bridge.py)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py) | [往返回归](../tools/tests/dsh-component-exchange.test.py)、[隔离驱动](../tools/tests/run-component-exchange.py)、[ownership](../tools/tests/dsh-node-ownership.test.py)；完整依赖/候选更新仍待覆盖 |
| 接口/控制 | [SOP合同](../houdini/python3.11libs/dsh_sop_contracts.py)、[控制绑定](../houdini/python3.11libs/dsh_control_bindings.py)、[质量检查](../houdini/python3.11libs/dsh_quality_contracts.py) | [公共输出](../tools/tests/dsh-output-publication.test.py)、[集成](../tools/tests/dsh-module-integration.test.py)、[控制](../tools/tests/dsh-parameter-controls.test.py)；补跨进程片段/真实实例关系 |
| 需求/证据 | [来源](../src/task-sources.ts)、[工具](../src/tools.ts)、[Trace归一](../tools/normalized-trace-steps.mjs)、[usage](../tools/trace-session-lib.mjs) | [Trace证据](../tools/tests/trace-evidence-helpers.test.mjs)；补模块修订、主子成本与末次修改后证据失效 |

每阶段按[开发规范](development.md)运行适用Node/HOM回归，H21/H22分别验证；新入口必须继承raw-gate、ownership、caught-failure、tab-create-failure、object-parenting和scene/network/render门。
文档改动用npm run docs:check；运行时实现用npm test及对应隔离回归，发行/加载另按[兼容设计](dsh-update-compatibility.md)。
真实模型收费、live修改/重启与正式发行分别按相应边界执行；机制测试不能核销真实建模质量或运行时加载路径。

## 候选启用与人工验收

源码Houdini菜单只显示Open Workspace；新开且已保存的HIP在无自有前端时可显式选择Component preview，Regular workspace为默认。组件预览选择会准备独立profile、启动自有共享Host并打开内嵌页；重复点击只唤起同一HIP页面，不迁移模式或另起Host。
不再需要两终端手工启动。首次预览只自动采用专用`DSH_HOUDINI_COMPONENT_BIN`显式指定的CLI；普通工作区的`DSH_HOUDINI_DSH_BIN`仅作选择框初值，不能证明已带子任务cwd扩展。未指定组件候选仍须选择构建好的DSH CLI。当前Houdini GUI可执行文件从进程/HFS定位，独立Python从真实`python.exe`或唯一的本地pythoncore安装定位；WindowsApps商店别名和歧义安装不自动采用，缺项才弹窗。路径/源码校验仍执行，配置持久化后重复打开不再询问，
新profile独立配置模型/账号，旧手工Host任务不自动迁入。菜单收敛不代表普通运行时或受管安装已启用组件能力；未保存HIP直接走普通工作区。
当前保存的HIP作为总装HIP；首次委派在它的目录下建`dsh-components/<child-id>/workspace/component.hip`，
先核对已绑定执行端、实际HIP和任务cwd一致。每个子作者仍是独立HIP/进程，不改主HIP；
同目录布局允许主工作区的普通文件工具访问子工程，不能把它宣传为文件系统隔离。
它只消除启动脚手架，不核销下面的自然任务、图像、恢复与发行门。

候选要求带provider cwd扩展的DSH源码构建，不能把官方同版本号包当作已含扩展。未修改版本应在子任务模型准入前因workspace不符拒绝。
使用新建独立DSH_HOME，不复制账号或旧任务；[准备器](../tools/prepare-component-profile.mjs)参数依次为DSH bin.js、新home、Python、Houdini GUI、worker根、registry绝对路径，环境DSH_HOME须等于参数home。
准备器仅建候选profile/preset和component.cordis.yml，不启动模型/服务、不修改正式兼容清单，不是受管发行安装。
共享Host启动使用该overlay及同一registry环境；总装可用[worker监管器](../tools/component-worker.py)的--gui --show显式打开独立新工程。
--show只用于需要用户查看的总装，默认子worker隐藏；首次启动的限额闸后才保存新HIP、登记动态Bridge。停止写STOP到监管器stdin；空闲时保存检查点。`component_stop`在等待超时或写入失败时返回`ok=false, checkpoint=unknown`，`component_status`保留`stop_unknown`及原因；稍后进程退出也不把未知改写为已保存。无法按期退出的监管器会回收自有树，不承诺运行中原生操作无损取消。

人工测试应先做两普通subnet的参数/输出/修改闭环，再做接口稳定的两个细节组件；不以盒体夹具替代自然建模验收。
检查任务/目录/执行身份分离、两模块真正进入最终输出、局部细节与接口特写、共享控制扰动恢复、局部返工不重建另一组件、预览后手改导致替换拒绝。
另测简单单参编辑不派工、worker关闭后的续跑拒绝、停止worker后总装可用；不要直接从旧任务跨进程认领重开的节点。
各case报告pass/fail/unverified与实际步骤/截图，费用口径包含全部主子请求。C5及未实现的完整依赖/迁移能力不能因这些基本测试通过而核销。

## 长期维护规则

本页只维护组件协作的决策/合同/稳定验收矩阵；执行端运维在multi-instance，控制实现边界在parameter-controls，底层权限在execution-contract，活动状态在handoff。
schema/绑定/更新语义改变时同步producer、consumer及正反例，旧片段必须明确拒绝或有显式迁移；绝不静默解释为新合同。
能力落地后将本页对应“未实现”边界原位替换为实际保证及测试入口，并核销handoff项；不保留已完成阶段的流水账。
领域建模方法仍只在skills维护；只有新工具链可用且完成治理/版本验收后才更新协作skill与preset，不用提示词提前绕过现役边界。
单次Trace、图片、耗时、模型成绩与机器路径留会话/CI或非打包产物；长期文档不依赖tools/out，不建立按日期分叉的计划或HDA历史库。
