# 模块文件与复用

Houdini只有一种模式。普通建模由当前作者完成，复杂网络可以分模块观察和修改。模块先定义实际输入、输出、控制与空间，选用普通节点或Subnet；复用不自动要求HDA。

## 文件片段

需要备份、复用或显式替换时使用`component_export`、`component_import`和`component_replace`。用`verb_help`读取准确参数；导出记录路径、hash、revision与外部依赖，导入消费同一档案事实。

共享尺寸、坐标系、接口和控制有一份来源；接线使用实际端口。替换既有网络时观察消费者及参数引用，消费计划和应用回读。

## 集成观察

先验实际输出和计算状态，再按用户目标检查部件、连接、控制和图像。跨OBJ片段需说明local/world变换；文件成功导入不能替代这些观察。

工具提供文件、节点和接口事实；程序化构造及工作顺序由作者选择。

边界见[节点片段交换](../../../docs/component-collaboration.md)，构造见[模块合同](module-quality-contracts.md)。
