# 来源、版本与候选验收

## Provenance 与决策

本skill维护工具入口、HDA/脚本生命周期与分发；参数UI唯一正文在houdini-parameter-ui。SideFX公开帮助仅提炼必要机制并链接，不复制手册/示例或用户资产代码。在线文档标识Houdini 22.0，支持目标为H21/H22，未获得对应本机行为复现的项目保持未验证。

职责边界是：SOP等领域负责业务输出；parameter-ui负责参数布局/控件与面板观察；tool-development负责公开工具入口、context、脚本生命周期和分发验收；network-handoff负责节点导航、分组与说明。HDA维护合同只在本skill维护，执行与所有权继续以仓库合同为准。

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
