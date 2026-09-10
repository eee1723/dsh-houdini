# AGENTS.md

## 项目定位

dsh-houdini是DeepSeek Harness插件：src/（5个houdini_*工具）→ HTTP →
dsh_bridge.py（Houdini主线程队列）→ `dsh_hou_helpers.py`（65 动词）。
hou只存在于Houdini侧，Node Host不直接调用HOM。

## 命令与入口

- 构建：npm install && npm run build，只用npm，不运行pnpm。生成器刷新节点卡文档、
  client.js目录和src/generated-verb-contract.ts，再由tsc输出lib；不手改生成区或lib。
- 文档门：npm run docs:check；测试：npm test。HOM回归在tools/tests/*.test.py，用隔离hython跑；
  至少raw-gate、node-ownership、caught-failure、tab-create-failure、object-parenting和scene/network/render；
  发布前覆盖H21/H22。方法见docs/development.md，结果不写成docs流水账。
- 启动：DSH-Houdini → Open Workspace。重载Host/Bridge/helper用Version & Diagnostics →
  Advanced diagnostics → Repair and restart runtime；WebView/menu/package变更完整重启Houdini。
  不未经用户授权重启live或修改HIP；构建通过不等于live已加载。
- 部署：main push/tag/Draft不算正式发布；安装/启动/修复默认共用兼容清单preferred精确DSH。
  正式受管安装合同见docs/setup.md，未交付部分见docs/handoff.md，不把源码build当成用户发行包安装。
- trace先按houdini-trace-analysis skill跑extract-trace-evidence.mjs，再跑tools/trace-report.mjs；
  区分目录广度、调用含动词率、动词密度、只读裸探针、Gate拦截与成功裸修改。

## 单一维护源

- docs/README.md是长期知识索引；架构与代码地图在docs/architecture.md。
- 接续开发先读docs/handoff.md；它是唯一滚动交接入口，只保留未完成动作/验证缺口，按docs/development.md及时删项。
- docs/tool-design.md维护动词目录/执行版本；houdini/node-operation-contracts.json维护节点卡，
  docs/node-operation-cards.md只由生成器镜像。领域方法只在skills按需维护。
- docs只放现役设计、接口、维护规范、稳定测试方法和实现边界。修改时就地替换旧说明，
  docs/handoff.md仅例外容纳必要交接；不追加版本叙事、尝试/测试流水、session记录，不建立docs/archive或按日期分叉交接。
- 新增长期生产模块必须进入架构代码索引；新增文档须加入索引并有源码与验证入口。
- 过程与证据保留在会话/CI或不打包的临时产物，历史在Git；不改机器生成记忆或范围外项目。
- TypeScript ESM/Cordis，client.js是手写CJS factory；Python通过PYTHONPATH兼容H21/H22。
  presets承载身份/工作方式并由launcher同步，插件guidance保持persona中性。

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
- 冻结的benchmark protocol/matrix/holdout不得随普通开发改动或解封；评测答案不进入生产面。
