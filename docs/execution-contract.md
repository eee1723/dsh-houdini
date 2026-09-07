# 执行与证据契约

实现入口：[Bridge](../houdini/python3.11libs/dsh_bridge.py)、[helpers](../houdini/python3.11libs/dsh_hou_helpers.py)。
调用签名与版本以[工具设计](tool-design.md)及运行时verb_help为准；本页只维护跨动词边界。

## 安全与权限

- hou仅在Houdini主线程调用；HTTP线程只排队。泵不可用即拒绝，不退回网络线程执行。
- query使用只读namespace与AST预检；exec负责修改，job负责长操作。Raw Gate默认开启，
  已有动词覆盖的裸修改不能用allow_raw旁路；仅独立、无动词等价的低层缺口允许单次明确理由。
- ownership是runtime创建identity与session provenance，不是路径、父网络、名称或可复制userdata。
  foreign可读/作输入，不等于可写；单次allow_foreign必须绑定用户明确目标与非空授权说明。
  持久render服务不可豁免，layout默认仅本session节点。
- 原生OBJ parent/unparent使用set_object_parent并说明reason；generic connect/disconnect只管数据流。
- loopback并不鉴别所有本地进程。AST和ownership面向正常agent，不是恶意Python安全沙箱。
  不应向不可信网络暴露Bridge。

## 事务与异步

exec异常恢复Houdini可撤销状态；捕获mutation/cook异常不重新抛出会被caught-failure机制拦截。
消费transaction最终状态：后项失败可能撤销同exec中前面成功的build，不能沿用已回滚节点。
失败补充清理仅限本调用journal的确切新建identity；foreign后代不自动删除。

job仍通过同一主线程队列串行执行。排队取消可阻止执行；已开始的代码不能强杀，
客户端超时/取消不能保证场景未改。重试前检查job结果和实际场景。
HIP保存、render/cache和HDA库等外部I/O不属于undo保证，失败要单独报告外部副作用。

## 参数与创建

真实Tab/Shelf初始化与静态类型模板不同。node_info提供实际parent下解析的类型、端口和模板，
不创建scratch；操作卡关键参数不受普通筛选裁切，见[节点卡](node-operation-cards.md)。
精确菜单用token/set_value；数值表达式字符串是HScript，显式Python要声明语言；
VEX仅在snippet内。tuple表达式用组件字段，严格设参不允许跳过未知/无效字段假报成功。
静态multiparm先设置父/子count，再设置实例；动态或超预算情况用原生动词回读，不猜编号。
connect替换既有输入，断开后输入可能压缩，后续使用inputs_after而不是旧索引。

## 小模块构建

[SOP contracts](../houdini/python3.11libs/dsh_sop_contracts.py)负责新增节点的静态检查、构建、cook与清理。
build_module只新增1..64个SOP，不覆盖既有节点或输出旗标；inputs引用更早声明/现有直属子节点，
None为空槽，跨subnet用Object Merge或明确端口。独立静态错误汇总后零创建拒绝。
operation_advisories只描述缺少显式选择：不替用户封口、选边或转类型；没有提示也不证明正确。

output必须是明确新建非空交付；空CTRL/helper用tab_create。required_outputs检查必需分支，
防止非空Merge掩盖丢件。可附实际interfaces；失败或unsupported会使该构建失败并清理新节点。
dry_run只有静态效力。verify_network必须明确output，默认拒绝empty/error；
require_valid=False仅诊断，不能用来完成验收。warning、cook成功和语义正确分别报告。

## 几何、接口与控制

[geometry observation](../houdini/python3.11libs/dsh_geometry_observation.py)和
[quality contracts](../houdini/python3.11libs/dsh_quality_contracts.py)对实际输出做有界检查：

