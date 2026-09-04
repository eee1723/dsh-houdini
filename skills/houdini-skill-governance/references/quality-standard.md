# Houdini domain skill 质量规范

## 目录

1. 质量目标
2. 弱模型执行标准
3. 新建准入
4. 标准结构
5. 泛化与边界
6. 拆分、合并、弃用
7. 验证清单

## 1. 质量目标

每个 domain skill 同时追求：

- **触发准确**：description 能区分适用和相邻但不同的任务。
- **决策增益**：正文只保留会改变 agent 选择或完成判定的非显然知识。
- **泛化**：规则围绕数据模型、输入/输出契约和意图，不围绕某个 HIP 的节点名。
- **稳定**：写明版本、失败面、状态恢复、warning/error 和交付边界。
- **可证**：完成门绑定客观数据；视觉只承担可见语义。
- **动态更新**：来源、反例和下一验收清楚，允许窄修正而不是永久叠加。
- **精简**：SKILL.md 是路由和硬规则，条件性细节进入 references；不复制手册。
- **可组合**：和 SOP、Solaris、trace 等 skill 的职责不重复，联用顺序明确。

精简不是追求最少文件或最短字数，而是让每条内容只有一个维护位置，且实际改变决策。
新增文字必须至少完成一件事：改变路由、提供已验证 fast path、阻断已证失败或定义完成门；否则删除。
优先替换旧规则而不是尾部追加，发布前检查同一概念在 guidance/SKILL/reference 间是否重复或矛盾。

## 2. 弱模型执行标准

domain skill 的首要消费者是可能缺少 Houdini 经验、版本记忆不稳定、容易在局部成功后提前完成的
agent。skill 不替它完成任务，但必须提供一条低歧义、能恢复、能验收的执行脊柱。

### 2.1 复杂度门

- 简单且规格完整的一步编辑直接执行，只取与改动同层的回读证据；不强制写长计划、研究或渲染。
- 跨三个以上模块、含状态/时间/缓存/绑定、依赖版本敏感节点、质量关系复杂或需正式交付的任务，
  在首个大规模 mutation 前用 prose 或 todo 留下一份紧凑合同。
- 合同写意图和边界，不写项目答案；至少回答：最终交付是什么、采用哪类数据模型、关键模块之间
  传什么数据、哪些证据才能完成、哪些 helper 不属于交付。

### 2.2 执行脊柱

复杂任务的 domain skill 应让 agent 能按以下状态推进；标题和步数可因领域调整，不要求机械复述：

```text
任务契约 / 交付边界
→ 数据模型与原生系统选择
→ 已验证 fast path 或最小骨架
→ 分模块 build → cook/readback checkpoint
→ 集成后的最终 deliverable 取证
→ 时序/视觉/文件等交付门
→ 清理、恢复、保存、诚实报告
```

每个模块用 `输入/身份/rest state → 操作/求值 → 输出 → 不变量` 描述。driver、binding/evaluation、
driven output、presentation 是不同层；上游层通过不能替代下游交付。

### 2.3 Fast path 与渐进披露

- `SKILL.md` 只保留高频路由、执行脊柱、关键边界和完成门；具体节点、参数 token、HOM 片段、
  版本差异与罕见失败进入按需 reference。
- reference 以用户意图/数据模型路由，不按节点字母表堆手册。每条已验证 fast path 至少写：
  `Applies when`、`Do not use when`、输入/输出、目标版本、最小构建、checkpoint、失败转向和验收。
- 只有跨目标版本实测或目标版本 runtime 已复现的脆弱语法才允许给精确片段。片段使用占位名称和
  最小几何，不携带训练实例的对象、数值、帧号、审美或评分答案。
- 同一知识只在一个 canonical reference 维护；主 skill 只链接和概括决策，不复制长 recipe。

### 2.4 探测阶梯与停止条件

已存在 fast path 时先采用，不从零逆向 HDA。未知字段按最便宜、最公开的证据逐级探测：

