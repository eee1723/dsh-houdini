# 系统架构与代码地图

## 运行边界

dsh-houdini是Cordis形状的DeepSeek Harness插件，不是独立MCP服务器。TypeScript Host注册
5个工具，通过HTTP驱动一个已运行的Houdini；只有Houdini侧Python使用HOM。
用户内容输出锚定$HIP，插件源码不是任务工作区。后台job是异步排队，不是同一HOM会话并行。

```text
用户消息 → preset/persona + 按需skill
         → src/context.ts：每条用户消息至多一次只读现场摘要
         → src/tools.ts → src/bridge.ts：类型/权限上下文、握手、请求
         → dsh_bridge.py：HTTP → 主线程队列 → 受限执行/动词追踪
         → dsh_hou_helpers.py → SOP/几何/相机模块
         → 结构化结果、operation-evidence、原生图像附件 → Host → client/trace
```

静态文档和构建通过不证明live已加载。查看当前/预期版本与重载要求使用[兼容设计](dsh-update-compatibility.md)
和[安装更新](setup.md)，不要从历史日志推断部署状态。

## Host与浏览器

| 源码 | 维护职责 |
|---|---|
| [src/index.ts](../src/index.ts) | Cordis注册、稳定且persona中性的guidance、配置入口 |
| [src/image-output.ts](../src/image-output.ts) | Bridge 图像→DSH 原生附件；模型能力检查、字节限额、原生与 Code Mode 图像返回，无工作区副本 |
| [src/tools.ts](../src/tools.ts) | 五工具schema、参数分支互斥、结果/原生图像交付、纯展示函数 |
| [src/bridge.ts](../src/bridge.ts) | HTTP、取消/超时、每次场景执行前比对词表及语义版本 |
| [src/context.ts](../src/context.ts) | 按需指代采集、message绑定及预算；pre-step按公开surface去重独立补充段，历史替换时恢复，普通查询不追加上下文 |
| [src/execution-state.ts](../src/execution-state.ts) | 从公开工具事件重建有限历史状态及未决请求/检查失效/运行身份变化提醒；不按时间戳/计数触发注入，不维护另一事实库 |
| [src/task-sources.ts](../src/task-sources.ts) | 公开session中的原始用户消息/澄清问答来源锚、去重、有限摘录及同session分页回读；目标仅为计划记录，不推导需求替代/授权/验收 |
| [src/result-details.ts](../src/result-details.ts) | 大返回的不可变hash文件、原workspace内分页JSON Pointer读取、损坏校验和保存失败回退；不执行HOM |
| [src/ask-user-guard.ts](../src/ask-user-guard.ts) | 交互选择题的互斥性与可执行约束 |
| [src/skill.ts](../src/skill.ts) | 随包skill/resource注册 |
| [src/generated-verb-contract.ts](../src/generated-verb-contract.ts) | 构建生成的Host名称/hash/语义版本，不手改 |
| [client.js](../client.js) | 手写CJS factory；Houdini Trace视图、回放解析和生成目录 |
| [client/trace-view.js](../client/trace-view.js)、[trace-view.css](../client/trace-view.css) | 五看板、公开Trajectory请求/调用适配、结构化详情、技能证据与类型配色；构建嵌入client.js |

默认配置在src/index.ts：bridgeUrl为loopback 8765、requestTimeoutMs为120000、
automaticContext默认开启。超时不取消已开始的HOM修改，重试前回读状态。
scene-context只为现场指代提供用户消息绑定的metadata；execution-state按有意义的异常变化提醒，
task-sources是按需回读/历史替换恢复用的原始材料索引。补充段独立记入plugin消息，不随Host整包runtime context重发。
三者不互相替代。缺失不等于空场景，被动选择变化不构成新任务或foreign修改授权。
client消费公开trajectory snapshot，不依赖已删除的Session内部字段。

## Houdini执行模块

