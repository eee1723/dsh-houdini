# dsh-houdini 跨域能力评测计划

> 状态：2026-09-02 路线与反过拟合硬约束已拍板；M1 完整冷启动/live query/Trace 基线已封口，
> B0 schema、交叉 hash、smoke 产物门禁、通用 seed generator 与三族 calibration seed 输入已实现；
> 执行模型已选 K3/GLM 并通过当前 provider 的同图原生视觉探针；DashScope qwen-vl-max 的独立
> blind/target prompt 与两阶段 smoke 已冻结/通过。三族 calibration/counterexample 与独立 holdout hash
> 已封存。首个 mechanical smoke 暴露 workspace/seed-copy P0 后，三族隔离 smoke 均已通过；Lookdev
> evaluator 又暴露 ID namespace/hard-failure 语义缺口。Final protocol 已升为 `b0-2026-09-02-v4`，
> V2 normalizer 的引用完整性与确定性 hard-failure 回放通过。正式 3×2 已全部完成（6/6 coreSuccess、
> 0 hard failure、0 泄漏），B2 跨 run 归因与 B3 候选门槛状态见 §10；holdout 仍未解封。

2026-09-01 已加入 evaluator-spec/sealed-instance 通用 schema 与 seal 工具，三族 calibration 和
counterexample bundle 均在 Git 忽略目录完成交叉 hash 封存；tracked freeze status 只记录六个 bundle hash，
三个 holdout 槽保持 `null` 且 `finalProtocolGenerated=false`。独立 holdout authoring request 只允许未参与
当前实现的设计者返回三个 sealed hash，正文在 production freeze 前不得进入本线程或执行 workspace。

独立设计任务现已返回三个互异 holdout hash；当前线程未读取/枚举其正文目录，只将 hash 填入
`protocol-manifest.json`。Final protocol canonical SHA-256 为 `a39d7c0e…`，文件 SHA-256 为
`3fd34d49…`；`protocol-freeze-status.json` 已变为 `ready-for-smoke`，三个 family 的 calibration/holdout/
counterexample 均为非空 hash，`finalProtocolGenerated=true`。Holdout 正文继续保持未见，正式 3×2 前只运行
calibration 的非评分基础设施 smoke，不解封 holdout。

Mechanical smoke attempt 1 实际构建、保存和渲染成功，但消息被发送到 `E:/dsh-houdini` workspace，而
HIP workspace 对应的 session 为空；repo workspace 中 evaluator-only calibration 文件理论可访问，因此该
run 必须 `invalidated`，不能因 agent 未实际读取就降级污染事实。另因直接打开 sealed seed，`scene_save` 不能
Save As，agent 只能 `saveAsBackup + shell copy`。V2 协议现强制 `isolated-run-directory`，将 seed 精确字节
复制为当前 `work.hip`，execution workspace 只允许 `agent-message.txt` 和 `work.hip`，evaluator material
不可访问。污染 run 只有在 status=`invalidated` 时才允许记录 `evaluatorMaterialExposed=true`。

Mechanical attempt 2 使用隔离 workspace、`work.hip` 和正式 workspace/session API，execution cwd、preset、
model 在 prompt 前核验；`validate-run`/`validate-inputs`/`validate-smoke`、H21 独立 HIP 回读、整体/特写 PNG、
trace 和 final node 均通过。Qwen-VL Blind 连续返回语义正确但带单层 `json` code fence 的响应，另一次回显中性
`viewLabel`；V3 加入 `evaluator-json-normalizer-v1`，只接受 raw JSON 或无外部文本的单层 JSON fence，
剥壳后仍严格校验 stage/字段/状态，未知字段继续拒绝。整体 Target 为 pass，关节特写 Target 为 unverified；
该分歧保留但不阻塞非评分基础设施 smoke。

