# DSH 与插件版本适配

本项目通过DSH公开接口加载，当前精确目标是 **0.2.1-rc.2**。选择源为[兼容清单](../dsh-runtime-compatibility.json)，依赖锁在[package-lock](../package-lock.json)和[受管锁](../deployment/package-lock.json)；cordis为4.0.5，schemastery为3.18.5，zod固定4.4.3。

DSH 0.2.1默认模型目录包含`deepseek-flash`（显示名`DeepSeek-V4.1-Flash`，1017快照），插件不固定模型名，按DSH当前配置选择。0.2.1还提供可选的DeepSeek Search/Fetch API提供方；`web_search`/`web_fetch`的工具schema不变，换提供方不改变模型调用方式。

网络继承由DSH的http-proxy包维护，公开proxyRouteFor现在异步返回当前请求的确定路线；配套web-fetch-http与本插件探针同步消费，不能混装旧版同步调用者。

当前组合还包含[运行修复声明](../deployment/dsh-runtime-fixes/manifest.json)指定的同版本源码修复。唯一修改源为声明中的补丁，基线固定到上游提交；不覆盖正在运行的缓存，不用alpha版本或强制依赖升级代替验证。修复覆盖Windows自有目录的沙箱标签初始化、平台临时目录、只读权限诊断、Windows系统代理/PAC继承、受文件策略保护的二进制下载、命令结果呈现、Gateway连接活性及原生jobs完成通知和原值保留。

Gateway心跳同时观察Pong、入站消息、等待过发送缓冲区的完整写入，以及大帧发送队列的实际减少；大帧未发完不等于传输停止。尚未写出的Ping只保留一个，不继续堆积；没有实际进展的连接仍按原心跳预算退出，立即完成的持续发包不制造对端在线证据。退出日志只记录时间、缓冲字节数和Ping写入状态，不记录请求正文或凭据。此传输状态与Houdini执行端、场景加载代际及请求是否完成分别判断。

原生jobs的取消仅在实际killed后抑制完成通知；取消竞争后仍completed/failed的结果继续通知。job_output持久保留canonical原值，模型展示限额不截坏执行事实。registry在终态后释放生产者控制引用，首次消费结果后释放已交付正文，继续保留任务列表、状态和输出ring；完整回执仍由原生会话日志维护，不由Houdini插件另建回收层。

会话目录接续由同一DSH补丁维护：`workspaceRegistry.relocateSession`在模型/工具步骤边界沿唯一持久写入器更新工程目录，并在同一持久迁移意图内追加原生`working-directory/change`事件，再调整工作区归属。已加载与冷会话都保持会话ID、创建时间、已有事件字节、置顶与归档；文件工具、模型上下文和附件搜索从原生工作目录投影取得新位置，原生会话摘要发布新工程目录。步骤入口若已组装旧目录的提示/运行上下文，则重新组装后才准入模型请求，不重复执行步骤监听器。原日志和写锁保持原物理位置，后续追加使用该位置，不按新cwd生成第二份历史。中断的迁移意图由DSH工作区域数据恢复，不由Houdini插件另建账本。已开始的命令/工具保留启动时的范围，后续步骤使用新目录；工程依赖文件不会因此自动搬运。

`SessionHeader.cwd`是当前文件工作区目录，由迁移操作替换；DSH文件操作的实际cwd由原生工作目录服务维护。迁移完成后主动cd可以与工程目录不同，重复选择同一文件目录不覆盖这个选择，Houdini现场选择本身不调用目录迁移。Session事件格式仍为4，旧历史可读取；发生目录迁移的会话要求带此适配的读取器，不能将它交给仍校验“cwd必须等于物理存储目录”的旧DSH组合。正式升级/回退须按安装合同保留各版数据，不能用未打补丁的同版本包替换此运行组合。

原生提问卡沿同一源码适配维护布局：补充说明与标题对齐，选项description独立放在标签下方并保留换行，长路径在卡片内部折行。单题不显示分页，多题仍保留原导航；选项、自由文本、提交和取消沿用DSH问答协议，插件不建立第二套恢复面板或修改既有回答。

源码使用 `npm run runtime:prepare` 从受管依赖锁安装独立缓存，再从固定上游提交应用补丁、编译并记录文件摘要。构建入口为[准备器](../tools/prepare-dsh-runtime.mjs)和[编译器](../tools/build-dsh-runtime-fixes.mjs)；发行组装复用同一入口。默认启动只选择匹配修复声明的缓存，完整文件检查在启动worker执行，界面选择只读小型元数据。运行记录保留本次启动实际验证的修复身份；包版本号相同不能代替修复已加载。

