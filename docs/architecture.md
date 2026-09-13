# 系统架构与代码地图

## 运行边界

dsh-houdini是Cordis形状的DeepSeek Harness插件，不是独立MCP服务器。TypeScript Host注册
5个工具，通过HTTP驱动一个已运行的Houdini；只有Houdini侧Python使用HOM。
用户内容输出锚定$HIP，插件源码不是任务工作区。后台job是异步排队，不是同一HOM会话并行。

```text
用户消息 → preset/persona + 按需skill
         → src/context.ts：每条用户消息至多一次只读现场摘要
         → src/tools.ts → src/bridge.ts：类型/权限上下文、握手、请求
         → dsh_bridge.py：HTTP → 主线程队列 → 受限执行/动词追踪
         → dsh_hou_helpers.py → SOP/几何/相机模块
         → 结构化结果、operation-evidence、原生图像附件 → Host → client/trace
```

静态文档和构建通过不证明live已加载。查看当前/预期版本与重载要求使用[兼容设计](dsh-update-compatibility.md)
和[安装更新](setup.md)，不要从历史日志推断部署状态。

## 职责分层

### 多Houdini执行端与任务恢复

源码已集成显式共享执行端模式：一个DSH Host、多个独立Houdini Bridge、每个任务持久绑定一个执行端。
默认Open Workspace仍是单实例，受管安装锁不自动解除；共享模式需明确启用，不能复用另一实例的端口身份。
唯一设计与运维说明见[多实例与任务恢复](multi-instance.md)：身份分层、启动/选择、写入预留、Repair范围、
退出与恢复边界及验收入口。代码整合和隔离验证不代表当前live已加载，也不代表崩溃自动续跑完成。

### 现役分层

四个产品方向共用执行内核，不各建一套状态机、权限层或完成证书。
程序化建模、HDA/工具、视频教学工程与Copernicus的差异由按需workflow和领域模块承载。

| 层 | 唯一职责 | 不承担 |
|---|---|---|
| preset | 目标、问询、推进和交付表达 | 复述每个领域的recipe、强制所有问题变选择题 |
| guidance / tool schema | 跨域执行边界、发现入口、参数与返回合同 | 资产特例、动画测试帧清单、第二份需求账本 |
| workflow / domain helpers | 按任务装载方法，构建并测量声明范围 | 用文档或数值启发式认证未测语义 |
| Bridge | 主线程串行、身份、事务、回执和同次执行观察 | 为展示提醒重新执行Python、抢占正在运行的原生HOM |
| Host / client | 适配DSH公共接口、原生附件、结果与历史投影 | 猜用户意图并拒绝合法问答、按端口认领或终止进程 |

性能优化优先消除重复工作：工作区提示读取同次`execution.hip_dir`，不追加health/exec或维护HIP缓存；
视频读取的完整性校验只在单次命令内复用，下一次重新校验；主线程队列在任务间按时间片让出GUI。
权限与历史结果校验继续保留，不以缓存的观察代替现场事实。

## Host与浏览器

HDA交付开发检查由[tools/hda-delivery-check.py](../tools/hda-delivery-check.py)启动独立hython，
复制声明库/模块后验证真实回调、菜单、输出与实际依赖路径；不向live运行态开放任意按钮执行。

