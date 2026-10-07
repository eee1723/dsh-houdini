# Houdini 工具说明

本页由[src/tool-catalog.ts](../src/tool-catalog.ts)生成，代码注册与Trace工具说明共用这一份职责目录。参数及执行以[src/tools.ts](../src/tools.ts)为准。

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

观察现场和读取历史分开，是因为前者读取当前Houdini，后者可以在Houdini离线时使用。查回执行分开，是因为响应丢失后应取回原结果。长任务的提交、等待和取消分开表达各自真实状态。

保存、渲染、节点发现与几何检查属于可组合的Python能力，详见[动词目录](tool-design.md)。领域工作方法在[skills](../skills/)维护；任务计划使用DSH已有能力。

验证入口：[工具注册与展示](../tools/tests/houdini-tool-presentation.test.mjs)、[请求查回](../tools/tests/request-recovery.test.mjs)、[历史结果](../tools/tests/result-details.test.mjs)。
