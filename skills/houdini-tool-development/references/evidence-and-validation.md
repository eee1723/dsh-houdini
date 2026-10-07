# 来源、版本与候选验收

## Provenance 与决策

本skill维护工具入口、HDA/脚本生命周期与分发；参数UI唯一正文在houdini-parameter-ui。SideFX公开帮助仅提炼必要机制并链接，不复制手册/示例或用户资产代码。在线文档标识Houdini 22.0，支持目标为H21/H22，未获得对应本机行为复现的项目保持未验证。

职责边界是：SOP等领域负责业务输出；parameter-ui负责参数布局、控件、绑定及参数面板的判断依据；tool-development负责公开工具入口、context、脚本生命周期、通用界面观察方法和分发验收；network-handoff负责节点导航、分组与说明。HDA维护合同只在本skill维护，执行与所有权继续以仓库合同为准。

## 观察实际工作界面

界面观察回答具体的使用问题：用户能否找到操作、当前控件是否裁切、状态反馈是否清楚，或教程操作后本机界面是否对应预期。先明确需要看的表面与状态，不因新增截图能力为每一步操作拍图。

检查用户当前工作界面时先发现当前可见目标，再根据类型、标题、所在pane和当前节点等事实选择明确目标；同标题窗口不能只按标题猜选。目标关闭、隐藏、切换标签或已失效时读取当前事实后重新选择，不用旧目标自动回退到另一个窗口。

调用顶层`houdini_ui_list`取得当前`surfaces`，使用其中`target`原样调用`houdini_ui_screenshot(target=...)`。`kind`、`label`、`pane_type`、`node`与屏幕位置只用于辨认对象，不能据此编造target；`supported`与`reason`说明当次发现的支持条件，实际截图仍以捕获结果为准。target是当前运行环境的引用，不跨重启持久。只捕获任务相关表面，不为发现界面遍历所有Qt子控件或读取无关文本。

列表覆盖当前显示的原生paneTab、同进程可见Qt顶层窗口（QWidget容器）和QDockWidget面板容器；隐藏标签、隐藏窗口、Popup/Tooltip及任意普通Qt子控件不作为独立目标。纯QWindow/Qt Quick窗口不在当前发现范围。pane截图是该pane的屏幕区域，Qt窗口截图是其客户区，不包含系统窗口边框；只有当前可见内容可用于判断。模态对话框保持未支持，不为取得图片确认、取消或关闭它。

截图只接受发现所得`target`及图片输出选项，不接受node/view/width/height，不创建临时参数或网络面板。需要打开节点、切换页或检查宽/窄布局时，先把它作为明确的界面交互处理，再发现并截图当前实际显示；已有交付节点可用focus_node按真实ID定位。尺寸测试按预期使用条件选择，不作为统一设计规格，也不伪装成只读截图。具体签名以现场工具说明为准。

已有表面的捕获保持当前显示状态，不为了取图打开隐藏窗口、切页、改变滚动/选择/视角、移动缩放、激活或关闭窗口。若需要测试另一页或宽度，这是另一个明确的交互或自有窗口测试，不能包装成只读截图。只看一个首屏不能证明其他页、滚动区、窗口大小或焦点下的行为。

新增工具窗口使用稳定的模块/入口标识、清楚的中文标题和Qt objectName，便于定位与维护；这些标识不构成HOM写权限。检查主要操作、输入选择、无选择/空结果、错误/长操作反馈和关闭后状态，按工具实际承诺挑选用例。截图不点击控件，不替代真实按钮、选择器、快捷键或Viewer State的操作验证。

原生Qt控件的绑定与实际绘制分别判断。ParmDialog的node/visibleParms回读正确仍不能证明独立Qt窗口里已画出参数；按实际宿主载体与Houdini版本观察真实图像，不用元数据替代像素，也不为未绘制窗口补造控件画面。

使用顶层界面工具，HOM仍经Bridge主线程队列；不把截图放进同步houdini_exec，也不通过嵌套事件循环或回调注入绕过队列。可见目标不等于一定可捕获：屏内/遮挡条件、原生绘制区域、活动模态窗口及宿主版本以当次结果和已验证范围为准，未支持时如实保留缺口。

先确认当前模型图像输入能力，再分别看真实捕获、附件送达和作者语义读图。黑图、失效目标、传输错误先读原始错误及同一request回执；参数写入或求值不符合预期先核对实际值、引用和输出，不靠反复拍同一画面定位原因。没有新的观察条件或具体待答问题时不继续盲拍。

根据实际图像检查可发现性、文字裁切、操作顺序和当前状态；只声明图中能确认的范围。无法识图时继续结构与行为验证，明确视觉未验证。截图通常是临时观察资料，不为它强制Save As，也不把临时图片全部交付给用户；路径和最终图片规则沿用houdini-network-handoff。

## 官方机制与设计判断

