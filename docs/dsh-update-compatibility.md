# DSH 与插件版本适配

插件是官方 DSH Desktop 的标准 bundle，使用宿主原生会话、模型、任务与文件权限。当前锁定并实测的宿主版本为 **0.2.1-rc.3**；新版本须按下述资格流程重新核对，不以浮动 npm 标签推断兼容。精确支持源为[兼容清单](../dsh-runtime-compatibility.json)，开发依赖锁为[package-lock](../package-lock.json)。同版本号不能代替组件身份与实际消费者验证。

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

## DSH耦合点与升级维护

| 边界 | 唯一实现与验证入口 |
|---|---|
| bundle/preset 与工具 scope | [生成器](../tools/gen-agent-presets.mjs)、[preset 回归](../tools/tests/dsh-preset-parity.test.mjs)、[真实官方组合](../tools/tests/dsh-host-smoke.test.py) |
| 本机接入、启动及导航 | [Desktop 服务](../src/desktop-integration.ts)、[通道反例](../tools/tests/desktop-integration.test.mjs)、[原生菜单检查](../tools/tests/dsh-desktop-client.test.py)、[真实页面](../tools/tests/dsh-client-navigation.mjs) |
| 原生历史与 HIP 观察 | [保存观察](../src/scene-recovery.ts)、[Save As 回归](../tools/tests/scene-directory-follow.test.mjs)、[目标路由](../tools/tests/executor-routing.test.mjs) |
| 工具结果、jobs 与上下文 | [DSH 适配](../src/dsh-adapter.ts)、[live jobs](../src/live-jobs.ts)、[结果回归](../tools/tests/dsh-adapter.test.mjs)、真实 Host/Bridge 组合 |
| Bridge 与领域执行 | [执行契约](execution-contract.md)、[开发维护](development.md#修改与验证)中的隔离 H21/H22 检查 |

开发验证使用[官方宿主准备器](../tools/prepare-dsh-runtime.mjs)，只安装未修改的精确官方包，不应用核心补丁。运行时缓存不属于用户发行物。工作区、账户、网络、通知等通用问题先核对官方版本和公开接口，再按开发规范比较解决方案，不能恢复整套私有核心差异作为默认修复。

## 账户能力与入口验收

账户归宿主管理是所有权约束，不表示每个官方版本都提供旧适配版的全部登录入口。迁移或删去私有扩展时，须逐项核对用户实际入口、可用登录方式、授权保存与刷新、账号模型目录及真实请求；依赖包存在、后端有OAuth或模型名字可见，都不能代替这条验收链。

官方0.2.1-rc.3的[提供方登录实现](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.3/packages/llm/llm-pi-ai/src/login.ts)明确排除了`openai`的OAuth，原生账号页只呈现DeepSeek；旧ChatGPT订阅页面及其`piAiAccounts`等扩展并无等价交付。`openai-codex`后端流程属于另一条路线。当前公开authorization服务允许新增流程，但同一凭据key只允许一个owner，不能通过覆盖已注册流程、私读凭据或换提供方名称冒充恢复。

方案选择顺序为：先消费完整可用的官方入口；缺少通用展示层时以独立的薄授权扩展呈现现有流程，凭据与续期继续由原提供方负责；提供方本身缺少安装身份或注册生命周期合同时，优先形成窄上游改进。恢复旧核心补丁会重新承担账户、注册、目录与升级的耦合，不作为Houdini插件的默认方案。完整原路线尚未恢复时，安装说明明确缺口，不承诺用户换个入口即可登录。

## 新 DSH 版本的资格流程

核对官方发行、npm 标签与实际可获取包，选择精确版本，更新兼容声明和锁文件；构建后验证标准模式仍为原默认、其他 preset 可用、Houdini 工具只在对应 scope、根客户端只有一份。启动/导航变化必须在实际页面核对所选任务、工作区、preset 与现场；配置存在或局部 RPC 成功不能代替消费方状态。

涉及文件/持久化时核对未修改官方读取器的重开与原值。涉及执行边界才选择必要的 H21/H22 HOM 回归，不因移除 Qt 壳机械重跑全部模型质量评测。用户现场实际加载与源码验证分开报告。

## 正式发行单元与发布门

标准发布物是符合 npm 包格式的 `.tgz` 插件包及其 Houdini helper/领域资源，使用[发布构建器](../tools/build-release.py)；包格式不表示已发布到 npm。媒体功能保留插件私有 FFmpeg/ffprobe、依赖、许可与完整源码资源，按[安装](setup.md#教程视频与转录设置)定位；不捆绑另一套 DSH 会话或运行时。构建失败不得以缺资源的包宣称离线能力齐全。

正式交付须核对 Desktop 安装/启停、其他模式保持、两条完整用户入口、H21/H22 helper 身份与重开。main push、tag、Draft 或源码 build 不代表已安装和正式发布；尚欠项见[交接](handoff.md)。

当前代码等待维护者实测，暂不发布新版。源码CI与手动候选构建均不执行Release或npm发布；候选只作为测试输入。测试者应使用维护者提供的完整tgz，并优先从原生插件管理安装本地文件，历史独立工作台包不属于本次标准插件交付。
