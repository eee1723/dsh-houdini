# AGENTS.md

## 项目定位

dsh-houdini 是 DeepSeek Harness（dsh）插件，让 agent 驱动一个正在运行的 SideFX Houdini 会话。链路：`src/`（注册 5 个 `houdini_*` 工具）→ HTTP → `dsh_bridge.py`（主线程工作队列）→ `dsh_hou_helpers.py`（57 动词）。`hou` 只存在于 Houdini 侧 Python 模块，Node Host 不直接调用 HOM。

## 怎么跑

- 构建：`npm install && npm run build`。生成器从 `docs/tool-design.md` 同时刷新 `client.js` 目录和 `src/generated-verb-contract.ts`，再由 tsc 输出 `lib/`；不要手改生成区或 `lib/`。
- 启动：Houdini 菜单 `DSH-Houdini` → `Open Workspace`。加载新代码/修复运行时时，打开 `Version & Diagnostics...` → `Advanced diagnostics` → `Repair and restart runtime`。
- 验证：Web UI 新建「Houdini 模式」会话，发「用 houdini_query 列出 /obj 下所有节点」。Host 会在第一次场景调用前比较自身词表指纹与运行中 Bridge；不一致会拒绝执行并要求重启服务。
- 测试：`npm test` 跑构建和全部 Node 确定性回归；需要 HOM 的回归在 `tools/tests/*.test.py`，目标版本用 `hython` 跑。至少再执行 raw-gate、node-ownership、caught-failure、tab-create-failure、object-parenting 和 scene/network/render contract；发布前同时跑 H21/H22。
- trace：先按 `houdini-trace-analysis` skill 跑 `extract-trace-evidence.mjs`，再跑 `node tools/trace-report.mjs`。报告必须区分目录广度、调用含动词率、动词密度、只读裸探针、被 Gate 拦截和成功裸修改。

## 技术栈与目录

- TypeScript ESM（tsc 直出，无 bundler）；Cordis 形状 `{name, inject, Config, apply}`；`client.js` 是手写 CJS factory。
- `houdini/python3.11libs/`：Bridge、动词 helper、launcher、版本诊断、WebView。纯 Python 通过 `PYTHONPATH` 同时支持 H21 py3.11 / H22 py3.13。
- `presets/houdini*`：生产/开发 persona；launcher 自动同步到 `~/.dsh/.agent-presets/`。
- `skills/`：trace、asset-review、SOP、Solaris/Karma、rig/animation、skill-governance 六个随包 skills。
- `docs/tool-design.md` 是动词目录唯一真相源；`docs/development.md` 记录当前进度和历史证据。

## 关键约束

- `hou` 只能在 Houdini 主线程调用；所有执行经 Bridge 工作队列串行编组。GUI 线程不得做 socket/进程/netstat 阻塞探测。
- 插件 guidance 保持 persona 中性，只放稳定执行契约；身份和程序化工作方式放 preset；领域 recipe 放按需 skill。
- 动词是场景修改主接口，裸 `hou` 是只读/低层逃生舱。Raw Gate 默认开启；动词已覆盖的裸修改不可用 `allow_raw` 旁路。
- 节点可读不等于可写。mutation 默认只作用于当前 DSH session 创建的节点；foreign 节点只有用户明确指定时才可用单次 `allow_foreign`。render service 永不豁免。
- 视觉 transport、bootstrap、presentation 与语义识图是四件事。没有成功 semantic inspection 就必须写“视觉未验证”；`render_check` 只证明文件/像素事实。
- `render_view(EXPLICIT_SOP)` 使用持久 `__dsh_houdini_*` 服务；任务收尾复用、不删除。动画 A/B 使用同一 `framing_frame`。
- `node_modules` 只用 npm 管；不要在本仓库运行 pnpm。Houdini 产出锚定 `$HIP`，不写进 workspace 或插件仓库。
- 执行契约 v3：继承v2严格设参；verify_network必须明确output、默认拒绝empty/error，require_valid=False仅诊断。build_module支持None输入空槽；跨subnet接线不能猜端口。渲染相对路径锚HIP、缺后缀拒绝，file/pixel/semantic分层；geo_point_spacing全量检查有序点弦长，不证明表面关系。Save As仍须目标路径/当前HIP/用户授权，不放开raw load/clear。
- 执行契约 v4 继承上述边界：build_module可附interfaces，geo_check_interfaces只验证实际output上的命名表面点到指定表面的距离，不证明实体穿插/强度；test_controls必须exec，临时数字控制、声明指标/关系、恢复参数/keys/frame及bgeo。unsupported保持unverified，不用P-only断言原生primitive无响应；外部文件/Python/solver副作用不属恢复保证。

