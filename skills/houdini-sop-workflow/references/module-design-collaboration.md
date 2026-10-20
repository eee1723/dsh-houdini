# 模块文件与复用

Houdini只有一种模式，同一live现场由当前作者修改。任务拆分使用[任务拆分skill](../../houdini-task-decomposition/SKILL.md)，源组件与容器选择见[建模方法](modeling-methods.md#完整源组件与布局)。本页维护模块文件交换与独立结果的接入；复用不自动要求导出文件或HDA。

## 独立作者与计算

DSH团队成员可以独立准备模块代码与文件，并用[独立执行skill](../../houdini-isolated-execution/SKILL.md)在一次性hython中构建、自验证。调用`houdini_isolated`消费明确builder或已保存HIP副本；它不建立常驻子作者工程、不绑定子agent到live、不自动导入结果。团队默认交付builder文件、实际调用入口与依赖、本次输入版本和检查范围，现场作者选择后在当前工程执行并接入。

独立计算适合输入已具备、接口可说明的模块；共享曲面、跨模块Boolean或强耦合求解可以保持同一构造边界。单位、轴向、local/world变换、输入输出及公共控制由明确来源维护，不能靠两份近似公式或同名路径推定一致。

## 接入builder

需要创建节点的builder接入已约定的父网络与共享输入，可在其中构建Subnet或同层支路；公开输出供实际消费者使用。跨OBJ、材质或LOP的构建说明其依赖，纯文件或事实脚本沿自身接口交付。容器选择见[逻辑模块](modeling-methods.md#逻辑模块与容器选择)。

使用`houdini_exec`的`script`字段传入绝对`.py`路径，可用`expected_sha256`固定已验证文件的hash；需要调用文件中定义的构建函数时，将调用放在可选`code`尾段，例如在已选模块网络中构建：

```json
{"script":"D:/project/dsh-artifacts/scripts/build_part.py","code":"parent = hou.node('/obj/asset/part')\n__result__ = build_part(parent)"}
```

只有`script`时，文件以`__name__='__main__'`运行；带`code`尾段时为`__name__='__dsh_builder__'`，尾段调用其已定义入口。`__file__`是实际源文件路径。文件源码与尾段进入同一次Bridge执行，共用当前作者、事务与执行边界；不要改用`exec`或`eval`动态执行未进入该入口的构建源码。准确字段及边界见[执行契约](../../../docs/execution-contract.md)。

builder若创建节点，这些是当前工程中的真实节点；独立进程报告的路径不是可直接移植的节点身份。接入可以只新增或修改当前局部，不要求整件重建、重复执行或统一包装成Subnet/HDA；简单现场编辑继续使用内联`code`。保留已有有效网络与用户修改，按实际消费者连接选定输出。

## 实际节点快照与迁移

需要保留实际节点状态、备份自足子网或显式迁移时，按需使用`component_export`、`component_import`和`component_replace`。它们保留在builder之外的用途：已有节点的参数、动画或人工修改不一定能由旧builder重新生成。它们不是默认团队交付方式，也不自动合并内部编辑。用`verb_help`读取准确参数；导出返回实际档案的路径、hash与合同，导入消费同一档案事实，支持范围见[节点片段交换](../../../docs/component-collaboration.md)。

共享尺寸、坐标系、接口和控制有一份来源；接线使用实际端口。替换既有网络时观察消费者及参数引用，消费计划和应用回读。

## 集成观察

先验实际输出和计算状态，再按用户目标检查部件、连接、控制和图像。跨OBJ片段需说明local/world变换；文件成功导入不能替代这些观察。

工具提供文件、节点和接口事实；程序化构造及工作顺序由作者选择。

边界见[节点片段交换](../../../docs/component-collaboration.md)，构造见[模块合同](module-quality-contracts.md)。
