# DSH 与插件版本适配

本项目通过DSH公开接口加载，当前精确目标是 **0.2.0-rc.2**。选择源为[兼容清单](../dsh-runtime-compatibility.json)，依赖锁在[package-lock](../package-lock.json)和[受管锁](../deployment/package-lock.json)。

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

Houdini WebView采用H21/H22实际QtWebEngine。修复Host与Bridge、重开客户端以及正式安装组合的验证各自说明；编译通过不代表已有进程加载。已知浏览器接口补齐由[webview](../houdini/python3.11libs/dsh_webview.py)与[polyfill生成器](../tools/gen-web-polyfills.mjs)管理，不修改上游缓存。

## 正式发行单元与发布门

正式发行交付一个精确组合：插件源码提交、Node、DSH、完整依赖、平台/Houdini支持范围以及文件摘要。受管安装使用签名release.json和离线包，详见[安装](setup.md#正式发行与受管安装合同)。

main push、tag和Draft不构成正式发行；发布端构建和校验组合，用户安装不运行源码build。旧版本回退不改写用户工程。普通开发按改动选择必要检查，正式发行补正常入口与受管安装验收。

当前未验证的正常加载、模型质量与发行事项在[交接](handoff.md)维护。

