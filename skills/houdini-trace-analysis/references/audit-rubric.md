# Houdini trace 审计量表

## 目录

1. 证据边界
2. 任务契约与完成判定
3. 轨迹阶段与推进逻辑
4. 工具机会矩阵
5. 动词组合的保留、补充、拆分与合并
6. Houdini 领域逻辑
7. 分模块验证阶梯
8. 视觉、渲染和动画验证
9. 效率、恢复和卫生
10. 证据强度与产品决策
11. 标准报告模板
12. Skill 演化协议

## 1. 证据边界

必须同时使用三层证据：

- 原始层：用户/assistant 消息、tool call、tool result、turn 结束状态。
- 结构层：工具数量、动词 ledger、失败、advisory、代码长度、重复调用、帧间 diff。
- Houdini 层：节点类型、拓扑、参数、属性、点/面/顶点、局部 bbox、cook 状态、显示旗标、帧依赖和渲染结果。

报告中的每个重要结论标注 `步骤 #N HH:MM:SS`、事件 seq 或用户原话。HTML 报告用于导航；JSON evidence 和原始 session 才是事实源。

先检查 evidence 的 `capabilitySnapshots`。只有当某能力在该步骤之前已出现在 request header/
skill catalog 或能由当时工具契约合理发现时，才允许标 `MISSED`；用当前仓库目录回看旧 trace
时，新加入的工具必须标“当时未曝光”，不能倒果为因。

不要把以下内容混为一谈：

- tool 返回错误。
- tool 成功但某个 verb 失败。
- tool/verb 都成功但节点结果语义错误。
- 结果正确但没有完成保存、清理、说明或用户验收。

失败 exec 另查 `rollbackSteps`：`applied=true` 表示 Houdini undoable scene edits 已撤销，
不表示文件/HDA 库等外部副作用消失；`supported=false` 的 headless 失败仍可能留半成品。

## 2. 任务契约与完成判定

从用户消息提取可验证契约：

| 维度 | 例子 | 完成证据 |
|---|---|---|
| 场景产物 | 程序化草地网络 | 节点存在、拓扑合理、参数可编辑 |
| 形态 | 草叶有宽度、密度合理 | 单株/复制后局部几何验证 + 中性视觉检查 |
| 动态 | 风吹麦浪 | 相隔帧的几何/图像差异，且差异方向符合风场 |
| 运行健康 | 无 cook 错误 | 关键节点 errors 为空；warning 已解决或解释 |
| 用户界面 | 用户视口可见 | 仅当用户关心屏幕时，用 viewport_screenshot 诊断 |
| 交付 | 保存/路径/说明 | 明确文件、节点、控制参数和限制；最终消息存在 |

完成状态只能是：

- `完成`：全部核心契约有证据且已交付。
- `部分完成`：部分目标成立，但核心形态/动画/交付至少一项缺失。
- `未完成`：核心目标没有验证、产物错误，或会话无交付地结束。
- `不可判定`：trace 缺失必要结果；列出缺失证据，不猜。

若最后事件是 tool result、最后 todo 仍 pending/in_progress、最后 A/B 验证失败或没有 assistant 交付，不能判“完成”。

## 3. 轨迹阶段与推进逻辑

用状态跃迁而非 assistant 文案划阶段：

1. 检查：版本、HIP、现有节点、帧范围、用户上下文。
2. 设计：选择 Houdini 原生模块和数据契约；明确验证点。
3. 构建：建立最小网络，避免一条超长 exec 在中途失败后留下不明半成品。
4. 模块验证：逐节点/逐分支验证输入、输出和局部不变量。
5. 集成：合并分支，处理属性和 warning。
6. 静态视觉：agent 自有 render_view；先客观 check，再中性识图。
7. 时序验证：至少 A/B 两帧，验证动态幅度与空间传播。
8. 清理交付：删除 probe、恢复显示状态、布局、保存/说明、更新 todo。

标记反模式：

- 在模块验证前宣称“网络成功”。
- aggregate bbox/点数通过即判形态正确。
- 几何异常时优先调相机、灯光、gamma 或视觉 prompt。
- 连续失败后只改 API 拼写，不回到上一稳定状态。
- 为验证创建 probe 后未恢复接线或删除节点。
- 用户纠正后没有重新核对完整任务契约。

## 4. 工具机会矩阵

对“与本次任务相关”的每个能力使用以下唯一标签：

- `USED_RIGHT`：调用时机、参数和结果消费正确。
- `MISSED`：已有能力与当前意图直接匹配，但 agent 走裸 API、猜测或绕路。
- `MISUSED`：调用了工具，但语义/参数/结果解释不正确。
- `TOOL_BUG`：工具实现或契约导致错误、状态污染或不可操作报错。
- `MISSING`：目录中没有能表达该通用意图的能力，且重复手写成本高或风险大。
- `NOT_APPLICABLE`：本任务不需要；不能用来支持删除。
- `REDUNDANT_CANDIDATE`、`MERGE_CANDIDATE`、`SPLIT_CANDIDATE`：只用于跨 trace 产品建议，必须附证据强度。