Simulation/Lookdev smoke 通过后，Lookdev Target 暴露两类 shape schema 无法发现的语义错误：图片 ID 与
deterministic ID namespace 交叉，以及把未触发的 critical 条件写进 `hardFailures`。V4 使用
`target-verification-v6` + `evaluator-json-normalizer-v2`：模型只输出 criteria/overall；normalizer 要求
预期 criterion 集合完全相等、引用存在且 namespace 不交叉，并根据冻结 critical rules 与 `status=fail`
确定性生成 hardFailures。相同 Lookdev 输入最终回放为 9 criterion、core/visual pass、0 hard failure；此前
5 个语义不合规 Target 响应全部 fail-closed，不进入评分。
> 本文是下一阶段 benchmark、评分协议与准入决策的唯一维护位置。README 只保留路线摘要，
> `development.md` 只记录执行状态，`tool-design.md` 只记录经评测进入的工具决策。

## 1. 决策与目标

下一阶段选择“能力证据优先”：先证明 agent 在机械程序化资产、真实 solver/cache 模拟和
Solaris/Karma lookdev 三类任务中的实际成功率与自我纠错能力能否提升，再决定结构化任务合同、
agent-native 检查动词和新领域 skill 的正式形态。

本阶段不是放弃诚实完成门。现有自然语言合同、`pass/fail/unverified`、trace evidence 和人工审计
继续保留，但不先把它们扩成生产级 Host 状态机，也不以合同字段完整率作为主优化目标。

要回答四个问题：

1. agent 能否在没有用户追加纠错时自行发现并修复关键缺陷；
2. 哪些质量失败跨模型、跨任务重复，属于系统缺口而非单次模型波动；
3. 独立视觉评审与客观几何/字段/时序证据组合后，能否可靠反驳执行 agent 的自证；
4. 哪些重复 probe 应进入通用动词，哪些抽象知识只应进入领域 skill，哪些内容必须永远留在
   evaluator-only 的实例与评分材料中。

## 2. 泛化与实验不变量

### 2.1 执行信息防火墙

具体任务可以用于评测，但不得反向变成该任务的常驻答案。每次评分运行都必须满足：

- 执行 agent 只接收一份正常用户会给出的任务 brief，以及该领域原本就可按需加载的通用 skill；
- 生产 `GUIDANCE`、preset、skills、verb/tool 名称、错误提示和默认参数在所有实例之间保持相同，
  不出现 benchmark ID、实例对象名、目标数值、评分 rubric、固定节点网络或修题提示；
- evaluator-only 合同、硬失败线、参考图、隐藏诊断维度和预期答案不进入执行会话上下文，也不放入
  执行 agent 可访问的 `$HIP` workspace；
- 用户 brief 和 evaluator spec 分别计算 hash 并记入 manifest，不能用 evaluator spec 冒充用户提示；
- 执行中只回答预注册的真实歧义，不回答“应该用什么节点”“检查哪里”“如何达到评分线”；
- smoke 或失败复盘产生的对象专用做法不能写回 production surface；候选改进必须先抽象成数据模型、
  状态转换、检查意图或完成门。

仓库测试会扫描 `AGENTS.md`、`client.js`、`src/`、`presets/` 和 `skills/` 等 agent-visible
surfaces，拒绝已登记的 benchmark 标识或唯一对象短语。该扫描是最低门槛，不替代人工 diff 审查：
换个说法写入同一答案仍然算泄漏。

B0 的通用管理资产位于仓库顶层 `benchmark/`，但该目录不进入 npm `files`：只跟踪 baseline、JSON
Schema 和无题目内容的协议工具。具体题面、evaluator spec 与逐 run manifest 分别放在被 Git 忽略的
`benchmark/sealed/`、`benchmark/runs/` 或独立评测存储中。`tools/benchmark-manifest.mjs` 计算规范化
agent-surface hash、sealed file hash、关键 manifest 不变量，并验证 completed smoke 的真实产物没有逃出
`$HIP`、trace 没有落进插件仓库；它不生成任务内容。

### 2.2 实例分层

每个能力族至少分三类实例：

1. **校准/发现实例**：用于建立基线、定位失败和提出候选改进；
2. **未见留出实例**：在生产改进冻结后才解封，不能参与 prompt、skill、工具或参数设计；
3. **跨域反例**：不应触发该候选规则，用于发现过宽 dispatch、固定 recipe 和不必要问卷。

