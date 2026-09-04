# Houdini Skills Governance M1 Audit

日期：2026-08-21

范围：`houdini-trace-analysis`、`houdini-sop-workflow`、
`houdini-solaris-karma-workflow`、`houdini-rig-animation-workflow`、
`houdini-skill-governance`

授权：用户已要求继续长期 skill 治理与开发；允许修改仓库内 bundled skills，不涉及用户 HIP。

## 1. 结论

五个 skills 的触发、数据模型和完成门均有独立价值，当前决策是：

| Skill | 决策 | 理由 |
|---|---|---|
| trace analysis | KEEP | 审计的是轨迹证据、工具机会和产品演化，不承担内容制作 |
| SOP workflow | UPDATE/KEEP | 数据流与局部几何门独立；修正“所有任务强制 render_view”的过硬视觉门 |
| Solaris/Karma | UPDATE/KEEP | USD/material/render 产品契约独立；补 H21/H22 claim 状态，不与 SOP 合并 |
| rig/animation | UPDATE/KEEP | channel/piece/KineFX/APEX 状态模型独立；APEX smoke 进入 reference，不新增动词 |
| skill governance | UPDATE/KEEP | 管理证据与生命周期，不替代领域知识；新增真实跨版本 GOV-002 行为案例 |

没有 SPLIT、MERGE、DEPRECATE 或新 skill。COP/SIM/project-analysis 仍未达到 M2 准入门。

## 2. 触发正例与相邻反例

| Skill | Canonical positive | Counterexample / 应联用而非误触发 |
|---|---|---|
| trace | 用户要求复盘 session、漏用/误用/缺失工具、任务推进因果 | 普通建模任务不因产生 trace 就自动加载；只输出 delta proposal 不静默改 skill |
| SOP | Copy/Scatter/VEX/Sweep/Merge/属性/局部退化/普通时间变形 | 最终 Karma 网络归 Solaris；绑定状态模型归 rig；二者可先联用 SOP 完成源数据门 |
| Solaris | MaterialX/Karma CPU-XPU/USD binding/RenderSettings/AOV/USD Render ROP | 快速 SOP 检查仍用 SOP `render_view`；普通 COP 图像处理尚不由 Solaris skill 吞并 |
| rig | keys、刚体序列、机械层级、capture/deform、FK/IK/APEX controls | 静态 SOP 不加载；simulation solver/cache 不能用 keyframe/rig 完成门替代 |
| governance | 创建/审查/更新/拆并/发布 bundled skills，多来源证据吸收 | 普通内容制作和只读 trace 分析不授权生产 skill 修改 |

相邻领域重叠均有明确联用顺序，未发现真实 trace 中因 skill 名称造成的反复误路由，故不合并。

## 3. 版本 claim 审计

| Claim | H21.0.440 | H22.0.368 | 当前边界 |
|---|---|---|---|
| channel / keyframe frame units | regression pass | regression pass | `set_keyframes` 仅负责 channel 数据 |
| rigid R→U ordered state | 6/6 | 6/6 | 不外推所有机械 rig |
| KineFX Joint Deform foundation | 7/7 | 7/7 | 不等于 animator-facing APEX rig |
| APEX Graph→Invoke Graph | 5/5 | 5/5 | 只证明 graph engine/binding/output/error，不证明 Animate State |
| scene/geometry verbs | 11/11 | 11/11 | GUI 专属行为另验 |
| Karma Setup / Material Builder | H21 GUI + ROP render pass | shelf entry confirmed | H22 完整 GUI recipe/状态恢复仍未验证 |
| render_view isolation | H21 GUI pass | 未验证 | 不把 H21 GUI 结果写成 H22 已通过 |

在线最新文档只提供概念参考；工具 id、fixture 路径和 GUI recipe 继续以目标版本
runtime、`$HFS/houdini/help`、shipped shelf/source 与最小实验为准。

## 4. 唯一维护位置与去重结论

- trace 量表拥有证据强度、工具机会、完成判定；domain skills 不复制完整审计协议。
- SOP 拥有通用几何/属性/Copy/局部退化；rig 只引用源 SOP 联用，不复制 SOP 手册。
- rig 拥有 channel/piece/skeleton/APEX 状态模型；trace 只保留审计判据和 HTA-017 证据。
- Solaris 拥有 USD/material/render delivery；SOP 只保留快速验证与 source 数据门。
- governance 拥有 evidence lifecycle、拆并准入、来源/隐私；不承载 APEX/Karma 操作 recipe。
- system guidance 只保留 skill dispatch、动词优先、视觉/状态硬边界，不加入本审计全文。

## 5. 本次最小变更

1. SOP 视觉门从“所有 SOP 必须 render_view 成功”窄化为视觉契约/可用环境才是视觉完成门；
   纯网络/数据交付允许诚实标注用户画面判断，不把语义完成伪装成视觉通过。