必查机会：

- 发现节点：`find_nodes`，不要默认裸遍历 `/obj`。
- 拓扑诊断：`graph`，尤其在接线或属性来源混乱时。
- 参数导航：`list_parms`；参数意图：`read_parms`。
- 同一节点三项以上赋值：优先 `set_parms`。
- 动词签名/返回形状不确定：先 `verb_help(name)`；若 agent 先制造一次失败或读取仓库源码才发现契约，标记为可避免的 discoverability 失败。
- SOP 创建：`search_tab_menu`/`tab_create`；避免猜旧节点或错误版本。
- 显示：SOP 用 `sop_set_output/sop_output_node`，OBJ 用 `set_object_visible/visible_objects`；旧 `set_display/display_node` 只作兼容。检查是否错误混用 singular/plural context。
- cook/状态：`cook_node` + `describe`，但不得忽略 warning。
- 属性值：`geo_attrib_stats`；若局部形态仍不可证，记录新的几何自省缺口。
- 视觉验证：`render_view`；交付 ROP 才用 `render_frame`。
- 用户屏幕问题：`viewport_screenshot` 仅作诊断。

## 5. 动词组合的保留、补充、拆分与合并

### 保留

即使低频，只要语义独立、风险边界不同或是关键逃生能力，就应保留。零使用只说明本 trace 不适用或采用率低。

### 补充

同时满足以下条件时列 `MISSING`：

1. 意图可跨任务复用，不是某个草地/镜头的专用操作。
2. 当前需要多段易错裸 hou/VEX 或多次探测。
3. 封装能加入校验、状态恢复或更诚实的返回。
4. 已有动词不能自然扩展覆盖。

### 合并

只有两项能力的用户意图、生命周期、副作用和返回契约基本相同，且 trace 显示 agent 经常选错，才考虑合并。`set_parm` 与 `set_parms` 是 primitive + batch，不因名字近就合并。

### 拆分

当同名动词跨 context 有不同基数、所有权或副作用时拆分或改为 context-aware。例如 SOP 网络只有一个 display child，而 OBJ 可有多个可见对象；单一“display node”契约若假设错误，就必须拆分或显式返回不同形状。

### 删除

至少满足：三个以上多样 trace 中无独立价值；有等价且更安全的替代；迁移路径明确；没有诊断/逃生用途。单 trace 不允许建议删除。

## 6. Houdini 领域逻辑

### 节点类型和模块

- 选择节点前确认 Tab Menu 类型和最新版；优先 Houdini 语义正确的 SOP，而非熟悉但过时的 SOP。
- Copy to Points 应承担模板点 orient/pscale/N/up 的实例变换；使用经典 Copy 后手写变换需要强证据。
- 形变和成形的顺序必须保留数据：通常先变形中心线/曲面，再 Sweep/PolyWire 生成厚度，比生成截面后用错误 rest 坐标重建更安全。
- 草叶等扁平对象优先 Sweep/skin/ribbon 语义；PolyWire 是管状截面，不应无理由替代叶片模块。

### 数据流和属性

对每个关键边界写出 `输入属性 → 操作 → 输出属性`。检查：

- 属性 class（point/prim/vertex/detail）是否正确。
- Copy/Merge 后属性是否传递、缺失、默认初始化或冲突。
- rest/local 坐标是在最终拓扑之前还是之后捕获。
- per-instance 属性是否在复制后仍存在。
- warning 中的 N/uv/Cd 等是否影响显示、材质或下游运算。

### Cook 和缓存

- 每次改接线/代码后 cook 目标分支；需要时强制更新。
- 渲染字节长期完全相同而场景已变，优先怀疑未 cook、显示对象错误或 ROP 缓存。
- 性能问题使用节点 cook 时间和 SideFX Performance Monitor；工具调用次数不是 Houdini cook 性能。

### 显示和所有权

- 区分 SOP display/render flag、OBJ visibility、用户 viewport 和 agent-owned camera/ROP。
- agent 验证管线不得改变用户视口或永久抢走对象可见性。
- 创建 camera/light/null 后核对并恢复原有 OBJ 显示状态。

## 7. 分模块验证阶梯

复杂程序化网络必须由小到大验证：

1. 源数据：地形或输入几何。
2. 最小生成单元：单株草叶、单块碎片、单个实例。
3. 成形后：宽度、面积、法线、UV、局部 bbox。
4. 模板点：数量、orient/pscale/id/phase 等。
5. 复制/实例后：随机抽样单个 piece 的局部 bbox 和属性。
6. 变形后：根部固定、尖端位移、面积/厚度未退化。
7. Merge/输出：属性一致、warning 解释、显示旗标正确。
8. 静态渲染。
9. 多帧差异。

