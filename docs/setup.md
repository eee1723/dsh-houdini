# dsh-houdini 安装、更新与开发

Windows x64受管安装把插件、Node、DSH和完整依赖作为一个签名发行单元。普通用户不运行npm/build，不单独升级DSH。
源码checkout、预构建包、已选版本与正在运行的版本分别判断。发布前尚欠的真实用户路径见[交接](handoff.md#h-01-用户入口与受管发行)。

## 普通安装

1. 从[正式发行页](https://github.com/eee1723/dsh-houdini/releases/latest)下载完整 `dsh-houdini-版本-offline.zip`，解压后双击 `Install.cmd`。
2. 安装器按用户权限注册H21/H22菜单，不修改系统Node、Python或全局PATH。
3. 完整重开Houdini，选择 **DSH-Houdini → Open Workspace**。后台校验并准备隔离profile后启动配套DSH。
4. 首次在DSH页面配置模型/API凭据。受管安装不自动迁移或清空既有 `~/.dsh`，此前独立DSH原样保留。

完整包包含运行依赖，可离线安装；模型服务仍依赖用户配置与网络。
轻量 `dsh-houdini-installer.zip`，或clone/源码ZIP中的Install.cmd，只部署管理器；在面板检查正式Release并安装完整组合。
仓库已有正式签名Release；管理器仍只接受受信签名和完整资产。发行不可用或公钥未配置时如实报告，不将main或测试候选伪装成可安装正式版。
GitHub自动生成的Source code.zip不是完整运行包；源码构建是下文的显式开发路径。

### 注册位置与引导修复

默认安装根为 `%LOCALAPPDATA%/DSH-Houdini`，偏好目录使用Windows真实Documents文件夹，支持重定向/OneDrive。
默认注册21.0和22.0；支持指定偏好目录与安装根：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PrintOnly
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PackagesDir 'D:/HoudiniPrefs/packages' -Root 'D:/DSH-Houdini'
```

`HOUDINI_USER_PREF_DIR`优先，必须含`__HVER__`占位符，安装器分别展开为21.0/22.0后注册对应package，否则Houdini会忽略它；显式目录可用-PackagesDir。ExecutionPolicy只作用于该次引导进程，不永久改系统策略；
企业策略禁止脚本时遵循管理员要求，不关闭安全功能绕过。此前package原子备份到安装根的package-backups。
重复运行可信安装器可修复损坏管理器：复制到新目录再切换注册，不覆盖已加载模块。
完整包在检测到标准Houdini安装中的内置Python时直接暂存；未检测到时，在面板选择原解压目录的release.json。
已完成安装不依赖原下载解压目录，不要求系统Git、Node、额外Python或管理员权限。
启动桩按[SideFX脚本位置](https://www.sidefx.com/docs/houdini/hom/locations)分别生成在python3.11libs/pythonrc.py和python3.13libs/pythonrc.py，共享同一份Python模块实现。

## Version & Updates（版本与更新）

源码和受管安装共用中文主面板。默认只显示版本、更新状态和「检查更新」；发现适用的新版本后才出现安装或发行页入口。未检查、检查失败、没有正式发行和已是最新分别显示；源码版本只是磁盘 package 版本，不认证实际加载状态。
有下次启动待切换版本时才显示第二列。安装路径、源码更新说明、维护操作、运行诊断、日志和共享执行端实验入口统一收在「高级设置」。无适用对象的修复/回退/取消切换操作隐藏，正在工作时才显示进度与取消。

| 操作 | 行为 |
|---|---|
| 检查更新 / 安装更新 | 只查明确发布的稳定Release；在线安装要求不可变Release、受信签名与完整资产 |
| 安装本地包 | 选择与ZIP、release.sig.json同目录的release.json；离线也要求受信签名 |
| 修复当前版本 | 重新下载并暂存当前版本完整包，不升级DSH/latest、不覆盖损坏目录；离线时选择同版本地包 |
| 检查安装文件 | 检查全量文件哈希、缺失/多余文件、包版本和依赖锁；通过不证明live加载 |
| 回退到上一版本 | 下次启动使用上一套程序及其独立数据，新版数据保留但不自动合并 |
| 取消下次切换 | 取消待切换状态，不删除版本、数据或下载 |
| 运行诊断 | 查看实际运行版本、连接和依赖；修复并重启仍受活动任务保护，不重复插件发行检查 |

网络失败/限流不冒充已是最新。Draft、prerelease、push与tag不进入默认更新通道；目前没有面向普通用户的预览通道。
后台下载/解压可取消；提交pending是原子步骤，提交后使用「取消下次切换」取消下一次切换。
独立管理器不依赖Node、DSH或插件lib，缺依赖时仍可打开。

### 网页抓取与代理诊断

在 **高级设置 → 运行诊断 → 联网诊断与代理设置** 中，先读取配套 DSH 的原生启动配置，再按需测试公开网页。测试使用同一精确 DSH、当前 DSH_HOME 和工作目录的独立新进程，不续跑会话、不调用收费搜索，也不证明已经运行的 Host 已加载新配置。搜索组件是否安装、网页抓取实际结果、本地 Bridge 路由分别显示；搜索返回来源链接不等于网页正文已读。

公开域名在 Fake-IP 网络环境中可能解析到 `198.18.*` 等非公网地址。DSH 的直连抓取会拒绝该地址；不要关闭地址检查或把保留网段改成公网。可将当前 Windows 手动 HTTP 代理作为建议填入，核对后明确保存到实际 **DSH_HOME/.env**。系统代理不会自动覆盖 DSH：启动环境和用户 `.env` 的最终优先级由配套 DSH 自己解析，界面显示生效来源。只保存所填协议，保留其他配置、注释、ALL_PROXY 和 NO_PROXY；留空不删除旧值。含凭据的代理地址在诊断与确认中脱敏。

代理配置只影响下次启动的 DSH。此入口不改系统全局环境、不热改或重启当前服务；有进行中的任务时先结束并保存，再按既有运行环境修复入口重启。也可在 DSH 用户 `.env` 中手动配置 HTTP_PROXY/HTTPS_PROXY；项目目录的 `.env` 不能携带代理设置。受管安装使用本版本独立数据目录中的 `.env`，不修改旧版或独立 `~/.dsh`。

代理模式将域名解析与目的地路由交给用户信任的代理，直连仍执行原生 DNS 校验和地址固定。HTTP(S)/URL 凭据检查、非公网 IP 字面地址拒绝、loopback 直连、重定向限制仍保留；不能把使用代理描述为与直连完全相同的 DNS 验证。上游尚不自动识别 Windows 系统代理、PAC 或 SOCKS，插件不维护第二套隐式代理优先级。

实现与维护入口为 [网络诊断](../houdini/python3.11libs/dsh_network_diagnostics.py)、[原生探针](../houdini/python3.11libs/dsh_network_probe.mjs)；配置保留回归见 [代理配置检查](../tools/tests/dsh-network-proxy-config.test.py)，Qt 交互见 [界面检查](../tools/tests/dsh-network-ui.test.py)。[实际 DSH 网络检查](../tools/tests/dsh-network-diagnostics.test.py)用独立 DSH_HOME 启动精确 CLI，验证用户 `.env`、启动环境优先级及 loopback 传输；显式传 `--proxy` 才执行匿名外网抓取，不调用模型。
## 正式发行与受管安装合同

下载 → 签名/资产摘要验证 → 新目录安全解压 → 全量文件检查 → 原子记录pending。
Houdini启动时只读取小型状态并固定本进程选择，不在GUI线程执行哈希、网络或进程探测。
首次打开工作区在worker里校验/准备，主线程只接收状态并加载HOM模块；安装完成后必须完整重启，不能热切换已打开的Houdini。
同一次启动尚未结束时，重复打开工作区共用现有启动状态，并更新最新HIP目录意图，不另开一套启动worker。

新版首次启用从当前受管版本复制独立DSH数据快照，不跟随依赖junction，再由发行包的DSH API初始化profile并检查Node、DSH和插件。
用户自建preset随数据保留，只重新生成产品拥有的唯一houdini。state.json损坏时不能猜测当前版本；保留旧目录恢复数据，选择新安装根，不把重装程序当作状态恢复。
失败保留当前选择及旧数据；未完成快照另存，重试重新采集仍在用的旧版数据。
回退恢复旧版保留的数据，新版会话仍在新版data目录；这不是数据格式转换，也不承诺跨版本自动合并。
预检后选择current不等于前端/Bridge/模型已验证，运行身份仍需独立检查。

同时只允许一个Houdini进程使用受管DSH工作区；其他实例可管理/暂存更新，待前一实例退出后再启动工作区。
动态loopback端口隔离独立DSH/开发Bridge，Windows Job Object只管理自有Node进程树，退出时收回，不按端口停止外部服务。
Windows源码模式也使用同一Job生命周期：CLI/npx在加入自有Job后才开始执行，启动器重载及UI清理不丢失所有权。
普通打开工作区/启动不接管外部监听者。Repair确认后强制停止本Houdini拥有的前端树，允许中断DSH agent；
对旧版无Job前端，只允许经真实可执行文件、精确DSH主入口/参数及本安装CLI路径核验的监听进程，
保留原生进程句柄并在终止前重查端口，防止PID复用误杀。源码限本项目npx缓存，受管限本发行安装；
未知程序/自定义入口拒绝，不能仅凭端口、node.exe名称或runtime.json终止。未登记的旧进程后代不凭端口推定归属。
确认框说明会中断任务，默认取消；保留会话文件但不保证未完成结果。普通更新仍等DSH空闲，不隐式使用强制路径。
另一Houdini占用Bridge时拒绝，不杀Houdini、不修改HIP或自动迁移历史。
Host不再运行不等于HOM已结束；强制停止前后均检查Bridge未完成请求/jobs。旧Bridge缺少完整活动观察时不猜空闲，
等待现有工作结束、确认场景后完整重开Houdini加载当前Bridge，不绕过此观察缺口强制重启。
默认单实例退出仍按Job回收自有DSH；显式终端共享Host可独立运行，退出时保留服务选择和崩溃后安全续跑尚未实现。
启动器创建的DSH携带当前Houdini的executor ID，所有Bridge请求核对目标，防止同端口换进程后误操作。
ID不是密码或节点ownership；进程重开不能凭原HIP路径自动续跑。共享任务入口/多执行端的目标设计、
身份分层与尚未开放部分见[多执行端与恢复](architecture.md#多houdini执行端与任务恢复)。
内嵌网页渲染进程异常退出时显示原生恢复面板和实际退出码，停止自动重试，由用户选择重新加载；普通HTTP服务尚未就绪继续异步重试。错误显示不等于底层渲染依赖已修复。
WebView使用独立的内存浏览器profile，不争用Houdini默认磁盘profile或其他版本的浏览器锁；浏览器cookie/缓存随窗口生命周期结束，DSH会话与配置仍在受管data目录持久化。
使用Houdini常规桌面入口启动。测试工具以所选安装bin为工作目录，并隔离外部开发宿主的MSIX包身份；包身份继承可能改变Qt helper的DLL搜索规则，不能仅凭PATH或退出码判断安装缺库。实现及验证见[开发规范](development.md)。DSH工作区独立跟随HIP目录，插件不改Houdini的cwd、不复制Qt DLL或关闭浏览器沙箱。
安装器不删除旧版本、旧数据、HIP或工作区。清理下载、暂存及旧版本须另行确认。

| 安装根下的位置 | 职责 |
|---|---|
| bootstrap/内容标识 | 独立菜单、管理器、公钥；损坏后旁路重装 |
| releases/版本-摘要-实例 | 不可变签名元数据、全量文件清单、Node及固定依赖 |
| data/安装实例 | 对应版本的DSH配置、凭据、会话、附件与profile |
| runtime/进程实例 | 端口/路径上下文、前端日志、实际运行标记 |
| downloads、staging | 下载与中断暂存，不作为运行版本 |
| state.json | current/previous/pending选择，不证明服务在线 |

## 工作区使用

常规菜单只保留「Open Workspace」和「Version & Updates...」。菜单标签使用ASCII英文，兼容Houdini原生菜单；窗口内部保留中文。共享执行端登记/修复在版本面板的高级设置中。

仅显示 **Houdini 模式**。它通过DSH 0.2的preset注册表由插件bundle声明，领域方法按需加载。
根级`dsh-houdini`装载前端扩展，Houdini preset内的`dsh-houdini/agent`注册工具和现场上下文；
两者来自同一插件包。正常会话只有一个 **执行记录**（Houdini Trace）入口，工具和技能资料在其「能力资料」中。打开记录时隐藏底部普通输入区和任务浮层，审批/澄清等原生交互仍可处理；返回对话时恢复原草稿；空白新会话仍由DSH显示起始页。
启用步骤、数据目录约束、单端Repair和未实现的退出/恢复能力唯一维护在[多实例与任务恢复](multi-instance.md)。

已保存HIP使用其父目录作为DSH工作区；未保存工程也可直接打开。保存、另存或切换HIP后再次打开工作区，选择对应目录的对话。
已有同源页面通过新的目录意图切换，包括隐藏后的重开，不刷新当前草稿。前端通过DSH原生workspace/session状态复用有效Houdini任务，
不会选中归档、其他preset或子agent。确实没有可用任务才创建；创建后读取更新后的workspace成员，再确认实际选中的任务、preset与cwd。
启动URL和窗口缓存不证明切换完成；导航失败可原位重试，不自动重复建任务。普通点击或打字不取消正在完成的导航。
未保存场景使用仓库外、每个Houdini进程独立的临时工作区，重复打开或重载保持稳定；连续新建未保存工程共用该临时目录。打开已命名HIP的工作区后，再进入未保存工程会分配新的临时目录，不继承已保存项目目录或默认用户目录，不自动删除历史对话和文件。源码与发行目录不是任务工作区。新会话使用「Houdini模式」。
首次请求houdini_inspect调用scene_info并列出/obj节点，确认工具、Trace和合同握手。
图像使用DSH原生附件，不安装额外视觉工具；没有成功语义识图仍需报告视觉未验证。最终图片默认归`$HIP/dsh-render/`，先确定真实路径并验证，再调用present；显式用户目标优先。render_view/viewport_screenshot可选output_policy='delivery'分配该目录，正式ROP按相同目标配置。验证图和缓存不自动交付；只清理当前任务明确创建且不再需要的测试产物，保留运行依赖、用户资料、公开交付和原执行回执。`present`不复制文件内容，移动/删除/改写源文件会影响旧卡片；整理旧工程后提供新的实际入口，不篡改历史。$HIP与Session workspace不同时使用权威绝对路径，切换HIP后重新打开工作区。
交付控制面板或模型编辑入口时，回复下方可显示节点卡片，点击“打开控制”或“定位节点”进入当前工程的实际节点与参数页。入口首次声明后须保存HIP；同一工程重开或节点改名仍可定位。打开其他工程时提示先回到对应工程，不自动加载文件。使用范围与复制节点标识的处理见[控制导航](parameter-controls.md)。
工作区、版本与更新、运行诊断等工具窗口通过原生窗口归属关系保持在 Houdini 上方，不使用系统全局置顶；其他应用切到 Houdini 前方时也可以遮挡插件窗口。独立安装器没有 Houdini 父窗口时使用普通应用窗口。工具明确启用原生标题栏的关闭、系统菜单和最小化按钮；关闭工作区只隐藏窗口，保留当前页面、任务和草稿，再次明确打开时复用；关闭版本面板会请求取消该面板尚未完成的操作并停止刷新。用户手动最小化后，页面加载和后台状态刷新不会自动恢复。再次通过明确打开入口唤起时，恢复已有窗口，不建立新的工作区或安装操作。窗口规则由[dsh_ui_style.py](../houdini/python3.11libs/dsh_ui_style.py)统一维护。
H21/H22内嵌QtWebEngine的`dsh-resource`解析由插件在创建页面前注册；旧进程必须按WebView变更规则完整重开Houdini才会加载这一修复。
仅在最近一次调用明确观察到已保存工程且目录不一致时，在输入区上方显示可展开的中文提示。未保存状态清除旧目录提示。提示以执行观察时间/序列为准，回读历史结果不会冒充新现场。它不是持续监控，切换HIP后须重新打开工作区，最终文件路径以当前权威回执为准。
视频教程使用当前Houdini安装内的普通Python 3.11+进程与版本私有的FFmpeg/ffprobe。正式发行随版本打包媒体工具，不依赖系统Python、FFmpeg或全局PATH；Houdini和模型服务授权不随插件分发。
完整包保留FFmpeg、zlib、FreeType、HarfBuzz、dav1d、MinGW-w64、LLVM七份对应完整源码和原始许可，位于插件`runtime/video/sources`与`licenses`。zlib支持PNG读写，dav1d提供普通电脑上的AV1软件解码；同时提供实际编译配置、Windows对象响应文件构建补丁、DLL依赖和文件摘要。媒体工具在发行端由固定来源编译，普通安装不下载编译器或运行源码构建。来源和维护入口见[开发规范](development.md#修改与验证)。

## 教程视频与转录设置

在DSH设置中打开「教程视频」，选择「转录服务供应商」，再从该供应商的已配置模型目录下拉选择转录模型。页面完整显示已配置的目录型与自定义供应商，并标出当前能否复用音频API地址；出现在列表中不代表支持转录。语音模型未列在聊天目录时，选择「其他转录模型」填写供应商公布的准确ID。API地址和密钥继续在「模型」页面统一配置；独立的转录用途选择不会改变当前对话模型，插件不另建密钥库。

当前支持显式OpenAI兼容路由的`/audio/transcriptions`，千问`qwen3-asr-flash`及日期快照的音频Chat接口，以及`qwen-audio-3.0-asr-flash`/`qwen-audio-3.1-asr-flash`的DashScope原生同步接口。千问直接提交经过校验的本地WAV切片，自动识别语种，单片不超过5分钟或10MB Base64。成功原始响应和句词时间保留在任务中；导出同时给切片范围与有真实依据的句词时间，分别声明正文覆盖和未核对的时间精度，缺失时间不插值。3.1可显式开启说话人分离取得句数组，转录工具可指定术语词表。异步Filetrans、实时语音及其它未接入型号会在上传前明确拒绝。

精确DSH的第三方目录包含千问Token Plan路由，普通百炼语音API仍需在「模型」添加自定义OpenAI兼容API。北京地址可填`https://dashscope.aliyuncs.com/compatible-mode/v1`，新加坡为`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`；也可按[阿里云官方API参考](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)填写业务空间专属域名。凭据必须匹配地域，Token Plan不代替普通百炼语音服务。DSH要求自定义供应商有可用的真实聊天目录，不能用空目录代替，也不要把ASR模型伪装成聊天模型；在教程页单独选择`qwen3-asr-flash`即可。模型可用性和价格以提供方当前目录与短段实际请求为准，配置存在不等于转录成功。

千问AI平台对应的兼容基址为`https://maas.qianwenaiapi.com/compatible-mode/v1`，见[完整Qwen-ASR参考](https://platform.qianwenai.com/docs/api-reference/speech-recognition/qwen-asr/api-reference)。官网DashScope SDK示例的`/api/v1`属于另一请求协议，不能把它当成普通聊天兼容基址。教程页选择`qwen-audio-3.0-asr-flash`时，插件从同一供应商明确的`/compatible-mode/v1`或`/api/v1`基址映射到同域名`/api/v1/services/aigc/multimodal-generation/generation`，使用原生`input.messages`请求与`X-DashScope-SSE: disable`；不切换账号、域名或模型。响应读取`output.text`完整累计正文，当前句不能代替它。其它网关路径不推断，接口依据见[原生HTTP参考](https://help.aliyun.com/en/model-studio/fun-asr-flash-recorded-speech-recognition-http-api)。

「本机依赖与高级设置」检查当前Houdini Python和版本私有FFmpeg/ffprobe，并允许开发者指定绝对路径。保存与检查不会安装全局软件或上传媒体。正式安装缺失或损坏媒体工具时，使用Version & Updates中的同版修复恢复整份受管版本；源码开发使用私有媒体工具准备入口，见[视频运行契约](../skills/houdini-video-tutorial/references/video-processing.md)。真正的短段转录由Agent在用户已允许的服务、范围与费用内执行；普通用户无需把密钥写进聊天或额外维护环境变量。

给Agent提供完整视频或包含分离音视频的目录即可。Agent先导入稳定资料、试转录少量音频并定位成品画面，再按问题回看原图、另存有依据的纠错与章节/模块资料；需要复现时才构建工程。转录工具支持1..64并发和独立启动速率，CLI与Host默认64并发、8次每秒、每次最多100次提交；这不是服务商的配额保证。遇到429、5xx或传输断联/超时时先停止派发、保存全部在途结果，再降为32或16继续预算内尚未尝试的新片；16及以下再次失败则停止。认证、模型/响应语义错误和本地文件错误直接停止，失败/未知片不自动重试。结果如实保留失败和降级记录，成功片续跑不重传；目录被强制取消时的unknown不能冒充未计费。下载中的文件需先完成下载。转录文字、画面检查和Houdini工程验证分别报告，文字覆盖完整不代表复刻成功。入口为`video_models`/`video_transcribe`与[视频教程skill](../skills/houdini-video-tutorial/SKILL.md)。
工程默认尽量还原作者方法；必要适配以及明显更优方案的并列说明和切换入口，按[视频复现协议](../skills/houdini-video-tutorial/references/reconstruction.md)处理。插件实现允许重构不改变这一目标。
本地抽帧、查询与资料整理使用`video_process`，运行时自动跟随当前任务所选Houdini，显式Python配置仍优先；不依赖终端重定向、全局Python/FFmpeg或ACL修补。设置页无任务上下文时明确仅检查Host启动环境。独立CLI继续可用，来源与文件校验由同一脚本维护。

## 指定图片模型

Houdini模式提供`image_models`与`image_generate`，复用DSH模型设置中的显式OpenAI兼容API路由（`api`、`baseURL`、`apiKeyEnv`），不维护第二份服务商配置或密钥文件。当前接入Images API的base64图片响应，普通对话/OAuth路由和URL-only响应不冒充已支持。目录出现某个模型只证明配置存在，图片接口是否可用由实际请求决定；模型名按用户指定原样发送，不自动替换。

有参考图时传本地`references`，工具将原始像素上传到`images/edits`；把URL写进prompt不等于参考图已送达。默认managed输出读取当前所选Houdini的真实HIP，purpose选择reference或texture；output省略或仅给basename，返回实际唯一文件名。未保存工程、离线或用户自定目的地使用explicit，相对路径才按DSH workspace解析，Host不展开`$HIP`。已有文件不覆盖，文件操作遵从当前DSH策略；目录、检查图分组与Save As边界见[工程文件](project-files.md)。

生成原图和模型观察用预览分别保存。原图指纹不使用预览附件的指纹代替；目标写盘失败时，已取得的原始文件附件仍可恢复。预览尺寸限制、解码或附件存储失败不撤销已保存原图。请求规格与实际图片尺寸分别报告，提供方返回不同尺寸时不自动缩放或重新计费。请求后的断联/超时保留结果未知，不自动重试；HTTP拒绝、返回格式不支持与图片质量不合格分别判断。编辑和生成都可能产生提供方费用，按用户已授权的模型及用途调用。

接口依据：[OpenAI Images API](https://developers.openai.com/api/docs/guides/image-generation)。兼容服务的实际支持需单独验证。验证入口见[开发维护](development.md)，实现见[image-generation.ts](../src/image-generation.ts)。

## 显式源码开发安装

此路径保留供开发者使用，不是正式发行安装。需要Node/npm、Python或Houdini内置Python；clone/pull时需要Git。
接续时先核对main提交与各工作树的未提交改动，再读[当前交接](handoff.md)；所有现役改动合入main，不从目录名称推断已加载版本。

```powershell
git clone https://github.com/eee1723/dsh-houdini.git
Set-Location dsh-houdini
npm install
npm run build
python houdini/install.py
```

`houdini/install.py --print`只预览package；`--skip-dsh-profile`只注册源码package。
lib和node_modules不提交，生成区不手改；更新源码执行git pull --ff-only、npm install、npm run build。
源码安装仍使用系统Node与项目npx缓存，只锁DSH根包，不具有完整受管发行保证。profile同时校验根前端入口和preset工具入口；共用面板不拉main、不原地构建。
开发者命令行构建仍是明确路径，受管界面不提供构建源码或启用未发布checkout按钮。

默认安装/启动/修复共用[兼容清单](../dsh-runtime-compatibility.json)的preferred精确DSH。
隔离资格验证可设置 `DSH_HOUDINI_DSH_SPEC=@deepseek-ai/dsh@精确版本` 或 `DSH_HOUDINI_DSH_BIN`；
受管模式忽略这些开发覆盖，只用签名组合。源码Host/Bridge/helper/preset更新可用Advanced diagnostics中的Repair and restart runtime，
WebView、菜单和package变更完整重开Houdini。构建通过、诊断存在和live加载分别验收。

## 卸载与保留数据

受管安装：关闭使用它的Houdini，移除目标偏好目录的packages/dsh-houdini.json；需要恢复此前注册时使用package-backups对应备份。
数据与版本保留在安装根，删除它们须单独确认并备份，不处理用户HIP、工作区、独立DSH或其他插件。
源码安装：通过所用精确DSH的官方plugin命令移除web profile中的dsh-houdini，并移除Houdini package，不连带删除共享内容。

发行维护和验证命令见[开发维护](development.md#发行操作与信任配置)，兼容边界见[兼容设计](dsh-update-compatibility.md)。
