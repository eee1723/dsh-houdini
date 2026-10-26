# 节点操作卡参考

> 自动生成，勿手改。唯一数据源：[node-operation-contracts.json](../houdini/node-operation-contracts.json)。
> 生成：`npm run docs:generate`；只读校验：`npm run docs:check`；正常构建会自动更新。

Schema: 2 · Cards: 29 · Source SHA-256: `5061d477142761411934633b77705727f4ec2849e0048889430132085d15d78e`

## 数据与设计契约

- JSON维护输入语义、决策、反例与来源；本页逐项镜像，英文操作说明不另行手译成第二份真相。
- `id`标识知识修订；`node_types`限定精确类型，省略时按现有family规则匹配。`tested_versions`是证据范围，省略不表示已验证所有版本。
- `critical_parameters`只维护关键参数名；实际类型、默认值、组件名、菜单token/set_value由Houdini运行时模板提供，不在文档固化菜单索引。
- `decisions[].any_of`列出备选字段组合：满足任一组合仅表示显式提供字段，不证明值或建模意图正确。`always_advisories`保存每次采用该节点都必须看到的参数语义反例；两者的`guidance`都解释边界。
- `node_info`返回不受普通filter/limit裁切的`operation_parameters`及缺字段提示；静态模板不等于Shelf初始化后的实际值。
- `build_module.operation_advisories`按类型合并缺字段和常驻语义反例，最多16条并报告总数/截断。不阻断、不改默认值、不cook、不解析VEX；未决选择可先dry_run。
- 精确类型不匹配时不套用受限卡；复制返回值不应修改缓存。新增字段必须同时更新生成器、运行时消费者和测试。

实现：[卡加载器](../houdini/python3.11libs/dsh_operation_cards.py)、[node_info](../houdini/python3.11libs/dsh_hou_helpers.py)、[模块构建](../houdini/python3.11libs/dsh_sop_contracts.py)。
契约：[工具设计](tool-design.md)；验证：[节点行为回归](../tools/tests/dsh-node-knowledge.test.py)。

## 卡片目录

