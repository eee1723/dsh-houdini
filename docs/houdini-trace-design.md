# Houdini Trace 设计与维护契约

## 唯一展示与诊断边界

DSH 原生「轨迹」和工具结果卡是会话内通用调用详情的唯一入口。插件不再注册另一套执行记录视图，也不把完整 persona、skill、工具 schema 或提示词镜像进客户端。Houdini 只补充自身需要的节点交付和现场状态；通用会话、工具展示、草稿及模式切换由 DSH 负责。

诊断分为两条路径，不建立第二份执行事实：

- 在线：DSH原生会话、trajectory、jobs与`src/execution-facts.ts`的增量投影提供执行事实；`src/dsh-adapter.ts`统一解码原生/嵌套工具结果、生产者Bridge终态事实及历史live job回执。
- 离线：先运行 [trace 提取 skill](../skills/houdini-trace-analysis/SKILL.md) 的 `extract-trace-evidence.mjs`，再运行 [trace-report](../tools/trace-report.mjs)。它们读取原生 Session 日志，用于分析工具选择、重复工作、失败、视觉证据和完成差距，不进入 Agent 的生产提示词。

`tools/out` 中的报告、截图和试验材料是过程证据，不是另一套生产数据通道。构建成功、UI 注册或本地 HTML 均不证明 live 已加载。

## 原生轨迹与节点交付

通用工具调用使用DSH的`presentCall`、`presentResult`、`presentationMeta`和原生视图。执行回执的持久canonical与文字正文各受64KiB预算约束，独立run多执行聚合也有同一总预算；超限展示既有作业摘要中的定位、结论、状态和检查数，并保留原run读取入口，原生图片独立按附件合同传递。原生/PTC当前结构返回保持完整，浏览器不复制整份动词和作者结果。完整JSON优先进入工作区长期hash归档；只读、归档失败或超预算时使用DSH原生opaque spill，后端拥有读取方式与保留期限；两者均失败明确durable unavailable，不回填全文，也不把成功执行改成失败。

Bridge终态由生产者经`appendPluginRecord`写入同一Session的`plugin:dsh-houdini/execution`可忽略事实，保存原sourceCallId/rootCallId及轻量canonical；事实没有模型可见surface，不是另一次工具调用。投影、Trace与节点卡不依赖job_output被读取才看见完成；generic jobs始终保留原生定义、通知、取消和卸载生命周期，插件不再复制每个Agent的job_output定义。该事件不能仅依据DSH job/settled生成，缺少execution的排队取消也不补造HOM执行。

live job的模型摘要复用普通执行渲染器，在生产者声明的16000字节内保留首部错误/请求/检查和尾部恢复/详情入口，中间省略明确标注。原生job_output最终裁剪保留尾部，因此摘要在提交给原生finalizer之前有界；`tools/post-execute`只适配自己的作业摘要，不生成另一份持久canonical，也不改变其他job。消费方验证见[真实jobs组合](../tools/tests/dsh-job-completion-fixture.mjs)。

离线Trace通过`EXECUTION_FACT_PROJECTION`展开可验证的hash归档；历史文件保持原details地址。原生opaque locator只提供其真实读取指导，不按路径解读或假装已应用JSON Pointer。未展开、缺失、篡改与durable unavailable分别保留原因，不从缺少全文推断没有动词、错误或执行。不能为了展示重新执行Python或重新解释领域结论。留存与实际native/PTC消费验证见[结果读取](../tools/tests/result-details.test.mjs)。

Houdini 特有节点卡由 [client/node-delivery.js](../client/node-delivery.js) 提供：

- 只读取成功 `present_nodes` 动词的真实回执，不依赖 `__result__` 包装、节点名称或自报路径。
- 使用DSH公开Conversation与回复尾部插槽；原生/PTC结果及Bridge终态事实消费同一canonical解码，后台交付按rootCallId关联原调用。旧job_output回执只作历史读取，不伪造新的Houdini操作。
- 节点持久标识、原交付 HIP、控制声明和重开/改名行为由 Bridge 执行事实决定。点击经 `src/node-delivery.ts` 按当前 Agent 的原执行绑定查回；浏览器不接收任意 PID、窗口或节点写入权限。
- 不同 HIP、缺失或重复标识、失败导航明确拒绝；旧卡片不会把后续同名节点或另一个现场当作交付目标。

[生成器](../tools/gen-node-delivery-client.mjs)仅嵌入同源Bridge终态/历史live-job解码、节点记录提取和卡片工厂。它不生成工具目录、提示词来源或独立Trace页面。节点卡与文件交付并列，文件本体仍由DSH present负责。

## 上下文与提示词事实

离线阅读可以关联实际 System、schema、usage、消息、技能和资源读取记录；当前源码、进程实际加载与历史请求内容是三个不同事实。不得用当前文件补写历史正文，也不得以配置中的插件清单证明某段提示词已生效。

| 内容 | 权威来源 / 注册入口 | 必须保留的区别 |
|---|---|---|
| DSH 身份及其他系统段 | Host 最终组装/模型请求 | 开关、作用域遮蔽、顺序、覆盖与最终生效情况 |
| Houdini persona | [persona.md](../presets/houdini/persona.md) 和生成 preset | 手写来源、生成声明与本次实际生效内容 |
| 执行硬边界 | [src/index.ts](../src/index.ts) 的 `dsh-houdini:guidance` | 稳定工具路由和不可补救约束，不复制领域 recipe |
| 现场摘要与恢复 | [src/context.ts](../src/context.ts)、[src/execution-state.ts](../src/execution-state.ts) | 一次消息绑定观察与未决事实；本步toolSet/modelSelection与仅注册工具、旧模型配置分开，不是现场通过证书 |
| 原始任务来源 | [src/task-sources.ts](../src/task-sources.ts)、`houdini_resource` | 按需原文与已消费状态；不向每次请求自动追加副本 |
| 工具、技能与参考正文 | 最终 schema/messages、读取和压缩记录 | 已注册、已返回、仍保留、已压缩与未采集分别表达 |
| 当前动词与节点交付合同 | [工具设计](tool-design.md)、[节点记录](../src/node-delivery-record.ts) | 当前维护源不能替代历史请求中的版本 |