具体校准/发现实例也不在本仓库公开题面；它们与未见留出实例都由 evaluator 侧保管。本仓库只记录
sealed manifest hash、能力标签、普通 brief schema 和解封规则，运行结束后再归档脱敏证据。任何人在
留出实例解封前参与查看其正文，都不能再作为该轮改进的执行者或设计者。

### 2.3 可重复运行约束

每次主矩阵运行必须同时满足：

- 使用全新 Houdini 场景、全新 DSH session 和相同版本的插件、DSH、Houdini、视觉 toolkit/provider；
- 同一实例使用完全相同的普通用户 brief、seed scene/fixture、预设用户回答、帧范围、预算和终止条件；
- 只回答预注册的澄清问题，不提供“检查这里”“再修一下”等追加纠错；
- Houdini 产物、cache 和 render 仍写入 `$HIP`；仓库只保存任务定义、评测代码和脱敏结果摘要；
- 原始 trace、图片、HIP/cache 路径与版本写入 run manifest，不把运行产物复制进插件仓库；
- transport、runtime bootstrap、Artifact presentation、semantic inspection 分开记账；
- 执行 agent 的最终陈述不作为 ground truth；评分只读取可重放证据和独立评审；
- 任一用户 brief、fixture、模型、provider 或评分规则改变都生成新 protocol version，不混入旧批次；
- 每轮改进前冻结 production-surface commit/hash；发现矩阵中途不得按某项任务结果改写 agent surface。

先登记再运行。不得看到结果后修改核心通过线并仍称为同一批 A/B。

## 3. 能力族与实例合同边界

第一轮只预注册三个能力族，不在插件仓库登记具体对象题面：

### CAP-MECH：程序化机械资产

衡量可编辑结构、共享关系、尺度/轴线/间隙、参数扰动后的约束保持，以及数值证据与局部视觉证据能否
共同支持交付。实例必须要求真实的结构依赖，不能只靠外形拼装；但具体对象、部件数、尺寸、控制参数和
参考资料由 evaluator 侧 sealed manifest 决定。

### CAP-SIM：真实 solver/cache 模拟

衡量 solver 路线、source/field 驱动、时间演化、cache 新鲜度、参数失效与重算，以及正交诊断能否反驳
单帧 hero 图。实例必须排除静态几何或预烘焙结果冒充模拟；但具体效应、形态、帧位、字段和目标参数不在
生产仓库或 agent context 中公开。

### CAP-LOOK：Solaris/Karma lookdev

衡量固定 seed geometry 上的 USD stage、材质绑定、灯光、相机、RenderSettings、正式渲染和独立审美
核验，避免把建模差异混入 lookdev。具体产品、风格、参考图、构图阈值和材质答案只存在 evaluator 侧。

每个能力族的 evaluator 合同可以有更具体的核心交付和硬失败，但执行时只能向 agent 发送自然用户 brief。
评审细节不得转写成系统提示、隐藏 checklist、错误建议或工具默认值。后续能力提升必须由未见留出实例
证明，不能因为发现实例原题分数上升就宣称通用 agent 变强。

## 4. 发现矩阵与运行顺序

第一批校准/发现矩阵为 6 次独立运行：

| 能力族校准实例 | 模型 A | 模型 B |
|---|---:|---:|
| CAP-MECH | 1 次 | 1 次 |
| CAP-SIM | 1 次 | 1 次 |
| CAP-LOOK | 1 次 | 1 次 |

模型在批次开始前固定；不得根据首个结果换掉较弱模型。若某个结论只来自单次随机波动，对该实例做
同模型重复，而不是改 prompt。执行顺序在两模型之间交错，避免 Houdini/runtime 状态和人工评审疲劳
总是偏向同一模型。该矩阵用于发现和归因，不单独承担“通用能力提升”的证明。

