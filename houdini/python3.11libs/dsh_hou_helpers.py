"""Houdini hou helpers. Executed on the Bridge owning thread."""
from __future__ import annotations




def verify_network(parent, output=None, nodes=None, limit: int = 512, require_valid: bool = True,
                   *, output_index: int | None = None) -> dict:
    """SOP network cook/geometry checkpoint, including upstream warning nodes.

    Checks direct children by default; optional nodes limits scope explicitly.
    Explicit output is always required; no display fallback. Empty/error output
    raises CheckpointError by default; require_valid=False is diagnostic only.
    No viewport changes. output_index=0..63 additionally requires the matching
    native Output to be this source or directly wired to it. Packed wrapper
    counts alone do not prove nonempty embedded content.
    Parent-relative references and absolute paths use the same explicit parent.
    Healthy still means cook/output
    health, not correct shape, relationship or visual finish.
    healthy != task/visual success; relationships remain unverified.
    """
    from dsh_sop_contracts import verify_network as verify
    return verify(parent, output=output, nodes=nodes, limit=limit, require_valid=require_valid,
                  output_index=output_index)


def modeling_dimensions(quantities, require_meter_scene=True) -> dict:
    """Read-only typed source quantities -> meter/area/volume values and CTRL spec.

    quantities={name:{value:number,unit:m|cm|mm|um|in|ft|m2|cm2|mm2|m3|cm3|mm3|deg|rad|count|ratio,
    min?:number,max?:number,source?:string}}. Requires actual HIP unit length 1m
    by default. Existing nonmeter scenes need explicit False and scene_values
    adaptation; never changes HIP settings. Counts/angles are not length-scaled.
    Example: modeling_dimensions({'length':{'value':120,'unit':'mm'}})
    returns canonical_values['length']=0.12. Use converted values in construction.
    Source meanings and final physical dimensions remain separately verified.
    """
    from dsh_modeling_units import modeling_dimensions as convert
    return convert(quantities,require_meter_scene)


def sop_recipe(kind, spec=None) -> dict:
    """Read-only ordinary SOP specs; includes curve_path, sweep_tube and structural recipes.

    Read catalog or sop_recipe(kind) for examples of every recipe. guided_slider bounds
    travel against actual polygon source/guide projections. surface_attach projects
    a source Y=0 foot to a named receiver surface; complete-foot contact remains
    separately verified. gusset/fastener generate editable local detail sources.
    Inputs are direct source children; one
    named CTRL supplies parameter references and shared frame origin. Returns
    nodes/output/required_outputs for build_module, never creates/cooks nodes.
    Hinge uses degrees about a normalized axis and a source-local origin pivot;
    slider translates along axis; repeat uses integer count 1..256 and spacing.
    Numeric origin/dimensions or {parm:name} reference one shared controller.
    No automatic interfaces, world-space conversion, HDA, ownership or acceptance.
    curve_path uses named anchors/handle offsets to plan native Add -> Curve 2.0
    cubic Bezier -> Resample; shared symmetric handles retain C1 joins. It does
    not route, project onto geometry, avoid obstacles or certify swept surfaces.
    """
    from dsh_procedural_plans import sop_recipe as plan
    return plan(kind, spec)


def control_test_plan(controller, parameters, max_cases=16, domain=None) -> dict:
    """Read scalar current values and plan <=16 pairwise representative cases.

    parameters={scalar:[2..8 explicit boundary/intermediate levels]}, <=8 controls,
    <=4096 candidate combinations. domain uses test_controls scalar constraints.
    No writes/cook. Returned tests contain EMPTY expectations: author must add
    independent response/invariant measurements and state-specific interfaces.
    Coverage reports exact uncovered requested levels/pairs, never a full-domain
    proof. Run accepted cases with test_controls; no auto-pass or silent clamping.
    """
    from dsh_procedural_plans import control_test_plan as plan
    return plan(controller, parameters, max_cases, domain)


