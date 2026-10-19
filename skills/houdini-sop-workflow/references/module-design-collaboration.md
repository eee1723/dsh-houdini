# 模块文件与复用

Houdini只有一种模式，同一live现场由当前作者修改。任务拆分使用[任务拆分skill](../../houdini-task-decomposition/SKILL.md)，源组件与容器选择见[建模方法](modeling-methods.md#完整源组件与布局)。本页维护模块文件交换与独立结果的接入；复用不自动要求导出文件或HDA。

## 独立作者与计算

DSH团队成员可以独立准备模块代码与文件，并用[独立执行skill](../../houdini-isolated-execution/SKILL.md)在一次性hython中构建、自验证。调用`houdini_isolated`消费明确builder或已保存HIP副本；它不建立常驻子作者工程、不绑定子agent到live、不自动导入结果。子作者报告本次输入版本、实际输出和证据，现场作者选择并接入产物。

独立计算适合输入已具备、接口可说明的模块；共享曲面、跨模块Boolean或强耦合求解可以保持同一构造边界。单位、轴向、local/world变换、输入输出及公共控制由明确来源维护，不能靠两份近似公式或同名路径推定一致。

## 文件片段

需要备份、复用或显式替换时使用`component_export`、`component_import`和`component_replace`。用`verb_help`读取准确参数；导出记录路径、hash、revision与外部依赖，导入消费同一档案事实。

共享尺寸、坐标系、接口和控制有一份来源；接线使用实际端口。替换既有网络时观察消费者及参数引用，消费计划和应用回读。

## 集成观察

先验实际输出和计算状态，再按用户目标检查部件、连接、控制和图像。跨OBJ片段需说明local/world变换；文件成功导入不能替代这些观察。

工具提供文件、节点和接口事实；程序化构造及工作顺序由作者选择。

边界见[节点片段交换](../../../docs/component-collaboration.md)，构造见[模块合同](module-quality-contracts.md)。
