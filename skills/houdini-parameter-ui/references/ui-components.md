# 可组合的参数UI组件与设计参考

用于把一组控制整理成可发现、可调整的原生Houdini界面。组件是可选的局部组合，不是固定皮肤或整套HDA架构。
只有一个参数就用一个原始spec；业务逻辑、网络和资产命名仍由当前任务决定。不要为了采用组件额外添加开关、页签或层级。

## 按用户操作选择结构

| 用户需要 | 候选结构 | 不适用情形 |
|---|---|---|
| 在少量不同任务之间切换 | 普通tabs：例如整体控制与局部细化 | 每页只有一两个字段时，简单分区可能更直接 |
| 开关一个功能，并调整其细节 | section：标题开关与折叠区 | 必需且始终生效的设置不必有额外开关 |
| 一个开关/模式紧邻它控制的值 | row：同排控件 | 长文件路径、Ramp或很多字段会挤压空间 |
| 偶尔调整响应曲线 | remap：开关与按需显示Ramp | 核心曲线应始终可见，可直接放原始ramp |
| 用户决定同类条目的数量 | repeater：原生multiparm | 少量语义不同的固定页面不必转为重复块 |
| 折叠后仍需常用主控 | section.header_parm | 控件含义与标题不一致、引用在区外时容易误导 |

常用控制先出现，低频选项按需展开。先按任务阶段分组，再决定分组是否需要tab；深层嵌套有真实用途时保留，不把“层数少”当机械标准。
同类模块保持字段顺序和标签习惯，比照搬某个资产的参数名称更有价值。开关可见不证明下游逻辑已接线。

## 最小调用

读取当前版本verb_help后，在exec中按载体选择入口。普通节点使用create_spare_parms(layout=...)默认追加，拒绝同名覆盖；HDA定义使用hda_set_interface(layout=...)整组重建。
先用dry_run=True检查展开树和建议。spare追加保持已有通道状态；HDA已有值/动画需保留时使用适用的edits模式。所有权范围由载体决定，不由组件扩大。

```python
layout = [{
    'component': 'section', 'name': 'detail', 'label': 'Detail',
    'enabled': False, 'collapsed': True,
    'parms': [
        {'type': 'float', 'name': 'strength', 'label': 'Strength',
         'default': 1, 'min': 0, 'max': 2},
        {'component': 'remap', 'name': 'response', 'label': 'Response'}
    ]
}]
preview = create_spare_parms(node, layout=layout, dry_run=True)
# 核对preview.interface/ui_analysis后，对同一明确目标应用。
create_spare_parms(node, layout=layout)
```

| component | 字段与展开结果 |
|---|---|
| row | parms；展开为同级叶控件，自动设置join_next，最后一项不继续连接；拒绝folder/Ramp |
| section | name/label/parms；可选enabled、collapsed、header_parm、help。enabled省略时没有开关；提供时生成name_enabled，放在folder外。子控件禁用条件与原条件按“或”组合 |
| remap | name/label；可选enabled、ramp_type(float/color)、help。生成name_enabled和name_ramp，默认关闭曲线，Ramp控制点面板默认折叠 |
| repeater | name/label/parms；style为tabs/list/scroll，count为0..64，label_ref可指向条目内字符串参数；子字段按原生规范包含#，一层重复一个# |

其他条目直接使用原始spec，可与组件混用。name必须稳定且唯一；组件只为自身生成的控件命名，不自动给用户提供的子参数改名，也不重写业务表达式。
重复块内部当前适合普通spec和row；section/remap的组件name不接受#，需要此类组合时先用原生spec明确每个引用。

## 原生字段补齐

- float/int的components支持1..4，默认值长度必须对应；look支持regular/vector/color，color要求3或4分量。
- ramp支持float/color、points(2..16)、basis(linear/constant/catmullrom/bspline)、show_controls。当前表达默认点数量和插值，不提供任意自定义控制点曲线或其状态迁移。
- label生成真实显示文本；heading/空白间隔/无滑条等使用原生tags，可按需要调整。
- folder支持simple/tabs/collapsible与multiparm_list/multiparm_tabs/multiparm_scroll；普通folder支持ends_tab_group和单页/单区tab_hide_when/tab_disable_when，multiparm不支持tab条件。
- 控件支持disable_when、hide_when、hidden、hide_label、join_next。这些是UI状态，不代替严格参数校验或后端业务条件。