| 源码 | 维护职责 |
|---|---|
| [src/index.ts](../src/index.ts) | Cordis注册、稳定且persona中性的guidance、配置入口 |
| [src/image-output.ts](../src/image-output.ts) | Bridge 图像→DSH 原生附件；模型能力检查、字节限额、原生与 Code Mode 图像返回，无工作区副本 |
| [src/tools.ts](../src/tools.ts) | 五工具schema、参数分支互斥、结果/原生图像交付、纯展示函数 |
| [src/bridge.ts](../src/bridge.ts) | HTTP、取消/超时、每次场景执行前比对词表及语义版本 |
| [src/executor-routing.ts](../src/executor-routing.ts) | 共享Host候选：从持久任务绑定解析登记、验证执行端并固定调用级Bridge，无自动默认或重绑 |
| [src/executor-controller.ts](../src/executor-controller.ts) | DSH公开Remote候选：发现列表与空闲任务首次选择，严格输入/预留/代际校验，不是模型工具 |
| [src/executor-host.ts](../src/executor-host.ts) | 仅Host层挂载的共享服务候选；preset消费不持有服务生命周期，重复挂载拒绝，卸载撤销旧Bridge请求 |
| [src/context.ts](../src/context.ts) | 按需指代采集、message绑定及预算；pre-step按公开surface去重独立补充段，历史替换时恢复，普通查询不追加上下文 |
| [src/execution-state.ts](../src/execution-state.ts) | 从公开工具事件重建有限历史状态及未决请求/检查失效/运行身份变化提醒；不按时间戳/计数触发注入，不维护另一事实库 |
| [src/task-sources.ts](../src/task-sources.ts) | 公开session中的原始用户消息/澄清问答来源锚、去重、有限摘录及同session分页回读；目标仅为计划记录，不推导需求替代/授权/验收 |
| [src/result-details.ts](../src/result-details.ts) | 大返回的不可变hash文件、原workspace内分页JSON Pointer读取、损坏校验和保存失败回退；不执行HOM |
| [src/ask-user-guard.ts](../src/ask-user-guard.ts) | 问答参数结构与错键诊断；不按问句关键词推断意图，不强制选项数量 |
| [src/skill.ts](../src/skill.ts) | 随包skill/resource注册；[工具开发skill](../skills/houdini-tool-development/SKILL.md)维护HDA UI、脚本、Shelf与快捷键开发方法 |
| [src/generated-verb-contract.ts](../src/generated-verb-contract.ts) | 构建生成的Host名称/hash/语义版本，不手改 |
| [client.js](../client.js) | 手写CJS factory；原生DSH工作区/任务导航、Houdini Trace、回放解析和生成目录 |
| [client/trace-view.js](../client/trace-view.js)、[trace-view.css](../client/trace-view.css) | 五看板、公开Trajectory请求/调用适配、结构化详情、技能证据与类型配色；构建嵌入client.js |

默认配置在src/index.ts：bridgeUrl为loopback 8765、requestTimeoutMs为120000、
automaticContext默认开启。超时不取消已开始的HOM修改，重试前回读状态。
工作区差异提醒由同次执行返回的已命名HIP目录投影，按agent去重；无目录或不确定回执不另发HOM探针。
scene-context只为现场指代提供用户消息绑定的metadata；execution-state按有意义的异常变化提醒，
task-sources是按需回读/历史替换恢复用的原始材料索引。补充段独立记入plugin消息，不随Host整包runtime context重发。
三者不互相替代。缺失不等于空场景，被动选择变化不构成新任务或foreign修改授权。
client消费公开trajectory snapshot，不依赖已删除的Session内部字段。
导航由DSH公开session/workspace store提供当前任务、归档及重连状态，Python只提供HIP目录意图。
同HIP已有页仅唤起，换目录/新页/Repair才触发一次选择；有效当前Houdini任务优先，再选同目录非归档根任务，
确实没有才经公开Remote创建明确preset。原位重试复用同request ID，不刷新草稿；用户操作或新意图取消旧导航。

## Houdini执行模块

