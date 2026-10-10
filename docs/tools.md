# Houdini 工具说明

本页由[src/tool-catalog.ts](../src/tool-catalog.ts)生成，代码注册与Trace工具说明共用这一份职责目录。Houdini参数及执行以[src/tools.ts](../src/tools.ts)为准，Host生图以[image-generation](../src/image-generation.ts)、教程离线处理以[video-process](../src/video-process.ts)、转录以[video-transcription](../src/video-transcription.ts)为准。

系统提供准确的场景信息、充分的批量操作、真实反馈和观察结果。理解需求、选择方法、安排步骤与判断效果由模型负责；领域知识按任务需要读取。

| 工具 | 为什么存在 | 输入 | 返回 | 执行位置 |
|---|---|---|---|---|
| `houdini_inspect` · 观察现场 | 读取真实Houdini场景、节点、参数和能力资料。 | 只读Python代码；hou与动词已导入。 | 读取结果、诊断及本次观察的场景身份。 | Houdini主线程，只读 |
| `houdini_exec` · 执行操作 | 批量创建、修改、检查、保存或出图。 | Python代码，可组合动词；__result__返回结构数据。 | 结果、真实错误、操作记录、事务状态、图像和文件。 | Houdini主线程，串行 |
| `houdini_request` · 查回执行 | 回答某个未知响应的请求是否执行、是否完成；避免重复修改。 | request_ref，或index列出本会话可查回请求。 | 原执行状态与可取得的原始结果；不会重发代码。 | Bridge请求记录，无HOM |
| `houdini_resource` · 读取资料 | 按需读取原始用户资料与完整历史工具结果。 | kind=source/result、ref及可选分页；result可选JSON Pointer。 | 原文或JSON分页及继续读取位置。 | DSH Host，无HOM |
| `houdini_capabilities` · 观察通道 | 确认当前模型能否接收图片，以及附件通道是否可用。 | 无需参数。 | 当前模型与附件能力事实；不会渲染或判断画面。 | DSH Host，无HOM |
| `houdini_ui_list` · 发现界面 | 列出当前Houdini中可见的原生pane及Qt窗口/面板，提供明确截图目标和实际支持状态。 | 无需参数；不打开或切换界面。 | 当前runtime目标引用、类型、用途线索、实际区域及支持/未支持原因。 | Bridge主线程队列，只读发现 |
| `houdini_ui_screenshot` · 观察界面 | 截图明确的当前可见界面；目标须完整在屏内且无遮挡。 | target为houdini_ui_list发现所得引用；可选path/output_policy。不打开或调整界面，不传Python代码。 | 真实PNG附件、准确目标区域、实际尺寸与状态保持事实；识图与捕获分别判断。 | Bridge主线程队列分阶段观察/捕获，不改导航或窗口状态 |
| `houdini_job_submit` · 提交长任务 | 把渲染、模拟或长计算放入Houdini队列并立即返回。 | Python代码；与exec相同的操作能力。 | jobId及提交回执。 | Houdini串行队列 |
| `houdini_job_status` · 等待长任务 | 读取或等待长任务状态和结果。 | jobId及可选wait秒数。 | queued/running/done/failed/cancelled及实际结果。 | Bridge任务记录 |
| `houdini_job_cancel` · 取消长任务 | 取消尚未执行的任务，并对运行中的任务发出取消意图。 | jobId。 | 实际取消状态；运行中的HOM操作不会被强杀。 | Bridge任务控制 |
| `image_models` · 发现生图模型 | 读取DSH已配置的OpenAI兼容API路由和模型名称，供指定生图模型使用；不调用模型，不证明图片接口可用。 | 可选provider和模型名称子串query，默认image。 | 配置中的provider/model及图片接口支持尚未验证的说明；不返回凭据。 | DSH Host，无HOM |
| `image_generate` · 生成参考或纹理图 | 使用指定provider/model生成或编辑一张图片，实际上传参考像素；默认按当前HIP目录和用途分配文件，显式目的地支持离线工作。 | provider、model、prompt；purpose=reference/texture，output_policy=managed/explicit；可选output、references、size、quality、background。 | 实际路径、工程锚点和目录角色、来源指纹、原图恢复/预览附件及请求事实；不自动重试或更换模型。 | DSH Host HTTP与文件；managed只读查询所选Houdini现场 |
| `video_process` · 处理教程资料 | 在Host受控进程中导入/抽帧和查询/整理本地教程证据，复用原脚本的来源校验及唯一文件记录。 | operation与options；只接受随包离线命令，路径绝对，写入使用工作区内新output目录。 | 原命令JSON、进度、实际退出状态、选定Houdini的Python/私有媒体工具与输出路径；不认证语义。 | DSH Host普通Python子进程，无shell/密钥/云请求/HOM |
| `video_models` · 发现转录配置 | 读取教程视频的转录用途配置、DSH服务商和凭据状态；不上传音频，不证明转录接口可用。 | 可选provider和模型名称子串query。 | 默认用途、API路由、模型建议和缺失配置诊断；不返回凭据。 | DSH Host，无HOM |
| `video_transcribe` · 转录教程音频 | 用DSH中选定服务商与转录模型并行处理已准备的教程音频，复用原任务的分片和请求记录。 | work、allow_upload；可选provider/model、chunks、max_chunks、concurrency、requests_per_second、术语词表、说话人分离及明确授权的重试预算。 | 逐片进度、实际在途峰值与成功/失败、剩余/未知请求、原任务目录及准确模型；原始响应和时间戳在同源outcome中，密钥只交给受控子进程。 | DSH Host Python子进程与HTTP，无HOM |

观察现场和读取历史分开，是因为前者读取当前Houdini，后者可以在Houdini离线时使用。查回执行分开，是因为响应丢失后应取回原结果。长任务的提交、等待和取消分开表达各自真实状态。

保存、渲染、节点发现与几何检查属于可组合的Python能力，详见[动词目录](tool-design.md)。领域工作方法在[skills](../skills/)维护；任务计划使用DSH已有能力。

验证入口：[工具注册与展示](../tools/tests/houdini-tool-presentation.test.mjs)、[请求查回](../tools/tests/request-recovery.test.mjs)、[历史结果](../tools/tests/result-details.test.mjs)。