ChatGPT订阅沿DSH原生authorization、credentials和llm-pi-ai接入；当前固定组合补充提供方的安装身份、登录提交、账户安全描述和退出能力。插件通过已加载的`piAiAccounts`服务消费它，不从源码目录动态导入另一份同版本依赖。OAuth协议实现只维护于[pi-ai源码差异](../deployment/dsh-runtime-fixes/pi-ai.patch)，DSH接线继续在[原生差异](../deployment/dsh-runtime-fixes/fixes.patch)；固定来源、包integrity和编译范围由同一manifest声明，[依赖编译器](../tools/build-dsh-dependency-fixes.mjs)供源码缓存及正式组装共用。不能直接修改运行中的node_modules，或仅启用登录按钮却省略配套协议修复。

提供方验证ID token的签名、issuer/audience、有效期、nonce及返回账户，使用已保存的client/host身份重新授权；续期与退出沿原生凭据锁，取消后的迟到登录不提交凭据。退出分别返回服务端撤销与本机清除事实，保留不含token的注册身份以便后续登录。设置界面仅消费账户白名单与授权交互，不读取或保存access/refresh token；临时授权链接和返回信息不进入模型上下文。机制依据见[OpenAI登录合同](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)与[账户和会话](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)。真实账户权限和网络回调仍须独立于离线协议测试验证。

`web_fetch`负责网页文本，`web_download`经同一个网络提供方取得完整字节，再由DSH文件系统检查当前会话范围并原子创建新文件。它拒绝已有文件、只读/范围外目标、非成功HTTP和截断下载；图片仍须解码和实际观察。公开跨域重定向逐跳重新验证地址和路线，拒绝私网目标、URL凭据、非HTTP(S)、HTTPS降级和过长跳转；每跳实际来源、直连/代理和HTTP状态进入回执，代理凭据不进入这些诊断。传输失败保留底层错误码，不自动换路。

Windows工作区授权逐对象核对已有普通内容，补齐能力权限和Low安全等级；使用固定对象句柄读写原生安全描述符，避免目录级自动传播影响外部硬链接。已有链接、多硬链接文件、受保护权限、其他所有者及显式非Low标签保持边界；临时标签写权限不继承，失败恢复原权限，撤销按对象移除对应能力。新内容继承所在目录，已初始化工作区的授权由Host缓存；运行中从外部搬入且保留原权限的内容需重新准备，不监控整盘文件事件。

原生命令保存 `shellExit` 元数据，前台命令的渲染结果还保留末尾 `process-result` 记录；嵌套调用同时保留实际进程值及子调用回执。`hasStderr`只表示有标准错误输出，退出0时聊天和Trace仍提示诊断，不伪造失败退出码。脚本捕获错误后仅向stdout打印文字不构成系统可确认的失败；stdout中的伪造退出标记也不能覆盖执行事实。`isError`继续表达工具传递错误。

## 运行职责

DSH负责模型调用、会话与持久化、Agent循环、任务/计划、通用工具、资源呈现和上下文生命周期。插件负责Houdini执行、信息与观察，通过[dsh-adapter](../src/dsh-adapter.ts)集中接入真实消息与工具日志接口。

唯一的Houdini preset由[生成器](../tools/gen-agent-presets.mjs)使用同版web-app标准声明生成，通过插件bundle patch注册到agent-preset-registry。内置模式在该组合禁用；插件没有dev/product模式或全局重复挂载。领域方法按需读取。persona模板只引用DSH循环注册的`{{model}}`/`{{provider}}`；工作目录由工作目录服务作为原生用户上下文提供，不引用未注册的`{{cwd}}`（未解析会在任何模型请求前失败，[preset检查](../tools/tests/dsh-preset-parity.test.mjs)静态阻止回归）。

## 公开接口

| 接入 | 当前合同 |
|---|---|
| 配置 | Cordis 4.0.5与精确DSH包，插件组合在package.dsh.bundle.patch声明 |
| 模式 | dsh-agent-preset声明、registry默认Houdini |
| 消息 | 独立source.kind=dsh-houdini，使用DSH原生context |
| 工具 | defineTool注册，原始结果供程序使用、render负责模型文本、presentationMeta供界面 |
| 嵌套工具日志 | 直接消费DSH持久的meta.canonical；展示正文由原生保留策略处理，不再另写整份日志包装 |
| 图像 | DSH原生附件与模型输入能力；图片展示不代替实际理解 |
| 子进程环境 | 网络转录与诊断复用DSH的scrubbedParentEnv，仅显式转交本次凭据或诊断定位；离线媒体与hython保留更小的必要环境 |
| 客户端 | CJS factory、公开conversation/trajectory与workspace/session接口 |
| 运行历史 | Session格式4，native和PTC调用共用实际执行事实索引 |

原生及PTC工具结果使用DSH持久的meta.canonical；展示spill不改变该原值，插件不再维护另一份PTC日志正文。已存旧文本记录仅作为历史格式读取。原生job_output通过正式live producer标识解码Houdini回执，普通DSH jobs不成为场景事实。模型任务判断不进入执行日志。

