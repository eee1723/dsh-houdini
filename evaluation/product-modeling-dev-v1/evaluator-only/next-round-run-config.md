# 下一轮单作者产品模型试验配置（评审侧）

本配置用于三件事：定位执行中断与最终工程缺失、核对最终报告是否对应真实交付、在另一构造类别上做单作者对照。它是评审侧运行记录的模板，不发给建模作者；公开题与评审答案继续按 [评审协议](../REVIEW_PROTOCOL.md) 隔离。只有下表的待锁项填完、A/B 各自的实际加载身份与预锁版本吻合后，才启动对照。源码提交、构建成功或旧会话截图都不能代替加载身份。

## 开跑前冻结

| 项目 | 锁定值或必须填写的值 |
|---|---|
| 对照任务 | `hand-crank-reel-build`。它是卷筒、转轴和传动构造，未用于本轮铰链孔径与交付报告修复；属于**已公开开发题上的迁移**，不宣称未见题泛化。 |
| 输入 | 仅由 `prepare-run.mjs` 给作者 `brief.md` 和 `task.json`；本题没有附件。当前 Windows 检出字节的 `brief.md` SHA-256 为 `a43131feb5c3ef167b280aab31d5338181e06a24d6dda293342bc577f98efa0a`，测试集 `manifest.json` 为 `a27e0ce3ef300fd80130a7843890b0c3ce5051e56c24b15857d593f8d06c9600`；Git blob 分别为 `4980f743d883cc70e025008a13ff7c996f8757c5` 和 `cd684fbbcff30d74c2bea3f414fae7878cf84fce`。不同换行检出的文件 SHA 可能不同，但两臂 `task.json` 中每件输入的 SHA 必须逐字一致，否则停跑。澄清答复若有，必须在首跑前逐字登记，两臂相同。 |
| A / 基线源码 | `174f51562bd83bf41e8a9fca563c5889cd663be8`。这是本配置写成时的源码提交，不代表任何 Houdini 进程已加载它。 |
| B / 候选源码 | `e5754bd1f7318938f1657ad3851ebe2b77ab41cf`。候选 checkout 须干净；开跑前另记构建产物摘要及实际加载身份，不得在对照中途修改。此提交含预览撤销修复、交付审计和最终堵孔反例。 |
| 作者 | 单作者；DeepSeek V4 Flash、`high`。开跑前记录 API 暴露的完整模型/部署标识；若服务只暴露商品名，则如实记“后端修订未知”，不能称精确权重版本固定。 |
| 环境 | 隔离 Houdini 21.0.440、DSH 0.1.6-alpha.2；每 run 总墙钟上限 40 分钟，worker 4 线程/8 GB。开跑前记录 Houdini 可执行文件路径与摘要、DSH 可执行入口/包版本、插件根目录与提交/内容摘要、Host/Bridge/helper 诊断版本和 runtime ID；任一实际加载身份不符则暂停该臂。H22 与用户 live 另行验收。 |
| 预算与干预 | 两臂同一总时限、同一模型配额/工具权限、同一提示和文件范围；不加作者、不给评审清单、不在运行中手改 HIP。每次记录输入/输出 token、费用（若可得）、原始工具调用数、Houdini 调用数、模型等待、Houdini 执行和总耗时。未知成本写未知。 |
| 评审 | 使用本题冻结的 [`checklist.json`](../cases/hand-crank-reel-build/evaluator-only/checklist.json) 和下方重开步骤。整体视图固定为 1280×720、正交、`iso` 方向、`coverage=0.82`；先从三状态最终输出的世界包围盒并集计算共同取景与深度包络，三图复用同一相机/包络。孔道按支架和卷筒实际板厚分别取覆盖入口到出口的轴向区间；近景固定拍两侧支架孔口、卷筒中心、曲柄接轴及握柄。缺少可定位的实体组或孔口时记 `unverified`，不改用作者自述位置。评审先看来源和独立成品，再看作者结论。 |

先各跑一条 A、B。若 B 有最终可重开 HIP，至少一项核心关系改善，其他核心项无退步，且总 token/费用（可得时）和总耗时均未比 A 增加超过 25%，再各追加两条，执行顺序预先定为 `A1,B1,B2,A2,A3,B3`。首轮无改善或出现新失败，就保留结果并回到原因分析；重试是新 run，不能替换失败 run。两臂产物和评审条件在全部运行前冻结，临时调整另立实验条件。

## 每个 run 的准备与产物

评审者先运行：

```text
node evaluation/product-modeling-dev-v1/scripts/validate.mjs
node evaluation/product-modeling-dev-v1/scripts/prepare-run.mjs --case hand-crank-reel-build --out <仓库外绝对路径>/<run-id>/task
```

