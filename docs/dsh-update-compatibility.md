# DSH 与插件版本适配

本项目通过DSH公开接口加载，当前精确目标是 **0.2.0-rc.2**。选择源为[兼容清单](../dsh-runtime-compatibility.json)，依赖锁在[package-lock](../package-lock.json)和[受管锁](../deployment/package-lock.json)。

网络继承由DSH的http-proxy包维护，公开proxyRouteFor现在异步返回当前请求的确定路线；配套web-fetch-http与本插件探针同步消费，不能混装旧版同步调用者。

当前组合还包含[运行修复声明](../deployment/dsh-runtime-fixes/manifest.json)指定的同版本源码修复。唯一修改源为声明中的补丁，基线固定到上游提交；不覆盖正在运行的缓存，不用alpha版本或强制依赖升级代替验证。修复覆盖Windows自有目录的沙箱标签初始化、平台临时目录、只读权限诊断、Windows系统代理/PAC继承、受文件策略保护的二进制下载及命令结果呈现。

源码使用 `npm run runtime:prepare` 从受管依赖锁安装独立缓存，再从固定上游提交应用补丁、编译并记录文件摘要。构建入口为[准备器](../tools/prepare-dsh-runtime.mjs)和[编译器](../tools/build-dsh-runtime-fixes.mjs)；发行组装复用同一入口。默认启动只选择匹配修复声明的缓存，完整文件检查在启动worker执行，界面选择只读小型元数据。运行记录保留本次启动实际验证的修复身份；包版本号相同不能代替修复已加载。

`web_fetch`负责网页文本，`web_download`经同一个网络提供方取得完整字节，再由DSH文件系统检查当前会话范围并原子创建新文件。它拒绝已有文件、只读/范围外目标、非成功HTTP和截断下载；图片仍须解码和实际观察。公开跨域重定向逐跳重新验证地址和路线，拒绝私网目标、URL凭据、非HTTP(S)、HTTPS降级和过长跳转；每跳实际来源、直连/代理和HTTP状态进入回执，代理凭据不进入这些诊断。传输失败保留底层错误码，不自动换路。

Windows工作区授权逐对象核对已有普通内容，补齐能力权限和Low安全等级；使用固定对象句柄读写原生安全描述符，避免目录级自动传播影响外部硬链接。已有链接、多硬链接文件、受保护权限、其他所有者及显式非Low标签保持边界；临时标签写权限不继承，失败恢复原权限，撤销按对象移除对应能力。新内容继承所在目录，已初始化工作区的授权由Host缓存；运行中从外部搬入且保留原权限的内容需重新准备，不监控整盘文件事件。

原生命令保存 `shellExit` 元数据，前台命令的渲染结果还保留末尾 `process-result` 记录；嵌套调用同时保留实际进程值及子调用回执。`hasStderr`只表示有标准错误输出，退出0时聊天和Trace仍提示诊断，不伪造失败退出码。脚本捕获错误后仅向stdout打印文字不构成系统可确认的失败；stdout中的伪造退出标记也不能覆盖执行事实。`isError`继续表达工具传递错误。

## 运行职责

DSH负责模型调用、会话与持久化、Agent循环、任务/计划、通用工具、资源呈现和上下文生命周期。插件负责Houdini执行、信息与观察，通过[dsh-adapter](../src/dsh-adapter.ts)集中接入真实消息与工具日志接口。

唯一的Houdini preset由[生成器](../tools/gen-agent-presets.mjs)使用同版web-app标准声明生成，通过插件bundle patch注册到agent-preset-registry。内置模式在该组合禁用；插件没有dev/product模式或全局重复挂载。领域方法按需读取。

## 公开接口

| 接入 | 当前合同 |
|---|---|
| 配置 | Cordis 4.0.4与精确DSH包，插件组合在package.dsh.bundle.patch声明 |
| 模式 | dsh-agent-preset声明、registry默认Houdini |
| 消息 | 独立source.kind=dsh-houdini，使用DSH原生context |
| 工具 | defineTool注册，原始结果供程序使用、render负责模型文本、presentationMeta供界面 |
| 嵌套工具日志 | tools/ptc-dispatch-log公开扩展点保存明确标识的执行事实；不追加DSH不支持的事件类型 |
| 图像 | DSH原生附件与模型输入能力；图片展示不代替实际理解 |
| 客户端 | CJS factory、公开conversation/trajectory与workspace/session接口 |
| 运行历史 | Session格式4，native和PTC调用共用实际执行事实索引 |

原生工具结果使用meta.canonical；PTC持久日志的文本记录采用精确kind、调用ID和工具名定位。适配只改变日志副本，模型文本、程序值与附件走原生通道。模型任务判断不进入这份日志。

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

