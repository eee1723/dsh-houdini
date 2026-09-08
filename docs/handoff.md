# 当前开发交接

核对日期：2026-09-09

只保留下一次开发所需的活动事项；完成对应移除条件即删除整项，不追加完成日志。
维护规则见[交接文档生命周期](development.md#交接文档生命周期)。实现版本以[工具设计](tool-design.md)为准，
本页不证明当前live已加载；不授权重启服务、修改用户HIP或发起收费测试。
更远的产品范围见[主要开发方向](development-directions.md)，不在这里复制路线图。

## 待交接事项

### H-01 当前源码的完整运行态验收

- 状态：待验证
- 现状：标量设参、结果/来源回读、Trace失败详情、WebView鉴权导航和SOP聚焦已有源码与隔离回归；完整当前checkout的live与新session验收未闭环。
- 下一步：用户授权后核对Host/Bridge版本，测试首次启动/重连、失败详情返回、来源回读及新SOP触发；WebView变更需完整重开Houdini。
- 移除条件：目标H21/H22的实际用户路径和加载版本均有证据；隔离回归不得冒充live验收。
- 入口：[兼容验收](dsh-update-compatibility.md)、[WebView回归](../tools/tests/dsh-webview-navigation.test.py)、[Trace回归](../tools/tests/trace-view.test.mjs)。

### H-02 控制值发生未解释的变化（RT-01）

- 状态：待修复
- 现状：控制测试返回恢复值后，后续查询曾观察到辐条数量/显示开关变值；根因未定，不能归为用户undo或等同已处理的编译依赖刷新。
- 下一步：按请求顺序对齐设参、测试恢复、渲染和外部修改观察，在隔离输出上定位第一次偏离；先复现再改恢复逻辑。
- 移除条件：有因果明确的最小复现、修复及H21/H22正反例；若需GUI外部事件才能区分，先明确观察缺口。
- 入口：[控制实现](../houdini/python3.11libs/dsh_quality_contracts.py)、[执行观察](../houdini/python3.11libs/dsh_bridge.py)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)。

### H-03 超时与不确定请求恢复（RT-02）

- 状态：待修复
- 现状：HTTP取消不保证HOM未执行；有job状态与in-flight历史提示，但没有完整的不确定请求查回和异步核算闭环。
- 下一步：隔离注入排队超时、执行中断联、迟到回包与重复查询；设计请求关联/查询语义，防止重提修改与重复计账。
- 移除条件：能区分未执行/执行中/已返回或仍未知，结果查回不重做修改；job乱序与runtime更换回归通过。
- 入口：[Host传输](../src/bridge.ts)、[Bridge队列](../houdini/python3.11libs/dsh_bridge.py)、[执行状态测试](../tools/tests/execution-state.test.mjs)。

### H-04 原始要求与控制/结构验收（QA-01/05/06、RB-06）

- 状态：待验证
- 现状：来源锚、控制变化/覆盖摘要和接口/精确变换测量已有；模型仍可能用bbox或面数通过声称整体连接、均匀变换或全部控制正确。
- 下一步：在不同资产上核对“要求→实际输出/关系→适用判据→修改后复验”，保留未测范围；不新增第二份可写完成证书。
- 移除条件：默认与扰动关系反例能被自然任务发现，未满足核心要求不会被goal/todo完成覆盖；不能只靠固定脚本通过核销。
- 入口：[证据契约](execution-contract.md)、[控制回归](../tools/tests/dsh-quality-contracts.test.py)、[变换反例](../tools/tests/dsh-modeling-identity.test.py)。

### H-05 聚焦模块与上下文成本（PL/IN/CX/EV）

- 状态：待验证
- 现状：整体代理→局部交付→集成复验已是SOP候选；局部漏件/实例脱离机制回归存在，但质量收益和上下文净成本未受控比较。
- 下一步：固定模型、工具版本、任务信息、总预算与视角，只替换旧/新SOP指导；记录局部质量、集成关系、返工和上下文成本，含简单编辑/单部件反例。
- 移除条件：重复的未见任务对照支持采用或明确放弃该候选；不能混入工具升级、加预算或不同车型后宣称收益，不自动启多作者。
- 入口：[模块合同](../skills/houdini-sop-workflow/references/module-quality-contracts.md)、[集成反例](../tools/tests/dsh-module-integration.test.py)、[任务来源](../src/task-sources.ts)。

### H-06 Trace判据与接口发现误差（QA-03、API、OBS）

- 状态：待修复
- 现状：已有误报包括“用户已选高细节却算缺LOD”“手写关系probe算无关系证据”；图片返回、实际读图结论和最终图新鲜度也需分别判断。result_ref/source_ref互斥误用仍发生。
- 下一步：补澄清答案关联、手写量测范围、读图与最终声明冲突的通用fixture；核对来源读取统计及签名发现，区分调用失败与检查未通过。
- 移除条件：正反例与已有轨迹回归不误判，不以启发式推导艺术正确性；精确API/表达式写入、求值、cook和效果边界清楚。
- 入口：[审计提取](../skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs)、[证据测试](../tools/tests/trace-evidence-helpers.test.mjs)、[工具接口](../src/tools.ts)。

### H-07 视频解析到教学工程的端到端验证

- 状态：待验证
- 现状：本地视频转录/抽帧/变化候选、context证据包和记录校验已有；链接下载、逐句对齐、语义识别及教学HIP交付仍不能据此视作可用。
- 下一步：用户提供并授权材料后，用短片验证音画核对、缺口记录和领域复现；云提交与工程修改分别授权，不建设自动知识沉淀。
- 移除条件：当前候选的真实媒体/语义及最小教学工程验收有证据；更远能力继续留在开发方向，不扩成交接长清单。
- 入口：[视频当前范围](development-directions.md#教程转教学工程)、[解析脚本](../skills/houdini-video-tutorial/scripts/video_tutorial.py)、[离线回归](../tools/tests/video-tutorial.test.py)。
