# Houdini skills 长期维护生命周期

## 1. 状态模型

```text
observation
  → candidate
    → accepted
      → verified
        → released
candidate/accepted → rejected
released → superseded → deprecated → removed
```

- `observation`：原始事实，尚未决定是否属于 skill。
- `candidate`：目标 skill、规则和验收已提出；不得写成硬规则。
- `accepted`：证据门和设计评审通过，可实施。
- `verified`：结构、行为、版本和反例测试通过。
- `released`：已注册、打包、部署，并由新 session 确认曝光/触发。
- `superseded/deprecated`：替代已存在，保留迁移期。
- `removed`：调用者、注册、资源和文档已迁移，且删除门通过。

Git 历史是本地 skill 的版本与回滚基础；OpenAI hosted Skills API 另有 immutable versions，
但 dsh-houdini 当前不依赖远程 Skill API，不要混用发布状态。

## 2. 事件驱动维护

### 每个符合条件的 trace 后

- 生成 skill delta proposal；
- 检查是 activation、知识、工具还是验证层问题；
- 更新 known pattern 的证据等级；
- 只有当前任务明确授权且达到准入门时才修改 skill。

### 每次用户提供视频/工程后

- 先走 provenance/隐私/版本记录；
- 提取候选 claim 和反例；
- 不直接发布，安排官方/本机/独立任务复核。

### 每次 Houdini major/minor 或 Python ABI 更新

- 审查 domain skill 的关键 node/tool/context claim；
- 对 H21/H22 等受支持矩阵运行 discovery 与最小基准；
- 更新版本差异，不为了最新版本破坏旧基线；
- 未验证的版本明确标 unsupported/untested。

### 每次发布前

1. 运行治理 audit、目标 skill quick validation 和 build；
2. 检查注册/打包资源；
3. 跑每个变更 skill 的 canonical positive + counterexample；
4. 若变更来自 benchmark，另跑未见同族实例，并确认 agent-visible surfaces 没有泄漏实例标识、
   对象配方、目标参数或评分答案；
5. 检查 system guidance 重复和 skill description 冲突；
6. 新 session 验证 catalog、implicit activation 与资源可读；
7. development 记录实际状态、测试和回滚点。

### 定期健康审查

以事件为主，时间为兜底。建议每季度或积累 10 个新 Houdini traces 后做一次：

- 来源链接/版本是否过期；
- description 误触发/漏触发；
- SKILL.md 是否被不断追加而失去路由作用；
- reference 是否孤儿、重复或无调用；
- 三个以上任务中是否出现稳定 split/merge/deprecate 证据；
- 支持版本与真实测试是否一致。

## 3. 健康指标

不要用 skill 字数或数量单独评价质量。按 trace 观察：

- activation precision：不相关任务是否误加载；
- activation recall：相关任务是否及时加载；
- 首次正确模块/状态所需时间和调用数；
- 用户纠正次数；
- 硬失败、rollback、raw-hou exemptions；
- 已有能力 MISSED vs 真实 MISSING；
- warning/error 与完成门覆盖；
- 视觉/数值证据冲突是否诚实裁决；
- H21/H22 行为差异；
- skill 间重复规则和选择错误。

指标用于定位原因，不作为机械 KPI。例如加载次数低可能只是领域不适用，不支持删除。

## 4. 自进化安全门

- ordinary task 不得悄悄修改 skill；修改生产知识是独立外部副作用，需要当前任务授权。
- trace analyzer 可以自动生成候选，不得绕过 governance 直接把 E1 写成强规则。
- domain skill 不直接修改其他 skill；它报告 evidence/delta，由治理 skill协调唯一维护位置。
- governance skill 不自证自己的改动。修改自身需用户明确授权，并至少满足：跨两个领域重复问题、
  可复现流程缺陷，或官方 skill 规范变化 + 本地验证。
- 所有变更保持最小、可 diff、可回滚；大重构分 checkpoint，不一次改完所有 skills。
- 发现冲突时允许 NO_CHANGE、REJECT 或降级旧规则；演化不是只增不减。

## 5. 长期路线

### M0：治理地基

- 发布本治理 skill；
- 确定性 inventory/registration/reference audit；
- trace skill 在“用户要求更新 skills”时路由治理 skill；
- 文档登记 evidence levels 和变更状态。

### M1：当前五类 skills 标准化

- 审查 trace、SOP、Solaris/Karma、rig/animation、governance 的 trigger、结构、来源与完成门；
- 消除跨文件重复，建立 canonical positive/counterexample；
- 给关键版本 claim 补 H21/H22 状态。

### M2：新领域准入

- COP：至少覆盖图像生成/处理、材质或纹理接口、缓存/颜色空间/输出三个真实任务；
- SIM：至少覆盖 solver setup、缓存、时间/随机性、长 job/取消、交付验证；
- project analysis：至少覆盖普通 HIP、缺依赖 HIP、HDA/外部缓存工程的只读边界；
- 达到准入再建 skill，不预建空壳目录。

### M3：持续知识刷新

- Houdini 版本事件触发官方文档 + 本机帮助 + runtime 三角复核；
- trace/video/project 形成候选队列；
- 发布前 eval matrix 和新 session activation 检查；
- 基于 S3 证据做 split/merge/deprecation，控制 skill 数量和 prompt 暴露成本。

## 6. 回滚

每次发布记录：修改文件、来源、证据等级、验证命令、支持版本和已知反例。回滚优先恢复上一个
通过验证的 Git revision；不要用删除整个 `skills/`、覆盖用户工作区或重建无关文件的方式回滚。
如果已发布 description 导致严重误触发，先窄化 description/dispatch，再回退领域内容；如果
知识规则错误，保留反例和 rejected 记录，避免未来再次引入。
