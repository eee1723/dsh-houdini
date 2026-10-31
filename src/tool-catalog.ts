/** Public purpose of each tool; registration, UI and docs consume this catalog. */
export const HOUDINI_TOOLS = {
  houdini_inspect: {kind:'python',scene:true,label:'观察工程',purpose:'读取真实Houdini场景、节点、参数和能力资料。',input:'只读Python代码；hou与动词已导入。',output:'读取结果、诊断及本次观察的场景身份。',execution:'Houdini主线程，只读'},
  houdini_exec: {kind:'python',scene:true,label:'执行操作',purpose:'批量创建、修改、检查、保存或出图。',input:'Python代码或绝对UTF-8 .py脚本；script可带expected_sha256及code调用尾段，不使用exec(open(...))加载；__result__返回结构数据。',output:'结果、真实错误、操作记录、事务状态、脚本版本、图像和文件。',execution:'Houdini主线程，串行'},
  houdini_request: {kind:'receipt',scene:true,label:'查回执行',purpose:'回答某个未知响应的请求是否执行、是否完成；避免重复修改。',input:'原请求的request_ref；index仅列当前所选运行实例中本会话的回执。',output:'原执行状态与可取得的原始结果；不会重发代码。',execution:'Bridge请求记录，无HOM'},
  houdini_resource: {kind:'host',scene:false,label:'读取资料',purpose:'按需读取原始用户资料、完整历史工具结果及已归档加载警告。',input:'kind=source/result、ref及可选分页；result可选JSON Pointer。',output:'原文或JSON分页及继续读取位置。',execution:'DSH Host，无HOM'},
  houdini_capabilities: {kind:'host',scene:false,label:'观察通道',purpose:'确认当前模型能否接收图片，以及附件通道是否可用。',input:'无需参数。',output:'当前模型与附件能力事实；不会渲染或判断画面。',execution:'DSH Host，无HOM'},
  houdini_isolated: {kind:'isolated',scene:false,label:'独立Houdini执行',purpose:'按需在新hython中执行构建脚本、已保存工程副本及加载后的准备操作，取得真实检查、错误和图片，供当前作者或团队成员自验证。',input:'operation=run/read、manifest；run可选全新output_dir，默认在当前DSH工作区execution_run角色内分配唯一目录；read传原run路径。使用已选工程登记的安装信息，离线仍可运行；可选houdini_installation显式指定HFS。manifest支持hip+script与input_root；可选background、timeout_seconds、memory_mb。',output:'独立运行报告、输入版本、构建结果、检查和原生图片；大型原始回执单份保留并返回details；后台使用DSH job_output/job_kill。',execution:'Host监管的一次性独立hython，不修改当前工程、不自动合并'},
  houdini_ui_list: {kind:'ui',scene:true,label:'发现界面',purpose:'列出当前Houdini中可见的原生pane及Qt窗口/面板，提供明确截图目标和实际支持状态。',input:'无需参数；不打开或切换界面。',output:'当前runtime目标引用、类型、用途线索、实际区域及支持/未支持原因。',execution:'Bridge主线程队列，只读发现'},
  houdini_ui_screenshot: {kind:'ui',scene:true,label:'观察界面',purpose:'截图明确的当前可见界面；目标须完整在屏内且无遮挡。',input:'target为houdini_ui_list发现所得引用；可选path/output_policy。不打开或调整界面，不传Python代码。',output:'真实PNG附件、准确目标区域、实际尺寸与状态保持事实；识图与捕获分别判断。',execution:'Bridge主线程队列分阶段观察/捕获，不改导航或窗口状态'},
  houdini_job_submit: {kind:'submission',scene:true,label:'提交长任务',purpose:'把渲染、模拟或长计算放入Houdini串行队列，由DSH原生jobs跟踪、通知和收集。',input:'Python代码或script、expected_sha256及可选code调用尾段；与exec相同的操作能力。',output:'DSH job_id用于job_output/job_kill，Bridge jobId和原request_ref用于真实结果及恢复；houdini_request查回原结果和图片。',execution:'DSH jobs观察；Houdini主线程串行执行'},
} as const

