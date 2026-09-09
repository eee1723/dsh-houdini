---
name: houdini-trace-analysis
description: 系统复盘 dsh-houdini / DeepSeek Harness 的 Houdini agent trace，包括 session.jsonl.zstd、trace-report HTML 或多次会话对比。用于用户要求分析最新/指定 Houdini trace、检查任务为何失败或低效、审计工具和动词的应调用未调用/缺失/误用/冗余/拆分/合并、判断节点模块与 cook/属性/显示/渲染/动画逻辑是否符合 Houdini 工作方式，以及依据累积 trace 更新审计规范和词表路线时。
---

# Houdini Trace Analysis

把 trace 当作一次可重放的工程实验，不把调用次数当结论。先确定性提取事实，再按 Houdini 数据流和 agent trajectory 审判，最后区分“本次修复”与“跨 trace 产品决策”。

## 工作流

1. 定位原始 `session.jsonl.zstd`。记录 session ID、用户任务、时间范围和是否有后续纠正。
2. 在 dsh-houdini 仓库中运行：

   ```powershell
   node <skill-dir>/scripts/extract-trace-evidence.mjs <session-file> --out tools/out/trace-evidence-<id>.json
   node tools/trace-report.mjs <session-file> --out tools/out/trace-session-<id>.html
   ```

   多会话对比时向 evidence 脚本连续传多个 session 路径。不得只读 HTML 摘要；必须保留原始事件证据。
3. 完整阅读 [references/audit-rubric.md](references/audit-rubric.md)，按其中的强制量表审计。分析工具演化或重复问题时再读 [references/known-patterns.md](references/known-patterns.md)。
   若 trace 是 SOP 构建/动画任务，同时加载 `houdini-sop-workflow`，用其模块契约检查 agent 路径。
4. 从用户消息重建任务契约：产物、参考状态、质量/LOD、已确认选择、agent 假设、视觉目标、时间/动画目标、交互约束、保存/交付要求。不要用 agent 自己的 todo 替代用户契约；把“未询问”“用户授权自选”和“已有可信来源”分开。
5. 给轨迹划分真实阶段：接收/判歧义 → 研究 → 澄清 → 合同 → 现场检查 → 设计 → 分模块构建 → 模块验证 → 集成 → 静态视觉验证 → 时序验证 → 修订 → 清理/交付。不适用的前置阶段可省略，但开放式任务不能把基于模型记忆的暗中选型伪装成已确认合同。阶段以证据和状态跃迁为准，不按 assistant 宣称划分。
6. 建立工具机会矩阵。对目录中每个相关动词标记 `已正确使用`、`该用未用`、`误用/工具缺陷`、`不适用`；另列 `能力缺失`。未使用不等于应删除。
7. 对每个关键 Houdini 模块检查输入、输出、属性契约、局部几何不变量、cook 错误/警告、帧依赖、显示/渲染状态。整体 bbox/点数不能替代局部拓扑和模块语义验证。
8. 重建一条最小反事实轨迹：如果从头正确执行，阶段和工具顺序应是什么；用它量化绕路、重复探测和过早完成声明。
9. 将建议分级：
   - `P0`：工具自身错误、数据破坏、错误成功判定、无法完成任务。
   - `P1`：明确重复出现的缺失能力或工作流守卫。
   - `P2`：单 trace 假设、便利性或性能改进，等待更多证据。
10. 检查本次是否发现新的通用模式。只有满足量表中的准入条件才更新 `known-patterns.md`；写明 session ID、证据步骤、反例和状态。若用户明确要求更新/修复 skills，先加载 `houdini-skill-governance` 决定唯一维护位置、证据等级和验证；只要求分析时输出 skill delta proposal，不静默修改生产 skill。若动词设计已拍板，再同步 `docs/tool-design.md` 与 `docs/development.md`。

## 硬规则

- 每个主要判断引用至少一个 trace 步骤编号/时间或用户消息 seq；数字来自 evidence，不凭印象。
- 区分工具调用失败、动词内部失败、执行成功但产物错误、最终未交付四种失败。
- 区分“工具缺失”和“已有工具未使用”；先证明任务意图，再做词表建议。
- 用 `capabilitySnapshots` 判断该步骤当时实际曝光的能力；不得用当前新词表倒查旧 trace 后指责 agent 漏用。
- 视觉证据读取 `visionEvidence[].role/transportOk/semanticOk/reason` 与 `completionRisks`。只有 `role="inspection" && semanticOk=true` 才算语义识图；bootstrap、presentation、transport success、结构化 `ok:false` 或文本拒绝都不算。只有 render/render_check 而没有成功 inspection 时，必须保留“视觉语义未验证”的边界。
- 不把 `catalog.used/catalog.total` 称为动词使用率。优先读取 `verbAdoption`，分别解释调用含动词率、动词密度、只读query守卫范围、Gate拦截、裸修改候选、疑似/未知副作用；成功exec含动词率的分母也包含测试/动态调用，不是修改采用率。目录广度只说明触达能力，没检出修改不证明只读。
- HDA维护按量表区分section写入、实际回调、最终输出和交付依赖；内嵌Python不证明无其他HDA/资源依赖，内部函数通过不冒充按钮验收。普通功能维护不强制艺术渲染。
- 开放式质量任务优先读取 `qualityLoopEvidence` 与对应 `completionRisks`，核对合同缺字段、research
  可用但未用、质量合同未加载、首张 render 过晚、关系 probe、控制扰动恢复和最终统计新鲜度；
  自动风险是可复核证据索引，不是艺术质量评分。合同字段可来自 mutation 前 assistant prose、
  goal 或 todo；后二者只证明 agent 记录了计划，用户确认仍以 ask result/用户消息为准。
- 工具删除/合并不得由单次零使用推出。跨至少三个多样任务仍冗余、存在安全替代且无独立语义，才可列为删除候选。
- Houdini 中先验证数据流和局部几何，再调相机、灯光、材质或视觉模型。渲染能出图不证明 SOP 结果正确。
- 任务声称符合真实对象、行业范围或外部质量标准时，必须找到用户提供或 agent 实际检索的来源证据；自生成尺寸的内部一致、模型记忆和“看起来合理”只能标假设。风格化、用户授权自选或无需外部真实性的任务是边界，不强迫无意义研究。
- 对动画任务必须做至少两个相隔帧的几何或固定相机图像 A/B 验证。客观数据完全静止必须判未完成；节点/数据/时间语义通过而静帧难以裁定细微动态或审美力度时，可标记“视觉待用户播放判断”，不得无限追图或伪称视觉确认。
- `cook_node` 返回 warning 不能被“无 error”覆盖；必须解决或解释其可接受性。
- 视觉提问先用中性描述，再做目标核验；不要在 prompt 中预设“这是草地/已经成功”。
- 当前 trace 结束于 tool result、仍有未完成 todo、或没有最终交付文本时，结论必须明确写“未完成”。
- 输出要同时覆盖任务质量、工具质量和审计体系演化；不能只列调用统计。

## 输出契约

严格按以下顺序输出：

1. 结论与完成度
2. 用户任务契约及实际交付差距
3. 阶段时间线与关键转折
4. 工具/动词证据总览
5. 该用未用、误用、缺失、拆分/合并/保留矩阵
6. Houdini 节点模块、数据流、cook、显示、渲染与动画审计
7. 最小正确轨迹
8. P0/P1/P2 改进清单，含证据强度
9. 对审计 skill 本身的更新建议

不要为了显得全面而平均分配篇幅；优先解释造成错误产物、用户返工和长时间绕路的因果链。