| 源码 | 维护职责 / 深入文档 |
|---|---|
| [dsh_bridge.py](../houdini/python3.11libs/dsh_bridge.py) | HTTP/main-thread queue、job、Raw Gate、query、transaction、trace envelope；队列每轮8ms预算，在任务之间让出GUI，不抢占HOM |
| [dsh_requests.py](../houdini/python3.11libs/dsh_requests.py) | 同runtime单次入场票、有界回执/正文缓存、owner/payload冲突拒绝；活动请求/job关联保护到执行终结，旧票不随缓存淘汰复活，无HOM |
| [dsh_hou_helpers.py](../houdini/python3.11libs/dsh_hou_helpers.py) | 65动词的主要实现、真实Tab/Shelf、参数、provenance、HDA、USD、render入口 |
| [dsh_cop_contracts.py](../houdini/python3.11libs/dsh_cop_contracts.py) | 原生ImageLayer全buffer观察、对齐差值和可恢复COP控制；exec-only、Manual/预算/非有限值边界，不证明艺术效果 |
| [dsh_hda_interfaces.py](../houdini/python3.11libs/dsh_hda_interfaces.py) | HDA界面版本、增量预检、通道保持及定义写入恢复；与场景Undo分离 |
| [dsh_hda_lifecycle.py](../houdini/python3.11libs/dsh_hda_lifecycle.py) | HDA解锁/保存/锁定/参数提升的版本预览、共享实例权限和状态回读；不拆包或认领后代 |
| [dsh_parameter_ui.py](../houdini/python3.11libs/dsh_parameter_ui.py) | 共享组件展开、布局预检/诊断、单节点spare追加及状态保留 |
| [dsh_control_bindings.py](../houdini/python3.11libs/dsh_control_bindings.py) | 显式数值源/目标绑定、计划版本、现有驱动保护、回读与通道恢复 |
| [dsh_cook_control.py](../houdini/python3.11libs/dsh_cook_control.py) | Manual计算边界、单次批量依赖预检与规范不终止VEX模式识别；未知控制流不认证安全，不设隐藏上游节点数门，无跨调用缓存 |
| [dsh_worker_limits.py](../houdini/python3.11libs/dsh_worker_limits.py) | 自有Windows worker进程树限额、超时/取消与退出回收，不接管live进程 |
| [dsh_hda_ui.py](../houdini/python3.11libs/dsh_hda_ui.py) | 旧UI模块的兼容导入入口 |
| [dsh_sop_contracts.py](../houdini/python3.11libs/dsh_sop_contracts.py) | build_module/verify_network、原生公共Output发布/接线验收、有界Packed内容检查、静态预检、失败清理、有序点弦长 |
| [dsh_operation_cards.py](../houdini/python3.11libs/dsh_operation_cards.py) | [节点卡](node-operation-cards.md)加载、精确类型限制、关键参数与决策提示 |
| [dsh_geometry_observation.py](../houdini/python3.11libs/dsh_geometry_observation.py) | Polygon边界/连通/朝向/截面、唯一性、稳定ID位移与变换 |
| [dsh_quality_contracts.py](../houdini/python3.11libs/dsh_quality_contracts.py) | 实际接口、拓扑/domain和可恢复control实验 |
| [dsh_camera_framing.py](../houdini/python3.11libs/dsh_camera_framing.py) | 八角点投影、预览取景/深度分离与镜头缩放、静态OBJ camera_fit、实际USD产品预检 |
| [dsh_context.py](../houdini/python3.11libs/dsh_context.py) | 主线程现场metadata，无socket/进程探测 |

[执行与证据契约](execution-contract.md)维护这些模块的跨层不变量，节点领域recipe在skills。

## 生命周期与机器态