## 复刻时实际遇到的问题

| 失败面 | 为什么影响设计 | 当前处理和边界 |
|---|---|---|
| 自省漏掉单页条件 | 看见参数树却不知道某页为何消失/禁用 | hda_info增加tab_conditionals与UI分析；请求足够max_depth，截断时不判断全局完整性 |
| 标题/条件引用拼错 | 界面能打开，相关开关却可能失效 | ui_analysis提示未解析引用，不自动猜同义名；tuple分量/动态或外部引用需人工核对 |
| 菜单索引与UI条件token混淆 | eval返回索引，条件却可能需要符号token | 实际菜单token与条件相互核对；分析器提醒可疑数字比较，不盲目改写 |
| HDA页签内部名被原生归并 | 提交名不一定是最后的folder-set参数名 | 自省实际FolderSet/标签树，验证结构顺序；不按未确认的name操作页签 |
| 只给folder设禁用条件 | 模板回读正确却不保证子控件状态回读一致 | section同时给叶控件附加条件；原始folder仍保留原生机制，不能由模板存在宣布GUI已验证 |
| Label只填label属性 | 可出现分隔区域却无可读标题 | 同时提供column_labels显示文本，并以原生面板确认 |
| 重复块#与条目标签 | 错误名字不能创建实例；相同默认标签让条目难区分 | 预检占位层数；label_ref可选。没有合适业务名称时使用索引，不强配重复标签 |
| 行过密、层级过深 | 合法结构在窄面板中仍可能难用 | 只给布局建议；不按固定审美阈值阻断或自动重排 |

## 分析与样例

parameter_ui(node,max_depth=12,analyze_ui=True)返回ui_analysis：类型计数、深度、标题开关数、单页条件数、结构建议和截断标志。hda_info保留兼容。
它不执行回调/菜单，不cook，不复制源码，也不生成“视觉正确”的证书。发现引用不存在时先核对当前实例，再决定是否需要修复。

[组件画廊JSON](../assets/ui-component-gallery.json)包含两种可编辑组合：整体/细节控制，以及重复属性条目/输出区。
只展示通用结构，没有参考资产的内部代码、专有类型、机器路径或建模效果。可删改任何分组，不能把画廊的字段当任务必需项。

在空白隔离hython进程运行[画廊构建器](../scripts/build-ui-gallery.py)并传--output到仓库外目录，会生成两个HDA、一个HIP和节点索引。
脚本拒绝非空场景与覆盖既有产物；不要在用户当前HIP运行。业务效果故意为空，完成门只覆盖界面机制。

## 来源与验证

来源：用户授权分析的两种复杂SOP资产公开界面，加SideFX H22在线
[Heading interfaces](https://www.sidefx.com/docs/houdini/ref/windows/optype.html#heading-interfaces)、
[FolderParmTemplate](https://www.sidefx.com/docs/houdini/hom/hou/FolderParmTemplate.html)、
[RampParmTemplate](https://www.sidefx.com/docs/houdini/hom/hou/RampParmTemplate.html)。核对日期2026-09-10。
用户资产仅提炼通用组合，不将资产内容或原始分析快照纳入分发。

H21.0.440/H22.0.368的tools/tests/dsh-hda-ui-components.test.py验证生成、条件状态、向量/颜色、Ramp、重复块增删和重载，以及错误名称/字段/简单布局反例。
tools/tests/dsh-hda-ui-gui.test.py可选地在新建自有GUI进程输出原生面板截图，无需computer-use；截图成功和语义可读需分别判断。
机制证据与作者固定样例不等于未见自然任务泛化；具体艺术布局仍是可选设计建议。
