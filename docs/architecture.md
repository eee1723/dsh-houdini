# 系统架构与代码地图

## 运行边界

dsh-houdini是Cordis形状的DeepSeek Harness插件，不是独立MCP服务器。TypeScript Host注册
职责明确的工具；现场操作通过HTTP驱动已运行的Houdini，独立计算通过一次性hython执行明确文件，只有Houdini侧Python使用HOM。
用户内容输出锚定$HIP，插件源码不是任务工作区。后台job是异步排队，不是同一HOM会话并行。

```text
浏览器 → bare dsh-houdini frontend-host → DSH根client graph与Houdini Trace
用户消息 → Houdini preset内dsh-houdini/agent + persona + 按需skill
         → src/context.ts + scene-context.ts：事实上下文与一次现场指代观察
         → src/tools.ts → tool-runtime.ts / tool-query.ts → src/bridge.ts
         → dsh_bridge.py：HTTP → 主线程队列 → dsh_execution.py
         → dsh_hou_helpers.py → SOP/几何/相机模块
         → dsh_execution_results.py：结构化结果与证据
         → tool-output.ts / execution-history.ts → 模型上下文与client/trace
```

静态文档和构建通过不证明live已加载。查看当前/预期版本与重载要求使用[兼容设计](dsh-update-compatibility.md)
和[安装更新](setup.md)，不要从历史日志推断部署状态。
上游源码补丁、DSH公开接口、Qt容器、安装与纯Bridge的耦合分类、维护源及升级检查入口统一见
[DSH耦合点与升级维护](dsh-update-compatibility.md#dsh耦合点与升级维护)；本页只维护生产模块职责与代码位置。

## 职责分层

### 多Houdini执行端与任务恢复

默认入口使用独立工作台：一个DSH Host、多个自行登记的Houdini Bridge。对话通过DSH原生选择事件保存当前目标；用户可以更换已执行对话的现场，旧请求与历史回执保留自己的运行身份。
工作区目录只组织文件和对话，不用于猜测工程归属；Open Workspace按明确来源创建/定位指定对话，不读取目录内全部历史。只读不领取作者预留，修改才核对单作者和节点范围；保存点恢复仅处理原节点权限，不作为连接或聊天的前提。
工作台持有安装级运行锁；显式共享登记仅保留为开发入口，不能复用另一实例的端口身份。唯一设计与运维说明见[现场选择与工程恢复](multi-instance.md)，真实发行和用户live仍需单独验证。

### 节点片段交换

[节点片段交换](component-collaboration.md)维护component_export/import/replace的文件与显式替换能力。它不注册子Agent或提供另一种模式。

### 一次性独立执行

`houdini_isolated`为本次调用在新hython中执行明确builder或已保存HIP的副本，复用[隔离检查器](../tools/isolated-houdini-check.py)、输入依赖复制与自有进程回收。结果保留本次输入版本、实际执行、进程退出、检查和产物；原生图像沿DSH附件返回，长任务沿DSH既有作业机制承载。

DSH团队负责创建子任务、上下文和消息；每个作者可以调用同一工具完成独立构建与自验证，不需要常驻子作者执行端或新的会话状态机。同一live现场仍只有一个修改作者。团队默认交付builder及输入/入口和实际检查；现场作者通过现有exec/job的script入口执行并观察实际消费者，不自动合并或重放。需保留已有节点真实状态时按需使用原生片段；未保存现场与未声明依赖不属于独立检查的证据范围。按需方法见[独立执行skill](../skills/houdini-isolated-execution/SKILL.md)。

### 现役分层

程序化建模、HDA/工具和视频教学工程共用执行内核，不各建一套状态机、权限层或完成证书。
各方向与保留的Copernicus按需能力由workflow和领域模块承载，产品范围见[主要开发方向](development-directions.md)。
DSH负责会话、模型、通用Agent循环与通用交互；插件只增加Houdini能力与观察。
执行内核校验真实调用条件，任务计划和建模方法由作者选择。任务记录使用DSH已有能力，不形成执行准入。

| 层 | 唯一职责 | 不承担 |
|---|---|---|
| preset | 目标、问询、推进和交付表达 | 复述每个领域的recipe、强制所有问题变选择题 |
| guidance / tool schema | 跨域执行边界、发现入口、参数与返回合同 | 资产特例、动画测试帧清单、第二份需求账本 |
| workflow / domain helpers | 按任务装载方法，构建并测量声明范围 | 用文档或数值启发式认证未测语义 |
| Bridge | 主线程串行、身份、事务、回执和同次执行观察 | 为展示提醒重新执行Python、抢占正在运行的原生HOM |
| Host / client | 适配DSH公共接口、原生附件、结果与历史投影 | 猜用户意图并拒绝合法问答、按端口认领或终止进程 |

性能优化优先消除重复工作：工作区提示读取同次`execution.hip_dir`；浏览器按执行回执内观察时间/序列展示Session workspace与最近观察到的$HIP目录，查回旧回执不更新现场时间，不追加health/exec或维护HIP缓存；
视频读取的完整性校验只在单次命令内复用，下一次重新校验；主线程队列在任务间按时间片让出GUI。
权限与历史结果校验继续保留，不以缓存的观察代替现场事实。

## Host与浏览器

HDA交付开发检查由[tools/hda-delivery-check.py](../tools/hda-delivery-check.py)启动独立hython，
复制声明库/模块后验证真实回调、菜单、输出与实际依赖路径；不向live运行态开放任意按钮执行。

| 源码 | 维护职责 |
|---|---|
| [src/tool-catalog.ts](../src/tool-catalog.ts) | 工具的职责唯一源，注册、Trace与[工具说明](tools.md)共用 |
| [src/dsh-adapter.ts](../src/dsh-adapter.ts) | DSH消息生产者与持久工具日志适配；PTC原回执在公开日志middleware外层定型，避免展示spill截坏审计JSON，不改变模型展示或执行值 |
| [dsh_isolated_worker.py](../houdini/python3.11libs/dsh_isolated_worker.py) | 自有隔离进程初始化与退出，经[isolated-worker.py](../tools/isolated-worker.py)监管；一次性执行和开发评测复用 |
| [src/index.ts](../src/index.ts) | Cordis注册、稳定且persona中性的guidance、配置入口 |
| [src/frontend-host.ts](../src/frontend-host.ts) | bare包入口，在Host根Loader登记前端模块、前端能力与教程视频用途配置；DSH volatile字段和共享设置表单持久化provider/model/Python，设置页只做配置发现与本机依赖诊断；模型工具通过preset内dsh-houdini/agent加载 |
| [src/workbench-desktop.ts](../src/workbench-desktop.ts) | 认证DSH前端到当前独立桌面的固定工程动作、窗口置顶与非HOM在线观察；启动凭证不下发浏览器，不接受任意URL、命令或可执行路径 |
| [src/workbench-workspaces.ts](../src/workbench-workspaces.ts) | 已知临时目录的空工作区登记退出；复用DSH条件删除，保留目录、文件及会话，保护活动现场和用户保留项 |
| [src/node-delivery.ts](../src/node-delivery.ts) | 从原DSH执行回执坐标取回节点交付，复用当前Agent执行端绑定与Bridge队列；浏览器不自报节点目标 |
| [src/node-delivery-record.ts](../src/node-delivery-record.ts) | Host与生成客户端共享成功present_nodes动词回执的提取，不依赖业务返回值包装 |
| [src/image-output.ts](../src/image-output.ts) | 模型步骤前/显式查询的图像能力预检，Bridge 图像→DSH 原生附件；字节限额、原生与 Code Mode 图像返回，无工作区副本；元数据预检不证明GUI或识图成功 |
| [src/image-generation.ts](../src/image-generation.ts) | Host图片生成/编辑：复用DSH配置/凭据、上传参考图原字节；managed经Bridge只读观察所选HIP，原图与预览分别保存，不修改场景、不自动重试或替换模型 |
| [src/api-route.ts](../src/api-route.ts) | 图片与转录共用的DSH显式API路由、endpoint和凭据解析；不猜测模型协议、不维护第二份账号注册表 |
| [src/video-transcription.ts](../src/video-transcription.ts) | 教程ASR发现与执行，读取根配置后把单次凭据经环境传给普通Python子进程；传递明确并发/速率与模型选项，原生/PTC消费同一转录结果，attempt/outcome仍由视频脚本维护，无HOM和自动重试 |
| [src/video-runtime.ts](../src/video-runtime.ts) | 当前任务所选Houdini健康信息中的Python与版本私有FFmpeg/ffprobe路径事实；无任务上下文时明确Host启动环境范围，不依赖全局PATH、不安装系统软件 |
| [src/video-process.ts](../src/video-process.ts) | 随包离线媒体/证据CLI的Host入口，消费DSH文件策略与选定执行器运行时，直接返回原JSON/退出事实；无shell/凭据/云/HOM，不另建证据记录 |
| [src/project-paths.ts](../src/project-paths.ts)、[dsh_project_paths.py](../houdini/python3.11libs/dsh_project_paths.py)、[project-layout.json](../houdini/project-layout.json) | 工程目录角色同源合同、只读HIP锚点投影和Host受管目的地；不维护资产账本、迁移或自动清理，合同与验证见[工程文件](project-files.md) |
| [src/tools.ts](../src/tools.ts) | 公开执行/查询工具注册、参数分支互斥与派发；按职责注册工具 |
| [src/tool-runtime.ts](../src/tool-runtime.ts) | 调用级Host身份、只读/修改准入、按原回执定位历史runtime、原生图像附件与结果留存 |
| [src/isolated-execution.ts](../src/isolated-execution.ts) | houdini_isolated的一次性builder/HIP副本及受管准备操作；消费DSH输入政策、共享默认运行目录、原报告事实和详情引用，复用隔离检查器/DSH作业/附件，不建立常驻子执行端或自动合并 |
| [src/execution-source.ts](../src/execution-source.ts) | exec/job共用的内联或文件源码读取；经DSH文件服务固定UTF-8字节和摘要、核对可选版本后提交，不选择现场、不执行HOM、不自动重放 |
| [src/tool-query.ts](../src/tool-query.ts) | 场景读取与Host来源/历史结果/能力/回执查询分支；本地读取不解析执行端 |
| [src/tool-output.ts](../src/tool-output.ts) | 通用结果schema、模型正文与预览；同源执行事实保留canonical，重复内容和稳定审计清单按原详情引用，不再次解释领域结论 |
| [src/bridge.ts](../src/bridge.ts) | HTTP、取消/超时、每次场景执行前比对词表及语义版本；透传非自动交付的`artifactCandidates` |
| [src/executor-routing.ts](../src/executor-routing.ts) | 按对话明确选择路由、同工作区首次候选、写时作者预留和原运行实例历史查询；固定请求的runtime/scene epoch，不寻找历史替代目标 |
| [src/executor-controller.ts](../src/executor-controller.ts) | DSH认证Remote：按明确启动来源创建或定位指定会话，列出/选择/取消目标和退出活动查询；不扫描会话历史、不恢复节点或迁移目录 |
| [src/executor-host.ts](../src/executor-host.ts) | 工作台及显式共享开发入口共用的Host层服务；原生不唤醒上下文记录初始选择，preset不拥有Host，卸载撤销旧Bridge请求 |
| [src/executor-identity-projection.ts](../src/executor-identity-projection.ts) | 同源Session投影：原生目标选择/取消与旧格式读取，晚到回执不能覆盖新选择；输出当前工程与目标快照，历史本身不证明在线或节点归属 |
| [src/context.ts](../src/context.ts) | 上下文装配与请求准入；异步准备的按任务文本由原生context provider同步读取，原生/PTC共用能力注册事实，不以当前工具schema判断能力是否存在 |
| [src/scene-context.ts](../src/scene-context.ts) | 为每条用户消息采集一次轻量现场metadata，绑定消息、限制观察大小并在续接时读取原观察 |
| [src/scene-recovery.ts](../src/scene-recovery.ts) | 原节点权限的独立保存点评估与激活重试；写入时仅对匹配保存点尝试恢复，不自动找窗/加载/丢内容；本对话成功Save As从动词回执调用DSH原生目录迁移 |
| [src/prompt-data.ts](../src/prompt-data.ts) | 结构化补充段读取、事件定位及JSON字符串的模板转义 |
| [src/execution-history.ts](../src/execution-history.ts) | 单次快照的调用/结果索引、终态回执与job关联、未决执行和当前runtime锚；派生视图共同消费 |
| [src/executor-binding.ts](../src/executor-binding.ts) | 原生目标选择/取消的记录和固定开发连接来源；DSH负责持久化，不将历史操作作为明确换目标的门槛 |
| [src/support-report.ts](../src/support-report.ts) | 精确会话的原生持久读取与诊断投影，沿root Host认证RPC收集，不启动Agent或访问HOM |
| [dsh_support_report.py](../houdini/python3.11libs/dsh_support_report.py)、[dsh_support_ui.py](../houdini/python3.11libs/dsh_support_ui.py) | 唯一本地脱敏/ZIP收集器及独立管理器入口；worker收集已有记录，预览与分享同一份bytes，合同见[故障报告](support-reports.md) |
| [dsh_downloads.py](../houdini/python3.11libs/dsh_downloads.py) | QtWebEngine下载接收、用户目标、进度、取消与完成/失败反馈；用户打开的 HTTP(S) 外链交给系统浏览器，保留账户登录预开空页直到延迟导航到达 |
| [inspect-support-report.py](../tools/inspect-support-report.py) | 不可信诊断包的限额/清单/哈希检查与离线转义HTML，不解压或执行日志 |
| [src/execution-state.ts](../src/execution-state.ts) | 从公开工具事件重建运行状态、真实失败与未决请求；不按时间戳/计数触发注入，不维护另一事实库 |
| [src/task-sources.ts](../src/task-sources.ts) | 公开session中的原始用户消息/澄清问答来源锚、去重、有限摘录及同session分页回读；目标仅为计划记录，不推导需求替代/授权/验收 |
| [src/result-details.ts](../src/result-details.ts) | 大返回的不可变hash文件、分页JSON Pointer读取、损坏校验和保存失败回退；普通详情从原生/嵌套工具回执取原路径，加载警告从原生恢复记录取原路径，跨目录/重启仍可查；不执行HOM |
| [src/skill.ts](../src/skill.ts) | 随包skill/resource注册；[任务拆分skill](../skills/houdini-task-decomposition/SKILL.md)维护跨领域模块与反馈方法，[工具开发skill](../skills/houdini-tool-development/SKILL.md)维护HDA UI、脚本、Shelf与快捷键开发方法 |
| [src/generated-verb-contract.ts](../src/generated-verb-contract.ts) | 构建生成的Host名称/hash/语义版本，不手改 |
| [dsh_scene_recovery.py](../houdini/python3.11libs/dsh_scene_recovery.py) | Bridge主线程维护保存快照、加载基线、场景代际及部分精确恢复；保留未激活作者的可信来源，复制及原生重建不认领 |
| [dsh_recovery_store.py](../houdini/python3.11libs/dsh_recovery_store.py) | worker核对HIP字节、提交及查询可信末端保存点、保留原进程生命周期锁；查询不另建索引、不执行HOM |
| [dsh_load_warnings.py](../houdini/python3.11libs/dsh_load_warnings.py)、[结果预算](../houdini/result-detail-policy.json) | 主线程只采集有界首尾预览，HTTP worker按既有结果格式保存完整警告；同内容复用hash文件，后续现场仅引用，失败不回填全文；预算与Host结果读取同源 |
| [client.js](../client.js) | DSH CJS factory；普通任务导航、紧凑工程状态与选择组件、共享在线观察和按需Trace诊断 |
| [client/trace-runtime.js](../client/trace-runtime.js) | 回包解析与诊断组件创建；构建进入同一个DSH客户端bundle |
| [client/trace-model.js](../client/trace-model.js) | 公开轨迹的请求/调用索引、关系和统一统计；与React渲染分离 |
| [client/trace-view.js](../client/trace-view.js)、[trace-view.css](../client/trace-view.css) | 消费轨迹投影的记录/资料/高级诊断、历史正文、结构化详情与来源路径展示 |
| [client/node-delivery.js](../client/node-delivery.js) | 原生/嵌套回执的节点卡片投影，使用DSH公开Conversation与回复尾部插槽；文件交付继续由DSH负责 |

默认配置在src/index.ts：bridgeUrl为loopback 8765、requestTimeoutMs为120000、
automaticContext默认开启。超时不取消已开始的HOM修改，重试前回读状态。

提示词按唯一职责分层，避免同一规则在多处漂移：preset persona维护身份、质量/总成本目标、任务推进、观察判断与交付表达；
插件guidance只维护每次工具调用都必须可见的执行硬边界和领域路由；tool schema/verb docstring维护精确参数与返回；
domain skill给出本领域默认方法、例外和按需路由，reference维护具体构造、验证与依赖方法。SOP的原生编辑入口偏好由SOP skill维护，不进入执行准入。低频对象recipe不得进入persona/guidance；一个规则需要跨层出现时，
上层只保留路由或不可补救的硬约束，并指向下层唯一细节源。

复杂任务由persona路由到[任务拆分skill](../skills/houdini-task-decomposition/SKILL.md)，按编辑用途和依赖选择可观察单元；SOP的完整源组件由[建模方法](../skills/houdini-sop-workflow/references/modeling-methods.md#完整源组件与布局)维护，网络分组由[网络交接skill](../skills/houdini-network-handoff/SKILL.md)消费实际职责。DSH计划记录当前工作，执行回执提供事实，不增加模块状态机、完成账本或执行门槛。

工作区差异提醒由同次执行返回的已命名HIP目录投影，按agent去重；无目录或不确定回执不另发HOM探针。
scene-context为每条用户消息提供一次消息绑定的metadata；execution-history关联已记录执行事实，execution-state仅提供运行状态、真实失败与未知请求。任务资料从resource按需读取。
task-sources是按需回读/历史替换恢复用的原始材料索引。补充段独立记入plugin消息，不随Host整包runtime context重发。
三者不互相替代。缺失不等于空场景，被动选择变化不构成新任务或foreign修改授权。
client消费公开trajectory snapshot，不依赖已删除的Session内部字段。
导航由DSH公开session/workspace store提供当前任务、归档及重连状态，Python只提供HIP目录意图。
启动意图等原生列表基线就绪后才接管layout导航信号，避免把DSH初始恢复误认成用户离开；
后续导航取消、实际已选任务和意图消费仍取原生状态，不读取私有启动标记或另建选择缓存。
入口只消费Host返回的精确session ID；从某个Houdini进入默认创建明确preset的原生对话，继续历史需明确指定原对话。
不按目录和历史顺序自动找任务；原位重试复用同request ID，用户操作或新意图取消旧导航。

## Houdini执行模块

| 源码 | 维护职责 / 深入文档 |
|---|---|
| [dsh_component_contracts.py](../houdini/python3.11libs/dsh_component_contracts.py) | 普通SOP subnet片段候选导出/可信导入、hash/同构建/有限依赖检查；component_replace已有显式计划与有限迁移，完整依赖迁移和质量验收不由片段往返保证 |
| [dsh_bridge.py](../houdini/python3.11libs/dsh_bridge.py) | HTTP、主线程队列、job、身份与合同；队列每轮8ms预算，在任务之间让出GUI，不抢占HOM |
| [dsh_code_analysis.py](../houdini/python3.11libs/dsh_code_analysis.py) | 内联或脚本/尾段的同一AST、源码摘要核对、共享预检、Raw Gate、只读限制与raw使用分类；拒绝已知隐藏执行源码，编译同一AST，无HOM |
| [dsh_execution.py](../houdini/python3.11libs/dsh_execution.py) | 动词注册、签名绑定/缓存、调用追踪、编辑事务和现场执行事实；只读不准备编辑Undo或journals |
| [dsh_execution_results.py](../houdini/python3.11libs/dsh_execution_results.py) | 序列化、操作证据、检查和产物路径，统一编组公开结果信封 |
| [dsh_requests.py](../houdini/python3.11libs/dsh_requests.py) | 同runtime单次入场票、有界回执/正文缓存、owner/payload冲突拒绝；活动请求/job关联保护到执行终结，旧票不随缓存淘汰复活，无HOM |
| [dsh_hou_helpers.py](../houdini/python3.11libs/dsh_hou_helpers.py) | 公开动词导出与按需帮助；不持有可变执行状态，领域实现不反向导入此入口；完整目录由tool-design维护 |
| [dsh_ownership.py](../houdini/python3.11libs/dsh_ownership.py) | 节点identity、当前调用作者、嵌套创建记录、只读快照及Undo/HDA转换身份接续的唯一维护源；路径与持久标签不授予归属 |
| [dsh_errors.py](../houdini/python3.11libs/dsh_errors.py)、[dsh_node_access.py](../houdini/python3.11libs/dsh_node_access.py)、[dsh_service_constants.py](../houdini/python3.11libs/dsh_service_constants.py) | 无上层依赖的执行错误、节点解析和值投影、持久渲染服务标识 |
| [dsh_node_types.py](../houdini/python3.11libs/dsh_node_types.py)、[dsh_node_creation.py](../houdini/python3.11libs/dsh_node_creation.py) | 节点类型/参数卡自省、真实Tab/Shelf创建与失败清理；通过ownership接口记录身份 |
| [dsh_node_operations.py](../houdini/python3.11libs/dsh_node_operations.py)、[dsh_node_inspection.py](../houdini/python3.11libs/dsh_node_inspection.py)、[dsh_node_layout.py](../houdini/python3.11libs/dsh_node_layout.py) | 节点/端口修改、场景图读取、布局与网络展示；SOP组合调用这些基础操作，基础操作不依赖组合层 |
| [dsh_parameter_templates.py](../houdini/python3.11libs/dsh_parameter_templates.py)、[dsh_parameter_values.py](../houdini/python3.11libs/dsh_parameter_values.py)、[dsh_keyframes.py](../houdini/python3.11libs/dsh_keyframes.py)、[dsh_spare_parameters.py](../houdini/python3.11libs/dsh_spare_parameters.py) | 参数模板、严格读写与恢复、关键帧、spare/参数UI入口；共享模板和通道恢复由下层提供 |
| [dsh_hda_operations.py](../houdini/python3.11libs/dsh_hda_operations.py)、[dsh_hda_sections.py](../houdini/python3.11libs/dsh_hda_sections.py) | HDA创建/独立分叉/接口修改与section编辑；共享定义权限仍由hda_interfaces维护，节点身份转换交给ownership |
| [dsh_scene.py](../houdini/python3.11libs/dsh_scene.py)、[dsh_usd_inspection.py](../houdini/python3.11libs/dsh_usd_inspection.py)、[dsh_geometry_queries.py](../houdini/python3.11libs/dsh_geometry_queries.py) | 场景保存/时间线、USD只读信息、几何属性/分件/帧差与指纹观察 |
| [dsh_media_output.py](../houdini/python3.11libs/dsh_media_output.py)、[dsh_image_pixels.py](../houdini/python3.11libs/dsh_image_pixels.py) | 请求级图片收集、输出路径及预览预留；有界像素读取与统计，不把像素检测当语义识图 |
| [dsh_render.py](../houdini/python3.11libs/dsh_render.py)、[dsh_render_service.py](../houdini/python3.11libs/dsh_render_service.py)、[dsh_viewport.py](../houdini/python3.11libs/dsh_viewport.py)、[dsh_view_state.py](../houdini/python3.11libs/dsh_view_state.py) | 渲染编排、持久服务节点、viewport捕获、共享取景方向与界面状态恢复；服务标识与像素工具来自下层 |
| [dsh_preview_paths.py](../houdini/python3.11libs/dsh_preview_paths.py) | 验证/交付图片的managed/delivery/explicit路径、唯一capture预留及artifact元数据；不负责渲染或保留策略 |
| [dsh_network_layout.py](../houdini/python3.11libs/dsh_network_layout.py) | 无HOM、确定性的矩形/净距、局部避障与Box handoff规划 |
| [dsh_network_boxes.py](../houdini/python3.11libs/dsh_network_boxes.py) | 受治理Network Box、语义色、类型化provenance、handoff应用及Bridge恢复journal |
| [dsh_network_navigation.py](../houdini/python3.11libs/dsh_network_navigation.py) | 真实节点上的控制声明、持久交付标识、无cook读取与队列内定位；注解不代替控制有效性或ownership |
| [dsh_network_notes.py](../houdini/python3.11libs/dsh_network_notes.py) | Sticky Note读取/局部修改、独立运行身份归属、失败补偿与编辑事务恢复；在节点首次创建登记边界记录原生初始化便签，后加便签不继承父级归属；说明不承担任务完成状态 |
| [dsh_ui_capture.py](../houdini/python3.11libs/dsh_ui_capture.py) | 当前可见pane/Qt窗口/停靠面板发现、实际对象引用与精确区域截图；Bridge显式传入本次runtime身份，捕获实现不反向导入HTTP层；只观察已有界面，不建另一登记表或认证语义 |
| [dsh_cop_contracts.py](../houdini/python3.11libs/dsh_cop_contracts.py) | 原生ImageLayer全buffer观察、对齐差值和可恢复COP控制；exec-only、Manual/预算/非有限值边界，不证明艺术效果 |
| [dsh_hda_interfaces.py](../houdini/python3.11libs/dsh_hda_interfaces.py) | HDA界面版本、增量预检、通道保持及定义写入恢复；与场景Undo分离 |
| [dsh_tool_catalog.py](../houdini/python3.11libs/dsh_tool_catalog.py) | 当前原生节点/Shelf/Panel/State/Radial目录、实际来源与候选HDA定义；只读不建临时实例，不维护安装账本 |
| [dsh_package_discovery.py](../houdini/python3.11libs/dsh_package_discovery.py) | 原生Package配置与当前加载的唯一观察/解析边界；顶层磁盘目录、多资源/模块路径关系、未知条件与敏感值处理，不执行源码或推断修改权 |
| [dsh_tool_packages.py](../houdini/python3.11libs/dsh_tool_packages.py) | 原生JSON直接注册唯一源码目录、资源冲突自省和当前进程加载/启停；不复制源、不产归档、不改旧持久条件或删资源，保留部分失败和缓存事实 |
| [dsh_hda_lifecycle.py](../houdini/python3.11libs/dsh_hda_lifecycle.py) | HDA解锁/保存/锁定/参数提升的版本预览、共享实例权限和状态回读；不拆包或认领后代 |
| [dsh_hda_versions.py](../houdini/python3.11libs/dsh_hda_versions.py) | 原库追加原生类型版本、失败恢复和明确实例切换；保留旧定义，不迁移其他实例或认领foreign库/后代 |
| [dsh_parameter_ui.py](../houdini/python3.11libs/dsh_parameter_ui.py) | 共享组件展开、布局预检/诊断、单节点spare追加及状态保留 |
| [dsh_control_bindings.py](../houdini/python3.11libs/dsh_control_bindings.py) | 显式数值源/目标绑定、计划版本、现有驱动保护、回读与通道恢复 |
| [dsh_cook_control.py](../houdini/python3.11libs/dsh_cook_control.py) | Manual计算边界、单次批量依赖预检与规范不终止VEX模式识别；未知控制流不认证安全，不设隐藏上游节点数门，无跨调用缓存 |
| [dsh_worker_limits.py](../houdini/python3.11libs/dsh_worker_limits.py) | 自有Windows worker树限额、截止/取消与实际Job进程归零；GO、payload结果与树退出分开，不接管live进程 |
| [dsh_sop_contracts.py](../houdini/python3.11libs/dsh_sop_contracts.py) | build_module/verify_network、原生公共Output发布/接线验收、有界Packed内容检查、静态预检、失败清理、有序点弦长 |
| [dsh_operation_cards.py](../houdini/python3.11libs/dsh_operation_cards.py) | [节点卡](node-operation-cards.md)加载、精确类型限制、关键参数与决策提示 |
| [dsh_geometry_observation.py](../houdini/python3.11libs/dsh_geometry_observation.py) | Polygon边界/连通/朝向/截面、唯一性、稳定ID位移与变换；从最终SOP明确组采集有界观察，整件bgeo流核对大型控制实验恢复；同次复用、不跨调用缓存 |
| [dsh_geometry_evidence.py](../houdini/python3.11libs/dsh_geometry_evidence.py) | 有界Packed内存展开、面候选扫描和完整命名部件表面分区；不创建场景节点、不读Packed外部文件 |
| [dsh_modeling_units.py](../houdini/python3.11libs/dsh_modeling_units.py) | 源数量/单位到米制及显式旧场景适配的只读换算，保留源值和量纲，不改变HIP单位 |
| [dsh_procedural_plans.py](../houdini/python3.11libs/dsh_procedural_plans.py) | 只读原生SOP构造spec及代表参数状态规划；普通build/test执行仍受现有边界约束 |
| [dsh_quality_contracts.py](../houdini/python3.11libs/dsh_quality_contracts.py) | 实际接口、拓扑/domain和可恢复control实验 |
| [dsh_bgeo_fingerprint.py](../houdini/python3.11libs/dsh_bgeo_fingerprint.py) | 以原生BJSON流核对完整大型几何；解析字符串引用后排除写入时间等既定元数据，不忽略用户同名属性；不支持编码明确失败 |
| [dsh_camera_framing.py](../houdini/python3.11libs/dsh_camera_framing.py) | 八角点投影、预览取景/深度分离与镜头缩放、静态OBJ camera_fit、实际USD产品预检 |
| [dsh_context.py](../houdini/python3.11libs/dsh_context.py) | 主线程现场metadata与统一HIP身份；GUI自动采集不探测HIP文件或真实目录，显式磁盘状态另查；无socket/进程探测 |

[执行与证据契约](execution-contract.md)维护这些模块的跨层不变量，节点领域recipe在skills。

## 生命周期与机器态

| 源码 / 配置 | 职责 |
|---|---|
| [houdini/install.py](../houdini/install.py) | Houdini package安装、profile同步入口 |
| [Install.cmd](../Install.cmd)、[installer/install.ps1](../installer/install.ps1) | 无外部Python/Node引导、独立管理器不可变复制、package同目录原子注册、跨盘备份及注册清单；完整离线包使用Houdini内置Python暂存 |
| [Uninstall.cmd](../Uninstall.cmd)、[installer/uninstall.ps1](../installer/uninstall.ps1) | 读取实际注册清单并核对安装根，解除自有 Houdini 注册与快捷方式，保留版本/凭据/会话；独立于 Host/模型可用性 |
| [dsh_bootstrap.py](../houdini/python3.11libs/dsh_bootstrap.py) | Houdini启动固定版本选择，worker唤起受管独立工作台，主线程加载已校验版本的Bridge；未安装时仍能打开管理器 |
| [dsh_workbench.py](../houdini/python3.11libs/dsh_workbench.py) | 无HOM的独立桌面入口、工作台单例租约、Host进程组与Qt主窗口；先显示临时阶段/计时窗口，worker准备安装与服务；认证本机唤起、退出确认和受管激活，不持有工程执行身份 |
| [dsh_workbench_client.py](../houdini/python3.11libs/dsh_workbench_client.py) | Houdini菜单适配；主线程采集场景与原生文件事件，worker登记和唤起同一工作台；不复制DSH会话或在GUI线程等待网络 |
| [dsh_workbench_projects.py](../houdini/python3.11libs/dsh_workbench_projects.py) | 桌面端按需原生工程对话框、受控进程启动、启动回执和共享非HOM在线观察；明确启动意图与进程创建身份绑定，不替换其他现场、不自动重放操作 |
| [dsh_workbench_entry.py](../houdini/python3.11libs/dsh_workbench_entry.py) | 私有uiready启动钩子的Houdini侧接入；主线程捕获实际文件/场景，worker发布并回交同一次启动，不复制任务或凭路径认领节点 |
| [dsh_houdini_installations.py](../houdini/python3.11libs/dsh_houdini_installations.py) | Windows安装目录/版本发现与跨Houdini子进程环境；保留用户路径与启动脚本，不通过启动Houdini来探测安装 |
| [dsh_workbench_start.py](../houdini/python3.11libs/dsh_workbench_start.py)、[Open Workspace.cmd](../Open%20Workspace.cmd)、[open-workbench.ps1](../installer/open-workbench.ps1) | 不依赖运行中Houdini的源码/受管工作台入口；复用签名激活与单例租约。安装器创建带图标的本机快捷方式 |
| [产品Logo原图](../assets/dsh-houdini.png)、[设计说明](../assets/dsh-houdini.prompt.txt)、[ICO编码工具](../tools/build-workbench-icon.py) | 产品标志的唯一原图与多尺寸Windows图标生成；工作台和安装器快捷方式共用派生ICO |
| [dsh_install_ui.py](../houdini/python3.11libs/dsh_install_ui.py) | 源码/受管共用独立Qt主面板，高级设置并排提供运行与联网诊断入口；源码仅查看/更新说明，受管安装/同版修复/校验/回退，worker队列与取消 |
| [dsh_ui_style.py](../houdini/python3.11libs/dsh_ui_style.py) | 原生窗口共享主题与中文确认框；由独立管理器和当前运行版本各自随包交付，避免跨版本模块依赖 |
| [dsh_deployment.py](../houdini/python3.11libs/dsh_deployment.py) | RSA签名/资产/全量文件校验、安全解压、OS锁、旁路安装、独立数据快照和回退；无Node/hou/Qt依赖 |
| [dsh_managed_runtime.py](../houdini/python3.11libs/dsh_managed_runtime.py) | 受管路径/环境与共用Windows前端生命周期；先建立Job再放行CLI，reload保留句柄。普通路径只收自有树；显式强制Repair可按安装/主入口/原生进程句柄核验并终止旧DSH监听者，不按端口自动认领 |
| [dsh_executor_registry.py](../houdini/python3.11libs/dsh_executor_registry.py) | 多执行端登记与协作HIP单写租约候选；独立记录、原生文件身份、崩溃释放，不自动路由/重开或截获GUI保存 |
| [dsh_shared_executor.py](../houdini/python3.11libs/dsh_shared_executor.py) | 高级设置中的候选登记：主线程采集实际HIP/绑定Bridge动态端口，worker持久登记；不启动共享DSH、不保存HIP、不自动绑定任务 |
| [installer/release-trust.json](../installer/release-trust.json)、[deployment/runtime.json](../deployment/runtime.json)、[deployment/package-lock.json](../deployment/package-lock.json) | 发布公钥、固定Node分发摘要和完整依赖锁；不含私钥，公钥未配置时拒绝安装 |
| [MainMenuCommon.xml](../houdini/MainMenuCommon.xml) | Open Workspace与Version & Updates菜单；联网诊断收在版本窗口高级设置 |
| [dsh_launcher.py](../houdini/python3.11libs/dsh_launcher.py) | Open Workspace进入独立工作台；维护主线程Bridge修复、模块重载与HIP目录；保留旧内嵌诊断/隔离验证入口，不作为默认打开路线 |
| [dsh_manager.py](../houdini/python3.11libs/dsh_manager.py) | 版本诊断、配套DSH安装/修复、正式Release只读发现；更新等空闲，Repair显式确认强制DSH退出并交由launcher核验进程/Bridge空闲，不拉取或构建Git源码 |
| [dsh_network_diagnostics.py](../houdini/python3.11libs/dsh_network_diagnostics.py)、[原生网络探针](../houdini/python3.11libs/dsh_network_probe.mjs) | worker内复用精确DSH的系统/环境选路和抓取；只读展示来源与错误，区分新进程测试与live、搜索组件与实际搜索；不编辑代理配置 |
| [dsh_release_policy.py](../houdini/python3.11libs/dsh_release_policy.py) | 无hou/Node的官方稳定Release元数据验证、语义版本比较和受限大小查询；仅发现，不下载/激活资产 |
| [dsh_webview.py](../houdini/python3.11libs/dsh_webview.py) | QtWebEngine窗口、无隐藏/重建的原生窗口置顶、cookie、共享浮层材质/输入区背景兼容、页面剪贴板写入、`dsh-resource` Host语法注册与旧WebEngine先初始化时的窄URL兼容补丁；文件内容仍走Host RPC |
| [dsh_iterator_polyfill.js](../houdini/python3.11libs/dsh_iterator_polyfill.js) | 构建生成的core-js Iterator与Array.toSorted兼容实现，附MIT许可证；仅缺失/不兼容API补齐，不手改 |
| [dsh_web_auth.py](../houdini/python3.11libs/dsh_web_auth.py) | process-token→signed cookie、RPC wire与会话请求 |
| [dsh_profile_sync.py](../houdini/python3.11libs/dsh_profile_sync.py) | 官方CLI幂等同步当前profile声明的项目依赖 |
| [dsh_runtime_compat.py](../houdini/python3.11libs/dsh_runtime_compat.py) | 安装器/launcher/manager共享精确preferred版本、修复声明与cache选择；GUI仅读身份，启动worker核对完整文件；不以缓存时间选择其他版本 |
| [dsh-runtime-compatibility.json](../dsh-runtime-compatibility.json) | preferred DSH及支持组合的唯一清单 |
| [dsh-profile.requirements.json](../dsh-profile.requirements.json) | 当前受管profile的项目插件依赖清单 |
| [Houdini preset patch](../presets/houdini/cordis.patch.yml) | bundle组合与插件配置 |
| [presets](../presets/) | 唯一Houdini角色与由DSH 0.2标准生成的声明式preset；没有dev/product模式 |
| [gen-agent-presets.mjs](../tools/gen-agent-presets.mjs) | 使用精确DSH标准patch与persona.md生成唯一preset声明；build刷新、docs:check检查漂移 |
| [shared-host.cordis.yml](../shared-host.cordis.yml) | 显式候选Host组合；仅共享登记模式使用，不修改现役profile或替用户启动服务 |

GUI线程不得阻塞socket/子进程/netstat探测；进程缓存的UI/package变更需要完整重启Houdini。
前端Job所有权独立于launcher的UI状态，窗口关闭清理与launcher reload不丢失；Houdini退出回收自有前端及npx子孙。
启动器将Popen直接发布给本次attempt；异步取消按该对象匹配Job，迟到/重复取消不会停止后续启动。
普通启动对外部Bridge/Host端口占用仅报告冲突；显式强制Repair的窄范围核验例外见[安装合同](setup.md)。真实父/子/孙、reload、启动闸失败和外部进程隔离见
[前端生命周期回归](../tools/tests/dsh-frontend-lifetime.test.py)。此发行生命周期限Windows。
python3.11libs是目录名，通过PYTHONPATH共享纯Python实现，支持矩阵以兼容清单为准。

## 视觉、追踪和开发工具

[dsh_preview_paths.py](../houdini/python3.11libs/dsh_preview_paths.py)只维护验证与交付图片的managed/delivery/explicit路径策略、唯一capture分配
和artifact元数据；渲染、像素检查、Host原生附件及保留/清理策略仍由既有层负责。默认managed root为
`$HIP/dsh-artifacts/checks/previews/<run-id>/`，delivery直接生成到`$HIP/dsh-artifacts/renders/`；消费实际返回路径，不建立第二条图片复制管线，也不自动移动旧交付。
[dsh_network_layout.py](../houdini/python3.11libs/dsh_network_layout.py)是无HOM的矩形/间距、局部避障与Box handoff规划核心；
[dsh_network_boxes.py](../houdini/python3.11libs/dsh_network_boxes.py)维护可直接应用的Network Box分组、可选role颜色注解、
同批任意声明顺序的members/boxes嵌套、类型化Box provenance、presentation快照与Bridge undo核对。普通分组不要求预览hash；
布局handoff按其具体移动计划保留预览与应用。handoff不改变现有children/flow语义，只移动显式选中的
当前session自有扁平叶子Box及完整自有成员；component模式移动一层组件容器内的叶子框和成员，保留叶内布局。明确授权的既有网络可单次allow_foreign；服务和其他未授权/未选网络项仍固定。

视频教程解析由[video skill](../skills/houdini-video-tutorial/SKILL.md)组织，
[video_tutorial.py](../skills/houdini-video-tutorial/scripts/video_tutorial.py)在普通宿主进程中执行
  本地媒体准备、授权云转录、全片均匀粗扫/局部重看和结果校验，不经 Bridge、不调用 HOM。
帧索引保留实际 PTS 和播放时间轴起点；缩略图联系表与按显式区域比较的像素变化候选用于导航，
候选保留前后原图、阈值、比较模式和时间区间；可选择原图区域先裁切再缩放，不做自动语义或操作识别。
局部 `context` 汇集 hash 绑定的图像与转录，`check-notes` 校验 agent 填写的状态/操作记录，
只提供引用和结构验证，不证明语义真实性，不执行其中内容，也不据此授权工程修改。
同脚本的index-init/check-index维护来源绑定的章节/多时间段模块索引；read-transcript分页原文，
read-index按模块或section分页读取原文和既有notes引用，固定跨页索引版本并保留模块目的、输入输出和依赖；容器与视频跨度分别校验。
检查依赖、证据失效和预算，不自动划分语义或认证工程完成。
同脚本notes-init生成schema-2草稿或显式迁移旧notes，记录视频对象/网络/面板上下文、逐项事实引用、
跨包修正和参考图；index-link追加到新索引版本。query-notes按模块/对象/上下文/时间/字段查询，
保留冲突与历史；final视图只汇总作者声明，不自动选最新值。review-packet从已校验原帧生成局部观察入口，
export-brief从同源记录派生JSON与Markdown，保留对象/网络、方法事实和依据、观察/推断及缺口，不维护第二份事实源。
作者方法优先、必要适配与可切回优化由[视频复现协议](../skills/houdini-video-tutorial/references/reconstruction.md)维护，领域workflow引用该协议，不由工具建立准入或完成账本。回归仍在tools/tests/video-tutorial.test.py。
索引查询的SHA与context校验在单次命令内去重，文件身份/大小/时间变化则拒绝；成功返回前每个依赖
再做一次独立SHA核验，防止同大小且保留mtime的新内容绑定旧摘要。失败后释放作用域，下一次命令重新验证。
该优化不提供跨命令新鲜度保证，也不把多文件读取当成文件系统原子快照。
ASR按本次片段选择和请求/重试预算推进，失败/未知片默认延后，不阻断未提交片；重试另需明确授权。
网络线程有界并发且单任务锁覆盖全部已派发请求的结果保存；派发速率与在途上限分开。失败停止新派发，已在途成功/失败回执分别保留。成功outcome维护原始提供方响应、usage和句词时间的唯一源，export/context/分页从该出处校验正文和真实时间偏移，不维护第二份转录状态或按字数生成时间戳。另存纠错依据与整理稿不改变原ASR。
上传只使用逐片校验过的同一份bytes；现有日志缺原模型配置时不猜补，历史格式与原始尝试记录保留。
普通Python进程复用当前Houdini安装，FFmpeg/ffprobe由正式发行随版本提供；源码开发用私有依赖准备工具。注册skill和保存设置不会安装全局软件。DSH统一管理供应商与凭据，转录支持兼容音频接口及Qwen3-ASR-Flash的音频Chat接口；接口配置与真实转录支持分别判断。图像理解仍依赖当前模型的原生图像输入能力。
原视频、切片、转录及画面依据保存在仓库外任务目录，不进入包或 Trace 来源目录。
输入目前为本地视频，脚本不下载链接、不做语义识图，也不自动复现工程或更新生产知识。

教程复现按阶段选择领域 workflow；[COP skill](../skills/houdini-cop-workflow/SKILL.md)独立维护
Copernicus 图层/端口/关系、缓存和纹理交付，通过 [src/skill.ts](../src/skill.ts) 注册。
正文与参考按需读取，不扩充默认 guidance；[表面外观skill](../skills/houdini-surface-workflow/SKILL.md)统一维护参考分析、外观程度、来源选择与SOP的常量/文件/COP预览，SOP源几何与Solaris正式渲染仍各自负责。preset提供简短路由，src/skill.ts注册完整技能，具体参考由DSH原生skill/read按需送入模型；不引入材质账本或第二套供应商配置。COP的[图案设计](../skills/houdini-cop-workflow/references/pattern-design.md)按结构关系组织图层，不绑定产品题型。
图层工具实现独立在 `dsh_cop_contracts.py`，skill 只组织调用；版本与行为门见其
[验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)。

上下文通过DSH原生systemPrompt.context提供现场、运行状态和视觉通道事实。插件不重写会话surface，不自行执行上下文压缩或建立持久化门槛。DSH管理会话与上下文生命周期。

图片由Bridge按请求关联产图事实，经Host送入DSH原生附件存储和多模态工具结果，不复制到工作区media目录、不调用独立识图工具。附件传递不是语义验证，当前模型须实际查看图像。
Bridge从成功动词回执提取绝对且非链接、存在且非空的`artifactCandidates`，区分`delivery-candidate`、`visual-check`和`diagnostic`；`scene_save`/`scene_save_as`、`component_export`、`render_frame`、`render_view`及`viewport_screenshot`只报告各自权威路径。整个exec失败时降为诊断。候选不调用`present`，不能替代用户要求和最终验收；未进入动词回执的图片只作visual-check。
正式渲染、预览服务和用户viewport分别管理，不能通过用户视口状态选择交付目标。
节点交付使用普通执行结果中的显式引用，由DSH公开Conversation回放和回复尾部插槽展示。Root导航RPC重读原事件，使用`agentPresets.serviceFor`取得该任务隔离preset内的连接；与普通工具共用执行端绑定。Bridge导航路由只接受持久节点ID和原工程身份，主线程执行固定定位动作；票据/排队取消由同一RequestRegistry负责，不扩展普通同步HOM修改的取消语义。节点ID保存在HIP节点上，原路径只作历史显示，不另写节点交付账本。
Trace记录动词ledger、rawUsage、Gate、transaction与execution观察；Host在原生metadata保留返回事实，
大结果保存到workspace的`dsh-artifacts/results/`后才精简模型文本，路径来自工程目录合同；历史`.dsh-houdini-results`仍按回执原路径读取。该目录是工具返回副本，不是HIP内容输出。
失败/警告/unsupported/恢复错误、媒体路径和权限提示保留；未知结果可通过已提供的result_ref按字段读取。
页面信息架构、内容来源与历史快照同步规则见[Houdini Trace设计](houdini-trace-design.md)。
该文档区分实际请求System/schema/usage、上下文事件与当前构建来源目录；逐段运行provenance和最终messages可见集合尚未提供。

| 工具 | 长期职责 |
|---|---|
| [catalog-lib.mjs](../tools/catalog-lib.mjs)、[gen-client-catalog.mjs](../tools/gen-client-catalog.mjs) | 词表解析与Host/client生成 |
| [gen-trace-client.mjs](../tools/gen-trace-client.mjs) | 同源提取guidance/preset/注册技能与资源，嵌入手写Trace组件、样式及evidence-helpers副作用分类/采用统计函数；--check只读漂移验证 |
| [gen-web-polyfills.mjs](../tools/gen-web-polyfills.mjs) | 从锁定core-js生成Chrome 108兼容资产与许可证；web-polyfills与双版本Qt导航回归验证 |
| [gen-node-card-docs.mjs](../tools/gen-node-card-docs.mjs) | JSON节点卡→文档，严格schema与漂移检查 |
| [verb-operation-contracts.json](../houdini/verb-operation-contracts.json)、[gen-verb-contract-docs.mjs](../tools/gen-verb-contract-docs.mjs) | 按需动词输入/成功返回结构与示例的唯一源；dsh_execution.py的verb_help读取，生成[动词契约](verb-contracts.md)，不参与执行校验或常驻提示拼接 |
| [normalized-trace-steps.mjs](../tools/normalized-trace-steps.mjs)、[trace-session-lib.mjs](../tools/trace-session-lib.mjs) | 多帧zstd/回放去重、调用结果时序归一；逐请求usage去重及字段算术、逐轮错误/目标变更/压缩事件提取；V3上下文经安装的DSH公开surface校验器折叠，非法或校验器不可用时报告未知，legacy独立兼容 |
| [trace-report.mjs](../tools/trace-report.mjs) | 独立可读HTML目录与时间线 |
| [trace evidence extractor](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[evidence helpers](../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs) | 确定性调用/安全/视觉/证据提取；资源读取/能力预检作为Host调用单列，不计HOM动词采用率或裸执行；后台任务与结果保留范围复用executionHistory，不将提交回执完整误认为任务完成 |
| [run-node-tests.mjs](../tools/run-node-tests.mjs)、[clean-build.mjs](../tools/clean-build.mjs) | 回归发现与每次构建前清空纯生成lib，避免删除源码后残留旧输出 |
| [build-release.py](../tools/build-release.py)、[finalize-release.py](../tools/finalize-release.py)、[release-sign.mjs](../tools/release-sign.mjs) | 冻结npm依赖/组装与隔离签名分开、文件/许可证清单及候选隔离；不发布Release |
| [prepare-dsh-runtime.mjs](../tools/prepare-dsh-runtime.mjs)、[build-dsh-runtime-fixes.mjs](../tools/build-dsh-runtime-fixes.mjs)、[runtime-fix-inputs.mjs](../tools/runtime-fix-inputs.mjs)、[运行修复声明](../deployment/dsh-runtime-fixes/manifest.json) | 固定上游提交、完整补丁摘要及依赖锁；声明的inputFiles共同决定缓存身份，Node构建与Python启动核对同一份输入摘要，依赖或构建器变化须生成新缓存。记录产物摘要与许可；api-gateway维护WebSocket心跳与发送进展，排队Ping不重复堆积，传输状态不替代Houdini现场事实；Windows系统网络继承由http-proxy维护，原生PAC在专用worker解析；sandbox-windows-acl逐对象准备工作区，web-fetch-http提供实际路线，shell提供进程事实，ui-tool/Trace消费同源结果；session/persistence/workspace维护原生目录迁移，agent-loop与session-controller同步模型上下文及前端当前目录；不手改活动Host，不在Houdini插件重复实现这些通用能力 |
| [prepare-video-runtime.py](../tools/prepare-video-runtime.py) | 源码开发的私有媒体工具准备；复用正式发行的锁定来源与SHA校验，不修改系统PATH或用户全局工具 |
| [build-video-runtime.py](../tools/build-video-runtime.py) | 发行端从固定源码与工具链构建FFmpeg/zlib/FreeType/HarfBuzz/dav1d共享库，提供CPU AV1解码与PNG；保留七份对应源码、原始许可、实际Windows对象响应文件补丁、命令、DLL依赖与文件摘要，不进入普通用户安装步骤 |
| [prepare-managed-profile.mjs](../tools/prepare-managed-profile.mjs) | 使用锁定DSH的正式API初始化隔离profile，复制preset并绑定本Houdini的动态Bridge端口；无包管理器 |
| [run-deployment-tests.py](../tools/run-deployment-tests.py) | 离线安装故障与H21/H22隔离矩阵；真实包RPC入口见[部署测试](../tools/tests/dsh-deployment-e2e.test.py) |
| [houdini_test_environment.py](../tools/houdini_test_environment.py) | 部署/GUI测试及随包作者检查器共用的偏好、包目录、Python/Qt/DSH环境隔离与厂商bin启动目录；GUI验收CLI可隔离开发宿主的MSIX身份，保留自有进程树清理，不改变用户进程环境 |
| [isolated-houdini-check.py](../tools/isolated-houdini-check.py) | 固定输入根下的builder、HIP副本及加载后的受管准备代码；共享Bridge脚本执行、单份大详情与有界报告、检查及自有临时环境回收，供Host/CLI复用，不连接live或覆盖原HIP |
| [camera-karma-smoke.py](../tools/camera-karma-smoke.py)、[camera-preview-smoke.py](../tools/camera-preview-smoke.py) | 隔离真实renderer/GUI验收；预览入口核对取景、透明几何/实体背板合成与用户状态恢复，不代替任意材质的语义识图 |

程序化产品模型的开发评测集见[evaluation/product-modeling-dev-v1](../evaluation/product-modeling-dev-v1/)，信息隔离和验收原则见[评测设计](product-modeling-evaluation.md)。一次性probe及tools/out不是生产API；退役实验由Git历史保留，不在现役树维持副本。测试入口见[开发维护](development.md)。
