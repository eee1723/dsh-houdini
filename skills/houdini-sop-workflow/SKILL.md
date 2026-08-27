---
name: houdini-sop-workflow
description: 设计、构建、调试和交付稳健的 Houdini SOP 程序化网络。用于创建或修改建模、散布、Copy to Points、属性传递、VEX 变形、Sweep/PolyWire、Merge、时间动画等 SOP 任务，尤其在开放式建模需要参考/质量合同、共享尺寸与锚点、模块关系验收，或需要选择正确原生节点、处理 cook warning、验证局部 piece、隔离视觉输出和多帧验收时。
---

# Houdini SOP Workflow

按 Houdini 数据流工作，不把“大段 Python/VEX 跑通”当完成。先选对原生模块，再逐模块验证，最后才渲染和交付。

## 前置合同

简单、规格完整的编辑可直接执行。开放式、质量敏感、机械/空间关系复杂或明确要求“程序化资产”
的任务，在大规模建图前先确认上游任务合同至少覆盖：目标/参考状态、LOD 与允许简化、单位和
关键尺寸、需要暴露的控制、模块关系、客观完成门和视觉取证视角。缺少外部参考时，把尺寸与
审美判断标为假设，不得用自生成数值的内部一致性冒充外部真实性。

只要任务满足上述任一条件，就在首个大规模 scene mutation 前读取
[references/procedural-quality-contract.md](references/procedural-quality-contract.md)；它不是可跳过的补充材料。
简单、规格完整的编辑才按需省略该引用。

## 强完成协议

质量敏感的开放式资产按下列 checkpoint 推进；某项不适用时显式说明原因，不静默跳过：

1. **研究/合同**：外部真实性会改变方案且 research/web 可用时实际检索并记录来源；否则向用户
   索取参考，或把自选尺寸标为未验证假设。合同必须包含质量/LOD、允许简化、控制、关系和证据视角。
2. **骨架**：先只做 controls、named anchors/local frames、中心线或代理体；在增加装饰和重复小件前，
   用数值关系及需要时的整体 render 验证比例、轮廓和主要连接。骨架未通过不进入细化。
3. **模块/关系账本**：逐模块记录输入、输出和不变量；每条连接、共轴、包含、间隙、禁止穿插或
   属性连续关系最终标记 `pass / fail / unverified`，并指向对应 query、统计或局部视图。
4. **视觉批评**：整体图只验轮廓，局部关系必须有可辨认的特写。首次读图先列可见缺陷和不确定项，
   再决定返工或降级结论；“可辨认”“成功出图”和“高质量/与参考一致”是三个不同结论。
5. **扰动/恢复**：可调资产至少改变一个会影响多个模块的关键用户控制，cook 并重跑受影响关系门，
   然后恢复交付值再复验。只在默认值能 cook 不算程序化完成。
6. **新鲜证据**：最后一次几何 mutation 后重新采集最终输出统计、warning、关系账本和交付视图；
   不复用修改前的点数、primitive 数或图片。无法证明的项保留 `unverified`，不得由 todo 完成状态补证。

## 执行顺序

1. 用 `scene_info`、`find_nodes` 和 `graph` 检查现场；不要猜当前 HIP、时间线或拓扑。
2. 把需求拆成模块，逐个写出 `输入几何/属性 → 操作 → 输出几何/属性 → 验收不变量`；质量敏感
   资产另写共享尺寸/anchor 和模块关系，避免多个 Wrangle 复制同一绝对坐标。
