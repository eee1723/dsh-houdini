# Houdini Trace 设计与维护契约

## 唯一展示与诊断边界

DSH 原生「轨迹」和工具结果卡是会话内通用调用详情的唯一入口。插件不再注册另一套执行记录视图，也不把完整 persona、skill、工具 schema 或提示词镜像进客户端。Houdini 只补充自身需要的节点交付和现场状态；通用会话、工具展示、草稿及模式切换由 DSH 负责。

诊断分为两条路径，不建立第二份执行事实：

- 在线：DSH 原生会话、trajectory、jobs 与 `src/execution-facts.ts` 的增量投影提供执行事实；`src/dsh-adapter.ts` 是原生/嵌套回执及 live job 解码唯一源。
- 离线：先运行 [trace 提取 skill](../skills/houdini-trace-analysis/SKILL.md) 的 `extract-trace-evidence.mjs`，再运行 [trace-report](../tools/trace-report.mjs)。它们读取原生 Session 日志，用于分析工具选择、重复工作、失败、视觉证据和完成差距，不进入 Agent 的生产提示词。

`tools/out` 中的报告、截图和试验材料是过程证据，不是另一套生产数据通道。构建成功、UI 注册或本地 HTML 均不证明 live 已加载。

## 原生轨迹与节点交付

通用工具调用使用 DSH 的 `presentCall`、`presentResult`、`presentationMeta` 和原生视图。参数、执行证据、错误及完整原值按原生折叠和详情限额展示；模型可见文本、canonical 回执和展示投影分别处理，不能为了展示重新执行 Python 或重新解释领域结论。

live job的模型结果复用普通执行渲染器的字段与优先级，在生产者声明的16 KB内保留开头的错误、请求和检查上下文，以及末尾的恢复提示和详情入口；中间省略处明确标注，完整值仍在原生canonical与原归档中。原生`job_output`最终裁剪保留尾部，因此不能先输出任意大的操作清单再依赖宿主裁剪来保住首部错误。插件在既有`tools/post-execute`扩展内适配自身回执，不改原生finalizer、其他job类型、会话或共享配置，也不另维护一套领域字段筛选器；消费方回归见[真实jobs组合](../tools/tests/dsh-job-completion-fixture.mjs)。宿主如提供保留领域优先字段的公开投影合同并验证等价，可替换此窄摘要实现。

Houdini 特有节点卡由 [client/node-delivery.js](../client/node-delivery.js) 提供：

- 只读取成功 `present_nodes` 动词的真实回执，不依赖 `__result__` 包装、节点名称或自报路径。
- 使用 DSH 公开 Conversation 与回复尾部插槽；原生和 PTC 子调用消费同一 canonical 解码。普通 `job_output` 只沿 `liveJobResult` 恢复原执行，不伪造新的 Houdini 操作。
- 节点持久标识、原交付 HIP、控制声明和重开/改名行为由 Bridge 执行事实决定。点击经 `src/node-delivery.ts` 按当前 Agent 的原执行绑定查回；浏览器不接收任意 PID、窗口或节点写入权限。
- 不同 HIP、缺失或重复标识、失败导航明确拒绝；旧卡片不会把后续同名节点或另一个现场当作交付目标。

[生成器](../tools/gen-node-delivery-client.mjs) 仅嵌入同源 live-job 解码、节点记录提取和卡片工厂。它不再生成工具目录、提示词来源或独立 Trace 页面。节点卡与文件交付并列，文件本体仍由 DSH `present` 负责。

## 上下文与提示词事实

离线阅读可以关联实际 System、schema、usage、消息、技能和资源读取记录；当前源码、进程实际加载与历史请求内容是三个不同事实。不得用当前文件补写历史正文，也不得以配置中的插件清单证明某段提示词已生效。