2. Solaris reference 记录 H21/H22 shelf entry 均存在，但 H22 完整 GUI recipe 未验证。
3. Rig reference 加入 SideFX fixture 的 H21/H22 APEX 输入、输出、错误和版本路径证据。
4. Governance eval 增加 GOV-002 跨版本行为用例；没有修改 evidence level 或授权边界。

没有采纳：新 APEX verb、APEX builder 自动化、COP/SIM 空壳 skill、五个 skill 合并、长官方
文档复制、OpenGL 开关/兼容设计。

## 6. 验证、证据等级与下一门

- 结构：项目治理 audit 为 5 skills / 5 registrations / 0 issue / 0 warning；各变更 skill 走
  `skill-creator` quick validation（Windows 下需 `PYTHONUTF8=1`）。
- 行为：H21/H22 APEX regression 各 5/5；launcher 11/11；Node client/trace tests 通过；
  build 保持 11 domains / 46 verbs。
- 发布态：新 session `session-83a553e7...` 为精确 `houdini` preset；skill catalog 含 5/5
  Houdini skills。agent 成功加载 rig skill、读取 APEX reference，只调用
  `skill ×1 + read ×1 + houdini_query ×1`，query 内 `scene_info + verb_help`；0 failure、raw
  mutation、rollback、advisory，最终明确拒绝把 APEX engine smoke 外推成完整 rig。
- 测试 session 完成后通过正式 `workspace.archiveSession` 归档；launcher 排除 archived id，
  WebView 恢复原用户 session，未直接删 session 文件或留下“测试会话成为默认入口”的副作用。
- forward trace 同时发现 HTA-019：result signature 内 `->` 使 greedy ledger regex 错切；已改为
  结构扫描并用该真实 session 回归，计数与完成判定不变、args/result 证据恢复准确。
- APEX shared graph contract：SideFX fixture + H21/H22 runtime 复现，E2；完整 character rig 仍 E0/E1。
- Solaris H22 entry existence：shipped shelf 双版本复核，E2；H22 GUI execution 仍未验证。
- SOP 视觉门修正：跨草地/动画 trace 与用户明确交付边界，作为既有规则冲突的窄修正。

下一验收：真实 channel、mechanical、KineFX/APEX 用户任务各产生新 trace，观察 activation、
首次正确状态、raw exemption、用户返工和完成门；没有重复易错裸代码前不扩词表。M2 仍从
真实 COP 三类任务开始，不预建 skill。

回滚：按 Git diff 分别回退三个 domain reference/entry 与 GOV-002；不删除整个 skills 目录，
不修改用户 preset 或 HIP。

## 7. 弱模型执行标准复审（2026-09-04）

同模型同提示的 KineFX 原题由 `7bf34ae9…` 的核心失败改善为 `975f49a0…` 的最终 rigid geometry
通过，证明“交付边界 + driver/binding/deliverable + 条件 fast path”能改变弱模型行为；但新 trace
仍有 20 failed calls，说明路线正确不等于执行足够高效。治理 quality standard 因此新增统一的
复杂度门、执行脊柱、fast path、探测阶梯、两次同边界失败换策略、证据失效和七类发布验收。

当前采用度不是简单的 pass/fail，而按领域列 backlog：

| Skill | 当前强项 | 相对新标准的缺口 | 状态 |
|---|---|---|---|
| rig/animation | 分类、三层交付、KineFX H21/H22 fast path、时序/最终几何门 | 未见层级刚体正例、control/channel/solver 反例；multiparm 与 node-help 工具缺口 | reference implementation / verified candidate |
| SOP | 质量合同、模块关系、扰动/恢复、新鲜证据、局部几何门 | 按数据模型整理 fast path、两次失败换策略、简单任务负担反例需复审 | pending standardization |
| Solaris/Karma | USD/material/render 分层、Tab setup、正式产物门 | H22 GUI fast path、诊断升级顺序、渲染超时转 job 的停止合同需复审 | pending standardization |
| trace analysis | 确定性 evidence、失败分类、反事实轨迹、证据等级 | 视觉失败后恢复和跨证据冲突需更结构化；不强套内容制作 fast path | audit-specialized / partial |
| skill governance | 来源、版本、反例、发布/回滚 | 新 §2 弱模型标准与 GOV-007 已补；需要用后续两个 domain update 验证治理本身 | canonical standard / candidate |

推进顺序：先用 rig 完成未见正例与反例，确认标准不只修原题；再按自然 trace 中的主要失败面依次
标准化 SOP、Solaris/Karma。不得为了表格全绿一次性给所有 entrypoint 复制通用段落；每个 domain
只加入会改变本领域决策的内容，并用自己的 fast path 和反例发布。

K3 未见正例 `db2cf0bf…` 进一步确认“简洁”不能等同只写建议：架构禁止项由主 skill 一条短 gate
表达，确定性阻断交给 verb。新增 `set_object_parent` 后，guidance 只说明 `connect` 是 dataflow，rig
entrypoint 只说明 KineFX 默认和 OBJ 例外，具体 parenting reason/回读放 §3.2；避免三层重复整段规则。
