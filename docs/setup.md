# 安装与使用

dsh-houdini 是官方 DeepSeek Harness Desktop 的插件。当前发行包面向 **Windows x64**，精确 DSH 版本由[兼容清单](../dsh-runtime-compatibility.json)维护，当前为 **0.2.1-rc.3**；Houdini 侧支持 21.0 和 22.0，实测构建为 21.0.440 和 22.0.368。产品使用同一份 DSH 原生会话，不另启动 Qt 聊天窗口或私有 DSH Host。

## 普通安装

标准发行单元是包含 Houdini 和媒体资源的 `.tgz`。当前处于维护者实测阶段，标准插件尚未正式发布，测试包由维护者单独提供；源码推送不触发发布。后续经用户确认才建立正式分发渠道，状态统一见[发行交接](handoff.md#h-01-标准插件发布与用户加载)。[历史发布页](https://github.com/eee1723/dsh-houdini/releases)中的独立工作台包不适用于这条安装路径，不以旧包或 npm 安装名代替当前候选包。

1. 安装受支持的官方 DSH Desktop，并确认其 DSH 宿主版本符合上方精确兼容范围。
2. 将完整 `.tgz` 下载或复制到本机，打开 Desktop 原生插件管理，填入其本地绝对路径安装。直接安装压缩包即可，无须解压后寻找 `Install.cmd`，也无须另装 Node。
3. 安装完成后启用插件。当前宿主的新装插件默认停用，可在安装结果中选择「立即启用」，或在插件列表启用 `dsh-houdini`；安装成功本身不表示 Houdini 模式已经加载。
4. 在 DSH 原生模型设置中完成供应商或账户配置，为当前对话选择可用主模型。插件复用这些设置。
5. 新建或选择 Houdini 模式的对话，在现场菜单选择 Houdini 安装，新建场景或打开已有 HIP；已经加载兼容组件的现场也可直接选择绑定。

插件在真正新开 Houdini 前自动准备本端组件，包括登记菜单所需的 Package、检查已确认的旧入口并取得安装回执；准备失败会显示实际原因，不继续新开一个未准备好的窗口。日后普通启动的 Houdini 也通过该 Package 加载菜单。需要单独准备或修复组件时，可使用 Houdini 模式现场菜单的「安装 / 更新 Houdini 组件」。

远程 tarball URL 属于宿主支持的安装机制，但缓存复用与实际公网渠道尚未完成稳定性核对；当前推荐本地完整包路径，具体缺口见[发行交接](handoff.md#h-01-标准插件发布与用户加载)。

已经打开且没有加载组件、或仍加载旧版组件的 Houdini，须先保存，再重新打开对应窗口；磁盘安装不能替换进程内已经加载的 Python 模块。组件准备不关闭其他 Houdini，不重启 Desktop。发现进程或 HIP 路径不证明该窗口已经连接。Desktop 未安装、版本不兼容或插件未启用时，菜单显示实际接入原因。

## 旧版入口迁移与数据保留

首次新开 Houdini 或显式更新组件时，安装器检查目标目录中的旧入口。仅对能确认来自历史 dsh-houdini 安装器的 Package、启动桩、菜单和独立工作台快捷方式执行停用，保留原始字节备份和可恢复报告；复制、改名后的纯插件 Package 也在检查范围内。自定义 Shelf、混有其他代码的启动脚本和无法确认的快捷方式保持原样，安装详情提示需要核对的内容。同名 Package 若无法确认归属，准备会停止并给出具体报告，不要求用户盲删目录。

旧运行包、缓存、密钥、会话、附件和 HIP 都保留。入口迁移不合并两套历史，不改写会话头或搬动日志；已有旧记录的处置范围见[宿主与历史交接](handoff.md#h-06-官方dsh共存与插件边界)。不要通过清空旧 runtime、账户目录或历史来解决入口冲突。运行中的旧 Houdini 仍须保存后重开。

安装器只部署自身 helper 和 Package。helper 默认位于 `%LOCALAPPDATA%/DSH-Houdini`，不安装 DSH/Node，不修改官方 Desktop 安装、其他插件、profile、会话或账户。目标优先采用显式 `-PackagesDir` 和已有登记；没有已登记目标时，依次使用 `HOUDINI_PACKAGE_DIR`、`HOUDINI_USER_PREF_DIR` 或系统 Documents 中的 Houdini 21.0/22.0 偏好目录。`HOUDINI_PACKAGE_DIR` 可用分号列出多个绝对目录；已有自定义登记在升级时继续保留。

支持人员可在完整插件资源目录使用[安装器](../installer/install.ps1)的高级预览与恢复入口。预览不写文件；恢复只处理报告记载的入口，校验备份和安装后文件摘要，遇到用户后改的文件就停止并保留它：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -MigrationPreview
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -RollbackMigration '报告绝对路径' -MigrationPreview
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -RollbackMigration '报告绝对路径'
```

自定义组件根可追加 `-Root`。恢复迁移会重新启用报告中的原入口，应按明确的恢复目的使用；组件版本选择和已加载状态仍以本端版本信息及重开后的实际连接为准。

## 工作区使用

从 Desktop 选择 Houdini 模式，在对话目标控件中选择已登记现场；也可选已发现的 Houdini 安装，新建或打开现有 HIP。打开其他文件默认使用新进程，不隐式清空已有现场。启动成功、HIP 加载完成、Bridge 连接和任务绑定分别以实际回执确认。

在 Houdini 选择 DSH-Houdini → Open Workspace，菜单取得当前现场身份，启动/确认本端 Bridge，再唤起同一 Desktop 并定位或创建 Houdini 对话。已有明确目标优先；发生歧义才选择。GUI 主线程不等待网络或进程探测。

未保存场景使用插件专属临时工作目录，不自动保存 HIP。已有对话切换目标保留其原生工作区与历史；Save As 只更新真实 HIP 事实，原项目内的文件目录可由原生 cd 跟随，跨项目文件权限仍沿 DSH 公开机制处理。工程输出锚定实际 $HIP 与明确目的地，不修改会话创建目录来扩大权限。

只有当前选中的 Houdini 对话显示领域交互控件。其他模式没有现场面板；历史执行卡片仍可读取，已经提交的后台执行不因切换界面而取消。多现场、节点修改权限与恢复合同见[现场选择](multi-instance.md)。

## Version & Updates（版本与更新）

Desktop 的应用和账户更新由官方管理；Node 侧插件沿官方插件管理更新。Houdini 菜单中的版本信息、检查与修复只作用于本端 Bridge/helper。已加载版本以当次 Bridge 执行合同为准，不能只查看磁盘文件或包版本。

修复当前 Bridge 必须等待其执行队列空闲，不终止其他 Houdini、不重启 Desktop、不重放未确认代码。Package/菜单变更按提示重开对应 Houdini；本端更新不改变原 HIP 和节点内容。

## 教程视频与转录设置

普通用户只需先在DSH配好主聊天模型。第一次分析有讲解的教程时，可以直接说「帮我配置教程分析」或在「设置 → 教程视频」点击「让 Agent 帮我配置」。Agent先检查已有状态，只问缺少的服务、准确模型、并发和必要速率；ASR与STT是同一语音转文字能力，不需要配两套，TTS也不是解析教程的前置要求。

已有DSH提供方可明确复用其API地址和凭据引用；独立官方、中转或本机服务则保存为教程用途端点，不需要添加一个假聊天模型。协议按实际文件接口选择，不按厂商或模型名称猜测。支持OpenAI兼容文件转录、千问音频Chat与DashScope同步音频；实时流与异步云任务需要专用适配器，不能仅换URL或模型ID。已有本机兼容服务可使用无密钥模式；本机地址不证明它的后端绝不联网。

密钥只在状态页的「安全录入或更换密钥」输入，通过DSH原生凭据接口保存；不要发进聊天、提问答案或脚本。Agent只看到是否已配置。新网络origin不会自动继承旧服务的key；聊天OAuth或订阅也不等于语音API授权。页面展示当前配置与缺项，实际识别能力以获授权的一个短片试转录为准。默认并发2、每秒1次，本机可先1；试段明确只提交1片，这些限制不能替代总费用/上传范围授权。

FFmpeg/ffprobe随完整插件包交付，普通用户不用安装到PATH。普通Python自动来自已选安装的静态信息或发现的Houdini安装；只解析教程不必先连接场景。缺少图片能力时由Agent引导使用DSH原生模型选择，不能把转录文本冒充完整画面分析。若用户需要部署本地推理模型，应在明确硬件和资源下载后使用独立环境，不把CUDA/推理依赖安装进Houdini Python，也不默启宿主的可选听写bundle。

正式插件媒体资源位于 runtime/video，包含 FFmpeg/ffprobe、所需依赖、许可与完整对应源码。构建使用现有受控媒体构建/暂存入口，不从用户系统 PATH 猜测另一套默认工具。源码开发可以显式指定经过验证的 FFmpeg/ffprobe；缺失资源时返回实际依赖原因，不宣称离线功能已就绪。方法与验证见[开发规范](development.md)及[媒体契约](../skills/houdini-video-tutorial/references/video-processing.md)。

## ChatGPT 订阅

使用官方 Desktop 的原生账户、模型与授权界面。插件不提供另一套 ChatGPT 登录、模型选择或上下文压缩设置，不在退出插件时注销宿主账户。图像输入能力由当前模型声明与实际成功识图分别判断。

## 指定图片模型

Houdini 模式通过 image_models 发现当前可用路由，再以 image_generate 使用实际模型和参考文件。使用 DSH 原生凭据与附件；生成图片及其目的地不证明语义判断已经完成。输出角色与文件边界见[工程文件](project-files.md)。

## 显式源码开发安装

```powershell
npm install
npm run build
npm run runtime:prepare
npm run docs:check
```

官方宿主准备器仅用于隔离开发验证。开发/测试必须显式使用临时 DSH_HOME、profile、依赖缓存和浏览器数据；不要把未验证的 checkout 安装进用户正在使用的 Desktop。源码 Houdini Package 可用 python houdini/install.py --print 预览或安装；该命令不改 DSH profile。

具体职责、替代方案比较和宿主共存纪律见[开发维护](development.md#插件职责与方案选择)。受支持版本与公开接口见[DSH 适配](dsh-update-compatibility.md)，未完成验收只维护于[交接](handoff.md)。

## 卸载与保留数据

需要完整卸载时，先在已安装 helper 的 Houdini 中打开 **DSH-Houdini → Version & Updates...**，选择「移除本机组件…」并确认，再到 Desktop 原生插件管理停用或卸载 `dsh-houdini`。本机组件解除登记后，当前窗口与 Bridge 继续运行，下次启动不再加载菜单；若继续从仍启用插件的 Desktop 新开 Houdini，组件会按正常流程重新准备。无需寻找卸载脚本或清空目录。

高级维护可使用完整插件或已安装 helper 中的 [installer/uninstall.ps1](../installer/uninstall.ps1)，提供只读预览和按报告恢复。卸载不结束正在运行的 Houdini，不删除 HIP、会话、附件、恢复材料或 helper 版本目录，不修改官方 Desktop 安装。保留的旧私有入口不会因卸载新插件而自动重新启用。

## 正式发行与受管安装合同

发布构建器打包标准插件及 Houdini/媒体资源，不再生成包含私有 DSH、Node、账户配置和 Qt 工作台的运行组合。安装完成不等于旧 Houdini 进程已加载。正式发布与源码构建分开，完整验证范围见[DSH 兼容](dsh-update-compatibility.md#正式发行单元与发布门)。
