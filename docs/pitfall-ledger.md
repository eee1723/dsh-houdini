# 坑位台账（Pitfall Ledger）

> 2026-09-04 建立（plan §12 O3）。人工策展的跨任务坑位清单，每批评测/开发复盘时维护。
>
> 归档规则（按强度，能往左沉就不留在右）：
>
> 1. **动词 guard**：能被工具确定性拦截/纠正的，进动词层（Raw Gate、ownership、resolve 修复）；
> 2. **skill recipe**：属于"做法"的，进对应 skill 的 reference（按需加载）；
> 3. **评测侧**：评审/协议缺口，进 plan 变更单；
> 4. **本台账**：以上都不满足的跨会话长尾，以及所有已沉淀条目的索引。
>
> 原则：能用 guard 挡的不用 skill 教，能用 skill 教的不靠记忆猜。记忆系统暂缓
> （非确定性 + 过期风险 + 污染评测可复现性），本台账就是确定性版本的记忆。

| # | 坑 | 首次证据 | 沉淀层 | 状态 |
|---|---|---|---|---|
| L01 | `kinefx::*` 等 namespace 注册类型过不了 `tab_create`（`createNode(exact_type_name=True)` 拒裸别名） | 2026-09-04 O2 探针 | 动词（`resolve_latest_type` 支持 namespace 解析） | ✅ 已修复 |
| L02 | Rig Pose `group{i}` 必须 `@name=<joint>`，裸 joint 名命中空组且只有 warning | 同上 | skill reference §3.1 | ✅ 已沉淀 |
| L03 | `rigdoctor` 的 `inittransforms` 默认关，不初始化 `transform`/`localtransform` | 同上 | skill reference §3.1 | ✅ 已沉淀 |
| L04 | `attachjointgeo` 需要 skeleton 带 16-float `rest_transform`，缺它报 "No valid roots found"；输入序 = (skeleton, shape library) | 同上 | skill reference §3.1 | ✅ 已沉淀 |
| L05 | H22 裸名 `rigpose` 命中接口不同的 `apex::rigpose`；跨版本 recipe 必须钉 `kinefx::` | 同上 | skill reference §3.1 + tool-design resolve 条目 | ✅ 已沉淀 |
| L06 | `/obj` 下 subnet 的 childTypeCategory 是 Object 不是 SOP；SOP 链要建在 `geo` 内 | 同上 | skill reference §3.1 | ✅ 已沉淀 |
| L07 | Raw Gate 拦截"同一 exec 里动词已覆盖调用 + 低层调用混排"；拆开发送，低层部分单独一次裸调用 | 同上 | skill reference §3.1 | ✅ 已沉淀 |
| L08 | 最终报告台账与可回读事实不符（虚构灯光 / 漏报 warning），跨模型重复 | v4 lookdev K3+GLM | 评测侧（C2 报告原文入 target 输入；honest 重评待做） | 🔶 观察中 |
| L09 | 无动词覆盖的长渲染（>110s）被迫多次 allow_raw 豁免 | v4 lookdev/GLM | 待第二个任务复现才立项动词（B3 门槛） | ⏳ 等复现 |
| L10 | File Cache 写盘无动词，裸 `pressButton` 高频重复 | v4 simulation/K3 | 待第二个任务复现才立项动词（B3 门槛） | ⏳ 等复现 |
| L11 | hython 进程背靠背连跑偶发启动失败（license/启动争用），单独跑全绿；判断回归真假失败须单独复跑 | 2026-09-04 O2 回归 | 本台账（执行习惯） | ✅ 已记录 |
| L12 | `set_keyframes` 的 channels 是 `{parm: [key spec]}` dict，不是 list；误用报明确错误 | 2026-09-04 O2 探针 | 已在 verb_help 文档，错误信息自纠充分 | ✅ 已记录 |
| L13 | driver skeleton / `jointgeo` metadata / 混合总 bbox 在动，不等于最终 rigid geometry 在动；Attach Joint Geometry 不是 skin deformation | `7bf34ae9` + H21/H22 复现；`975f49a0` 正向 | rig skill 三层交付合同 + corrected KineFX regression；trace HTA-031 | ✅ 原题回归通过，待未见正例/反例 |
| L14 | “在 `/obj` 下”被误读为 OBJ hierarchy 授权；generic `connect` 又使 parenting 方向反转 | `db2cf0bf` | rig 路由 + `set_object_parent` / connect guard；trace HTA-032 | ✅ H21/H22 guard 通过，待新 session |