| 方法 | 能证明的范围 | 不能替代 |
|---|---|---|
| Polygon inspect | 指定输出/组的边界、共享边连通、非流形、朝向冲突、逐壳条件性有向体积 | 目标外形、自交、实体强度；分组切口可有意开放 |
| attrib unique | 全量精确tuple唯一性、基数和有限重复样本 | 容差焊接；bbox不变不能排除复制重叠 |
| point spacing | 明确有序点的全量相邻弦长 | 曲面关系、弧长、实体间隙 |
| named surface proximity | 指定实际表面点到目标表面的最近距离与声明基数 | 实体插入深度、全表面无穿插、强度 |
| axis_gap | 实际primitive组沿指定轴的投影间隙和横向重叠 | 任意曲面真实接触 |
| section_proximity | 实际Polygon截面样本对目标表面距离、声明部件覆盖 | 连续全表面接触 |
| stable-ID displacement/transform | 相同Polygon拓扑与唯一point ID下的位移/声明仿射残差 | packed/native primitive内部状态；混合点均值不是设计中心 |

test_controls必须exec：临时数字控制、声明指标/关系/domain，随后恢复参数、keys、frame和完整bgeo。
恢复指纹仅排除导出头时间，不忽略用户属性、拓扑或原生primitive数据。
不支持的表示/菜单/副作用保持unverified；文件/Python/solver副作用不属于恢复保证。
控制响应非零不等于设计正确，单次case不证明所有参数组合。相关修改使旧证据失效。

## 渲染、构图与保存

[camera framing](../houdini/python3.11libs/dsh_camera_framing.py)按八角点在实际普通透视/正交相机中的投影求解；
coverage=.82表示每侧9%的中央安全框，不是面积。full必须完整包络，detail可主动裁切。
A/B复用同framing_frame以及覆盖所有状态的framing_bounds与depth_bounds；前者决定取景，
后者只约束全部实际渲染内容（包含未隔离上下文）的深度。默认depth_bounds取framing_frame的
proxy全包络；只传framing_bounds时两者使用同一包络，独立关注范围应同时传两者。
复用返回framing.bounds/depth_bounds并保持方向/画幅/模式不变；越界零渲染失败，不悄悄移动相机。

detail通过正交宽度或透视镜头视角放大，不靠推进相机。服务相机可调整自身焦距以保持关注范围，
不改变camera_fit保留正式相机焦距的合同。二维outside_safe_frame可标intentional_crop，
near_or_behind_camera/far_clip始终失败；返回depth_check报告全部渲染内容的深度范围，
crop_reasons与错误reasons分开。full中的局部framing_bounds不是ROI，局部观察用focus_group或detail。
Python返回与Bridge证据均以check承载像素事实，pixels为兼容别名；EXR等未支持像素检查时可为null。
图像访问成功不等于异常归因正确；拓扑闭合不能排除相机裁切，也不能由另一视角无缺口推断着色原因。

render_view(EXPLICIT_SOP)使用持久__dsh_houdini_*服务，任务结束复用不删除；不改作正式交付相机。
camera_fit只修改明确授权的静态OBJ cam，保留焦距、清lookatpath、世界空间拟合并回读，
拒绝动画/表达式/约束/偏移窗口/lens shader等未支持状态；dry_run仍属于exec。
render_frame可用framing检查实际USD RenderProduct相机、画幅/裁切/像素比例；
未传保留艺术裁切语义，不隐式调整正式相机。预检不保证位移/运动模糊/遮挡或视觉质量。

渲染相对路径锚定$HIP，缺后缀拒绝；render_check仅证明文件新鲜度/像素事实。
transport、bootstrap、presentation、semantic inspection四层独立；没有成功语义识图就写视觉未验证。
viewport_screenshot用于用户屏幕诊断，不能把视口漂移当成最终模型错误。

scene_save_as需授权的目标路径及expected_current_path，不开放raw load/clear。
资产库修改不是普通场景撤销；create_spare_parms/update_hda的写后回读与锁定定义边界以动词合同为准。
