# 原生艺术家交互参考

适用于选择操作结构、参数组件与原生入口。下表“官方事实”来自SideFX H22在线文档；“应用建议”是本项目设计判断。查阅文档不等于目视目标版本GUI，真实布局与业务效果仍要独立验证。

| 参考 | 官方事实 | 应用建议 |
|---|---|---|
| [Attribute Adjust Float](https://www.sidefx.com/docs/houdini/nodes/sop/attribadjustfloat.html) | Constant/Random/Noise/Attribute来源，范围与权重，Ramp重映射 | 先选择变化来源，再显示有关设置；把算法变量转成范围、分布、响应 |
| [Attribute Adjust Color](https://www.sidefx.com/docs/houdini/nodes/sop/attribadjustcolor.html) | 固定颜色、属性与图片采样，RGB/HSV分量控制 | 值与来源紧邻；颜色、Ramp和预览表达效果，保留色彩空间术语 |
| [Scatter and Align](https://www.sidefx.com/docs/houdini/nodes/sop/scatteralign.html) | 点分布、尺度、朝向供Copy to Points使用，建议看到实例结果后调节 | 按艺术操作分区，guide或实际实例预览帮助理解随机与方向 |
| [Curve 2.0](https://www.sidefx.com/docs/houdini/nodes/sop/curve.html) | Draw/Edit/Auto-Bézier/Orient模式，切线与方向手柄、实时曲线预览 | 路径、轮廓、摆放优先画、拖、选择；参数用于精确修正 |
| [Vellum Brush](https://www.sidefx.com/docs/houdini/nodes/sop/vellumbrush.html) | Enter进入刷子，工具栏选择模式，HUD提示，Reset All Changes明确恢复 | 说明当前动作、模式、退出与恢复；操作发现和撤销也是界面设计 |
| [File Cache 2.0](https://www.sidefx.com/docs/houdini/nodes/sop/filecache.html) | 读取与写盘分离，构造/显式路径、背景执行与取消、缓存版本 | 把连续调节与副作用动作分开；显示写入目标和真实进度，更新不默默覆盖原内容 |
| [Python Panel](https://www.sidefx.com/docs/houdini/ref/panes/pythonpanel.html)、[hou.qt](https://www.sidefx.com/docs/houdini/hom/hou/qt/index.html) | 原生Pane嵌入Qt；提供节点/文件选择、搜索、颜色、TreeView、ParmDialog与主题资源 | 跨资产与批量工作流用Panel；复用原生选择器，参数编辑仍使用真实节点参数 |

## 组件与入口选择

原生参数适合稳定可动画的数值、模式与重复条目；NodeReference与FileReference负责明确资源选择。值来源可用mode组件，范围用原始同排spec与Ramp，命名重复项用repeater，不固定每个工具的页签和字段。

Viewer State适合连续空间操作。先界定Enter进入、鼠标/键盘/handles行为、提示、undo与退出；不要把所有视口事件写进Shelf脚本。名称必须唯一并匹配工具命名空间。[官方Viewer State机制](https://www.sidefx.com/docs/houdini/hom/python_states.html)提供handles、guide、选择和事件生命周期；[HUD](https://www.sidefx.com/docs/houdini/hom/hud_info.html)仍为实验接口，且不同viewer能力有边界，不作为全部工具必需依赖。

Python Panel适合资源或节点浏览、批量操作和长期工作台。使用原生选择器与可筛选列表，选择详情和主要动作形成短闭环；复杂业务模块与.pypanel薄入口分开。每次取当前pane/node，不永久保存已删除对象，按窗口与HIP生命周期释放监听。可继续修改的Panel/Viewer State/Shelf源码范式与资源构建方法在[工具入口](../../houdini-tool-development/references/shelf-and-hotkeys.md)维护。

## 当前画廊范围

[画廊](../assets/ui-component-gallery.json)包含整体/细节、重复属性/输出，以及中文艺术家控制三个机制示例。第三例覆盖NodeReference、值来源切换、范围/Ramp与命名multiparm；没有业务算法、动态Attribute菜单或Group视口拾取，不声明它们可用。画廊JSON是唯一布局源，生成的HDA与HIP是测试产物，不能手改后当作维护源。

官方文档确定原生机制；设计建议、例子和目标版本测试各自说明范围。中文窄面板还需目视核对，旧接口的值、动画与引用迁移独立验收，不能因采用了原生控件而省略。
