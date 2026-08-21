# Houdini domain skill 质量规范

## 目录

1. 质量目标
2. 新建准入
3. 标准结构
4. 泛化与边界
5. 拆分、合并、弃用
6. 验证清单

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

## 2. 新建准入

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

## 3. 标准结构

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

## 4. 泛化与边界

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

知识放置优先级：

1. 已存在的唯一维护位置；
2. 最具体但仍覆盖整个主张的 domain skill；
3. governance/trace 只保留跨域准入和证据规则；
4. system prompt 只放高频 dispatch 和无法靠 skill 触发补救的硬不变量。

## 5. 拆分、合并、弃用

### 拆分

当以下至少两项长期不同才拆：触发意图、Houdini context、数据模型、执行副作用、来源集合、
完成门、版本节奏。文件变长本身不是拆分理由，先用 reference 渐进披露。

### 合并

当两个 skill 的触发、决策树、资源和完成门基本相同，且 trace 显示 agent 经常选错时合并。
相邻领域可联用不等于应合并，例如 SOP 源数据与 Solaris 最终渲染有明确交付边界。

### 弃用/删除

至少需要：三个多样任务无独立价值、存在更安全等价替代、迁移路径、无诊断/逃生用途。
先标 superseded/deprecated，更新注册和调用者，新 session 验证后再删除。

## 6. 验证清单

- `SKILL.md` frontmatter/name/description 通过结构校验；无模板占位。
- 所有 reference 链接存在并可从 SKILL.md 渐进到达；无孤儿 reference。
- `src/skill.ts` 注册名/目录一致；`npm pack --dry-run` 包含全部资源。
- `npm run build` 通过；若只改未注册 reference，可说明为何 build 非必要。
- description 用正例/相邻反例做触发检查。
- 至少一个真实行为用例验证决策和完成门，不只匹配文字。
- 强制规则有来源、版本、边界和反例。
- 与现有 skills/system guidance/tool-design 无冲突或重复真相源。
- 变更状态、证据强度、下一验收写入 development/模式库；没有把计划写成已完成。
- 发布后用新 session 检查 skill catalog/activation，旧 session 不能作为曝光证据。