| 源码 | 维护职责 / 深入文档 |
|---|---|
| [dsh_bridge.py](../houdini/python3.11libs/dsh_bridge.py) | HTTP/main-thread queue、job、Raw Gate、query、transaction、trace envelope |
| [dsh_requests.py](../houdini/python3.11libs/dsh_requests.py) | 同runtime的有界exec/jobs回执、owner_call索引、payload/owner冲突拒绝和原结果/jobId查回；无HOM，不重提代码 |
| [dsh_hou_helpers.py](../houdini/python3.11libs/dsh_hou_helpers.py) | 58动词的主要实现、真实Tab/Shelf、参数、provenance、HDA、USD、render入口 |
| [dsh_sop_contracts.py](../houdini/python3.11libs/dsh_sop_contracts.py) | build_module/verify_network、静态预检、失败清理、有序点弦长 |
| [dsh_operation_cards.py](../houdini/python3.11libs/dsh_operation_cards.py) | [节点卡](node-operation-cards.md)加载、精确类型限制、关键参数与决策提示 |
| [dsh_geometry_observation.py](../houdini/python3.11libs/dsh_geometry_observation.py) | Polygon边界/连通/朝向/截面、唯一性、稳定ID位移与变换 |
| [dsh_quality_contracts.py](../houdini/python3.11libs/dsh_quality_contracts.py) | 实际接口、拓扑/domain和可恢复control实验 |
| [dsh_camera_framing.py](../houdini/python3.11libs/dsh_camera_framing.py) | 八角点投影、预览取景/深度分离与镜头缩放、静态OBJ camera_fit、实际USD产品预检 |
| [dsh_context.py](../houdini/python3.11libs/dsh_context.py) | 主线程现场metadata，无socket/进程探测 |

[执行与证据契约](execution-contract.md)维护这些模块的跨层不变量，节点领域recipe在skills。

## 生命周期与机器态

| 源码 / 配置 | 职责 |
|---|---|
| [houdini/install.py](../houdini/install.py) | Houdini package安装、profile同步入口 |
| [MainMenuCommon.xml](../houdini/MainMenuCommon.xml) | Open Workspace、Version & Diagnostics菜单 |
| [dsh_launcher.py](../houdini/python3.11libs/dsh_launcher.py) | worker启动/repair、主线程接入、模块重载、HIP工作区、preset同步 |
| [dsh_manager.py](../houdini/python3.11libs/dsh_manager.py) | 版本诊断UI、DSH npm与插件Git双更新通道 |
| [dsh_webview.py](../houdini/python3.11libs/dsh_webview.py) | QtWebEngine窗口、cookie、DocumentCreation兼容补丁 |
| [dsh_web_auth.py](../houdini/python3.11libs/dsh_web_auth.py) | process-token→signed cookie、RPC wire与会话请求 |
| [dsh_profile_sync.py](../houdini/python3.11libs/dsh_profile_sync.py) | 官方CLI幂等同步profile依赖、精确版本兼容修补 |
| [dsh_runtime_compat.py](../houdini/python3.11libs/dsh_runtime_compat.py) | 精确兼容清单读取/选择，未知latest不自动激活 |
| [dsh-runtime-compatibility.json](../dsh-runtime-compatibility.json) | preferred DSH及支持组合的唯一清单 |
| [dsh-profile.requirements.json](../dsh-profile.requirements.json) | 受管profile依赖与移除清单 |
| [cordis.patch.yml](../cordis.patch.yml) | bundle组合与插件配置 |
| [presets](../presets/) | Houdini生产/开发persona；身份与领域工作方式，不放进插件guidance |

GUI线程不得阻塞socket/子进程/netstat探测；进程缓存的UI/package变更需要完整重启Houdini。
python3.11libs是目录名，通过PYTHONPATH共享纯Python实现，支持矩阵以兼容清单为准。

## 视觉、追踪和开发工具