def build_module(parent, nodes: list, output: str, dry_run: bool = False, interfaces=None, *, required_outputs=None) -> dict:
    """Build NEW SOP nodes from a nonempty {name,type,parms?,inputs?} spec list.

    Inputs name any declared spec or existing direct child; declaration order is
    free. All nodes exist before wiring and parameter expressions. None retains an empty input.
    For secondary Wrangle lookup use inputs=[None, 'source']. No overwrite or flags.
    dry_run is static preflight (no scratch node); VEX/cook not yet verified.
    Failed creation/parameters/cook removes only this batch's new nodes.
    Output must contain geometry. Create empty controllers/helpers with tab_create.
    Returned validation reports warnings separately from errors and semantics.
    Optional interfaces are final-output point-group → primitive-group proximity
    contracts, checked after construction; failing/unverified contracts fail the
    module and clean its new nodes. See geo_check_interfaces for exact schema.
    required_outputs=[new_node_name,...] optionally requires nonempty module
    branches, so a healthy merge cannot hide missing deliverable pieces. Empty
    helpers remain allowed when not declared required. Independent static field
    errors are returned together before creation; retain parameter components.
    Query node_info for operation knowledge when needed; construction returns
    execution and output facts without inferring unresolved design choices.
    """
    from dsh_sop_contracts import build_module as build
    return build(parent, nodes, output=output, dry_run=dry_run, interfaces=interfaces, required_outputs=required_outputs)


def geo_check_interfaces(output, interfaces, max_pairs: int = 50000) -> dict:
    """验证实际最终SOP上的连接接口，不用另建的anchor/proxy代替部件。

    interfaces=[{id,source_group,target_group,max_distance,expected_points}]。
    source_group为最终polygon/mesh表面顶点的命名point group；target_group为不相交
    的命名primitive group（closed Polygon/Mesh/Sphere/Tube）。全source点都须在容差内。
    只测SOP local点到指定表面的距离，不证明整体穿插/强度/所有表面最小间隙。
    空选择/基数不符fail；不支持表示unverified；超max_pairs拒绝不抽样。
    可选method='axis_gap'时source_group/target_group均为实际primitive组，带axis(0..2)、
    gap_range=[min,max]和正数min_overlap。测source.min-target.max及横向投影重叠；
    正数表示轴向分離，负数表示投影重叠，仅此，不能称为真实接触或插入深度。
    method='solid_overlap'时两组都是同一最终SOP内完整、独立、闭合且朝外的
    Polygon实体primitive组，另给max_overlap_volume（SOP local单位的三次方）。
    内存Boolean Intersect量实体相交体积；正体积超限fail，零交集pass；
    不完整/开放/非Polygon或数值模糊为unverified，不添加场景节点。
    例：{id:'shaft_clearance',method:'solid_overlap',source_group:'lug',
    target_group:'shaft',max_overlap_volume:0}。须另验同轴和孔壁距离；
    零交集不证明轴已穿孔，逐状态检查也不证明连续扫掠或力学。
    method='axis_passage'只需最终输出的target_group primitive组、axis(0..2)、
    start/end两个SOP local轴对齐三维点。两端须在所选组轴向包络之外，横向
    位于包络内；在最终Polygon表面上射线碰到任何面即fail，单轴无遮挡才pass。
    缺组fail；不支持表示或线段未跨包络为unverified。只证明这一条中心线，
    不证明孔径、孔壁、周围材料或其他轴；后续增材修改后必须复验。
    method='bore_clearance'增加正数radius（SOP local单位），在声明的start/end
    区间内以外切24边棱柱与最终闭合朝外Polygon组做Boolean相交；零交集pass，
    有效正体积fail，不完整实体/数值含糊unverified。区间须按安装板等实际待验
    壁厚指定；若组还有远处的铰耳，不要求整组包围盒都被孔轴贯穿。它不证明
    区间两端之外仍通畅、孔周有材料、图纸孔位正确或加工公差。
    bore_clearance超出目标面数或剩余预算时返回unverified、实际规模和下一步，
    不把未检查当作几何失败。当前数值限制见完整verb_help的runtime_limits；
    提高max_pairs不能解除目标面数限制，不能裁掉待验实体的一部分面来冒充完整检查。
    method='component_count'用最终Polygon primitive组target_group和
    expected_components(1..32)测共享边连通岛数；缺组或数目不符fail，
    不支持表示/退化面unverified。期望件数须先从要求得出，不能从幸存件反推；
    数目通过不证明每件身份、对称位置、形状或连接到主体。
    method='physical_extent'用最终闭合Polygon primitive组target_group、axis(0..2)、
    expected_mm(正数)和tolerance_mm(0..expected_mm)量选中点的逐轴跨度，按HIP
    unitlength换算毫米。尺寸归属与允许误差须先由用户/厂家图核对，不能从现有模型反推。
    缺组或超差fail；非Polygon、单位未知、非单位OBJ变换等为unverified。
    只证明所选最终组的一轴数值，不证明完整零件身份、孔径、造型或装配。
    大型最终输出中，具名primitive关系组会先被精确提取再按原预算量测；
    geometry_scope列出来源总量、选中量和组。未选几何不被认证；点到面旧合同仍有整件预算。
    """
    from dsh_quality_contracts import geo_check_interfaces as check
    return check(output, interfaces, max_pairs=max_pairs)