“全场景 bbox 高度正常”无法证明每个草叶有宽度；“点数很多”无法证明拓扑没有重合。若现有工具无法低成本检查 piece/local extent，应列为通用几何自省缺口。

## 8. 视觉、渲染和动画验证

### 静态视觉

1. `cook_node`/模块不变量先通过。
2. `render_view` 返回非空、合理 content bbox 和亮度。
3. 第一轮视觉 prompt 只问“描述可见几何、颜色、位置、异常”，不说“这是成功的草地”。
4. 第二轮才按用户目标核验草叶、密度、风向等。
5. 视觉结论与数值冲突时回到几何，不用 prompt 说服视觉模型。

### 动画

- 至少选两帧，帧距足以覆盖相位变化。
- 比较几何样本或 render diff；仅文件大小不同不够。
- `mean_abs_diff≈0`、max diff 仅 1 灰阶时，按静态或缓存问题处理。
- 几何 diff 明显非零只证明“数据随时间变化”，不证明运动符合用户语义。继续验证锚点、活动区、方向和空间传播。若固定相机 A/B 暴露明确的结构性反例（完全静止、方向相反、主体缺失），完成门失败；若节点/数据/时间语义均通过而静帧只是不足以裁定细微动态或审美力度，可停止追图并标记“视觉待用户播放判断”，但不能写成“视觉已确认通过”。
- render A/B 必须使用完全相同的相机与构图。逐帧按动态 bbox 自动重取景时，先比较返回的 camera `center/eye/dist/direction`；任一变化都会把相机漂移混入 pixel diff，该 diff 只能证明两张图不同，不能证明几何运动。
- 验证根部近似固定、尖端运动更大、波峰沿风向传播；不能只看“画面动了”。

### Render 工具边界

- `render_view(EXPLICIT_SOP)`：agent 自有快速验证，显式 SOP 经隐藏 proxy + forceobjects；检查 fingerprints、stale、状态恢复、确定性 headlight/Cd 和用户 display 漂移隔离。
- 动画 A/B 给每次 `render_view` 传同一 `framing_frame`；不同 framing metadata 下的 pixel diff 不作纯几何运动证据。
- `render_frame`：已有 ROP 的正式或自定义构图渲染，不应承担反复修复 `render_view` 的职责。
- `viewport_screenshot`：用户屏幕诊断，不是 agent 自证成功的主路径。

## 9. 效率、恢复和卫生

统计并解释：

- 首次正确模块产物时间、首次视觉证据时间、用户纠正时间、最终交付时间。
- 构建、几何调试、渲染调试各占多少调用/分钟。
- 同类硬失败是否连续发生；是否在第三次前改变策略。
- 三项以上 `set_parm` 是否可批量。
- 是否反复全文重发 VEX/Python；能否局部 patch。
- 是否创建并清理 test box/light/probe/camera。
- 是否恢复 display/ROP/frame，是否保存或说明未保存。

## 10. 证据强度与产品决策

- `S1 单例`：一个 trace；只能提出假设或 P0 可复现工具 bug。
- `S2 重复`：两个独立 trace 或当前 trace + 可复现实验；可进入 P1 设计。
- `S3 稳定`：至少三个多样任务、反例分析完成；才可删工具或大幅重构契约。

工具自身抛错、污染状态或虚假成功，现场可复现后可直接 P0，不必等待三个 trace。采用率、拆并和删除必须积累证据。

## 11. 标准报告模板

### 结论

- 完成状态、最严重因果链、用户是否被迫纠正。

### 任务契约差距

| 契约 | 证据 | 状态 | 缺口 |

### 阶段时间线

| 时间/步骤 | 阶段 | 行为 | 结果/转折 |

### 工具矩阵

| 能力/动词 | 标签 | 证据 | 正确替代/产品动作 | 强度 |

### Houdini 模块审计

| 模块 | 输入/输出契约 | 验证 | 问题 |

### 最小正确轨迹

列出 8–15 个状态跃迁，不写逐参数流水账。

### 优先级

P0/P1/P2，每项写：问题、证据、建议、验收、是否需要更多 trace。

## 12. Skill 演化协议

每次复盘后回答：

1. 当前量表是否漏掉了一个可复用维度？
2. `known-patterns.md` 是否已有同类模式？追加证据还是创建新条目？
3. 新发现是 task-specific、Houdini domain、tool contract 还是 agent policy？放到对应层。
4. 是否出现反例，要求降级或关闭旧建议？
5. evidence 脚本是否漏计失败、工具结果或新 schema？若是先修脚本并回归旧 trace。

模式库条目必须包含：ID、状态、首次/最近证据、症状、根因、建议、反例/边界、下一验收。不得把一次草地任务的专有节点名写成通用硬规则。