| Claim / 决策影响 | 来源 | 适用与反例 | 最小复核 |
|---|---|---|---|
| 定义界面不同于实例 spare parms；选择修改层级 | [Type Properties](https://www.sidefx.com/docs/houdini/ref/windows/optype.html) | HDA 公共 UI；单节点临时控制不必改类型 | 两个实例中确认定义改动范围，保留旧值/引用 |
| PythonModule 与事件/磁盘模块生命周期不同；避免隐式实例状态 | [HDAModule](https://www.sidefx.com/docs/houdini/hom/hou/HDAModule.html)、[locations](https://www.sidefx.com/docs/houdini/hom/locations.html) | 可复用工具；HIP 私有原型可用 session | 新实例真实回调、不同实例不串状态、GUI/headless 分别加载 |
| Shelf 通用拖放可能丢失自定义创建交互 | [Tool scripts](https://www.sidefx.com/docs/houdini/hom/tool_script.html)、[Shelf](https://www.sidefx.com/docs/houdini/shelf/customize.html) | 资产自定义工具；普通节点通用创建无需改写 | 比较实际公开创建入口，取消无半成品 |
| 动作定义不同于个人绑定；H20.5+ 用新配置体系 | [Hotkeys](https://www.sidefx.com/docs/houdini/basics/hotkeys.html) | H21/H22；不发布旧 keymap 片段或通用固定键位 | 动作可发现、真实按键、冲突与持久化 |
| package 组织资源搜索路径；外部模块是有效分发选项 | [Packages](https://www.sidefx.com/docs/houdini/ref/plugins.html) | 多文件工具；单 HDA 不需强加外部包 | 干净环境确认实际加载路径及缺依赖失败 |
| Panel 是独立 UI 入口，不据在线旧提示断言 Qt 兼容 | [Panel Editor](https://www.sidefx.com/docs/houdini/ref/windows/pythonpaneleditor.html) | 复杂工作台；普通按钮优先原生参数 | 目标版本绑定、重复开关与引用释放 |

官网机制、特定本机复现和未见自然任务各自陈述；工作流整体为candidate。UI分组、薄入口和代码布局是项目设计建议，不作为所有Houdini项目的强制规定。默认不分发个人键位、不外推Qt组件版本，也不要求所有工具都必须单HDA。

## 机制验证与行为验收入口

`tools/tests/dsh-hda-public-contract.test.py`覆盖原生subnet间接输入、输入/输出声明、公共消费者、
定义保存后的表达式/双实例隔离、标准输入标签隐藏与业务标题保留、spare冲突库写前拒绝。
机制回归不替代作者工作流；新任务仍需完成各端口、参数域和真实UI验收。

界面增量与交付检查已有H21.0.440/H22.0.368隔离hython回归入口：
tools/tests/dsh-hda-interface-patch.test.py、tools/tests/dsh-hda-delivery.test.py。
覆盖旧通道状态/新默认、过期版本与恢复、真实按钮异常/菜单/重复调用、不同输入、错误结果、
缺Python模块和子HDA偷偷加载原开发路径。对应机制具备双版本实验依据，整体skill仍为candidate；
这些固定夹具不证明新session采用、未见任务质量、GUI布局或Shelf/快捷键交互。

可选布局组件的来源、已知失败面和双版本机制测试在[UI组件](ui-components.md)维护。原生GUI画廊在H21.0.440/H22.0.368的420px浮动参数面板核对中文、mode显隐、重复条目命名与禁用；不外推其它字体配置、用户原资产效果或任意窄面板。测试worker完成报告后由launcher回收，不把原生floating pane的回调关闭当作已验证生命周期。

`tools/tests/dsh-tool-entry-ui-gui.test.py`从仅含声明资源的package发现原生Panel、Viewer State和Shelf，覆盖Panel重载、搜索、chooser信号输入、窄窗口，以及真实Shelf进入状态后退出且场景保持。H21例子使用继承宿主主题的QTreeView，因为该版没有hou.qt.TreeView。物理节点选择器选择、视口鼠标/键盘与高级handles仍未验证；入口例子不是完整业务工具或任意工具制作泛化证据。

原生Package通过dsh-package-discovery、dsh-package-gui与dsh-tool-packages回归检查配置/加载分离、多资源路径、敏感值、名称冲突和失败事实。dsh-tool-packages-gui在H21/H22的干净启动中，以普通JSON直接注册唯一源目录，验证真实HDA/Shelf/Panel和原场景保持、运行态动作不改JSON/源；向已注册源添加Shelf后由下一新进程发现。此范围不外推动态插件依赖、任意用户工具生命周期或模型自然选择。

以下为完整行为矩阵；上述机制回归只覆盖相应子集，其余仍待执行。使用隔离 H21/H22 环境和自建夹具；agent 对live场景的操作走 Bridge。离线纯语法/打包检查不等同于 GUI 或自然任务验收。

| 类别 | 用例与可观察判据 |
|---|---|
| 既有失败模式 | 动态菜单显示选项但默认值为空：新实例从真实入口验证 token/实际值/最终结果；内部 helper 成功不足以通过 |
| 未见同族正例 | 制作不同类型的小工具，含模式控制、按钮与外部共享模块：从公开入口得到指定输出；移出原开发路径仍可运行 |
| 相邻反例 | 只要求创建普通 SOP 网络：选择 SOP skill；不擅自封装 HDA、加 Shelf 或改快捷键 |
| 领域内反例 | 只改已有按钮 label：保留内部 name、回调和依赖；不要求完整渲染或重建工具包 |
| UI/context | 新实例、窄面板、禁用/隐藏、多选择、无选择、取消；真实 Shelf 和快捷键在指定焦点各触发一次 |
| 版本矩阵 | H21/H22 各自确认 Python/Qt、配置格式、模块路径、HDA 定义和公开入口，不从一版成功外推另一版 |
| 失败恢复 | 缺子 HDA、模块缺失、第二个写入失败：不虚报成功；区分场景 undo 和库/偏好文件恢复，重复失败停止猜测 |
| 最终交付 | 最后改动后复验、隔离依赖、产物路径/hash、无未声明 helper；新 session 核对 catalog、隐式触发和 references 可读 |

结构验证：仓库治理 audit、skill-creator quick_validate、npm run docs:check、npm run build、npm pack --dry-run。行为门未通过前不标 verified/released。下一步是真实入口、GUI 与版本矩阵验收，活动交接从 docs/handoff.md 统一跟踪；回滚只恢复本次相关文件及注册行，不覆盖其他在途修改。