1. 当前任务已加载的 domain reference；
2. `verb_help`、`search_tab_menu/search_tab_entries`、`list_parms/read_parms/describe`；
3. 一个最小、可删除、单变量的 runtime probe；
4. 同版本本机 help/shipped example；
5. 只有公开合同不足或 runtime 与合同冲突时才检查 HDA internals/源码，并明确这是诊断而非默认做法。

同一模块边界连续两次失败后，不继续改拼写或叠补丁：回到最后一个已验证 checkpoint，重述失败层，
查对应 fast path/公开合同并换策略。probe 必须有停止条件和清理路径；最终任务不保留诊断网络。

### 2.5 证据、失效与裁决

- 每个核心主张绑定同层证据；cook success、总 bbox、文件存在、pixel diff 或上游 metadata 都不能
  自动证明最终语义。
- actual deliverable 的直接探针失败后保持 fail，不能换测 proxy/anchor/driver 后把同一契约改判 pass。
- 最后一次影响数据模型、核心参数、接线、材质、状态求值或输出形态的 mutation，会使受影响的
  旧证据失效；只重跑受影响完成门，不无差别重做全部任务。
- 证据冲突按“最接近交付物且最直接”裁决。数值可推翻视觉对隐藏状态、相机元数据或精确角度的
  猜测；清晰视觉反例可推翻仅凭像素变化得出的主体成功。无法裁定则标 `unverified`。
- 最终报告只声明最后一轮新鲜证据实际覆盖的对象、样本和版本；todo complete 不补证。

### 2.6 标准验收矩阵

每个新建或实质更新的 domain skill 都必须准备以下行为验收；可分批完成，但未完成不得写 released：

| 用例 | 证明什么 |
|---|---|
| 原失败实例 | 修正确实挡住已知因果链，不只改措辞 |
| 未见同族复杂正例 | 规则能迁移到不同对象/规模/命名/参数 |
| 相邻领域反例 | description 与路由不会过度触发 |
| 领域内反例 | fast path 的 `Do not use when` 真能选择另一正确模型 |
| 目标版本矩阵 | H21/H22 等支持版本的类型、参数、数据和失败面一致或显式分支 |
| 失败恢复 | 相同边界重复失败时换策略、rollback/cleanup 正确 |
| 最终交付 | helper 隔离、新鲜证据、保存/缓存/渲染与诚实报告成立 |

审查记录同时报告结果质量与过程效率：首次正确 checkpoint、调用数、失败/rollback、重复探测、
raw exemption、用户纠正、证据刷新。指标用来定位下一处改进，不设置会诱导作弊的固定得分阈值。

## 3. 新建准入

新 domain skill 至少满足：

1. 有可识别的用户意图和触发边界；
2. 有与现有 skill 不同的数据模型、关键选择或完成门；
3. 领域知识足以减少重复失败，不只是节点目录；
4. 至少有一个真实任务/工程/官方模式和一个反例；探索型候选可先记录在 development，
   不必立即发布；
5. 能说明为什么更新既有 skill 不够；
6. 有可执行的第一验收。

以下通常不应新建：

- 某个镜头、草地、魔方、材质球的专用 recipe；
- 只有一个节点或一个 API 的速查；
- 与现有 skill 相同触发、相同生命周期、相同完成门的另一个名字；
- 尚无任务证据、只是“将来可能会用”的领域目录。

COP 和 SIM 可以成为独立 skill，但应先证明各自有独立 context、数据/缓存/时间语义、
执行风险和完成门，不能只因为 Houdini UI 中有独立网络类型。

## 4. 标准结构

### Frontmatter

```yaml
---
name: houdini-<domain>-workflow
description: <做什么、何时触发、必要的相邻排除边界>
---
```

名称使用小写连字符，description 不写穷举大全，不吸引无关任务。

### SKILL.md 正文

按实际需要保留以下内容，不要求机械套满所有标题：

1. 一句话目标与非目标；
2. 任务/数据模型分类；
3. 最小执行顺序和 checkpoint；
4. 关键原生系统选择及反例；
5. 跨 context/skill 联用边界；
6. 完成门；
7. 按需 reference 路由。

