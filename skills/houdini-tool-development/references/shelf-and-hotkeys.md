# Shelf、快捷键与其他工具入口

适用：新增或维护用户会直接调用的工具入口；点击现成工具完成普通建模不需要此流程。

## Shelf 与 Tab

采用“一个可测试动作函数 + 薄入口”的候选路径。先明确工具是否创建节点、处理选择或启动交互，再核对 network/viewer context、kwargs 和取消行为。SideFX [Tool scripts](https://www.sidefx.com/docs/houdini/hom/tool_script.html) 说明 Shelf/Tab 脚本共享的原生入口机制；需要创建交互时核对目标版本自带 toolutils 等实现，不凭名字复制调用。

设计建议：工具使用稳定且带项目命名空间的内部 ID；label 用明确动作，图标和帮助说明作用及选中对象要求。按实际用途组合 tab，避免一工具一架或重复同名按钮。首次先验证一个工具，再扩展一组入口。

持久工具存于 `toolbar/*.shelf` 或明确的 HDA 内嵌位置；`session:` 只用于临时工具。Shelf set、tab、tool 分别组织，不以新建 tab 证明工具已正确注册。拖节点到 Shelf 会生成通用脚本，资产已有自定义交互时应添加资产自身工具。来源：[Customize the shelf](https://www.sidefx.com/docs/houdini/shelf/customize.html)。

验证：正确上下文、错误上下文、空选择、多选择、取消、重复点击；检查目标网络、选择/flags、撤销范围和磁盘副作用。Tab 成功不替代 Shelf/快捷键入口验证。

## 快捷键

先定义动作与适用 context，再决定键位。优先保留用户绑定；新工具可只提供可绑定动作。用户要求默认按键时检查目标 context 的冲突、文本输入焦点和键盘布局，不按个人习惯覆盖全局键。

H20.5 起新体系区分动作、context 与默认绑定，对应 `HotkeyActions.json`、`HotkeyContexts.json`、`HotkeyDefaultBindings.json`。用户 `.keymap2`/overrides 用于绑定变更，不作为新增动作及描述的唯一来源；H21 已移除退回旧体系的环境变量开关。配置相对布局和 schema 从目标版本 `HOUDINI_UI_PATH`/自带文件核实，未验证前不生成猜测的 JSON。

以上是 SideFX [Configuring hotkeys](https://www.sidefx.com/docs/houdini/basics/hotkeys.html) 的机制；本项目据此建议分发动作定义并尽量保留个人按键。Shelf 可从界面关联快捷键，不必为了单个按钮建整套配置。

测试动作实际触发、只触发一次、焦点/context 冲突、保存重开及移除本工具后的绑定影响；回读绑定不证明按键可达。自动测试未覆盖真实按键时写“快捷键交互未验证”。

## 面板与视口交互

参数控制先用原生 HDA UI；跨资产浏览/列表/长期工作台可考虑 Python Panel；持续的视口拾取、拖拽及手柄交互考虑 Viewer State。不要把一次按钮操作扩成定制窗口。

Panel 的 `.pypanel` 是入口定义，复杂逻辑仍放模块；按实际 Qt/Python 版本核对绑定及生命周期，覆盖多次打开关闭、selection 改变与对象删除后的引用处理。SideFX [Python Panel Editor](https://www.sidefx.com/docs/houdini/ref/windows/pythonpaneleditor.html) 是定义格式入口；当前 online 页面有混杂的旧版本提示，不能直接当 H21/H22 Qt 兼容表。

Viewer State开发先核对目标版本Type Properties的Interactive/State Script与原生生成器，明确进入、操作、取消和退出的状态恢复。用唯一状态名绑定factory；参数、handles与guide按业务需要添加。连续修改用状态undo边界，退出/中断后不留下工具私有选择、提示或监听。参考 [Python states](https://www.sidefx.com/docs/houdini/hom/python_states.html)；不同viewer能力与实验HUD保持实际版本边界，不声称一个状态适用于全部上下文。

## 可继续修改的入口源码

[入口资源构建器](../scripts/build-entry-examples.py)按目标Python版本把[源码资产](../assets/tool-entry-examples/dsh_artist_example_panel.py)组织为独立资源树，不安装或修改用户配置：

```powershell
python skills/houdini-tool-development/scripts/build-entry-examples.py --python-version 3.13 --output E:/tmp/artist-entry-resources
```

只在明确的空输出目录运行；3.11/3.13是此例的声明目标，不能据目录存在外推其它版本。派生用户工具时，先选定已有包或新包及唯一源码位置；已有注册路径覆盖资源时不用改JSON。新包用tool_package_create令注册JSON直接指向该资源目录，按已有授权另行加载，不生成ZIP或构建/安装副本。资产源码是此例维护源；派生后在用户选定源码同步入口，不保留两个可独立手改的权威副本。

- Panel例子用原生NodeChooserButton、SearchLineEdit和TreeView浏览明确SOP的参数模板，不cook、不修改节点；.pypanel仅转发创建、销毁与HIP/导航生命周期。参数双向编辑若需要可嵌入hou.qt.ParmDialog，仍须验证用户的动画/表达式和目标范围。
- [Viewer State例子](../assets/tool-entry-examples/dsh_artist_example_state.py)是nodeless XZ平面坐标读取，包含进入、鼠标事件、提示与退出；Shelf薄入口进入同一状态，不建节点。它不是geometry拾取、handles编辑或完整建模工具，需按任务继续实现与验收。
- 资源构建器保留模块名和状态ID示例前缀；派生新工具时同时更换Python模块、Panel、Shelf、Viewer State标识，避免重复加载遮蔽。实例业务不依赖DSH注入或开发机绝对路径。

原生菜单ASCII标签与中文面板/提示分开。声明可移机时在无仓库Python路径的新进程仅加载生成资源和声明依赖；注册状态、内部函数或Shelf脚本文本存在不等于真实视口鼠标交互已通过。
