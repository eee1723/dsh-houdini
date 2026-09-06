# 可信交付：有界离线原型（2026-09-06）

> 本文保留v5离线阶段证据。后续v6已增加受限Host/Bridge入口，核心观察逻辑移至
> `houdini/python3.11libs/dsh_delivery.py`，离线入口为adapter；当前支持范围与未验收项见
> [可信交付运行时](trusted-delivery-runtime.md)，不要把本文“未接入”当成当前源码状态。

## 决策与状态

不增加第58个动词，不扩长生产skill，不再通过重做同一辆自行车验证提示曝光。
本轮只实现一个离线垂直切片：**冻结义务 → 读取最终输出 → 定位失败 → 局部修正 →
旧证据失效 → 复验 → 数值收据**。生产Host尚未维护此状态，模型侧没有自动获得这项能力。

单独修复的生产风险：connect/disconnect_input 的 allow_foreign 改为keyword-only；共享
ownership guard在owned/direct-call快路径之前拒绝非字符串、空白显式理由。57动词名称不变，
执行合同升级v5以阻止新Host配旧Bridge。未自动重启live；当前source baseline记录候选，
不修改冻结的正式protocol/matrix/holdout/provider配置。

## 实现与边界

代码在开发目录 `tools/prototypes/`，不属于package files，不注册verb，不写入preset/skill：

- `delivery_audit.py`：冻结合同、直接读取最终OUT上的必交primitive groups、复用现有接口与
  控制测试、自动枚举CTRL的全部数值spare controls；没有用例的控制保持unverified。
- 每次receipt读取当前网络、参数表达式/keys、控制schema、frame和真实Polygon输出内容。
  观察到变化时**保守失效全部缓存控制证据**，不是已经实现精确依赖图/事件驱动的Host状态机。
  同几何的接线切换、同值的表达式改动、同路径节点重建也会失效；未变化的重复读取不失效。
- 控制测试只能执行冻结合同中的独立case，不接受模型提交的`passed=True`。测试或恢复异常
  清空缓存并停止；返回结果/contract副本无法改写内部记录。新合同从无测试证据开始。
- 数值全通过仅是`ready_for_independent_review=true`，仍为
  `delivery_status=partial_pending_independent_review`、`semantic_status=unverified`。
  分组标签不证明实际身份/造型；部件最少面数不是产品级评分，缺声明的关系也未获认证。
- 当前仅单一SOP网络、直接子节点、Polygon输出；有数量/内存预算，packed/native/volume
  等不支持的fingerprint保持unverified。接口计算仍复用已有工具，不扩展为实体碰撞求解器。
- 只允许隔离hython主线程，GUI拒绝。没有生产会话绑定、持久恢复、并发/异步job集成，也
  没有外部文件/Python/solver副作用恢复保证。观察边界以本网络及实际输出为限，不能作为
  任意外部依赖的完整缓存证明。生产接入前必须解决这些生命周期边界或明确拒绝相应范围。

没有实现自动修模。局部修正由开发者在回归中用现有动词完成；它验证“修正后能建立新证据”，
不证明弱模型能自主选择正确修正，更不能冒充未见任务质量增益。

## 已完成的验证

### 通用原生Box装配（不是自行车配方）

`tools/tests/dsh-delivery-prototype.test.py`覆盖：

1. 默认接口正确，但一个控制无响应，测试应fail；控制值恢复。
2. 用已有set_parm把原生Box尺寸连接到控制，旧测试失效，重测后数值pass。
3. 部件节点仍然存在/cook正常，但断开总装输入时最终part义务fail；接回后不复活旧pass。
4. 两个部件存在、方向不变、cook正常，移动一件后实际表面接口fail。
5. 同几何源之间换线、同值表达式改变、新增控制、同路径重建、unsupported输出、缺输出，
   都不能继续使用原先通过状态；新暴露的控制不被悄悄漏掉。
6. 合同副本修改、重复/系统保留ID、非有限值、无效计数、未注册case拒绝。

### 原始test9文件，不重生成模型

