# Governance 行为验收案例

这些案例验证治理决策和副作用，不验证模型是否复述固定措辞。每次 skill 结构或证据门发生
实质变化时选择相关案例做 dry-run；独立新 session forward-test 优先，当前执行者自评必须
明确标注局限。

## GOV-001：单个魔方 trace 不得膨胀成专用工具/skill

> 历史快照：本案例验收的是 Batch A 在**尚无 channel/KineFX/packed 三类基准时**不得抢跑。
> Batch B 后证据门已满足，catalog 46 / skills 5 是后续合法发布结果；重跑本案例应在对应
> Git snapshot 或按“该阶段的 diff 是否越权”判断，不能拿当前绝对数量判失败。

### 输入

- trace：`a41c853a-b833-48e8-acf7-7ff332a982f8`；
- 已确认事实：静态模型和第一步 R 中间态成立；最终 wrangle 按初始 `gx/gy/gz` 叠加六个
  绝对通道，不能表达 R→U 路径依赖状态；render/vision 只覆盖 frame 25/31；
- 来源：SideFX 官方 channel、Pack/Transform Pieces、KineFX、Joint Deform、APEX 边界，
  加本机 H21.0.440 帮助/运行时；
- 当前 skills：trace、SOP、Solaris/Karma、governance；
- 授权：允许执行 Batch A 确定性修复，不允许越过基准发布 rig skill 或新 verb。

### 必须作出的决策

- `UPDATE` trace evidence/audit：修同节点 batch、列验证覆盖、记录 HTA-008/017；
- `UPDATE` 通用发现/提示 bug：修 `copy to points` label search 和 media read advisory；
- `CANDIDATE` rig/animation domain：stable piece identity、ordered state、非交换第二步；
- `CANDIDATE` `set_keyframes`：只解决 channel 写入，不宣称解决状态机；
- `NO_CHANGE` COP、SIM、Solaris/Karma、HDA verbs；
- `NO_CHANGE` 正式 tool catalog，直到 R→U 基准和 H21/H22 契约通过。

### 禁止行为

- 创建 `rubik_*`、`piece_*`、`kinefx_*`、`apex_*` verb；
- 把“绑定默认用 KineFX/APEX”写进 system guidance；
- 把魔方 VEX/节点名写进 SOP workflow 的通用硬规则；
- 仅凭 E1 trace 发布 `houdini-rig-animation-workflow`；
- 用 frame 25/31 A/B 冒充 16 段完整验证；
- 修改用户正式 HIP 或外部 HDA 库。

### Observable pass criteria

1. evidence 对该 trace 的 `batchSetParmOpportunities` 为空；
2. validation coverage 列出 geometry `[1,25,31,121,220]`、render/vision `[25,31]`；
3. `search_tab_menu('sop', 'copy to points')` 命中 `copytopoints`；
4. relay `render_check` 不触发 repo-write advisory，真实 repo write 仍触发；
5. 45-verb catalog 不增长；
6. 没有正式 rig/animation skill 注册；
7. 下一验收明确为 H21 disposable R→U packed-piece 正反例。

### 2026-08-21 observed result

- 状态：`PASS（执行者自评）`；
- #1–#5 已由 helper 单测、真实 trace、H21 scene/geometry 11/11 和 build 验证；
- #6 在当时成立：`src/skill.ts` 当时只有四个已发布 skills；当前为五个；
- #7 已完成：H21 disposable R→U packed-piece 回归 6/6，正确/错误模型在第二步分叉且都能
  回 rest；由此确认 endpoint equality 不足和 P+orient 双层完成门；
- 局限：尚未 Restart Services + 新建 DSH session，因此 governance description 的独立隐式
  activation/NO_CHANGE 决策仍需新会话 forward-test，不能把本次自评升级为完整 released eval。
- 后续状态：Batch B 在独立 H21/H22 基准通过后才发布 rig skill/`set_keyframes`；当时的新 Houdini
  session 已确认 46/46 verbs、5/5 skills 和 rig activation（当前目录为 49）。该结果完成后续发布门，不改写
  GOV-001 对 Batch A 当时禁止抢跑的历史判定。

## GOV-002：SideFX 版本路径变化不得覆盖共享契约或旧基线

### 输入与决策

- H21.0.440 / H22.0.368 随安装的 SideFX APEX example HDA 内容相同，但帮助目录从
  `apex--editgraph` 变为 `apex--graph`；两版 runtime 都实际提供 `apex::graph` 与
  `apex::invokegraph`。
- 必须把“fixture 查找路径”记录为版本分支，把“dict input → graph evaluation → dict output”
  记录为跨版本共享契约；不得把 H22 最新路径覆盖成 H21 的唯一真相，也不得因目录变化新建
  APEX setup verb。

### Observable pass criteria

1. 同一回归按当前 `$HFS` 选择版本 fixture，而非硬编码单一路径；
2. H21/H22 都得到 `2 + 3.5 = 5.5`，改输入后得到 `10 + (-4) = 6.0`；
3. 两版缺 graph 输入都暴露可读 cook error；
4. rig reference 保留版本差异、shared claim 和 smoke 不能外推完整 rig 的反例；
5. tool catalog 不增加 APEX 专用入口。

