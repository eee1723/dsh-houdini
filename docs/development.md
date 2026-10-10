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
| 开发评测 | [评测原则](product-modeling-evaluation.md)、evaluation/、tools/ | 公开题面与评审答案隔离；生产面不读取评审材料 |

新增长期生产模块必须加入架构代码地图。新增文档必须加入索引，说明它的职责及源码、验证入口。

## 构建与生成

```powershell
npm install
npm run build
npm run docs:check
```

只用 npm。build 刷新节点卡、动词结构合同、唯一Houdini preset、工具文档、客户端目录和Trace资源指纹，再编译TypeScript。`lib/`、生成区、`presets/houdini/cordis.patch.yml`不手改。

角色在 persona.md 维护；组合继承锁定版本 DSH 的标准插件，关闭其他内置 preset，只注册 Houdini。插件以 DSH 0.2 的 `bundle.patch` 装载配置：根级bare package `dsh-houdini`承载前端，preset内`dsh-houdini/agent`提供工具和原生context producer。DSH客户端模块图识别bare package，不能以preset scope或包子路径导入成功替代根客户端注册。客户端使用DSH的conversation/trajectory注册接口。

`docs:check` 只检查生成漂移、文档索引、模块覆盖和 Markdown 链接，不自动修文档。改动生成源后先 build，再检查最终一致性。

## 修改与验证

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

原生USD退出问题用[reproduce-usd-exit](../tools/reproduce-usd-exit.py)在指定`--hython`中运行独立的导入、内存stage和LOP对照，可重复传版本路径并用`--repeat`检查复现率。每次使用新偏好/package目录和明确HFS，不加载用户HIP或DSH插件；保留脚本主体完成标记、真实退出码与stdout/stderr。主体完成但进程非零退出仍属异常；相同退出码不能证明同一根因，headless结果不能外推GUI行为。证据写到新临时目录，不修改系统崩溃报告或用户配置。

COP接入材质使用[dsh-cop-material-delivery](../tools/tests/dsh-cop-material-delivery.test.py)在新建隔离工程中验证曲面贴图、材质直接采样alpha、粗糙度控制、`$HIP/dsh-texture`读回与同版本独立进程重开。完整纹理网络不以数值变化代替实际图片检查。跨版本节点/算法默认值可能不同，分别验证各版消费和重开，不默认像素一致。

指定生图接入使用[图像请求回归](../tools/tests/image-generation.test.mjs)覆盖精确路由、参考图片字节、防覆盖/文件策略、原图恢复与不自动重试；[真实DSH图片消费](../tools/tests/dsh-image-generation-smoke.test.py)用自有HTTP夹具验证动态设置/凭据、原生及PTC请求、真实附件与交付，默认不调用收费模型。真实提供方测试另记录实际model、请求、原图与视觉范围，不把夹具通过当成外部API可用。

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

节点交付的定向入口为[Host路由](../tools/tests/node-delivery.test.mjs)、[原生/嵌套卡片投影](../tools/tests/node-delivery-client.test.mjs)、[持久标识HOM](../tools/tests/dsh-node-delivery.test.py)及[排队取消HTTP/HOM](../tools/tests/dsh-node-navigation-cancel.test.py)。跨层修改还需在精确DSH组合和新建的隐藏GUI进程中，由真实Agent工具循环产生原生/嵌套回执，选中对应任务点击实际卡片，回读网络/参数页；重开同HIP并改名后再点击旧卡片，切HIP核对错误提示，暂停队列后切任务并恢复队列核对旧导航没有生效。局部模拟通道不能替代这条连接；测试脚本、截屏、完整结果和运行目录留在仓库外证据目录。服务框保存重开由[服务框回归](../tools/tests/dsh-render-service-box.test.py)核对标题、固定边界、真实成员与用户节点位置。

## 隔离开发工具

[hda-delivery-check.py](../tools/hda-delivery-check.py)在新 hython 中加载声明 HDA，按 manifest 创建实例、设置参数、调用按钮并检查几何/参数/错误。判据应能区分正确与错误结果，例如尺寸控制检查 bounds_size，而非只有点面数。

原库版本维护用[HDA版本机制回归](../tools/tests/dsh-hda-versions.test.py)覆盖多定义保留、同库追加、参数/关键帧/表达式/锁定/连线、失败恢复和权限；[DSH版本维护贯通](../tools/tests/dsh-hda-version-smoke.test.py)以`--runtime-cache <精确DSH缓存> --hython <目标hython>`启动隔离真实Bridge和DSH会话，核对普通/嵌套调用的回执、会话/现场身份、新旧定义行为及下一进程Package发现。规划模型为受控夹具；这些检查不证明用户GUI版本菜单、任意回调或自然任务自主采用。

