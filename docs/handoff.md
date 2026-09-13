# 当前开发交接

核对日期：2026-09-13

只保留下一次开发所需的活动事项；完成对应移除条件即删除整项，不追加完成日志。
维护规则见[交接文档生命周期](development.md#交接文档生命周期)。实现版本以[工具设计](tool-design.md)为准，
本页不证明当前live已加载；不授权重启服务、修改用户HIP或发起收费测试。
更远的产品范围见[主要开发方向](development-directions.md)，不在这里复制路线图。

**执行计划与完成门**

本轮范围是H-01～H-08及修复发现的同链路缺陷，不扩成四大产品方向的全部远期功能。
每项按“最小反例/观察缺口→修复→正反例→真实路径验收→核销”推进；外部验收阻塞不阻止无依赖的本机研发。

| 顺序 | 事项 | 交付与依赖 |
|---|---|---|
| 1 / P0 | H-01 验收环境 | 明确源码/受管包/加载身份；准备隔离H21/H22与启动环境用例；异机、签名运维和live另取证 |
| 2 / P0 | H-02 控制异常 | 补连续参数/keys/frame/identity及GUI边界观察，先取得因果反例再修复，不用旧恢复测试核销 |
| 3 / P0 | H-03 执行与恢复 | 依次处理隔离执行、Manual/新鲜度、协作取消、持久身份、图片历史和断联回执；真实验收依赖H-01 |
| 4 / P1 | H-06 判据与接口 | 校准Trace正反例、表达式/节点诊断、参数UI与工具入口；未验证的语义和自然采用单列 |
| 5 / P1 | H-08 → H-04 意图与交付 | 准备信息不足/信息等价/中途变更/续跑用例，再验要求→控制→结构→恢复→复验；模型验收依赖H-01/H-06 |
| 6 / P1 | H-05 质量与成本 | H-04判据稳定后分别比较SOP与压缩策略，固定模型/版本/预算，报告质量、返工、问询与成本分布 |
| 7 / P2 | H-07 教学工程 | 获授权短片的音画核对、阶段复现、参数实验和重开验收；材料/云提交授权未到时保留缺口 |
| 8 / 收口 | 全链路代码与知识review | 修复后逐层审查安装→Host→Bridge→helpers→结果/图像→Trace→交付；发现缺陷回到对应H项复验 |

最终review核对重复实现/状态源、无调用代码、兼容入口真实消费者、异常吞没、权限/生命周期与文档冲突；不因名字旧或无人静态引用就删除兼容接口。
稳定结论原位同步docs/规则，生成区仅由生成器刷新；门禁覆盖docs:check、npm test、H21/H22相关HOM与包内容检查。
运行态未验证、缺授权/材料/异机证据必须保留pending；临时产物/分支清场先只读列候选，汇报后经用户确认才删除。

## 待交接事项

### H-01 部署更新改造与完整运行态验收

- 状态：待验证
- 现状：正式发行链已可用；部署/GUI验收驱动共用环境隔离，拒绝继承外部Houdini包、Python/Qt/DSH配置和模型凭据。另一台物理机器、自定义用户启动环境及模型路径仍待验收；H22 Qt helper按安装合同从bin启动，私钥备份与长期发布环境仍待维护者确认。
- 下一步：用户已授权将源码默认运行时切至DSH 0.1.5-rc.2并自行在Houdini验收；按[候选资格流程](dsh-update-compatibility.md#新-dsh-版本的资格流程)补H21/H22 WebView与发送/停止/重连、V3 Trace真实历史及签名组合验收。源码变更触发的benchmark指纹仍需明确授权重封，不能放宽门禁；不以preferred切换证明live已加载或正式发布，不自动迁移用户历史。确认私钥备份和长期发布运维；补异机/自定义启动目录及完整重开后的共用主面板、模式和高级诊断。获授权后验请求恢复、来源/工作流、新session/压缩恢复、原生/Code Mode图像，不以只读smoke核销模型与视觉。
- 移除条件：上述跨机/启动环境边界及获授权用户路径有证据，备份/长期发布运维责任明确；未测试的模型和驱动组合不被宣称为已验证，当前用户旧进程不冒充已加载发行版。
- 入口：[安装合同](setup.md)、[兼容验收](dsh-update-compatibility.md)、[安装器](../houdini/install.py)、[发布策略](../houdini/python3.11libs/dsh_release_policy.py)、[部署回归](development.md#4-回归与发布)、[WebView回归](../tools/tests/dsh-webview-navigation.test.py)、[Trace回归](../tools/tests/trace-view.test.mjs)。

### H-02 控制值发生未解释的变化（RT-01）

- 状态：待修复
- 现状：原主控轨迹已定位，曾提交的旧字段后续回读偏离；不是辐条/显示开关定位。历史记录缺连续参数/动画快照和GUI事件，当前OBJ主控设值→追加folder→独立失败/回滚→cook反例不能复现，仍未定因。
- 下一步：在H-01确认版本的新建测试场景逐边界回读参数、keys、frame及identity；异常首次出现时保留前后请求和GUI操作，区分同调用恢复与请求间变化。不能把恢复回归通过归为原异常已修复，也不能推定用户undo或编译刷新为原因。
- 移除条件：有因果明确的最小复现、修复及H21/H22正反例；若需GUI外部事件才能区分，先明确观察缺口。
- 入口：[控制实现](../houdini/python3.11libs/dsh_quality_contracts.py)、[执行观察](../houdini/python3.11libs/dsh_bridge.py)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)。

### H-03 超时与不确定请求恢复（RT-02）

- 状态：待修复
- 现状：exec/jobs已有同runtime回执；Manual/失败cook保留未知、不隐式重试；HDA与可信脚本作者检查器已有受限worker，支持新场景cook/cache/ROP及输入/结果/产物复核。现有场景移交隔离执行、live运行中取消、持久身份恢复和图片历史恢复仍未闭环。
- 下一步：新加载Host验正常首次绑定和旧错误会话续接；绑定必须在pre-step正常消息批次接受，工具期只flush，旧完整文本交换只追加摘要投影修正。再按[多实例与恢复](multi-instance.md)验Qt登记/单端Repair、共享Host启动/退出及续接；默认入口和live未切换。完善Save As预留、GUI/外部替换与恢复授权后再解除受管互斥。退出选择/崩溃暂停/检查点及跨进程身份恢复仍待实现，不因心跳超时杀Houdini、不重发代码、不凭tag认领。发布需授权重封surface并验收，不复制账号/会话；图片恢复保留原历史、不改node_modules。
- 移除条件：H-01所确认版本的真实路径可区分未执行/执行中/完成/仍未知，查回不重做修改、不重复计账；过期及无法恢复的情况如实报告，不能仅以隔离脚本通过核销。
- 入口：[Host传输](../src/bridge.ts)、[Bridge队列](../houdini/python3.11libs/dsh_bridge.py)、[执行状态测试](../tools/tests/execution-state.test.mjs)。

### H-04 原始要求与控制/结构验收（QA-01/05/06、RB-06）

- 状态：待验证
- 现状：来源锚、控制变化/覆盖摘要和接口/精确变换测量已有；模型仍可能用bbox或面数通过声称整体连接、均匀变换或全部控制正确。
- 下一步：新加载合同41验公共Output逐层发布、空Pack拒绝、独立HDA实例与默认/边界参数；核对“要求→控制→实际输出/关系→恢复→复验”。验证原生方法失败后的同层诊断、源码重建一致性及局部pass不外推全局；不新增第二份可写完成证书。回滚后原生初始化后代foreign的线索仍需隔离因果复现，不能以放宽ownership消除。
- 移除条件：默认与扰动关系反例能被自然任务发现，未满足核心要求不会被goal/todo完成覆盖；不能只靠固定脚本通过核销。
- 入口：[证据契约](execution-contract.md)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)、[变换反例](../tools/tests/dsh-modeling-identity.test.py)。

### H-05 聚焦模块与上下文成本（PL/IN/CX/EV）

- 状态：待验证
- 现状：整体代理→局部交付→集成复验已是SOP候选；局部漏件/实例脱离机制回归存在，但质量收益和上下文净成本未受控比较。
- 下一步：先作固定模型/工具版本/任务信息/预算/视角的旧新SOP单因素比较，包含简单编辑/单部件反例；另行隔离测结果压缩/状态摘要的净成本，不与SOP变化混测。记录质量、返工、问询负担及input/cache/output口径。
- 移除条件：重复的未见任务对照支持采用或明确放弃该候选；不能混入工具升级、加预算或不同车型后宣称收益，不自动启多作者。
- 入口：[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md)、[集成反例](../tools/tests/dsh-module-integration.test.py)、[任务来源](../src/task-sources.ts)。

### H-06 Trace判据与接口发现误差（QA-03、API、OBS）

- 状态：待验证
- 现状：公开UI与HDA实例/消费者/隔离加载链有正向证据，尺寸/Cd/BOM判据仍待自然采用。工具开发规范已区分工程目录/独立package/已有包授权、HDA修改层及运行态来源；完整package发现与加载验证未实现。H22预览已复核、H21不变；隔离GUI退出和临时目录ACL问题待诊断，不扩大权限。读图与声明仍需语义复核。
- 下一步：用H-01确认版本的新轨迹核对引用/诊断与参数UI自然触发；按[共享控制设计](parameter-controls.md)验先UI/后UI、真正窄面板和总控选参。HDA按[生命周期回归](../tools/tests/dsh-hda-lifecycle.test.py)扩展复杂嵌套/外部回调边界与未见自然任务，按[公共接口回归](../tools/tests/dsh-hda-public-contract.test.py)验新实例/多端口与实际控制关系；不维护某次trace资产，不将模型自然采用视为机制回归已证明。按[工具验收矩阵](../skills/houdini-tool-development/references/evidence-and-validation.md)补Shelf/快捷键；benchmark封存指纹不符须获重封授权，不降低门禁或宣称live已更新。
- 移除条件：正反例与已有轨迹回归不误判，不以启发式推导艺术正确性；精确API/表达式写入、求值、cook和效果边界清楚。
- 入口：[审计提取](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)、[工具接口](../src/tools.ts)。

### H-07 视频解析到教学工程的端到端验证

- 状态：待验证
- 现状：schema-2 notes已增加视频内对象/网络/面板上下文、逐项事实引用、跨包修正、缺口与参考图；草稿/显式迁移、多入口分页查询、局部取证和派生交接有源码入口，旧记录保持可读。像素候选仍会漏掉低幅操作，结构校验不证明语义；完整人工标注基线、DSH自然采用、未见视频和教学工程未验，不能因局部真实资料回读通过核销。Agent可见面变化触发封存指纹门，不能自动重封。
- 下一步：按[视频测试矩阵](../skills/houdini-video-tutorial/references/video-processing.md#维护验收)验新session未见视频：成品参考前置/覆盖、后段修正、低幅回查与对象身份；明确效果但缺参数时主动实验收敛，严格原值任务不被效果拟合替代。按[COP验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)验单元形态→整体→材质对照、较优候选恢复与重开；在新加载runtime验大依赖网络、H22原生材质连线及参数别名守卫的自然采用，不以隔离机制回归核销视觉/泛化。人工基线/新模型采用未验；旧资料副本核对，云提交/live修改及benchmark重封分别授权。
- 移除条件：当前候选的真实媒体/语义及最小教学工程验收有证据；更远能力继续留在开发方向，不扩成交接长清单。
- 入口：[视频当前范围](development-directions.md#教程转教学工程)、[解析脚本](../skills/houdini-video-tutorial/scripts/video_tutorial.py)、[离线回归](../tools/tests/video-tutorial.test.py)。

### H-08 意图形成、依赖计划与跨轮保留（IN-01/02/03、PL-01/02、EV-01）

- 状态：待验证
- 现状：原始材料、澄清和来源回读已有；Trace的retryWork.hostWork补充同文件写入、相同shell命令及无Houdini调用区间，弥补离线计算循环不可见。只观察重复，不推断停滞或自动中断。完整义务/依赖计划、摘要压缩和中途纠正仍缺受控行为证据。
- 下一步：新session验证停止规则候选：核心缺口可安全推进时继续，部分报告/保存不作停止许可；真实限制保留身份/未完成项/下一步，可选美化不无限续跑。系统上下文剩余量与自动续接尚未实现，不以模型自述预算充当系统证据。用短/信息完整/冗长等价任务加中途变更和压缩续跑作对照；先离线核对，收费模型另授权，不加默认长问卷或第二份需求账本。
- 移除条件：未见任务中短请求能形成合理边界且实际可调，多轮摘要不自行降级必需项，计划按依赖推进，重复失败有新增证据或换诊断方法；信息不足与信息等价分别评价，并报告问询与成本分布。
- 入口：[任务来源](../src/task-sources.ts)、[Houdini preset](../presets/houdini/agent.cordis.yml)、[SOP工作流](../skills/houdini-sop-workflow/SKILL.md)、[来源回归](../tools/tests/task-sources.test.mjs)。
