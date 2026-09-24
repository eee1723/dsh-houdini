# 当前开发交接

核对日期：2026-09-23

只保留下一次开发所需的活动事项；完成对应移除条件即删除整项，不追加完成日志。
维护规则见[交接文档生命周期](development.md#交接文档生命周期)。实现版本以[工具设计](tool-design.md)为准，
本页不证明当前live已加载；不授权重启服务、修改用户HIP或发起收费测试。
更远的产品范围见[主要开发方向](development-directions.md)，不在这里复制路线图。

**执行计划与完成门**

当前主线是程序化产品模型质量：先用独立开发评测定位“理解图纸、建模、看图修正、交付判断”哪一段失效，再修对应H项。其他方向保留原有验证缺口，不扩成全部远期功能。
每项按“最小反例/观察缺口→修复→正反例→真实路径验收→核销”推进；外部验收阻塞不阻止无依赖的本机研发。

| 顺序 | 事项 | 交付与依赖 |
|---|---|---|
| 1 / P0 | 产品模型开发评测 | 建立独立案例与公开/评审材料分离；先做图纸理解、给定清单建模、只读局部评审、限时细节组件四类对照；真实模型运行另取证 |
| 2 / P0 | H-01 验收环境 | 明确源码/受管包/加载身份；准备隔离H21/H22与启动环境用例；异机、签名运维和live另取证 |
| 3 / P0 | H-08 → H-04 → H-06 产品质量 | 根据评测失效阶段修要求提取、实体连接、局部视觉和最终报告；模型验收依赖H-01确认的运行版本 |
| 4 / P1 | H-02 / H-03 执行可靠性 | 控制漂移取得因果反例；隔离执行、恢复、图片历史和断联回执按真实路径验收，不把机制回归当模型质量 |
| 5 / P1 | H-05 组件协作与成本 | 先无模型节点片段往返；是否提升细节质量需固定总预算与单作者对照，不以多作者数量为成果 |
| 6 / P2 | H-07 教学工程 | 获授权短片的音画核对、阶段复现、参数实验和重开验收；材料/云提交授权未到时保留缺口 |
| 7 / 收口 | 全链路代码与知识review | 修复后逐层审查安装→Host→Bridge→helpers→结果/图像→Trace→交付；发现缺陷回到对应H项复验 |

最终review核对重复状态、消费者、异常吞没、权限/生命周期及文档冲突；退役接口先核对消费者与替代路径，历史只留Git。
稳定结论原位同步docs/规则，生成区仅由生成器刷新；门禁覆盖docs:check、npm test、H21/H22相关HOM与包内容检查。
运行态未验证、缺授权/材料/异机证据必须保留pending；临时产物/分支清场先只读列候选，汇报后经用户确认才删除。

## 待交接事项

### H-01 部署更新改造与完整运行态验收

- 状态：待验证
- 现状：源码锁定DSH 0.1.6-alpha.2；打包API/preset、独立Host/RPC及H21/H22隔离GUI交付卡片、图片/文本预览、HIP卡片和先初始化WebEngine反例通过。未重启live或证明签名发行、异机启动和模型路径；私钥备份与长期运维责任未定。
- 下一步：按[候选资格流程](dsh-update-compatibility.md#新-dsh-版本的资格流程)补H21/H22 live WebView发送/停止/重连、V3 Trace、插件实时禁用/重载及签名组合；把弃用的同步Session历史读取逐域迁至projection。再验异机启动、主面板/诊断、请求恢复、来源/工作流、压缩恢复和原生/Code Mode图像；live确认交付卡片与Explorer源文件定位。preferred与隔离smoke均不证明live已加载、正式发布、历史迁移或视觉正确；live重载后复核无票据及Job跨会话拒绝。
- 移除条件：上述跨机/启动环境边界及获授权用户路径有证据，备份/长期发布运维责任明确；未测试的模型和驱动组合不被宣称为已验证，当前用户旧进程不冒充已加载发行版。
- 入口：[安装合同](setup.md)、[兼容验收](dsh-update-compatibility.md)、[安装器](../houdini/install.py)、[发布策略](../houdini/python3.11libs/dsh_release_policy.py)、[部署回归](development.md#4-回归与发布)、[WebView回归](../tools/tests/dsh-webview-navigation.test.py)、[Trace回归](../tools/tests/trace-view.test.mjs)。

### H-02 控制值发生未解释的变化（RT-01）

- 状态：待修复
- 现状：原主控轨迹已定位，曾提交的旧字段后续回读偏离；历史记录缺连续参数/动画快照和GUI事件，当前OBJ主控设值→追加folder→独立失败/回滚→cook反例不能复现，仍未定因。
- 下一步：在H-01确认版本的新建测试场景逐边界回读参数、keys、frame及identity；异常首次出现时保留前后请求和GUI操作，区分同调用恢复与请求间变化。不能把恢复回归通过归为原异常已修复，也不能推定用户undo或编译刷新为原因。
- 移除条件：有因果明确的最小复现、修复及H21/H22正反例；若需GUI外部事件才能区分，先明确观察缺口。
- 入口：[控制实现](../houdini/python3.11libs/dsh_quality_contracts.py)、[执行观察](../houdini/python3.11libs/dsh_bridge.py)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)。

### H-03 超时与不确定请求恢复（RT-02）

- 状态：待修复
- 现状：exec/jobs已有同runtime回执；Manual/失败cook保留未知、不隐式重试；HDA与可信脚本作者检查器已有受限worker，支持新场景cook/cache/ROP及输入/结果/产物复核。现有场景移交隔离执行、live运行中取消、持久身份恢复和图片历史恢复仍未闭环。
- 下一步：新加载Host验正常首次绑定和旧错误会话续接；绑定必须在pre-step正常消息批次接受，工具期只flush，旧完整文本交换只追加摘要投影修正。再按[多实例与恢复](multi-instance.md)验Qt登记/单端Repair、共享Host启动/退出及续接；默认入口和live未切换。完善Save As预留、GUI/外部替换与恢复授权后再解除受管互斥。退出选择/崩溃暂停/检查点及跨进程身份恢复仍待实现，不因心跳超时杀Houdini、不重发代码、不凭tag认领。发布仍须真实路径验收，不复制账号/会话；图片恢复保留原历史、不改node_modules。
- 移除条件：H-01所确认版本的真实路径可区分未执行/执行中/完成/仍未知，查回不重做修改、不重复计账；过期及无法恢复的情况如实报告，不能仅以隔离脚本通过核销。
- 入口：[Host传输](../src/bridge.ts)、[Bridge队列](../houdini/python3.11libs/dsh_bridge.py)、[执行状态测试](../tools/tests/execution-state.test.mjs)。

### H-04 原始要求与控制/结构验收（QA-01/05/06、RB-06）

- 状态：待验证
- 现状：来源锚、控制/接口测量已有；模型仍会用bbox/面数外推整体关系。置物架暴露职责混杂、无稳定根输出、绝对引用、假失败及H21 PolyBevel guide崩溃。后续装配已采用同层模块、`OUT_<MODULE>`/`OUT_ASSET`与相对依赖，却把Z当世界高度并用`min Z=0`误证接地。现已补原生Y-up起模、旧工程根输出前适配、逐足世界接地、part观察色及一层组件容器→角色小框；叶子handoff与组件布局分层，H21/H22 GUI已验父子框、undo和保存重开。既有HIP只证明局部回归。
- 下一步：新加载合同用未见Y-up装配任务验世界轴、稳定输出、组件/角色两层布局、连接件归属和相对依赖；仅在端口稳定、独立复用/替换/组件作者或用户明确层级时采用Subnet。公开仪器箱同题复跑已自然采用一个密封接口并如实披露锁扣/铰链未测，说明关系提示被消费；但逐部件零重复面后未查整件，独立重开在密封条与两片箱壳之间发现40处完全重合面。下一轮验整件无group检查、风险定位与未测项报告，开放端口反例仍未验；不能把机制回归或规则文字当能力提升。继续验公共Output、空Pack、HDA实例及“要求→控制→关系→恢复→复验”；继续约简原复杂工程的PolyBevel附加崩溃条件。局部pass不外推全局。
- 移除条件：默认与扰动关系反例能被自然任务发现，未满足核心要求不会被goal/todo完成覆盖；不能只靠固定脚本通过核销。
- 入口：[证据契约](execution-contract.md)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)、[变换反例](../tools/tests/dsh-modeling-identity.test.py)。

### H-05 组件协作与质量成本（PL/IN/CX/EV）

- 状态：待验证
- 现状：候选component-host已接原生可续跑子任务、独立worker和pre-step绑定；单个Open Workspace菜单：仅新开已保存HIP且无自有前端时显式选Component preview，普通为默认；普通/受管运行时尚未合并，live正式加载未验。首次预览的独立Python/当前Houdini路径可确定时自动采用；CLI只信显式候选，live首次配置未验，现有live Host不随源码编辑自动加载新策略。预览在绑定HIP目录建dsh-components，主子可互访文件，不声称文件系统隔离；文件工具反例要求工作区不在平台TEMP（DSH共同可写例外），组件要求workspace-write并禁shell/再委派。机制见[组件协作](component-collaboration.md)；Host在父简报前注入权威workspace/HIP并返回同一字段；上游cwd候选固定于eee1723/deepseek-harness的codex/component-child-preparation@02f873ac，本机已构建该修订CLI；未安装/发布，官方原版有零子模型执行拒绝反例。自然任务已暴露两类集成失败：test21跑通委派/片段交换但轴向错误、穿板、绝对Object Merge引用与遗留warning/probe致质量门失败；test22控制正向收敛但父作者未读协作reference、自行升级HDA并裸install，受管交换零采用；临时装配预览因Object Merge未保留OBJ变换显示轮子穿板并带wheel_id mismatch warning——数值场景与视觉proxy须分别验同一数据流。
- 下一步：跨机接续须从上游cwd候选固定修订构建，本仓库源码分支/构建产物/官方DSH发行线均不能替代；升级基线是独立资格重验，不随普通开发rebase。用新加载skill复验未见两组件任务：父作者先读协作reference，默认普通subnet→component_export→hash/revision→component_import→槽位接纳，不得自行升级HDA或裸安装；HDA交付任务作反例。集成输出须同坐标系实测关系，跨OBJ代理显式保留world变换，proxy bbox与源world bbox一致且warning-free后才可读图；颜色自述与像素不符、Trace无独立语义识图记录，视觉结论须人工对照原图。继续验异常worker展示、局部图、公共控制、输入/外部依赖与手改/消费者迁移、迁移表达式/keys、修订失效、GUI双worker渲染互斥；Host中断后旧session受管恢复仍需带checkpoint hash/session ownership的executor恢复协议，不能靠重绑或认领既有节点。未见要求变化与同信息单作者对照按C5固定模型/版本/信息/质量门进行，不以并行数量或单一墙钟证明收益。
- 移除条件：C1～C4在隔离H21/H22与获授权真实路径完成；C5以固定模型/版本/信息/总预算比较整体单作者、聚焦单作者与独立多作者，覆盖简单任务反例，报告主子总成本/质量/返工分布并明确采用范围。压缩策略另测；不以加预算或子作者自评核销。
- 入口：[组件协作与完成门](component-collaboration.md)、[执行端路由](../src/executor-routing.ts)、[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md)、[集成反例](../tools/tests/dsh-module-integration.test.py)。

### H-06 Trace判据与接口发现误差（QA-03、API、OBS）

- 状态：待验证
- 现状：公开UI/HDA隔离链有正向证据，尺寸/Cd/BOM仍待自然采用；完整package发现未实现。H22预览已复核，H21不变；隔离GUI退出/临时目录ACL待诊断。test22误判已窄修；test32关系探针冲突可提取；中文“程序化+关系保持+网络清楚”现会进入qualityLoop。原生图附件与语义inspection仍须分开，无地面参照不能证明世界姿态。
- 下一步：用H-01确认版本的新轨迹核对引用/诊断与参数UI自然触发；按[共享控制设计](parameter-controls.md)验先UI/后UI、真正窄面板和总控选参。新session另验默认低成本预览/原生读图、普通HIP交付及显式HDA对照；domain/接口返回/原生身份接续的自然采用与live仍待验。HDA按[生命周期回归](../tools/tests/dsh-hda-lifecycle.test.py)扩展复杂嵌套/外部回调边界与未见自然任务，按[公共接口回归](../tools/tests/dsh-hda-public-contract.test.py)验新实例/多端口与实际控制关系；不维护某次trace资产，不将模型自然采用视为机制回归已证明。按[工具验收矩阵](../skills/houdini-tool-development/references/evidence-and-validation.md)补Shelf/快捷键；产品模型的局部视觉和报告真实性用[开发评测](benchmark-design.md)单独验，不宣称live已更新。
- 移除条件：正反例与已有轨迹回归不误判，不以启发式推导艺术正确性；精确API/表达式写入、求值、cook和效果边界清楚。
- 入口：[审计提取](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)、[工具接口](../src/tools.ts)。

### H-07 视频解析到教学工程的端到端验证

- 状态：待验证
- 现状：schema-2 notes已增加视频内对象/网络/面板上下文、逐项事实引用、跨包修正、缺口与参考图；草稿/显式迁移、多入口分页查询、局部取证和派生交接有源码入口，旧记录保持可读。像素候选仍会漏掉低幅操作，结构校验不证明语义；完整人工标注基线、DSH自然采用、未见视频和教学工程未验，不能因局部真实资料回读通过核销。
- 下一步：按[视频测试矩阵](../skills/houdini-video-tutorial/references/video-processing.md#维护验收)验新session未见视频：成品参考前置/覆盖、后段修正、低幅回查与对象身份；明确效果但缺参数时主动实验收敛，严格原值任务不被效果拟合替代。按[COP验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)验单元形态→整体→材质对照、较优候选恢复与重开；在新加载runtime验大依赖网络、H22原生材质连线及参数别名守卫的自然采用，不以隔离机制回归核销视觉/泛化。人工基线/新模型采用未验；旧资料副本核对，云提交与live修改分别授权。
- 移除条件：当前候选的真实媒体/语义及最小教学工程验收有证据；更远能力继续留在开发方向，不扩成交接长清单。
- 入口：[视频当前范围](development-directions.md#教程转教学工程)、[解析脚本](../skills/houdini-video-tutorial/scripts/video_tutorial.py)、[离线回归](../tools/tests/video-tutorial.test.py)。

### H-08 意图形成、依赖计划与跨轮保留（IN-01/02/03、PL-01/02、EV-01）

- 状态：待验证
- 现状：原始材料、澄清和来源回读已有；Trace的retryWork.hostWork补充同文件写入、相同shell命令及无Houdini调用区间，弥补离线计算循环不可见。只观察重复，不推断停滞或自动中断。完整义务/依赖计划、摘要压缩和中途纠正仍缺受控行为证据。
- 下一步：新session验证停止规则候选：核心缺口可安全推进时继续，部分报告/保存不作停止许可；真实限制保留身份/未完成项/下一步，可选美化不无限续跑。系统上下文剩余量与自动续接尚未实现，不以模型自述预算充当系统证据。用短/信息完整/冗长等价任务加中途变更和压缩续跑作对照；先离线核对，收费模型另授权，不加默认长问卷或第二份需求账本。
- 移除条件：未见任务中短请求能形成合理边界且实际可调，多轮摘要不自行降级必需项，计划按依赖推进，重复失败有新增证据或换诊断方法；信息不足与信息等价分别评价，并报告问询与成本分布。
- 入口：[任务来源](../src/task-sources.ts)、[Houdini preset](../presets/houdini/agent.cordis.yml)、[SOP工作流](../skills/houdini-sop-workflow/SKILL.md)、[来源回归](../tools/tests/task-sources.test.mjs)。