图像的原始文件、持久附件和实际模型请求版本分别核对。固定pi-ai路由已提供requestImagePixelBudget、requestImageMaxBytes及maxRequestImageBytes：前两者控制每张请求图的像素预算和编码字节目标，后者限制整次请求的base64图片字节；经DSH原生provider profile设置，不能另建插件缩图或历史图片账本。调整请求版本不改源文件、持久附件和会话中的原参考/A/B；恢复配置后仍应取得原请求版本。像素减少可能伴随编码改变，不能从文件大小、请求字节或分辨率推断token费用或识图质量。通用read_image沿原生自动处理，具体路由的能力和验证入口见[开发维护](development.md)。

## DSH耦合点与升级维护

本表维护现役耦合边界与升级时的查找入口，不记录修复历史或复制运行修复声明中的包清单。
精确DSH选择由[兼容清单](../dsh-runtime-compatibility.json)维护；上游基线、补丁、编译范围和缓存输入身份由
[运行修复声明](../deployment/dsh-runtime-fixes/manifest.json)维护。模块完整索引仍在[系统架构](architecture.md)。

| 耦合类别 | 当前依赖与唯一维护源 | 升级检查入口与判断 |
|---|---|---|
| 同版本上游源码补丁 | 通用Windows权限/网络、下载与命令呈现、会话目录迁移和原生提问布局的修改只维护于[fixes.patch](../deployment/dsh-runtime-fixes/fixes.patch)；基线、产物范围及摘要由修复声明绑定，[准备器](../tools/prepare-dsh-runtime.mjs)与[编译器](../tools/build-dsh-runtime-fixes.mjs)共用，不直接改缓存或复制到插件实现 | 先对照新上游源码判断哪些修复已吸收，再调整剩余补丁与声明；[输入身份回归](../tools/tests/runtime-fix-inputs.test.mjs)核对缓存身份，[运行修复检查](../tools/tests/dsh-runtime-fixes-check.mjs)、[系统网络检查](../tools/tests/dsh-system-proxy-check.mjs)及[原生目录接续](../tools/tests/dsh-workspace-continuity.test.py)按受影响部分验证实际配套运行时 |
| DSH公开Host扩展 | [dsh-adapter.ts](../src/dsh-adapter.ts)维护消息、原生/嵌套工具日志与执行事实的接入；[tools.ts](../src/tools.ts)维护工具注册；唯一preset由[生成器](../tools/gen-agent-presets.mjs)消费同版标准声明，根客户端与preset工具各守自身作用域 | [适配回归](../tools/tests/dsh-adapter.test.mjs)、[preset回归](../tools/tests/dsh-preset-parity.test.mjs)与[真实Host组合](../tools/tests/dsh-host-smoke.test.py)检查公开接口、实际加载的根客户端、preset与工具；包可导入不代替实际组合 |
| DSH原生会话与工程消费 | [绑定投影](../src/executor-identity-projection.ts)是对话当前目标与工程标识的唯一消费源；[scene-recovery.ts](../src/scene-recovery.ts)独立消费保存点与目录迁移，[executor-controller.ts](../src/executor-controller.ts)经原生API创建或定位用户指定会话，不全量匹配历史；迁移能力的实现仍在上游源码补丁 | [绑定投影](../tools/tests/executor-identity-projection.test.mjs)、[路由](../tools/tests/workbench-routing.test.mjs)、[目录跟随](../tools/tests/scene-directory-follow.test.mjs)与原生目录接续检查历史、排队/晚到回执和目录保持；跨层改动再核对真实选中任务及普通/嵌套回执，不以同目录或最近任务代替身份 |
| Qt客户端容器 | [dsh_webview.py](../houdini/python3.11libs/dsh_webview.py)维护浏览器认证、页面生命周期和必要的容器适配；[dsh_downloads.py](../houdini/python3.11libs/dsh_downloads.py)维护下载与用户外链，保留DSH延迟登录popup；[工作台](../houdini/python3.11libs/dsh_workbench.py)维护启动阶段；浏览器补齐只由[生成器](../tools/gen-web-polyfills.mjs)生成 | [导航回归](../tools/tests/dsh-webview-navigation.test.py)、[外链/延迟登录回归](../tools/tests/dsh-external-links-qt.test.py)、[启动阶段回归](../tools/tests/dsh-workbench-startup.test.py)与[真实Qt验收](../tools/tests/dsh-source-webview.test.py)按页面改动选择；核对H21/H22实际浏览器与DSH登录/RPC行为，普通Chrome通过不证明容器可用，模拟登录不证明真实账户授权 |
| 安装与运行生命周期 | 安装、启动和修复共用兼容清单；[dsh_runtime_compat.py](../houdini/python3.11libs/dsh_runtime_compat.py)核对精确运行修复身份，[dsh_deployment.py](../houdini/python3.11libs/dsh_deployment.py)维护签名安装/激活，[安装器](../installer/install.ps1)与[卸载器](../installer/uninstall.ps1)维护本机注册；发行合同唯一见[安装与更新](setup.md) | [版本选择](../tools/tests/dsh-runtime-compat.test.py)、[引导安装](../tools/tests/dsh-installer-bootstrap.test.py)、[部署组合](../tools/tests/dsh-deployment-e2e.test.py)和[前端生命周期](../tools/tests/dsh-frontend-lifetime.test.py)按影响验证；正式发行核对完整签名包在H21/H22的正常入口，磁盘包版本不代替实际Host/Bridge加载 |
| 纯Houdini Bridge与执行内核 | [dsh_bridge.py](../houdini/python3.11libs/dsh_bridge.py)维护HTTP合同、代际与主线程队列；[dsh_execution.py](../houdini/python3.11libs/dsh_execution.py)、[Raw Gate分析](../houdini/python3.11libs/dsh_code_analysis.py)和[ownership](../houdini/python3.11libs/dsh_ownership.py)维护真实执行边界；合同说明唯一见[执行契约](execution-contract.md)与[工具设计](tool-design.md)，不依赖DSH内部会话实现 | [Bridge合同](../tools/tests/bridge-contract.test.mjs)核对Host封装；只有Bridge/执行边界受到影响时，按[开发维护](development.md#修改与验证)选择隔离HOM与H21/H22检查。纯DSH界面、安装或文档修改不机械触发整套HOM/模型评测 |

升级以实际受影响的消费方为准。上游补丁被吸收后，删除已无必要的差异并继续验证现役合同；
公开接口适配、Qt容器问题和Houdini执行问题分别在所属源码处理，不用同版本号掩盖补丁身份差异。
检查方法在本页和[开发维护](development.md)原位更新；待完成的迁移或验证仅写入[当前交接](handoff.md)，
完成即删。变更原因与发布历史由Git和正式Release说明保存，不另建升级日志或并行交接文档。

## 新 DSH 版本的资格流程

先取得实际存在的精确包，检查公开API与组合注册，更新必要适配和锁文件，再构建与运行直接受影响的回归。

[preset检查](../tools/tests/dsh-preset-parity.test.mjs)核对只有一个Houdini声明和同版标准能力；[DSH适配检查](../tools/tests/dsh-adapter.test.mjs)核对原生/嵌套结果与持久历史。一次隔离Host启动确认真实包能加载插件、列出模式与工具，使用自建DSH_HOME和临时端口，不需要收费模型。

Houdini WebView采用H21/H22实际QtWebEngine。源码GUI资格由[真实Qt验收](../tools/tests/dsh-source-webview.test.py)读取实际浏览器版本、界面交互和文件资源，不以Chrome或普通Qt窗口替代。测试启动器按[开发规范](development.md)排除开发宿主的MSIX身份继承。修复Host与Bridge、重开客户端以及正式安装组合的验证各自说明；编译通过不代表已有进程加载。已知浏览器接口补齐由[webview](../houdini/python3.11libs/dsh_webview.py)与[polyfill生成器](../tools/gen-web-polyfills.mjs)管理，不修改上游缓存。

内嵌视图关闭背景模糊时，同步将DSH共用菜单材质、浮层和分组标题底色改为随主题切换的不透明色，涵盖使用伪元素的目标栏；不改变遮罩、禁用态或悬停效果的透明度。H21的Chromium 108不支持`color-mix()`，活动对话输入区的渐变使用等价透明起点，避免整条背景失效。样式消费主题token与稳定DOM属性，不依赖构建生成的类名。

页面显式开启Qt的`JavascriptCanAccessClipboard`，让DSH共用复制入口写入系统剪贴板；`JavascriptCanPaste`保持默认关闭，不自动授予读取权限。回归使用实际用户/助手消息与Markdown代码块复制按钮的Qt鼠标事件，核对系统剪贴板内容并恢复原MIME数据；按钮出现或点击回调执行不代表复制成功。

## 正式发行单元与发布门

正式发行交付一个精确组合：插件源码提交、Node、DSH、完整依赖、平台/Houdini支持范围以及文件摘要。受管安装使用签名release.json和离线包，详见[安装](setup.md#正式发行与受管安装合同)。

main push、tag和Draft不构成正式发行；发布端构建和校验组合，用户安装不运行源码build。旧版本回退不改写用户工程。普通开发按改动选择必要检查，正式发行补正常入口与受管安装验收。

当前未验证的正常加载、模型质量与发行事项在[交接](handoff.md)维护。

