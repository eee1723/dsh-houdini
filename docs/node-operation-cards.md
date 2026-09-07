# 节点操作卡参考

> 自动生成，勿手改。唯一数据源：[node-operation-contracts.json](../houdini/node-operation-contracts.json)。
> 生成：`npm run docs:generate`；只读校验：`npm run docs:check`；正常构建会自动更新。

Schema: 2 · Cards: 14 · Source SHA-256: `b4a196e7412ca8a1a40b708db7f19f208c0e81131f2233d4d0cec4a8a4d71397`

## 数据与设计契约

- JSON维护输入语义、决策、反例与来源；本页逐项镜像，英文操作说明不另行手译成第二份真相。
- `id`标识知识修订；`node_types`限定精确类型，省略时按现有family规则匹配。`tested_versions`是证据范围，省略不表示已验证所有版本。
- `critical_parameters`只维护关键参数名；实际类型、默认值、组件名、菜单token/set_value由Houdini运行时模板提供，不在文档固化菜单索引。
- `decisions[].any_of`列出备选字段组合：满足任一组合仅表示显式提供字段，不证明值或建模意图正确。`guidance`解释决策边界。
- `node_info`返回不受普通filter/limit裁切的`operation_parameters`及缺字段提示；静态模板不等于Shelf初始化后的实际值。
- `build_module.operation_advisories`按类型/缺字段合并，最多16条并报告总数/截断。不阻断、不改默认值、不cook、不解析VEX；未决选择可先dry_run。
- 精确类型不匹配时不套用受限卡；复制返回值不应修改缓存。新增字段必须同时更新生成器、运行时消费者和测试。

实现：[卡加载器](../houdini/python3.11libs/dsh_operation_cards.py)、[node_info](../houdini/python3.11libs/dsh_hou_helpers.py)、[模块构建](../houdini/python3.11libs/dsh_sop_contracts.py)。
契约：[工具设计](tool-design.md)；验证：[节点行为回归](../tools/tests/dsh-node-knowledge.test.py)。

## 卡片目录

