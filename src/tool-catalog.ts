/** Public purpose of each tool; registration, UI and docs consume this catalog. */
export const HOUDINI_TOOLS = {
  houdini_inspect: {label:'观察现场',purpose:'读取真实Houdini场景、节点、参数和能力资料。',input:'只读Python代码；hou与动词已导入。',output:'读取结果、诊断及本次观察的场景身份。',execution:'Houdini主线程，只读'},
  houdini_exec: {label:'执行操作',purpose:'批量创建、修改、检查、保存或出图。',input:'Python代码，可组合动词；__result__返回结构数据。',output:'结果、真实错误、操作记录、事务状态、图像和文件。',execution:'Houdini主线程，串行'},
  houdini_request: {label:'查回执行',purpose:'回答某个未知响应的请求是否执行、是否完成；避免重复修改。',input:'request_ref，或index列出本会话可查回请求。',output:'原执行状态与可取得的原始结果；不会重发代码。',execution:'Bridge请求记录，无HOM'},
  houdini_resource: {label:'读取资料',purpose:'按需读取原始用户资料与完整历史工具结果。',input:'kind=source/result、ref及可选分页；result可选JSON Pointer。',output:'原文或JSON分页及继续读取位置。',execution:'DSH Host，无HOM'},
  houdini_capabilities: {label:'观察通道',purpose:'确认当前模型能否接收图片，以及附件通道是否可用。',input:'无需参数。',output:'当前模型与附件能力事实；不会渲染或判断画面。',execution:'DSH Host，无HOM'},
  houdini_ui_list: {label:'发现界面',purpose:'列出当前Houdini中可见的原生pane及Qt窗口/面板，提供明确截图目标和实际支持状态。',input:'无需参数；不打开或切换界面。',output:'当前runtime目标引用、类型、用途线索、实际区域及支持/未支持原因。',execution:'Bridge主线程队列，只读发现'},
  houdini_ui_screenshot: {label:'观察界面',purpose:'截图明确的当前可见界面；目标须完整在屏内且无遮挡。',input:'target为houdini_ui_list发现所得引用；可选path/output_policy。不打开或调整界面，不传Python代码。',output:'真实PNG附件、准确目标区域、实际尺寸与状态保持事实；识图与捕获分别判断。',execution:'Bridge主线程队列分阶段观察/捕获，不改导航或窗口状态'},
  houdini_job_submit: {label:'提交长任务',purpose:'把渲染、模拟或长计算放入Houdini队列并立即返回。',input:'Python代码；与exec相同的操作能力。',output:'jobId及提交回执。',execution:'Houdini串行队列'},
  houdini_job_status: {label:'等待长任务',purpose:'读取或等待长任务状态和结果。',input:'jobId及可选wait秒数。',output:'queued/running/done/failed/cancelled及实际结果。',execution:'Bridge任务记录'},
  houdini_job_cancel: {label:'取消长任务',purpose:'取消尚未执行的任务，并对运行中的任务发出取消意图。',input:'jobId。',output:'实际取消状态；运行中的HOM操作不会被强杀。',execution:'Bridge任务控制'},
} as const

export type HoudiniToolName=keyof typeof HOUDINI_TOOLS

/** Host media requests are not Houdini executions or entries in the verb ledger. */
export const IMAGE_TOOLS = {
  image_models:{label:'发现生图模型',purpose:'读取DSH已配置的OpenAI兼容API路由和模型名称，供指定生图模型使用；不调用模型，不证明图片接口可用。',input:'可选provider和模型名称子串query，默认image。',output:'配置中的provider/model及图片接口支持尚未验证的说明；不返回凭据。',execution:'DSH Host，无HOM'},
  image_generate:{label:'生成参考或纹理图',purpose:'使用指定provider/model生成或编辑一张图片，实际上传参考像素；默认按当前HIP目录和用途分配文件，显式目的地支持离线工作。',input:'provider、model、prompt；purpose=reference/texture，output_policy=managed/explicit；可选output、references、size、quality、background。',output:'实际路径、工程锚点和目录角色、来源指纹、原图恢复/预览附件及请求事实；不自动重试或更换模型。',execution:'DSH Host HTTP与文件；managed只读查询所选Houdini现场'},
} as const

export const VIDEO_TOOLS = {
  video_process:{label:'处理教程资料',purpose:'在Host受控进程中导入/抽帧和查询/整理本地教程证据，复用原脚本的来源校验及唯一文件记录。',input:'operation与options；只接受随包离线命令，路径绝对，写入使用工作区内新output目录。',output:'原命令JSON、进度、实际退出状态、选定Houdini的Python/私有媒体工具与输出路径；不认证语义。',execution:'DSH Host普通Python子进程，无shell/密钥/云请求/HOM'},
  video_models:{label:'发现转录配置',purpose:'读取教程视频的转录用途配置、DSH服务商和凭据状态；不上传音频，不证明转录接口可用。',input:'可选provider和模型名称子串query。',output:'默认用途、API路由、模型建议和缺失配置诊断；不返回凭据。',execution:'DSH Host，无HOM'},
  video_transcribe:{label:'转录教程音频',purpose:'用DSH中选定服务商与转录模型并行处理已准备的教程音频，复用原任务的分片和请求记录。',input:'work、allow_upload；可选provider/model、chunks、max_chunks、concurrency、requests_per_second、术语词表、说话人分离及明确授权的重试预算。',output:'逐片进度、实际在途峰值与成功/失败、剩余/未知请求、原任务目录及准确模型；原始响应和时间戳在同源outcome中，密钥只交给受控子进程。',execution:'DSH Host Python子进程与HTTP，无HOM'},
} as const

export const PLUGIN_TOOLS = {...HOUDINI_TOOLS,...IMAGE_TOOLS,...VIDEO_TOOLS} as const
