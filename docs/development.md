# 开发与文档维护规范

入口见[文档索引](README.md)和[系统架构](architecture.md)。这里维护开发方法、生成规则和验证入口；尚欠动作只放[交接](handoff.md)。

## 设计原则

系统负责让模型获得准确信息、充分操作能力、真实执行反馈、可观察结果和清楚的错误。模型负责理解需求、选择方法、组织步骤和判断效果。领域知识按任务读取，执行接口只落实平台与操作合同。

已完成的功能、工具数量、历史测试和目录结构都可以调整。新增检查应解决实际接口条件或已观察到的失败；模型的一次遗漏或方法选择错误不应成为永久准入门槛。删除策略时同步删除只证明该策略的断言。

继续使用 DSH 的会话、模型、通用 Agent 循环、上下文组合、压缩和原生工具能力。插件维护 Houdini 适配；不要在插件重建一套通用 Agent 状态机或提示词历史。

## 插件职责与方案选择

目标交互唯一见[架构](architecture.md#目标产品形态)。以下边界用于每次改动的设计判断，不因现有工作台或补丁已实现而放宽。

| 责任方 | 应维护的内容 |
|---|---|
| DSH宿主 | 会话与持久化、模型/账户/凭据、通用Agent循环、压缩、任务/jobs、工作区与文件授权、通用界面及宿主升级 |
| Houdini插件 | Houdini preset、工具与领域skill、真实现场与执行事实、明确绑定、模式内界面、Houdini启动/打开意图及与宿主的接入 |
| Houdini侧helper/Bridge | 原生菜单与Package、主线程队列、HOM执行、节点归属、场景回执、连接身份及版本兼容 |
| 插件交付 | 本插件与Houdini侧组件的安装/更新/卸载、DSH及Houdini兼容范围；不接管官方Desktop的安装、登录或运行时更新 |

需要重做DSH现有能力或修改其核心时，先在实际支持版本中核对公开接口，再比较复用现有能力、插件内窄扩展、最小上游改进与核心补丁。变更说明须写清用户需要什么、现有接口为何不够、替代方案的实际限制、所选方案的宿主/数据影响与维护成本，以及临时实现的移除条件。没有证据时保留缺口，不把“当前代码能跑”或已有测试数量当作最优方案依据；不为比较另建长期决策账本。现役设计就地更新，未完成动作只放handoff。

重构按用户能力核对旧入口、替代实现和实际消费方，而不以旧文件已删除证明功能完成；未保留的能力须明确是产品取舍还是待补缺口。检查实际Desktop打包的依赖来源和版本，不能把开发锁文件当作安装事实。通用模型/授权扩展单独成为标准插件；进程级代理、默认模型和共享解析不由Houdini功能暗中接管。对暂时没有公开接口的窄适配，记录操作对象、原值恢复和官方接口出现后的退出条件。

Houdini交互控件按当前选中会话的原生preset投影显示；切换到其他模式不出现现场选择等领域控件，不改变其工具、模型或默认模式。根客户端可为注册扩展和历史回执加载；最小后台接入可等待菜单唤起，UI隐藏不取消已经提交的Houdini任务。无需另造Qt聊天窗口或浏览器壳；确需Houdini原生对话框时保留窄调用，不将其扩展为另一套应用。

## DSH宿主不受影响的开发纪律

插件的开发、安装、启动、更新、修复和卸载必须保持官方DSH Desktop的启动、工作区、历史会话、模型设置及其他插件正常可用。标准插件使用宿主原生会话和配置服务；永久分开用户历史不是产品要求。职责与兼容边界见[DSH适配](dsh-update-compatibility.md#宿主所有权与数据兼容边界)。

- 开发和自动化测试必须显式使用自有DSH_HOME、profile、缓存及浏览器数据；源码安装、快捷方式、修复和子进程共用同一个确定的数据根。检查路径与执行环境从同源参数派生，不回落用户默认`~/.dsh`。只换profile不隔离会话与storage；不得设置用户或系统全局DSH_HOME。
- 官方安装目录、`profiles/desktop`、home级补丁和共享依赖图由宿主管理。通用插件只贡献自身工具、Houdini preset和界面扩展，不覆盖默认模型、关闭其他模式或接管插件管理。插件不维护独立应用组合。
- 保持DSH已有字段、事件和存储版本的原意；`SessionHeader.cwd`的创建项目身份、当前文件目录、Houdini现场/HIP与写入授权分别处理。不能保留格式号而改变官方读取器依赖的含义，也不能将自定义核心状态写进共享会话或workspace域。
- 通用能力优先使用已核对的公开合同；缺口通过上游改进或明确的产品取舍解决。必要的过渡核心补丁只能随私有运行时和独立数据根交付；不得要求用户给官方Desktop打补丁。数据导入、迁移和旧记录修复须单独明确范围并保留可恢复原值，不自动合并、链接或同步两套活动历史。
- 涉及启动、依赖、preset、存储或目录语义的改动，先列明受影响的读写边界，再在自有fixture中核对官方包读取、正常工作区创建、插件启停及原有模式保持。共享格式还须核对重开与升级/回退的实际消费者；适配版自行读回和相同版本号不能代替兼容证据。测试不使用用户live数据。

未完成的用户入口、旧数据和发布验收只维护于[当前交接](handoff.md#h-06-官方dsh共存与插件边界)。纯文档修改运行文档门；不为这项纪律机械扩大HOM或模型评测。

## 单一维护源

根README面向插件使用者，围绕产品定位、整体能力、架构概要、安装、用法与文档入口组织。兼容范围和实际使用边界可以摘要说明，详细合同链接到对应维护源；个人测试安排、等待实测或发布的开发状态、验收流水与交接事项留在handoff及专门维护文档，不放进产品首页。

| 内容 | 维护位置 | 派生或验证入口 |
|---|---|---|
| Host 工具职责与参数 | [tool-catalog](../src/tool-catalog.ts)、[tools](../src/tools.ts) | gen-tool-docs 生成 docs 工具表；工具注册与前端共用目录 |
| Houdini 动词签名、执行版本 | [工具设计](tool-design.md)，实现同步 helpers/Bridge | gen-verb-contract 生成 Host 执行合同；verb-contract 回归 |
| 动词按需结构与例子 | [verb-operation-contracts.json](../houdini/verb-operation-contracts.json)，签名仍来自运行函数 | gen-verb-contract-docs生成[结构合同](verb-contracts.md)，verb_help按需返回；说明不参与执行校验 |
| 工程图像目录角色 | [project-layout.json](../houdini/project-layout.json)，Host/Houdini同源读取 | gen-project-layout-docs生成[工程文件目录表](project-files.md)，构建与docs:check校验同步 |
| 节点操作知识 | [node-operation-contracts.json](../houdini/node-operation-contracts.json) | gen-node-card-docs 生成[节点卡](node-operation-cards.md)；node-knowledge 验实际参数和几何 |
| DSH 组合与角色 | 精确 DSH 标准组合及 [Houdini persona](../presets/houdini/persona.md) | [gen-agent-presets](../tools/gen-agent-presets.mjs)生成唯一 Houdini patch |
| 运行版本与安装组合 | [兼容清单](../dsh-runtime-compatibility.json)、[runtime](../deployment/runtime.json)、[部署锁文件](../deployment/package-lock.json) | 安装、启动、修复共用 preferred 精确组合 |
| 执行与恢复事实 | Houdini 实际执行/结果模块 | [执行契约](execution-contract.md)；Host 和前端消费 Bridge 回执 |
| 领域方法 | 对应 [skills](../skills/) 的入口和 references | 按需知识；docs 链接原文，不重复 recipe |
| Trace 解析与展示 | [Trace 设计](houdini-trace-design.md)、client/ | 使用真实请求和工具记录；按需加载诊断 |
| 故障报告 | [诊断包合同](support-reports.md)、DSH原生会话读取、唯一Python收集器 | 精确会话/竞态、脱敏/恶意ZIP及官方页面下载；不把诊断采集当作现场恢复 |
| 目标选择与工作状态 | [选择边界](multi-instance.md)、[绑定投影](../src/executor-identity-projection.ts) | [明确选择与历史隔离](../tools/tests/executor-routing.test.mjs)、[工程组件](../tools/tests/executor-picker.test.mjs)、[原运行实例查询](../tools/tests/tool-target-selection.test.mjs)、[双进程锁](../tools/tests/dsh-runtime-occupancy.test.py) |
| 开发评测 | [评测原则](product-modeling-evaluation.md)、evaluation/、tools/ | 公开题面与评审答案隔离；生产面不读取评审材料 |

新增长期生产模块必须加入架构代码地图。新增文档必须加入索引，说明它的职责及源码、验证入口。

## 构建与生成

Desktop正常退出验收使用已配置自有模型、实际显示的主窗口，不能仅在欢迎页背后的隐藏页面调用RPC。区分退出检查、原生确认与Host终止；透明诊断不得改写原生确认结果，只有实际确认后进程正常结束才算退出通过。自动化操作只针对已证明属于自有进程的返回窗口；可用持有原内核句柄的Popen存活事实复核身份，不因受限令牌下取不到GetProcessTimes就推断PID复用。Desktop退出后须检查原Houdini出生身份仍存活，再核对冷重开后的原会话与原现场；强制清理自有测试进程不算正常退出。入口为[原生窗口验证](../tools/tests/dsh-desktop-window.test.py)。

工程标识的[定向回归](../tools/tests/workbench-project.test.mjs)核对实际绑定投影、执行/文件事实与状态，不把历史标识解释为在线状态。[真实组件交互](../tools/tests/executor-picker-react-browser.mjs)接受精确prepared runtime根目录，读取同版静态React/Menu SDK，在独立浏览器中核对鼠标选择/取消、七种状态、宽窄暗色和隐藏撤销就绪；不修改运行缓存、不连接模型或用户现场。

注册界面slot前核对精确宿主中的实际消费点、props及list/single类型；不以更高order抢占已有原生single操作。空对话变为有内容对话时分别确认入口仍可见，注册成功不能代替页面消费。

窗口置顶使用[状态机回归](../tools/tests/desktop-window.test.mjs)、[客户端租用](../tools/tests/window-pin-client.test.mjs)和[原生Desktop消费检查](../tools/tests/dsh-window-pin-native.test.py)，核对Houdini/普通模式、空对话/页头、renderer替换、卸载与原层级恢复。只对自有Desktop进程做OS检查；不通过通用Remote接受PID或窗口句柄。第三方模型插件不由本仓库构建或维护。选用固定版本时须分别核对发布包来源、官方CLI安装、真实Desktop加载、其他模式与依赖解析；真实账户授权、模型目录及真实推理另行报告，不能以文档、模拟令牌、按钮出现或隔离加载替代。

原生Houdini冷启动使用独立的240秒验收预算，可用`--native-startup-timeout`显式指定；前端、RPC及其他等待预算不随之扩大，也不改产品的启动行为。`--profile-native-startup`为测试创建的原生进程启用[SideFX启动性能记录](https://www.sidefx.com/docs/houdini/ref/commandline.html)，将性能文件、GUI就绪／连接／实际前端选中时间及等待反馈留在隔离目录；最终结果必须同时核对完整断言、退出码与自有进程清理，不能用单条工具成功代替整条入口通过。

```powershell
npm install
npm run build
npm run docs:check
```

只用 npm。build 刷新节点卡、动词结构合同、Host动词合同、唯一Houdini preset、工具文档和节点交付客户端，再编译TypeScript。`lib/`、生成区、`presets/houdini/cordis.patch.yml`不手改。

角色在 persona.md 维护；生成组合继承所支持DSH的标准插件，仅增量注册Houdini，保留其他preset与用户默认选择。插件以 DSH 0.2 的 `bundle.patch` 装载配置：根级bare package `dsh-houdini`承载前端，preset内`dsh-houdini/agent`提供工具和原生context producer。DSH客户端模块图识别bare package，不能以preset scope或包子路径导入成功替代根客户端注册。客户端使用DSH的conversation/trajectory注册接口。

`docs:check` 只检查生成漂移、文档索引、模块覆盖和 Markdown 链接，不自动修文档。改动生成源后先 build，再检查最终一致性。

正式包由 `python tools/build-release.py --output <目录>` 构建；`--media-runtime`仅复用通过完整输入、构建来源与文件摘要核对的媒体资源。源码根保留`private`以防直接误发未构建源码，发行tarball去掉开发脚本与依赖并声明Windows x64。构建器输出同一包的`release-manifest.json`与`SHA256SUMS.txt`，自身不创建tag或Release。维护者在验证最终包、获得发布授权后，将该tgz及校验文件作为同一GitHub Release资产发布，再用正式HTTPS地址核对原生插件页的安装、启用与实际Houdini接入；下载地址不可由Draft、源码push或本地成功推断。npm包名分发需要单独的发布账户，不能用未发布包名替代GitHub完整包直链。

[Gateway心跳反例](../tools/tests/dsh-gateway-heartbeat-check.mjs)接收配套缓存根目录，使用真实loopback WebSocket并在写入边界注入大帧持续排空及停滞，检查排空期间不误断、排队Ping不增长、真正停滞仍退出、正常Pong与立即发包的反例。浏览器连接和原故障的现场复现分别判断；会话日志没有浏览器连接事件时，不能用同一Houdini运行身份或健康检查成功证明页面从未断线。

[权限恢复](../tools/tests/scene-recovery.test.mjs)验证同一保存点写前恢复、新目标不恢复、当前只读回执不抹除旧归属证据；[原工程保持](../tools/tests/scene-recovery-original.test.mjs)验证不自动load/clear/提问丢内容；[原生恢复](../tools/tests/dsh-scene-recovery.test.py)验证真实文件、节点基线、活跃作者与场景代际。真实加载后警告原文/有界投影由[警告边界](../tools/tests/load-warning.test.py)和[跨语言资源读取](../tools/tests/load-warning-resource.test.mjs)验证，不把日志摘要当跨版本兼容结论。

[已有工作区生命周期](../tools/tests/dsh-workspace-lifecycle-check.mjs)接受缓存根目录，核对预存文件的更新/重命名/删除、硬链接与目录联接的外部权限保持、显式保护、只读token、重复授权和撤销。[网页传输反例](../tools/tests/dsh-web-transport-check.mjs)验证公开CDN跳转、私网/凭据/降级拒绝、混合DNS答案、真实失败原因及代理凭据脱敏。开发缓存由官方精确版本和依赖锁准备，不编译或替换上游核心；客户端交付由官方插件管理器完成，不把源码测试组合当作正式安装。

## 修改与验证

标准宿主验证：先 npm run build 和 npm run docs:check，运行 [官方包边界](../tools/tests/official-host-package.test.mjs)、[本机接入反例](../tools/tests/desktop-integration.test.mjs)、[菜单线程/认证](../tools/tests/dsh-desktop-client.test.py)、[本端安装](../tools/tests/dsh-install-runtime.test.py)，再用 [真实官方组合](../tools/tests/dsh-host-smoke.test.py)及其 --browser-module 参数核对原生模式、页面所选任务、插件启停与意图消费。

启动接续使用[票据回归](../tools/tests/desktop-launch-recovery.test.mjs)核对两代宿主、真实票据、原生选择事件、提交前停止/提交后完成、无producer的明确继续、并发回执、身份暂不可用与安全清理；[OS边界](../tools/tests/desktop-process.test.mjs)核对Windows出生事实、进程退出、数据根别名互斥与崩溃释放；[Python交付](../tools/tests/dsh-connection-operation.test.py)核对真实HTTP断响应、凭据轮换后重新准入及原payload投递，不能只直接向Node POST来代替生产消费者。原生窗口[生命周期入口](../tools/tests/dsh-desktop-window.test.py)的--lifetime-hfs必须以同一进程出生事实、Bridge和原会话选中验证退出/重开，绑定实际包摘要；独立资料须覆盖首次Documents工作区并核对系统协议处理器，不把临时DSH_HOME等同于机器级设置隔离。

受控Bridge夹具验证协议与路由，不证明真实HOM；实际Houdini启动/接入须使用隔离偏好和自有进程，分别验证H21/H22，不连接用户live。真实入口另用`--helper-package`执行本端安装器并加载独立不可变helper目录，核对正常Package前置路径后仍接入；Host包根与helper物理目录不必相同，同Houdini进程模块来源和实际Bridge执行合同分别验证。

HIP网络路径改动用`dsh-launcher-preflight.test.py`与隔离H21/H22的`dsh-scene-context.test.py`，把文件存在与真实路径解析替换为立即失败的探针，检查入口、工程登记、metadata与实际Bridge回执均不依赖网络I/O；覆盖UNC正反斜线、共享根目录、中文空格和映射盘。`image-generation.test.mjs`同时核对字面目录投影、Host解析后的实际输出、工程根别名与子目录重定向拒绝。注入断网只证明调用边界，实际SMB读写、服务器权限与用户加载仍须用自有网络工程另验，不能用本地路径测试代替。

工程关联与空工作区改动用`workbench-association.test.mjs`核对同路径异工程、能力查询、UI回执、多窗口选择及目录提交失败；[保存目录回归](../tools/tests/scene-directory-follow.test.mjs)核对原生创建目录与历史日志位置保持。[真实Houdini入口](../tools/tests/dsh-desktop-live.test.py)覆盖H21/H22新建、打开和本端菜单，[共存重启](../tools/tests/dsh-desktop-coexistence.test.py)核对其他插件、默认模式、设置和持久会话，[正式包安装](../tools/tests/dsh-packaged-plugin-install.test.py)通过Desktop自带CLI在临时数据根安装最终tgz并检查实际运行与媒体资源。不连接用户live，不删除用户目录；后端及浏览器验证与原生Electron窗口验收分别报告。

按用户目标和实际问题选择修改范围。工具描述只讲能力和真实调用条件；persona 讲角色和知识路由；领域工作方法只放 skill；操作合同落在执行实现。同一事实不要复制到多层提示词。

验证与改动相称：先构建并运行直接受影响的回归。检查通过且没有新改动或未解问题时，不继续扩大测试。基线收口运行一次现有 Node 套件与文档门；日常无需每次全跑。

```powershell
# 单个受影响的 Node 回归
node tools/tests/verb-contract.test.mjs
# 完整 Node 回归（内部包含 build）
npm test
```

涉及 Houdini 执行内核时，使用隔离 hython 覆盖必要核心边界：

| 能力 | 验证入口 |
|---|---|
| Raw Gate | [纯词法反例](../tools/tests/dsh-code-analysis.test.py)、[dsh-bridge-raw-gate](../tools/tests/dsh-bridge-raw-gate.test.py)：内建值／标准库API来源、遮蔽／重绑定／成员覆写、HOM重导出与绑定方法分别核对 |
| 节点归属 | [dsh-node-ownership](../tools/tests/dsh-node-ownership.test.py) |
| 捕获失败与回滚 | [dsh-bridge-caught-failure](../tools/tests/dsh-bridge-caught-failure.test.py) |
| 创建失败清理 | [dsh-tab-create-failure](../tools/tests/dsh-tab-create-failure.test.py) |
| OBJ 父级 | [dsh-object-parenting](../tools/tests/dsh-object-parenting.test.py) |
| 场景、网络、渲染 | [dsh-scene-network-render-contract](../tools/tests/dsh-scene-network-render-contract.test.py) |
| 批量 SOP 构建 | [dsh-module-preflight](../tools/tests/dsh-module-preflight.test.py) |
| multiparm结构与通道恢复 | [dsh-multiparm-restoration](../tools/tests/dsh-multiparm-restoration.test.py) |

通过 [houdini_test_environment](../tools/houdini_test_environment.py) 创建临时偏好、空 package 环境和目标安装路径；启动目录使用指定安装的 bin。Python 通过 PYTHONPATH/测试入口兼容 H21/H22，不继承用户插件、Qt override 或模型凭据。隔离检查不连接 live，也不加载用户 HIP。部署运行器的纯 Python 检查由普通 CLI 解释器执行一次；显式hython只执行HOM与实际启动隔离检查，避免把Houdini运行成本混入普通进程／内存夹具。

领域改动选对应回归，例如 [node-knowledge](../tools/tests/dsh-node-knowledge.test.py)、[参数与绑定](../tools/tests/dsh-parameter-controls.test.py)、[控制恢复](../tools/tests/dsh-control-state-restoration.test.py)、[COP](../tools/tests/dsh-cop-contracts.test.py)。不机械把每个领域套件加到普通模块整理上。

功能回归验证真实接口和错误；GUI 验证页面及运行加载；模型任务评测验证自然采用与结果质量。三者按实际需要运行，结果不能相互替代。视觉验收区分文件与图像传输、显示、模型实际识图。

[图像请求组合](../tools/tests/dsh-image-consumption-fixture.mjs)以`node tools/tests/dsh-image-consumption-fixture.mjs <prepared-runtime> [output-root]`运行固定DSH Web标准preset、原生read_image及真实pi-ai适配器，由自建loopback provider捕获最终HTTP图片。它在同一会话调整并恢复原生requestImagePixelBudget，核对原参考/A/B均保留、请求变体与wire哈希一致、模型句柄尺寸、源文件/持久附件不变及无offload。受控响应不证明真实模型识图或token费用下降；比较像素和编码字节时分别记录格式变化，不把较小分辨率当成较小传输。记录实际Node/DSH/运行修复身份，标准preset通过不扩大为Houdini preset、GUI或正式发行验证。实际模型的预算对照仍沿下述授权试验入口。

任务拆分与完整源组件的方法改动，先用[skill审计](../skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs)、preset组合与下述`--context-loop`验证注册、资料路由和实际模型输入。自然采用另用同模型、同要求、同预算的独立工程对照：观察源组件的局部检查是否影响后续构建，再执行换源、改布局、局部细化或共享尺寸变化，检查最终消费者与修改范围；用另一类任务验证领域外适用性。源本来应为Box、共享连续表面和先代理后细化都是合法反例，不按节点数、截图数或技能关键词评分。审查需包含能推翻自报成功的情况，例如实际开口被封堵但模板未变、同包围范围的错误形状和局部遮挡；模板或生成公式通过不能升级为最终实体关系通过。trace的原生图片与显式读图记录通过nextToolStep定位观察返回后提交的下一动作，引用原时间线而不推断修改、因果或成功；并发中先提交后返回的动作不算后续决策。受控模型能取到技能不证明自主分治或质量提升，保留质量、返工及计算成本的实际证据，过程产物留会话/临时目录。

网络布局用[纯规划回归](../tools/tests/dsh-network-layout.test.py)核对宽支路、长链、分组、完整障碍与确定性，H21/H22的[handoff回归](../tools/tests/dsh-handoff-layout.test.py)核对原生盒、恢复及Subnet内外位置边界，并由原有公共输入／控制修改验证实际消费者。规划不自动迁移节点或修改引用；净距通过不代替用户界面和语义质量判断。

执行模块重构保持公开动词签名与结果合同；节点归属回归同时核对不可变快照、嵌套创建记录和作者作用域恢复，execution-runtime核对请求图片隔离及组件快照。HDA界面回归将故障注入实际实现模块，验证修复重载后公开导出与执行分派使用新函数，不能只改facade上的别名来模拟下游失败。真实GUI捕获夹具只调整自有临时窗口的显示顺序，不放宽生产捕获的遮挡/屏内要求。

默认能力还需验证实际组合。[HDA生命周期](../tools/tests/dsh-hda-lifecycle.test.py)在H21/H22将原生COP预览与普通源共同封装，核对公共参数、新实例几何、保存/锁定/解锁、失败Undo和完整内部identity；锁定嵌套定义不计作者工作量，但解锁内部后仍受同一工作量边界约束。foreign实例或后代不因组合测试获得豁免。这类检查不证明预览图像外观或任意大型HDA兼容。

原生USD退出问题用[reproduce-usd-exit](../tools/reproduce-usd-exit.py)在指定`--hython`中运行独立的导入、内存stage和LOP对照，可重复传版本路径并用`--repeat`检查复现率。每次使用新偏好/package目录和明确HFS，不加载用户HIP或DSH插件；保留脚本主体完成标记、真实退出码与stdout/stderr。主体完成但进程非零退出仍属异常；相同退出码不能证明同一根因，headless结果不能外推GUI行为。证据写到新临时目录，不修改系统崩溃报告或用户配置。

重复细节的代码生成方法在[SOP建模资料](../skills/houdini-sop-workflow/references/modeling-methods.md#重复规律与代码生成)维护。[重复布局检查](../tools/tests/dsh-repeated-layout.test.py)在隔离H21/H22通过Bridge执行随包示例，核对模板位置与ID、Sweep后的字符串属性、参数修改、空输出回滚和foreign边界。[VEX代码生成诊断](../tools/reproduce-vex-codegen.py)以`--hython <明确版本> --form both`在各自原生新进程对照展开语句与循环，保留源计算、下游计算和进程退出事实；展开形式可能崩溃，厂商修复后也可以成功，不把旧崩溃或字符数设为永久测试预期。默认`--form loop`。示例与诊断通过不代替真实模型采用、全部资产安全或GUI观察。

COP接入材质使用[dsh-cop-material-delivery](../tools/tests/dsh-cop-material-delivery.test.py)在新建隔离工程中验证曲面贴图、材质直接采样alpha、粗糙度控制、`$HIP/dsh-artifacts/textures`读回与同版本独立进程重开。完整纹理网络不以数值变化代替实际图片检查。跨版本节点/算法默认值可能不同，分别验证各版消费和重开，不默认像素一致。

SOP表面入口使用[dsh-sop-surface](../tools/tests/dsh-sop-surface.test.py)：`python tools/tests/dsh-sop-surface.test.py --houdini <明确houdini.exe> --output <新建仓库外目录>`，分别在H21/H22隔离GUI验证同一个COP Preview Material的纯色COP→图案→文件输入、vertex UV跨尺寸修改、render_view代理、用户视窗和文件依赖重开。像素标记只证明校准图案生效，不能替代自然任务外观判断；法线、透明度和正式渲染按受影响范围另验。首次显示Constant后切换纹理的刷新范围与稳定COP输入分开，不把后者通过扩大为前者已修复。表面路由与按需资料传输复用[dsh-host-smoke](../tools/tests/dsh-host-smoke.test.py)的`--context-loop --surface-method`，在精确DSH中核对实际provider收到的persona、完整skill及原生/嵌套read内容，不用源码正则断言代替消费方验证。这是受控模型传输检查，不证明自主选用。

指定生图接入使用[图像请求回归](../tools/tests/image-generation.test.mjs)覆盖精确路由、参考图片字节、防覆盖/文件策略、原图恢复与不自动重试；[真实DSH图片消费](../tools/tests/dsh-image-generation-smoke.test.py)用自有HTTP夹具验证动态设置/凭据、原生及PTC请求、真实附件与交付，默认不调用收费模型。真实提供方测试另记录实际model、请求、原图与视觉范围，不把夹具通过当成外部API可用。

复杂表面使用[dsh-surface-textures](../tools/tests/dsh-surface-textures.test.py)：`python tools/tests/dsh-surface-textures.test.py --houdini <明确houdini.exe> --output <新建仓库外目录> [--texture <已生成PNG>]`。隔离GUI覆盖共享图案的底色/粗糙度/高度与法线、图案编辑、圆柱vertex UV的物理尺度、File COP及混合图层、用户视窗与同版本独立重开。默认只使用程序生成文件；可传外部生图结果，脚本不调用收费模型。像素变化只证明消费或参数响应，重复边界、法线方向与外观仍须看实际图；文件输入通过不等于任意生图服务或Karma通过。

参数模式与条件使用[dsh-parameter-conditions](../tools/tests/dsh-parameter-conditions.test.py)在隔离H21/H22核对原生toggle/exclusive条的存储值、合法组合、非法值、归属和回滚，以及COP逐轴尺度在关闭/开启模式时的真实图层响应。参数目录的conditionals、menu_kind与set_value经过[目录回归](../tools/tests/dsh-parameter-catalog.test.py)保存实际回执；以`DSH_CATALOG_FIXTURE_OUT=<外部JSON>`导出，再用dsh-host-smoke的`--context-loop --catalog-fixture <JSON>`核对真实DSH原生/嵌套消费。几何表面方法的反例应区分全局UV范围与各目标面映射、部件单独正确与装配关系正确；自然任务验证不以技能读取或全局包络响应代替这些性质。

HDA回执呈现使用H21/H22的[dsh-hda-lifecycle](../tools/tests/dsh-hda-lifecycle.test.py)，以`DSH_HDA_PRESENTATION_FIXTURE=<外部JSON>`导出真实锁定预览；再运行dsh-host-smoke的`--context-loop --hda-fixture <JSON>`，核对原生文本、嵌套选择结果、完整归档及provider实际取得的可编辑范围。目录清单摘要不改变丢弃或归属范围，旧回执不能补造范围。任务持续推进与阶段反馈由persona维护，领域知识按当前决策加载；上下文夹具证明送达，行为收益另用有效provider/模型/推理档、API路线、参考输入和预算相匹配的新任务验证。相同模型名、更多反馈文字或更少调用都不能单独证明效率和质量提升。

UV与拓扑的机制范围由[dsh-uv-construction](../tools/tests/dsh-uv-construction.test.py)在隔离H21/H22核对：矩形面板开孔前传递UV、开孔后连续映射、切割体新增面的来源和UV、顶点硬切投影轴反例，以及尺寸/切割位置变化后的固定纹理密度。它不认证任意曲面展开或审美效果。PolyBevel用[节点知识回归](../tools/tests/dsh-node-knowledge.test.py)对照不同圆柱分段数、默认小角度与按几何选边；组件消费者用[输出回归](../tools/tests/dsh-output-publication.test.py)对照清理支路被绕过和正确重连后的实际属性/警告。Boolean/PolyBevel节点卡由上述目录回执一起送到真实DSH，表面方法继续沿`--surface-method`验证按需资料读取；无须新建生产验证框架或固定建模顺序。

忙碌请求的状态投影使用[请求查回回归](../tools/tests/request-recovery.test.mjs)、[执行状态回归](../tools/tests/execution-state.test.mjs)和[trace归一化回归](../tools/tests/normalized-trace-steps.test.mjs)，核对通信未知→queued/running→终态、过期结果分流及重复查回不增加上下文。真实DSH的`--context-loop`还通过原生/嵌套工具检查状态解释实际送到provider，且未重发原操作。此范围不证明具体COP/渲染原生阻塞已修复，也不证明模型必然正确采用诊断。

现场原生jobs使用[真实live长任务组合](../tools/tests/dsh-live-job-loop.test.py)传`--runtime-cache <精确DSH> --hython <目标hython>`，启动自有DSH Host与独立Bridge，核对原生/PTC提交与完整结果、原作者完成通知、排队取消、运行中取消后真实终态、丢提交响应和Host重开原任务恢复；H21/H22分别验证。夹具记录并核对两段Host实际消费的构建摘要，期间重建lib会使验收无效。规划回复由本地夹具控制，不证明自然任务质量或用户live加载。[通用jobs通知回归](../tools/tests/dsh-job-completion-fixture.mjs)接受同一精确缓存，核对取消竞争、大结果展示限额、冷历史原值及已消费结果/终态生产者引用释放。在线投影检查必须使用真实DSH registry、长工具历史及持久恢复，不能用仅聊天事件或配置存在代替实际消费者取得的状态。

资产主入口与后加模块用[dsh-asset-edit-entry](../tools/tests/dsh-asset-edit-entry.test.py)在隔离H21/H22验证：从当前模块值初始化公共控制，数值/开关单向引用，SOP主控驱动真实COP图层与最终材质消费者，两个COP容器的上层分组、原入口说明更新，以及同版本独立重开。跨进程图层对照使用完整buffer和明确元数据，不能把包含进程内identity的观察hash当跨进程内容标识。上述真实DSH的`--surface-method`同时验证参数与网络交接资料的按需消费。机制通过不证明自然模型会选对公共参数，或实际GUI布局已经验收。

孔径检查的能力范围由[dsh-quality-contracts](../tools/tests/dsh-quality-contracts.test.py)核对：几何违反条件、检查能力/预算不足、非法参数分别保留不同结果；能力不足不回滚同批正常修改。完整帮助的runtime_limits与执行来自同一维护源。目录回执导出的interface_observation由上述真实DSH循环同时核对原生/嵌套消费，不能只检查Python返回字典。

转录调度改动先用目标Houdini自带的普通Python运行[视频回归](../tools/tests/video-tutorial.test.py)中的四个并发检查，覆盖本地HTTP实际重叠、并发上界、失败停止新派发且保存已在途结果、成功片不重复提交、启动速率以及等待下一次派发时及时保存已完成响应。时间戳改动运行[时间戳回归](../tools/tests/video-timestamps.test.py)，核对原始成功回包、术语参数身份、毫秒音频偏移到视频秒数的投影、全量/部分/缺失覆盖以及context和分页读取实际消费；不能从格式有效推断听写或时间对齐准确。

```powershell
# $tutorialPython 指向目标安装的 python311/python.exe；不需要导入 hou 或启动 GUI。
& $tutorialPython tools/tests/video-tutorial.test.py VideoTests.test_concurrent_http_requests_overlap_within_bound_and_resume_skips_successes VideoTests.test_concurrent_failure_drains_inflight_success_without_dispatching_next_and_retries_explicitly VideoTests.test_dispatch_rate_uses_spacing_without_delaying_inflight_completion VideoTests.test_rate_wait_saves_completed_response_before_the_next_dispatch
& $tutorialPython tools/tests/video-timestamps.test.py
```

外部模型并发试验在授权任务中以相同片长逐级增加并发，启动速率单独固定；从唯一manifest/attempt/outcome统计实际提交、完成、失败、在途峰值、总耗时与续跑缺口。成功范围只能记作已验证并发，未遇限流不能称供应商最大容量；吞吐已平台化时不继续机械增加重复上传。内存随并发与音频片长增长，计入Base64、JSON请求体和响应的实际进程峰值，不能只统计WAV文件大小。每次提交数量上限保持100；更长任务再次调用时复用同一work，跳过已成功片，不改历史或重建任务来解除上限。

正常请求失败会排空已派发请求并保存结果；Host取消或进程退出是另一条边界，强制结束子进程不能撤回云端请求。已保存成功片保留，只有attempt而没有outcome的片仍为unknown，后续重发需要明确重试授权；取消后释放本子进程的锁不证明云端没有执行。检查中分别验证这两条路径，不把普通失败排空的结果外推为强制取消也能保存全部回包。

供应商目录连接由[API配置回归](../tools/tests/api-route.test.mjs)核对DSH已注册/已配置供应商联集、不可用配置与音频/图片显式API边界。私有运行环境用[路径与诊断](../tools/tests/video-runtime.test.mjs)和[发行装配](../tools/tests/video-runtime-package.test.py)核对HFS Python、无全局PATH回退、输入摘要、完整源码与许可提供物、已编译目录复用和坏包拒绝；真实媒体检查用当前Houdini Python和插件私有FFmpeg生成合成视频后执行prepare/scan，系统PATH不可掩盖依赖缺失。正式发行还需核对完整安装/同版修复，不以源码准备成功代替签名受管发行。

媒体发行装配使用[固定来源](../deployment/runtime.json)和[源码构建器](../tools/build-video-runtime.py)，从精确FFmpeg、zlib、FreeType、HarfBuzz、dav1d源码生成独立共享库，关闭外部库自动探测和网络。zlib支持PNG等压缩图像的读写，dav1d提供不依赖显卡的AV1解码；保留FFmpeg内部常见视频/音频解码、PCM切片、抽帧、文字标签、缩放、裁框和联系表。编译器带入的私有DLL按实际导入收集，Windows系统DLL不复制。完整FFmpeg/zlib/FreeType/HarfBuzz/dav1d/MinGW-w64/LLVM源码、原始许可证、工具链配方、实际配置与命令、实际补丁及范围、DLL导入表及输出摘要随同媒体运行时提供。Windows构建补丁只把过长对象列表改为GNU Make/llvm-ar响应文件，解决原生Windows命令行长度限制，不改变媒体算法；原始源码档案保持不变，差异文件随包提供。FreeType使用FTL许可并保留其署名。构建端需Python 3.11+和Git for Windows；编译器/CMake/Ninja/Meson/NASM/pkgconf自动按锁定来源下载，只用于发行构建，不成为用户安装依赖。`build-release --media-cache <目录>`可复用校验过的输入，`--media-runtime <目录>`可复用已编译的完整提供物并核对来源、配方和全量文件摘要；源码准备对应`prepare-video-runtime --cache`/`--runtime`，仍保留原`runtime/video.previous-*`。没有本地缓存时，clean tag按同一配方从固定来源完整装配。

预览后端变更使用[camera-preview-smoke](../tools/camera-preview-smoke.py)在自有GUI中核对透视/正交及detail取景、几何Alpha与实体背板的实际合成、PNG/viewport输出及frame/相机/选择/可见性恢复。原生节点参数存在、不透明RGB出图或透明背景均不能替代几何透明验证；新增后端或Houdini构建先通过同一公开合同，再调整选择边界。

Karma创建默认由[dsh-karma-defaults](../tools/tests/dsh-karma-defaults.test.py)在隔离H21/H22核对：原生景深默认与DSH新建设置、显式开启、已有艺术设置保持，以及最终USD的Karma属性；可选`--render`用小图对照实际清晰／失焦，不改render_frame的艺术设置。曲线方法由[dsh-curve-paths](../tools/tests/dsh-curve-paths.test.py)核对原生可编辑路径、控制引用到最终Sweep、实际线段最近对、局部弧距排除、预算与不支持输入；不把折线包络通过推广为平滑曲线或最终实体无穿插。工程图像目录由[project-paths](../tools/tests/project-paths.test.mjs)、[managed-preview](../tools/tests/dsh-managed-preview-paths.test.py)及[输出消费](../tools/tests/dsh-output-checkpoint.test.py)共同核对HIP分组、实际参数求值、显式模板与字面路径、Save As和隔离副本。

原生节点初始化框含便签的整根删除用[dsh-delete-editor-items](../tools/tests/dsh-delete-editor-items.test.py)在隔离H21/H22核对精确物件身份、foreign拒绝、原生Undo成员恢复及失败创建清理；它不扩展普通框布局对便签的支持，后加的用户编辑物件也不因父级曾被登记而被接管。

HDA正常界面比较与真实覆盖拒绝用[dsh-hda-lifecycle](../tools/tests/dsh-hda-lifecycle.test.py)；Sticky Note的归属、局部维护、Raw Gate和失败恢复用[dsh-network-notes](../tools/tests/dsh-network-notes.test.py)；已有pane/Qt窗口/停靠面板发现、精确裁框、当前内容与用户状态保持用[dsh-ui-surfaces-gui](../tools/tests/dsh-ui-surfaces-gui.test.py)，包含真实HTTP发现→目标截图→同票据恢复。[headless拒绝](../tools/tests/dsh-ui-capture.test.py)与[HTTP边界](../tools/tests/dsh-bridge-transport.test.py)分别核对无GUI、旧node/view/尺寸输入与请求事实。界面测试在自有GUI检查实际目标与图像，生成文件存在不代替人工识图，不连接用户live或改用户HIP。

跨层修改应验证消费方最终取得的状态，局部函数返回或静态配置存在不足以证明链路可用。入口/preset/client改动用精确DSH的实际模块图确认根前端与工具scope，再由真实页面确认内容视图和选中任务；工作区切换同时核对DSH store中的session、preset、cwd及workspace成员。入口可用空会话验启动，但原生轨迹页需要普通有内容会话验收。Host组合检查的`--context-loop`使用自有HTTP Bridge夹具与脚本化模型适配器，核对真实DSH最终请求中的错误、未决回执、后台任务和上下文更新；可用`--outcome-fixture`接入隔离HOM导出的真实回执，核对捕获的操作异常、fallback和验证状态。不调用收费模型或用户Houdini。相关入口为[Host组合](../tools/tests/dsh-host-smoke.test.py)和[真实页面导航](../tools/tests/dsh-client-navigation.mjs)。

从MSIX打包的开发宿主运行GUI验收时，测试CLI先调用`reexec_unpacked_test_cli()`。继承宿主包身份会使Windows使用打包程序DLL搜索规则，即使PATH含HFS/bin也可能找不到Qt helper依赖。此入口使用Windows桌面应用启动属性，并在继续前核对新进程没有包身份；保留标准输入输出、退出码及自有进程树清理，不修改用户安装、机器环境、令牌或Chromium沙箱。普通桌面CLI原地继续。实现与回归分别在[测试环境](../tools/houdini_test_environment.py)与[隔离回归](../tools/tests/dsh-test-environment.test.py)。依据为[Windows DLL搜索规则](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)和[桌面应用进程属性](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)。


执行结果应同时核对原生与Code Mode嵌套事件、取消/未知/过期回执及现场runtime身份；展示投影不得丢失无execution的真实回执。trace用真实当前版本日志校验可见内容、调用关联和解析缺口，不以旧fixture或旧session文件名证明新格式可读。用例保持针对已观察到的边界，旧策略删除后保留操作、权限和恢复检查，移除只证明策略存在的断言。

普通大结果的历史引用使用原生/嵌套工具回执中记录的路径，文件仍须通过hash校验；不能因Save As改变cwd而只查新目录，也不能从用户正文取得任意文件路径。[结果详情回归](../tools/tests/result-details.test.mjs)覆盖跨目录、伪造来源和篡改拒绝；官方宿主与保存目录回归分别核对现场消费和持久目录范围。

节点交付的定向入口为[Host路由](../tools/tests/node-delivery.test.mjs)、[原生/嵌套卡片投影](../tools/tests/node-delivery-client.test.mjs)、[持久标识HOM](../tools/tests/dsh-node-delivery.test.py)及[排队取消HTTP/HOM](../tools/tests/dsh-node-navigation-cancel.test.py)。跨层修改还需在精确DSH组合和新建的隐藏GUI进程中，由真实Agent工具循环产生原生/嵌套回执，选中对应任务点击实际卡片，回读网络/参数页；重开同HIP并改名后再点击旧卡片，切HIP核对错误提示，暂停队列后切任务并恢复队列核对旧导航没有生效。局部模拟通道不能替代这条连接；测试脚本、截屏、完整结果和运行目录留在仓库外证据目录。服务框保存重开由[服务框回归](../tools/tests/dsh-render-service-box.test.py)核对标题、固定边界、真实成员与用户节点位置。

曲线的脆弱接口由既有[node-knowledge](../tools/tests/dsh-node-knowledge.test.py)核对Add/Curve输入、Bezier与Fit、Resample过冲、Circle Spline及Sweep实际消费朝向；[参数目录](../tools/tests/dsh-parameter-catalog.test.py)导出其真实操作卡，再沿上述DSH原生/嵌套目录消费验证。曲线资料、Karma技能与质量交接仍沿`--surface-method`检查实际提供方输入；资料送达不证明自然作者采用或美术质量。

USD继承输出用[camera-framing](../tools/tests/dsh-camera-framing.test.py)在H21/H22核对实际stage/settings选择、Husk文件名、多个磁盘raster、部分缺失、checkpoint未验证、显式覆盖和预检帧恢复；只替换原生render方法来控制文件产出，不据此宣称Karma出图。需要验证真实渲染时显式运行[isolated-render](../tools/tests/dsh-isolated-render.test.py)，覆盖低分辨率Karma CPU的显式图片和原生RenderProduct继承，分别保留进程、文件与像素事实；不加载用户HIP或连接live，不认证场景美术效果。

## 隔离执行与开发工具

`houdini_isolated`是模型可调用的一次性独立计算入口，Host实现见[isolated-execution.ts](../src/isolated-execution.ts)，方法由[独立执行skill](../skills/houdini-isolated-execution/SKILL.md)按需维护。Host消费当前DSH任务的文件权限与明确所选登记的静态安装事实，或显式HFS；登记断连不要求live健康。无登记的固定Bridge配置保留在线安装信息入口。复用下述隔离检查器执行builder、已保存HIP副本及加载后的受管准备代码，将实际结果、退出事实和图片交回同一调用；后台运行使用DSH既有job_output/job_kill，read只取原run报告与图片，不连接live。省略output_dir时按工作区共享角色分配唯一run，显式和历史路径保持。它不创建另一套团队、常驻worker或完成账本，同一live的作者/节点权限不变。

验证该入口时，先核对实际文件范围、声明依赖、开始执行时的复制版本、builder/副本选择、成功与失败回执、原生附件、取消后自有进程清理；跨层检查必须由真实DSH Agent调用产生原生/嵌套工具结果，并确认选中任务收到同一产物。`inputs_unchanged`仅观察运行后的原来源，`input_observations`逐文件保留前后hash、改变/不可读与原错误，不覆盖执行终态。受影响的[纯入口回归](../tools/tests/dsh-isolated-manifest.test.py)核对来源变化/不可读与执行错误并存、staging损坏拒绝；[真实副本回归](../tools/tests/dsh-isolated-probe.test.py)在H21/H22核对授权保存回自产来源、并发改/删来源和载入前复制件hash检查。将所选登记置为断连、健康接口设为不可用后，默认及显式安装的新worker仍应运行，read不得重新发现运行时。独立执行结果只属于本次输入，未保存live修改、未声明依赖和当前用户GUI状态另行判断。自然团队成员自验证及主作者接入的效果，不能由固定脚本夹具通过外推。

直接入口为[Host适配](../tools/tests/isolated-execution.test.mjs)、[无输出探针](../tools/tests/dsh-isolated-probe.test.py)及[真实团队循环](../tools/tests/dsh-isolated-tool-loop.test.py)。团队循环用`--runtime-cache <精确DSH> --hython <目标hython>`启动独立Host和原生队友，覆盖预检/构建错误、真实Karma图、原生及PTC读图、DSH作业取消和同源报告；规划模型由本地夹具控制，不证明语义判断或自然采用。Windows入口复用无包身份测试CLI；外层受限令牌不支持再次创建DSH沙箱时，测试驱动需从正常桌面令牌运行，DSH内部仍保持workspace-write，不通过扩大模型权限证明默认路径。

模型对照用run-modeling-trial的`--reasoning-effort`与统一的`--max-output-tokens`固定请求参数；自定义PI模型确需声明能力时，另显式传`--reasoning-wire-value`，只改隔离副本。开始模型请求前核对原生resolveModelInfo的实际defaultEffort。缺推理声明不等于后端没有推理：适配器可能只省略推理参数，不能从模型名称补造能力。回环HTTP测试[dsh-image-consumption-fixture](../tools/tests/dsh-image-consumption-fixture.mjs)核对真实reasoning_effort、附件身份及请求变体；实际模型语义另验。`--smoke --scripted-smoke --smoke-continuity --followup <文件>`通过真实DSH和Houdini跑两轮同网络创建/修改，模型流完全本地拦截；[共享连接反例](../tools/tests/dsh-shared-continuity.test.py)保留其他执行端/工程及跨进程动作拒绝。

源码文件同步复用[参数补丁回归](../tools/tests/dsh-parameter-patch.test.py)，核对UTF-8原文、完整source写入、相同内容不写、过期hash整批零写入及原有恢复。大型控制回执可由dsh-scoped-observation导出`DSH_HDA_PRESENTATION_FIXTURE`到诊断目录，再用dsh-host-smoke的`--context-loop --geometry-fixture <回执>`验证实际provider取得geometry_scope、完整恢复证据及原生/嵌套一致性；导出变量只用于测试夹具，不是生产状态。

[hda-delivery-check.py](../tools/hda-delivery-check.py)在新 hython 中加载声明 HDA，按 manifest 创建实例、设置参数、调用按钮并检查几何/参数/错误。判据应能区分正确与错误结果，例如尺寸控制检查 bounds_size，而非只有点面数。

传 `--output` 时完整报告写入指定文件，stdout 保留每个用例的结果、实测量、错误和进程状态；原生内部节点清单改为计数及报告内 JSON Pointer，并返回文件路径/hash/字节数。未指定输出文件时保留完整 stdout。不要将输出丢到 `Out-Null` 后只看退出码，也不要把新实例求值和包围尺寸通过当成部件关系或成品质量通过。[报告呈现回归](../tools/tests/dsh-hda-report.test.py)覆盖大清单中后部失败、未知诊断和归档失败；[实际CLI回归](../tools/tests/dsh-delivery-geometry.test.py)在隔离H21/H22对照 stdout 与磁盘报告及正确/错误几何判据。

原库版本维护用[HDA版本机制回归](../tools/tests/dsh-hda-versions.test.py)覆盖多定义保留、同库追加、参数/关键帧/表达式/锁定/连线、失败恢复和权限；[DSH版本维护贯通](../tools/tests/dsh-hda-version-smoke.test.py)以`--runtime-cache <精确DSH缓存> --hython <目标hython>`启动隔离真实Bridge和DSH会话，核对普通/嵌套调用的回执、会话/现场身份、新旧定义行为及下一进程Package发现。规划模型为受控夹具；这些检查不证明用户GUI版本菜单、任意回调或自然任务自主采用。

工具制作的机制检查包括[真实工具目录](../tools/tests/dsh-tool-catalog.test.py)、[共享定义与分叉](../tools/tests/dsh-hda-definition-ownership.test.py)、[参数组件](../tools/tests/dsh-hda-ui-components.test.py)、[原生Package配置发现](../tools/tests/dsh-package-discovery.test.py)和[注册/运行态失败](../tools/tests/dsh-tool-packages.test.py)。[发现GUI](../tools/tests/dsh-package-gui.test.py)核对已配置、条件与实际加载的不同状态；[Package GUI](../tools/tests/dsh-tool-packages-gui.test.py)以普通包名JSON直接指向唯一源目录，核对干净启动发现/当前加载、HDA/Shelf/Panel实际来源与公开入口、旧内容保持，以及启停不改变配置或源。已有包新增资源后从新进程验证，不靠隐式reload证明更新安全。Shelf和Viewer State需要回到Houdini外层事件循环后再验状态；installFile/sys.path不替代此路径。不同载体的结果保留实际范围，不从固定例子外推任意工具泛化。

```powershell
python tools/hda-delivery-check.py --manifest path/to/tool-check.json --hython D:/houdini/bin/hython.exe --output path/to/report.json
```

[isolated-houdini-check.py](../tools/isolated-houdini-check.py)在独立进程执行可信builder或明确保存HIP的副本，经Bridge完成cook/cache/ROP检查。manifest至少声明script/hip之一；同时提供时driver先加载副本、登记同一作者，再执行准备脚本和checks。input_root明确输入基准，files保留依赖相对结构，checks可选；省略时仅证明声明的执行，额外断言和观察由builder承担。`--trusted`沿用户授权的工程/代码计算范围，不是未知HIP的沙箱。产物使用新的运行目录；渲染继续遵守媒体输出合同，不以插件源码目录为目的地。report.json与worker-result.json保留同源有界事实；大执行详情按共享保留政策单份写入executions并返回hash/path/pointer，原失败和归档失败分别验证。独占prefs移到机器临时根，只有自有进程树退出已确认才清理；[worker边界回归](../tools/tests/dsh-worker-limits.test.py)验证GO、运行、树退出及清理事实不混用。`--status --output-dir <run>`只读最后记录，不当作进程存活；`--cancel --output-dir <run>`请求停止该run自有进程树，不启动或重试任务。默认取消文件在run内，Host可提供本次专用标记；原输入保持核对，未保存现场和未声明外部依赖不包含在快照证明中。

[快照回归](../tools/tests/dsh-snapshot-worker.test.py)在H21/H22核对真实图像/ROP、来源不变、缺输出、启动前/运行中取消；[输入回归](../tools/tests/dsh-isolated-manifest.test.py)覆盖状态身份和不完整回执。大型最终输出的[选择回归](../tools/tests/dsh-scoped-observation.test.py)使用百万面背景与明确目标组，验证正例、错尺寸、无组拒绝和未选部件漂移。整件恢复使用[流式BJSON指纹](../houdini/python3.11libs/dsh_bgeo_fingerprint.py)，按本机SideFX `UT_JSONDefines.h`读取；[指纹反例](../tools/tests/dsh-bgeo-fingerprint.test.py)验证写入时间可变化，但与日期共用字符串token的用户属性仍不能被忽略。大型流指纹不承诺任意编码/属性表布局变更等价；无法建立相同完整内容时保留恢复未确认。

```powershell
python tools/isolated-houdini-check.py --trusted --manifest path/to/check.json --hython D:/houdini/bin/hython.exe --output-dir D:/checks/run-001 --timeout 120 --memory-mb 4096
```

[isolated-worker.py](../tools/isolated-worker.py)及 [Houdini worker](../houdini/python3.11libs/dsh_isolated_worker.py)提供开发评测使用的独立Bridge进程；[worker 回归](../tools/tests/dsh-isolated-worker.test.py)验证明确IPC、启动与回收。生产的一次性Host工具调用上述checker与受限进程执行器，不为模型挂载常驻Bridge。[delivery-audit](../tools/delivery-audit.mjs)只在开发评测中从会话回执读取交付事实，不进入模型的生产工具目录。

隔离工具通过自有进程句柄和 Windows Job 管理超时、取消及进程树内存。报告与退出状态都要读取；不把启动成功当作负载完成。任意 Python、回调、绝对路径文件和外部服务的副作用不属于场景恢复保证。

收费任务只在用户授权的模型与预算范围内运行 [run-modeling-trial.py](../tools/run-modeling-trial.py)。使用隔离任务目录、精确 DSH/Node/Houdini 和明确provider/model，只复制所选路由及必要credential reference，不修改用户设置或live。教程试验通过显式`--service-profile`加入单个转录服务与用途选择，不复制整个用户配置；服务说明只含provider/api/baseURL/apiKeyEnv/model/models及可选python。DSH自定义服务商需要非空的真实聊天模型目录`models`；独立的`model`填写实际转录模型，不把ASR伪装为聊天能力。密钥仍由隔离凭据引用或指定环境变量解析。时间上限不等于费用上限，按提供方实际价格/套餐边界核算；DSH observer的usage事件与未知费用分别记录。评审答案不进入生产提示词或用于未见题调参。

验证自然复刻能力时使用`--no-feedback --approval-policy never`且不传followup；只提交初始用户目标、来源与环境事实，运行中不向作者补充接线、参数、截图答案或几何/效果修正。冻结初始输入与禁止外部反馈不限制作者自主调查：作者可以只读原片、回查原分析，并在自己的`dsh-artifacts/analysis/`中抽取画面、补证及整理；原始资料不改写，成功音频不重复上传。任务说明不能用“启动后不补资料”同时指代外部答案介入和作者自主补证；范围有歧义时，不将该运行计作主动补证能力通过。工具缺陷在运行后回到系统维护源修复，用新快照验证，受干预运行不作为独立能力证据。复用已有分析与只给视频的冷启动分别报告。
驱动保持workspace-write并核对原生权限回执；取消用运行目录的cancel文件或Ctrl+C。到期、未决审批与失败明确记录，不自动扩大权限或代替作者续跑。输入、代码、依赖身份与预算启动前固定，结束后核对；自有进程停止与隔离凭据副本清空分别确认，不能由driver退出0代替。对应[生命周期回归](../tools/tests/modeling-trial-lifecycle.test.py)不调用HOM或收费模型。

可视化试验须以真实DSH `llm.resolveModelInfo` 的inputModalities确认当前路由，而非从准备配置摘要推断。锁定DSH的pi-ai模型配置使用`input`，发现/解析结果使用`inputModalities`；两者不能原样互换。原生Houdini观察用`--show-gui`，`--observe-model-images`通过透明observer记录实际LOOP图像引用及供应商完成；前端消费沿同一官方Host的浏览器验证入口单独检查。供应商单独图像探针、模型实际收到工具图像、前端预览及工程重开分别核对，不互相代替；观察器仅用于隔离开发试验，不进入生产插件图。

## 分支与接续入口

接续或合并前先核对 `git status --short`、`git branch -a -vv`、`git worktree list` 和相关提交，再读目标分支 handoff。不同工作树的文档描述各自提交，main 不代表全部尚未合并的工作。

现役设计原位替换，不在 docs 追加版本叙事、试验流水或 session 记录。历史保留在 Git；日志、耗时、截图、评测 HIP 和本机材料放会话、CI、tools/out 或仓库外目录。

### 交接文档生命周期

handoff 是唯一滚动交接入口，只保留下一次接续仍需完成的动作、阻塞和验证缺口。每项写现状、下一步、移除条件和仓库内入口；完成后删除整项。保持一份文件，不按日期分叉，不把历史成功继续标为活动项。没有待办时写“当前无待交接事项”。

## 运行与发行

标准交付为包含Houdini/媒体资源的`.tgz`，通过受支持官方Desktop的原生插件管理安装本地绝对路径或可访问的tarball URL；当前发行进度见[H-01](handoff.md#h-01-标准插件发布与用户加载)，不把源码目录或历史独立运行包当作标准发行，也不假定npm包已经上架。宿主原生UI新装默认停用，须启用后配置主模型、进入Houdini模式。普通用户新开Houdini前由`DesktopIntegration.installHelper`自动执行包内安装器并消费唯一结构回执；现场菜单的组件安装/更新复用同一路径，不要求用户解压找Install.cmd或配置Node。

本端安装由[install.ps1](../installer/install.ps1)部署不可变helper并原子切换Package；[legacy-migration.ps1](../installer/legacy-migration.ps1)维护历史生成入口的唯一所有权识别、只读预览、原始字节/SHA256备份、停用和受变更保护的恢复，[uninstall.ps1](../installer/uninstall.ps1)复用同一边界解除登记。仅停用已确认的本插件入口，自定义或混合内容保留并报告；未知canonical冲突在新Houdini进程启动前停止。保留旧运行包、凭据、会话、HIP与其他插件，不自动合并或修复历史。已加载helper仍须保存重开，安装器不杀进程或替换进程内模块。

目标采用显式PackagesDir、已登记路径、HOUDINI_PACKAGE_DIR、HOUDINI_USER_PREF_DIR/系统Documents的顺序；公开package目录列表必须为绝对路径。安装入口以UTF-8输出`DSH_HOUDINI_INSTALL_RESULT=`结构回执，Host只消费该事实，不从stdout文案推断结果。[安装生命周期回归](../tools/tests/dsh-install-runtime.test.py)覆盖旧入口、未知冲突、定制目录、两版选择、重复安装、回退、卸载和真实Node UTF-8消费。测试必须隔离APPDATA、LOCALAPPDATA、DSH_HOME及Houdini目录；仅设置HOUDINI_PACKAGE_DIR不能隔离旧helper根中的有效安装记录。原生UI安装/启用和H21/H22加载仍须使用最终发行包验证，不能由纯安装回归或官方CLI安装代替。

### 发行操作与信任配置

代码推送只运行源码CI；[手动候选构建](../.github/workflows/desktop-plugin.yml)接受现有branch、commit或tag，只以只读仓库权限构建并保存短期Actions产物，不创建tag、Draft/正式Release或发布npm。维护者实测确认前保持发布暂停；未来公开分发须作为单独明确的操作执行，不能由main push或候选构建隐式完成。

通过 tools/build-release.py 构建标准tgz，发布前核对完整媒体资源、许可和源码，以及包内没有私有DSH/Node、核心补丁和Qt聊天壳。具体命令参数由脚本 --help 提供；候选构建不等于已发布。完整签名/发布策略属于实际分发渠道，不以旧私有运行包协议代替官方插件安装合同。