def test_controls(controller, output, tests, interfaces=None, allow_foreign=None, *, domain=None, topology=None,
                  baseline_interfaces=None, views=None, view_bounds=None) -> dict:
    """数字标量控制的可恢复测试；必须用exec（会临时改参数/cook）。

    tests为1..16个case；每个case是
    {id,values:{parm:number},expectations:[{metric,axis?,group?,id_attrib?,delta:[min,max],range?}],interfaces?}，
    values只放相对当前基准实际改变的参数；未变化字段和基准状态不要作为扰动case传入。
    每个case最多16个expectations；同一扰动的大检查按相同values拆成多个case。
    metric精确枚举：bounds_size、bounds_center、bounds_min、bounds_max（axis0..2）、
    point_count、primitive_count、area、point_mean(axis)、boundary_edges、piece_count（Polygon共享边）。
    max_point_displacement/mean_point_displacement需id_attrib稳定唯一point ID及相同面连接；
    max_transform_error另给transform（16数row-major仿射矩阵，SOP-local行向量约定），
    测max(|P_baseline*transform-P_test|)，baseline残差=0；仍需另有非零响应项。
    range=[min,max]验证基准/扰动绝对范围，delta是相对响应；center/min/max不是有效缩写。
    先消费control_summary的status/reason/case_counts；results=[]可能是基准失败，绝非通过。
    control_summary保留未运行case、输出变化与失败测量，coverage区分全输出/部件测量和接口覆盖。
    bounds/count通过不证明连接或均匀变换；输出变化而所选指标失败不等于控制未接线。
    修正判据后复跑，不能用文字解释替代新结果。
    group为实际output内命名primitive group。delta是变化前后的有符号允许区间。
    不指定group时point_count/primitive_count允许显隐后的合法0；显式命名组仍须存在且非空，
    bounds、表面及实体关系等指标继续要求其实际可测选择，不把空输出视为关系通过。
    大型输出须给每项指标明确group，所有关系/拓扑也使用具名primitive组，
    才能按选中部件取证。geometry_scope不证明未选区域；恢复仍用整件原生bgeo字节流核对，
    未选部件漂移也会失败。无法完整保存恢复快照时在改参数前拒绝。
    顶层interfaces在基准及每次扰动均检查；baseline_interfaces只在基准状态检查，
    case内interfaces只在该扰动状态检查，用于合盖接触与开盖分离等不同状态合同。
    三者均用geo_check_interfaces同一schema；实体禁穿插可用solid_overlap，
    但所选组须完整闭合，孔轴无遮挡可用axis_passage，声明孔径空域可用
    bore_clearance；这些检查均不认证整件孔系或制造公差。
    每case最终恢复原参数/keys/frame，
    用完整bgeo内容核对输出恢复（包括原生primitive intrinsic）。
    拒绝foreign控制（除单次授权）、menu/button/callback/multiparm/tuple；只声明已测case，
    当前控制输出支持Polygon/Mesh/Sphere/Tube及点几何；内嵌PackedGeometry有界内存展开量测，
    原Packed内容与变换单独做恢复指纹。磁盘/Alembic/Fragment等其他类型写前unverified。
    每case至少一项预期delta排除0；不保证外部文件/Python或solver副作用可撤销。
    可选domain=[{id,left:数值spare参数名,op:lt|le|gt|ge|eq|ne,right:参数名或有限数值}]。
    检查基准和实际扰动值；独立无key控制还可写前拒绝无效测试值。不求解/钳制，不证明全范围。
    可选topology=[{id,groups:[最终primitive组名,...],require_closed:true}]检查融合表面的
    共享边连通/闭合；在基准与每次扰动实际输出上复查。不用于未焊接独立部件的距离/强度证明。
    views可选最多两个iso/front/side/top；先拍基准，再用相同取景/深度包络拍各case。
    view_bounds可显式给覆盖全部状态的世界坐标[min_xyz,max_xyz]；省略则锁定基准包络。
    状态超出包络不重新取景；GUI/图片不可用保持unverified，几何恢复仍执行。图片不证明语义正确。
    """
    from dsh_quality_contracts import test_controls as test
    return test(controller, output, tests, interfaces=interfaces, allow_foreign=allow_foreign,
                domain=domain, topology=topology, baseline_interfaces=baseline_interfaces,
                views=views, view_bounds=view_bounds)


