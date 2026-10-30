# 系统架构与代码地图

## 运行边界

dsh-houdini是Cordis形状的DeepSeek Harness插件，不是独立MCP服务器。TypeScript Host注册
职责明确的工具；现场操作通过HTTP驱动已运行的Houdini，独立计算通过一次性hython执行明确文件，只有Houdini侧Python使用HOM。
用户内容输出锚定$HIP，插件源码不是任务工作区。后台job是异步排队，不是同一HOM会话并行。

```text
浏览器 → bare dsh-houdini frontend-host → DSH根client graph、原生轨迹与节点交付
用户消息 → Houdini preset内dsh-houdini/agent + persona + 按需skill
         → src/context.ts + scene-context.ts：事实上下文与一次现场指代观察
         → src/tools.ts → tool-runtime.ts / tool-query.ts → src/bridge.ts
         → dsh_bridge.py：HTTP → 主线程队列 → dsh_execution.py
         → dsh_hou_helpers.py → SOP/几何/相机模块
         → dsh_execution_results.py：结构化结果与证据
         → tool-output.ts / execution-history.ts → 模型上下文、原生轨迹与节点交付
```

静态文档和构建通过不证明live已加载。查看当前/预期版本与重载要求使用[兼容设计](dsh-update-compatibility.md)
和[安装更新](setup.md)，不要从历史日志推断部署状态。
DSH公开接口、插件安装与Bridge的耦合分类、维护源及升级检查入口统一见
[DSH耦合点与升级维护](dsh-update-compatibility.md#dsh耦合点与升级维护)；本页维护目标产品边界与当前生产模块职责，不把现有模块清单当作保留要求。

## 目标产品形态

标准交付官方DSH Desktop中的标准插件，使用宿主原生会话、模型、任务与工作区，不再另维护Qt聊天窗口、独立Host或应用壳。插件贡献一个Houdini preset及对应界面；当前选中Houdini会话时显示现场选择、打开/新建及领域状态，其他模式保持原样。交互UI的显示与根客户端注册分开，后台接入和历史回执不因切换界面而丢失。

| 用户入口 | 目标行为 |
|---|---|
| 从Desktop进入 | 通过原生插件管理安装；选择Houdini模式后，明确绑定已登记现场，或选择Houdini版本和HIP/新工程，由插件启动并关联 |
| 从Houdini菜单进入 | 主线程取得当前实例/场景事实；向同一Desktop插件提交打开意图，定位或创建Houdini对话、选择合适工作区并绑定发起现场，再唤起页面。已有明确选择优先；歧义才让用户选择 |

两条入口走同一套会话、绑定与执行合同。菜单减少可由当前现场确定的步骤，不改变DSH存储含义或文件授权，也不从目录内全部历史猜测关联；未保存HIP不自动保存。绑定已有现场要求该Houdini已加载兼容Bridge，发现进程或HIP路径不等于取得控制连接。打开其他HIP默认新进程，不隐式替换已有未保存场景。

Houdini侧Package/helper由显式组件准备和真正新开Houdini前的同一安装路径部署；Host消费安装器结构回执，准备失败或取消时不继续启动进程。标准用户在官方插件UI安装并启用tgz后即可从Houdini模式使用，无须另找Install.cmd。Desktop插件版本、helper版本、Houdini安装及Bridge执行合同分别识别。Host插件目录与Bridge安装目录可以不同，不以相同物理路径证明兼容。宿主插件管理拥有Node侧安装，插件只管理自己的Houdini侧组件与兼容信息，不替换Desktop运行时。

菜单通过插件认证窄通道提交明确意图，由原生工作区/会话接口准备并在前端核对所选任务、preset和现场后确认。`dsh://open`只负责唤起窗口，不携带宿主owner权限；其余接线在插件内完成，没有修改Desktop主程序。标准路径已移除独立Qt工作台与私有运行包，尚欠验收只维护于[H-06](handoff.md#h-06-官方dsh共存与插件边界)。

Houdini模式的「置顶」只控制当前官方Desktop所属窗口，离开该模式恢复进入前的窗口层级。当前公开客户端没有窗口置顶合同，因此使用Windows窄适配：Host只能定位自己的Desktop父进程及窗口，不接受浏览器提供PID或窗口句柄；复用官方安装已有的Koffi，不带另一份Electron。窗口身份不明确时不操作，插件重载/卸载恢复自己的变更。退出条件是官方提供等价窗口接口，届时替换该适配。

模型与账户由DSH原生接口及用户选择的提供方管理；可选的第三方模型插件独立安装、升级和授权，不进入Houdini发行依赖。Houdini不维护订阅登录、账户数据库或授权迁移。Houdini侧仅保留接入、组件维护和离线诊断小窗口。完整会话诊断仍由Desktop提供，本端离线报告只包含明确的组件与连接事实。

## 职责分层

### 多Houdini执行端与任务恢复

默认入口使用官方DSH Desktop：一个原生Host、多个自行登记的Houdini Bridge。对话通过DSH原生选择事件保存当前目标；用户可以更换已执行对话的现场，旧请求与历史回执保留自己的运行身份。
工作区目录只组织文件和对话，不用于猜测工程归属；Open Workspace按明确来源创建/定位指定对话，不读取目录内全部历史。只读不领取作者预留，修改才核对单作者和节点范围；保存点恢复仅处理原节点权限，不作为连接或聊天的前提。
插件描述符只标识当前宿主的窄接入服务；场景登记与Bridge身份独立，不复用其他进程的端口或运行代际。设计与运维说明见[现场选择与工程恢复](multi-instance.md)，用户live实际加载须单独核对。

### 节点片段交换

[节点片段交换](component-collaboration.md)维护component_export/import/replace的文件与显式替换能力。它不注册子Agent或提供另一种模式。

### 现场长任务与在线状态

现场长任务只通过`houdini_job_submit`启动，先取得DSH原生jobs准入，再向Bridge提交。DSH负责job_id、归属、界面、通知与job_output/job_kill；Bridge的jobId、request_ref和runtime保留真实执行身份。Host只观察原任务，不另建调度器。运行中的HOM不能强停，取消排队任务与请求取消已运行任务分别表达；Host/作者卸载只释放本机观察，不等待或终止用户Houdini。重开后houdini_request按原回执重新观察，不重发代码。队列异步不保证原生长计算期间Houdini界面可交互；适合独立副本的计算可用houdini_isolated。

当前目标、待处理执行及恢复摘要由同一个DSH session projection增量维护；在线路由、上下文和恢复直接读取该投影，不在每个工具入口重扫日志。完整结果留原生日志与详情，按需历史读取和离线Trace复用同一事实转换。job/settled只表示DSH观察生命周期，不能替代HOM终态；明确的live job_output原始回执由同一个adapter解码，普通DSH作业不会改变Houdini身份。

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

| 源码 | 维护职责 |
|---|---|
| [desktop-paths.ts](../src/desktop-paths.ts) | 唯一插件运行命名空间、描述符、启动票据与登记路径，不另建DSH home |
| [desktop-integration.ts](../src/desktop-integration.ts) | 固定认证菜单通道、单次启动票据与原进程回执、显式继续观察和待消费导航；当前连接批次不替代原操作身份，不持有第二份会话历史 |
| [desktop-process.ts](../src/desktop-process.ts) | 复用DSH公开Win32绑定读取OS进程出生事实；按规范数据根的IPC生命周期互斥，不启动Houdini、不维护可抢删的PID锁 |
| [desktop-window.ts](../src/desktop-window.ts) | Windows Desktop父窗口的置顶读取、模式租用与原值恢复；仅操作经进程出生事实核对的自身父窗口，不提供通用窗口控制 |

HDA交付开发检查由[tools/hda-delivery-check.py](../tools/hda-delivery-check.py)启动独立hython，
复制声明库/模块后验证真实回调、菜单、输出与实际依赖路径；不向live运行态开放任意按钮执行。

| 源码 | 维护职责 |
|---|---|
| [src/tool-catalog.ts](../src/tool-catalog.ts) | 工具的职责唯一源，注册、节点交付及[工具说明](tools.md)共用 |
| [src/dsh-adapter.ts](../src/dsh-adapter.ts) | DSH消息与原生/嵌套持久工具日志适配；精确live job结果解码唯一源，节点交付生成器复用；日志原值与展示限额分离，不从普通作业文本猜Houdini事实 |
| [src/live-jobs.ts](../src/live-jobs.ts) | 先原生jobs准入再提交现场任务，按原runtime观察/请求队列取消，卸载释放本机观察；不重放代码、不把断线或取消意图冒充HOM终态 |
| [src/execution-facts.ts](../src/execution-facts.ts) | 同源增量执行事实转换；在线只维护待处理事实和必要锚点，冷历史读取可捕获原始记录；不建立任务完成账本 |
| [dsh_isolated_worker.py](../houdini/python3.11libs/dsh_isolated_worker.py) | 自有隔离进程初始化与退出，经[isolated-worker.py](../tools/isolated-worker.py)监管；一次性执行和开发评测复用 |
| [src/index.ts](../src/index.ts) | Cordis注册、稳定且persona中性的guidance、配置入口 |
| [src/frontend-host.ts](../src/frontend-host.ts) | bare包入口，在Host根Loader登记前端模块、前端能力与教程视频用途配置；DSH volatile字段和共享设置表单持久化provider/model/Python，设置页直接保存同源配置并诊断本机依赖；模型工具通过preset内dsh-houdini/agent加载 |
| [src/node-delivery.ts](../src/node-delivery.ts) | 从原DSH执行回执坐标取回节点交付，复用当前Agent执行端绑定与Bridge队列；浏览器不自报节点目标 |
| [src/node-delivery-record.ts](../src/node-delivery-record.ts) | Host与生成客户端共享成功present_nodes动词回执的提取，不依赖业务返回值包装 |
| [src/image-output.ts](../src/image-output.ts) | 模型步骤前/显式查询的图像能力预检，Bridge 图像→DSH 原生附件；字节限额、原生与 Code Mode 图像返回，无工作区副本；元数据预检不证明GUI或识图成功 |
| [src/image-generation.ts](../src/image-generation.ts) | Host图片生成/编辑：复用DSH配置/凭据、上传参考图原字节；managed经Bridge只读观察所选HIP，原图与预览分别保存，不修改场景、不自动重试或替换模型 |
| [src/api-route.ts](../src/api-route.ts) | 图片与转录共用的DSH显式API路由、endpoint和凭据解析；不猜测模型协议、不维护第二份账号注册表 |
| [src/video-transcription.ts](../src/video-transcription.ts) | 教程ASR发现与执行，复用DSH的环境清理后仅显式传入本次凭据；传递明确并发/速率与模型选项，原生/PTC消费同一转录结果，attempt/outcome仍由视频脚本维护，无HOM和自动重试 |
| [src/video-runtime.ts](../src/video-runtime.ts) | 普通Python与插件私有FFmpeg/ffprobe路径及真实命令诊断；明确设置优先，已选安装使用静态登记，无现场时使用已发现Houdini，不为分析教程先唤起HOM，不依赖全局PATH或安装推理包 |
| [src/video-configuration.ts](../src/video-configuration.ts) | 教程专用非秘密设置、显式文件协议与安全状态；复用DSH凭据引用、按origin隔离自定义服务key，不造聊天模型或第二套密钥存储 |
| [src/video-process.ts](../src/video-process.ts) | 随包离线媒体/证据CLI的Host入口，消费DSH文件策略与选定执行器运行时，直接返回原JSON/退出事实；无shell/凭据/云/HOM，不另建证据记录 |
| [src/project-paths.ts](../src/project-paths.ts)、[dsh_project_paths.py](../houdini/python3.11libs/dsh_project_paths.py)、[project-layout.json](../houdini/project-layout.json) | 工程目录角色同源合同、只读HIP锚点投影和Host受管目的地；不维护资产账本、迁移或自动清理，合同与验证见[工程文件](project-files.md) |
| [src/tools.ts](../src/tools.ts) | 公开执行/查询工具注册、参数分支互斥与派发；按职责注册工具 |
| [src/tool-runtime.ts](../src/tool-runtime.ts) | 调用级Host身份、只读/修改准入、按原回执定位历史runtime、原生图像附件与结果留存 |
| [src/isolated-execution.ts](../src/isolated-execution.ts) | houdini_isolated的一次性builder/HIP副本及受管准备操作；安装来自明确选定的执行端登记或显式HFS，登记断连不要求live健康；消费DSH输入政策、共享默认运行目录、原报告事实和详情引用，复用隔离检查器/DSH作业/附件，不建立常驻子执行端或自动合并 |
| [src/execution-source.ts](../src/execution-source.ts) | exec/job共用的内联或文件源码读取；经DSH文件服务固定UTF-8字节和摘要、核对可选版本后提交，不选择现场、不执行HOM、不自动重放 |
| [src/tool-query.ts](../src/tool-query.ts) | 场景读取与Host来源/历史结果/能力/回执查询分支；本地读取不解析执行端 |
| [src/tool-output.ts](../src/tool-output.ts) | 通用结果schema、模型正文与预览；同源执行事实保留canonical，重复内容和稳定审计清单按原详情引用，不再次解释领域结论 |
| [src/bridge.ts](../src/bridge.ts) | HTTP、取消/超时、每次场景执行前比对词表及语义版本；透传非自动交付的`artifactCandidates` |
| [src/component-compatibility.ts](../src/component-compatibility.ts)、[src/component-installation.ts](../src/component-installation.ts) | 执行/界面共用兼容判断；异步消费安装器预览与实际加载身份，区分待安装和待重开，不以组件构建差异阻断兼容执行 |
| [src/plugin-updates.ts](../src/plugin-updates.ts)、[release-update.json](../release-update.json) | 本插件正式发行的只读适用更新建议与同源修复范围校验；复用DSH兼容合同，安装/宿主更新仍由官方管理，方法与验证见[适配](dsh-update-compatibility.md#第三方插件更新入口) |
| [src/executor-routing.ts](../src/executor-routing.ts) | 按对话明确选择路由、同工作区首次候选、写时作者预留和原运行实例历史查询；固定请求的runtime/scene epoch，不寻找历史替代目标；独立worker只读所选登记的静态安装事实，不领取现场权限 |
| [src/executor-controller.ts](../src/executor-controller.ts) | DSH认证Remote：按明确启动来源创建或定位指定会话，列出/选择/取消目标和退出活动查询；不扫描会话历史、不恢复节点或迁移目录 |
| [src/executor-host.ts](../src/executor-host.ts) | 官方根插件拥有的现场目录与选择服务；原生不唤醒上下文记录初始选择，preset不拥有Host，卸载撤销旧Bridge请求 |
| [src/executor-identity-projection.ts](../src/executor-identity-projection.ts) | 同源Session投影：原生目标选择/取消与旧格式读取，晚到回执不能覆盖新选择；输出当前工程与目标快照，历史本身不证明在线或节点归属 |
| [src/context.ts](../src/context.ts) | 上下文装配与请求准入；异步准备的按任务文本由原生context provider同步读取，原生/PTC共用能力注册事实，不以当前工具schema判断能力是否存在 |
| [src/scene-context.ts](../src/scene-context.ts) | 为每条用户消息采集一次轻量现场metadata，绑定消息、限制观察大小并在续接时读取原观察 |
| [src/scene-recovery.ts](../src/scene-recovery.ts) | 原节点权限的独立保存点评估与激活重试；写入时仅对匹配保存点尝试恢复，不自动找窗/加载/丢内容；本对话成功Save As可在原授权项目内跟随原生工作目录，不改会话创建目录或历史位置 |
| [src/prompt-data.ts](../src/prompt-data.ts) | 结构化补充段读取、事件定位及JSON字符串的模板转义 |
| [src/execution-history.ts](../src/execution-history.ts) | 单次快照的调用/结果索引、终态回执与job关联、未决执行和当前runtime锚；派生视图共同消费 |
| [src/executor-binding.ts](../src/executor-binding.ts) | 原生目标选择/取消的记录和固定开发连接来源；DSH负责持久化，不将历史操作作为明确换目标的门槛 |
| [src/support-report.ts](../src/support-report.ts) | 精确会话的原生持久读取与诊断投影，沿root Host认证RPC收集，不启动Agent或访问HOM |
| [dsh_support_report.py](../houdini/python3.11libs/dsh_support_report.py) | 唯一本地脱敏/ZIP收集器及不可信包检查、转义HTML；会话与离线接入报告分别声明范围，预览和保存消费同一份bytes，合同见[故障报告](support-reports.md) |
| [dsh_connection_diagnostics.py](../houdini/python3.11libs/dsh_connection_diagnostics.py) | 本端Qt接入诊断与用户明确选择的报告查看/保存；主线程只采集内存白名单，worker生成/检查报告，不探测宿主私有日志或场景 |
| [inspect-support-report.py](../tools/inspect-support-report.py) | 命令行薄入口，复用同一不可信ZIP检查和离线HTML实现，不解压或执行日志 |
| [src/execution-state.ts](../src/execution-state.ts) | 从公开工具事件重建运行状态、真实失败与未决请求；不按时间戳/计数触发注入，不维护另一事实库 |
| [src/task-sources.ts](../src/task-sources.ts) | 公开session中的原始用户消息/澄清问答来源锚、去重、有限摘录及同session分页回读；目标仅为计划记录，不推导需求替代/授权/验收 |
| [src/result-details.ts](../src/result-details.ts) | 大返回的不可变hash文件、分页JSON Pointer读取、损坏校验和保存失败回退；普通详情从原生/嵌套工具回执取原路径，加载警告从原生恢复记录取原路径，跨目录/重启仍可查；不执行HOM |
| [src/skill.ts](../src/skill.ts) | 随包skill/resource注册；[任务拆分skill](../skills/houdini-task-decomposition/SKILL.md)维护跨领域模块与反馈方法，[工具开发skill](../skills/houdini-tool-development/SKILL.md)维护HDA UI、脚本、Shelf与快捷键开发方法 |
| [src/generated-verb-contract.ts](../src/generated-verb-contract.ts) | 构建生成的Host名称/hash/语义版本，不手改 |
| [dsh_scene_recovery.py](../houdini/python3.11libs/dsh_scene_recovery.py) | Bridge主线程维护保存快照、加载基线、场景代际及部分精确恢复；保留未激活作者的可信来源，复制及原生重建不认领 |
| [dsh_recovery_store.py](../houdini/python3.11libs/dsh_recovery_store.py) | worker核对HIP字节、提交及查询可信末端保存点、保留原进程生命周期锁；查询不另建索引、不执行HOM |
| [dsh_load_warnings.py](../houdini/python3.11libs/dsh_load_warnings.py)、[结果预算](../houdini/result-detail-policy.json) | 主线程只采集有界首尾预览，HTTP worker按既有结果格式保存完整警告；同内容复用hash文件，后续现场仅引用，失败不回填全文；预算与Host结果读取同源 |
| [client.js](../client.js) | DSH CJS factory；普通任务导航、紧凑工程状态与选择组件、全局教程设置及节点交付；通用调用详情复用DSH原生轨迹 |
| [client/node-delivery.js](../client/node-delivery.js) | 原生/嵌套回执的节点卡片投影，使用DSH公开Conversation与回复尾部插槽；文件交付继续由DSH负责 |
| [gen-node-delivery-client.mjs](../tools/gen-node-delivery-client.mjs) | 只生成同源live-job解码与节点交付客户端，不再生成独立Trace或提示词镜像 |
| [gen-verb-contract.mjs](../tools/gen-verb-contract.mjs) | 从tool-design生成Host动词名称、摘要、hash与执行版本，构建及docs:check共同校验 |

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
| [dsh_code_analysis.py](../houdini/python3.11libs/dsh_code_analysis.py) | 内联或脚本/尾段的同一AST、源码摘要核对、共享预检与Raw Gate；同源词法调用归属区分内建值、可信标准库API、HOM与未知，分类同时供准入和执行证据消费；拒绝已知隐藏执行源码，无HOM |
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
| [dsh_scene.py](../houdini/python3.11libs/dsh_scene.py)、[dsh_usd_inspection.py](../houdini/python3.11libs/dsh_usd_inspection.py)、[dsh_geometry_queries.py](../houdini/python3.11libs/dsh_geometry_queries.py) | 场景保存/时间线、USD只读信息及正式渲染共用的stage/settings与产品文件观察、几何属性/分件/帧差与指纹观察 |
| [dsh_media_output.py](../houdini/python3.11libs/dsh_media_output.py)、[dsh_image_pixels.py](../houdini/python3.11libs/dsh_image_pixels.py) | 请求级图片收集、输出路径及预览预留；有界像素读取与统计，不把像素检测当语义识图 |
| [dsh_render.py](../houdini/python3.11libs/dsh_render.py)、[dsh_render_service.py](../houdini/python3.11libs/dsh_render_service.py)、[dsh_viewport.py](../houdini/python3.11libs/dsh_viewport.py)、[dsh_view_state.py](../houdini/python3.11libs/dsh_view_state.py) | 渲染编排、持久服务节点、viewport捕获、共享取景方向与界面状态恢复；服务标识与像素工具来自下层 |
| [dsh_preview_paths.py](../houdini/python3.11libs/dsh_preview_paths.py) | 验证/交付图片的managed/delivery/explicit路径、唯一capture预留及artifact元数据；不负责渲染或保留策略 |
| [dsh_network_layout.py](../houdini/python3.11libs/dsh_network_layout.py) | 无HOM、完整矩形空间层级的避障/净距证明、迭代拓扑与Box handoff规划；预算约束实际搜索与空间关系计算，不按整网节点数准入 |
| [dsh_network_boxes.py](../houdini/python3.11libs/dsh_network_boxes.py) | 受治理Network Box、语义色、类型化provenance和handoff应用；首次创建网络登记原生框，整根删除通过原生Undo核对框／便签成员；局部完整补偿与按原生identity首次状态去重的Bridge恢复journal |
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
| [dsh_curve_paths.py](../houdini/python3.11libs/dsh_curve_paths.py) | 少量锚点与共享控制柄规划原生Add/Curve/Resample网络；实际折线段及半径包络的有界净距观察，返回最近位置与未覆盖范围，不求解自动布线或认证最终Sweep实体 |
| [dsh_quality_contracts.py](../houdini/python3.11libs/dsh_quality_contracts.py) | 实际接口、拓扑/domain和可恢复control实验 |
| [dsh_bgeo_fingerprint.py](../houdini/python3.11libs/dsh_bgeo_fingerprint.py) | 以原生BJSON流核对完整大型几何；解析字符串引用后排除写入时间等既定元数据，不忽略用户同名属性；不支持编码明确失败 |
| [dsh_camera_framing.py](../houdini/python3.11libs/dsh_camera_framing.py) | 八角点投影、预览取景/深度分离与镜头缩放、静态OBJ camera_fit、实际USD产品预检 |
| [dsh_context.py](../houdini/python3.11libs/dsh_context.py) | 主线程现场metadata与统一HIP身份；GUI自动采集不探测HIP文件或真实目录，显式磁盘状态另查；无socket/进程探测 |

[执行与证据契约](execution-contract.md)维护这些模块的跨层不变量，节点领域recipe在skills。

## 生命周期与机器态

| 源码 / 配置 | 维护职责 |
|---|---|
| [houdini/install.py](../houdini/install.py)、[installer/install.ps1](../installer/install.ps1)、[installer/uninstall.ps1](../installer/uninstall.ps1) | 显式源码Package与标准不可变helper安装、原子登记/版本选择和可恢复解除注册；以UTF-8结构回执供Host消费，不管理DSH运行时或会话 |
| [installer/legacy-migration.ps1](../installer/legacy-migration.ps1) | 历史生成入口的唯一所有权识别、安装目标环境解析、只读预览、逐字节/SHA256备份、可逆停用与变更保护；未知/混合内容保留，旧运行包、凭据、会话和工程不搬动、不清空 |
| [dsh_launcher.py](../houdini/python3.11libs/dsh_launcher.py) | 当前Bridge安全修复、版本事实及Desktop快捷入口；未保存工程目录由本进程维护 |
| [dsh_desktop_client.py](../houdini/python3.11libs/dsh_desktop_client.py) | worker内读取插件描述符、认证窄通道、官方Desktop唤起与错误反馈，不取得宿主owner凭据 |
| [dsh_workbench_client.py](../houdini/python3.11libs/dsh_workbench_client.py)、[dsh_workbench_entry.py](../houdini/python3.11libs/dsh_workbench_entry.py) | 菜单与uiready共享主线程捕获/worker接入流程，自动启动保留原票据准入、菜单保留明确现场导航语义；传输重试不重复HOM捕获与登记。保存转交下一原生脚本，uiready由Houdini平台调度所有匹配 |
| [dsh_deployment.py](../houdini/python3.11libs/dsh_deployment.py) | 原子JSON、进程创建身份和原生FileLease，供登记和恢复材料复用；不激活DSH版本 |
| [dsh_managed_runtime.py](../houdini/python3.11libs/dsh_managed_runtime.py) | 本进程执行端身份及隔离验证所需的自有进程树生命周期，不管理用户Desktop |
| [dsh_executor_registry.py](../houdini/python3.11libs/dsh_executor_registry.py)、[dsh_shared_executor.py](../houdini/python3.11libs/dsh_shared_executor.py) | 现场登记、实际运行/场景事实、节点与HIP写租约；不复制会话或推断执行终态 |
| [dsh_runtime_compat.py](../houdini/python3.11libs/dsh_runtime_compat.py) | 插件精确支持版本与本端兼容信息 |
| [dsh_ui_style.py](../houdini/python3.11libs/dsh_ui_style.py) | Houdini原生小对话框的本端样式，不是独立应用主题 |
| [dsh_web_auth.py](../houdini/python3.11libs/dsh_web_auth.py) | 隔离验证工具复用的官方Web认证与RPC客户端；不启动Host或维护用户会话 |

## 视觉、追踪和开发工具

[dsh_preview_paths.py](../houdini/python3.11libs/dsh_preview_paths.py)只维护验证与交付图片的managed/delivery/explicit路径策略、唯一capture分配
和artifact元数据；渲染、像素检查、Host原生附件及保留/清理策略仍由既有层负责。默认managed root为
当前命名HIP的`project_layout.directories.visual_check`并按run分组，delivery直接生成到`project_layout.directories.render`；两个角色按完整HIP文件主名分组。消费实际返回路径，不建立第二条图片复制管线，也不自动移动旧交付。
[dsh_network_layout.py](../houdini/python3.11libs/dsh_network_layout.py)是无HOM的矩形/间距、局部避障与Box handoff规划核心；
[dsh_network_boxes.py](../houdini/python3.11libs/dsh_network_boxes.py)维护可直接应用的Network Box分组、可选role颜色注解、
同批任意声明顺序的members/boxes嵌套、类型化Box provenance、presentation快照与Bridge undo核对。普通分组不要求预览hash；
布局handoff按其具体移动计划保留预览与应用。handoff不改变现有children/flow语义，只移动显式选中的
当前session自有扁平叶子Box及完整自有成员；component模式移动一层组件容器内的叶子框和成员，保留叶内布局。明确授权的既有网络可单次allow_foreign；服务和其他未授权/未选网络项仍固定。

规划保留全部固定障碍，以空间层级成簇证明净距，不展开全量节点对。readable按实际占用面积为宽层折行，保留主链、侧输入和真实层次；独立连通部分及显式分组共用矩形紧凑排布。宽度是阅读目标，不是准入限制；长链保留自然高度。布局只改变显式范围的位置，不创建Subnet或迁移依赖。搜索最多4096个候选，每个证据域最多250000次空间关系访问；预算耗尽明确失败，不截断障碍或报告通过。真实节点图须无环；分组折叠产生的相互依赖在同一层排列。事务只保留原生identity首次触碰状态，操作本身的失败补偿仍使用完整局部快照。

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
[参考工程与质量迁移](../skills/houdini-task-decomposition/references/reference-transfer.md)由任务拆分skill维护，把相关原图、观察尺度、可测精度和控制意图沿DSH现有任务／文件交给消费者；源工程不是完成证书，也不注册长期质量状态。原图与文字送达机制由既有原生附件及按需read消费，实际语义与新结果质量另验。
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

程序化产品模型的开发评测集见[evaluation/product-modeling-dev-v1](../evaluation/product-modeling-dev-v1/)，信息隔离和验收原则见[评测设计](product-modeling-evaluation.md)。一次性probe及tools/out不是生产API；退役实验由Git历史保留，不在现役树维持副本。测试入口见[开发维护](development.md)。
