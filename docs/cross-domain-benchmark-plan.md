# dsh-houdini 跨域能力评测计划

> 状态：2026-08-31 路线与反过拟合硬约束已拍板；B0 schema、交叉 hash 与 smoke 产物门禁已实现，
> 实际 seed generator、模型/provider 和最终 protocol version 待冻结。
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

brief envelope 的 `briefId`、能力族和实例角色只供 evaluator/run 管理；执行 agent payload 只能取普通
`agentMessage` 与公开资源，不能暴露 calibration/holdout 身份。answers 只允许用户偏好、资产位置、输出格式
和执行约束，逐项声明不含实现指导/evaluator 材料且最多使用一次。run 单向绑定 brief、answers、seed HIP
和资源 hash，避免双向 hash 环。评分固定 40/25/25/10 四维求和，并检查 blind/target 输入独立封存、
hard-fail、core-success 和 run 结论一致。

已建立的通用底座：`benchmark/baseline.json`、protocol/run 两份 JSON Schema、agent-surface 规范化
SHA-256、sealed file SHA-256、关键不变量 CLI 校验和确定性回归。首轮公共 P0 与 trace normalized-step
共享解析器落地后，baseline commit 更新为 `ce794177b449e9259f369040cd387d027bc764c1`，当前
agent-surface hash 为 `24ac8552f4ec537dd39719377f0665b0cf4bcf7ecea51032f3de6d32648b3c7c`。在模型/provider 和 sealed
实例齐备前，不生成看似完整的 protocol manifest。

2026-08-28 已从管理提交 `dea0ec8` 执行一次安全 repair：idle gate 通过，Houdini 21.0.440、DSH
0.1.1-rc.2、vision toolkit 0.1.7、Raw Gate、47 个动词及词表指纹均已复核；Bridge 无 active/queued/
running job，Web 返回 200。管理提交只增加未打包的 B0 工具，没有改变上述 agent-surface hash。

2026-08-31 已对当前工作树再次执行安全 repair：Houdini 21.0.440 Bridge 返回 49 个动词、指纹
`4f3516dec006…`，Raw Gate 开启且 job 计数全零，Web 返回 200。新 Houdini 模式会话成功执行
`houdini_query` 列举空 `/obj`；Host/Bridge 握手通过，Houdini Trace 将其记为只读 HOM probe，未误报
mutation 或 Gate block。该 smoke 证明当前通用合同已 live loaded，不代替未见实例的泛化评测。

同日全项目 review 后，Host read-only/media relay 与 launcher/WebView GUI 线程边界又有通用修复，因此
上述 smoke 已降级为历史 live 证据，`baseline.runtimeVerification.matchesBaseline=false`。阻塞 preflight
已全部迁到 worker；正式 protocol freeze 前完整重启 Houdini并重跑同一 smoke。这是修复已存在的执行
边界，不是按某个 benchmark 实例扩写 GUI 能力。

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