def cop_layer_stats(node, output=0, *, max_pixels=4194304) -> dict:
    """exec-only: full bounded ImageLayer statistics, metadata and exact buffer fingerprint.

    output is an exact output name/index. No sampling, normalization or Geometry conversion.
    max_pixels is 1..16777216; memory/cook cost is not a hard process budget.
    Manual, failed cook, unsupported output and oversized buffer reject; sticky upstream cache
    remains explicitly unknown. Returns per-channel min/max/mean/nonfinite and XY variation.
    """
    from dsh_cop_contracts import layer_stats
    return layer_stats(node, output, max_pixels=max_pixels)


def cop_compare_layers(before, after, *, before_output=0, after_output=0, expected_delta=None,
                       tolerance=1e-6, max_pixels=4194304) -> dict:
    """exec-only: full aligned buffer difference AFTER - BEFORE; no implicit resampling.

    expected_delta is optional {node,output?} naming a declared increment layer; when provided
    check max(abs((after-before)-expected_delta)) <= tolerance. Without it return measurement,
    status=unverified, never artistic/semantic success. Channel/window/space mismatch rejects.
    """
    from dsh_cop_contracts import compare_layers
    return compare_layers(before, after, before_output=before_output, after_output=after_output,
                          expected_delta=expected_delta, tolerance=tolerance, max_pixels=max_pixels)


def test_cop_controls(controller, output, tests, *, output_port=0, max_pixels=4194304,
                      allow_foreign=None) -> dict:
    """exec-only reversible numeric scalar COP controls, exact channel/frame/output restoration.

    tests=[{id,values:{parm:number},expectations:[{metric,channel,delta:[min,max],range?:[min,max]}]}].
    Metrics: mean,min,max,mean_abs_change,max_abs_change; change metrics baseline=0.
    Every case needs a nonzero expected response; range checks baseline and perturbation.
    Reject menus/callbacks/multiparms/tuples, Manual, unsupported/nonfinite layers before writes.
    Uses full ImageLayer fingerprint (not bgeo), checks all controlled channels after recook.
    Sticky Cache upstream is rejected; external files/Python/solver effects are not restored.
    A restored failed test is status=fail; restoration failure raises CheckpointError.
    """
    from dsh_cop_contracts import test_controls
    return test_controls(controller, output, tests, output_port=output_port,
                         max_pixels=max_pixels, allow_foreign=allow_foreign)


