# Solaris / Karma patterns

本文件记录会改变 agent 决策的版本化工作流，不复制完整 SideFX 手册。运行时先信当前
Houdini 安装的 node/tool/help，再用官方在线文档核对概念与新版本变化。

## 目录

1. H21 标准 Tab tools
2. 材质 render context
3. SOP/USD 动画
4. Render Settings 与交付 ROP
5. 灯光
6. Copernicus 接口
7. 官方参考

## 1. H21 标准 Tab tools

H21.0.440 本机 shipped shelf：

- `lop_karma_setup`，label `Karma (Setup)`：创建名为 `karmarendersettings` 的 Karma
  Render Settings 与 `usdrender_rop`；ROP 表达式引用 settings prim、motion blur 和
  CPU/XPU engine。它是多节点 setup，不是 `createNode('karma')`。
- `vop_karmamtlxsubnet`，label `Karma Material Builder`：在 Material Library 根层创建
  `karmamaterial` subnet，配置 Karma/MaterialX tab mask 与 `kma` render context；内部
  默认包含 MtlX Standard Surface、MtlX Displacement、Karma Material Properties 和
  Material Outputs/AOVs。

工具 id 可能随版本变化；每次用 `search_tab_entries(actual_parent, query)` 发现，不能把
本节当作跳过运行时查询的理由。`tab_apply` allowlist 暂只覆盖上述两个已回归意图。

H22.0.368 的 shipped shelf 仍登记同名 `lop_karma_setup` / `vop_karmamtlxsubnet` 与相同 label，
但当前完整 setup/material-builder 状态恢复和 USD Render ROP 出图回归只在 H21 GUI 执行过。
因此“入口仍存在”是 H21/H22 已确认事实，“H22 完整 recipe 已通过”仍是未验证项；H22 任务
必须先运行 parent-aware discovery 和最小 GUI 验收，不能由 shelf 文本直接外推。

## 2. 材质 render context

优先级不是“哪个节点能 cook”，而是目标 delegate 能消费哪个 render context：

- Karma Material Builder：Karma/MaterialX 混合能力，默认 `outputs:kma`。
- USD MaterialX Builder：纯 `outputs:mtlx`，适合跨 renderer。
- USD Preview Material Builder：通用 preview。
- VEX/Principled：主要是 Karma CPU/旧资产兼容；XPU 可能自动转换为有限的 preview，
  画面有颜色不能证明原网络完整受支持。

读取 SOP `Cd` 时，先在 `usd_prim_info` 确认导入后的 primvar 名和 class。SOP Import 常把
它变成 `primvars:displayColor`；MaterialX 使用 Geometry Property Value 或兼容 primvar
reader 显式读取。薄片植物的双面行为应由 MaterialX/Karma 几何或材质设置明确控制，
不要依赖旧 Principled 的单一 toggle 名跨版本迁移。

## 3. SOP/USD 动画

- SOP Import 的 Author Time Samples 控制 authoring 策略，但某次 cook 只看到一个 sample
  不等价于序列静止，也不等价于序列已验证。
- 先在 SOP 用 `geo_frame_diff` 证明源数据随时间变化；再在最终 stage 检查 time-sampled
  points/xform/primvars；最后用同一 USD camera 渲染两个间隔帧。
- Motion blur 还依赖 camera shutter、Render Settings 和足够的 stage samples；它与“每帧
  重新 cook 能产生动画”是两个不同契约。

## 4. Render Settings 与交付 ROP

标准职责分离：

```text
LOP scene chain -> Karma Render Settings
                         |
                         +-> USD Render ROP / husk process
```

- Render Settings/Product/Var 是 USD prim，属于 stage 数据。
- USD Render ROP 是可执行 `hou.RopNode`，负责进程、frame range、output override、husk、
  Slap Comp 等交付行为。
- `render_frame` 接收可执行 ROP；普通 LopNode 即便有 `execute` 按钮也不应被当作
  `render()` 对象。
- AOV/denoiser 不在简单 beauty 测试时强制开启；用户要求合成、深度、Cryptomatte、
  去噪或生产 EXR 时才配置并用 stage summary 检查 RenderVar/Product。

## 5. 灯光

- 中性测试：Distant + Dome 合理。
- 自然日光：Karma Physical Sky 把 sun 与 sky rig 合在一个物理模型中，优先于手工模拟
  “真实天空”；艺术化灯光仍可自由组合。
- HDRI：Dome Light；检查纹理路径、颜色空间与缺失纹理错误。

灯光“最佳”取决于任务，不把 Physical Sky 设成所有场景的硬规则。

## 6. Copernicus 接口

未来 COP 能力先复用 Tab/setup/USD 地基，不在 system prompt 预载节点清单。常见接口：

- Texture Material Library LOP + USD Material COP。
- Quick Surface Material LOP。
- Karma Material Builder 内 MtlX Image/Tiled Image 的 `op:/path/to/cop` 输入。
- USD Render ROP Slap Comp。

只有在真实 trace 需要低成本验证图层、分辨率、数据类型、保存或 slap comp 结果时，才
新增 COP 自省/交付动词。

## 7. 官方参考

- Karma materials: https://www.sidefx.com/docs/houdini/solaris/kug/materials.html
- Material Library: https://www.sidefx.com/docs/houdini/nodes/lop/materiallibrary.html
- Karma XPU: https://www.sidefx.com/docs/houdini/solaris/karma_xpu.html
- Karma Render Settings: https://www.sidefx.com/docs/houdini/nodes/lop/karmarendersettings.html
- USD Render ROP: https://www.sidefx.com/docs/houdini/nodes/out/usdrender.html
- Karma Physical Sky: https://www.sidefx.com/docs/houdini/nodes/lop/karmaphysicalsky.html
- Copernicus workflows: https://www.sidefx.com/docs/houdini/copernicus/working_with_cops.html