视频教程解析由[video skill](../skills/houdini-video-tutorial/SKILL.md)组织，
[video_tutorial.py](../skills/houdini-video-tutorial/scripts/video_tutorial.py)在普通宿主进程中执行
本地媒体准备、授权云转录、全片均匀粗扫/局部重看和结果校验，不经 Bridge、不调用 HOM。
帧索引保留实际 PTS 和播放时间轴起点；缩略图联系表与按显式区域比较的像素变化候选用于导航，
候选保留前后原图、阈值和时间区间，不做自动语义或操作识别。
局部 `context` 汇集 hash 绑定的图像与转录，`check-notes` 校验 agent 填写的状态/操作记录，
只提供引用和结构验证，不证明语义真实性，不执行其中内容，也不据此授权工程修改。
依赖宿主 Python、FFmpeg、SiliconFlow 凭据及当前模型的原生图像输入能力；注册 skill 不会安装依赖。
原视频、切片、转录及画面依据保存在仓库外任务目录，不进入包或 Trace 来源目录。
输入目前为本地视频，脚本不下载链接、不做语义识图，也不自动复现工程或更新生产知识。

图片由Bridge按请求关联产图事实，经Host送入DSH原生附件存储和多模态工具结果，不复制到工作区media目录、不调用独立识图工具。附件传递不是语义验证，当前模型须实际查看图像。
正式渲染、预览服务和用户viewport分别管理，不能通过用户视口状态选择交付目标。
Trace记录动词ledger、rawUsage、Gate、transaction与execution观察；Host在原生metadata保留返回事实，
大结果保存到workspace的.dsh-houdini-results后才精简模型文本。该目录是工具返回副本，不是HIP内容输出。
失败/警告/unsupported/恢复错误、媒体路径和权限提示保留；未知结果可通过已提供的result_ref按字段读取。
页面信息架构、内容来源与历史快照同步规则见[Houdini Trace设计](houdini-trace-design.md)。
该文档区分实际请求System/schema/usage、上下文事件与当前构建来源目录；逐段运行provenance和最终messages可见集合尚未提供。

| 工具 | 长期职责 |
|---|---|
| [catalog-lib.mjs](../tools/catalog-lib.mjs)、[gen-client-catalog.mjs](../tools/gen-client-catalog.mjs) | 词表解析与Host/client生成 |
| [gen-trace-client.mjs](../tools/gen-trace-client.mjs) | 同源提取guidance/preset/注册技能与资源，嵌入手写Trace组件、样式及evidence-helpers副作用分类/采用统计函数；--check只读漂移验证 |
| [gen-node-card-docs.mjs](../tools/gen-node-card-docs.mjs) | JSON节点卡→文档，严格schema与漂移检查 |
| [normalized-trace-steps.mjs](../tools/normalized-trace-steps.mjs)、[trace-session-lib.mjs](../tools/trace-session-lib.mjs) | 多帧zstd/回放去重、调用结果时序归一；逐请求usage去重及字段算术、逐轮错误/目标变更/压缩事件提取 |
| [trace-report.mjs](../tools/trace-report.mjs) | 独立可读HTML目录与时间线 |
| [trace evidence extractor](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[evidence helpers](../skills/houdini-trace-analysis/scripts/evidence-helpers.mjs) | 确定性调用/安全/视觉/证据提取 |
| [run-node-tests.mjs](../tools/run-node-tests.mjs)、[prune-retired-build.mjs](../tools/prune-retired-build.mjs) | 回归发现与退役构建文件清理 |
| [camera-karma-smoke.py](../tools/camera-karma-smoke.py)、[camera-opengl-smoke.py](../tools/camera-opengl-smoke.py) | 隔离真实renderer/GUI验收入口，不代替语义识图 |

评测工具与schema见[评测设计](benchmark-design.md)。tools/prototypes、一次性probe及tools/out
不是生产API，不把其试验方案提升为现役功能；测试入口见[开发维护](development.md)。
