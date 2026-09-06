# 受限可信交付入口 v8（历史，v9已退役生产流程）

2026-09-07：用户授权移除登记/累计收据/缓存状态机，改为独立资产评审；当前使用说明见
[independent-asset-review.md](independent-asset-review.md)。以下保留v8当时的实现与验收事实，
不是当前可调用接口。旧实现和专属测试移至不打包的`tools/prototypes/retired-delivery/`。

2026-09-06。v7在e8c90d2b中已真实被调用并完成登记/失效/复验，但验证成本偏高。
v8按表示区分融合拓扑与独立表面，成功受限展示整理可在重新观察一致后复用数值证据，
并排除bgeo导出头时间戳造成的假恢复失败。未重启live v8，未证明未见任务质量/效率提升。
仍为5个工具、57动词；没有新增造型算法、自动修模或全局final-answer拦截。

## 这次接入了什么

- `src/delivery.ts`按DSH工具上下文中的session/call管理冻结合同、控制证据和待检查摘要。
  模型不能传owner、revision或pass结果；返回值是副本，跨session不能复用。
- `houdini_exec`有一个typed `delivery`分支，不能与code/allow_raw混用；query无此入口。
- `HoudiniBridge`跟踪修改请求的generation和pending状态，提交job同样使旧证据失效。
  模型下次exec回包可见紧凑状态提醒，不会在每次修改后自动执行昂贵检查。
- Bridge `/delivery`走同一主线程队列；结构化服务直接调用检查层，无字符串拼接eval。
  活动job阻止收据，检查期间不接收新job。控制写操作仍经原有ownership/恢复合同。
- 每次check新读最终几何、网络/参数/keys/schema；变更后全量保守失效控制缓存。
  它不是精确依赖图，不是实时GUI监听器：旧收据是某次观察的事实，交付前必须再check。
- runtime UUID、HIP load/clear generation、HIP路径绑定；变化后重新登记。Host缓存只在
  内存，重启不加载旧pass。每Host最多128个session，超限拒绝；当前不持久化/迁移合同。
- 共用Houdini侧`dsh_delivery.py`，旧离线入口变为adapter，没有复制第二套检查实现。

## v8：减少不适用检查与无效重测

### 按表示登记连接义务

独立表面仍用interfaces。Boolean融合后的Polygon部件使用可选topology，例如：

```json
"topology": [{"id":"connection","groups":["part_a","part_b"],"require_closed":true}]
```

groups必须来自已登记parts，至少两组非空、不重叠primitive组；读取实际最终表面，检查共享
边连通、闭合、非流形边、绕向冲突和退化边/面。基准与每次控制扰动都复查，避免bbox响应
通过但融合部件已经断开。require_closed默认true；false只表示允许开放表面，仍要求共享边
连通。未焊接接触、仅共点、空间重叠不算共享面；NURBS/原生quadric等对该方法unverified。
它不证明自交、体积内部关系、强度或目标形状。inspect观察到完整闭合共享面时给方法候选，
不会替用户决定哪些部件必须交付。共享点距离检查失败时返回正确方法提示。

Host收据保留contract_changes（added/removed/changed）和本次复用/失效case ID；换方法
不能假装从未有连接义务。该记录不是自然语言需求完整性裁判，也不禁止明确修订合同。

### 有条件的数值证据复用

Bridge独立分析Python AST，仅识别小型字面量调用/结果打包：允许的查询和render_view、
layout_nodes、sop_set_output、scene_save等。禁止在这项证书中使用import、任意HOM、别名/
重绑定、未知调用、循环、异常处理等；不满足时照常执行既有安全门，但数值证据必须失效。
这不是Python沙箱，也不是由agent提供的“我没有修改”标志。

只有成功且没有失败检查/用户状态恢复失败的候选程序，Bridge才回报deliveryEffect=reobserve。
Host仍重新核对runtime/HIP绑定、节点身份、图/参数/几何；真正改变就失效。独立activity代际
确保观察与任何并发操作交错时不接受旧证据；job、未知/失败操作、实际setter均保守失效。
即使set_parm设回同一值也不获展示豁免。画面像素需重看不能用此数值缓存替代。

不会承诺复用e8原始轨迹中所有重测：那里还有render_view参数错误，失败调用在v8仍失效。
验证的收益是**无失败的**查询/展示整理序列不再自动要求重跑所有数值case，不是人为改低失败率。

### 完整恢复指纹，只排除导出时间