3. 创建复杂节点前先 `search_tab_menu`；用 `tab_create`，不要裸 `createNode` 或凭旧经验选节点。
4. 每次只构建一个可验证 batch。batch 后运行 `cook_node`、`describe` 和必要的属性/piece 统计；失败时依靠 exec rollback 回到上个 checkpoint。
5. 参数名先 `list_parms`；同节点三项以上独立赋值用 `set_parms`；实际意图用 `read_parms`。
6. 按“源几何 → 单元 → 成形 → 模板点 → 复制 → 变形 → 合并输出”逐层验收。全场 bbox 和点数不能证明每个 piece 正确。
7. 用 `geo_piece_stats` 检查重复单元局部 extent/面积；用 `geo_attrib_stats` 检查驱动属性；动画用 `geo_frame_diff` 检查至少两帧。
8. 所有 cook warning 必须解决或解释。Merge 的 N/uv/Cd mismatch 不能因没有 error 而忽略。
9. 任务需要视觉证据且当前 GUI 渲染环境可用时，用 `render_view(EXPLICIT_SOP)`；用户
   viewport 漂移不影响它。用户说屏幕异常时再用 `viewport_screenshot` 诊断并与显式输出
   对照。动画固定构图先用 bbox/测试帧选择能覆盖验收帧包络的 `framing_frame` 和 coverage；
   `render_check` 的 `content_bbox` 触边或安全边距不足时视为裁切风险并重新取景。纯网络/数据交付
   或视觉难以裁定时，不为追图推翻已通过的语义门。
10. 布局节点、把用户 SOP output 移到交付节点、恢复 frame/selection/visibility，最后说明控制参数、warning、文件和验证证据。

## 关键选择

- 散布复制优先 `copytopoints`，让 Houdini 处理 `orient/N/up/pscale`。classic Copy 只有在其独有语义被明确需要时使用。
- 叶片、带状物等应使用有面积的 Grid/ribbon 或 Curve → deform → Sweep。不要捕获中心线 rest 后再用它重建已生成截面的所有点。
- 非刚性弯曲优先在中心线/低维结构上完成，再生成宽度/厚度；刚性每实例摇摆可在模板点 `orient` 上做时间变化。
- Copy/Merge 前后明确属性 class 和传播规则；不要依赖“看起来可能自动复制”。
- VEX 代码以模块不变量为目标；编译通过只证明语法，不证明几何语义。
- 关键控制采用单一真相源，派生模块引用同一参数/属性/anchor；“去多个 VEX 字符串里分别改坐标”
  不算可靠的程序化接口。需要用户反复调整时，用 spare parms/HDA interface 或清晰的控制节点暴露。
- `geo_piece_stats` 的非退化只证明局部面积/extent，不证明部件已连接、无穿插或满足最小间隙；
  涉及装配关系时必须另验轴线、接触、包含、间隙或禁止相交等契约。

复杂 Copy、变形、属性和动画模式按需阅读 [references/sop-patterns.md](references/sop-patterns.md)。

## 完成门

仅在以下条件全部成立后交付：

- 最终显式 SOP 存在、非空、无 cook error。
- warning 已清理或逐条解释。
- 单元/piece 没有非预期零宽、零面积或属性缺失。
- 契约要求可调时，关键参数已集中暴露，依赖模块由共享参数/anchor 派生；不存在会在一次合理调参后
  立即失配的重复常量。
- 已对至少一个跨模块关键控制完成“改变 → cook/关系复验 → 恢复交付值 → 再复验”；若资产没有
  此类控制，说明为何扰动门不适用。
- 契约涉及部件连接、包含、间隙或禁止穿插时，相关关系有逐项证据；整体 bbox、点数、无 warning
  或 `degenerate_surface_pieces=0` 不替代这些证据。
- 用户目标涉及动画时，两帧 `geo_frame_diff` 或固定相机 render diff 明显非零；检查锚点/活动区等可客观语义。静帧无法可靠裁定细微动态或审美力度时，明确交给用户播放判断，不无限追图、不伪称视觉确认。
- 若契约包含视觉交付，`render_view(EXPLICIT_SOP)` 应成功且 `stale=false`，动画 A/B 使用相同
  `framing_frame`，并确认所有验收帧的 `content_bbox` 都保留安全边距。纯网络/数据交付，或当前环境无法可靠视觉验证时，明确把画面/播放判断交给
  用户且不声称视觉通过；这不阻塞已经客观证明的结构与数据完成度。
- 小零件、连接和穿插不能只靠整物远景确认；视觉验收按契约增加能看清目标关系的局部视角，并把
  “与参考一致”“主观质量通过”和“图像成功生成”分开报告。
- 最终统计、关系结果和交付图均晚于或同批发生于最后一次几何修改；最终报告逐项列
  `pass / fail / unverified`，不把内部一致升级成有来源的真实性。
- Probe 已清理，网络已布局，用户 viewport output 仅在交付阶段设置。
