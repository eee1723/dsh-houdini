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

Viewer State 开发先核对目标版本 Type Properties 的 Interactive/State Script 与原生生成器，明确进入、操作、取消和退出的状态恢复。参考 [Operator Type Properties](https://www.sidefx.com/docs/houdini/ref/windows/optype.html) 的 Interactive 部分；此处只提供选择与完成门，具体事件/API 尚需本机帮助及最小交互实验，不声称已有通用验证配方。