| 源码 / 配置 | 职责 |
|---|---|
| [houdini/install.py](../houdini/install.py) | Houdini package安装、profile同步入口 |
| [Install.cmd](../Install.cmd)、[installer/install.ps1](../installer/install.ps1) | 无外部Python/Node引导、独立管理器不可变复制、package原子注册与备份；完整离线包使用Houdini内置Python暂存 |
| [dsh_bootstrap.py](../houdini/python3.11libs/dsh_bootstrap.py) | Houdini启动固定版本选择，后台校验/数据快照、主线程加载；未安装时仍能打开管理器 |
| [dsh_install_ui.py](../houdini/python3.11libs/dsh_install_ui.py) | 源码/受管共用独立Qt主面板与高级诊断入口；源码仅查看/更新说明，受管安装/同版修复/校验/回退，worker队列与取消 |
| [dsh_deployment.py](../houdini/python3.11libs/dsh_deployment.py) | RSA签名/资产/全量文件校验、安全解压、OS锁、旁路安装、独立数据快照和回退；无Node/hou/Qt依赖 |
| [dsh_managed_runtime.py](../houdini/python3.11libs/dsh_managed_runtime.py) | 受管路径/环境与共用Windows前端生命周期；先建立Job再放行CLI，reload保留句柄。普通路径只收自有树；显式强制Repair可按安装/主入口/原生进程句柄核验并终止旧DSH监听者，不按端口自动认领 |
| [dsh_executor_registry.py](../houdini/python3.11libs/dsh_executor_registry.py) | 多执行端登记与协作HIP单写租约候选；独立记录、原生文件身份、崩溃释放，不自动路由/重开或截获GUI保存 |
| [dsh_shared_executor.py](../houdini/python3.11libs/dsh_shared_executor.py) | 候选登记菜单：主线程采集实际HIP/绑定Bridge动态端口，worker持久登记；不启动共享DSH、不保存HIP、不自动绑定任务 |
| [installer/release-trust.json](../installer/release-trust.json)、[deployment/runtime.json](../deployment/runtime.json)、[deployment/package-lock.json](../deployment/package-lock.json) | 发布公钥、固定Node分发摘要和完整依赖锁；不含私钥，公钥未配置时拒绝安装 |
| [MainMenuCommon.xml](../houdini/MainMenuCommon.xml) | Open Workspace、Version & Diagnostics菜单 |
| [dsh_launcher.py](../houdini/python3.11libs/dsh_launcher.py) | worker启动/repair、主线程接入、模块重载与HIP目录意图；只读Host就绪、不再筛选/创建任务，preset/profile共用动态DSH_HOME |
| [dsh_manager.py](../houdini/python3.11libs/dsh_manager.py) | 版本诊断、配套DSH安装/修复、正式Release只读发现；更新等空闲，Repair显式确认强制DSH退出并交由launcher核验进程/Bridge空闲，不拉取或构建Git源码 |
| [dsh_release_policy.py](../houdini/python3.11libs/dsh_release_policy.py) | 无hou/Node的官方稳定Release元数据验证、语义版本比较和受限大小查询；仅发现，不下载/激活资产 |
| [dsh_webview.py](../houdini/python3.11libs/dsh_webview.py) | QtWebEngine窗口、cookie、DocumentCreation兼容补丁 |
| [dsh_iterator_polyfill.js](../houdini/python3.11libs/dsh_iterator_polyfill.js) | 构建生成的core-js Iterator兼容实现，附MIT许可证；仅缺失/不兼容API补齐，不手改 |
| [dsh_web_auth.py](../houdini/python3.11libs/dsh_web_auth.py) | process-token→signed cookie、RPC wire与会话请求 |
| [dsh_profile_sync.py](../houdini/python3.11libs/dsh_profile_sync.py) | 官方CLI幂等同步profile依赖、精确版本兼容修补 |
| [dsh_runtime_compat.py](../houdini/python3.11libs/dsh_runtime_compat.py) | 安装器/launcher/manager共享精确preferred版本与cache选择；不以缓存时间选择其他已验证版本 |
| [dsh-runtime-compatibility.json](../dsh-runtime-compatibility.json) | preferred DSH及支持组合的唯一清单 |
| [dsh-profile.requirements.json](../dsh-profile.requirements.json) | 受管profile依赖与移除清单 |
| [cordis.patch.yml](../cordis.patch.yml) | bundle组合与插件配置 |
| [presets](../presets/) | Houdini生产/开发persona；身份与领域工作方式，不放进插件guidance |
| [shared-host.cordis.yml](../shared-host.cordis.yml) | 显式候选Host组合；仅共享登记模式使用，不修改现役profile或替用户启动服务 |

