---
name: houdini-skill-governance
description: 创建、审查、维护和演化 dsh-houdini 的领域 skills。用于新增 COP/SIM/rig/project-analysis 等 skill，或依据 Houdini trace、SideFX 官方文档、本机版本、用户视频/工程更新现有 skill；不用于普通内容制作，也不允许未经授权或未经证据门自动修改生产 skill。
---

# Houdini Skill Governance

把 skill 当成有来源、版本、适用边界和回归证据的产品模块，不当成不断追加经验的笔记。
目标是让 Houdini 领域知识持续演化，同时保持触发准确、规则泛化、内容精简和版本可验证。

## 入口工作流

1. 先确认当前任务授权的是**只读分析/提案**，还是允许修改源码仓库中的 skills。普通
   Houdini 内容任务、只要求分析 trace、安装包目录或 `$HIP` 都不授权修改生产 skill；
   在这些场景只输出候选变更。不要把 skill 文件写进用户 HIP。
2. 定位 dsh-houdini 源码根；修改前运行：

   ```powershell
   node skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs --strict
   ```

   先盘点已有 skill、注册状态、引用完整性和重叠范围，不能默认新建。
3. 给请求分类：`CREATE`、`UPDATE`、`INGEST`、`SPLIT/MERGE`、`DEPRECATE`、`RELEASE_AUDIT`。
4. 创建或重构 skill 时完整阅读
   [references/quality-standard.md](references/quality-standard.md)。
   domain skill 的实质更新必须按其中“弱模型执行标准”检查复杂度门、执行脊柱、fast path、
   探测停止、证据失效与验收矩阵；不能只过 frontmatter/链接审计就称质量达标。
5. 证据来自 trace、官方文档、视频、HIP/HDA 工程或源码时，完整阅读
   [references/evidence-ingestion.md](references/evidence-ingestion.md)，先建立 claim/provenance，
   再决定是否改变规范。
6. 做长期维护、Houdini 版本升级、跨 skill 冲突、发布或回滚时，完整阅读
   [references/maintenance-lifecycle.md](references/maintenance-lifecycle.md)。
   做 governance 行为回归时读取 [references/eval-cases.md](references/eval-cases.md)，按
   observable decision/side effect 验收，不写只匹配标题或措辞的测试。
7. 把每条候选知识放到正确层：
   - system guidance：极少量跨域 dispatch/硬不变量；
   - governance skill：证据门和维护协议；
   - domain skill：领域路由、数据契约、关键选择和完成门；
   - reference：条件性细节、官方模式、版本差异、反例；
   - verb/tool：跨任务执行意图、校验、事务和状态恢复；
   - trace pattern/development docs：证据历史、候选和路线，不冒充已发布能力。
8. 做最小 diff，清除重复规则，保留反例和适用边界。单个项目节点名、艺术偏好、视频作者
   个人习惯、benchmark ID、实例对象/目标参数、评分答案或模型臆测不得升级为通用硬规则。
9. 验证后才标记完成：目标 skill 的结构校验、治理审计、引用/注册、必要构建、当前 Houdini
   版本实验、原失败、未见同族行为用例和相邻/领域内反例。新 session 才能验证新的 skill
   catalog/guidance 是否曝光；缺少任一发布门时明确停在 candidate/verified。

## 受控自进化

允许任何任务产出 `skill delta proposal`，但生产 skill 只按以下状态迁移：

```text
observation → candidate → accepted → verified → released
                                  ↘ rejected
released → superseded/deprecated → removed
```

- 单 trace、单视频、单工程默认只到 `candidate`。
- SideFX 官方资料仍需用目标 Houdini 版本的 Tab/本机帮助/最小实验确认适用性。
- 可复现的 P0 工具或契约 bug 可直接修，但必须有回归。
- 跨任务规则通常要求两个独立证据；删除/合并要求至少三个多样任务、反例和迁移路径。
- 修改本治理 skill 自身需要比普通 domain skill 更强的理由：明确用户授权，并有跨领域证据或
  治理流程自身的可复现失败。它不得因为自己生成的建议递归改写自己。

## 硬边界

- “分析材料”不等于“获得发布、复制或外传材料的权利”。记录来源、权限、隐私和许可；
  用户工程中的专有 HDA、代码、路径、资产和第三方视频内容只提炼抽象规律，不复制进包。
- 不复制整本 SideFX 手册或长视频转录。保存会改变决策的结论、前提、版本、反例和链接。
- 不因一个新领域自动创建 skill。只有触发条件、数据模型、工作流和完成门与现有 skill 明显
  不同时才拆分；能自然扩展既有 skill 时优先更新。
- 不让管理 skill 代替领域专家 skill。它裁判证据与结构，不伪装成 COP、SIM、KineFX 或
  Solaris 的操作手册。
- 不以文档更新冒充能力实现。若工具/skill 尚未注册、构建、部署和用新 session 验证，状态
  必须写“计划/候选”，不能写“已完成”。
- 不用训练/发现实例本身验证泛化。实例修复必须再过未见同族任务和跨域反例；只在原题变好时
  记录为局部回归通过，不发布为通用能力提升。

## 输出契约

每次治理任务都交付：

1. 输入来源与授权边界；
2. 已确认事实、未验证假设、冲突与版本；
3. 目标 skill/layer 与 CREATE/UPDATE/SPLIT/MERGE/NO_CHANGE 决策；
4. 最小变更及没有采纳的内容和理由；
5. 验证结果、失败和未覆盖反例；
6. evidence level、下一验收和回滚方式。
