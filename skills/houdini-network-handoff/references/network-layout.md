# 网络说明与布局

适用所有Houdini节点网络。先依据用户接手动作分清输入、编辑入口、处理职责与输出，再选框与说明；不因整理而改变接线、表达式、节点类型或Subnet结构。

## 分组与阅读

Network Box是同一parent中的编辑器分组，不提供端口或写权限。一个节点只有一个直接所属框；框可嵌套。组件与技术阶段都需要时，组件大框内可放工序叶子框，但层数由可读性决定，不逐节点套框。

主输入链通常上下对齐，侧输入靠近使用它的节点，独立管线分列；控制入口和可替换源应容易找到。控制上方、输出下方只是适合部分SOP网络的排布选择，不要求所有领域使用。已有布局优先。

`network_boxes(parent, groups)`按明确成员局部创建/更新框，`name`稳定，`label`说明用途，`role`只是可选颜色提示。常见role包括controls/source/component/placement/assembly/output，未知role可用中性色。少量低饱和颜色配合标题辨认，不用随机色替代真实成员关系。

```python
network_boxes('/obj/example', [
    {'name': 'inputs', 'label': '可替换输入', 'role': 'source',
     'members': ['PATH', 'SOURCE']},
    {'name': 'tool', 'label': '工具与输出', 'members': ['ARRAY', 'OUT']}
])
layout_nodes('/obj/example', mode='handoff', boxes=['inputs', 'tool'], profile='readable')
```

已成框后，不对整网再调用children/flow布局打散成员。handoff处理明确叶子框，component处理支持的一层组件容器；局部改动可只指定nodes。预览按需要使用，不是强制准入。查看layout_status、重叠、containment/clearance失败与实际净距，不仅检查调用ok。

## Sticky Note

用`network_notes(parent)`只读现有说明；用明确name/text局部维护。新说明默认放到现有内容旁，可指定网络坐标position、size与颜色。先整理框，再加相邻说明。当前动词只支持独立Note，已在Box中的Note写前拒绝，因为现有Box恢复合同不覆盖Note成员；这不是Houdini原生能力限制。后续框布局将相邻Note作为固定障碍。

```python
network_notes('/obj/example', [
    {'name': 'start_here', 'text': '从 ARRAY 调数量或间距。\nPATH 可替换曲线，SOURCE 可替换源几何。'}
])
```

文字保持短且面向操作。多行说明不要覆盖节点或连线；一眼能读懂的框标题不再重复写长Note。更新时读取已有内容，不覆盖无关笔记，也不写会随测试变动的完成状态。

框与Note都有独立session归属，名称、所在parent、颜色和成员不构成授权；foreign仅在用户明确指定范围时单次豁免，渲染服务永不豁免。布局的未选节点、用户框/Note/Network Dot是固定障碍；blocked时缩小本次范围，不删除障碍。

## 布局观察

检查用户当前看到的网络时，按[通用界面观察](../../houdini-tool-development/references/evidence-and-validation.md#观察实际工作界面)发现已有Network Editor，核对其当前parent后用返回target捕获；保留当前缩放、位置和选择。截图不创建或导航独立网络编辑器，也不接受网络的node/view尺寸入口。需要查看另一网络或改变取景时，把它作为明确的编辑器交互单独处理，再发现并捕获实际表面；已有交付入口可用focus_node定位，未看到的范围保持未验证。

读图看标题/注释是否被裁切、节点与线是否容易跟随，以及输入/控制/输出能否找到。全网过大时再观察相关小网络，不把缩小到看不清的全景当验收；只看到局部时保留范围说明，不擅自重排用户网络以满足截图。

捕获不能代替真实数据流、参数绑定和业务输出检查。改变本次节点/框/Note后，只刷新受影响的观察；捕获与语义读图状态沿用通用方法。对无可见影响的小维护，不追加无意义的截图流程。