GUI线程不得阻塞socket/子进程/netstat探测；进程缓存的UI/package变更需要完整重启Houdini。
前端Job所有权独立于launcher的UI状态，窗口关闭清理与launcher reload不丢失；Houdini退出回收自有前端及npx子孙。
启动器将Popen直接发布给本次attempt；异步取消按该对象匹配Job，迟到/重复取消不会停止后续启动。
普通启动对外部Bridge/Host端口占用仅报告冲突；显式强制Repair的窄范围核验例外见[安装合同](setup.md)。真实父/子/孙、reload、启动闸失败和外部进程隔离见
[前端生命周期回归](../tools/tests/dsh-frontend-lifetime.test.py)。此发行生命周期限Windows。
python3.11libs是目录名，通过PYTHONPATH共享纯Python实现，支持矩阵以兼容清单为准。

## 视觉、追踪和开发工具

视频教程解析由[video skill](../skills/houdini-video-tutorial/SKILL.md)组织，
[video_tutorial.py](../skills/houdini-video-tutorial/scripts/video_tutorial.py)在普通宿主进程中执行
  本地媒体准备、授权云转录、全片均匀粗扫/局部重看和结果校验，不经 Bridge、不调用 HOM。
帧索引保留实际 PTS 和播放时间轴起点；缩略图联系表与按显式区域比较的像素变化候选用于导航，
候选保留前后原图、阈值、比较模式和时间区间；可选择原图区域先裁切再缩放，不做自动语义或操作识别。
局部 `context` 汇集 hash 绑定的图像与转录，`check-notes` 校验 agent 填写的状态/操作记录，
只提供引用和结构验证，不证明语义真实性，不执行其中内容，也不据此授权工程修改。
同脚本的index-init/check-index维护来源绑定的章节/多时间段模块索引；read-transcript分页原文，
read-index按模块或section分页读取原文和既有notes引用，固定跨页索引版本；容器与视频跨度分别校验。
检查依赖、证据失效和预算，不自动划分语义或认证工程完成。
同脚本notes-init生成schema-2草稿或显式迁移旧notes，记录视频对象/网络/面板上下文、逐项事实引用、
跨包修正和参考图；index-link追加到新索引版本。query-notes按模块/对象/上下文/时间/字段查询，
保留冲突与历史；final视图只汇总作者声明，不自动选最新值。review-packet从已校验原帧生成局部观察入口，
export-brief派生资料交接，不维护第二份事实源。回归仍在tools/tests/video-tutorial.test.py。
索引查询的SHA与context校验在单次命令内去重，文件身份/大小/时间变化则拒绝；成功返回前每个依赖
再做一次独立SHA核验，防止同大小且保留mtime的新内容绑定旧摘要。失败后释放作用域，下一次命令重新验证。
该优化不提供跨命令新鲜度保证，也不把多文件读取当成文件系统原子快照。
ASR按本次片段选择和请求/重试预算推进，失败/未知片默认延后，不阻断未提交片；重试另需明确授权。
上传只使用逐片校验过的同一份bytes；现有日志缺原模型配置时不猜补，历史格式与原始尝试记录保留。
依赖宿主 Python、FFmpeg、SiliconFlow 凭据及当前模型的原生图像输入能力；注册 skill 不会安装依赖。
原视频、切片、转录及画面依据保存在仓库外任务目录，不进入包或 Trace 来源目录。
输入目前为本地视频，脚本不下载链接、不做语义识图，也不自动复现工程或更新生产知识。

教程复现按阶段选择领域 workflow；[COP skill](../skills/houdini-cop-workflow/SKILL.md)独立维护
Copernicus 图层/端口/关系、缓存和纹理交付，通过 [src/skill.ts](../src/skill.ts) 注册。
正文与参考按需读取，不扩充默认 guidance；SOP 源几何与 Solaris 材质消费仍由各自 workflow 负责。
图层工具实现独立在 `dsh_cop_contracts.py`，skill 只组织调用；版本与行为门见其
[验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)。