V4 的六次顺序已冻结在 `benchmark/formal-matrix.json`：Mechanical/K3 → Simulation/GLM →
Lookdev/K3 → Mechanical/GLM → Simulation/K3 → Lookdev/GLM。阶段为 `discovery`、实例角色为
`calibration`、追加纠错上限为 0，且 `holdoutReleased=false`；正式矩阵不会提前解封 B4 holdout。

每次 run manifest 至少记录：protocol/task/run id、Git commit、Houdini/DSH/toolkit/provider/model
版本、production-surface hash、seed scene hash、用户 brief hash、独立 evaluator spec hash、向 agent
实际暴露的资源清单、预设回答、开始/结束时间、终止原因、trace 路径、HIP/cache/render 路径、
最终输出节点、所有 evaluator 版本与原始结论。留出实例在解封前只记录 sealed hash，不记录正文。

## 5. 独立评审协议

每次运行使用三层评审，顺序不可颠倒：

1. **确定性检查**：cook/warning、拓扑、参数依赖、关系数值、字段/帧差、cache 指纹、USD stage/
   binding、render 文件与像素边界；
2. **盲语义描述**：独立视觉模型只看匿名图片和“描述实际可见形态、缺陷与不确定项”，不提供任务名、
   目标词、执行过程或 agent 自评；
3. **目标核验**：第二轮才提供用户目标、参考和验收维度，逐项输出 `pass/fail/unverified`、置信度和
   可反驳理由。

同一执行 agent 不得充当独立评委。独立视觉模型和人工结论冲突时保留分歧，不用语言置信度覆盖；
先增加正交视图、隔离层、切片/profile 等诊断证据。仍无法裁定的审美项标记为人工判断边界。

## 6. 评分与主要指标

每个任务总分 100，但硬失败优先于加权总分：

| 维度 | 权重 | 说明 |
|---|---:|---|
| 实际核心交付 | 40 | 结构/solver/cache/USD-Karma 路线与用户核心结果是否成立 |
| 客观证据与可复现性 | 25 | 数值关系、时序、cache、stage、warning、扰动恢复和证据新鲜度 |
| 独立视觉结果 | 25 | 盲描述与目标核验是否支持可见形态、构图和参考一致性 |
| 诚实交付 | 10 | 是否把 fail/unverified 正确降级，是否引用最终新鲜证据 |

批次主指标不是平均合同完整率，而是：

- **Core success rate**：无硬失败且总分 ≥ 75 的运行比例；
- **Self-detected defect rate**：最终交付前由 agent 自己发现的关键缺陷数 / 独立评审确认的关键缺陷数；
- **Effective repair rate**：有复验证据支持的成功返工数 / agent 发起的返工数；
- **False-completion rate**：存在核心 hard fail 或核心 `unverified` 却宣称完成的运行比例；
- **Reviewer agreement**：盲语义、目标核验与人工抽检在核心视觉维度上的一致率；
- **User-correction dependency**：主矩阵固定为 0 次追加纠错；若任务只能靠追加提醒通过，单列失败原因。
- **Generalization gap**：发现实例改善幅度与未见留出实例改善幅度之差；差距大说明可能在记题；
- **Leakage incidents**：agent surface、执行上下文或人工回答中出现实例专用提示的次数；任一次都会使受影响
  run 失效，不能通过扣少量分继续计入主结论。

## 7. 实施阶段与停止条件

### Phase B0：冻结协议与 fixture

- 建立 tracked 的 protocol/run manifest schema、普通用户 brief 模板、预设回答边界、seed 生成/校验脚本
  和评分表；具体 evaluator spec 与未见留出正文不进入 agent-visible package；
- 冻结 agent-visible surface 清单和 hash，运行 benchmark leakage 自动检查并做人工语义 diff；
- 为每个能力族预登记校准实例、未见留出实例和跨域反例；仓库只记录未见材料的 sealed hash 与解封规则；
- 用非评分 smoke 验证三个校准实例都能启动、保存到 `$HIP`、采集 trace 和生成评审输入；
- 固定模型/provider/version 后生成 protocol version；smoke 结果不得混入主矩阵。

completed smoke 的产物门禁已实现：

```sh
node tools/benchmark-manifest.mjs validate-smoke benchmark/runs/<run>.json --hip-root <实际HIP目录>
```

