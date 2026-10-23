# dsh-houdini 安装、更新与开发

Windows x64受管安装把插件、Node、DSH和完整依赖作为一个签名发行单元。普通用户不运行npm/build，不单独升级DSH。
源码checkout、预构建包、已选版本与正在运行的版本分别判断。发布前尚欠的真实用户路径见[交接](handoff.md#h-01-用户入口与受管发行)。

## 普通安装

1. 从[正式发行页](https://github.com/eee1723/dsh-houdini/releases/latest)下载完整 `dsh-houdini-版本-offline.zip`，解压后双击 `Install.cmd`。
2. 安装器按用户权限注册H21/H22菜单，不修改系统Node、Python或全局PATH。
3. 完整重开Houdini，选择 **DSH-Houdini → Open Workspace**。读取已安装版本、准备隔离profile并启动配套DSH。
4. 首次在 DSH 页面选择“登录 DeepSeek 账号”或“添加 API Key”。已有模型密钥的用户可直接添加 API Key；后续在“设置 → 模型”修改。账户登录与 API Key 是两条入口，Houdini 插件不另外收集密钥。受管安装不自动迁移或清空既有 `~/.dsh`，此前独立 DSH 的配置不会自动出现在专用工作台。

工作台可以接入多个Houdini。每段对话的工程组件显示未绑定、待命、工作中、其他对话占用或断开；点击可选择当前现场、取消绑定及打开/新建工程。从Houdini进入默认打开新对话；继续旧内容时从侧栏选择历史对话并明确指定现场。选择只改变操作目标，不清空聊天、不接管全场景节点；详情见[现场选择与工程恢复](multi-instance.md)。

完整包包含运行依赖，可离线安装；模型服务仍依赖用户配置与网络。
轻量 `dsh-houdini-installer.zip`，或clone/源码ZIP中的Install.cmd，只部署管理器；在面板检查正式Release并安装完整组合。
仓库已有正式签名Release；管理器仍只接受受信签名和完整资产。发行不可用或公钥未配置时如实报告，不将main或测试候选伪装成可安装正式版。
GitHub自动生成的Source code.zip不是完整运行包；源码构建是下文的显式开发路径。

### 注册位置与引导修复

默认安装根为 `%LOCALAPPDATA%/DSH-Houdini`，偏好目录使用 Windows 真实 Documents 文件夹，支持重定向/OneDrive。工作台快捷方式使用 Windows 原生 Unicode 接口，安装根和启动参数不依赖当前系统的 ANSI 代码页。
默认注册21.0和22.0；支持指定偏好目录与安装根：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PrintOnly
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PackagesDir 'D:/HoudiniPrefs/packages' -Root 'D:/DSH-Houdini'
```

`HOUDINI_USER_PREF_DIR`优先，必须含`__HVER__`占位符，安装器分别展开为21.0/22.0后注册对应package，否则Houdini会忽略它；显式目录可用-PackagesDir。ExecutionPolicy只作用于该次引导进程，不永久改系统策略；
企业策略禁止脚本时遵循管理员要求，不关闭安全功能绕过。此前 package 先备份到安装根的 package-backups，再用 preferences 同目录临时文件原子替换注册，支持安装根与 Documents/preferences 分属不同磁盘。实际注册文件列表保存在安装根的 registrations.json，供卸载识别自定义目录。
重复运行可信安装器可修复损坏管理器：复制到新目录再切换注册，不覆盖已加载模块。
完整包通过 SideFX 的 Windows 安装注册和标准安装目录查找 H21/H22 内置 Python，支持非默认盘安装；检测成功后直接准备运行包，未检测到时，在面板选择原解压目录的 release.json。
已完成安装不依赖原下载解压目录，不要求系统Git、Node、额外Python或管理员权限。
启动桩按[SideFX脚本位置](https://www.sidefx.com/docs/houdini/hom/locations)分别生成在python3.11libs/pythonrc.py和python3.13libs/pythonrc.py，共享同一份Python模块实现。

### 打开工作台时的等待

工作台先显示临时启动窗口，再在后台核对小型签名清单、依赖锁和包版本，准备对话配置、启动对话服务和打开工作区。日常启动不遍历安装目录或重新校验全部文件；完整校验与配套运行预检在安装、升级和同版修复事务中完成，通过后才记录待启用版本。高级设置中的「检查安装文件」仍执行完整校验。

启动窗口显示当前真实阶段及已等待秒数，不用虚构百分比；“后台打开”只隐藏等待窗口，准备继续进行。重复打开复用已有工作台，不重复启动服务。阶段耗时进入已有启动日志，失败由当前入口解释并提供报告问题路径。Houdini 入口观察子进程真实就绪或退出，不在固定等待期限后把仍在准备的子进程误报为结束；并发启动的锁等待仍有明确上限。

性能判断分别测量安装事务、配置准备、Host 认证、工作区定位和页面可用时间。已安装记录不证明所有文件当前仍未变化；实际模块加载、Host 认证和 Houdini 现场身份仍须取得当次真实回执。缺失或损坏在真实使用时报错，可用「检查安装文件」定位并修复；安装优化不放宽节点权限或恢复边界。

### 首次配置与登录等待

“等待登录”表示 DSH 正等浏览器中的账户授权，不表示正在安装插件或校验 API Key。工作台将用户点击打开的网页交给系统浏览器，并支持先开空白页、稍后取得登录地址的授权流程；取消登录后仍可选择“添加 API Key”。没有自动打开浏览器时，使用同一对话框中的“复制登录链接”手动打开，完成后回到原工作台。该跳转可用不代表账号服务、网络和授权回调已经验证成功；不要通过重装或删除配置尝试清除账户问题。

已有 API Key 可从“设置 → 模型”配置提供方并选择模型。首次配置入口未显示、保存失败与模型请求失败需要分别诊断；故障报告不应收集明文密钥。

### 部署路线与职责

当前普通用户使用上面的完整签名发行包：插件与经过验证的精确 DSH、Node 和运行修复作为一个单元交付。用户不用另装全局 Node/DSH，不独立追随 DSH latest，也不同时维护两套推荐客户端。

当前保持完整签名安装方案。官方 DSH 桌面端稳定后再评估“官方桌面端 + 插件”组合；届时按[兼容维护](dsh-update-compatibility.md#dsh耦合点与升级维护)逐项核对依赖、配置职责和实际用户路径，不能仅以版本号一致或插件注册成功作为迁移完成。

## Version & Updates（版本与更新）

源码和受管安装共用中文主面板。默认只显示版本、更新状态和「检查更新」；发现适用的新版本后才出现安装或发行页入口。未检查、检查失败、没有正式发行和已是最新分别显示；源码版本只是磁盘 package 版本，不认证实际加载状态。
有下次启动待切换版本时才显示第二列。安装路径、源码更新说明、维护操作、运行诊断、日志和共享执行端实验入口统一收在「高级设置」。无适用对象的修复/回退/取消切换操作隐藏，正在工作时才显示进度与取消。

工作台就绪后在后台发现正式新版，持续运行时每六小时刷新；离线或查询失败不阻塞打开，也不冒充已是最新。仅确认有高于当前运行、当前安装和待切换版本的正式版时，在既有对话页头显示紧凑「有更新」按钮。按钮打开同一「版本与更新」面板，直接消费已取得的发现结果；手动检查与后台检查共用在途请求，不另建下载或安装流程。面板中的安装仍由用户主动触发，不中断活动任务或热切换版本。

Houdini 的 Version & Updates 保留所属现场的完整管理器；工作台按钮复用同一面板实现和安装事务。现场运行、联网诊断及共享执行端维护在 Houdini 内打开的管理器中提供，桌面面板不调用 HOM。新版准备完成后，关闭工作台并重开相关 Houdini 才启用；工作台、Bridge 和磁盘版本分别表达。

| 操作 | 行为 |
|---|---|
| 检查更新 / 安装更新 | 只查明确发布的稳定Release；在线安装要求不可变Release、受信签名与完整资产 |
| 安装本地包 | 选择与ZIP、release.sig.json同目录的release.json；离线也要求受信签名 |
| 修复当前版本 | 重新下载并暂存当前版本完整包，不升级DSH/latest、不覆盖损坏目录；离线时选择同版本地包 |
| 检查安装文件 | 检查全量文件哈希、缺失/多余文件、包版本和依赖锁；通过不证明live加载 |
| 回退到上一版本 | 下次启动使用上一套程序及其独立数据，新版数据保留但不自动合并 |
| 取消下次切换 | 取消待切换状态，不删除版本、数据或下载 |
| 运行诊断 | 查看实际Host/Bridge端点与接口版本；「重新加载本机更新」应用同安装的文件更新，受活动任务和保存状态保护，不重复发行检查 |

网络失败/限流不冒充已是最新。Draft、prerelease、push与tag不进入默认更新通道；目前没有面向普通用户的预览通道。
后台下载/解压可取消；提交pending是原子步骤，提交后使用「取消下次切换」取消下一次切换。
独立管理器不依赖Node、DSH或插件lib，缺依赖时仍可打开。

### 网络继承与诊断

Windows 下，没有显式代理环境覆盖时，配套 DSH 使用当前用户的系统网络设置。手动 HTTP/HTTPS 代理、系统例外列表和 PAC/WPAD 由同一个 DSH 网络模块解析；自动代理脚本由 Windows 原生 API 在后台线程处理。模型、搜索、网页抓取和图片下载共用实际请求的路由。每次新请求重新取得系统选择，已派发请求保持其原路线；关闭系统代理后不用重启 Houdini 来清除端口。不会因连接失败自动改走直连或重发付费请求。

插件不保存代理端口、模型直连域名或自己的分流规则。从 **DSH-Houdini → Version & Updates... → 高级设置 → 联网诊断…** 打开只读窗口；入口与「运行诊断…」并排，位于共享执行端实验功能上方，可查看实际来源、目标地址路线与失败原因，并由用户点击打开 Windows 网络设置。测试在独立新进程中使用同一精确 DSH，不修改系统设置、不续跑会话、不调用收费搜索；结果不证明已有 Host 已加载相同版本。模型服务、搜索服务的地址/凭据仍由 DSH 自身配置；搜索组件存在不证明搜索调用成功。

用户或部署显式设置的 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY、NO_PROXY 仍沿用 DSH 的环境优先级，覆盖系统继承；诊断会说明来源。插件不会自动修改这些用户设置，项目目录的 .env 也不能选择网络路线。发行包不携带开发者的端口、域名例外或凭据。非 Windows 平台保持原有 DSH 环境行为，本项目没有宣称读取其原生系统代理。

系统 HTTP 代理通过原有传输连接；SOCKS-only 设置会明确报不支持，不擅自直连。企业认证代理、企业私有证书和 PAC 的多代理故障切换未获得完整验证。应用直连仍使用系统 DNS/VPN/TUN。公开网页的非公网地址检查、HTTP(S)/URL 凭据限制和重定向边界保持；Fake-IP 返回值不是公网地址，不能靠关闭检查解决。用户配置的代理负责代理路线的 DNS，直连路线仍执行原生解析与地址固定。任意 shell/模型自写网络脚本不承诺使用同样的传输；联网资料使用原生工具。

实现入口为 [网络诊断](../houdini/python3.11libs/dsh_network_diagnostics.py)、[原生探针](../houdini/python3.11libs/dsh_network_probe.mjs)及[DSH修复声明](../deployment/dsh-runtime-fixes/manifest.json)。[系统代理检查](../tools/tests/dsh-system-proxy-check.mjs)验证同进程切换、系统例外、原生PAC、取消与失败不换路；[界面检查](../tools/tests/dsh-network-ui.test.py)确认只读和主线程不阻塞；[DSH检查](../tools/tests/dsh-network-diagnostics.test.py)覆盖显式覆盖、凭据脱敏和loopback。

参考图片继续使用 `web_download`，支持通过公开CDN重定向下载。回执记录请求实际路线，网络错误带底层原因；访问返回403等站点拒绝不等同于电脑断网。命令退出0但有标准错误输出时显示诊断提示，需阅读具体输出；单凭退出0不能断言脚本内每项操作成功。

源码首次启动或运行修复声明变更后，执行 `npm run runtime:prepare`，或从源码运行诊断准备配套环境。修复从固定DSH源码和依赖锁构建到独立缓存，当前Host不会被替换或自动重启。正式安装包在发布组装时完成同一构建，用户安装不运行源码编译；详见[版本适配](dsh-update-compatibility.md)。
## 正式发行与受管安装合同

下载 → 签名/资产摘要验证 → 新目录安全解压 → 全量文件检查与隔离运行预检 → 原子记录pending。
Houdini启动时只读取小型状态并固定本进程选择，不在GUI线程执行哈希、网络或进程探测。
打开工作区在worker里核对小型签名元数据并准备配置，不重复全包校验与安装探针；主线程只接收状态并加载HOM模块。安装完成后必须关闭工作台并完整重开相关 Houdini，不能热切换已打开的进程。
同一次启动尚未结束时，重复打开工作区共用现有启动状态，并更新最新HIP目录意图，不另开一套启动worker。

新版首次启用从当前受管版本复制独立DSH数据快照，不跟随依赖junction，再由发行包的DSH API初始化profile、核对前端/preset组合及当次执行端登记位置；配套Node、DSH和插件的安装探针已在暂存事务中完成。
用户自建preset随数据保留，只重新生成产品拥有的唯一houdini。state.json损坏时不能猜测当前版本；保留旧目录恢复数据，选择新安装根，不把重装程序当作状态恢复。
失败保留当前选择及旧数据；未完成快照另存，重试重新采集仍在用的旧版数据。
回退恢复旧版保留的数据，新版会话仍在新版data目录；这不是数据格式转换，也不承诺跨版本自动合并。
配置准备后选择current不等于前端/Bridge/模型已验证，运行身份仍需独立检查。

同一受管运行根只运行一个DSH Host，由独立工作台持有；兼容的多个Houdini可接入同一工作台。其他实例不重复激活、复制或并写DSH数据，活动版本不同须先结束工作台再切换。
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
独立工作台使用按安装与数据身份隔离的持久浏览器profile，以及同一安装的稳定本机地址；DSH原生浏览器存储保留选中对话和未发送草稿，不由插件复制输入内容。地址被外部进程占用时明确报错，不接管监听或悄悄换地址。旧内嵌WebView仍使用内存profile，不争用Houdini默认profile；DSH会话与配置在各自data目录持久化。更新前旧内存profile的未发送内容需要自行保留，新的持久profile不能追溯恢复它。
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

源码版可双击仓库根目录的`Open Workspace.cmd`先打开独立工作台；受管安装器在安装根生成`DSH-Houdini.lnk`。工作台的工程小图标提供打开、新建和打开关联工程，选择文件/版本后自动连接；无需先手动启动一个空白Houdini。已有Houdini仍可使用其Open Workspace菜单接入。窗口图标与快捷方式共用多尺寸ICO，安装器与新运行包必须配套交付，源码构建不代表用户安装已经更新。

Open Workspace启动或唤起独立工作台，并定位当前Houdini对应的对话；另一Houdini使用同一入口加入，不再要求退出前一个窗口。关闭Houdini保留工作台，退出工作台不结束Houdini；有活动对话时先确认退出。普通聊天区没有常驻连接条或检查按钮；旧对话需要接续时直接说明要继续的工程。旧内嵌后台须正常退出后迁移，不删锁或强杀进程。源码能力与正式受管包交付须分别核对，具体边界见[多实例与恢复](multi-instance.md#独立工作台)。

故障反馈从对话标题栏「报告问题」生成并预览诊断包；工作区打不开时，可从Version & Updates窗口「报告问题 / 导出诊断包」收集已有运行记录。保存到本机后手动分享，不自动上传。DSH原生`/export`另行导出完整会话和附件；完整包没有默认诊断包的筛选和脱敏，分享前须检查。数据位置、范围与开发者分析方法见[故障报告](support-reports.md)。

常规菜单只保留「Open Workspace」和「Version & Updates...」。菜单标签使用ASCII英文，兼容Houdini原生菜单；窗口内部保留中文。共享执行端登记/修复在版本面板的高级设置中。

同安装源码构建或实现更新后，使用Version & Updates → 高级设置 → 运行诊断 →「重新加载本机更新」。系统先核对工作台无活动对话且历史已保存，正常关闭旧Host并确认退出，再重载当前Houdini连接，启动此安装的新工作台；HIP、未保存节点修改和其他Houdini进程保持原样。关闭时会再次检查活动状态，遇到新任务不会强杀Host。按钮完成以实际新Host和Bridge回执为准，磁盘文件或接口版本相同不能证明实现已更新。旧工作台不支持正常关闭协议时，先手动正常退出一次；不会强杀旧进程。跨安装版本、package/menu或Houdini内WebView变更仍按下述规则完整重开对应Houdini。

版本页区分本次启动选定、实际加载与下次切换的安装。重开Houdini后，已选定的新版本在打开工作区时加载，页面提示“打开工作区即可使用”；加载成功后自动更新状态。目标安装与本进程已加载版本不同时仍须重开Houdini，同版本修复也按安装身份判断。工作台持有运行锁，活动工作台的版本不能被第二个Houdini静默替换；先保存任务、退出工作台再切换版本。

版本页与启动入口由独立安装器维护，普通插件包更新不会替换这部分已注册的代码。启动入口或版本页修复需要运行新版安装器的`Install.cmd`后重开Houdini；安装器保留已有版本、数据及原注册备份，不要求卸载或清空会话。

仅显示 **Houdini 模式**。它通过DSH 0.2的preset注册表由插件bundle声明，领域方法按需加载。
根级`dsh-houdini`装载前端扩展，Houdini preset内的`dsh-houdini/agent`注册工具和现场上下文；
两者来自同一插件包。正常会话只有一个 **执行记录**（Houdini Trace）入口，工具和技能资料在其「能力资料」中。打开记录时隐藏底部普通输入区和任务浮层，审批/澄清等原生交互仍可处理；返回对话时恢复原草稿；空白新会话仍由DSH显示起始页。
启用步骤、数据目录约束、单端Repair和未实现的退出/恢复能力唯一维护在[多实例与任务恢复](multi-instance.md)。
普通单实例在原任务收到用户消息时自动核对并接续可信保存点；需要决定如何处理未保存内容时通过原生对话询问，不提供额外恢复按钮。源码能力、保存脚本安装及旧HIP限制见[保存点恢复](multi-instance.md#单实例保存点恢复)，不等于当前发行版或已运行实例已加载。

已保存HIP使用其父目录作为DSH工作区；未保存工程也可直接打开。保存、另存或切换HIP后再次打开工作区，选择对应目录的对话。
已有同源页面通过新的目录意图切换，包括隐藏后的重开，不刷新当前草稿。前端通过DSH原生workspace/session状态复用有效Houdini任务，
不会选中归档、其他preset或子agent。确实没有可用任务才创建；创建后读取更新后的workspace成员，再确认实际选中的任务、preset与cwd。
启动URL和窗口缓存不证明切换完成；导航失败可原位重试，不自动重复建任务。普通点击或打字不取消正在完成的导航。
未保存场景使用仓库外、每个Houdini进程独立的临时工作区，重复打开或重载保持稳定；连续新建未保存工程共用该临时目录。打开已命名HIP的工作区后，再进入未保存工程会分配新的临时目录，不继承已保存项目目录或默认用户目录，不自动删除历史对话和文件。源码与发行目录不是任务工作区。新会话使用「Houdini模式」。
首次请求houdini_inspect调用scene_info并列出/obj节点，确认工具、Trace和合同握手。
图像使用DSH原生附件，不安装额外视觉工具；没有成功语义识图仍需报告视觉未验证。最终图片默认归`$HIP/dsh-artifacts/renders/<HIPNAME>/`，先确定真实路径并验证，再调用present；显式用户目标优先。render_view/viewport_screenshot可选output_policy='delivery'分配该目录，正式ROP按相同目标配置。验证图和缓存不自动交付；只清理当前任务明确创建且不再需要的测试产物，保留运行依赖、用户资料、公开交付和原执行回执。`present`不复制文件内容，移动/删除/改写源文件会影响旧卡片；整理旧工程后提供新的实际入口，不篡改历史。$HIP与Session workspace不同时使用权威绝对路径，切换HIP后重新打开工作区。
交付控制面板或模型编辑入口时，回复下方可显示节点卡片，点击“打开控制”或“定位节点”进入当前工程的实际节点与参数页。入口首次声明后须保存HIP；同一工程重开或节点改名仍可定位。打开其他工程时提示先回到对应工程，不自动加载文件。使用范围与复制节点标识的处理见[控制导航](parameter-controls.md)。
独立工作台默认是普通应用窗口；现有对话顶部工具区的小图钉可开启/取消全局置顶，不另占一行、不隐藏重建窗口或重载页面，重开工作台默认关闭。工作台关闭与进程生命周期见[独立工作台](multi-instance.md#独立工作台)。Houdini内的版本与更新、运行诊断等工具窗口使用原生归属关系保持在其父窗口上方，其他应用可以正常覆盖；独立安装器使用普通应用窗口。工具保留原生关闭、系统菜单和最小化按钮；旧内嵌工作区关闭时只隐藏，保留页面、任务和草稿，再次打开复用；关闭版本面板会取消其未完成操作并停止刷新。手动最小化后，后台加载与状态刷新不恢复窗口。默认窗口样式由[dsh_ui_style.py](../houdini/python3.11libs/dsh_ui_style.py)维护，工作区图钉由[dsh_webview.py](../houdini/python3.11libs/dsh_webview.py)维护。
H21/H22内嵌QtWebEngine的`dsh-resource`解析由插件在创建页面前注册；旧进程必须按WebView变更规则完整重开Houdini才会加载这一修复。
仅在最近一次调用明确观察到已保存工程且目录不一致时，在输入区上方显示可展开的中文提示。未保存状态清除旧目录提示。提示以执行观察时间/序列为准，回读历史结果不会冒充新现场。它不是持续监控，切换HIP后须重新打开工作区，最终文件路径以当前权威回执为准。
视频教程使用当前Houdini安装内的普通Python 3.11+进程与版本私有的FFmpeg/ffprobe。正式发行随版本打包媒体工具，不依赖系统Python、FFmpeg或全局PATH；Houdini和模型服务授权不随插件分发。
完整包保留FFmpeg、zlib、FreeType、HarfBuzz、dav1d、MinGW-w64、LLVM七份对应完整源码和原始许可，位于插件`runtime/video/sources`与`licenses`。zlib支持PNG读写，dav1d提供普通电脑上的AV1软件解码；同时提供实际编译配置、Windows对象响应文件构建补丁、DLL依赖和文件摘要。媒体工具在发行端由固定来源编译，普通安装不下载编译器或运行源码构建。来源和维护入口见[开发规范](development.md#修改与验证)。

## ChatGPT 订阅

设置 →「ChatGPT 订阅」提供登录、模型选择、连接测试与断开入口。浏览器完成OpenAI授权，DSH原生凭据存储负责保存和续期；插件不读取Codex登录文件，也不要求把密钥或返回地址发进聊天。已有临时接入的订阅授权沿用同一DSH记录，设备标识只在显式登录时按原生合同迁移。

先使用ChatGPT登录，再选择模型和思考程度，点击「设为新对话默认」。已有对话继续使用自己的模型，在输入框旁的原生模型菜单切换。模型目录只是当前DSH的可选配置，不是账户权限证明；「测试模型连接」显式发送一条短消息并消耗少量额度，不附带工程文件或聊天内容。授权保存、默认选择和这次请求成功分别显示，页面不自动花费额度测试或切换到API计费。

OpenAI路由存在API Key、自定义地址、协议或请求头覆盖时，页面说明具体冲突，由用户在「模型」设置处理；不会为了订阅覆盖已有服务配置。用量入口指向[ChatGPT官方用量设置](https://chatgpt.com/settings/usage)，当前不推算剩余额度。此授权用于助手对话；图片生成与教程转录继续使用各自明确的API服务。账户适用范围以[OpenAI官方说明](https://developers.openai.com/siwc/quickstart)为准。

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

受管安装：在 **Version & Updates → 高级设置 → 卸载插件（保留数据）** 操作，或双击下载包/安装根中的 **Uninstall.cmd**。它移除本安装对应的 Houdini package 注册和工作台快捷方式，不停止当前进程；完整重开 Houdini 后菜单消失。卸载不要求工作台或模型配置可用。

卸载保留整个安装根中的版本文件、API 配置、会话、备份和注册清单，重新运行 Install.cmd 可继续使用。它不删除用户 HIP、项目目录、独立 DSH 或其他安装的注册。需要恢复此前注册时，使用 package-backups 对应备份。物理删除保留目录需先正常关闭相关程序并单独备份，不与解除注册混为一次操作。

旧版没有 registrations.json 时，卸载器会核对标准 Documents 和 HOUDINI_USER_PREF_DIR 位置。旧版任意自定义 preferences 若未留记录，可用 installer/uninstall.ps1 的 -PackagesDir 明确补充；它不会全盘寻找或猜测删除。手动删除安装目录后，可重新运行可信新版 Install.cmd 修复，或用下载包中的 Uninstall.cmd 解除残留标准注册；无需删除模型配置或工程。
源码安装：通过所用精确DSH的官方plugin命令移除web profile中的dsh-houdini，并移除Houdini package，不连带删除共享内容。

发行维护和验证命令见[开发维护](development.md#发行操作与信任配置)，兼容边界见[兼容设计](dsh-update-compatibility.md)。