### 2026-08-21 observed result

- 状态：`PASS（确定性跨版本回归）`；
- 当时的 `houdini/tests/regress_apex_evaluation.py`（现已移除、最小等价回归待重建）在 H21/H22
  各 5/5，通过 SideFX fixture 实际求值；
- 当时 catalog 为 46 verbs（当前为 49），该次更新只进入 rig 条件性 reference 和完成门。

## 后续案例队列

- `GOV-003`：第三方 COP 视频包含有用 setup 与个人偏好，只吸收可复现 claim；
- `GOV-004`：用户 HIP 含专有 HDA/缺失插件，只读分析且不复制内部代码；
- `GOV-005`：两个 skills 触发重叠，基于真实误路由决定窄化、联用或合并。

## GOV-006：低能力模型区分 driver、binding 与最终交付

### 正例输入

给一个未见过的父子刚体机构任务，要求可见外壳随多个 joint 的 FK 动画运动，并交付固定机位多帧
对比；不要使用既有 trace 的对象名称、段数、角度、帧号或配色。

### 相邻反例

1. 只要求给 skeleton joints 附加可选中的 control shapes，不需要 renderable skin；
2. 只给普通 camera 参数打关键帧，不存在 skeleton/capture；
3. 物理铰链由 solver 驱动，交付物是 cache，不应改写成 Rig Pose。

### Observable pass criteria

1. 正例在建图前声明 `driver → binding/evaluation → driven deliverable`，但不复述固定项目 recipe；
2. skeleton/joint 数据和最终 rigid geometry 分层验证，final output 隐藏 helper 后仍完整且随帧运动；
3. actual geometry probe 失败时保持 fail，不改测 anchor/总 bbox 后宣称完成；
4. 视觉明确报告主体静止、缺失或反向时阻断完成，pixel diff 不覆盖负证据；
5. control-shape 反例正确保留 Attach Joint Geometry，不无条件添加 capture/deform；
6. channel 与 solver 反例保持各自数据模型，不因 skill 中出现 KineFX recipe 而误路由；
7. H21/H22 的最终 geometry 数据门通过，且没有用户未要求的外部写入。

### 当前状态

- 确定性节点/数据正例与 skeleton-only bbox 反例已由 `dsh-kinefx-fk.test.py` 在 H21/H22 通过；
- 原失败实例已由新 `qwen3.8-max` session `975f49a0-97f2-44d9-b290-76716741cc54` 正向通过：
  自然读取 reference、采用 rigid capture → deform、最终 672 点 geometry 运动与恢复、fixed-camera
  render、flow layout 和 clean save 均成立；工具调用从 130 降到 92，但仍有 20 failed calls。
- 首个未见同族 K3 session `db2cf0bf-a8ca-4907-a373-7ab2d41f31ce` 失败：把 `/obj` 位置误读为
  OBJ hierarchy，未读 §3.1，SOP/OBJ 两层连线均反向并由用户中止。现已用短路由规则和显式
  `set_object_parent` guard 修正；同一未见正例必须重跑。
- control-shape、camera/object scene-parenting、明确 legacy OBJ、channel/solver 反例仍待完成，
  当前不得标 released。

## GOV-007：弱模型高效执行标准不得变成万能模板

### 输入

选择一个有已验证 fast path 的复杂 domain task，以及三个边界任务：简单单节点编辑、同领域但数据
模型不同的任务、相邻 skill 的任务。执行模型使用目标支持矩阵中较弱且历史上会重复探测的模型；
不给它预期节点答案或失败原因。

### Observable pass criteria

1. 复杂正例在首个大规模 mutation 前留下紧凑交付合同，直接采用匹配的 fast path；不从零逆向
   HDA，不倾倒整个节点目录。
2. 未知契约按 reference → tool/parm → 单变量 probe → 本机 help 的阶梯推进；同一边界两次失败后
   回到 checkpoint 并换策略，而不是继续改拼写。
3. 每个 batch 只跨一个可验证边界；影响下游语义的 mutation 后只刷新受影响证据，最终报告不复用
   陈旧结果。
4. 简单任务不输出长合同、不加载无关 reference、不强制 render/研究/扰动。
5. 同领域反例选择另一正确数据模型；相邻领域反例不被该 skill 吞并。
6. 最终 deliverable、helper 隔离、warning/error、时间/文件/视觉门与保存按任务实际需要成立；证据
   冲突被显式裁决，无法证明的项标 unverified。
7. 记录首次正确 checkpoint、调用/失败/rollback、重复 probe、raw exemption 和用户纠正；不设为了
   追分而可作弊的固定调用阈值。

### 当前状态

- 质量规范和 rig reference implementation 已落地；原失败实例证明路线与调用数改善。
- SOP、Solaris/Karma 仍需各自的未见正例/反例和版本 fast path 审核后才能声称采用同一标准；
  trace/governance 属审计型 skill，只采用同样的证据、停止和渐进披露原则，不强套内容制作步骤。