它要求 `finishedAt`、仓库外的绝对 trace、非空 HIP、至少一份非空 render 和至少一个最终节点；HIP、cache、
render 的每条 `$HIP/...` 路径都会解析真实文件并拒绝 `..`/symlink 逃逸。该门禁只验证启动与证据管线，
不读取 evaluator 答案，也不把 smoke 计入评分矩阵。

B0 的普通 brief、预设回答、seed fixture 和独立评分结果均已有通用 JSON Schema 与确定性 validator：

```sh
node tools/benchmark-manifest.mjs validate-brief <brief.json>
node tools/benchmark-manifest.mjs validate-answers <answers.json> --brief-sha <brief-file-sha256>
node tools/benchmark-manifest.mjs validate-seed <seed.json> --hip-root <实际HIP目录>
node tools/benchmark-manifest.mjs validate-inputs <run.json> --brief <brief.json> --answers <answers.json> --seed <seed.json> --hip-root <实际HIP目录>
node tools/benchmark-manifest.mjs validate-evaluation <evaluation.json> --run <run.json>
```

2026-09-01 已加入不进入 npm production package 的通用 seed generator：

```sh
node tools/benchmark-seed.mjs generate benchmark/seed-inputs/<family>-calibration.json \
  --hip-root <实际HIP目录> --hython <目标版本hython> --manifest <输出manifest.json>
```

generator 只允许空场景或固定 shaderball、FPS、帧范围和当前帧，不接收题目、材质、灯光、相机、目标参数
或 evaluator 答案。manifest 同时记录实际 HIP 字节 SHA-256 与规范化结构 identity SHA-256；同版本重复
生成必须结构 identity 一致，HIP 字节 hash 只绑定该次真实文件，不伪称 Houdini 二进制存档跨运行逐字节相同。
机械/模拟使用空场景，lookdev 使用固定 shaderball 以隔离建模差异；三份 calibration 输入已在 H21 实际
重复生成并通过 `validate-seed`，H21/H22 HOM 重复 identity 回归通过。它们只完成 seed fixture 基础，不等于
三个能力族的任务级 smoke、sealed 实例或评分协议已经完成。

执行模型冻结候选现为 `kimi-coding/k3` 与 `apikeyfun/glm-5.3-flash`。2026-09-01 使用同一 47,120-byte
PNG、同一中性 prompt、零工具直连两条 provider：K3 一次完成并正确描述图片；GLM 的 500-token 首次尝试
因 482 reasoning tokens 挤占正文而 `finish_reason=length`，1500-token 重试完成并正确描述同一内容。因此
两条当前 provider 路径的 native image transport/semantic 均已验证，但 GLM 的正式运行预算不得低于已验证
的 1500 max tokens。hash 与判定摘要记录在 `benchmark/model-capability-baseline.json`，不保存图片或凭据。
该探针只验证直接图片输入，不替代独立 evaluator；执行期 Vision Toolkit 仍固定为 0.1.7 + qwen-vl-max。

独立 evaluator 固定为 DashScope `qwen-vl-max`。通用 `blind-visual-v1` 与
`target-verification-v6` 分别封存为 canonical SHA-256 `51a96b85…` 与 `5b0f1bcf…`；blind 只收匿名图并
禁止 pass/fail，target 才收 public goal、criteria、确定性证据和已冻结 blind result。2026-09-01 用同一
Lookdev 整体/特写同输入做 V4 smoke：blind 一次返回可见布局与不确定性；Target 经 5 次合同拒绝后，v6
返回完整 9 criterion 与正确 namespace，normalizer 确定性生成空 hardFailures。完整 canonical bundle 输入
hash `bfe85928…` / `2fde0f28…` 不同，结果 hash `043bd75f…` / `e62e5ab0…`；基线在
`benchmark/evaluator-prompt-baseline.json` 标为 `verified`。