## 2026-09-07 v9：独立资产评审候选（当前）

用户明确授权清理delivery流程，改一次前台spawn评审、自主改参/产图/恢复、一次汇总。
仍5工具/57动词；houdini_exec新增review(scope)/review_test(batch)，与code/allow_raw互斥。
移除生产delivery登记/累计收据/缓存及node_info/build_module准入字段；旧实现/专属回归
保留在不打包的tools/prototypes/retired-delivery。底层网络/接口/拓扑/domain/控制检查保留。
Host提供原始用户消息/问答/附件，不fork作者自评；评审token仅在Host/Bridge传递，绑定
原作者拥有的SOPparent/output/controller及唯一子agent。评审只query和受控测试，不普通
exec修改/保存/删节点/job；作者等待。临时权限不改变ownership；测试不支持时零写入
unverified；参数/keys/frame和截图用户状态恢复失败均阻断后续case。10分钟/取消/结束撤销。
不再维护长期证据缓存；每批紧凑结果。response-only只证明有/无响应，不证明设计正确。
技能6个，新增houdini-asset-review；默认复杂SOP资产收尾一次评审，简单编辑或用户不需时
不委派。新源码v9未自动重启live；真实新DSH评审和GUI扰动图仍待验收，不能把确定性子
agent替身的HTTP回归当成模型质量增益。见docs/independent-asset-review.md。

## 2026-09-06 v8：方法路由与数值证据复用候选（历史）

`e8c90d2b…`已真实使用v7登记/失效/重测，55calls但验证成本偏高。v8仍5工具/57动词：
融合Polygon使用topology共享边连通/闭合义务（基准/扰动均查），独立表面仍用interfaces；
inspect给当前数据的方法候选，Host保留合同义务变更和复用/失效case ID。
仅受限AST且成功的查询/展示整理调用可在绑定/资产重新观察一致后保留数值测试；未知/失败/
真实修改/job仍失效，并用activity代际保护并发。禁止由agent自报无副作用来豁免。
bgeo比较使用完整hjson解码内容，仅去掉导出头info.date（已捕获相邻秒唯一差异），不排除
用户date属性/原生primitive数据/拓扑，不降为P-only。Node17/H21/H22各25项及原支架临时
副本回放通过；源HIP未改。OpenGL复用只做替身策略测试，未重启live v8/未做新模型验收。
SOP治理只更新方法路由，不新增skill/对象recipe；不再重跑同题证明v7加载和采用。

## 2026-09-06 v7：Boolean准入与参数域候选（历史）

test10 `c7bf5c01…`已加载v6并主动inspect，但Boolean被白名单拒绝；支架当前形态正确，
不能将这次降级底层检查当成Host闭环已自然通过。v7仍5工具/57动词，准入Boolean，node_info
和build_module预检共享运行时类型策略；精确枚举bounds_*指标。delivery合同与test_controls
可带domain标量比较（lt/le/gt/ge/eq/ne，参数名/有限数值，不eval/求解/钳制），检查当前及
实际扰动值；无key独立控制的无效候选可零写入拒绝。仅声明case，不证明所有参数组合。
Node17、H21/H22各23回归及原始7节点test10隔离回放通过；source HIP未改。未重启live v7，
完整K3自然采用/质量增益仍待验收，不扩大矩阵，不新增动词。见docs/trusted-delivery-runtime.md。

## 2026-09-06 v6受限可信交付入口候选（历史）