`fixtures/test9-obligations.json`是**诊断fixture**，仅位于不打包的tools/prototypes，含
上轮已查明的两个控制/胎齿义务，不是给agent的自行车recipe或完整设计合同。
容差在测试前声明，用于判断应有非零响应；未按实际零变化反推合格线。

H21/H22均在隔离进程加载原文件，结果：

| 阶段 | 胎齿（最终OUT） | 两个已声明控制 | 另外17个控制 |
|---|---|---|---|
| 首次检查 | 0面，fail | hub_half/drive_z均fail | 未声明case，unverified |
| 内存中仅补回已有胎齿接线 | 1584面，pass | 旧证据失效，unverified | unverified |
| 重新测试 | pass | 仍fail | unverified |

始终没有把局部修正升级成完整交付；源HIP未保存，SHA256始终为
`2ec19787302b4a139277db223948a5c3aef3b02d5b7664d4db1425dbe527f28f`。
这次未自动修用户test9的实际文件、未修其前叉/链条/盒体造型，也没把缺接口声明的fixture
说成实际前叉检查通过。实际test8接口反例沿用v4已记录证据，本轮新增接口闭环只在通用fixture
验证，避免把开发者手工标组说成模型会自动标组。

验证集合：Node16文件；H21.0.440/H22.0.368各21个Python回归，包括权限参数、交付原型、
raw gate、ownership、caught failure、tab create、OBJ parenting、scene/network/render和
quality contracts。新增原型保留ID边界另在双版本重跑。pack dry-run确认原型/fixture/pycache
未进入发布包；类型编译和diff检查通过。

本机结果路径（开发环境外部诊断产物，不是包内依赖）：

- `Z:/tmp/dsh-review-20260906/v5-test9-repair-final-21.0.440.json`
- `Z:/tmp/dsh-review-20260906/v5-test9-repair-final-22.0.368.json`
- `Z:/tmp/dsh-review-20260906/v5-regressions-21.0.440.json`
- `Z:/tmp/dsh-review-20260906/v5-regressions-22.0.368.json`

## 复现

使用目标Houdini版本的hython；没有绑定live Bridge，也不要求repair/restart：

```text
hython tools/tests/dsh-authorization-arguments.test.py
hython tools/tests/dsh-delivery-prototype.test.py
hython tools/prototypes/audit_saved_sop.py <已保存HIP> <冻结合同JSON> --report <新的报告JSON> --test-controls
hython tools/prototypes/replay_test9_repair.py <原始test9-HIP> <新的报告JSON>
```

最后一个命令是指定hash的旧反例回放，只在内存中改一条线，不是通用修模入口。
report必须是新的JSON文件，不覆盖原文件；控制恢复异常立即终止，不能继续生成绿色报告。
纯审计命令可省略`--test-controls`，则未测控制保持unverified。源文件最后再次核对SHA。

## 下一决策门（不能直接跳到六场生成）

本轮通过的是“机制可运行/能揭示旧失败/可局部复验”，不是自然采用门。
下一步若接入：只在一个受限SOP任务入口让Host绑定会话、保存冻结合同并回传紧凑缺口摘要；
临时控制测试仍经Bridge主线程/ownership，query不能触发，异步job未完成时不能发收据，
重启或HIP变化清空证据。不能把这个离线Python对象直接塞进任意exec namespace就宣布完成。

更重要的待证假设：**模型能否低负担地产生正确义务，并依据反例完成局部纠正。**
不能只把同一长schema塞回skill，把最难的工作重新交给K3；优先从已有部件/控制声明收集
候选合同，独立复核覆盖，再按阶段提供最小接口信息。当前尚无自动契约推导或自主纠正证据。

该小入口通过后才冻结一次两题×三路线的决策试验（K3+候选、K3+原始MCP、GPT6参考），
同参考/LOD/预算，不中途提示、不解封现有holdout。若仍将核心缺件/无效控制判pass，候选
不发布；若两题未显示质量或同质量成本优势，停止扩工具/skill，收缩领域或调整产品定位。
不把拒绝率、动词采用率、测试绿灯当作最终质量提升。