export type HoudiniToolName=keyof typeof HOUDINI_TOOLS
export type HoudiniToolKind=(typeof HOUDINI_TOOLS)[HoudiniToolName]['kind']
/** Historical names are decoding contracts, never tool registrations. */
export function houdiniToolKind(name:unknown):HoudiniToolKind|undefined {
  if(typeof name!=='string')return
  if(Object.hasOwn(HOUDINI_TOOLS,name))return HOUDINI_TOOLS[name as HoudiniToolName].kind
  return ({houdini_query:'python',houdini_product:'host',houdini_job_status:'receipt',houdini_job_cancel:'host'} as Record<string,HoudiniToolKind>)[name]
}


/** Known Bridge tools share scene identity facts; Host metadata never binds a scene. */
export const HOUDINI_SCENE_TOOLS:ReadonlySet<string>=new Set(
  Object.entries(HOUDINI_TOOLS).filter(([,tool])=>tool.scene).map(([name])=>name),
)

/** Host media requests are not Houdini executions or entries in the verb ledger. */
export const IMAGE_TOOLS = {
  image_models:{label:'发现生图模型',purpose:'读取DSH已配置的OpenAI兼容API路由和模型名称，供指定生图模型使用；不调用模型，不证明图片接口可用。',input:'可选provider和模型名称子串query，默认image。',output:'配置中的provider/model及图片接口支持尚未验证的说明；不返回凭据。',execution:'DSH Host，无HOM'},
  image_generate:{label:'生成参考或纹理图',purpose:'使用指定provider/model生成或编辑一张图片，实际上传参考像素；默认按当前HIP目录和用途分配文件，显式目的地支持离线工作。',input:'provider、model、prompt；purpose=reference/texture，output_policy=managed/explicit；可选output、references、size、quality、background。',output:'实际路径、工程锚点和目录角色、来源指纹、原图恢复/预览附件及请求事实；不自动重试或更换模型。',execution:'DSH Host HTTP与文件；managed只读查询所选Houdini工程'},
} as const

export const VIDEO_TOOLS = {
  video_process:{label:'处理教程资料',purpose:'在Host受控进程中导入/抽帧和查询/整理本地教程证据，复用原脚本的来源校验及唯一文件记录。',input:'operation与options；只接受随包离线命令，路径绝对，写入使用工作区内新output目录。',output:'原命令JSON、进度、实际退出状态、选定Houdini的Python/私有媒体工具与输出路径；不认证语义。',execution:'DSH Host普通Python子进程，无shell/密钥/云请求/HOM'},
  video_models:{label:'检查教程配置',purpose:'检查教程专用转录协议、准确模型、DSH凭据状态和本机依赖；不以聊天模型目录证明语音能力。',input:'可选provider/名称过滤。',output:'非秘密配置、缺项、能力边界与真实运行路径；不上传音频或返回密钥。',execution:'DSH Host，无HOM'},
  video_configure:{label:'配置教程服务',purpose:'按用户选择保存教程专用非秘密设置，复用DSH原生设置与凭据；不改聊天模型或接收密钥。',input:'明确的文件协议、已有服务商或完整端点、模型ID；可选认证/并发/速率。',output:'实际生效配置、缺项和安全录入密钥的下一步；旧任务仍绑定原服务。',execution:'DSH Host，仅本插件设置，无HOM'},
  video_transcribe:{label:'转录教程音频',purpose:'用DSH中选定服务商与转录模型并行处理已准备的教程音频，复用原任务的分片和请求记录。',input:'work、allow_upload；可选provider/model、chunks、max_chunks、concurrency、requests_per_second、术语词表、说话人分离及明确授权的重试预算。',output:'逐片进度、实际在途峰值与成功/失败、剩余/未知请求、原任务目录及准确模型；原始响应和时间戳在同源outcome中，密钥只交给受控子进程。',execution:'DSH Host Python子进程与HTTP，无HOM'},
} as const

export const PLUGIN_TOOLS = {...HOUDINI_TOOLS,...IMAGE_TOOLS,...VIDEO_TOOLS} as const