工具制作的机制检查包括[真实工具目录](../tools/tests/dsh-tool-catalog.test.py)、[共享定义与分叉](../tools/tests/dsh-hda-definition-ownership.test.py)、[参数组件](../tools/tests/dsh-hda-ui-components.test.py)、[原生Package配置发现](../tools/tests/dsh-package-discovery.test.py)和[注册/运行态失败](../tools/tests/dsh-tool-packages.test.py)。[发现GUI](../tools/tests/dsh-package-gui.test.py)核对已配置、条件与实际加载的不同状态；[Package GUI](../tools/tests/dsh-tool-packages-gui.test.py)以普通包名JSON直接指向唯一源目录，核对干净启动发现/当前加载、HDA/Shelf/Panel实际来源与公开入口、旧内容保持，以及启停不改变配置或源。已有包新增资源后从新进程验证，不靠隐式reload证明更新安全。Shelf和Viewer State需要回到Houdini外层事件循环后再验状态；installFile/sys.path不替代此路径。不同载体的结果保留实际范围，不从固定例子外推任意工具泛化。

```powershell
python tools/hda-delivery-check.py --manifest path/to/tool-check.json --hython D:/houdini/bin/hython.exe --output path/to/report.json
```

[isolated-houdini-check.py](../tools/isolated-houdini-check.py)在新场景执行可信 builder，经 Bridge 完成明确 cook/cache/ROP 检查。manifest 指定 script 和 checks；`--trusted` 表示调用方授权执行该脚本。产物目录是仓库外的新目录，报告保留实际执行与文件证据。

```powershell
python tools/isolated-houdini-check.py --trusted --manifest path/to/check.json --hython D:/houdini/bin/hython.exe --output-dir D:/checks/run-001 --timeout 120 --memory-mb 4096
```

[isolated-worker.py](../tools/isolated-worker.py)及 [Houdini worker](../houdini/python3.11libs/dsh_isolated_worker.py)是开发评测使用的自有新进程入口；[worker 回归](../tools/tests/dsh-isolated-worker.test.py)验证明确 IPC、启动与回收。[delivery-audit](../tools/delivery-audit.mjs)只在开发评测中从会话回执读取交付事实。它们不进入模型的生产工具目录。

隔离工具通过自有进程句柄和 Windows Job 管理超时、取消及进程树内存。报告与退出状态都要读取；不把启动成功当作负载完成。任意 Python、回调、绝对路径文件和外部服务的副作用不属于场景恢复保证。

收费任务只在用户授权的模型与预算范围内运行 [run-modeling-trial.py](../tools/run-modeling-trial.py)。使用隔离任务目录、精确 DSH/Node/Houdini 和明确provider/model，只复制所选路由及必要credential reference，不修改用户设置或live。教程试验通过显式`--service-profile`加入单个转录服务与用途选择，不复制整个用户配置；服务说明只含provider/api/baseURL/apiKeyEnv/model/models及可选python。DSH自定义服务商需要非空的真实聊天模型目录`models`；独立的`model`填写实际转录模型，不把ASR伪装为聊天能力。密钥仍由隔离凭据引用或指定环境变量解析。时间上限不等于费用上限，按提供方实际价格/套餐边界核算；DSH observer的usage事件与未知费用分别记录。评审答案不进入生产提示词或用于未见题调参。

验证自然复刻能力时使用`--no-feedback --approval-policy never`且不传followup；只提交初始用户目标、来源与环境事实，运行中不向作者补充接线、参数、截图答案或几何/效果修正。冻结初始输入与禁止外部反馈不限制作者自主调查：作者可以只读原片、回查原分析，并在自己的`dsh-analysis/`中抽取画面、补证及整理；原始资料不改写，成功音频不重复上传。任务说明不能用“启动后不补资料”同时指代外部答案介入和作者自主补证；范围有歧义时，不将该运行计作主动补证能力通过。工具缺陷在运行后回到系统维护源修复，用新快照验证，受干预运行不作为独立能力证据。复用已有分析与只给视频的冷启动分别报告。
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

[签名包部署验收](../tools/tests/dsh-deployment-e2e.test.py)使用实际离线包、独立安装与数据目录，检查精确Node/DSH、profile、认证RPC和所选H21/H22 Bridge。可选`--previous-bundle <旧受信包目录>`再覆盖旧包自身入口与profile准备、新版失败快照保留和重试、各版独立数据、回退不合并以及同版重新安装恢复损坏的私有媒体工具。测试数据只证明文件与版本选择保持，不证明DSH旧会话格式转换或模型续跑。正式Qt入口另用[发行GUI验收](../tools/tests/dsh-gui-release.test.py)，不能用源码页面检查替代签名安装。