v5的health/keyword-only签名已live只读确认；当前源码升v6，仍5工具/57动词。
houdini_exec新增与code/allow_raw互斥的delivery JSON分支（inspect/register/check/test_control）；
Host按DSH session保留冻结合同/控制证据，Bridge `/delivery`经主线程执行，不eval代码。
修改/job/观察变化失效旧证据，runtime/HIP load/clear/path变化重新登记；数值pass仍为
partial_pending_independent_review、语义unverified。首次接入只支持原生无外部副作用
SOP/Polygon、128直属节点/15000点/10000面，不支持VEX/Python/file/solver/subnet/外部依赖。
共用dsh_delivery.py，旧离线入口为adapter；见docs/trusted-delivery-runtime.md。
未重启live v6、未验证K3自然采用或质量增益，不自动改test9、不解封holdout。

## 2026-09-06 test9复盘后：v5安全窄修 / 离线可信交付原型（历史）

`d5ce091d…`真实加载57/v4，但新接口/控制工具0采用；全网warning已清，仍丢胎齿、两个dead
controls并错误宣称产品级完成。停止继续堆动词/长skill。本轮57/v5仅收紧connect/disconnect
的allow_foreign为keyword-only，共享ownership guard拒绝非字符串/空白显式理由（包括owned
快路径）。原型在不打包的tools/prototypes，仅隔离hython：最终part覆盖、全部数值spare控制
用例覆盖、观察状态变化后保守失效与复验；数值pass不等于语义/完整交付。Node16、双版本各21
Python回归通过；test9仅内存补线恢复胎齿并重验，两dead控制仍fail，源HIP未写。
见docs/trusted-delivery-prototype.md。未接生产Host状态机、未重启live、未跑新的弱模型质量
验收；冻结的protocol/matrix/holdout未动，不能让用户再跑整辆车来验证这个离线原型。

## 2026-09-06 模块质量合同 v4 候选（历史）

`9d3b119f…` 已真实采用v3/build_module（21次），但方向平行掩盖连接脱开、两个暴露控制无效。
本轮源码57/v4新增geo_check_interfaces/test_controls与build后接口门，SOP按需reference记录
声明接口/控制预期，不携带自行车配方。具体版本回归与验收边界见docs/execution-contract-review.md
末节；未自动重启live，不把本地功能回归写成弱模型未见任务质量已提升。以下保留历史。

## 2026-09-06 验收反馈与 v3 候选

`a28410c5…` 已真实加载54/v2：strict生效但19工具失败、build_module零采用、六次verify选到空
默认输出后仍交付。独立回读发现局部间距漏检和无效控制；相对picture落到进程cwd。
v3源码候选为55动词：显式输出/失败证据、跨网络诊断、稀疏模块inputs、渲染路径与状态、
geo_point_spacing。记录见`docs/execution-contract-review.md`末节；未自动重启live runtime，
不把本机代码回归或v2曝光写成v3新会话/弱模型质量验收通过。下列v2和更早条目是历史。

## 2026-09-05 执行契约候选

本轮新增四动词，目录54/执行语义v2；收敛 Raw Gate 分类、严格设参、模块清理、主线程 fail-closed、
job 取消真实结果、请求级图片隔离和图像解码预算。源码修复、双版本回归与未覆盖的现场验收见
`docs/execution-contract-review.md`。运行中 Bridge/Host 未自动重启；baseline 的 runtimeVerification
保持 false，不能把定向回归或旧 session 写成新弱模型质量/视觉语义已经通过。下列条目保留历史状态。

## 当前状态（2026-09-02）

端到端链路、50 个目录动词、五个 skills、ownership guard、Raw Gate、rollback、隔离 `render_view`、HTML/evidence trace 已实现。2026-09-01 从 `cf1f1e8` 完整冷启动 H21 时 Bridge 为 49 动词/指纹 `4f3516dec006…`；当前第 50 个动词 `set_object_parent` 已通过 H21/H22 回归但待 runtime reload。该历史 cold-start 的 Web 200、异步 WebView、Host/Bridge 握手与真实 Houdini 模式 `houdini_query`/Trace 只读分类均通过；session `45798bd2-41a6-4b12-9dfa-fb62b25faa45` 为 1 次无动词只读 HOM probe，0 mutation、0 Gate block、0 rollback。