brief envelope 的 `briefId`、能力族和实例角色只供 evaluator/run 管理；执行 agent payload 只能取普通
`agentMessage` 与公开资源，不能暴露 calibration/holdout 身份。answers 只允许用户偏好、资产位置、输出格式
和执行约束，逐项声明不含实现指导/evaluator 材料且最多使用一次。run 单向绑定 brief、answers、seed HIP
和资源 hash，避免双向 hash 环。评分固定 40/25/25/10 四维求和，并检查 blind/target 输入独立封存、
hard-fail、core-success 和 run 结论一致。

已建立的通用底座：`benchmark/baseline.json`、protocol/run 两份 JSON Schema、agent-surface 规范化
SHA-256、sealed file SHA-256、关键不变量 CLI 校验和确定性回归。首轮公共 P0 与 trace normalized-step
共享解析器落地并完成 M1 冷启动复核后，runtime baseline commit 更新为
`cf1f1e80affa08c13db79294e78a49ee9a945d85`；路线状态同步后的 agent-surface hash 为
`b9bee29b431701e7262da916addbaeb3971c348e6a059685cf5df4400b9e02aa`。在模型/provider 和 sealed
实例齐备前，不生成看似完整的 protocol manifest。

2026-08-28 已从管理提交 `dea0ec8` 执行一次安全 repair：idle gate 通过，Houdini 21.0.440、DSH
0.1.1-rc.2、vision toolkit 0.1.7、Raw Gate、47 个动词及词表指纹均已复核；Bridge 无 active/queued/
running job，Web 返回 200。管理提交只增加未打包的 B0 工具，没有改变上述 agent-surface hash。

2026-08-31 已对当前工作树再次执行安全 repair：Houdini 21.0.440 Bridge 返回 49 个动词、指纹
`4f3516dec006…`，Raw Gate 开启且 job 计数全零，Web 返回 200。新 Houdini 模式会话成功执行
`houdini_query` 列举空 `/obj`；Host/Bridge 握手通过，Houdini Trace 将其记为只读 HOM probe，未误报
mutation 或 Gate block。该 smoke 证明当前通用合同已 live loaded，不代替未见实例的泛化评测。

同日全项目 review 后，Host read-only/media relay 与 launcher/WebView GUI 线程边界又有通用修复，旧
smoke 一度降级为历史证据。2026-09-01 已从 `cf1f1e8` 完整冷启动 H21：Bridge 49 动词/指纹、Web 200、
异步 WebView 与 Host 握手通过；真实 Houdini 模式 session `45798bd2-41a6-4b12-9dfa-fb62b25faa45`
的 query/Trace 记为 1 次只读 HOM probe，0 mutation、0 Gate block、0 rollback，baseline 恢复
`matchesBaseline=true`。这只封口 transport/runtime/分类基线，不代替三个能力族 seed smoke 或未见泛化。

### Phase B1：跑 3 × 2 校准/发现矩阵

- 每次运行结束立即归档 manifest 和原始证据，不先修改 persona、skill 或动词；
- 每个执行会话只得到普通用户 brief；评审合同、参考答案、隐藏检查和其他 run 的结果均不可见；
- 只修复会使整批无效的基础设施 P0，例如 trace 丢失、seed 不一致、图像实际未送达评审器；
- 基础设施 P0 修复后，受影响任务全部重跑并升级 protocol version。

### Phase B2：盲评、目标核验与跨 run 归因

- 先完成全部盲语义描述，再公开任务目标给评审器，防止后一个 run 污染前一个；
- 区分模型差异、任务特有 recipe、公共工作流缺口、工具缺口和 evaluator 不可靠五类原因；
- 对失败建立最小反事实轨迹，比较 agent 是否有足够现有能力发现它。

### Phase B3：只做证据达到门槛的改进

- 同一通用 probe 在至少两个独立任务重复、现有动词无法安全表达时，才进入 agent-native 动词设计；
- 同一领域知识在至少两个独立任务或“官方资料 + 本机复现”成立时，才进入生产 skill；
- 每个候选改进必须用对象无关的意图和状态表达；禁止加入 benchmark 名称、固定尺寸、节点清单、
  目标构图、任务专用报错或对该实例的隐式触发词；
