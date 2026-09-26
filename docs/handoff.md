# 当前开发交接

核对日期：2026-09-26

只保留下一次开发所需的活动事项；完成对应移除条件即删除整项，不追加完成日志。
维护规则见[交接文档生命周期](development.md#交接文档生命周期)。实现版本以[工具设计](tool-design.md)为准，
本页不证明当前live已加载；不授权重启服务、修改用户HIP或发起收费测试。
更远的产品范围见[主要开发方向](development-directions.md)，不在这里复制路线图。

**执行计划与完成门**

当前主线是程序化产品模型质量：先用独立开发评测定位“理解图纸、建模、看图修正、交付判断”哪一段失效，再修对应H项。其他方向保留原有验证缺口，不扩成全部远期功能。
接续前读[评审侧阶段结论与可迁移证据索引](../evaluation/product-modeling-dev-v1/evaluator-only/stage-2026-09-26.md)；该记录不替代本页活动待办，也不向建模作者提供评审答案。
每项按“最小反例/观察缺口→修复→正反例→真实路径验收→核销”推进；外部验收阻塞不阻止无依赖的本机研发。

| 顺序 | 事项 | 交付与依赖 |
|---|---|---|
| 1 / P0 | 产品模型开发评测 | 保留12题公开开发/独立评审协议；输入对照后固定模型复测构造干预，再用厂家照片与尺寸图迁移；不把少量开发题当完整基准 |
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
- 现状：源码锁定DSH 0.1.6-alpha.2；打包API/preset、独立Host/RPC及H21/H22隔离GUI交付卡片、图片/文本预览、HIP卡片和先初始化WebEngine反例通过。隔离H21新会话已跑DeepSeek V4 Flash并保留原始轨迹/HIP；正常入口live、签名发行及异机仍未证实，私钥备份与长期运维责任未定。
- 下一步：按[候选资格流程](dsh-update-compatibility.md#新-dsh-版本的资格流程)补H21/H22 live WebView发送/停止/重连、V3 Trace、插件实时禁用/重载及签名组合；把弃用的同步Session历史读取逐域迁至projection。再验异机启动、主面板/诊断、请求恢复、来源/工作流、压缩恢复和原生/Code Mode图像；live确认交付卡片与Explorer源文件定位。preferred与隔离smoke均不证明live已加载、正式发布、历史迁移或视觉正确；live重载后复核无票据及Job跨会话拒绝。
- 移除条件：上述跨机/启动环境边界及获授权用户路径有证据，备份/长期发布运维责任明确；未测试的模型和驱动组合不被宣称为已验证，当前用户旧进程不冒充已加载发行版。
- 入口：[安装合同](setup.md)、[兼容验收](dsh-update-compatibility.md)、[安装器](../houdini/install.py)、[发布策略](../houdini/python3.11libs/dsh_release_policy.py)、[部署回归](development.md#4-回归与发布)、[WebView回归](../tools/tests/dsh-webview-navigation.test.py)、[Trace回归](../tools/tests/trace-view.test.mjs)。

### H-02 控制值发生未解释的变化（RT-01）

- 状态：待修复
- 现状：原主控偏移轨迹已定位，现有OBJ反例不能复现。新任务曾读到angle=61.1、base_w约13.4后恢复；缺连续GUI/写入证据，原因未定。
- 下一步：在H-01确认版本的新建测试场景逐边界回读参数、keys、frame及identity；异常首次出现时保留前后请求和GUI操作，区分同调用恢复与请求间变化。不能把恢复回归通过归为原异常已修复，也不能推定用户undo或编译刷新为原因。
- 移除条件：有因果明确的最小复现、修复及H21/H22正反例；若需GUI外部事件才能区分，先明确观察缺口。
- 入口：[控制实现](../houdini/python3.11libs/dsh_quality_contracts.py)、[执行观察](../houdini/python3.11libs/dsh_bridge.py)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)。

### H-03 超时与不确定请求恢复（RT-02）

- 状态：待修复
- 现状：exec/jobs已有同runtime回执；Manual/失败cook保留未知、不隐式重试；受限worker支持新场景cook/cache/ROP和结果复核。真实模型任务在渲染阶段发生worker退出，只留下较早检查点，退出原因缺证；新场景重跑与原失败分别保留。现有场景隔离移交、live取消、持久身份与图片历史恢复仍未闭环。
- 下一步：新加载Host验正常首次绑定和旧错误会话续接；绑定必须在pre-step正常消息批次接受，工具期只flush，旧完整文本交换只追加摘要投影修正。再按[多实例与恢复](multi-instance.md)验Qt登记/单端Repair、共享Host启动/退出及续接；默认入口和live未切换。完善Save As预留、GUI/外部替换与恢复授权后再解除受管互斥。退出选择/崩溃暂停/检查点及跨进程身份恢复仍待实现，不因心跳超时杀Houdini、不重发代码、不凭tag认领。发布仍须真实路径验收，不复制账号/会话；图片恢复保留原历史、不改node_modules。
- 移除条件：H-01所确认版本的真实路径可区分未执行/执行中/完成/仍未知，查回不重做修改、不重复计账；过期及无法恢复的情况如实报告，不能仅以隔离脚本通过核销。
- 入口：[Host传输](../src/bridge.ts)、[Bridge队列](../houdini/python3.11libs/dsh_bridge.py)、[执行状态测试](../tools/tests/execution-state.test.mjs)。

### H-04 原始要求与控制/结构验收（QA-01/05/06、RB-06）

- 状态：待验证
- 现状：共享轮廓/尺寸、有效模式参数、危险局部和少量自由输入指导已有候选。有限平面面内自交观察可在H21/H22复现旧破面并透传摘要。混合输出仍unverified，但会给出有界的最终Polygon组候选供局部复查。最终Polygon组的axis_passage能区分开放轴线与后加封盖；component_count能按共享边检查声明的独立件基数。两者均不证明孔径、位置、连接或整件。真实任务仍有孔距误作轮廓、叶片漏数、对称连接漏件和跨部件重叠；主控刚体/比例/恢复通过可与这些成品错误并存。
- 下一步：用未见自然任务观察作者是否在最后一次修改后声明并复验关键孔轴；滑轨仍有后加封盖封住滑块孔，需推动最终零件身份及孔轴合同进入作者实际流程。继续补对称成员基数与连接件进入实际承载结构的反例，不以源刀体、单条清轴或旧检查替代当前成品。几何、参考保真、控制、交付判断分开；全部公共控制逐一响应并验证高风险组合。开放线尾、单位/Y-up、公共Output/空Pack/HDA与PolyBevel边界继续守住。
- 移除条件：默认与扰动关系反例能被自然任务发现，未满足核心要求不会被goal/todo完成覆盖；不能只靠固定脚本通过核销。
- 入口：[证据契约](execution-contract.md)、[控制设计](parameter-controls.md)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)、[共享控制构造反例](../tools/tests/dsh-control-design.test.py)、[节点模式知识回归](../tools/tests/dsh-node-knowledge.test.py)。

### H-05 组件协作与质量成本（PL/IN/CX/EV）

- 状态：待验证
- 现状：候选component-host已接原生可续跑子任务、独立worker和pre-step绑定；单个Open Workspace菜单：仅新开已保存HIP且无自有前端时显式选Component preview，普通为默认；普通/受管运行时尚未合并，live正式加载未验。首次预览的独立Python/当前Houdini路径可确定时自动采用；CLI只信显式候选，live首次配置未验，现有live Host不随源码编辑自动加载新策略。预览在绑定HIP目录建dsh-components，主子可互访文件，不声称文件系统隔离；文件工具反例要求工作区不在平台TEMP（DSH共同可写例外），组件要求workspace-write并禁shell/再委派。机制见[组件协作](component-collaboration.md)；Host在父简报前注入权威workspace/HIP并返回同一字段；上游cwd候选固定于eee1723/deepseek-harness的codex/component-child-preparation@02f873ac，本机已构建该修订CLI；未安装/发布，官方原版有零子模型执行拒绝反例。自然任务已暴露两类集成失败：test21跑通委派/片段交换但轴向错误、穿板、绝对Object Merge引用与遗留warning/probe致质量门失败；test22控制正向收敛但父作者未读协作reference、自行升级HDA并裸install，受管交换零采用；临时装配预览因Object Merge未保留OBJ变换显示轮子穿板并带wheel_id mismatch warning——数值场景与视觉proxy须分别验同一数据流。
- 下一步：跨机接续须从上游cwd候选固定修订构建，本仓库源码分支/构建产物/官方DSH发行线均不能替代；升级基线是独立资格重验，不随普通开发rebase。用新加载skill复验未见两组件任务：父作者先读协作reference，默认普通subnet→component_export→hash/revision→component_import→槽位接纳，不得自行升级HDA或裸安装；HDA交付任务作反例。集成输出须同坐标系实测关系，跨OBJ代理显式保留world变换，proxy bbox与源world bbox一致且warning-free后才可读图；颜色自述与像素不符、Trace无独立语义识图记录，视觉结论须人工对照原图。继续验异常worker展示、局部图、公共控制、输入/外部依赖与手改/消费者迁移、迁移表达式/keys、修订失效、GUI双worker渲染互斥；Host中断后旧session受管恢复仍需带checkpoint hash/session ownership的executor恢复协议，不能靠重绑或认领既有节点。未见要求变化与同信息单作者对照按C5固定模型/版本/信息/质量门进行，不以并行数量或单一墙钟证明收益。
- 移除条件：C1～C4在隔离H21/H22与获授权真实路径完成；C5以固定模型/版本/信息/总预算比较整体单作者、聚焦单作者与独立多作者，覆盖简单任务反例，报告主子总成本/质量/返工分布并明确采用范围。压缩策略另测；不以加预算或子作者自评核销。
- 入口：[组件协作与完成门](component-collaboration.md)、[执行端路由](../src/executor-routing.ts)、[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md)、[集成反例](../tools/tests/dsh-module-integration.test.py)。

### H-06 Trace判据与接口发现误差（QA-03、API、OBS）

- 状态：待验证
- 现状：Boolean卡、有限单面自交、声明接口失败/未知，以及混合最终输出的未验证原因与局部Polygon组复查入口已能进入模型回执开头；信息曝光仍不能保证正确采用。declared_checks_only及失败case保留仍会被完成式总述盖过；有作者用实测重定窗口或用包围盒宣称刚体。规则加载与遵循不稳定，普通HIP可重开不证明近看质量。API枚举/表达式错误、读取实现修schema及受管Save As摩擦有真实轨迹，live自然采用仍缺。
- 下一步：在已有summary保留测量对象、最终输出覆盖、实际关系与未测差额；即使一条孔轴pass或主控成功，其他必需孔、连接与外观仍按未测/失败单列。控制盘点先分可见可写输入、派生/单位/隐藏量；声明指标只认证其覆盖。先依据具体回执处理API发现误差，不盲加工具或放宽权限。正常入口、原生图像的语义判断、HDA生命周期/多端口及Shelf/快捷键仍按原矩阵另验。
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
- 现状：厂家图仍会误读；专注读图也曾错数叶片。评审事实表纠正部分尺寸/数量，构造仍可能错。滑轨收到160000 mm回执仍保留错误尺度，说明只读提示不够。新增最终零件组`physical_extent`毫米合同可直接判错，H21/H22及旧滑轨/搭扣反例通过；作者自然采用与图纸归属仍未验。
- 下一步：固定输入验证作者能否在建模前核对少量尺寸归属、声明物理尺寸合同并在最后修改后重验；错误/未知事实不得变成pass。验证危险局部原型、跨阶段保留、中途变更与压缩续接；核心缺失先报部分完成，不先扩多作者。
- 移除条件：未见任务中短请求能形成合理边界且实际可调，多轮摘要不自行降级必需项，计划按依赖推进，重复失败有新增证据或换诊断方法；信息不足与信息等价分别评价，并报告问询与成本分布。
- 入口：[任务来源](../src/task-sources.ts)、[Houdini preset](../presets/houdini/agent.cordis.yml)、[SOP工作流](../skills/houdini-sop-workflow/SKILL.md)、[来源回归](../tools/tests/task-sources.test.mjs)。
