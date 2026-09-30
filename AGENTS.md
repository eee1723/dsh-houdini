# AGENTS.md

## 项目定位

dsh-houdini是DeepSeek Harness插件：Host工具与上下文 → HTTP →
Houdini主线程执行队列 → 动词能力库及领域模块。
hou只存在于Houdini侧，Node Host不直接调用HOM。

## 设计与重构原则

- 从产品目标和平台事实出发：帮助用户在真实Houdini中完成高质量、可编辑、可继续修改的工程与工具，充分发挥LLM的理解、规划和操作能力。
- 已完成的实现、工具数量、目录结构和历史测试不是设计约束。可以删除、合并或替换不再服务目标的功能；在当前项目中直接重构，继续使用DSH提供的会话、模型与通用Agent能力。
- 执行层负责准确操作和真实反馈；任务策略与领域方法按需加载。不要把模型的一次失败写成永久执行门槛，产品计划不作为操作Houdini的准入条件。
- 同一事实只有一个维护源；结果、上下文和界面消费同一份执行事实。避免重复状态解释器、兼容补丁和猜测来源的逻辑。
- 只提供Houdini一种模式，使用DSH的preset注册和通用任务能力。工具各有清楚职责；不建立插件自己的产品完成账本、强制建模流程或会话压缩系统。
- 避免过度防御：只处理真实接口条件和已观察到的失败，不因假想风险增加审批、拦截、回退或层层校验。
- 验证与改动相称：优先构建和直接受影响的回归，关键执行边界使用必要的隔离HOM检查。已有检查通过后不重复扩大测试；移除旧策略时同步删除只证明旧策略的断言，不为机械拆分新增测试体系。

## 面向用户的回复

- 默认用用户的语言和自然、简短的日常说法；先讲清结果、对用户的影响和下一步，再补技术细节。
- 专业词第一次出现时用一句话解释。失败和没验证的地方要直说；节点路径、哈希与完整报错放在后面的技术补充，不让用户先读这些才能明白结论。

## 命令与入口

- 构建：npm install && npm run build，只用npm，不运行pnpm。生成器刷新节点卡文档、
  唯一preset声明、工具说明、client.js目录和src/generated-verb-contract.ts，再由tsc输出lib；不手改生成区或lib。
- 文档门：npm run docs:check；完整Node回归：npm test。日常按受影响能力选择检查；涉及执行内核时用隔离hython覆盖raw-gate、node-ownership、caught-failure、tab-create-failure、object-parenting和scene/network/render。
  正式发布前覆盖H21/H22；纯文档、前端或模块整理不机械触发整套HOM/GUI/模型评测。方法见docs/development.md，结果不写成docs流水账。
- 启动：DSH-Houdini → Open Workspace。重载Host/Bridge/helper用Version & Diagnostics →
  Advanced diagnostics → Repair and restart runtime；WebView/menu/package变更完整重启Houdini。
  不未经用户授权重启live或修改HIP；构建通过不等于live已加载。
- 部署：main push/tag/Draft不算正式发布；安装/启动/修复默认共用兼容清单preferred精确DSH。
  正式受管安装合同见docs/setup.md，未交付部分见docs/handoff.md，不把源码build当成用户发行包安装。
- trace先按houdini-trace-analysis skill跑extract-trace-evidence.mjs，再跑tools/trace-report.mjs；
  区分目录广度、调用含动词率、动词密度、只读裸探针、Gate拦截与成功裸修改。

## 单一维护源

- docs/README.md是长期知识索引；架构与代码地图在docs/architecture.md。
- 查询开发状态或接续前先核对git branch -a -vv、git worktree list和相关提交，再读目标分支docs/handoff.md；不把当前目录或main当作全部开发状态。handoff是唯一滚动交接入口，只保留未完成动作/验证缺口，按docs/development.md及时删项。
- docs/tool-design.md维护动词目录/执行版本；houdini/node-operation-contracts.json维护节点卡，
  docs/node-operation-cards.md只由生成器镜像。领域方法只在skills按需维护。
- docs只放现役设计、接口、维护规范、稳定测试方法和实现边界。修改时就地替换旧说明，
  docs/handoff.md仅例外容纳必要交接；不追加版本叙事、尝试/测试流水、session记录，不建立docs/archive或按日期分叉交接。
- 新增长期生产模块必须进入架构代码索引；新增文档须加入索引并有源码与验证入口。
- 过程与证据保留在会话/CI或不打包的临时产物，历史在Git；不改机器生成记忆或范围外项目。
- TypeScript ESM/Cordis，client.js是手写CJS factory；Python通过PYTHONPATH兼容H21/H22。
  presets/houdini承载身份/工作方式并通过DSH bundle声明式注册，插件guidance保持persona中性。

## 不可放宽的执行边界

- 所有HOM执行经Bridge主线程队列串行编组；GUI线程不得阻塞socket/进程/netstat探测。
- 动词是修改主接口，裸hou是只读/低层逃生舱；Raw Gate默认开启，已覆盖修改不可allow_raw旁路。
- mutation默认仅当前session创建identity；foreign只有用户明确指定时允许单次allow_foreign。
  路径/父网络/自报理由不构成ownership；render服务永不豁免。
- 严格设参；verify_network必须明确output，默认拒绝empty/error，require_valid=False仅诊断。
  build_module的None保留空槽，跨subnet不能猜端口；advisories非阻断、不改默认、不证明正确。
- 真实表面接口、Polygon拓扑、稳定ID控制测试的范围见docs/execution-contract.md；
  不把bbox/driver点/响应非零冒充实体关系，unsupported保持unverified。
- test_controls必须exec，声明指标/关系并恢复参数、keys、frame及bgeo；外部文件/Python/solver副作用
  不属恢复保证。Save As须目标路径/当前HIP/用户授权，不放开raw load/clear。
- 渲染输出锚$HIP、必须后缀；render_view持久__dsh_houdini_*服务复用不删除。
  A/B用相同framing_frame及固定取景/深度包络；detail只允许二维裁框，近远裁面错误拒绝，
  不漂移相机。正式camera_fit保持自身边界。
- transport/bootstrap/presentation/semantic inspection分别判断；没有成功语义识图必须写视觉未验证。
- 普通建模与收尾验证由当前作者执行；无独立评审agent入口。没有多作者租约，不能借allow_foreign或共享身份建模。
- 程序化产品模型开发评测以evaluation/product-modeling-dev-v1/为准；公开任务与评审答案隔离，未见题不用于调参。评测答案不进入生产面。