- 只在自然语言合同/外部评分无法稳定比较或约束结论时，才设计最小结构化 ledger；
- 视觉 provider 若核心维度 reviewer agreement 不足，不晋升为 ground truth，先改诊断证据或换评审组合；
- 每项改进先在原失败任务上做回归，再冻结 production surface；是否具备泛化价值由 B4 的未见同族
  实例和跨域反例决定。

### Phase B4：复测与路线决策

B4 分成两条不可混淆的通道：

1. **回归通道**：重跑原失败实例，证明修复没有丢失原能力；
2. **泛化通道**：冻结改进后才解封未见同族实例，并运行预登记的跨域反例。

原题回归通过只能称为局部修复，不能证明通用能力提升。只有未见留出实例也改善、跨域反例没有误触发，
且出现以下结果才称为能力提升：

- core success rate 上升，且不是靠放宽硬失败线；
- self-detected defect 与 effective repair rate 上升；
- false-completion rate 不恶化；
- 独立评审和人工抽检的一致率足以支持结论；
- 改进没有把简单任务变成不必要的问卷或固定 recipe。

若原题显著改善而未见留出不改善，结论必须写“疑似过拟合/仅局部修复”，回退任务专用内容或缩小
主张；不得通过公开留出答案后继续修改并仍把它称为同一个 holdout。解封后的实例自动转为下一轮校准集。

## 8. 本阶段明确不做

- 不先实现覆盖所有 Houdini 领域的结构化任务本体或全 mutation fail-closed；
- 不把任何具体校准题或留出题的专用检查写成公开动词；
- 不把任何校准/留出实例的 ID、对象配方、目标参数、评分答案或失败补丁写入 production guidance、
  preset、skills、verb/tool 或错误提示；
- 不因单个模型一次失败就升级 prompt、skill 或工具；
- 不把同一目标描述再次喂给视觉评审并称为独立判断；
- 不把 node/primitive 数、render 成功、cache 文件存在或 todo 完成当作质量通过；
- 不在 6 次主矩阵完成前并行迁移 `ctx.jobs`、重做权限层或扩大 GUI 回归，以免改变实验底座；
- 不删除既有 trace、media、session 或 `tools/out` 证据来追求目录表面整洁。

## 9. 能力主张的最小证据

后续报告必须明确区分三种结论：

- **原题变好**：同一校准实例回归改善，只支持局部修复；
- **同族泛化**：未见同族实例改善，支持该领域内的有限泛化；
- **跨域通用**：至少两个能力族的独立实例受益，且跨域反例无副作用，才支持 system guidance 或
  通用工具层面的能力主张。

只有未见留出实例可以把“我们修好了这道题”提升为“agent 获得了可迁移能力”；原题重复、措辞变体、
同一 seed 换参数或 evaluator 被答案污染都不能证明通用能力提升。

## 10. B2 跨 run 归因（2026-09-02，正式 3×2 完成 6/6 后）

### 10.1 批次合规与主指标

- 6/6 自然完成（单 turn、0 追加纠错、墙钟均在 120 分钟内），`validate-run`/`validate-inputs`/
  `validate-evaluation` 全通过；`evaluatorMaterialExposed=false` 六场一致，leakage incidents = 0，
  holdout 全程未解封。
- **Core success rate = 6/6（100%）**：全部 0 hard failure 且总分 ≥ 75（100×4、90×2）。
- **False-completion rate = 0/6**：无核心 hard fail / 核心 unverified 被宣称完成的运行。
- **User-correction dependency = 0**（预登记值，无例外）。
- **Self-detected defect rate**：agent 自检发现并修复的缺陷均有复验证据（lookdev/K3 相机近裁剪黑屏、
  mechanical/GLM 局部图不清重渲、lookdev/GLM 480×360 预览重渲 1280×960）；但两起诚实缺陷
  （lookdev 两模型各一）均未被 agent 自己发现，诚实维度的自检出率 0/2。
