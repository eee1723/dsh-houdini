---
name: houdini-solaris-karma-workflow
description: 在 Houdini Solaris/LOPs 中设计、构建、检查和交付 Karma 材质与渲染网络。用于用户要求最终渲染、Karma CPU/XPU、MaterialX、USD 材质绑定、Render Settings、AOV、USD Render ROP，或把 SOP/COP 结果接入 /stage；不用于仅需 render_view 的快速 SOP 视觉验证。
---

# Houdini Solaris / Karma Workflow

目标是留下当前 Houdini 版本中用户通过 Tab 菜单能理解和继续维护的 USD/Karma 网络，
不以“有一张图片”替代材质、stage 和渲染契约。

## 执行顺序

1. 用 `scene_info` 确认 Houdini 版本、HIP、帧范围；明确单帧/序列和 Karma CPU/XPU。
2. 最终渲染前先完成源 SOP 的 cook/warning/几何/动画验证。`render_view` 仍只负责快速
   SOP 验证，Karma 不进入反复几何建模调试闭环。材质/COP 任务可在细节搭建前做低成本
   Karma 预览，先验证 UV、绑定、相机与采样；COP 图层构建/诊断按需加载 `houdini-cop-workflow`，
   仅消费现有贴图时不加载它。图层数值调试不靠反复最终渲染。
3. 对实际 parent 调 `search_tab_entries(parent, query)`。不要把全局 node type 注册表当作
   用户 Tab 菜单，不要用裸 `createNode` 绕过 hidden/deprecated 或 builder tab mask。
4. 新 Karma 材质默认从 Material Library 内的 **Karma Material Builder** 开始；用
   `tab_apply(matlib, 'vop_karmamtlxsubnet')` 取得预配置的 Karma/MaterialX subnet。
5. 新最终渲染默认用 `/stage` 的 **Karma (Setup)**；调用
   `tab_apply('/stage', 'lop_karma_setup')`，保留它生成的 Karma Render Settings 与
   USD Render ROP 及二者表达式。普通 `karma` LOP 或传统 Principled 能出图不代表这是
   当前默认架构。
6. 用 `usd_stage_summary` 验证 geometry/material/light/camera/RenderSettings/Product/Var，
   用 `usd_prim_info` 验证 primvar、material binding 和 time samples；warning 必须解释。
7. 整物构图先用 `camera_fit(正式OBJ相机,显式SOP)`，经Scene Import导入；不复用preview服务相机。对setup的USD Render ROP用 `render_frame(...,framing={'target':实际USD资产路径})` 在渲染前检查最终产品；长渲染走job。有意裁切/特殊lens另声明范围，不偷偷改用户相机，普通LOP不是ROP。
8. 动画交付至少渲染两个间隔帧，固定同一 USD camera；SOP time dependency 或单个 USD
   time sample 不能单独证明最终序列。静帧无法判断审美力度时交给用户播放判断。
9. layout、保留 Render Settings 为 stage 交付输出、清理 probe、保存 HIP，并说明 engine、
   material context、ROP、输出路径、warning 和尚未验证的事项。

## 材质选择

- Karma XPU 或新通用 Karma look-dev：Karma Material Builder + MaterialX/Karma 节点。
- 需要纯 MaterialX、跨 Hydra renderer 可移植：USD MaterialX Builder。
- 只需要通用 viewport/Storm preview：USD Preview Material Builder。
- 传统 Principled/VEX 只在用户明确要求 Karma CPU/旧资产兼容且接受限制时使用，并在
  交付中说明；不要把自动 USD Preview 转换误报成原 shader 的 XPU 完整支持。
- 几何颜色进入 USD 后通常是 `displayColor`；在 MaterialX 中显式用 geometry property/
  primvar reader 连接到 surface，不依赖旧 shader 的隐式 Cd 行为。

## 按需参考

- 构建材质、选择 CPU/XPU、设置标准 Karma ROP 或接入 COP 时，读取
  [references/karma-patterns.md](references/karma-patterns.md)。
- 若任务同时修改复杂 SOP/VEX/Copy/动画，先联用 `houdini-sop-workflow` 完成源数据门。

## 完成门

- 节点来自当前 parent 的可见 Tab entry；setup tool 的全部配套节点存在。
- material prim 有明确 `outputs:kma`/`outputs:mtlx`/preview context，且绑定到目标 prim。
- camera、lights、RenderSettings、RenderProduct 与 USD Render ROP 路径可自省。
- 单帧产物存在、非空、无未解释 render error/warning。
- 动画任务有最终 Karma 两帧或小序列证据；没有时只能报告“单帧完成”。