def geo_point_spacing(node, expected: float, tolerance: float, closed: bool = False,
                      order_attrib=None, max_points: int = 10000) -> dict:
    """全量检查一条有序点序列的相邻弦长（SOP local单位），不是曲线弧长或表面关系。

    默认按point number；可用唯一数值order_attrib排序。closed=True检查末→首。
    超max_points拒绝，不抽样；返回全量min/max/failure_count及最多16个最差相邻对。
    ok仅证明本条距离约束，geometry/视觉/实际零件关系须另外验证。
    """
    from dsh_sop_contracts import geo_point_spacing as check
    return check(node, expected, tolerance, closed=closed, order_attrib=order_attrib, max_points=max_points)


def geo_curve_clearance(node, radius, *, group=None, clearance=0.0, self_exclusion=None,
                        max_segments=2048, max_pairs=500000, max_results=16) -> dict:
    """Check all selected polyline segment/radius envelopes with explicit local exclusions.

    radius: positive scalar or scalar primitive radius attribute name. group:
    exact primitive group. Only actual open Polygon primitives are supported;
    smooth/native/packed/closed-face input is unverified without approximation.
    A geometric loop may repeat its endpoint. Computes closest finite segment
    points, including interior crossings, and gap=distance-radius_a-radius_b.
    clearance is the required nonnegative envelope gap in SOP local units.
    Same-curve point pairs within self_exclusion arc distance are omitted by
    clipping the segment-pair parameter domain, including a geometric loop's
    seam; long adjacent/backtracking segments retain their nonlocal parts.
    None uses pi*(curve_radius+clearance/2), a half-circle arc at the effective
    radius. Explicit zero omits no local neighborhood and can flag joint envelopes.
    max_pairs bounds candidate pairs BEFORE exclusion; budgets return unverified
    without measuring any pair. Read coverage/omissions and worst_pairs, not
    only ok. Pass covers eligible segment envelopes; it never proves local bend
    validity, smooth-curve intervals, final Sweep mesh or obstacle clearance.
    Does not modify curves, viewport or input geometry.
    """
    from dsh_curve_paths import geo_curve_clearance as check
    return check(node, radius, group=group, clearance=clearance, self_exclusion=self_exclusion,
                 max_segments=max_segments, max_pairs=max_pairs, max_results=max_results)

# Public verb vocabulary; implementation modules never import this facade.
from dsh_geometry_queries import (
    geo_attrib_stats,
    geo_piece_stats,
    geo_frame_diff,
)
from dsh_hda_operations import (
    hda_create,
    hda_fork,
    hda_version,
    hda_switch_version,
    hda_edit,
    hda_set_interface,
)
from dsh_hda_sections import (
    hda_get_section,
    hda_set_section,
    hda_patch_section,
)
from dsh_image_pixels import (
    render_check,
)
from dsh_keyframes import (
    set_keyframes,
)
from dsh_media_output import (
    report_image,
)
from dsh_node_creation import (
    search_tab_entries,
    tab_apply,
    tab_create,
)
from dsh_node_inspection import (
    find_nodes,
    graph,
    describe,
)
from dsh_node_layout import (
    layout_nodes,
    network_boxes,
    network_notes,
    network_controls,
    present_nodes,
    focus_node,
)
from dsh_node_operations import (
    set_object_parent,
    connect,
    disconnect_input,
    rename_node,
    delete_node,
    set_update_mode,
    cook_node,
    sop_set_output,
    sop_output_node,
    set_object_visible,
    visible_objects,
)
from dsh_node_types import (
    context_name,
    resolve_latest_type,
    search_tab_menu,
    node_info,
)
from dsh_ownership import (
    node_provenance,
)
from dsh_parameter_values import (
    list_parms,
    read_parms,
    set_parm,
    set_parms,
)
from dsh_render import (
    camera_fit,
    render_frame,
    render_view,
)
from dsh_scene import (
    scene_info,
    scene_save,
    scene_save_as,
    set_timeline,
    list_bookmarks,
    create_bookmark,
    delete_bookmark,
)
from dsh_spare_parameters import (
    create_spare_parms,
    bind_controls,
    parameter_ui,
)
from dsh_usd_inspection import (
    usd_stage_summary,
    usd_prim_info,
)
from dsh_viewport import (
    viewport_screenshot,
)
