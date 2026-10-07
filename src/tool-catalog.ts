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