回归捕获同一几何bgeo在相邻秒唯一变化为顶层info.date。现用Houdini自带hjson解析完整bgeo，
只排除此导出头时间戳；保持拓扑、全部属性（包括用户名为date的属性）、primitive数据/原生
形状、各类group与其余头字段。未知root格式/预算超限拒绝，不降为P-only。Packed等既有
unsupported边界不变，注入的真实恢复故障仍抛错。依据为H21本机hjson/Geometry.data文档和
捕获payload逐字段比较，双版本回归验证；不是任意忽略不同的序列化数据。

### 本轮证据与未覆盖

Node17与H21/H22各25项回归；新增surface-topology、evidence-reuse，并扩展真实Node→HTTP→
主线程→Host链路。旧支架test2.hip的临时副本完成4case后，查help、布局/设输出、保存三类
操作后每次都复用4case，零额外控制测试；实际改参仍撤销四项并要求复验。原文件sha保持
`63f833ded74897f3d0cdf8c37df05d600c0033595b9a0bdb1c7a7bc64f5b61af`。
回放：`tools/prototypes/replay_delivery_reuse.py`，结果位于本机
`Z:/tmp/dsh-review-20260906/v8-reuse-21.0.440.json`及`v8-reuse-22.0.368.json`。
这些是隔离临时副本（save写副本，不写源HIP）；fixture provenance仅在该独立进程中模拟，
不能用来绕过live ownership。OpenGL部分只在策略测试中用render服务替身，未做live GUI
渲染复用验收。SOP skill按治理窄修方法路由，没有新增skill或把支架配方写入生产规则。

## 支持边界

只支持单网络的直接SOP子节点、少量原生Box/Transform/Merge/Boolean/Group/Create/Copy/Sweep等
白名单节点。VEX/Python/File/Solver/Subnet、外部引用、Python/外部命令表达式、回调拒绝；
最终输出为Polygon，最多128直属节点、15000点、10000面。Unsupported不能冒充pass。
检查外来网络是读取，测试外来控制必须被拒绝；登记合同本身不是修改授权。

这是有意缩小的接入试验，不意味着以后只支持原生节点。复杂自行车/VEX现阶段仍走普通
工作流并明确可信交付不可用，不能要求原型对它们出具保证。扩域前需独立证明副作用、
依赖、恢复和指纹语义；Raw Gate也不是任意本地Python的安全沙箱。

目前所有数值检查通过也只返回`ready_for_independent_review=true`，
`delivery_status=partial_pending_independent_review`及`semantic_status=unverified`。
分组计数不证明造型/真实性；接口仅验证声明表面距离；每个控制的正确预期仍须来自设计要求。
首次inspect只提供实际名称/当前值，不能拿当前测量结果反推合格线。

## v7：选型前准入与联合参数条件

`node_info(parent,type)`的delivery字段直接使用运行时同一准入策略；Boolean附说明：agroup/
bgroup是输入选择，不是输出组名，部件标识宜在输入上游建立并在实际输出回读。
`build_module(dry_run=True)`和普通build结果也报告新模块类型是否可进入delivery。此字段
不证明实际参数、已有兄弟节点、外部引用或最终几何合格；普通模块构建不会因delivery不支持
而被一律禁止，仍可用于明确披露边界的草稿任务。

`inspect`返回精确metric枚举和domain格式。可在登记contract中增加可选domain数组，例如：

```json
"domain": [
  {"id":"positive_thickness","left":"thickness","op":"gt","right":0},
  {"id":"thickness_below_width","left":"thickness","op":"lt","right":"width"},
  {"id":"thickness_below_height","left":"thickness","op":"lt","right":"height"}
]
```

这是格式示例，条件由任务设计决定，不是所有模型的通用强制关系。最多32条；left为数值spare
参数名，right为另一个数值spare名或有限常量；op仅lt/le/gt/ge/eq/ne。不接受表达式代码，
不自动改值/求解。receipt检测当前条件；test_controls也接受同样的可选keyword-only domain。
独立无key控制可在写前拒绝越界候选值；有表达式/动画耦合时不猜其他参数变化，而是在实际
赋值后检查，再按原有合同恢复。基准条件失败不测试；零写入拒绝结果明确parameter_writes=0。

条件通过只证明当前或本次测试的数值关系；没有domain也不代表整个参数域已经正确。保留
`semantic_status=unverified`和独立评审要求。依靠表达式联动、部件消失或测试后外部改参时，
仍必须重新读取实际输出和控制测试，不能因返回默认值自动恢复旧pass。