图片由Bridge按请求关联产图事实，经Host送入DSH原生附件存储和多模态工具结果，不复制到工作区media目录、不调用独立识图工具。附件传递不是语义验证，当前模型须实际查看图像。
正式渲染、预览服务和用户viewport分别管理，不能通过用户视口状态选择交付目标。
Trace记录动词ledger、rawUsage、Gate、transaction与execution观察；Host在原生metadata保留返回事实，
大结果保存到workspace的.dsh-houdini-results后才精简模型文本。该目录是工具返回副本，不是HIP内容输出。
失败/警告/unsupported/恢复错误、媒体路径和权限提示保留；未知结果可通过已提供的result_ref按字段读取。
页面信息架构、内容来源与历史快照同步规则见[Houdini Trace设计](houdini-trace-design.md)。
该文档区分实际请求System/schema/usage、上下文事件与当前构建来源目录；逐段运行provenance和最终messages可见集合尚未提供。

| 工具 | 长期职责 |
|---|---|
| [catalog-lib.mjs](../tools/catalog-lib.mjs)、[gen-client-catalog.mjs](../tools/gen-client-catalog.mjs) | 词表解析与Host/client生成 |
| [gen-trace-client.mjs](../tools/gen-trace-client.mjs) | 同源提取guidance/preset/注册技能与资源，嵌入手写Trace组件、样式及evidence-helpers副作用分类/采用统计函数；--check只读漂移验证 |
| [gen-web-polyfills.mjs](../tools/gen-web-polyfills.mjs) | 从锁定core-js生成Chrome 108兼容资产与许可证；web-polyfills与双版本Qt导航回归验证 |
| [gen-node-card-docs.mjs](../tools/gen-node-card-docs.mjs) | JSON节点卡→文档，严格schema与漂移检查 |
| [normalized-trace-steps.mjs](../tools/normalized-trace-steps.mjs)、[trace-session-lib.mjs](../tools/trace-session-lib.mjs) | 多帧zstd/回放去重、调用结果时序归一；逐请求usage去重及字段算术、逐轮错误/目标变更/压缩事件提取 |
| [trace-report.mjs](../tools/trace-report.mjs) | 独立可读HTML目录与时间线 |
| [trace evidence extractor](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[evidence helpers](../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs) | 确定性调用/安全/视觉/证据提取 |
| [run-node-tests.mjs](../tools/run-node-tests.mjs)、[prune-retired-build.mjs](../tools/prune-retired-build.mjs) | 回归发现与退役构建文件清理 |
| [build-release.py](../tools/build-release.py)、[finalize-release.py](../tools/finalize-release.py)、[release-sign.mjs](../tools/release-sign.mjs) | 冻结npm依赖/组装与隔离签名分开、文件/许可证清单及候选隔离；不发布Release |
| [prepare-managed-profile.mjs](../tools/prepare-managed-profile.mjs) | 使用锁定DSH的正式API初始化隔离profile，复制preset并绑定本Houdini的动态Bridge端口；无包管理器 |
| [run-deployment-tests.py](../tools/run-deployment-tests.py) | 离线安装故障与H21/H22隔离矩阵；真实包RPC入口见[部署测试](../tools/tests/dsh-deployment-e2e.test.py) |
| [houdini_test_environment.py](../tools/houdini_test_environment.py) | 部署/GUI测试及随包作者检查器共用的偏好、包目录、Python/Qt/DSH环境隔离与厂商bin启动目录；不改变用户进程环境 |
| [isolated-houdini-check.py](../tools/isolated-houdini-check.py) | 可信构建脚本在新hython场景中的cook/cache/ROP检查；复用受限worker、Bridge与ownership，保留输入/结果/产物证据，不加载live HIP |
| [camera-karma-smoke.py](../tools/camera-karma-smoke.py)、[camera-opengl-smoke.py](../tools/camera-opengl-smoke.py) | 隔离真实renderer/GUI验收入口，不代替语义识图 |

评测工具与schema见[评测设计](benchmark-design.md)。tools/prototypes、一次性probe及tools/out
不是生产API，不把其试验方案提升为现役功能；测试入口见[开发维护](development.md)。
