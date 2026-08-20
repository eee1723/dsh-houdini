---
name: houdini-sop-workflow
description: 设计、构建、调试和交付稳健的 Houdini SOP 程序化网络。用于创建或修改建模、散布、Copy to Points、属性传递、VEX 变形、Sweep/PolyWire、Merge、时间动画等 SOP 任务，尤其在需要选择正确原生节点、避免旧 Copy/手写变换、建立模块输入输出契约、处理 cook warning、验证局部 piece 几何、隔离视觉输出和多帧验收时。
---

# Houdini SOP Workflow

按 Houdini 数据流工作，不把“大段 Python/VEX 跑通”当完成。先选对原生模块，再逐模块验证，最后才渲染和交付。

## 执行顺序

1. 用 `scene_info`、`find_nodes` 和 `graph` 检查现场；不要猜当前 HIP、时间线或拓扑。
2. 把需求拆成模块，逐个写出 `输入几何/属性 → 操作 → 输出几何/属性 → 验收不变量`。
3. 创建复杂节点前先 `search_tab_menu`；用 `tab_create`，不要裸 `createNode` 或凭旧经验选节点。
4. 每次只构建一个可验证 batch。batch 后运行 `cook_node`、`describe` 和必要的属性/piece 统计；失败时依靠 exec rollback 回到上个 checkpoint。
5. 参数名先 `list_parms`；同节点三项以上独立赋值用 `set_parms`；实际意图用 `read_parms`。
6. 按“源几何 → 单元 → 成形 → 模板点 → 复制 → 变形 → 合并输出”逐层验收。全场 bbox 和点数不能证明每个 piece 正确。
7. 用 `geo_piece_stats` 检查重复单元局部 extent/面积；用 `geo_attrib_stats` 检查驱动属性；动画用 `geo_frame_diff` 检查至少两帧。
8. 所有 cook warning 必须解决或解释。Merge 的 N/uv/Cd mismatch 不能因没有 error 而忽略。
9. 视觉验证只用 `render_view(EXPLICIT_SOP)`；用户 viewport 漂移不影响它。用户说屏幕异常时再用 `viewport_screenshot` 诊断并与显式输出对照。
10. 布局节点、把用户 SOP output 移到交付节点、恢复 frame/selection/visibility，最后说明控制参数、warning、文件和验证证据。

## 关键选择

- 散布复制优先 `copytopoints`，让 Houdini 处理 `orient/N/up/pscale`。classic Copy 只有在其独有语义被明确需要时使用。
- 叶片、带状物等应使用有面积的 Grid/ribbon 或 Curve → deform → Sweep。不要捕获中心线 rest 后再用它重建已生成截面的所有点。
- 非刚性弯曲优先在中心线/低维结构上完成，再生成宽度/厚度；刚性每实例摇摆可在模板点 `orient` 上做时间变化。
- Copy/Merge 前后明确属性 class 和传播规则；不要依赖“看起来可能自动复制”。
- VEX 代码以模块不变量为目标；编译通过只证明语法，不证明几何语义。

复杂 Copy、变形、属性和动画模式按需阅读 [references/sop-patterns.md](references/sop-patterns.md)。

## 完成门

仅在以下条件全部成立后交付：

- 最终显式 SOP 存在、非空、无 cook error。
- warning 已清理或逐条解释。
- 单元/piece 没有非预期零宽、零面积或属性缺失。
- 用户目标涉及动画时，两帧 `geo_frame_diff` 或固定相机 render diff 明显非零；检查锚点/活动区等可客观语义。静帧无法可靠裁定细微动态或审美力度时，明确交给用户播放判断，不无限追图、不伪称视觉确认。
- `render_view(EXPLICIT_SOP)` 成功、`stale=false`；动画 A/B 使用相同 `framing_frame`。视觉只承担它能可靠判断的部分。
- Probe 已清理，网络已布局，用户 viewport output 仅在交付阶段设置。