## 模型操作（全部通过 houdini_exec 的delivery参数）

先在node_info核对选型准入，再建集中控制、最小原生模块及稳定部件组，然后inspect。
以下名称和值只是schema示例，不是用户任务配方。

```json
{"delivery":{"action":"inspect","scope":{"parent":"/obj/asset","output":"/obj/asset/OUT","controller":"/obj/asset/CTRL"}}}
```

返回groups/controls后，由用户目标决定必交parts、控制预期和必要接口，登记：

```json
{"delivery":{"action":"register","contract":{
  "parent":"/obj/asset","output":"/obj/asset/OUT","controller":"/obj/asset/CTRL",
  "parts":[{"id":"body","group":"body","min_prims":6}],
  "controls":[{"id":"length_response","parm":"length","value":1.2,
    "expectations":[{"group":"body","metric":"bounds_size","axis":0,"delta":[0.199,0.201]}]}],
  "interfaces":[]
}}}
```

示例假定基准length=1且部件x长度一比一响应；不得不看任务就复制容差。需要连接时interfaces
使用现有geo_check_interfaces合同。所有数值spare控制自动列入覆盖义务，未登记case不消失。

```json
{"delivery":{"action":"test_control","case_id":"length_response"}}
{"delivery":{"action":"check"}}
```

修正仍用普通code分支的已有动词；修正后check并重跑登记case。不能把新code和delivery塞进
同一次请求，也不能用todo或一句pass覆写系统证据。重新register会丢弃全部旧控制证据。

## 回归与后续现场操作

`delivery-state.test.mjs`覆盖跨session、合同副本、mutation/revision失效、并发、超时、
运行时/HIP绑定变化、Host重启与五工具互斥入口。
`dsh-delivery-service.test.py`启动隔离HTTP server和Node工具调用，实际经过主线程pump，
验证dead control→局部修正→旧证据失效→复验、丢件、跨session修改拒绝、job、生命周期和
不支持的节点。旧离线交付回归继续验证接口反例与指纹/结果失效。

本轮Node17文件、H21.0.440/H22.0.368各22项Python回归通过。双版本日志位于
`Z:/tmp/dsh-review-20260906/v6-regressions-21.0.440.json`与`v6-regressions-22.0.368.json`。
这些是真实服务链路的隔离回归，不是当前GUI runtime或K3自然任务验收。

上述22项是v6历史验证。v7为Node17、H21/H22各23项，包括新增
`dsh-delivery-domain.test.py`及扩展的真实Node/HTTP/主线程Boolean链路。独立无key候选写前
拒绝、表达式耦合实际值检查、恢复、外部客户端改参失效均覆盖。
`tools/prototypes/replay_test10_delivery.py`复用原始7节点HIP，两版本成功inspect并测试三控制；
厚度7/高度6时同时检出domain失败和vertical空组，恢复后旧证据失效，复验才能pass。
原HIP SHA256始终`9a487f344898a1ef1d1370392e6c4d6108ed1d414c9856005b3f45be9a464a40`，
未保存源文件。报告：`Z:/tmp/dsh-review-20260906/v7-test10-delivery-21.json`与`-22.json`；
全量日志为同目录`v7-regressions-21.0.440.json`、`v7-regressions-22.0.368.json`。
这是开发侧旧资产回归，不是K3新会话完成，也不修用户资产本身。

v7接入/按提示采用已经由e8c90d2b证明，**停止重复同一支架的加载与采用smoke**。
开发侧v8回归已复用旧资产；下次正常任务需要新功能时再保存场景、Repair and restart runtime。
之后选择一个不同的小型原生任务，观察融合连接义务是否进入topology、正常展示整理后
check是否复用数值case、真实改参是否仍失效。不要规定完整节点答案来制造顺利路径，也
不要把收据pass当成审美/全参数空间验收。

完整自然控制流程仍须用当前session拥有的测试节点；重启后旧节点变foreign，不能通过登记
合同绕开ownership。未知/失败路径和live GUI渲染复用仍要保持保守边界。是否进入两题×三
路线对照，以验证成本是否确实下降及未见任务质量为依据；不因开发测试全绿立即扩大矩阵。

没有自动重启用户Houdini、没有改写test9/test10或生成新用户资产。v8仍是候选，不能从开发
回归推导“弱模型已接近强模型”。