没有最终 messages 可见集合时明确未采集。看到符合规则的动作不证明某 skill 促成，也不证明全部规则已遵守；资源文件存在不等于进入上下文，正文读取不等于视觉理解或任务验收。

## 构建与版本同步

| 内容 | 唯一维护源与派生入口 |
|---|---|
| 动词名称、目录摘要和执行版本 | [工具设计](tool-design.md) → [gen-verb-contract](../tools/gen-verb-contract.mjs) → `src/generated-verb-contract.ts` |
| 动词完整结构与例子 | `houdini/verb-operation-contracts.json` → `gen-verb-contract-docs` → [verb-contracts](verb-contracts.md)；运行时由 `verb_help` 读取 |
| 节点操作知识 | `houdini/node-operation-contracts.json` → `gen-node-card-docs` → [节点操作卡](node-operation-cards.md) |
| 节点交付客户端 | [节点记录](../src/node-delivery-record.ts)、[卡片工厂](../client/node-delivery.js)、Bridge终态/历史live-job解码 → [生成器](../tools/gen-node-delivery-client.mjs) |
| Houdini preset | [persona.md](../presets/houdini/persona.md) → `gen-agent-presets`；保留 DSH 标准能力，不替换其他 preset 或默认选择 |

`npm run build` 生成上述 Host/客户端合同；`npm run docs:check` 验证漂移。加载新构建不等于运行中的 Desktop 或 Houdini 已更新，实际版本按[安装更新](setup.md)和[兼容设计](dsh-update-compatibility.md)核对，不为更新 UI 重启用户 live。

## 离线关联和计数契约

[时序归一](../tools/normalized-trace-steps.mjs)、[会话解析](../tools/trace-session-lib.mjs)与execution-facts使用公开Session事件和canonical事实。请求按turn/step、工具按callId关联；后台终态通过生产者sourceCallId/rootCallId连到原提交，并保留真实终态事件坐标，不新增模型调用或把一次执行计两次。优先使用明确的resultSeq与原回执，不用相邻时间或目录猜归属。并发返回不改变发起顺序；pending、unknown、结果过期与失败分别保留，不能自动重试或冒充成功。

- 一次模型请求可有多个工具调用，一次调用可执行多个动词，一个动词可创建多个节点，分母不能混用。
- `processOutcome` 区分送达结果与子进程真实退出；stdout 的错误字样不是退出事实，没有退出证据保持 unknown。
- 模型 usage 按请求去重；同请求的多个工具不重复累计输入/输出，缺失用量不补零。缓存及推理字段按提供方定义，不重复相加。
- 原始 provider/model/reasoningEffort/maxTokens、实际 HTTP 字段、模型报告用量和语义效果分别判断；缺少推理档保持未知，不回填为 off。
- `rawUsage` 区分 Gate 拦截、只读候选、疑似/未知副作用和成功裸修改；`no_scene_change` 不排除文件或 Python 外部副作用。`exec` 含动词率不是修改意图覆盖率。
- 工具种类消费`src/tool-catalog.ts`；现场job提交是准入回执，不是已完成Python执行。`houdini_isolated`的提交与报告读取分别计数，不进入现场Python的动词采用率或无动词副作用统计。没有顶层verb ledger不证明builder没有使用动词；实际执行看原run的builder/check回执，不把再次read当作重新执行。
- 历史结果、图片和关系检查不扩大语义范围。新图只替代已知同视图记录；图像传输、像素变化、模型自述和最终视觉通过分别保留，未成功语义识图就是未验证。
- 重试分析只比较去重后的失败调用和回滚工作量；正常重复生成不算失败重试，字符数不冒充 token 或费用。
- 原生工具失败、动词异常、验证 failed/warning/unverified 分开统计。后续修复不改写历史，后续成功也不抹掉前序失败。

执行槽位由DSH适配器`returnedExecutions`识别；详情索引和离线归一使用同源地址，独立报告中的执行不投影为当前live状态。

具体证据判据由 [trace 分析 skill](../skills/houdini-trace-analysis/SKILL.md) 和 [证据回归](../tools/tests/trace-evidence-helpers.test.mjs)维护；不要在 UI 或报告中另写一套规则猜测成功。

## 验证入口

- [节点交付客户端回归](../tools/tests/node-delivery-client.test.mjs)：原生/PTC 回执、历史重放、选中任务和失败导航。
- [真实页面导航](../tools/tests/dsh-client-navigation.mjs)：原生轨迹往返、草稿保持、现场选择及其他模式不受额外界面影响。
- [时序测试](../tools/tests/normalized-trace-steps.test.mjs)、[会话解析测试](../tools/tests/trace-session-lib.test.mjs)、[请求审计](../tools/tests/trace-request-telemetry.test.mjs)：关联、去重、usage 和未知状态。
- [副作用分类](../tools/tests/trace-raw-effects.test.mjs)、[进程结果](../tools/tests/trace-process-outcome.test.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)：执行范围与诊断口径。
- `npm run docs:check`：文档索引、模块覆盖、生成合同和链接；`npm test` 中的动词合同检查 Host/Bridge 名称与执行版本一致。

实现或合同变更时就地更新本页，不追加阶段计划、会话流水或单次结果。