- [sweep](#sweep)
- [polyextrude](#polyextrude)
- [polybevel](#polybevel)
- [sphere](#sphere)
- [tube](#tube)
- [circle](#circle)
- [box](#box)
- [revolve](#revolve)
- [copytopoints](#copytopoints)
- [blast](#blast)
- [attribwrangle](#attribwrangle)
- [cam](#cam)
- [karmarendersettings](#karmarendersettings)
- [boolean](#boolean)

## sweep

标识：`sweep-cross-section-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/sweep.html)。

精确类型：`sweep::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`surfaceshape`、`endcaptype`、`radius`、`cols`、`primtype`。

### 构建前决策

- `section_source`：`surfaceshape`。Choose external input sections or a built-in section explicitly; wiring alone does not express the intended profile.
- `end_closure`：`endcaptype`。Choose open ends or an applicable cap type; an intentionally open tube/ribbon must not be capped automatically.

### 操作与边界

- Input 0 is the backbone; input 1 is an optional cross-section. Default custom sections are centered at the origin in the XY plane, +Y up (normal along Z), not placed at the path start.
- For a circular tube consider the built-in circle section. For custom sections explicitly establish section plane, path frame/up and end-cap intent before construction. tab_create with explicit input 1 reconciles the shipped Sweep 2.0 initializer to surfaceshape=input after wiring; explicit build parms may override this.
- A non-XY section may be intentional with Pitch/Yaw or upstream pre-rotation; do not rotate it blindly. Inspect local section extents and actual end boundaries; world bbox alone cannot prove a tube.

## polyextrude

标识：`extrusion-surfaces-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/polyextrude.html)。

精确类型：`polyextrude::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`outputfront`、`outputback`、`outputside`、`dist`、`inset`、`group`、`splittype`。

### 构建前决策

- `extrusion_surfaces`：`outputfront` + `outputback` + `outputside`。Choose displaced front/original back/connecting sides for the input: sheet thickening differs from extrusion on an existing solid. Front/back do not mean world top/bottom.

### 操作与边界

- Front is the displaced face; Back is the original face; Side bridges them. These names are relative to extrusion, not world up/down.
- When thickening an open sheet into a closed slab, explicitly choose outputfront/outputback/outputside and inspect the final boundary edges and world position.
- Do not enable Output Back universally: extruding faces of an existing solid can create unwanted interior faces.

## polybevel

标识：`bevel-selection-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/polybevel.html)。

精确类型：`polybevel::3.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`group`、`grouptype`、`ignoreflatedges`、`flatangle`、`offset`、`divisions`。

### 构建前决策

- `bevel_selection`：`group` + `grouptype` **或** `ignoreflatedges` + `flatangle`。Choose a typed selection or an explicit flat-edge policy. Empty group can intentionally mean all eligible edges; angle filtering alone is not a semantic part selection.

### 操作与边界

- Direct creation has empty group, grouptype=guess, ignoreflatedges=0. Maximum Normal Angle is flatangle (degrees): with ignoreflatedges=1, smaller adjacent face-normal angles are excluded. It is not a maximum angle to bevel.
- For controlled hard-surface fillets, build a procedural edge group from construction boundaries/part identity and geometric criteria, then set group and grouptype=edges. Avoid persistent hard-coded edge numbers after topology changes. Explicit all-edge or point bevels remain valid intents.
- Choose width against local feature spacing and inspect the selected edges and resulting corner geometry; nonempty output/collision options do not prove no overlap or correct detail. Increasing divisions cannot fix a wrong selection.

## sphere

标识：`sphere-representation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/sphere.html)。

精确类型：`sphere`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`freq`、`rows`、`cols`。

### 构建前决策

- `representation`：`type`。Choose the representation before face editing: a native sphere is not a polygon mesh. Preserve native/NURBS/packed representations when required by the downstream task.

### 操作与边界

- Direct creation type=prim is an analytic Sphere. Polygon and Polygon Mesh are distinct menu choices with different tessellation controls; use the current menu tokens, not a shared numeric index.
- For polygon modeling, explicitly choose the polygon representation and inspect actual primitive types and silhouette density. Houdini's generic primitive count also counts native/packed objects; it is not a polygon face count.

## tube

标识：`tube-representation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/tube.html)。

精确类型：`tube`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`cap`、`rows`、`cols`、`orient`、`height`、`rad`。

### 构建前决策

- `representation`：`type`。Choose polygon output for polygon face operations; native Tube is a legitimate alternative, not a failed polygon.
- `end_closure`：`cap`。Choose whether end caps are intended. Open pipes and closed solid cylinders have different contracts.

### 操作与边界

- Direct creation type=prim and cap=0. Explicit polygon type and caps are separate decisions; a nonempty native Tube does not establish polygon topology.
- Inspect the actual axis, radius, end boundaries and resolution before using the unit in booleans or instancing. A capped cylinder does not by itself model a hollow pipe wall.

## circle

标识：`circle-representation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/circle.html)。

精确类型：`circle`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`arc`、`orient`、`divs`、`rad`。

### 构建前决策

- `representation`：`type`。Choose a polygon or smooth curve representation for the downstream profile operation; do not assume a native circle provides editable perimeter points.

### 操作与边界

- Direct creation type=prim. For a polygon profile, explicitly choose type=poly and establish plane, arc/closure and subdivisions. A closed perimeter, filled polygon and thick closed solid are different deliverables.
- Native or NURBS curves can be intentional; do not insert Convert blindly. Verify the resulting representation after the consuming surface operation.

## box

标识：`box-representation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/box.html)。

精确类型：`box`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`size`、`divrate`。

### 操作与边界

- Unlike Sphere/Tube/Circle, direct Box creation already defaults to type=poly. Do not globally set type=0: numeric menu indices differ between node families.
- Set dimensions and only the subdivisions needed by the intended operation; a dense flat box does not gain construction detail merely from more faces. Native/mesh output remains an explicit alternative.

## revolve

标识：`revolve-ends-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/revolve.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Closing the revolution around its axis does not cap the two ends of an open profile. Decide profile endpoints/end closure explicitly and inspect final boundary loops.
- An intentional open vessel or tube must remain open. Profile radius and axial position are separate coordinates; validate one unit before instancing.
- Profile order and axis direction determine polygon winding. After forming a closed shell inspect both shared-edge consistency and orientation; a Normal SOP does not reverse polygon winding.

## copytopoints

标识：`copy-local-frame-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/copy/instanceattrs.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Input 0 is the source unit, input 1 the destination points. Establish the unit local axes and destination P/orient/scale before copying.
- Inspect attribute class and instance identity at the final output; do not assume a template name automatically identifies final primitives. Packed transform changes cannot be certified by P-only comparison.

## blast

标识：`selection-class-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/blast.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Set group type explicitly when selecting point numbers. A polyline with many points is still one primitive; primitive 0 is not point 0.
- Check surviving point/primitive counts before using the output as instance templates.

## attribwrangle

标识：`wrangle-execution-v3`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/attribwrangle.html)。

精确类型：`attribwrangle`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`class`、`group`、`grouptype`、`vex_numcount`。

### 构建前决策

- `execution_class`：`class`。Choose Run Over before writing VEX: point/primitive/vertex for existing components, detail for one global execution, number for intentional iteration-count execution. Use current menu tokens, not guessed integers or a parameter named runover.

### 操作与边界

- The snippet is VEX; numeric parameter expressions outside the snippet are HScript unless explicitly tagged Python. Do not copy VEX chf/chi calls into HScript parameter expressions.
- Declare attribute class/type and input slots. Use stable names/ids for module interfaces rather than recovering identity from bounding-box sort order.
- Run Over uses parameter class: detail executes once, point executes per input point (none on empty input), number repeats Number Count times. A snippet already looping over the entire generation domain usually needs detail, not number. Intentional Numbers generators use elemnum/numelem; do not change their mode blindly.
- Before Copy to Points, verify the template count and exact P/id tuple uniqueness with geo_attrib_stats(..., unique=True). Nonempty output and unchanged bounds do not rule out overlapping copies.

## cam

标识：`camera-framing-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/ref/cameralenses.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- For an owned static OBJ camera and explicit SOP target, use camera_fit to solve perspective depth and both screen axes before rendering. It preserves focal length, clears lookatpath, and reports actual projection margins; no preview service camera reuse as a delivery camera.
- Camera resolution/pixel aspect and the final USD RenderProduct may differ. After Scene Import, render_frame(..., framing={target: USD_asset_path}) checks the actual composed products. Do not infer full framing from camera distance or a nonempty image.

## karmarendersettings

标识：`karma-product-resolution-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/lop/karmarendersettings.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Karma Setup may derive and lock resolution components. Inspect list_parms locked_components and the actual RenderProduct before assigning both dimensions; do not unlock a recipe expression to suppress a strict-setting failure.
- Keep settings/product/camera paths explicit. Use render_frame's optional framing preflight for full-asset images; intentional crops and unsupported lens effects are separate contracts.

## boolean

标识：`boolean-input-groups-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/boolean.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- agroup/bgroup select INPUT primitive groups, not output names. Tag input primitives upstream and inspect groups on actual output; topology/group counts may change with parameters.
