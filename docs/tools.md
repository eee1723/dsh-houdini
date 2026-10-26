# Houdini 工具说明

本页由[src/tool-catalog.ts](../src/tool-catalog.ts)生成，代码注册与Trace工具说明共用这一份职责目录。现场工具以[src/tools.ts](../src/tools.ts)、独立hython以[isolated-execution](../src/isolated-execution.ts)为准，Host生图以[image-generation](../src/image-generation.ts)、教程离线处理以[video-process](../src/video-process.ts)、转录以[video-transcription](../src/video-transcription.ts)为准。

系统提供准确的场景信息、充分的批量操作、真实反馈和观察结果。理解需求、选择方法、安排步骤与判断效果由模型负责；领域知识按任务需要读取。

| 工具 | 为什么存在 | 输入 | 返回 | 执行位置 |
|---|---|---|---|---|
| `houdini_inspect` · 观察现场 | 读取真实Houdini场景、节点、参数和能力资料。 | 只读Python代码；hou与动词已导入。 | 读取结果、诊断及本次观察的场景身份。 | Houdini主线程，只读 |
| `houdini_exec` · 执行操作 | 批量创建、修改、检查、保存或出图。 | Python代码或绝对UTF-8 .py脚本；script可带expected_sha256及code调用尾段，不使用exec(open(...))加载；__result__返回结构数据。 | 结果、真实错误、操作记录、事务状态、脚本版本、图像和文件。 | Houdini主线程，串行 |
| `houdini_request` · 查回执行 | 回答某个未知响应的请求是否执行、是否完成；避免重复修改。 | 原请求的request_ref；index仅列当前所选运行实例中本会话的回执。 | 原执行状态与可取得的原始结果；不会重发代码。 | Bridge请求记录，无HOM |
| `houdini_resource` · 读取资料 | 按需读取原始用户资料、完整历史工具结果及已归档加载警告。 | kind=source/result、ref及可选分页；result可选JSON Pointer。 | 原文或JSON分页及继续读取位置。 | DSH Host，无HOM |
| `houdini_capabilities` · 观察通道 | 确认当前模型能否接收图片，以及附件通道是否可用。 | 无需参数。 | 当前模型与附件能力事实；不会渲染或判断画面。 | DSH Host，无HOM |
| `houdini_isolated` · 独立Houdini执行 | 按需在新hython中执行构建脚本、已保存工程副本及加载后的准备操作，取得真实检查、错误和图片，供当前作者或团队成员自验证。 | operation=run/read、manifest；run可选全新output_dir，默认在当前DSH工作区execution_run角色内分配唯一目录；read传原run路径。使用已选现场登记的安装信息，离线仍可运行；可选houdini_installation显式指定HFS。manifest支持hip+script与input_root；可选background、timeout_seconds、memory_mb。 | 独立运行报告、输入版本、构建结果、检查和原生图片；大型原始回执单份保留并返回details；后台使用DSH job_output/job_kill。 | Host监管的一次性独立hython，不修改当前现场、不自动合并 |
| `houdini_ui_list` · 发现界面 | 列出当前Houdini中可见的原生pane及Qt窗口/面板，提供明确截图目标和实际支持状态。 | 无需参数；不打开或切换界面。 | 当前runtime目标引用、类型、用途线索、实际区域及支持/未支持原因。 | Bridge主线程队列，只读发现 |
| `houdini_ui_screenshot` · 观察界面 | 截图明确的当前可见界面；目标须完整在屏内且无遮挡。 | target为houdini_ui_list发现所得引用；可选path/output_policy。不打开或调整界面，不传Python代码。 | 真实PNG附件、准确目标区域、实际尺寸与状态保持事实；识图与捕获分别判断。 | Bridge主线程队列分阶段观察/捕获，不改导航或窗口状态 |
| `houdini_job_submit` · 提交长任务 | 把渲染、模拟或长计算放入Houdini串行队列，由DSH原生jobs跟踪、通知和收集。 | Python代码或script、expected_sha256及可选code调用尾段；与exec相同的操作能力。 | DSH job_id用于job_output/job_kill，Bridge jobId和原request_ref用于真实结果及恢复；houdini_request查回原结果和图片。 | DSH jobs观察；Houdini主线程串行执行 |
| `image_models` · 发现生图模型 | 读取DSH已配置的OpenAI兼容API路由和模型名称，供指定生图模型使用；不调用模型，不证明图片接口可用。 | 可选provider和模型名称子串query，默认image。 | 配置中的provider/model及图片接口支持尚未验证的说明；不返回凭据。 | DSH Host，无HOM |
| `image_generate` · 生成参考或纹理图 | 使用指定provider/model生成或编辑一张图片，实际上传参考像素；默认按当前HIP目录和用途分配文件，显式目的地支持离线工作。 | provider、model、prompt；purpose=reference/texture，output_policy=managed/explicit；可选output、references、size、quality、background。 | 实际路径、工程锚点和目录角色、来源指纹、原图恢复/预览附件及请求事实；不自动重试或更换模型。 | DSH Host HTTP与文件；managed只读查询所选Houdini现场 |
| `video_process` · 处理教程资料 | 在Host受控进程中导入/抽帧和查询/整理本地教程证据，复用原脚本的来源校验及唯一文件记录。 | operation与options；只接受随包离线命令，路径绝对，写入使用工作区内新output目录。 | 原命令JSON、进度、实际退出状态、选定Houdini的Python/私有媒体工具与输出路径；不认证语义。 | DSH Host普通Python子进程，无shell/密钥/云请求/HOM |
| `video_models` · 检查教程配置 | 检查教程专用转录协议、准确模型、DSH凭据状态和本机依赖；不以聊天模型目录证明语音能力。 | 可选provider/名称过滤。 | 非秘密配置、缺项、能力边界与真实运行路径；不上传音频或返回密钥。 | DSH Host，无HOM |
| `video_configure` · 配置教程服务 | 按用户选择保存教程专用非秘密设置，复用DSH原生设置与凭据；不改聊天模型或接收密钥。 | 明确的文件协议、已有服务商或完整端点、模型ID；可选认证/并发/速率。 | 实际生效配置、缺项和安全录入密钥的下一步；旧任务仍绑定原服务。 | DSH Host，仅本插件设置，无HOM |
| `video_transcribe` · 转录教程音频 | 用DSH中选定服务商与转录模型并行处理已准备的教程音频，复用原任务的分片和请求记录。 | work、allow_upload；可选provider/model、chunks、max_chunks、concurrency、requests_per_second、术语词表、说话人分离及明确授权的重试预算。 | 逐片进度、实际在途峰值与成功/失败、剩余/未知请求、原任务目录及准确模型；原始响应和时间戳在同源outcome中，密钥只交给受控子进程。 | DSH Host Python子进程与HTTP，无HOM |

观察现场和读取历史分开，是因为前者读取当前Houdini，后者可以在Houdini离线时使用。查回执行分开，是因为响应丢失后应取回原结果。长任务的提交、等待和取消分开表达各自真实状态。

保存、渲染、节点发现与几何检查属于可组合的Python能力，详见[动词目录](tool-design.md)。领域工作方法在[skills](../skills/)维护；任务计划使用DSH已有能力。

验证入口：[工具注册与展示](../tools/tests/houdini-tool-presentation.test.mjs)、[请求查回](../tools/tests/request-recovery.test.mjs)、[历史结果](../tools/tests/result-details.test.mjs)。