- **Effective repair rate**：上述 3 次 agent 发起的返工均有复验证据支持，记 3/3。
- **Reviewer agreement**：六场核心视觉维度上 blind/target/人工审计一致；唯一保留分歧为
  lookdev/GLM honest-report（target 因缺报告原文裁 unverified，人工记录事实冲突），按规则同样 0 分，
  不影响总分结论。

### 10.2 五类归因

1. **模型差异**：结果同族并列（Mechanical 100/100、Simulation 100/100、Lookdev 90/90），差异全部在
   过程。K3 效率显著更高（mechanical 15.0 vs 31.7 min、simulation 36.8 vs 74.9 min），动词密度高、
   调用次数少；但 simulation/K3 出现 2 次 query mutation 和 18 次裸 File Cache 写盘，GLM 全部三场
   0 query mutation。GLM 风格是小步多探针（lookdev rawReadOnly 41、toolCalls 108），失败/回滚更多
   （10–14 次）但无越权修改。当前批次不支持排名结论，只支持“结果并列、过程画像不同”。
2. **任务特有 recipe**：未发现。同 brief 下两模型路线分化明显（lookdev：K3 per-mesh 绑定 + EXR/PNG
   双出图 vs GLM scope 绑定 + 仅 PNG），说明执行不是背固定配方。
3. **公共工作流缺口**：
   - **诚实报告与可回读事实不符在 lookdev 两模型独立重复**（K3 虚构 DomeLight；GLM 台账称无
     warning 而回读有 2 条 SOP import warning）。跨模型重复成立，但属同一实例，跨任务重复未成立。
   - **视觉 bootstrap 缺口跨族复现 2 次**（simulation/GLM、lookdev/GLM）：GLM adapter 未声明 image
     input 导致 direct `read_image` 失败，agent 自行回退 Vision Toolkit `vision_glance` 成功。这是
     provider/toolkit 声明缺口，不是模型能力问题。
4. **工具缺口**（均只有单任务证据，未达 B3 门槛，记观察）：
   - `render_frame` ~110s 硬顶 vs CPU 正式渲染 >2min → lookdev/GLM 7 次带理由的单次 allow_raw
     豁免（首次被 Gate 拦截后合规重发）。“长渲染无正式异步动词”是真实缺口。
   - File Cache 写盘无动词 → simulation/K3 18 次裸 `pressButton`。
5. **evaluator 可靠性**：所有不合规响应均 fail-closed 未进评分（lookdev/GLM blind 2 次拒绝后第 3 次
   通过；mechanical/GLM target 非法状态 `partial` 被拒后重试通过；批次内 1 次 CLI 更新提示污染 fence
   被拒并以 `--quiet` 重试）。发现的输入设计缺口：target 输入只含 honest-report 的声明摘要、不含最终
   报告原文，导致 lookdev/GLM 该项只能保守裁 unverified。

### 10.3 B3 候选清单（门槛状态如实标注）

| 候选 | 类型 | 证据 | 门槛状态 |
|---|---|---|---|
| 报告收尾前最终 stage 复核 probe（诚实缺口） | 动词/skill 候选 | lookdev 两模型重复 | 跨模型 ✓、跨任务 ✗，暂不进 surface |
| target 输入附最终报告原文 | evaluator 输入修复 | lookdev/GLM 单 run | 改 evaluator 输入 = 新 protocol version，记 v5 候选 |
| 长渲染异步动词（render 域） | 动词候选 | lookdev/GLM 单 run 7 次豁免 | 待第二个任务复现 |
| File Cache 写盘动词 | 动词候选 | simulation/K3 单 run 18 次裸写 | 待第二个任务复现 |
| GLM adapter image input 声明修复 | provider/toolkit 修复 | simulation+lookdev 两次复现 | 达复现门槛；改 agent surface，需新 protocol version + B4 回归 |

### 10.4 本阶段明确不下的结论

- 不宣布任何模型排名或通用能力提升；三族并列只说明 calibration 实例上当前 surface 不区分两模型结果。
- 不因诚实扣分修改评分线；两次 90 分保留为 discovery 事实。
- B3 候选在进入 surface 前一律先升级 protocol version，改进的泛化价值只能由 B4 留出解封判定。