生产视觉依赖已因 DSH 0.1.2 兼容性固定到 `@anionex/dsh-vision-toolkit@0.1.40`：该版移除了对旧 settings runtime API 的导入，Web profile 加载已实测；升级后的 semantic smoke/A-B 尚未跑，完成前不得把 runtime 可加载写成视觉语义已验证。provider/model/凭据仍由 profile 设置管理；旧 `dsh-vision-router` 与本地 `dsh-vision-fallback` 均退役。每次任务仍须区分 transport、bootstrap、presentation 与 semantic inspection。launcher 已适配 DSH 0.1.2 的 process token → signed browser cookie 鉴权和 slash/generated-args RPC，Host RPC 与 QtWebEngine 分别建立各自 cookie；五个 `houdini_*` 工具已有纯函数调用/结果卡片与回放回归。

跨能力族 discovery 已完成，B0 基础设施、三族 seed/smoke 与 Protocol `b0-2026-09-02-v4` 已冻结。正式 3×2 已完成 6/6：Mechanical/K3=100、Mechanical/GLM=100、Simulation/GLM=100、Simulation/K3=100、Lookdev/K3=90、Lookdev/GLM=90，均 0 hard failure/coreSuccess=true/claimLevel=none，三族同族并列。Mechanical/ Simulation 效率偏向 K3，但 Simulation/K3 出现 2 次 query mutation 和 18 次裸 File Cache 写盘，GLM 无 query mutation但运行更慢。Lookdev 两模型同 90、各扣诚实 10 分：K3 报告声称存在实际没有的 DomeLight；GLM 台账声称 stage 无 error/warning，独立回读发现 2 条 SOP import warning（Target 保守裁为 unverified，按规则 0 分）。GLM lookdev 另有 7 次成功裸 `rop.render()`（均为异步 job + 单次 allow_raw 豁免，因 render_frame ~110s 硬顶）。discovery 阶段结论可进入 B2 归因；最终能力结论仍待 B4 留出解封。生产面不得写实例答案；holdout未解封；大规模改动继续放在整批之后。两工具误选率已按六场正式数据评估：query mutation 2/101（均 simulation/K3），安全收益成立，`houdini_query`/`houdini_exec` 维持两工具保留（§10.5）。B2 归因与 B3 候选门槛见 plan §10；v5 变更单（§11）已批准并冻结为 `b0-2026-09-03-v5`：C1 glm-5.3-flash 声明 `input: [text, image]` 已应用（settings.yaml SHA-256 `13909d44…`，协议新增必填 `execution.settingsFileSha256` 覆盖仓库外 surface），C2 target 输入附报告原文（deterministicEvaluator 升 v3）；`formal-matrix.json` 已重置为 regression 阶段六场 pending；2026-09-04 决定六场回归暂缓：C1/C2 为评审/声明侧变更，v4 两个诚实失分点不由其修复、无可回归失败实例，改 C2 证据包重评 + read_image smoke 轻量验证，整批攒到下一次 agent surface 变更后一次执行。评估定位为发现/确认问题的手段而非目的，不为评估而评估；后续优化计划（O1 人性化 layout 动词、O2 rig skill 默认路由收紧为 KineFX、O3 坑位台账、O4 评审 pass^k 与第二评审模型、O5 精化种子与质量维度）与下一批回归触发条件见 plan §12。

2026-09-04 O1 已落地：`tab_create` 智能落位、`connect` 纠流（`position_adjusted`）、`layout_nodes` 新增 `mode='flow'` 拓扑分层；词表指纹不变（仍 `4f3516dec006`，指纹只绑动词名），但 agent-surface hash 变为 `1c3abd20…`，`benchmark/baseline.json` 已重封；H21/H22 `dsh-layout-flow` 回归通过，live Bridge 冷启动加载验证留待 v6 批次前一并做。O1 属 agent surface 变更，v5 矩阵继续 pending，攒入 v6 整批回归。