| 内容 | 权威来源 / 注册入口 | 必须保留的区别 |
|---|---|---|
| DSH 身份及其他系统段 | Host 最终组装/模型请求 | 开关、作用域遮蔽、顺序、覆盖与最终生效情况 |
| Houdini persona | [persona.md](../presets/houdini/persona.md) 和生成 preset | 手写来源、生成声明与本次实际生效内容 |
| 执行硬边界 | [src/index.ts](../src/index.ts) 的 `dsh-houdini:guidance` | 稳定工具路由和不可补救约束，不复制领域 recipe |
| 现场摘要与恢复 | [src/context.ts](../src/context.ts)、[src/execution-state.ts](../src/execution-state.ts) | 一次消息绑定观察与未决事实；不是现场通过证书或第二份完成账本 |
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
| 节点交付客户端 | [节点记录](../src/node-delivery-record.ts)、[卡片工厂](../client/node-delivery.js)、live-job 解码 → [生成器](../tools/gen-node-delivery-client.mjs) |
| Houdini preset | [persona.md](../presets/houdini/persona.md) → `gen-agent-presets`；保留 DSH 标准能力，不替换其他 preset 或默认选择 |

`npm run build` 生成上述 Host/客户端合同；`npm run docs:check` 验证漂移。加载新构建不等于运行中的 Desktop 或 Houdini 已更新，实际版本按[安装更新](setup.md)和[兼容设计](dsh-update-compatibility.md)核对，不为更新 UI 重启用户 live。

## 离线关联和计数契约

[时序归一](../tools/normalized-trace-steps.mjs)、[会话解析](../tools/trace-session-lib.mjs)与 `execution-facts` 使用公开 Session 事件和 canonical 回执。请求按 turn/step、调用按 callId/jobId 关联；优先使用明确的 resultSeq 和原始回执，不用相邻时间或目录名称猜归属。并发返回不改变调用发起顺序；pending、unknown、结果过期与失败分别保留，不能自动重试或冒充成功。

- 一次模型请求可有多个工具调用，一次调用可执行多个动词，一个动词可创建多个节点，分母不能混用。
- `processOutcome` 区分送达结果与子进程真实退出；stdout 的错误字样不是退出事实，没有退出证据保持 unknown。
- 模型 usage 按请求去重；同请求的多个工具不重复累计输入/输出，缺失用量不补零。缓存及推理字段按提供方定义，不重复相加。
- 原始 provider/model/reasoningEffort/maxTokens、实际 HTTP 字段、模型报告用量和语义效果分别判断；缺少推理档保持未知，不回填为 off。
- `rawUsage` 区分 Gate 拦截、只读候选、疑似/未知副作用和成功裸修改；`no_scene_change` 不排除文件或 Python 外部副作用。`exec` 含动词率不是修改意图覆盖率。
- 历史结果、图片和关系检查不扩大语义范围。新图只替代已知同视图记录；图像传输、像素变化、模型自述和最终视觉通过分别保留，未成功语义识图就是未验证。
- 重试分析只比较去重后的失败调用和回滚工作量；正常重复生成不算失败重试，字符数不冒充 token 或费用。
- 原生工具失败、动词异常、验证 failed/warning/unverified 分开统计。后续修复不改写历史，后续成功也不抹掉前序失败。

具体证据判据由 [trace 分析 skill](../skills/houdini-trace-analysis/SKILL.md) 和 [证据回归](../tools/tests/trace-evidence-helpers.test.mjs)维护；不要在 UI 或报告中另写一套规则猜测成功。

## 验证入口

- [节点交付客户端回归](../tools/tests/node-delivery-client.test.mjs)：原生/PTC 回执、历史重放、选中任务和失败导航。
- [真实页面导航](../tools/tests/dsh-client-navigation.mjs)：原生轨迹往返、草稿保持、现场选择及其他模式不受额外界面影响。
- [时序测试](../tools/tests/normalized-trace-steps.test.mjs)、[会话解析测试](../tools/tests/trace-session-lib.test.mjs)、[请求审计](../tools/tests/trace-request-telemetry.test.mjs)：关联、去重、usage 和未知状态。
- [副作用分类](../tools/tests/trace-raw-effects.test.mjs)、[进程结果](../tools/tests/trace-process-outcome.test.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)：执行范围与诊断口径。
- `npm run docs:check`：文档索引、模块覆盖、生成合同和链接；`npm test` 中的动词合同检查 Host/Bridge 名称与执行版本一致。

实现或合同变更时就地更新本页，不追加阶段计划、会话流水或单次结果。