每个 `run-id` 新建目录，不复用工作区；作者只可读其 `task/` 中的公开内容。评审侧另存 `lock.json`，至少含上表逐项值、条件 A/B、重复序号、UTC 开始时间、全部输入文件 SHA-256 和实际加载身份。对照开始后不得编辑 `lock.json`；勘误另记，保留原字节。输出至少收齐：

| 目录/文件 | 内容 |
|---|---|
| `task/` | 准备脚本原样生成的公开输入及 `task.json`。 |
| `raw/` | 原始会话轨迹、每次请求/回执、Host/Bridge/worker 日志、进程启动退出时间及退出码、Houdini 崩溃报告或“未生成”记录。原始失败不筛掉。 |
| `author/` | 作者最终原文、图片及其生成时间、显式保存得到的 `final.hip`（若存在）；每件计算 SHA-256。 |
| `checkpoints/` | 自动或手动检查点，逐件标明产生时刻与用途；不能改名冒充最终 HIP。 |
| `review/` | 从 `final.hip` 副本独立重开的诊断、固定取景图片、几何/控制测量、来源核对、逐项 `review-result.json`；无最终 HIP 时保存“无法重开”的记录。 |
| `run-result.json` | 结束时间、阶段与结果、预算消耗、最终 HIP 路径/摘要/保存回执/重开结果、首个失败、后续失败、所有未结算请求、作者声明与评审结论。 |

`run-result.json` 的阶段从 `prepare`、`launch`、`model`、`render`、`verify`、`save`、`reopen`、`report` 中选；结果分别记录 `timeout`、`process_exit`、`unknown_request`、`save_failure`、`reopen_failure`、`completed`，允许同一 run 同时有多种失败。记录首个失败时间、最后一条成功回执和最后一次 scene mutation。若返回 `unknown_transport`，保存 `request_ref` 与 `runtime_id`，仅用 `houdini_query(request_ref=...)` 查回；查回仍未知就保留未知，不重发修改调用。进程退出和超时分别记，不能由超时推断 Houdini 崩溃，也不能由 `final.hip` 缺失推断保存曾被调用。

`final.hip` 只有在目标路径、保存成功回执和文件摘要齐全时才算提交候选；独立重开成功才算交付成功。没有它时，结构、操作关系和报告一致性记 `unverified` 或明确失败，不能用检查点、作者截图或局部输出补算。每次后续修改都会使该修改前的结构/控制检查失效；逐项记录检查所指向的输出、参数状态、文件摘要或最终修改序号。旧证据只供诊断，不作为最终验收。

## 独立重开与判定

在新的隔离 Houdini 进程中只打开 `final.hip` 的评审副本，不修改作者原件。先确认文件摘要、HIP Unit Length、最终公共输出、cook 状态和物理尺寸。记录主控原值，再设 0°、90°、180°；从三次最终输出的世界包围盒求共同取景与深度包络，使用上表固定相机条件拍三张整体图，最后恢复原值并重新测量。取两侧支架孔口、卷筒中心、曲柄接轴及握柄近景，记录每张局部图的坐标范围与相机参数；若输出缺件，不移动镜头寻找作者未交付的替身。分别在支架和卷筒完整实体组上检查孔径空域、轴线和转轴实体占据，轴向区间须覆盖各自真实入口到出口；整件 bbox 不替代板厚。核对固定件不漂移、随动件连接且恢复精确。近景出现 OpenGL 锯齿时，结合可重复取景、最终几何与另一显示/渲染证据复核，不单凭截图判破面。

评审者依据公开要求核对单位、部件数量和尺寸归属，再逐项填 `pass`、`fail`、`unverified`；原图事实、推测和未知分开写。作者报告每条主张要对齐最终交付、最后有效检查及未验证项。保存后在评审侧运行：

```text
node evaluation/product-modeling-dev-v1/scripts/validate-review.mjs <run-id>/review/review-result.json
```

主结果只报告四项：最终 HIP 是否成功交付、核心结构、参数操作后关系、报告与成品一致性。每项给证据和覆盖范围；调用数、耗时与费用单列。首轮和追加运行全部入分母，分别列出失败原因及未知，不以成功重跑覆盖崩溃或无最终 HIP 的首次运行。已公开题上的改善只能说明这类开发条件有迁移迹象；进一步泛化需封存的未见来源和独立预锁评审。

对应入口：[`prepare-run.mjs`](../scripts/prepare-run.mjs)、[`validate-review.mjs`](../scripts/validate-review.mjs)、[评审协议](../REVIEW_PROTOCOL.md)。本配置只准备隔离试验，不授权重启用户 live、修改原 HIP 或部署发行包。
