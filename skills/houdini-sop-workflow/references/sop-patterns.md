# SOP 稳健模式

## 目录

1. 分支的用途与观察
2. Copy to Points
3. 形变与成形顺序
4. 属性传播
5. 局部几何验证
6. 时间动画
7. 视觉与用户 viewport
8. 失败恢复和性能
9. 小模块构建与检查 fast path

## 1. 分支的用途与观察

分支应让人看懂输入、处理目的和可观察输出；短链靠命名与接线即可，复杂依赖再补说明。
选择能区分当前疑点的观察：cook回答能否计算，属性回答数据传播，局部几何和图像回答成形效果。
材质、高光或取景也可以帮助定位轮廓与接缝，不必等待全网检查完成。
涉及空腔、交错、厚度、配合等结构含义时，见[检查与所声称的性质](procedural-quality-contract.md#检查与所声称的性质)；
能算出、件数正确和表面闭合不能互相替代。外观有疑点时读[建模诊断](modeling-methods.md#4-停止与验收)。

## 2. Copy to Points

适用：把一个或多个源几何复制/实例到模板点。

模板点常用属性：

- `P`：根位置。
- `orient`：四元数旋转。
- `N` + `up`：没有 orient 时的对齐基。
- `pscale` / `scale`：统一/非统一缩放。
- `id` / `phase` / `variant`：后续随机和动画标识。

按实际变换与属性传播选Copy to Points或classic Copy；未知接口先查节点信息。
检查模板点的实际属性，以及复制后单件的尺寸和方向；不能由全场bbox推断模板属性已被消费。

## 3. 形变与成形顺序

中心线驱动非刚性变形时，一种可观察的组合是：

```text
中心线/低维拓扑
→ curveu/rest/root 等驱动
→ 时间变形
→ Sweep/ribbon/skin 生成宽度
→ Copy/Merge
```

或对每实例刚性摇摆：

```text
成形后的单元
→ 模板点时间依赖 orient
→ Copy to Points
```

危险模式：

```text
中心线保存 local P
→ PolyWire/Sweep 生成截面
→ 用旧 local P 重建所有截面点
```

它可能把截面点压回中心线。使用rest/local坐标时核对捕获阶段、属性传播和当前点的对应关系。

## 4. 属性传播

检查属性 class：point、primitive、vertex、detail。Copy/Merge 后：

- 驱动属性是否复制到所有目标点。
- `Cd/N/uv` 是否因输入不一致产生默认值。
- 同名不同 class/size/type 是否冲突。
- 部件身份、side、局部坐标或下游使用的分组是否仍可追踪。

Merge的属性不一致warning影响取决于属性用途。先读具体节点、属性和下游消费者，
再选择统一class/type、重命名不同含义的属性，或给不适用的分支初始化明确默认值。
例如只在支架分支有`part_id`，合并时可保留其身份并用约定的非成员值/组标识其他分支；
默认值要能与有效ID区分。只有确认没有构造、选择、修改或外部消费者用途的临时属性才删除。
无需消除的警告说明实际影响和观察范围；warning数量不衡量模型质量，消警也不应损失可编辑性。

## 5. 局部几何验证

全场 bbox 会被散布 root 位置放大，不能发现每个实例零宽。

使用：

```python
geo_piece_stats(copy_or_deform_node)
```

检查：

- piece count 是否符合实例数。
- sampled piece 的 extent/area。
- `degenerate_surface_pieces`。
- 变形前后 piece 面积和最小 extent 是否保留。

需要追查时先隔离一株/一个 piece，再看全场。

## 6. 时间动画

不要只写 `@Time` 就宣称动画成立。

```python
geo_frame_diff(out, 1, 12, attrib='P')
```

验证：

- 根部或锚点近似不动。
- 尖端/活动点有显著位移。
- 波峰沿预期方向传播。
- frame A/B 的 topology 是否一致。
- 用户当前 frame 在调用后未改变。

全局 `mean_delta/max_delta` 非零证明时间依赖，不自动证明审美语义。若固定相机 A/B 暴露完全静止、方向相反、主体缺失等明确反例，应回到风场设计；若节点、属性、锚点/活动区和时间依赖均通过，而两张静帧只是不足以裁定细微动态或视觉力度，可诚实交付“画面待用户播放判断”，不能宣称视觉已经确认，也不必无限渲染说服视觉模型。

做render A/B时锁定相同direction/画幅/模式，复用framing_frame和覆盖状态的framing.bounds、framing.depth_bounds；核对matrix/focal/orthowidth，差异会把相机变化混入pixel diff。full取景不足应修正事先选定的共享包络，不逐帧移动相机；减小coverage会留更多边距，不是扩大coverage。detail只允许二维裁框，depth_check失败不能当有意裁切；focus未隔离时深度包络还包含周围几何。

若 geometry diff 非零但 render diff 为零，调查 proxy/ROP 缓存；若两者都为零，调查表达式、spare 参数和 time dependency。

## 7. 视觉与用户 viewport

- `render_view(EXPLICIT_SOP)`：agent 产物验证，走隐藏 proxy；用户 display/visibility 不选择源。
- `viewport_screenshot`：用户屏幕诊断；用户显示空节点时空图是正确诊断结果。
- 两者对照：render 有内容而 viewport 空，说明用户 display/viewport 漂移；两者都空，回到 SOP 数据。

视觉 prompt 先中性描述，不要预设“这是成功的草地”。

## 8. 失败恢复和性能

- 利用 exec undo rollback；失败结果检查 `rollback.applied`。
- 文件写入和 HDA 库修改不在 Houdini undo 范围内，必须另做事务/备份。
- 按可独立保留的工作划分构建批次；紧密耦合的修改保持同一事务。
- 性能以 cook time、点面数和 SideFX Performance Monitor 为证据，不用工具调用次数代替 cook 性能。
- 需要整理网络时用`layout_nodes`；缺省只整理当前 agent session 创建的节点并返回
  `foreign_nodes_skipped`，不要为了整洁移动用户临时创建的节点。

## 9. 小模块构建与检查 fast path

精确签名和返回读verb_help。tab_create返回hou.Node，list_parms/read_parms返回list；选择参数名用read_parms(names=[...])。
菜单优先使用当前token/set_value，数值字符串是HScript表达式，tuple表达式使用实际组件名。
None保留空输入槽；跨subnet使用明确端口或Object Merge。connect直接替换指定输入，Merge先断后接可能前移槽位，回读inputs_after。
控制默认值与当前值是不同操作，分别使用create_spare_parms(update_defaults=...)和set_parms并回读。

声明Sweep第二输入时tab_create会在接线后校正surfaceshape=input，build显式parms仍优先。
静态node_info默认值不保证等于Shelf创建值；保留卡片components/usage_notes，不只回传参数名。
build_module的独立参数/输入错误一次汇总为preflight errors，按具体field/components一起修，不重发多次长spec猜字段。
组合多个交付分支时可传required_outputs=[分支输出名,...]，防止Merge非空掩盖某个必需分支为空；
辅助空CTRL不在此列。仍优先按可独立检查的小模块构建，不把所有造型塞进一个大batch。

准备阶段读node_info的usage_notes/operation_card.decisions/operation_parameters；关键设置不受
普通参数filter/limit裁切。单节点事实仅由随包操作卡维护，不在reference复制菜单索引或默认值。
build_module按声明准确构建并返回执行与输出事实；类型、参数或引用有疑问时可先dry_run。
节点知识按需查询，表示、封口与选边由任务决定；静态预检通过不证明几何正确。
重复构造尚不确定时，在单元上观察实际表面/截面可避免把同一错误复制到整件；已有可靠来源可直接组合。
用geo_piece_stats(out,inspect=True,group=...)观察边界和局部basis extent；非Polygon返回unverified。
有意分组切口不视作整体实体破损，整体bbox不能证明弯曲薄片有管状截面。
同一exec后项失败会回滚前项成功的模块；transaction记录最终状态，普通诊断读取放query。
独立模块分不同exec提交，再用仍存活的输出集成；不能独立验收的部件保留同一事务，不能靠catch
异常让半成品提交。返回已知validation即可，陌生返回类型先verb_help查看return_type/call_mode。

适用：在现有 SOP parent 中新增一个可以独立 cook 的小模块；H21.0.440/H22.0.368 的
类型、参数菜单、失败清理与 warning 传播已有工具回归。行为发布仍需未见新 session 验证。
不适用：修改既有节点、OBJ parenting、Karma setup、HDA 库编辑或模拟写盘；这些继续使用
对应 primitive/domain verbs，不把多种生命周期塞进一个 build。

输入是新节点声明和已有输入，输出是一个明确 SOP。例如（parent 是当前任务的 SOP 容器）：

```python
card = node_info(parent, 'xform', parm_filter='scale')
spec = [
    {'name': 'unit', 'type': 'box'},
    {'name': 'shaped', 'type': 'xform', 'inputs': ['unit'], 'parms': {'sx': 1.5}},
    {'name': 'OUT_MODULE', 'type': 'null', 'inputs': ['shaped']},
]
# 接口已知可直接构建；有静态字段疑问时才 dry_run，它不证明 VEX/cook。
# build_module(parent, spec, output='OUT_MODULE', dry_run=True)
result = build_module(parent, spec, output='OUT_MODULE')
__result__ = result['validation']
```

消费 checkpoint，不只看 Python 成功：

- `validation.ok=False`：error或空输出，定位失效部分；下游依赖该结果时先修复，独立工作可继续。
- `warning_free=False`：检查 issues 中的真实节点和属性；解决或记录明确边界。
- `scope/checked_nodes`：说明检查覆盖；模块范围不能冒充整网。
- `semantic_status='unverified'`：还要验证原型、关系与视觉，不能自动改成 pass。
- `frame/checked_at/output_fingerprint`：用于识别证据属于哪个输出状态；抽样指纹不是
  全量拓扑/材质证明。用户或 agent 改了受影响参数/接线后重新检查。

输入只引用前面 spec 或现有直属 child 名，可用 None 跳过input；如 Wrangle 的 `[None,'anchors']`。
跨 subnet 在目标网络创建 Object Merge 并用objpath1引用源，不尝试用不同端口跨网络接线。
模块不覆盖同名节点，失败清理本批新增节点，
不自动改变用户 output；单节点仍可 `tab_create`。收尾再 `sop_set_output`。

菜单示例：`set_parm(wrangle,'class','detail')` 的 detail 是 token，不是 label/任意表达式；
动态菜单由 `list_parms(wrangle)` 给出。需要菜单表达式时显式传
`{'expression': '0', 'language': 'hscript'}`；表达式与普通字符串不混猜。

失败转向：消费returned error和实际node_info/list_parms；没有新信息的重试改为最小诊断，
区分类型、参数、输入与cook问题，保留已成功的独立部分。临时probe用完清理；文件/参数回调副作用不在模块删除保证内。

来源：本项目严格设参、SOP 模块回归与节点卡运行结果；SideFX
[Parm API](https://www.sidefx.com/docs/houdini/hom/hou/Parm.html)。
`verify_network(parent,output=out)`需要显式output；省略output不跟随display，空/error输出
默认硬失败。`require_valid=False`仅供保留失败诊断，不得替代复验。读取operation-evidence中的
output/frame/scope/失败原因，而不是只看开头“Python执行成功”或取不存在的errors字段。

已有节点的局部文本更新适用set_parms的literal patch；先在query读取实际字段：

```python
__result__ = read_parms(target, names=['snippet'])
```

再在exec使用读到的source_sha256及实际的唯一锚点（old_text/new_text由本次改动决定）：

```python
set_parms(target, {'snippet': {
    'expected_sha256': source_sha256,
    'patch': [{'old': old_text, 'new': new_text, 'count': 1}],
}})
__result__ = verify_network(parent, output=output)
```

缺锚点/多命中/hash过期时，重读当前字段并修正补丁；不删除expected_sha256或随意增加count。
本节点本批全部patch在任何设参前校验；跨节点仍以模块事务划分，不能把它当跨节点dry_run。
只支持无动画/表达式的literal string；带表达式/keys的代码先明确编辑意图，用原设参或资产接口，
不烘焙后冒充保留动画。输出hash证明文本回读，VEX语法/非空几何/关系须照常验收。
补丁数量、字符预算与返回字段以verb_help为准。无需全文替换时返回也只含变化摘要。

验证入口：tools/tests/dsh-parameter-patch.test.py、dsh-module-boundaries.test.py。


node_info返回默认multiparm实际编号；build_module支持显式
整数count（0..64）并按父count→子count→字段顺序赋值。动态count/超过静态预算仍走
原生tab_create/list_parms，不为预检限制改写成VEX。数值参数字符串为HScript表达式；需要
显式语言用{expression,language}。先前错误节点的cook_node会刷新旧错误；仍失败直接读
cook_details定位，不重发无关模块。Toggle的test_controls用整数0/1，菜单/按钮仍不支持。


node_info菜单项的set_value是可直接设置值，菜单token也由setter转换；菜单表达式用显式对象。
替换Merge既有输入直接connect，断开后消费inputs_after再操作；不要把旧索引当稳定身份。