长版本表、节点模式、输入 schema、来源账本、视频/工程分析细节进入 references。SKILL.md
不应成为官方手册的缩写版。

### Reference 条目最小 claim 格式

```text
Claim:
Why it changes a decision:
Source/provenance:
Houdini version/context:
Evidence level:
Applies when:
Counterexample/boundary:
Validation:
Last reviewed:
```

无需为每句常识建账本；对版本敏感、强制性、来源外部或将改变工具设计的主张使用该格式。

## 5. 泛化与边界

把观察拆成四层：

```text
project-specific choice
→ reusable technique
→ Houdini domain invariant
→ cross-domain system invariant
```

只把证据支持的那一层写入对应 skill。例如：

- “这个魔方用 27 块”是项目选择；
- “刚体 piece 需要稳定 ID/transform”是 domain invariant；
- “修改后必须重跑被失效的完成门”是 cross-domain invariant。

规则必须写适用条件和反例。没有反例的绝对规则通常尚未完成设计。

Benchmark 只提供证据，不提供可复制进生产 skill 的答案。不得把 benchmark ID、实例对象名、
目标数值、评分 rubric、固定节点网络或针对某次失败的补丁措辞写进 description、SKILL.md、reference、
preset 或 system guidance。候选规则要先改写成与对象无关的数据模型、状态转换、检查意图或完成门，
再同时验证：原失败实例、一个未见同族实例和一个不应触发该规则的跨域反例。只在原实例上改善属于
局部修复，不构成通用 skill 发布证据。

知识放置优先级：

1. 已存在的唯一维护位置；
2. 最具体但仍覆盖整个主张的 domain skill；
3. governance/trace 只保留跨域准入和证据规则；
4. system prompt 只放高频 dispatch 和无法靠 skill 触发补救的硬不变量。

## 6. 拆分、合并、弃用

### 拆分

当以下至少两项长期不同才拆：触发意图、Houdini context、数据模型、执行副作用、来源集合、
完成门、版本节奏。文件变长本身不是拆分理由，先用 reference 渐进披露。

### 合并

当两个 skill 的触发、决策树、资源和完成门基本相同，且 trace 显示 agent 经常选错时合并。
相邻领域可联用不等于应合并，例如 SOP 源数据与 Solaris 最终渲染有明确交付边界。

### 弃用/删除

至少需要：三个多样任务无独立价值、存在更安全等价替代、迁移路径、无诊断/逃生用途。
先标 superseded/deprecated，更新注册和调用者，新 session 验证后再删除。

## 7. 验证清单

- `SKILL.md` frontmatter/name/description 通过结构校验；无模板占位。
- 所有 reference 链接存在并可从 SKILL.md 渐进到达；无孤儿 reference。
- `src/skill.ts` 注册名/目录一致；`npm pack --dry-run` 包含全部资源。
- `npm run build` 通过；若只改未注册 reference，可说明为何 build 非必要。
- description 用正例/相邻反例做触发检查。
- 复杂任务有紧凑交付合同、数据模型、fast path、checkpoint、探测阶梯、停止条件和证据失效规则；
  简单任务不会被这些规则强制膨胀。
- fast path 明确 `Applies when / Do not use when`，版本敏感精确片段已在目标版本验证且不含实例答案。
- 至少一个真实行为用例验证决策和完成门，不只匹配文字。
- 原失败、未见同族正例、相邻/领域内反例、版本矩阵、失败恢复和最终交付按 §2.6 登记状态；
  缺项必须留在 candidate/verified，不得标 released。
- 强制规则有来源、版本、边界和反例。
- benchmark 派生规则不含实例标识、对象配方、目标参数或评分答案，并有未见同族实例和跨域反例。
- 与现有 skills/system guidance/tool-design 无冲突或重复真相源。
- 变更状态、证据强度、下一验收写入 development/模式库；没有把计划写成已完成。
- 发布后用新 session 检查 skill catalog/activation，旧 session 不能作为曝光证据。
