# 开发与文档维护规范

入口见[文档索引](README.md)和[系统架构](architecture.md)。这里维护开发方法、生成规则和验证入口；尚欠动作只放[交接](handoff.md)。

## 设计原则

系统负责让模型获得准确信息、充分操作能力、真实执行反馈、可观察结果和清楚的错误。模型负责理解需求、选择方法、组织步骤和判断效果。领域知识按任务读取，执行接口只落实平台与操作合同。

已完成的功能、工具数量、历史测试和目录结构都可以调整。新增检查应解决实际接口条件或已观察到的失败；模型的一次遗漏或方法选择错误不应成为永久准入门槛。删除策略时同步删除只证明该策略的断言。

继续使用 DSH 的会话、模型、通用 Agent 循环、上下文组合、压缩和原生工具能力。插件维护 Houdini 适配；不要在插件重建一套通用 Agent 状态机或提示词历史。

## 单一维护源

| 内容 | 维护位置 | 派生或验证入口 |
|---|---|---|
| Host 工具职责与参数 | [tool-catalog](../src/tool-catalog.ts)、[tools](../src/tools.ts) | gen-tool-docs 生成 docs 工具表；工具注册与前端共用目录 |
| Houdini 动词签名、执行版本 | [工具设计](tool-design.md)，实现同步 helpers/Bridge | gen-client-catalog 生成 Host 契约和客户端目录；verb-contract 回归 |
| 动词按需结构与例子 | [verb-operation-contracts.json](../houdini/verb-operation-contracts.json)，签名仍来自运行函数 | gen-verb-contract-docs生成[结构合同](verb-contracts.md)，verb_help按需返回；说明不参与执行校验 |
| 工程图像目录角色 | [project-layout.json](../houdini/project-layout.json)，Host/Houdini同源读取 | gen-project-layout-docs生成[工程文件目录表](project-files.md)，构建与docs:check校验同步 |
| 节点操作知识 | [node-operation-contracts.json](../houdini/node-operation-contracts.json) | gen-node-card-docs 生成[节点卡](node-operation-cards.md)；node-knowledge 验实际参数和几何 |
| DSH 组合与角色 | 精确 DSH 标准组合及 [Houdini persona](../presets/houdini/persona.md) | [gen-agent-presets](../tools/gen-agent-presets.mjs)生成唯一 Houdini patch |
| 运行版本与安装组合 | [兼容清单](../dsh-runtime-compatibility.json)、[runtime](../deployment/runtime.json)、[部署锁文件](../deployment/package-lock.json) | 安装、启动、修复共用 preferred 精确组合 |
| 执行与恢复事实 | Houdini 实际执行/结果模块 | [执行契约](execution-contract.md)；Host 和前端消费 Bridge 回执 |
| 领域方法 | 对应 [skills](../skills/) 的入口和 references | 按需知识；docs 链接原文，不重复 recipe |
| Trace 解析与展示 | [Trace 设计](houdini-trace-design.md)、client/ | 使用真实请求和工具记录；按需加载诊断 |
| 故障报告 | [诊断包合同](support-reports.md)、DSH原生会话读取、唯一Python收集器 | 精确会话/竞态、脱敏/恶意ZIP、H21/H22 Qt下载及真实DSH组合；不把诊断采集当作现场恢复 |
| 连接与占用反馈 | [接续边界](multi-instance.md#单实例保存点恢复)、[接续诊断](../src/connection-status.ts) | [只读/身份回归](../tools/tests/connection-status.test.mjs)、[前端可见边界](../tools/tests/executor-picker.test.mjs)、[双进程锁](../tools/tests/dsh-runtime-occupancy.test.py) |
| 开发评测 | [评测原则](product-modeling-evaluation.md)、evaluation/、tools/ | 公开题面与评审答案隔离；生产面不读取评审材料 |

普通聊天区不增加常驻连接提示或检查按钮；[DSH报告组合](../tools/tests/run-support-dsh.py)同时核对切换会话后没有此类额外UI。真实场景恢复使用[dsh-scene-recovery.test.py](../tools/tests/dsh-scene-recovery.test.py)的隔离H21/H22入口。[原生启动提示](../tools/tests/run-support-qt.py)增加`--startup-feedback`，核对占用者说明、重试清除及报告取得当前启动原因；窗口测试使用受控启动输入，不代替正式安装包的双Houdini菜单验收。

新增长期生产模块必须加入架构代码地图。新增文档必须加入索引，说明它的职责及源码、验证入口。

## 构建与生成

标题和工程标识的[定向回归](../tools/tests/workbench-project.test.mjs)核对原生自动/手动标题、显式重新命名、排队消息/晚回执、未保存与同名文件。隔离工作台另核对实际Qt页头短名/完整路径、绑定后自动标题及另存不迁移其他对话；不把历史标识解释为在线状态。

工作台图钉使用原生页头的常驻controls扩展位置；[实际工作台浏览器检查](../tools/tests/workbench-browser.mjs)覆盖空白/已有对话、紧凑尺寸与点击后真实回执。[Qt窗口检查](../tools/tests/dsh-webview-navigation.test.py)的`--standalone`入口使用普通Houdini Python与Windows Qt环境，核对原生TOPMOST状态、窗口句柄、Hide/Show事件、焦点及页面/视口保持；不能仅用网页未重新请求来代替无闪烁检查。

启动反馈用[真实 Qt 阶段检查](../tools/tests/dsh-workbench-startup.test.py)传目标 HFS 目录，验证窗口在准备结束前显示、GUI 定时器继续运行、真实阶段/计时、后台等待与失败传递；准备函数用受控等待替代，不据此宣称正式包启动性能。登录外链用[Qt 登录窗口检查](../tools/tests/dsh-external-links-qt.test.py)重复传 `--python <Houdini普通Python>`，直接消费精确 DSH 的 BrowserLogin，核对预开空页、延迟地址、取消和主页面保持，系统浏览器交接被截获；账户授权与真实回调仍需独立验证。两者仅创建自己的临时目录与 Qt 进程，不连接用户现场。安装注册使用[安装器回归](../tools/tests/dsh-installer-bootstrap.test.py)核对跨磁盘覆盖、手删目录修复、实际偏好记录、解除注册归属和用户数据保留；版本页操作沿 `dsh-install-ui` 定向检查。

工作台主动打开/新建使用[真实图形启动组合](../tools/tests/dsh-workbench-launch.test.py)：先独立启动工作台，再通过实际网页菜单与Qt对话框启动H21/H22，核对自动绑定、不同未保存名称、文件选择、重复打开、取消、原对话恢复修改权、在线/离线/场景切换及另存提示。脚本驱动控件而非物理键鼠，模型回复由受控提供方生成；`--standalone-only`只验证无Houdini启动及用户目录隔离。[启动边界](../tools/tests/dsh-workbench-projects.test.py)覆盖错文件/错进程/旧回执、后台隐藏与超时；[桌面RPC](../tools/tests/workbench-desktop.test.mjs)覆盖原对话读取、固定地址/凭证与非法输入。产品Logo以[选定PNG](../assets/dsh-houdini.png)为唯一原图，保留其透明底、完整鲸鱼和清晰点线轮廓；使用[编码工具](../tools/build-workbench-icon.py)生成16–256像素ICO，工作台与安装器共用该图标，运行时不依赖Pillow。

独立工作台使用[隔离组合验收](../tools/tests/dsh-workbench.test.py)：普通Python/Qt桌面、真实DSH持久与preset、H21/H22 Bridge、同目录不同HIP、重复打开、实际浏览器选中对话及目录、工具修改/另存、单端崩溃、手动重开原工程和工作台重启保留历史。本地脚本提供方驱动实际Agent循环生成原生/嵌套回执与可冷加载日志，不调用外部模型；不证明模型自主行为或正式签名安装组合。测试的Qt调试端口仅属于该隔离进程，正常运行不主动启用。受管安装入口仍需随新版bootstrap和签名运行包单独验收。

[原生菜单调用链](../tools/tests/dsh-workbench-menu.test.py)接受一个houdini.exe路径，使用全新偏好中的uiready调用真实Open Workspace入口，核对空白工程、实际Qt选中会话和正常退出Houdini后桌面存活，不替代物理菜单点击或签名安装验证。[写入反例](../tools/tests/dsh-workbench-registry.test.py)覆盖占用目标、保存失败、文件身份/硬链接、发布失败保留租约和旧场景选择。既有[执行回归](../tools/run-deployment-tests.py)支持重复传入`--suite`选择受影响检查，保持偏好与恢复材料隔离。

```powershell
npm install
npm run build
npm run docs:check
```

只用 npm。build 刷新节点卡、动词结构合同、唯一Houdini preset、工具文档、客户端目录和Trace资源指纹，再编译TypeScript。`lib/`、生成区、`presets/houdini/cordis.patch.yml`不手改。

角色在 persona.md 维护；组合继承锁定版本 DSH 的标准插件，关闭其他内置 preset，只注册 Houdini。插件以 DSH 0.2 的 `bundle.patch` 装载配置：根级bare package `dsh-houdini`承载前端，preset内`dsh-houdini/agent`提供工具和原生context producer。DSH客户端模块图识别bare package，不能以preset scope或包子路径导入成功替代根客户端注册。客户端使用DSH的conversation/trajectory注册接口。

`docs:check` 只检查生成漂移、文档索引、模块覆盖和 Markdown 链接，不自动修文档。改动生成源后先 build，再检查最终一致性。

[系统网络检查](../tools/tests/dsh-system-proxy-check.mjs)接收配套缓存根目录，使用隔离设置快照与真实Windows PAC API验证新请求切换和已选路线保持，不改当前用户注册表。

DSH运行修复的源码、上游提交和编译包清单由[修复声明](../deployment/dsh-runtime-fixes/manifest.json)维护；`npm run runtime:prepare`准备独立缓存。[运行修复反例](../tools/tests/dsh-runtime-fixes-check.mjs)接受该缓存根目录，实测Windows权限保持/回滚、内核拒绝、只读诊断、文件策略与网络边界。[网络全流程](../tools/tests/dsh-network-workflow.test.py)使用 `--runtime-cache <根目录>` 跟随Windows系统网络；可选 `--proxy <明确HTTP代理>` 仅在隔离测试数据中覆盖路线。该测试以受控回复驱动真实DSH网页取证、下载、读图和普通/嵌套调用；`--browser-module <Playwright入口>`另检查真实选中任务和命令退出状态。测试只访问公开资料，不调用收费模型；这些结果不证明自主模型选择或所有外部网站可用。

[目录接续组合](../tools/tests/dsh-workspace-continuity.test.py)使用`--runtime-cache <根目录>`启动原生DSH，检查会话/历史保持、实际文件工具与附件搜索、新目录范围和写入失败；在元数据提交与工作区归属更新之间终止隔离Host，再验证启动自动完成。[Houdini接续组合](../tools/tests/dsh-scene-recovery-e2e.test.py)增加`--save-as --gui --hython <路径> --browser-module <Playwright入口>`，在H21/H22实际保存后检查下一模型步骤取得新工程说明，写文件落到新目录，重开后浏览器原会话普通输入“继续”恢复HOM与嵌套工具。测试仅终止自身创建的进程，不修改用户HIP。

同一组合的`--original-choice open|keep --gui`改为在同目录打开无关HIP并制造真实未保存修改，浏览器在普通“继续”后通过原生对话选择切回原工程或保留当前内容；独立HOM探针检查最终路径、参数、脏状态。`dsh-recovery-locate.test.py`核对保存链分叉、缺失/替换文件与无记录复制品；`scene-recovery-original.test.mjs`核对自由文本、绑定变化和落盘失败不能触发打开；`dsh-scene-recovery.test.py`覆盖仍活跃的原作者、过期现场、任意路径拒绝和打开前文件变化。

`--original-choice auto --gui`检查空白新场景直接接续，非空场景不能利用该入口跳过选择；原生提问另外核对宽窄屏、路径换行及单题无分页。可用`--save-hython <H22路径> --hython <H21路径> --original-choice open --gui`建立带H22 Flipbook参数的保存点，核对真实加载警告能进入同一恢复回执和模型步骤。只验证已加载场景及警告传播，不证明复杂HIP跨版本兼容。

同一组合增加`--long-warning`，在真实加载后注入大段诊断，检查原生模型步骤只收到有界首尾预览，再经`houdini_resource`读出被省略的中段；后续HOM回执只能含引用。`--warning-archive-failure`只破坏诊断归档位置，验证恢复仍可继续且不回填全文。[警告边界](../tools/tests/load-warning.test.py)覆盖转义、原文无损、同内容复用、配额/存储/篡改和主线程隔离；[跨语言资源读取](../tools/tests/load-warning-resource.test.mjs)读取真实Python归档，核对换工作区、后续恢复、伪造消息及hash校验。

[已有工作区生命周期](../tools/tests/dsh-workspace-lifecycle-check.mjs)接受缓存根目录，核对预存文件的更新/重命名/删除、硬链接与目录联接的外部权限保持、显式保护、只读token、重复授权和撤销。[网页传输反例](../tools/tests/dsh-web-transport-check.mjs)验证公开CDN跳转、私网/凭据/降级拒绝、混合DNS答案、真实失败原因及代理凭据脱敏。全流程还验证下载到预存目录后的整理，以及退出0诊断在原生/嵌套调用和实际页面中的一致性。编译器的 `--development` 仅可写 `tools/out` 中无完成标记的试验运行目录；正式缓存必须从声明补丁与锁文件构建。客户端构建使用同版上游预设，缺失的打包依赖必须使构建失败，不能把未解析依赖发布到浏览器。

## 修改与验证

HIP网络路径改动用`dsh-launcher-preflight.test.py`与隔离H21/H22的`dsh-scene-context.test.py`，把文件存在与真实路径解析替换为立即失败的探针，检查入口、工程登记、metadata与实际Bridge回执均不依赖网络I/O；覆盖UNC正反斜线、共享根目录、中文空格和映射盘。`image-generation.test.mjs`同时核对字面目录投影、Host解析后的实际输出、工程根别名与子目录重定向拒绝。注入断网只证明调用边界，实际SMB读写、服务器权限与用户加载仍须用自有网络工程另验，不能用本地路径测试代替。

工程关联与空工作区改动用`workbench-association.test.mjs`核对同路径异工程、能力查询、UI回执、多窗口选择及目录提交失败。`dsh-workspace-continuity.test.py --runtime-cache <精确DSH运行时>`核对原生条件删除、归档/文件/活动现场/重命名保留及重启；`dsh-workbench.test.py <HFS> --runtime-cache <精确DSH运行时>`核对实际桌面、选中对话与另存目录消费。不连接用户live，不删除用户目录。

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
| Raw Gate | [dsh-bridge-raw-gate](../tools/tests/dsh-bridge-raw-gate.test.py) |
| 节点归属 | [dsh-node-ownership](../tools/tests/dsh-node-ownership.test.py) |
| 捕获失败与回滚 | [dsh-bridge-caught-failure](../tools/tests/dsh-bridge-caught-failure.test.py) |
| 创建失败清理 | [dsh-tab-create-failure](../tools/tests/dsh-tab-create-failure.test.py) |
| OBJ 父级 | [dsh-object-parenting](../tools/tests/dsh-object-parenting.test.py) |
| 场景、网络、渲染 | [dsh-scene-network-render-contract](../tools/tests/dsh-scene-network-render-contract.test.py) |
| 批量 SOP 构建 | [dsh-module-preflight](../tools/tests/dsh-module-preflight.test.py) |
| multiparm结构与通道恢复 | [dsh-multiparm-restoration](../tools/tests/dsh-multiparm-restoration.test.py) |

通过 [houdini_test_environment](../tools/houdini_test_environment.py) 创建临时偏好、空 package 环境和目标安装路径；启动目录使用指定安装的 bin。Python 通过 PYTHONPATH/测试入口兼容 H21/H22，不继承用户插件、Qt override 或模型凭据。隔离检查不连接 live，也不加载用户 HIP。

领域改动选对应回归，例如 [node-knowledge](../tools/tests/dsh-node-knowledge.test.py)、[参数与绑定](../tools/tests/dsh-parameter-controls.test.py)、[控制恢复](../tools/tests/dsh-control-state-restoration.test.py)、[COP](../tools/tests/dsh-cop-contracts.test.py)。不机械把每个领域套件加到普通模块整理上。

功能回归验证真实接口和错误；GUI 验证页面及运行加载；模型任务评测验证自然采用与结果质量。三者按实际需要运行，结果不能相互替代。视觉验收区分文件与图像传输、显示、模型实际识图。

[图像请求组合](../tools/tests/dsh-image-consumption-fixture.mjs)以`node tools/tests/dsh-image-consumption-fixture.mjs <prepared-runtime> [output-root]`运行固定DSH Web标准preset、原生read_image及真实pi-ai适配器，由自建loopback provider捕获最终HTTP图片。它在同一会话调整并恢复原生requestImagePixelBudget，核对原参考/A/B均保留、请求变体与wire哈希一致、模型句柄尺寸、源文件/持久附件不变及无offload。受控响应不证明真实模型识图或token费用下降；比较像素和编码字节时分别记录格式变化，不把较小分辨率当成较小传输。记录实际Node/DSH/运行修复身份，标准preset通过不扩大为Houdini preset、GUI或正式发行验证。实际模型的预算对照仍沿下述授权试验入口。

任务拆分与完整源组件的方法改动，先用[skill审计](../skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs)、preset组合与下述`--context-loop`验证注册、资料路由和实际模型输入。自然采用另用同模型、同要求、同预算的独立工程对照：观察源组件的局部检查是否影响后续构建，再执行换源、改布局、局部细化或共享尺寸变化，检查最终消费者与修改范围；用另一类任务验证领域外适用性。源本来应为Box、共享连续表面和先代理后细化都是合法反例，不按节点数、截图数或技能关键词评分。审查需包含能推翻自报成功的情况，例如实际开口被封堵但模板未变、同包围范围的错误形状和局部遮挡；模板或生成公式通过不能升级为最终实体关系通过。trace的原生图片与显式读图记录通过nextToolStep定位观察返回后提交的下一动作，引用原时间线而不推断修改、因果或成功；并发中先提交后返回的动作不算后续决策。受控模型能取到技能不证明自主分治或质量提升，保留质量、返工及计算成本的实际证据，过程产物留会话/临时目录。

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

资产主入口与后加模块用[dsh-asset-edit-entry](../tools/tests/dsh-asset-edit-entry.test.py)在隔离H21/H22验证：从当前模块值初始化公共控制，数值/开关单向引用，SOP主控驱动真实COP图层与最终材质消费者，两个COP容器的上层分组、原入口说明更新，以及同版本独立重开。跨进程图层对照使用完整buffer和明确元数据，不能把包含进程内identity的观察hash当跨进程内容标识。上述真实DSH的`--surface-method`同时验证参数与网络交接资料的按需消费。机制通过不证明自然模型会选对公共参数，或实际GUI布局已经验收。

孔径检查的能力范围由[dsh-quality-contracts](../tools/tests/dsh-quality-contracts.test.py)核对：几何违反条件、检查能力/预算不足、非法参数分别保留不同结果；能力不足不回滚同批正常修改。完整帮助的runtime_limits与执行来自同一维护源。目录回执导出的interface_observation由上述真实DSH循环同时核对原生/嵌套消费，不能只检查Python返回字典。

教程媒体使用[视频回归](../tools/tests/video-tutorial.test.py)核对分离轨导入、源变化、时间依据、部分转录与续跑；[离线Host处理](../tools/tests/video-process.test.mjs)核对新输出/导出锁目录的文件策略、精确参数、私有执行工具和取消进程树，[真实DSH离线处理](../tools/tests/dsh-video-process-smoke.test.py)核对选中执行器运行时与原生/PTC消费。[Host转录回归](../tools/tests/video-transcription.test.mjs)核对DSH路由/凭据、工作区策略、子进程取消及敏感值不进入回执。[真实DSH转录](../tools/tests/dsh-video-transcription-smoke.test.py)用合成媒体和本地HTTP服务贯通实际Python、设置持久化、原生/PTC工具和成功片复用，不调用收费模型。[教程设置Qt检查](../tools/tests/dsh-video-settings.test.py)复用源码GUI驱动核对实际页面注册、配置保存/切页重开、依赖检查与宽窄布局；不把包装驱动中未执行的其他检查列作通过。真实教程另核对实际音画、模型取得的信息、可编辑工程、控制与独立重开，不能用上述接口通过代替成品质量。

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

HDA正常界面比较与真实覆盖拒绝用[dsh-hda-lifecycle](../tools/tests/dsh-hda-lifecycle.test.py)；Sticky Note的归属、局部维护、Raw Gate和失败恢复用[dsh-network-notes](../tools/tests/dsh-network-notes.test.py)；已有pane/Qt窗口/停靠面板发现、精确裁框、当前内容与用户状态保持用[dsh-ui-surfaces-gui](../tools/tests/dsh-ui-surfaces-gui.test.py)，包含真实HTTP发现→目标截图→同票据恢复。[headless拒绝](../tools/tests/dsh-ui-capture.test.py)与[HTTP边界](../tools/tests/dsh-bridge-transport.test.py)分别核对无GUI、旧node/view/尺寸输入与请求事实。界面测试在自有GUI检查实际目标与图像，生成文件存在不代替人工识图，不连接用户live或改用户HIP。

跨层修改应验证消费方最终取得的状态，局部函数返回或静态配置存在不足以证明链路可用。入口/preset/client改动用精确DSH的实际模块图确认根前端与工具scope，再由真实页面确认内容视图和选中任务；工作区切换同时核对DSH store中的session、preset、cwd及workspace成员。入口可用空会话验启动，但Trace页需要普通有内容会话验收。Host组合检查的`--context-loop`使用自有HTTP Bridge夹具与脚本化模型适配器，核对真实DSH最终请求中的错误、未决回执、后台任务和上下文更新；可用`--outcome-fixture`接入隔离HOM导出的真实回执，核对捕获的操作异常、fallback和验证状态。不调用收费模型或用户Houdini。相关入口为[Host组合](../tools/tests/dsh-host-smoke.test.py)和[真实页面导航](../tools/tests/dsh-client-navigation.mjs)。

内嵌页面使用[真实源码Qt验收](../tools/tests/dsh-source-webview.test.py)在新Houdini GUI中检查认证、实际工作区选择、模型菜单、Trace与原生交互、草稿和文件预览，并核对深浅主题浮层/目标栏的实际背景、H21输入区渐变与原生点击后的系统剪贴板内容（检查结束恢复原MIME数据）。此入口不调用模型、不连接用户Bridge、不加载或保存HIP，并确认自有GUI与Qt后代退出。普通Chrome检查不能替代Qt结果。

[真实Qt工具循环](../tools/tests/dsh-source-webview-interaction.test.py)复用同一驱动，以本地[受控流式提供方](../tools/tests/dsh-source-webview-provider.mjs)核对原生输入、实际工具回执、停止、丢响应后的原请求查回和页面重载后同一任务继续。图像检查核对真实render_view原图、DSH附件、HTTP请求中的像素身份；对话工具行由DSH原生展示，普通Houdini调用不另加内嵌图库，图片查看使用DSH原生read_image或文件展示；受控回复不证明模型语义识图。示例HIP及声明HDA依赖在独立项目重开后检查控制、实例保持与保存，不连接用户live或调用收费模型。

从MSIX打包的开发宿主运行GUI验收时，测试CLI先调用`reexec_unpacked_test_cli()`。继承宿主包身份会使Windows使用打包程序DLL搜索规则，即使PATH含HFS/bin也可能找不到Qt helper依赖。此入口使用Windows桌面应用启动属性，并在继续前核对新进程没有包身份；保留标准输入输出、退出码及自有进程树清理，不修改用户安装、机器环境、令牌或Chromium沙箱。普通桌面CLI原地继续。实现与回归分别在[测试环境](../tools/houdini_test_environment.py)与[隔离回归](../tools/tests/dsh-test-environment.test.py)。依据为[Windows DLL搜索规则](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)和[桌面应用进程属性](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)。


执行结果应同时核对原生与Code Mode嵌套事件、取消/未知/过期回执及现场runtime身份；展示投影不得丢失无execution的真实回执。trace用真实当前版本日志校验可见内容、调用关联和解析缺口，不以旧fixture或旧session文件名证明新格式可读。用例保持针对已观察到的边界，旧策略删除后保留操作、权限和恢复检查，移除只证明策略存在的断言。

普通大结果的历史引用使用原生/嵌套工具回执中记录的路径，文件仍须通过hash校验；不能因Save As改变cwd而只查新目录，也不能从用户正文取得任意文件路径。[结果详情回归](../tools/tests/result-details.test.mjs)覆盖跨目录、伪造来源和篡改拒绝；`dsh-scene-recovery-e2e --save-as`在真实DSH/浏览器/HOM组合中同时核对原目录的普通/嵌套详情在进程重开后可读。

运行缓存身份包括[修复声明](../deployment/dsh-runtime-fixes/manifest.json)中inputFiles列出的依赖锁与构建器，不能只比较补丁hash。依赖更新保持精确DSH版本，更新开发与发行两份npm锁；[输入身份回归](../tools/tests/runtime-fix-inputs.test.mjs)核对Node/Python一致和仅依赖变化时的缓存失效，[文档依赖回归](../tools/tests/dependency-runtime.test.mjs)通过实际文档组件解析的fflate检查普通ZIP与畸形ZIP64，可传新缓存根目录验证发行组合。缓存准备不更新正在运行的Host，正式安装/Qt资格验证仍单独执行。

节点交付的定向入口为[Host路由](../tools/tests/node-delivery.test.mjs)、[原生/嵌套卡片投影](../tools/tests/node-delivery-client.test.mjs)、[持久标识HOM](../tools/tests/dsh-node-delivery.test.py)及[排队取消HTTP/HOM](../tools/tests/dsh-node-navigation-cancel.test.py)。跨层修改还需在精确DSH组合和新建的隐藏GUI进程中，由真实Agent工具循环产生原生/嵌套回执，选中对应任务点击实际卡片，回读网络/参数页；重开同HIP并改名后再点击旧卡片，切HIP核对错误提示，暂停队列后切任务并恢复队列核对旧导航没有生效。局部模拟通道不能替代这条连接；测试脚本、截屏、完整结果和运行目录留在仓库外证据目录。服务框保存重开由[服务框回归](../tools/tests/dsh-render-service-box.test.py)核对标题、固定边界、真实成员与用户节点位置。

## 隔离开发工具

模型对照用run-modeling-trial的`--reasoning-effort`与统一的`--max-output-tokens`固定请求参数；自定义PI模型确需声明能力时，另显式传`--reasoning-wire-value`，只改隔离副本。开始模型请求前核对原生resolveModelInfo的实际defaultEffort。缺推理声明不等于后端没有推理：适配器可能只省略推理参数，不能从模型名称补造能力。回环HTTP测试[dsh-image-consumption-fixture](../tools/tests/dsh-image-consumption-fixture.mjs)核对真实reasoning_effort、附件身份及请求变体；实际模型语义另验。`--smoke --scripted-smoke --smoke-continuity --followup <文件>`通过真实DSH和Houdini跑两轮同网络创建/修改，模型流完全本地拦截；[共享连接反例](../tools/tests/dsh-shared-continuity.test.py)保留其他执行端/工程及跨进程动作拒绝。

源码文件同步复用[参数补丁回归](../tools/tests/dsh-parameter-patch.test.py)，核对UTF-8原文、完整source写入、相同内容不写、过期hash整批零写入及原有恢复。大型控制回执可由dsh-scoped-observation导出`DSH_HDA_PRESENTATION_FIXTURE`到诊断目录，再用dsh-host-smoke的`--context-loop --geometry-fixture <回执>`验证实际provider取得geometry_scope、完整恢复证据及原生/嵌套一致性；导出变量只用于测试夹具，不是生产状态。

[hda-delivery-check.py](../tools/hda-delivery-check.py)在新 hython 中加载声明 HDA，按 manifest 创建实例、设置参数、调用按钮并检查几何/参数/错误。判据应能区分正确与错误结果，例如尺寸控制检查 bounds_size，而非只有点面数。

传 `--output` 时完整报告写入指定文件，stdout 保留每个用例的结果、实测量、错误和进程状态；原生内部节点清单改为计数及报告内 JSON Pointer，并返回文件路径/hash/字节数。未指定输出文件时保留完整 stdout。不要将输出丢到 `Out-Null` 后只看退出码，也不要把新实例求值和包围尺寸通过当成部件关系或成品质量通过。[报告呈现回归](../tools/tests/dsh-hda-report.test.py)覆盖大清单中后部失败、未知诊断和归档失败；[实际CLI回归](../tools/tests/dsh-delivery-geometry.test.py)在隔离H21/H22对照 stdout 与磁盘报告及正确/错误几何判据。

原库版本维护用[HDA版本机制回归](../tools/tests/dsh-hda-versions.test.py)覆盖多定义保留、同库追加、参数/关键帧/表达式/锁定/连线、失败恢复和权限；[DSH版本维护贯通](../tools/tests/dsh-hda-version-smoke.test.py)以`--runtime-cache <精确DSH缓存> --hython <目标hython>`启动隔离真实Bridge和DSH会话，核对普通/嵌套调用的回执、会话/现场身份、新旧定义行为及下一进程Package发现。规划模型为受控夹具；这些检查不证明用户GUI版本菜单、任意回调或自然任务自主采用。

工具制作的机制检查包括[真实工具目录](../tools/tests/dsh-tool-catalog.test.py)、[共享定义与分叉](../tools/tests/dsh-hda-definition-ownership.test.py)、[参数组件](../tools/tests/dsh-hda-ui-components.test.py)、[原生Package配置发现](../tools/tests/dsh-package-discovery.test.py)和[注册/运行态失败](../tools/tests/dsh-tool-packages.test.py)。[发现GUI](../tools/tests/dsh-package-gui.test.py)核对已配置、条件与实际加载的不同状态；[Package GUI](../tools/tests/dsh-tool-packages-gui.test.py)以普通包名JSON直接指向唯一源目录，核对干净启动发现/当前加载、HDA/Shelf/Panel实际来源与公开入口、旧内容保持，以及启停不改变配置或源。已有包新增资源后从新进程验证，不靠隐式reload证明更新安全。Shelf和Viewer State需要回到Houdini外层事件循环后再验状态；installFile/sys.path不替代此路径。不同载体的结果保留实际范围，不从固定例子外推任意工具泛化。

```powershell
python tools/hda-delivery-check.py --manifest path/to/tool-check.json --hython D:/houdini/bin/hython.exe --output path/to/report.json
```

[isolated-houdini-check.py](../tools/isolated-houdini-check.py)在独立进程执行可信builder或明确保存HIP的副本，经Bridge完成cook/cache/ROP检查。manifest在script与hip中二选一，files保留声明依赖的相对结构，checks指定实际输出；`--trusted`沿用户授权的工程/代码计算范围，不是未知HIP的沙箱。产物目录是仓库外的新目录，report.json与worker-result.json保留来源hash、实际执行、部分进度和产物。`--status --output-dir <run>`只读最后记录，不当作进程存活；`--cancel --output-dir <run>`请求停止该run自有进程树，不启动或重试任务。默认取消文件在run内，原输入保持核对，未保存现场和未声明外部依赖不包含在快照证明中。

[快照回归](../tools/tests/dsh-snapshot-worker.test.py)在H21/H22核对真实图像/ROP、来源不变、缺输出、启动前/运行中取消；[输入回归](../tools/tests/dsh-isolated-manifest.test.py)覆盖状态身份和不完整回执。大型最终输出的[选择回归](../tools/tests/dsh-scoped-observation.test.py)使用百万面背景与明确目标组，验证正例、错尺寸、无组拒绝和未选部件漂移。整件恢复使用[流式BJSON指纹](../houdini/python3.11libs/dsh_bgeo_fingerprint.py)，按本机SideFX `UT_JSONDefines.h`读取；[指纹反例](../tools/tests/dsh-bgeo-fingerprint.test.py)验证写入时间可变化，但与日期共用字符串token的用户属性仍不能被忽略。大型流指纹不承诺任意编码/属性表布局变更等价；无法建立相同完整内容时保留恢复未确认。

```powershell
python tools/isolated-houdini-check.py --trusted --manifest path/to/check.json --hython D:/houdini/bin/hython.exe --output-dir D:/checks/run-001 --timeout 120 --memory-mb 4096
```

[isolated-worker.py](../tools/isolated-worker.py)及 [Houdini worker](../houdini/python3.11libs/dsh_isolated_worker.py)是开发评测使用的自有新进程入口；[worker 回归](../tools/tests/dsh-isolated-worker.test.py)验证明确 IPC、启动与回收。[delivery-audit](../tools/delivery-audit.mjs)只在开发评测中从会话回执读取交付事实。它们不进入模型的生产工具目录。

隔离工具通过自有进程句柄和 Windows Job 管理超时、取消及进程树内存。报告与退出状态都要读取；不把启动成功当作负载完成。任意 Python、回调、绝对路径文件和外部服务的副作用不属于场景恢复保证。

收费任务只在用户授权的模型与预算范围内运行 [run-modeling-trial.py](../tools/run-modeling-trial.py)。使用隔离任务目录、精确 DSH/Node/Houdini 和明确provider/model，只复制所选路由及必要credential reference，不修改用户设置或live。教程试验通过显式`--service-profile`加入单个转录服务与用途选择，不复制整个用户配置；服务说明只含provider/api/baseURL/apiKeyEnv/model/models及可选python。DSH自定义服务商需要非空的真实聊天模型目录`models`；独立的`model`填写实际转录模型，不把ASR伪装为聊天能力。密钥仍由隔离凭据引用或指定环境变量解析。时间上限不等于费用上限，按提供方实际价格/套餐边界核算；DSH observer的usage事件与未知费用分别记录。评审答案不进入生产提示词或用于未见题调参。

验证自然复刻能力时使用`--no-feedback --approval-policy never`且不传followup；只提交初始用户目标、来源与环境事实，运行中不向作者补充接线、参数、截图答案或几何/效果修正。冻结初始输入与禁止外部反馈不限制作者自主调查：作者可以只读原片、回查原分析，并在自己的`dsh-artifacts/analysis/`中抽取画面、补证及整理；原始资料不改写，成功音频不重复上传。任务说明不能用“启动后不补资料”同时指代外部答案介入和作者自主补证；范围有歧义时，不将该运行计作主动补证能力通过。工具缺陷在运行后回到系统维护源修复，用新快照验证，受干预运行不作为独立能力证据。复用已有分析与只给视频的冷启动分别报告。
驱动保持workspace-write并核对原生权限回执；取消用运行目录的cancel文件或Ctrl+C。到期、未决审批与失败明确记录，不自动扩大权限或代替作者续跑。输入、代码、依赖身份与预算启动前固定，结束后核对；自有进程停止与隔离凭据副本清空分别确认，不能由driver退出0代替。对应[生命周期回归](../tools/tests/modeling-trial-lifecycle.test.py)不调用HOM或收费模型。

可视化试验须以真实DSH `llm.resolveModelInfo` 的inputModalities确认当前路由，而非从准备配置摘要推断。锁定DSH的pi-ai模型配置使用`input`，发现/解析结果使用`inputModalities`；两者不能原样互换。原生GUI观察用`--show-gui`，`--observe-model-images`通过透明observer记录实际LOOP图像引用及供应商完成，`--probe-frontend`检查同一真实会话的QtWebEngine消费。供应商单独图像探针、模型实际收到工具图像、前端预览及工程重开分别核对，不互相代替；观察器仅用于隔离开发试验，不进入生产插件图。

## 分支与接续入口

接续或合并前先核对 `git status --short`、`git branch -a -vv`、`git worktree list` 和相关提交，再读目标分支 handoff。不同工作树的文档描述各自提交，main 不代表全部尚未合并的工作。

现役设计原位替换，不在 docs 追加版本叙事、试验流水或 session 记录。历史保留在 Git；日志、耗时、截图、评测 HIP 和本机材料放会话、CI、tools/out 或仓库外目录。

### 交接文档生命周期

handoff 是唯一滚动交接入口，只保留下一次接续仍需完成的动作、阻塞和验证缺口。每项写现状、下一步、移除条件和仓库内入口；完成后删除整项。保持一份文件，不按日期分叉，不把历史成功继续标为活动项。没有待办时写“当前无待交接事项”。

## 运行与发行

Host/Bridge/helper 变更通过 `Version & Updates → 高级设置 → 运行诊断 → 修复并重启运行环境` 加载；package/menu/WebView 变更需要完整重开 Houdini。源码构建通过与 live 已加载分别判断；只有实际版本、握手和用户路径验证后才声明运行更新生效。重启用户进程和修改用户 HIP 需要当前授权。

### 发行操作与信任配置

正式安装流程见 [setup](setup.md)，支持组合及发行门见 [兼容设计](dsh-update-compatibility.md)。发行包使用 deployment 锁定的完整依赖树和 Node 分发摘要；普通源码 build 不等同用户发行安装。

正式发布前覆盖 H21/H22 必要执行和安装入口。发布使用 [build-release](../tools/build-release.py)、独立 [finalize-release](../tools/finalize-release.py)和受信公钥；私钥只存在于签名环境。main push、tag、Draft 均不构成正式发布。

```powershell
python tools/run-deployment-tests.py
python tools/run-deployment-tests.py --hython D:/houdini/bin/hython.exe --hython D:/Houdini22/bin/hython.exe
```

这是发行/部署回归入口，日常按改动选择检查。真实安装与 Qt 页面验收在新的自有进程和临时目录中执行；当前缺口只记 handoff，不在这里积累每次尝试。

[签名包部署验收](../tools/tests/dsh-deployment-e2e.test.py)使用实际离线包、独立安装与数据目录，检查精确Node/DSH、profile、认证RPC和所选H21/H22 Bridge。可选`--previous-bundle <旧受信包目录>`再覆盖旧包自身入口与profile准备、新版失败快照保留和重试、各版独立数据、回退不合并以及同版重新安装恢复损坏的私有媒体工具。测试数据只证明文件与版本选择保持，不证明DSH旧会话格式转换或模型续跑。正式Qt入口另用[发行GUI验收](../tools/tests/dsh-gui-release.test.py)：从真实Houdini菜单打开独立工作台，等待工程绑定完成，以当前执行端登记的任务核对[实际Qt页面](../tools/tests/dsh-release-workbench-browser.mjs)、工作目录、认证RPC、置顶状态及重开复用，并正常退出自有工作台。每个Houdini版本使用独立工程目录；不能按同目录或上一轮会话猜测选中任务，也不能用源码页面检查替代签名安装。
