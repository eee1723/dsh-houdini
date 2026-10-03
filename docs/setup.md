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
H22.0.368的Qt helper依赖启动目录查找原生DLL；使用Houdini常规快捷方式或以安装bin为工作目录启动。不要把Houdini进程cwd改成源码/安装暂存目录；DSH工作区仍独立跟随HIP目录，插件不改Houdini的cwd或关闭浏览器沙箱。
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
图像使用DSH原生附件，不安装额外视觉工具；没有成功语义识图仍需报告视觉未验证。最终要交给用户的文件（包括图片）在实际存在并完成验证后由Agent调用`present`声明，右侧交付卡片指向源文件；验证图和缓存不自动声明。`present`不复制文件内容，源文件被移动、删除或改写后，旧卡片的打开结果也会改变。$HIP与Session workspace不同时应使用权威绝对路径，并在切换HIP后重新打开工作区。
H21/H22内嵌QtWebEngine的`dsh-resource`解析由插件在创建页面前注册；旧进程必须按WebView变更规则完整重开Houdini才会加载这一修复。
仅在最近一次调用明确观察到已保存工程且目录不一致时，在输入区上方显示可展开的中文提示。未保存状态清除旧目录提示。提示以执行观察时间/序列为准，回读历史结果不会冒充新现场。它不是持续监控，切换HIP后须重新打开工作区，最终文件路径以当前权威回执为准。
视频教程等可选能力的FFmpeg和云服务凭据不属于核心离线运行依赖，仍需按对应skill准备；Houdini和模型服务授权不随插件分发。

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