- [add](#add)
- [curve](#curve)
- [fit](#fit)
- [resample](#resample)
- [circlespline](#circlespline)
- [orientalongcurve](#orientalongcurve)
- [fractalnoise](#fractalnoise)
- [coppreviewmaterial](#coppreviewmaterial)
- [mirror](#mirror)
- [bend](#bend)
- [skin](#skin)
- [pathdeform](#pathdeform)
- [sweep](#sweep)
- [polyextrude](#polyextrude)
- [polybevel](#polybevel)
- [sphere](#sphere)
- [tube](#tube)
- [circle](#circle)
- [box](#box)
- [revolve](#revolve)
- [normal](#normal)
- [reverse](#reverse)
- [copytopoints](#copytopoints)
- [object_merge](#object_merge)
- [blast](#blast)
- [attribwrangle](#attribwrangle)
- [cam](#cam)
- [karmarendersettings](#karmarendersettings)
- [boolean](#boolean)

## add

标识：`add-editable-control-polygon-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/add.html)。

精确类型：`add`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`points`、`prims`、`prim0`、`closed0`。

### 操作与边界

- The points multiparm creates editable point fields usept0/pt0/weight0, and so on, starting at zero. Set the count before addressing the generated fields; build_module orders declared counts before their instances. A point list alone does not create a connected path: prim0 gives its explicit point sequence and closed0 selects open/closed for that primitive.
- For a sparse path source, retain these point controls and an optional downstream Curve 2.0 editing entry before fitting or dense sampling. Point coordinates, spline control vertices and interpolated on-curve anchors have different roles. Preserve input order and recheck consumers after changing count or connectivity.
- Isolated evidence covers an open sparse Polygon through build_module and point edits reaching Curve 2.0, interpolation and Sweep; it does not certify arbitrary curve routing or GUI handles.

## curve

标识：`curve2-input-editing-and-reinterpretation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/curve.html)。

精确类型：`curve::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`outputtype`、`order`、`convertcurves`、`updatefrominput`、`mode`。

### 操作与边界

- Input 0 supplies existing curves for the native interactive editor. An Add control polygon or fitted curve can seed this editable entry through normal connections; do not guess the legacy Curve coords field or write Data parameters such as parmpoints/stashgeo with scalar setters.
- outputtype/order choose the representation for new curves; convertcurves also reinterprets existing input vertices as that representation. Reinterpretation is not a fit through every input point. A two-span open cubic Bezier uses seven control vertices: endpoints and the shared anchor are on-curve; the other vertices are tangent handles. For sparse mandatory on-curve anchors use an explicit interpolating method instead.
- updatefrominput keeps upstream edits live; disabling it freezes input updates. Keep a sparse editing source before dense sampling and recheck native edits after input topology/order changes. Scalar current-operation fields can express a local transform, but replacing the current operation is not appending an edit history.
- Isolated evidence covers input Polygon-to-Bezier reinterpretation, fitted NURBS passthrough, upstream point edits and a current-operation anchor transform that also moves its adjacent Bezier handles. It does not certify native GUI interaction, arbitrary edit-history replay or geometric clearance.

## fit

标识：`fit-interpolation-versus-approximation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/fit.html)。

精确类型：`fit`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`method`、`type`、`orderu`、`scope`、`dataparmu`、`tol`、`smooth`、`closeu`。

### 操作与边界

- Input primitive control vertices are treated as data points; the input spline basis is not the fitted shape. method=interp passes through the data points; method=approx follows them within its fitting policy and can reduce controls. Select the intended meaning before adjusting tolerance or sampling density.
- For curve interpolation, scope and dataparmu control the fit; do not confuse fitted CVs with input mandatory anchors. Uniform, chord-length and centripetal parameterization are distinct choices. The node may use float attributes beyond P when constructing an interpolation basis, so inspect unintended input data if the fit behaves unexpectedly.
- Retain editable sparse anchors upstream, or place Curve 2.0 after Fit when the user needs to edit the resulting spline CVs. Check endpoints, shape deviation and downstream clearance after edits; interpolation/approximation is not obstacle avoidance.
- Isolated evidence covers an open cubic NURBS global interpolation with chord-length parameterization, endpoint preservation and upstream anchor edits. Approximation, arbitrary attributes, closed curves and surface fitting are not certified by that fixture.

## resample

标识：`resample-shape-interpretation-and-sampling-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/resample.html)。

精确类型：`resample`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`treatpolysas`、`dolength`、`length`、`dosegs`、`segs`、`lod`、`last`、`onlypoints`、`useattribs`。

### 操作与边界

- treatpolysas=straight preserves the Polygon path interpretation; increasing sample count alone does not remove a designed corner. subd/interp explicitly reinterpret Polygon inputs as smooth curves and can change the silhouette or overshoot the original control polygon. Recheck anchors, endpoints and clearance after choosing a smoothing interpretation.
- For native NURBS/Bezier inputs, samples lie on the input curve while lod controls the polygonal approximation used to estimate arc length. dolength/dosegs enable the corresponding length/count limits; useattribs allows segment_length/num_segments primitive attributes to override them. Inspect the effective input and endpoint/equal-segment policy when exact attachment endpoints matter.
- onlypoints removes the connecting curve primitive, which is appropriate for a point consumer but not automatically a Sweep backbone. Preserve the sparse editable source; choose sample spacing for curvature and output scale rather than using a fixed large count as a smoothness claim.
- Isolated evidence compares straight and interpolating interpretations of one open control polygon, including interpolation overshoot, and samples editable Bezier/NURBS inputs. It does not bound arbitrary curves or certify continuous collision clearance.

## circlespline

标识：`circle-spline-sparse-anchor-shape-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/circlespline.html)。

精确类型：`circlespline`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`splinetype`、`usesplinetypeattrib`、`reparmstrength`、`segmentdivision`、`pseudoarclength`。

### 操作与边界

- Input 0 is one or more control polygons. Hybrid blends circular/elliptical interpolation for smooth paths through sparse anchors; it is an option for rounded design curves, not a mandatory replacement for tangent-controlled Bezier or measured-data fitting. Keep an editable control polygon upstream rather than exposing only the dense output.
- The documented C2 parameter continuity requires nonzero reparmstrength. segmentdivision controls output sampling per segment; pseudoarclength adjusts sample placement toward even spacing without increasing the total count. usesplinetypeattrib can select a different spline type from the input splinetype attribute, so inspect the effective segment types.
- The official bounded/generally non-self-intersecting description is not a control-point convex-hull guarantee, whole-curve self-intersection certificate or obstacle-clearance guarantee. Check the shaped path and its swept profile against actual scene geometry; circle/ellipse/helix variants have their own shape behavior.
- Isolated evidence covers Hybrid interpolation of an open sparse Polygon, anchor retention and upstream edits on H21/H22. It does not prove analytic C2 continuity, arbitrary mixed types, degenerate anchors, GUI appearance or collision freedom.

## orientalongcurve

标识：`curve-frame-and-sweep-consumer-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/orientalongcurve.html)。

精确类型：`orientalongcurve`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`tangenttype`、`transformbyattribs`、`upvectortype`、`upvectoratstart`、`useendupvector`、`continuousclosed`、`outputquaternion`、`outputyaxis`、`outputzaxis`、`applyroll`、`roll`。

### 操作与边界

- Computes path reference frames for copying or sweeping. A path tangent alone leaves roll undetermined; choose a suitable up/start/end policy and any intended twist. continuousclosed distributes accumulated closed-curve roll rather than concentrating it at the seam; this is distinct from changing path shape or fixing a kink.
- Choose outputquaternion or the required N/up axes explicitly and verify that the downstream node consumes them. transformbyattribs on this node chooses whether existing point transforms influence its frame; Sweep has a separate Transform Using Curve Point Attributes switch for consuming the result. Avoid applying the same roll twice.
- A circular cross-section may conceal orientation errors. Isolated evidence uses an asymmetric rectangular profile along a planar XZ path: an explicit 90-degree orient roll changes the actual swept width/height only when Sweep consumes point transforms. General spatial torsion, closed seams and GUI appearance remain outside that fixture.

## fractalnoise

标识：`cop-fractal-noise-scale-mode-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/cop/fractalnoise.html)。

精确类型：`fractalnoise`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`elementsize`、`elementsizetype`、`elementscale`、`percomp`、`dotiled`、`tilesize`、`amp`、`center`。

### 操作与边界

- Element Scale is conditional on Per-Component Controls (elementsizetype). On the tested versions this is a one-bit toggle icon strip: set_value=1 enables per-axis scaling; 0 disables it. Changing elementscale alone in uniform mode stores the value but does not change the noise. Discover the current menu_kind/set_value and conditionals, then check output response; setters do not enable modes automatically.
- percomp controls independent noise across output channels, not spatial anisotropy. size_ref supplies dimensions/metadata, while pos supplies the sampling coordinates. Long directional structures require both an effective coordinate/scale choice and the intended surface mapping; node names or nonzero image variance are not proof.
- Use the tile domain and pixel aspect appropriate to the image. Test direction and scale in the current layer and on a representative surface before reusing it across an asset; no fixed wood/noise recipe or universal aesthetic threshold.

## coppreviewmaterial

标识：`sop-surface-sources-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/coppreviewmaterial.html)。

精确类型：`coppreviewmaterial`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`group`、`basecolorsource`、`constantbasecolor`、`basecolorfile`、`basecolorpath`、`tintwithcdswitch`、`roughnesssource`、`constantspecularroughness`、`roughnessfile`、`roughnesspath`。

### 操作与边界

- SOP geometry is input 0; Group limits primitive assignment. One entry supports constant, file and COP sources independently per channel. Pure constant surfaces need no image, COP network or UV; preserve existing user materials instead of migrating them merely for consistency.
- Writes selected primitives' shop_materialpath to a preview shader inside this SOP; unselected primitives retain their assignment. Existing Solaris imports or ROPs may consume that attribute. Trace actual geometry material identities and downstream consumers before adding preview assignment; an empty /mat does not establish that the project has no materials.
- Source menu tokens are file/cop/constant. basecolor and roughness are UI headings, not the writable values: constantbasecolor is the RGB tuple and constantspecularroughness is the scalar. basecolorfile/basecolorpath select file/COP input. Discover current menus and writable parameter types before setting other channels.
- Spatial textures require suitable UVs and normal maps require matching tangent/encoding conventions. Tint With Cd multiplies base color; keep intentional tinting but avoid accidental multiplication by upstream diagnostic colors. Check the actual final SOP and viewport after upstream resizing, copying or deformation.
- The version list covers native parameter discovery and isolated primitive material-path assignment, including Group selection and unchanged upstream values. SOP display, file dependencies, USD material binding, renderer shader support and visual quality have separate validation scopes; consult the surface workflow and development checks.

## mirror

标识：`mirror-plane-and-seam-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/mirror.html)。

精确类型：`mirror`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`operation`、`dirtype`、`origin`、`dir`、`t`、`r`、`dist`、`keepOriginal`、`consolidatepts`、`consolidatetol`、`consolidateunshared`、`reversenml`。

### 操作与边界

- Input 0 is geometry to mirror. operation=all reflects all selected primitives; operation=clip first keeps the positive side of the mirror plane. keepOriginal is case-sensitive. Default direction plane is X=0; dist offsets it along its normal.
- consolidatepts joins eligible original/reflected points on the plane within consolidatetol, optionally restricted to unshared edges. It is not a union operation for overlapping solids. Check seam connectivity separately from symmetry or matching coordinates; an intentional open sheet remains open after joining its seam. Retain the editable half/source upstream so later width/detail changes propagate.
- Isolated evidence covers polygon sheet copy/clip, optional shared seam and an upstream width edit; it does not certify overlapping solid unions.

## bend

标识：`bend-capture-and-enables-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/bend.html)。

精确类型：`bend`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`dodeform`、`enablebend`、`bendmode`、`bend`、`enabletwist`、`twist`、`origin`、`dir`、`length`、`upvectorcontrol`、`up`、`limit_deformation`、`userest`。

### 操作与边界

- Input 0 is geometry to deform; optional input 1 supplies rest positions when userest is enabled. origin/dir/length define the capture spine; up sets the bending plane. Bend in angle mode and Twist use degrees. A different axis or capture length changes the resulting shape even at the same angle.
- Bend moves existing points; it does not add samples. A two-point segment remains a straight chord after bending, so retain enough upstream samples for the requested silhouette. Twist is off by default; a point on its axis does not move. With limited bend, geometry beyond the capture end follows the end transform rigidly; disabling the limit continues curvature. Recheck intended curvature, dimensions and local overlaps after editing rather than inferring them from successful angle assignment.
- Isolated geometry evidence covers sampled line bending and twisting, capture axes/length/limits and inactive Twist; other deformation modes and rest-input combinations are not covered by those fixtures.

## skin

标识：`skin-ordered-sections-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/skin.html)。

精确类型：`skin`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`uprims`、`vprims`、`surftype`、`keepshape`、`closev`、`skinops`、`prim`、`polys`。

### 操作与边界

- For a one-direction loft, input 0 contains the ordered section primitives. Input 1 supplies optional V sections for a different, cross-skin construction; it is not simply the next section in the loft.
- Section order, direction and seam correspondence define the surface. Reordering three valid sections can still cook without errors while joining nonadjacent sections. Preserve separate editable section sources and inspect their correspondence before and after edits.
- With polygon circles, keepshape=1, polys=1 and surftype=quads produce polygon strips through the section vertices. Output Polygons does not convert NURBS/Bezier outputs. closev closes the loft direction; it is not an end-cap switch. An intentionally open loft is a valid surface.
- Isolated evidence covers equal-point polygon sections and a local section edit, not automatic correspondence for arbitrary mixed curves.

## pathdeform

标识：`path-deform-source-frame-and-mapping-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/pathdeform.html)。

精确类型：`pathdeform`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`geo_controlaxis`、`geo_controlup`、`curve_controlup`、`geo_origin`、`geo_centeroncurve`、`geo_offsetunit`、`geo_capturestart`、`geo_captureend`、`curve_endunit`、`curve_posend`、`curve_posoffset`、`startbehavior`、`endbehavior`。

### 操作与边界

- Input 0 is existing geometry to deform; input 1 is the spine curve. Unlike Sweep, this reshapes an already modeled source. Source subdivisions must support the intended bend; deformation does not add sampling along a coarse source.
- Establish the source forward/up axes and curve up separately. Defaults are geo_controlaxis=z, geo_controlup=y and curve_controlup=yaxis. A wrong source axis can cook without errors while stretching the cross-section across the whole curve. Custom axis modes have separate vector parameters; inspect the active templates.
- curve_endunit=fractioncurvelength with curve_posend=1 spans the full curve; fractiongeolength with 1 preserves the source length along its forward axis. These are different valid intents. Capture bounds and centering determine which source interval bends; uncaptured regions can extend along the endpoint tangents.
- Retain the source and spine independently. After changing the path, check corresponding source landmarks, section orientation and thickness, and endpoint placement against the selected length/capture policy. Nonempty output and unchanged topology do not prove correct mapping.
- Isolated evidence covers a subdivided polygon solid mapped onto a planar sampled arc with a fixed up axis; complex spatial twist, rigidity and arbitrary self-intersection remain outside that fixture.

## sweep

标识：`sweep-cross-section-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/sweep.html)。

精确类型：`sweep::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`surfaceshape`、`endcaptype`、`radius`、`cols`、`primtype`、`transformbyattribs`、`upvectortype`、`applyroll`。

### 构建前决策

- `section_source`：`surfaceshape`。Choose external input sections or a built-in section explicitly; wiring alone does not express the intended profile.
- `end_closure`：`endcaptype`。Choose open ends or an applicable cap type; an intentionally open tube/ribbon must not be capped automatically.

### 操作与边界

- With an explicit backbone, input 0 supplies the backbone and input 1 supplies optional custom cross-sections. Custom sections normally use the origin in the XY plane, +Y up (normal along Z), not the path start.
- When input 0 contains no backbone curve, Sweep can use an implicit backbone with one vertex per input-1 cross-section, all at the origin. An unconnected input 0 with multiple sections on input 1 is supported when surfaceshape=input; it does not infer a spatial path from section centers. closeifnocurveinput closes that section sequence, not the cross-sections themselves or end caps. Inspect section order/correspondence and the actual generated surface for this input arrangement.
- For a circular cable, feed the open centerline to input 0 and use the built-in tube with explicit radius/columns/endcaptype; a second input is only for a custom cross-section. In VEX addprim(..., "poly", points) makes a closed path; use "polyline" for a free-ended cable. A closed path can Sweep to a clean watertight shell while adding a wrong return segment. Reversed input order can cook a surface with the wrong shape. The centerline's loose end must meet the preceding tangent smoothly; Sweep cannot remove an upstream sharp turn. For custom sections explicitly establish section plane and path frame/up. tab_create with explicit input 1 reconciles the shipped Sweep 2.0 initializer to surfaceshape=input after wiring; explicit build parms may override this.
- A non-XY section may be intentional with Pitch/Yaw or upstream pre-rotation; do not rotate it blindly. Inspect local section extents and actual end boundaries; world bbox alone cannot prove a tube.
- Upstream orient or N/up only affects the surface when transformbyattribs consumes the curve point transforms. For non-circular sections, choose the path up/frame and intended roll explicitly, then inspect the actual cross-section orientation. A smooth centerline can still have an unwanted frame flip; changing sampling density does not choose the intended roll. Isolated H21/H22 evidence covers a planar path with an asymmetric rectangle and a 90-degree upstream orient roll, including the disabled-consumer counterexample.
- On the listed tested versions, isolated Bridge evidence covers Tab-visible Sweep 2.0 with input 0 unconnected and two equal-count open polylines on input 1: input sections, default section order, quadrilateral surfaces and no caps produced the corresponding open quad strip. tab_create and build_module both preserved the None input slot. This scope does not certify unequal-count or other curve representations, implicit loop closure, arbitrary section correspondence, self-intersections, GUI appearance or artistic quality.

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

标识：`bevel-selection-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/polybevel.html)。

精确类型：`polybevel::3.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`group`、`grouptype`、`ignoreflatedges`、`flatangle`、`offset`、`divisions`。

### 构建前决策

- `bevel_selection`：`group` + `grouptype` **或** `ignoreflatedges` + `flatangle`。Choose the intended construction boundaries, using a typed group or an angle policy derived from the actual input. Empty group can intentionally mean all eligible edges; merely enabling flat-edge filtering does not select the intended boundaries.

### 操作与边界

- Direct creation has empty group, grouptype=guess, ignoreflatedges=0 and flatangle=2 degrees on the tested versions. Exclusions is a parameter section; its expanded/collapsed display is not the filtering switch. With ignoreflatedges=1, adjacent face-normal angles smaller than flatangle are excluded. It is not a maximum angle to bevel.
- Polygon segments approximating a smooth curved surface are distinct from a cap rim or an intentional hard crease. An N-sided straight cylinder has adjacent side-face angles of about 360/N degrees; if the threshold is smaller, all those longitudinal edges still qualify. Prefer construction-boundary edge groups where available, or choose a threshold between the actual unwanted and wanted angles and recheck after resolution changes. No fixed angle is a universal default.
- For controlled hard-surface fillets, build a procedural edge group from construction boundaries/part identity and geometric criteria, then set group and grouptype=edges. Avoid persistent hard-coded edge numbers after topology changes. Explicit all-edge or point bevels remain valid intents.
- Choose width against local feature spacing and inspect the selected edges and resulting corner geometry; nonempty output/collision options do not prove no overlap or correct detail. Increasing divisions cannot fix a wrong selection.
- On H21.0.440, a complex network has crashed during PolyBevel viewport guide cook despite successful output cook/render/save. A simple H21/H22 GUI smoke passed. For a risky final topology, retain a bypassable source and test its actual GUI selection/guide path before claiming it stable.

## sphere

标识：`sphere-representation-and-resolution-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/sphere.html)。

精确类型：`sphere`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`freq`、`rows`、`cols`。

### 构建前决策

- `representation`：`type`。Choose the representation before face editing: a native sphere is not a polygon mesh. Preserve native/NURBS/packed representations when required by the downstream task.

### 常驻语义提示

- `effective_resolution`：Sphere type=poly (Polygon) uses freq; rows/cols can accept values without changing its geometry. type=polymesh (Polygon Mesh) uses rows/cols and ignores freq. Select the representation first, then vary its effective resolution control and inspect actual polygon count and silhouette; successful parameter assignment is not evidence of finer geometry.

### 操作与边界

- Direct creation type=prim is an analytic Sphere. Polygon and Polygon Mesh are distinct menu choices with different tessellation controls; use the current menu tokens, not a shared numeric index.
- For polygon modeling, explicitly choose the polygon representation and inspect actual primitive types and silhouette density. Houdini's generic primitive count also counts native/packed objects; it is not a polygon face count.
- Inactive tessellation fields retain readable values. A high rows/cols value on type=poly does not establish a smooth surface, and a Normal SOP cannot improve a coarse silhouette. Check resolution on the actual source and again after the consuming operation; do not increase every subdivision control indiscriminately.

## tube

标识：`tube-representation-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/tube.html)。

精确类型：`tube`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`type`、`cap`、`rows`、`cols`、`orient`、`height`、`rad`。

### 构建前决策

- `representation`：`type`。Choose polygon output for polygon face operations; native Tube is a legitimate alternative, not a failed polygon.
- `end_closure`：`cap`。Choose whether end caps are intended. Open pipes and closed solid cylinders have different contracts.

### 常驻语义提示

- `radius_axes`：Tube rad1/rad2 are the X/Y ellipse radii of one cross-section, never outer/inner radii. A capped Tube is a filled cylinder even when rad1 and rad2 differ; use a construction that creates an actual inner surface for a pipe, washer or through-hole.

### 操作与边界

- Direct creation type=prim and cap=0. Explicit polygon type and caps are separate decisions; a nonempty native Tube does not establish polygon topology.
- rad1/rad2 are the X/Y ellipse radii of one cross-section, not outer/inner radii. Inspect the actual axis, radius, end boundaries and resolution before using the unit in booleans or instancing. A capped cylinder does not by itself model a hollow pipe wall.

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

标识：`revolve-solid-input-v4`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/revolve.html)。

精确类型：`revolve::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`origin`、`dir`、`divs`、`type`、`surftype`、`primtype`、`swaprowcol`、`reversecrosssections`、`cap`。

### 构建前决策

- `axis`：`origin` + `dir`。Choose the actual rotation axis relative to the profile; a centered Y-axis is only one valid intent.
- `surface_output`：`surftype` + `primtype`。Choose the surface grid and output primitive type. Automatic primitive type follows the input curve; nonempty output does not prove Polygon faces.
- `end_closure`：`cap`。Choose whether to cap the ends of an open profile. Closed revolution around the axis alone does not cap those ends.

### 常驻语义提示

- `surface_orientation`：A revolved Polygon may be closed and consistently wound yet face inward. Before instancing or solid operations, inspect a representative source with geo_piece_stats(..., inspect=True, integrity_only=True): read boundary_edges, orientation_conflicts and shell_orientation separately. Confirm facing against a known exterior face; then correct one direction control and recheck. Never default reversecrosssections=True or use Normal to repair winding.

### 操作与边界

- Facing comes from the ordered profile swept around the chosen axis, not from closure or cook success. With the same axis/settings, reversing profile vertex order reverses surface facing. Inspect the actual profile order and origin/dir; looking clockwise in an arbitrary viewport is not an orientation test.
- reversecrosssections treats the input curves as reversed. Toggling swaprowcol also reverses facing while changing grid ordering. For a confirmed inward simple shell, change one relevant setting or the profile order, then read the output again; toggling both can cancel the facing correction. There is no universal outward value of reversecrosssections.
- Revolve Type closed spans the full circle; Closed Arc adds a point on the axis and produces a different shape. End Caps applies to open input curves. Check the actual profile and final boundaries before instancing.
- A profile whose open endpoints merely coincide is not topologically closed. Establish intended profile closure, or target only a confirmed coincident seam with a scale-appropriate Fuse; recheck boundaries and shape. Fuse repairs connectivity, not facing; preserve intentional gaps.
- Normal computes or flips N without changing polygon vertex order. Double-sided shading, zero boundary edges and zero orientation_conflicts do not prove outward facing. shell_orientation positive follows outward HOM winding only for simple unnested closed shells; nested cavities, self-intersections and open surfaces need separate interpretation. Check mixed-direction profiles separately instead of reversing the entire output.
- After changing the profile order, axis or grid-direction settings, refresh the affected source check and its Copy/Boolean consumers. A passed group does not certify other profiles or the complete assembly.

## normal

标识：`normal-attribute-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/normal.html)。

精确类型：`normal`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`group`、`grouptype`、`docompute`、`type`、`cuspangle`、`reverse`。

### 常驻语义提示

- `winding_vs_normal`：Normal computes or changes the N attribute. Its reverse parameter multiplies N by -1; it does not reverse polygon vertex order or repair inconsistent winding.

### 操作与边界

- Choose point, vertex, primitive or detail normals for the shading need. For an actual wrong-facing Polygon, correct its winding upstream or with a targeted Reverse SOP, then recompute N if needed.

## reverse

标识：`reverse-vertex-order-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/reverse.html)。

精确类型：`reverse`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`group`、`vtxsort`。

### 构建前决策

- `vertex_order`：`vtxsort`。Choose the vertex operation explicitly using the current menu token; Reverse, Reverse U/V, Swap and Shift have different effects.

### 操作与边界

- Reverse changes vertex order on selected faces. Repair only the affected primitive group when the problem is local, then recheck topology orientation and any existing N attribute.

## copytopoints

标识：`copy-local-frame-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/copy/instanceattrs.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Input 0 is the source unit, input 1 the destination points. Establish the unit local axes and destination P/orient/scale before copying.
- Arbitrary destination attributes follow the node's target-attribute transfer rules. Inspect those settings and the actual output attribute class before reading or promoting an attribute; its presence on the destination input does not prove it exists on copied geometry.
- Inspect attribute class and instance identity at the final output; do not assume a template name automatically identifies final primitives. Packed transform changes cannot be certified by P-only comparison.

## object_merge

标识：`object-merge-space-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/object_merge.html)。

精确类型：`object_merge`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`objpath1`、`xformtype`。

### 构建前决策

- `transform_space`：`xformtype`。Choose whether the import preserves source object placement or intentionally reads SOP-local coordinates. Cross-object assembly and render proxies normally require Into This Object.

### 操作与边界

- An object path alone does not preserve assembly placement. For a source under another OBJ, explicitly use Into This Object when the final relationship depends on that OBJ's translate/rotate/scale; local-space import is only valid when ignoring those transforms is intentional.
- Before using a merged proxy for relationship or visual acceptance, compare its bbox with the contributing sources in the same world space and resolve attribute-mismatch warnings. A nonempty render of a local-space proxy is not evidence for the placed assembly.

## blast

标识：`selection-class-v1`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/blast.html)。

精确类型：未另限定（按family匹配）。
已测版本：此卡未列出，不外推版本保证。

### 操作与边界

- Set group type explicitly when selecting point numbers. A polyline with many points is still one primitive; primitive 0 is not point 0.
- Check surviving point/primitive counts before using the output as instance templates.

## attribwrangle

标识：`wrangle-execution-v4`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/attribwrangle.html)。

精确类型：`attribwrangle`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`class`、`group`、`grouptype`、`vex_numcount`、`vex_cwdpath`。

### 构建前决策

- `execution_class`：`class`。Choose Run Over before writing VEX: point/primitive/vertex for existing components, detail for one global execution, number for intentional iteration-count execution. Use current menu tokens, not guessed integers or a parameter named runover.

### 操作与边界

- The snippet is VEX; numeric parameter expressions outside the snippet are HScript unless explicitly tagged Python. Do not copy VEX chf/chi calls into HScript parameter expressions.
- vex_cwdpath is Evaluation Node Path: it changes the node-relative base for VEX ch() parameter lookup, not the filesystem directory for #include. Keep the default '.' unless deliberately evaluating relative to another node. Use an explicit project-relative include such as #include "$HIP/vex/shared.h" for an external file; check parameter values and actual output after changes.
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

标识：`karma-product-resolution-and-focus-v2`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/lop/karmarendersettings.html)。

精确类型：未另限定（按family匹配）。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`enabledof`。

### 操作与边界

- Karma Setup may derive and lock resolution components. Inspect list_parms locked_components and the actual RenderProduct before assigning both dimensions; do not unlock a recipe expression to suppress a strict-setting failure.
- Keep settings/product/camera paths explicit. Use render_frame's optional framing preflight for full-asset images; intentional crops and unsupported lens effects are separate contracts.
- DSH tab_create and Karma Setup initialize a new Karma Render Settings with enabledof off for a sharp general asset view. Explicit creation parameters or later set_parms can enable depth of field for an intentional shot; existing settings and render_frame preserve the artist's choice. Motion blur and denoising are separate controls.
- Karma's enabledof authors RenderSettings karma:global:enable_dof. The generic USD disableDepthOfField value alone does not report this Karma switch. With DOF enabled, inspect the composed camera fStop and focusDistance after import and after moving the camera; camera_fit solves framing, not focus.

## boolean

标识：`boolean-solid-inputs-and-shading-v4`。来源：[SideFX 官方说明](https://www.sidefx.com/docs/houdini/nodes/sop/boolean.html)。

精确类型：`boolean::2.0`。
已测版本：`21.0.440`、`22.0.368`。

关键运行时参数：`booleanop`、`subtractchoices`。

### 构建前决策

- `operation`：`booleanop`。Choose the operation explicitly. For subtraction, inspect subtractchoices and the actual input order: A is input 0, B is input 1; a node name does not establish which solid is removed.

### 常驻语义提示

- `solid_input_validity`：For solid operations, inspect input closure and winding with geo_piece_stats(..., inspect=True); an inward shell can make A-B retain cutter material even when Boolean reports no warning. An ordinary solid A-B cannot extend outside A: expanded output bounds disprove the intended subtraction, while unchanged bounds alone do not prove a valid cut. Check the local cut surface and intended opening after cooking. Sheet operations remain valid with their explicitly chosen surface semantics.

### 操作与边界

- agroup/bgroup select INPUT primitive groups, not output names. Tag input primitives upstream and inspect groups on actual output; topology/group counts may change with parameters.
- Boolean triangulates inputs internally, then may join triangles back into large n-gons. A cut planar face with repeated bridge points can be closed and correctly wound but shade unevenly in the viewport. When integrity inspection reports planar_repeated_point_ngons, compare the affected Boolean node's Detriangulate=Only Unchanged Polygons with the current result; do not change every Boolean by default. Keep the change only after checking the face and connected parts at representative control states.
- If the face is geometrically flat but shades unevenly, compare a Normal SOP with vertex normals and suitable cusp/face-area weighting after the final Boolean and before placement. Explicit N changes shading, not polygon winding or solid overlap; preserve intended bevel highlights and verify the same closeup in more than one state.
- Boolean interpolates point/vertex attributes and copies primitive attributes. Establish stable source UVs before cutting when preserving an existing pattern, and inspect new cutter-derived faces; alternatively compute UVs afterward from explicit surface regions and continuous local coordinates. Triangulation alone does not invalidate a planar mapping. Vertex-by-vertex switching between incompatible projection axes within one face produces interpolation distortion; UV ordering, surface segmentation and mapping formula are separate decisions.
