# 独立资产评审 v9（候选）

2026-09-07。用户明确要求移除delivery重流程，让独立评审agent自主调整参数、做效果测试并
一次汇总，不在作者/评审者之间逐参数转发。保持五工具/57动词；第六个skill为
`houdini-asset-review`。不是新增长期验收账本或自动修模器。

## 入口与生命周期

作者在明确交付SOP就绪后调用：

```json
{"review":{"parent":"/obj/asset","output":"/obj/asset/OUT","controller":"/obj/asset/CTRL"}}
```

这是`houdini_exec`参数；与code/allow_raw/review_test互斥。controller可省略，表示只检查
当前输出/基准图，不授予改参能力。当前入口要求parent/output/controller属于原作者、
output/controller为同一SOP网络直属节点。已有foreign或非SOP资产使用原有只读审查路径，
不因审查身份取得任意节点权限。

Host用DSH公开`subagents.start('spawn',request)`启动前台one-shot子agent，不fork作者
上下文；模型路线继承作者配置，没有新增模型/provider设置。Host从parent.session的
snapshotEvents读取原始用户消息、实际问答，原始图片保持附件引用转交；作者成功总结不
作为验收标准。应用自有review persona/skill，并在创建时限制工具为当前可见的query、exec、
read_image、skill、read。shell/写文件/多层委派/jobs不在允许清单。

作者等待一次结果；评审者自行批测/读图。必要修模回到作者，一次汇总问题后按影响复审，
不用持续聊天。10分钟上限、父调用取消、异常退出均停止子agent并撤销权限。Host不会持久化
测试pass或数值缓存；长图像/时序任务超出预算时保留未验收项，不假装完整。

## 自主测试

仅Host绑定的当前子agent可以调用：

```json
{"review_test":{"tests":[{"id":"size_response","values":{"size":1.2}}],"views":["iso"]}}
```

以上仅为schema示例，不是固定测试值。先读实际参数，再选择设计有效且不同于当前的值。
tests每批最多16项；可附expectations、interfaces、topology、domain，字段与底层检查器
一致。未声明expectations时，返回responsive/unchanged并保留unverified；参数有响应不
等于设计正确。没有register/check/case缓存，回包只包含本批关键证据。

`review_test={}`读取网络健康、组与控制概况；`views`配空tests取得基准图。支持最多2个
iso/front/side/top视角；每批含基准最多8张。测试过程在同一Houdini主线程工作项内完成：
基准取图→保存参数/keys/frame→临时赋值→cook/测量/产图→恢复→核对完整bgeo恢复。图片
通过原media relay提供给read_image，不把文件/像素通过当作语义通过。

参数状态不同可能自动重新取景；返回framing metadata，评审不得把相机差异解释为纯几何
像素变化。真正固定相机跨参数图像比较尚不是本入口的保证；动画仍沿用已有同framing_frame
要求。没有GUI时图片为unverified，不退回创建正式ROP或替模型猜图。

## 权限与不支持边界

- Bridge持有不暴露给模型的随机短期令牌，绑定原作者、唯一child、节点身份、HIP和起始
  网络/参数/frame状态。重启不保留；HIP/节点/参数变化后拒绝旧评审，不覆盖用户改值。
- `_review_parameter_access`仅在受控检查器调用栈内临时允许该child修改绑定controller；
  不改节点provenance，不能扩到另一个控制器或场景节点。普通exec修改、保存、删节点、job
  在评审期被Host和Bridge拒绝。原有Raw Gate、主线程、ownership都保留。
- 临时扰动限定有界原生无外部副作用SOP（含Tube/Sphere/Boolean），128直属节点；外部引用、
  回调、Python/VEX/File/Solver/Subnet等不在可恢复测试范围，写前返回unverified/0 writes。
  这不是普通建模的类型门禁，也不代表这些资产不能通过只读材料评审。
- 截图用户状态恢复异常必须逃出批处理并阻断下一case，即使参数恢复成功也不能洗成pass。
- 没有把任意Python变成安全沙箱，没有机械强度/实体碰撞/全参数组合或模型审美保证。
- 父调用和子agent不并发修改场景；人工变化通过每批与结束时绑定核对发现。HTTP客户端
  异常失联的权限最长保留到10分钟期限，不能跨恢复后继续使用。

## 清理范围

移除生产`src/delivery.ts`、`dsh_delivery.py`、`dsh_execution_effects.py`、`/delivery`路由、
Host generation/cache及node_info/build_module delivery准入字段；专属测试/源码保留到
`tools/prototypes/retired-delivery/`，不打包不运行。tsc遗留的lib/delivery.js/.d.ts由构建
清理脚本删除。历史原型脚本仅供旧版复现，不代表当前入口。

保留verify_network/build_module、geo_check_interfaces、test_controls、topology/domain与
完整恢复指纹，以及其通用正反例。SOP只替换方法路由，不写桌子/支架等对象配方。trace
提取将typed调用与裸HOM区分；父review报告的深入业务事实仍应回读对应child trace，不从
作者的单条summary猜测已测全部条件。

## 来源、验证与未覆盖

来源：用户对两次桌子trace的明确取舍；旧trace的累计收据/逐case往返证据；DSH本机
0.1.2-rc.1包的SubagentStartRequest/startInProcessRun/工具限制公开实现；本仓库的
参数快照、恢复、render_view和main-thread合同。规则是通用评审职责，不含实例答案。

CREATE asset-review：与trace历史分析不同，直接评审当前交付并受控实验；UPDATE SOP与
guidance：移除delivery路由；DEPRECATE生产delivery：用户明确授权，不凭单例采用率删除
底层检查器。skill-creator和houdini-skill-governance结构/作用域要求共同约束本次工作。

Node回归覆盖原始要求/附件转交、工具限制、启动publication竞态、失败/取消/清理、五工具
互斥入口；H21/H22回归覆盖所有权、伪造/过期令牌、批测、响应模式、截图/恢复故障、外部
改参、unsupported和主线程。真实Node→HTTP→主线程→Host链路使用确定性子agent替身。
独立skill前向检查覆盖连接失败、简单明确不委派/不渲染、unsupported模拟三个隔离情境。

最终本地验证：`npm test`为17个Node文件全过；H21.0.440/H22.0.368各24个Python脚本
全过（含截图恢复错误传播及过期权限收口）。skill-creator quick_validate通过，治理审计
6skills/6registrations/0issues；npm pack dry-run 70文件，包含新skill/runtime，不含退役
delivery模块或Python缓存。日志在`tools/out/v9-regressions-21.0.440.json`与`-22.0.368.json`。
只读health仍为live v8/57、无活动job；当前源码为v9，matchesBaseline保持false。

**候选状态**：这些不是真实DSH新模型评审会话，不证明质量或效率增益。实际GUI/OpenGL
扰动产图与新session权限/skill曝光仍待用户下一次正常任务验收；没有自动重启live runtime、
修改用户HIP、解封holdout或扩张正式评测矩阵。

回退必须整体回到上一执行合同并重新生成目录/构建、重启两端，不能只恢复旧提示或只撤销
权限校验。历史代码已保留；本轮开始前工作树本来非clean，回退不得覆盖其他未提交修改。
