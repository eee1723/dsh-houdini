# DSH 与插件版本适配

插件是官方DSH Desktop的标准bundle，使用宿主原生会话、模型、任务与文件权限。0.1.7精确面向 **0.2.2-rc.1**；旧版0.1.6仍使用其发行包内声明的rc.3/rc.5，不自动升级既有用户。新版本按下述资格流程核对，不以浮动npm标签推断兼容。当前支持源为[兼容清单](../dsh-runtime-compatibility.json)，开发依赖锁为[package-lock](../package-lock.json)；候选验证、正式发布和用户已加载分别表达，地址以[安装说明](setup.md)为准。

## 宿主所有权与数据兼容边界

产品入口见[架构](architecture.md#目标产品形态)，职责与替代方案选择见[开发规范](development.md#插件职责与方案选择)。插件不自带另一套 DSH/Node、Qt 聊天窗口、账户系统或会话数据库；官方 Desktop 自行管理其更新、登录和默认模式。

| 事实 | 所有者与处理方式 |
|---|---|
| 会话创建项目、历史日志位置与工作区归属 | DSH 原生 Session/workspace；不改变 header 字段原意 |
| 当前文件操作目录 | DSH workingDirectory；原授权项目内可使用原生 cd，不因此扩大写权限或更改既有 shell |
| Houdini 实例、HIP 与工程输出目录 | Bridge 真实回执和插件现有投影；Save As 不移动聊天历史 |
| 节点修改范围 | 原 session 创建身份与可信保存点恢复；选择现场不授予 foreign 修改权限 |
| 安装与依赖 | Desktop 插件管理负责 Node 侧；本端安装器只部署 Houdini helper/Package |
| 模式与界面 | 增量注册 Houdini，其他模式和用户默认选择保持；领域控件按当前会话 preset 显示 |

[官方工作目录合同](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/docs/subsystems/working-directory.md)区分原始项目与当前目录。[插件实践](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/preset/agent-preset/skills/cordis-plugin-development/references/practices.md)要求考虑其他插件和版本的读取行为。普通插件数据从既有执行事件派生，或写入插件命名空间，不新增核心域语义。

旧适配版曾更新 SessionHeader.cwd 而保留旧日志目录；这些共享记录不属于官方读取合同。当前插件不再生成该状态，也不自动改头、移动日志或合并旧库。已有记录的恢复必须另行按明确范围保留原值、核对旧读取器、附件/详情引用和工作区归属；处置缺口只维护于[交接](handoff.md)。

## 两端接入与版本选择

[生成器](../tools/gen-agent-presets.mjs)只插入 Houdini preset、根客户端与现场服务；根客户端负责界面注册，preset 内提供工具与领域上下文。安装的 Node 插件目录与 Houdini helper 目录可以不同；登记目录限定发现范围，实际操作仍核对 executor、runtime、scene epoch 和执行合同。

[Desktop 接入](../src/desktop-integration.ts)在插件数据目录发布本机描述符，固定通道只接收菜单打开意图、状态和启动回执，不暴露通用 Remote、代码执行或宿主 owner 凭据。[菜单客户端](../houdini/python3.11libs/dsh_desktop_client.py)在 worker 内发现和认证；主线程只采集现场和加载 Bridge。前端收到意图后使用原生工作区/会话导航，实际选中后才确认消费；切换模式不取消已提交的执行。

插件通过 engines.dsh 与实际 peer 合同声明支持范围，由官方加载器核对。[原生兼容检查](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/packages/boot/app-boot/src/plugin-compatibility.ts)之外，还需验证 Houdini helper 的当次执行合同。插件不自动升级/降级 Desktop 或覆盖其内置包。

跨不兼容宿主升级时，先在旧Desktop停用Houdini插件，再沿官方入口升级宿主，随后在原生插件管理更新到匹配的插件发行版并启用；不卸载会话或移除helper，也不添加版本豁免。匹配插件尚未正式可用时，现用用户继续原组合。原生CLI添加包可能直接选择启用，不能套用安装UI的默认停用语义；自动化迁移须通过公开管理API明确停用再换宿主。

插件自己的Zod依赖独立固定版本，源码也不使用全局override重写官方包的精确依赖。两份依赖按各自包根解析；升级后需核对实际官方组合能读取插件的投影schema。受支持宿主仅调用schema.parse，却在ProjectionDefinition声明完整Zod链式API；[投影注册入口](../src/executor-identity-projection.ts)只在这两个schema字段隔离跨版本TypeScript类型，状态、事件及视图仍受类型检查，运行时保留原Zod对象及完整校验。公开声明收窄为实际解析协议后移除该类型边界，不加运行时适配器或扩大编译内存。生产依赖审计与包含开发宿主的全依赖审计分开解释；宿主公告沿官方修复版本验证，不通过插件替换其共享库。

## DSH耦合点与升级维护

| 边界 | 唯一实现与验证入口 |
|---|---|
| bundle/preset 与工具 scope | [生成器](../tools/gen-agent-presets.mjs)、[preset 回归](../tools/tests/dsh-preset-parity.test.mjs)、[真实官方组合](../tools/tests/dsh-host-smoke.test.py) |
| 本机接入、启动及导航 | [Desktop 服务](../src/desktop-integration.ts)、[通道反例](../tools/tests/desktop-integration.test.mjs)、[原生菜单检查](../tools/tests/dsh-desktop-client.test.py)、[真实页面](../tools/tests/dsh-client-navigation.mjs) |
| 原生历史与 HIP 观察 | [保存观察](../src/scene-recovery.ts)、[Save As 回归](../tools/tests/scene-directory-follow.test.mjs)、[目标路由](../tools/tests/executor-routing.test.mjs) |
| 工具结果、jobs 与上下文 | [DSH 适配](../src/dsh-adapter.ts)、[live jobs](../src/live-jobs.ts)、[结果回归](../tools/tests/dsh-adapter.test.mjs)、真实 Host/Bridge 组合 |
| Bridge 与领域执行 | [执行契约](execution-contract.md)、[开发维护](development.md#修改与验证)中的隔离 H21/H22 检查 |

开发验证使用[官方宿主准备器](../tools/prepare-dsh-runtime.mjs)，只安装未修改的精确官方包，不应用核心补丁。运行时缓存不属于用户发行物。工作区、账户、网络、通知等通用问题先核对官方版本和公开接口，再按开发规范比较解决方案，不能恢复整套私有核心差异作为默认修复。

后台完成的通知与唤醒完全由原生tool-jobs处理，包括quiet、唤醒预算及模型调用job_kill后的通知抑制。插件不在settled回调自行followup。取消请求不证明HOM已停止；需要结果时用job_output等待，观察中断后用原request_ref恢复。Bridge结果生产者通过公开appendPluginRecord把轻量canonical写入同一Session的plugin:dsh-houdini/execution；通用job_output不再被复制或覆盖，卸载/重载自然遵守原工具生命周期。原生/嵌套工具结果与该事实记录共用一个解码器，记录不进入模型消息面。

选择原生插件记录是因为直接工具的output.presentationMeta不能扩展通用job_output，post-execute也没有meta入口；复制定义会滞留旧execute，反复监听注册只是扩大维护面。窄上游的生产者元数据扩展可作为未来替代，核心补丁则破坏标准宿主边界。当前只使用公开插件命名空间，不新增Session核心事件或第二账本；未知读取器按ignorable保留/跳过，格式迁移可能按宿主合同丢弃该插件状态，因此恢复仍依赖原请求及原值地址。官方出现等价生产者合同后替换写入入口，保留历史解码，不恢复定义覆盖。

媒体与转录共用公开subprocess服务的进程树生命周期，不维护taskkill/PID探测或另一套转录进程管理。插件只负责本次调用的JSON协议、输出限额与工作锁；服务不能证明整树退出时保留锁并返回未确认。独立GUI Houdini需要在Desktop退出后继续运行，因此保持独立启动，仅复用官方环境清理。隔离hython的Python监督器另有内存预算和取消回执合同，不能用GUI或媒体的生命周期替代。该方案无需核心补丁或新宿主依赖，维护范围限定于领域输入/输出；官方合同变更时沿精确版本资格流程核对。

## 模型提供方与账户验收

账户与模型由宿主及用户选择的提供方管理。当前可选社区模型插件为 **dsh-codex-subscription@3.1.8**，通过Codex OAuth及其账号目录提供能力；它不是本仓库的发行组成，不随Houdini安装或升级，也不从其他订阅插件迁移授权。

本仓库不为第三方模型插件维护私有认证、兼容补丁、版本豁免或宿主升级。安装和启停使用官方插件管理，先由其检查兼容声明，再核对实际Desktop加载、Houdini与其他模式以及实际依赖解析，不能仅依据第三方文档或安装退出码。

真实登录、目录、图片和模型请求分别验收。账号连接或目录缓存不代表推理成功，具体型号只以账户实际返回为准；不硬编码添加型号，也不将模型可见当作语音、生图或其他API授权。未完成的用户验收只维护于[交接](handoff.md#h-06-官方dsh共存与插件边界)。

## 网络与窗口等宿主能力

Windows窗口置顶是[插件窄适配](../src/desktop-window.ts)，仅处理Host所属Desktop父窗口的模式内选择和原层级恢复；Koffi作为已资格化宿主的peer提供，不引入新原生构建许可步骤或替换内置依赖。公开窗口接口可用后替换该OS适配。窗口身份不明确、浏览器入口或不支持平台不会猜测操作其他窗口。

官方rc.3的Node Host未把Windows系统代理/PAC/WPAD转换为模型和子进程统一网络策略。当前公开http-proxy模块按进程安装显式环境策略，不能表达每个URL的PAC路由；Electron更新器网络不等价于Node请求。现役产品复用显式代理环境，不从Houdini插件安装进程级代理或改写全局环境。旧适配版自动继承系统代理的用户能力尚无等价交付。

窄上游方案应由Desktop启动阶段建立统一网络策略，显式用户环境优先，再按每个URL解析系统代理/PAC；公开给Host请求和子进程一致的路由/继承合同，并处理NO_PROXY、直连、取消、重连及代理凭据的安全投影。验证用自有HTTP/HTTPS代理与PAC夹具，分别检查模型流、下载、转录子进程和其他模式；不自动读取或导出用户系统配置。Houdini插件只消费该合同，官方能力可用后移除相应缺口，不维护第二套网络平台。

旧工作台的通用网络探测面板不在Houdini里重建。当前保留本端离线接入报告、订阅目录刷新和原生模型实际错误；主动网络诊断须针对用户选择的服务与明确范围，不扫描全部账户或读取密钥。统一网络诊断应消费上述宿主网络合同，缺少时如实说明范围，不能用离线报告冒充模型出站网络已验证。

## 新 DSH 版本的资格流程

核对官方发行、npm 标签、Desktop实际更新通道与可获取包，在自有数据根完成候选资格验证后，再更新兼容声明和锁文件；GitHub tag不代表用户的Desktop已收到对应安装包。构建后验证标准模式仍为原默认、其他 preset 可用、Houdini 工具只在对应 scope、根客户端只有一份。启动/导航变化必须在实际页面核对所选任务、工作区、preset 与现场；配置存在或局部 RPC 成功不能代替消费方状态。

涉及文件/持久化时核对未修改官方读取器的重开与原值。涉及执行边界才选择必要的 H21/H22 HOM 回归，不因移除 Qt 壳机械重跑全部模型质量评测。用户现场实际加载与源码验证分开报告。

### 0.2.2 接口边界

[官方0.2.2-rc.1](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-rc.1)的合同由当前插件直接消费，不保留旧disposer/新handle或旧工具mode的猜测分支；旧用户沿原插件发行版使用。实际资格范围由兼容清单维护，剩余验收只进[交接](handoff.md#h-06-官方dsh共存与插件边界)。

| 官方合同 | 插件消费与验证 |
|---|---|
| [工具按步骤准入](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.1/packages/core/tools/src/index.ts)通过resolve生成本步集合，executable决定实际可执行定义 | 现场上下文消费本步toolSet；注册存在不等于获准，本步禁用时移除先前自身上下文。原生与PTC使用宿主同一步选择 |
| [投影注册](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.1/packages/session/session-projection/README.md)须await取得handle，再暴露同步消费者；按key读取已弃用 | executor-host在启动阶段持有私有handle，控制器、上下文与前端通过所属服务读状态；不加延时轮询或再建历史扫描器 |
| [提示词组装](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-rc.1/packages/core/system-prompt/src/index.ts)区分呈现与工具声明，Agent在本步固定模型 | scene/execution/vision消费捕获的modelSelection，诊断组装才读agent.model.current()；保留宿主覆盖、取消及PTC作用域，不在agent/request改模型 |
| 原生/PTC执行插件与配置overlay、run_code取消分类、官方组合包导出发生变化 | 更新隔离Host/原生与嵌套回执夹具和取消断言；生产插件不接管宿主PTC bootstrap或组合包安装 |
| Cordis 4.1.0、Schemastery 3.19.0及Node最低24.9 | 按实际官方发行组合验证依赖单例、根客户端、热重载和原生安装；不从插件升级共享依赖或替换Desktop运行时 |

第三方插件更新与失败恢复、后台完成通知、原始工具结果与嵌套调用展示继续消费宿主现有入口；新增统计、历史复制、文件预览和自动化也不在Houdini内重建。插件保留Bridge串行执行、现场身份、HOM权限、领域检查和不可变原值归档；官方通用结果展示不替代这些领域事实。新版Web Fetch对内网地址的策略变化与Windows沙箱修复须按实际部署复核，不能将它们写成插件网络或权限问题已经解决。

## 正式发行单元与发布门

标准发布物是符合 npm 包格式的 `.tgz` 插件包及其 Houdini helper/领域资源，使用[发布构建器](../tools/build-release.py)；包格式不表示已发布到 npm。媒体功能保留插件私有FFmpeg/ffprobe、运行依赖、全部许可及媒体库对应源码；LLVM完整项目采用固定来源引用，范围见[开发规范](development.md#受影响能力的验证)。用户运行所需文件均随包提供，按[安装](setup.md#教程视频与转录设置)定位；不捆绑另一套 DSH 会话或运行时。构建失败不得以缺资源的包宣称离线能力齐全。

正式交付须核对 Desktop 安装/启停、其他模式保持、两条完整用户入口、H21/H22 helper 身份与重开。main push、tag、Draft 或源码 build 不代表已安装和正式发布；尚欠项见[交接](handoff.md)。

源码CI与手动候选构建均不执行Release或npm发布；候选只作为测试输入。公开版本与安装地址以[安装说明](setup.md#普通安装)和实际可下载的正式Release资产为准，未发布的源码改动不自动成为更新。测试者使用维护者提供的完整tgz，历史独立工作台包不属于本次标准插件交付。

### 第三方插件更新入口

Node侧插件的安装、启停、卸载、升级与失败恢复只使用Desktop原生插件管理。Houdini工程菜单通过公开的`pluginNavigation.openBundle('dsh-houdini')`打开同一页面。DSH 0.2.2-rc.1的registry原生更新要求：当前profile中可管理的第三方包、有效semver版本，以及按自身包名记录的registry来源；Host由这些事实产生`updatable`，客户端只为符合条件的包显示版本区。GitHub tgz URL、本地文件和源码链接不取得这一资格，`homepage`／`repository`也不是更新来源。安装页再次添加已有包名会拒绝；新的tgz URL可能走普通安装路径，不能据此承诺`updateBundle`的旧版恢复保证。npm发布不会自动转换已有依赖来源。

registry中的精确版本、dist-tag和宿主兼容声明必须实际公开可查；裸包名查询latest不能证明它支持当前DSH。URL／文件来源可通过官方管理流程明确替换；迁移为registry来源后须核对真实依赖来源、版本、启用状态与页面资格。安装与更新入口见[安装说明](setup.md#connection--support连接与维护)，未完成的具体组合只进[交接](handoff.md#h-01-标准插件发布与用户加载)。

官方版本区和管理器已经覆盖包名安装的版本选择、更新及恢复，插件只需导航到该入口，并准确交付可获取版本。自制更新器会重复版本筛选和恢复逻辑，不能改变宿主记录的URL来源；为本次来源差异修改核心也增加共享profile影响与维护成本。采用公开管理流程是当前最小充分方案；只有确认官方流程不能满足必要的来源迁移时，才比较窄上游改进，并以官方合同补齐作为临时适配的退出条件，不恢复插件内Release查询、更新缓存或自制安装弹窗。

原生更新验收须实际打开详情、检查版本、点击更新和确认，并核对结果、来源和启用状态；直接调用`listVersions`／`updateBundle`只能证明API机制，不能证明按钮可达。URL／文件来源无版本区、重复包名的添加拒绝、新URL换包和来源迁移须分别观察，方法见[开发维护](development.md#受影响能力的验证)。公开导航不可用时仍从原生「插件」页进入。Houdini helper在插件加载或明确新建／打开时准备；运行观察只读，缺失或失败通过已有修复入口处理。实际加载版本与重开要求由插件判断，因为Desktop不知道进程内Python模块身份。

[组件观察](../src/component-installation.ts)异步复用安装器只读预览与既有 Package，不新建活动版本指针、不复制内容身份算法；文件检查不阻塞现场 health。Python 的 `loaded_helper()` 在模块首次加载捕获不可变目录与包版本，health/登记传递同源快照，磁盘更新不能改变运行中身份。安装事实与加载事实分别返回：当前进程内容正确但Package缺失时提示安装修复，不报告整条链已就绪；磁盘未知或来自其他安装位置保持未知。只有同一安装位置、预期Package已准备好且已加载身份不同才提示重开。执行准入与界面共同使用[合同判定](../src/component-compatibility.ts)，构建身份差异本身不扩大执行门槛。反例入口为[工程菜单](../tools/tests/executor-picker.test.mjs)、[真实页面](../tools/tests/dsh-client-navigation.mjs)及[加载身份](../tools/tests/dsh-deployment.test.py)。