2026-09-04 O2 路由与 namespace 修复已落地，但首个自然 KineFX 任务 `7bf34ae9…` 打穿首版回归假阳性：driver skeleton 正确，`attachjointgeo(role=capture)` 的最终刚体保持 rest；旧测试因混合输出总 bbox 随 skeleton 变化而假绿。rig skill 已改为通用 `driver → binding/evaluation → driven deliverable` 三层合同，条件性 recipe 修正为 Capture Packed Geometry → Joint Deform；新回归验证实际 link center/旋转 extent/recovery/boneCapture/无 skeleton polygon，H21/H22 通过。candidate agent-surface hash 为 `6534fde1…`；仍待 Repair/restart 后新 session 的未见刚体正例 + control-shape 反例，未标 released。O3 坑位台账已建立；O4–O5 未动。

2026-09-04 同模型同原题新 session `975f49a0…` 已完成原失败实例正向回归：最终 672 点 driven geometry、逐 piece 刚体不变量、解析 FK、f1/f96 recovery、fixed-camera render、flow layout 与 clean save 均成立；tools 130→92，但仍有 20 failed calls。治理 quality standard 已新增面向弱模型的复杂度门、执行脊柱、版本 fast path、探测阶梯、两次同边界失败换策略、证据失效和七类发布验收；rig reference 加入 H21/H22 验证过的 skeleton/capture 最小 API，作为其他 domain skill 后续标准化的参考实现。candidate agent-surface hash 为 `c8ba7353…`。不得一次性复制通用文案：SOP、Solaris/Karma 必须按各自 trace、fast path 和反例逐项发布。rig 仍待未见层级刚体正例、control-shape 反例及 channel/solver 反例。

2026-09-04 未见维护平台任务 `db2cf0bf…` 成为 K3 反例：最新 rig skill 已加载但 reference 未读，`/obj` 位置被误解为 OBJ hierarchy 授权；SOP 与 parenting 的 `connect` 方向均反，base output 为空，0 验证/渲染/保存后由用户中止。现将规则收敛为：新建几何父子机械/FK 必须 KineFX 且 mutation 前读 §3.1；OBJ parenting 只保留 scene assembly/legacy/explicit user/downstream delivery 四类边界。工具层新增 `set_object_parent(child,parent,keep_world,reason)`，generic `connect`/`disconnect_input` 拒绝 OBJ parenting/unparent，H21/H22 环检测、reason、world-preserve 与回读回归通过。当前源码 50 动词/新指纹待 Repair/restart 和 K3 未见正例/OBJ scene 反例验证。

2026-09-04 DSH 0.1.2 runtime 兼容已实装修复：launcher/manager 支持 process-token cookie 与 slash/generated-args RPC；H21/H22 QtWebEngine 在 DocumentCreation 注入 `AbortSignal.any` 和 `Promise.withResolvers`；vision-toolkit 0.1.40 的唯一旧 `session.events` callsite 由 exact-version fail-closed repair 改用公开 `snapshotEvents()`。新 workspace 合同为“已保存 HIP 父目录即 DSH workspace”，每次 Open Workspace 都在 worker 幂等注册、复用/创建并路由；未保存场景只用仓库外 scratch，绝不回退插件源码。当前 `E:/tmp/test11` workspace 与新 Houdini session 已 live 验证，浏览器 RPC 200；视觉 semantic smoke 仍待跑，不得冒充已验证。

2026-09-04 最新 K3 session `429506d9…` completed，但 Trace 因 client 读取已删除的 `Session.nodes` 静默为空；离线 evidence 为 936 events/35 tools/29 Houdini calls/117 verbs。client 已显式依赖 trajectory，用 DSH 0.1.2 `useTrajectory(eventNodes)` 与 0.1.1 `views.get('trajectory').eventNodes` 双版本 adapter；live UI 的 29、23/29、117、16/50、5 raw reads 与离线证据一致。DSH 更新改为 `dsh-runtime-compatibility.json` 精确白名单：下载不等于激活，未知 latest 不得成为 serving runtime。baseline schema v2 分离 agent surface 与 compatibility surface；新版本必须按 `docs/dsh-update-compatibility.md` 通过 Host RPC、H21/H22 QtWebEngine、Trace、workspace/session、第三方 bundle 门后才能提升。
