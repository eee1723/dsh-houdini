# 当前开发交接

核对日期：2026-09-28

只保留下一次开发所需的活动事项；完成对应移除条件即删除整项，不追加完成日志。
维护规则见[交接文档生命周期](development.md#交接文档生命周期)。实现版本以[工具设计](tool-design.md)为准，
本页不证明当前live已加载；不授权重启服务、修改用户HIP或发起收费测试。
更远的产品范围见[主要开发方向](development-directions.md)，不在这里复制路线图。

**执行计划与完成门**

当前主线是程序化产品模型质量：先用独立开发评测定位“理解图纸、建模、看图修正、交付判断”哪一段失效，再修对应H项。其他方向保留原有验证缺口，不扩成全部远期功能。
评测维护时读[评审侧阶段结论与可迁移证据索引](../evaluation/product-modeling-dev-v1/evaluator-only/stage-2026-09-26.md)；该记录不替代本页活动待办，也不向建模作者提供评审答案。
每项按“最小反例/观察缺口→修复→正反例→真实路径验收→核销”推进；外部验收阻塞不阻止无依赖的本机研发。

| 顺序 | 事项 | 交付与依赖 |
|---|---|---|
| 1 / P0 | 产品模型开发评测 | 保留12题公开开发/独立评审协议；输入对照后固定模型复测构造干预，再用厂家照片与尺寸图迁移；不把少量开发题当完整基准 |
| 2 / P0 | H-03 中断与最终HIP | 先分清渲染中断、未知请求、进程退出和保存缺失；查回不重做修改，检查点不算交付 |
| 3 / P0 | H-01 验收环境 | 明确源码/受管包/加载身份；准备隔离H21/H22与启动环境用例；异机、签名运维和live另取证 |
| 4 / P0 | H-08 → H-04 → H-06 产品质量 | 根据失效阶段修要求提取、实体连接、局部视觉和最终报告；模型验收依赖H-01确认的运行版本 |
| 5 / P1 | H-02 控制漂移 | 取得因果反例，隔离回归不冒充原问题已修 |
| 6 / P1 | H-05 组件协作与成本 | 先无模型节点片段往返；是否提升细节质量需固定总预算与单作者对照，不以多作者数量为成果 |
| 7 / P2 | H-07 教学工程 | 获授权短片的音画核对、阶段复现、参数实验和重开验收；材料/云提交授权未到时保留缺口 |
| 8 / 收口 | 全链路代码与知识review | 修复后逐层审查安装→Host→Bridge→helpers→结果/图像→Trace→交付；发现缺陷回到对应H项复验 |

最终review核对重复状态、消费者、异常吞没、权限/生命周期及文档冲突；退役接口先核对消费者与替代路径，历史只留Git。
稳定结论原位同步docs/规则，生成区仅由生成器刷新；门禁覆盖docs:check、npm test、H21/H22相关HOM与包内容检查。
运行态未验证、缺授权/材料/异机证据必须保留pending；临时产物/分支清场先只读列候选，汇报后经用户确认才删除。

## 待交接事项

### H-01 部署更新改造与完整运行态验收

- 状态：待验证
- 现状：源码锁定DSH 0.1.6-alpha.2；打包API/preset、H21/H22隔离共享Host浏览器选择/绑定与GUI交付卡片通过。隔离H21新会话已跑DeepSeek V4 Flash并保留原始轨迹/HIP；正常入口live、签名发行及异机仍未证实，私钥备份与长期运维责任未定。
- 下一步：按[候选资格流程](dsh-update-compatibility.md#新-dsh-版本的资格流程)补H21/H22 live WebView发送/停止/重连、V3 Trace、插件实时禁用/重载及签名组合；继续把绑定落盘屏障及其他同步Session历史读取逐域迁至projection。再验异机启动、主面板/诊断、请求恢复、来源/工作流、压缩恢复和原生/Code Mode图像；live确认交付卡片与Explorer源文件定位。preferred与隔离smoke均不证明live已加载、发布、历史迁移或视觉正确；live重载后复核无票据及Job跨会话拒绝。
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
- 现状：同runtime回执和受限worker具备；风扇退出、Neutrik长调用仍无最终HIP。undo挂起已修服务事务边界并经H21/H22隔离GUI验证，原任务同因未证。早期卷线盘A/B缺保存回执，C2存后未复存且GUI STOP超时；C4/V1最终保存、独立H21重开及清洁STOP通过；脏场景显式拒绝仍仅通过隔离H21/H22，未在真实作者运行触发。评审清场在隔离H21复现挂起，保留服务可退出；原弹窗归属未证。
- 下一步：在不同任务复验最终保存/回执/重开，并于真实作者脏场景验显式拒绝，区分进程退出、未知请求和保存失败；同runtime仅按request_ref查回，不重发修改。按[多实例与恢复](multi-instance.md)验Qt登记/单端Repair、共享Host退出与旧会话续接；跨进程恢复、GUI/外部替换与恢复授权后置。live未验；不因超时杀Houdini或凭tag认领，图片恢复保留原历史。
- 移除条件：H-01所确认版本的真实路径可区分未执行/执行中/完成/仍未知，查回不重做修改、不重复计账；过期及无法恢复的情况如实报告，不能仅以隔离脚本通过核销。
- 入口：[Host传输](../src/bridge.ts)、[Bridge队列](../houdini/python3.11libs/dsh_bridge.py)、[预览服务](../houdini/python3.11libs/dsh_hou_helpers.py)、[GUI反例](../tools/tests/run-render-undo-gui.py)、[执行状态测试](../tools/tests/execution-state.test.mjs)。

### H-04 原始要求与控制/结构验收（QA-01/05/06、RB-06）

- 状态：待验证
- 现状：最终Polygon组可查孔轴、件数、毫米尺寸；`bore_clearance`经H21/H22验证并在E6自然采用。WAGO拨杆/壳体12.09 mm³重叠仅在独立副本修复，E6叶片交叠仍unverified。卷线盘C1尺度/主控失效，C2无最终保存；C4交付重开且尺度、孔道、主控改善，仍缺轴—筒传力。V1台钳交付重开，合拢双垫接触与开度25/50 mm间隙通过，丝杠啮合/导轨承载未证。OpenGL锯齿不直接判破面。
- 下一步：不把OpenGL边缘锯齿直接判定为真实缺面；E6同一HIP作者图较平滑而独立重开图锯齿明显。下一种构造类别继续对照最终几何、固定视角近景和实际外观细节。最后修改后对交付SOP逐项复验孔轴、孔径区间、数量、机械传动逐段接合、表面和状态转换（含释放后的保持），明确临时输出与最终输出。未见题继续检查对称基数、承载连接、单位/Y-up及公共Output边界。
- 移除条件：默认与扰动关系反例能被自然任务发现，未满足核心要求不会被goal/todo完成覆盖；不能只靠固定脚本通过核销。
- 入口：[证据契约](execution-contract.md)、[控制设计](parameter-controls.md)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)、[共享控制构造反例](../tools/tests/dsh-control-design.test.py)、[节点模式知识回归](../tools/tests/dsh-node-knowledge.test.py)。

### H-05 组件协作与质量成本（PL/IN/CX/EV）

- 状态：待验证
- 现状：候选component-host已接原生可续跑子任务、独立worker和pre-step绑定；单个Open Workspace菜单：仅新开已保存HIP且无自有前端时显式选Component preview，普通为默认；普通/受管运行时尚未合并，live正式加载未验。首次预览的独立Python/当前Houdini路径可确定时自动采用；CLI只信显式候选，live首次配置未验，现有live Host不随源码编辑自动加载新策略。预览在绑定HIP目录建dsh-components，主子可互访文件，不声称文件系统隔离；文件工具反例要求工作区不在平台TEMP（DSH共同可写例外），组件要求workspace-write并禁shell/再委派。机制见[组件协作](component-collaboration.md)；Host在父简报前注入权威workspace/HIP并返回同一字段；上游cwd候选固定于eee1723/deepseek-harness的codex/component-child-preparation@02f873ac，本机已构建该修订CLI；未安装/发布，官方原版有零子模型执行拒绝反例。自然任务中test21片段交换通过但轴向/穿板/绝对引用/warning未过质量门；test22控制收敛却未读协作reference、擅升HDA并裸install，受管交换零采用；预览proxy丢OBJ变换并带wheel_id warning，须验数值与视觉同一数据流。
- 下一步：跨机接续须从上游cwd候选固定修订构建，本仓库源码分支/构建产物/官方DSH发行线均不能替代；0.1.5-rc.2 cwd候选缺`@deepseek-ai/dsh-workflow-ptc`而不能挂载现行preset；精确0.1.6-alpha.2无cwd原版在H21隔离链路首个子模型前按预期拒绝，正向链路先把cwd修订移到匹配的0.1.6依赖组合，升级基线需独立资格重验。用新加载skill复验未见两组件任务：父作者先读协作reference，默认普通subnet→component_export→hash/revision→component_import→槽位接纳，不得自行升级HDA或裸安装；HDA交付任务作反例。集成输出须同坐标系实测关系，跨OBJ代理显式保留world变换，proxy bbox与源world bbox一致且warning-free后才可读图；颜色自述与像素不符、Trace无独立语义识图记录，视觉结论须人工对照原图。继续验异常worker展示、局部图、公共控制、输入/外部依赖与手改/消费者迁移、迁移表达式/keys、修订失效、GUI双worker渲染互斥；Host中断后旧session受管恢复仍需带checkpoint hash/session ownership的executor恢复协议，不能靠重绑或认领既有节点。未见要求变化与同信息单作者对照按C5固定模型/版本/信息/质量门进行，不以并行数量或单一墙钟证明收益。
- 移除条件：C1～C4在隔离H21/H22与获授权真实路径完成；C5以固定模型/版本/信息/总预算比较整体单作者、聚焦单作者与独立多作者，覆盖简单任务反例，报告主子总成本/质量/返工分布并明确采用范围。压缩策略另测；不以加预算或子作者自评核销。
- 入口：[组件协作与完成门](component-collaboration.md)、[执行端路由](../src/executor-routing.ts)、[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md)、[集成反例](../tools/tests/dsh-module-integration.test.py)。

### H-06 Trace判据与接口发现误差（QA-03、API、OBS）

- 状态：待验证
- 现状：Host提醒fail/unverified并列出检查路径；WAGO曾自然检查最终尺寸/孔/控，Southco漏最终合同，E6交叠未验证却未披露。旧卷线盘多把局部通过写成整机完成，C2更把存后未复存称交付。工具回执/摘要现保留“关系未检查”；C4补三项接口仍漏轴—筒传力。V1新skill与B0旧包在同一台钳题均披露无真实丝杠啮合，独立评审均部分完成；事后非随机单对照不支持归因/泛化，正常入口与语义识图未验。
- 下一步：最终报告逐项绑定原要求、交付SOP、最后有效证据和控制转换，区分已测失败/未测/临时输出；新机制漏报再现时预锁重复与无传动反例，继续验错误成功判定。声明指标只认证其覆盖范围；正常入口、图像语义和其他接口按原矩阵另验。
- 移除条件：正反例与已有轨迹回归不误判，不以启发式推导艺术正确性；精确API/表达式写入、求值、cook和效果边界清楚。
- 入口：[审计提取](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)、[工具接口](../src/tools.ts)。

### H-07 视频解析到教学工程的端到端验证

- 状态：待验证
- 现状：schema-2 notes、多入口分页/局部取证和派生交接有源码入口，旧记录可读。像素候选仍会漏掉低幅操作，结构校验不证明语义；完整人工标注基线、DSH自然采用、未见视频和教学工程未验，不能因局部真实资料回读通过核销。
- 下一步：按[视频测试矩阵](../skills/houdini-video-tutorial/references/video-processing.md#维护验收)验新session未见视频：成品参考前置/覆盖、后段修正、低幅回查与对象身份；明确效果但缺参数时主动实验收敛，严格原值任务不被效果拟合替代。按[COP验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)验单元形态→整体→材质对照、较优候选恢复与重开；在新加载runtime验大依赖网络、H22原生材质连线及参数别名守卫的自然采用，不以隔离机制回归核销视觉/泛化。人工基线/新模型采用未验；旧资料副本核对，云提交与live修改分别授权。
- 移除条件：当前候选的真实媒体/语义及最小教学工程验收有证据；更远能力继续留在开发方向，不扩成交接长清单。
- 入口：[视频当前范围](development-directions.md#教程转教学工程)、[解析脚本](../skills/houdini-video-tutorial/scripts/video_tutorial.py)、[离线回归](../tools/tests/video-tutorial.test.py)。

### H-08 意图形成、依赖计划与跨轮保留（IN-01/02/03、PL-01/02、EV-01）

- 状态：待验证
- 现状：早期厂家图有真实误读和尺寸归属错误；滑轨/XLR曾有1000倍单位错误。WAGO 2020 PDF原生表格和图均为18.7，作者读数正确；错误评审备注已勘误。新候选仅WAGO建模前生成核验表，Southco没有。Southco 96基线仍有1000倍尺度，候选修正了尺度但未完成结构验收。E6中号新组没有混用同页大号的42.9 mm/63.5 mm宽度，仍有未标注机构和孔径细差。生产流程没有独立事实账本，同页裁图不是第二来源。
- 下一步：评审侧先核PDF原生规格与图示，冲突则保留不确定，不允许把未复核的评审备注当答案。再给关键数字和归属设计独立视觉/OCR核对或明确不确定状态的输入边界，与作者自建表分开评估；继续验事实跨构造/压缩保留、漏表提醒和核心缺失的部分完成报告。
- 移除条件：未见任务中短请求能形成合理边界且实际可调，多轮摘要不自行降级必需项，计划按依赖推进，重复失败有新增证据或换诊断方法；信息不足与信息等价分别评价，并报告问询与成本分布。
- 入口：[任务来源](../src/task-sources.ts)、[Houdini preset](../presets/houdini/agent.cordis.yml)、[SOP工作流](../skills/houdini-sop-workflow/SKILL.md)、[来源回归](../tools/tests/task-sources.test.mjs)。
