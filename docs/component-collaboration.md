# 节点片段交换

本页维护普通SOP子网的实际节点快照与显式迁移，入口是[component_contracts](../houdini/python3.11libs/dsh_component_contracts.py)。它可以保留当前节点状态、复用自足子网和显式替换，独立于团队协作；团队默认以builder交付并由现场作者执行，见[模块资料](../skills/houdini-sop-workflow/references/module-design-collaboration.md)。Houdini只有一种模式，插件不注册另一套子Agent调度。

## 片段表示

当前支持当前作者拥有的、自足普通SOP subnet。导出保存实际节点、参数、接线与公开控制，因此可保留旧builder未表达的实际编辑；不支持任意节点集合、已连接的根输入、自定义HDA、外部文件及Python/Solver SOP等依赖。准确范围和参数见[动词目录](tool-design.md#component-域普通-sop-组件交换)与运行时`verb_help`。

`component_export`产生原生节点档案、文件摘要与合同；`component_import`将明确选取、hash固定的同构建档案导入为新候选，不覆盖已有网络。原生档案包含可执行内容，可信导入不是沙箱；检查只证明档案和所声明接口。

## 显式替换

`component_replace`先观察当前对象与消费者，生成计划，再应用到指定范围。仅迁移明确支持和声明的参数、表达式、keys与连接，并返回实际回读；旧网络保留，预览后的变化使原计划失效。它不自动合并旧网络内部的人工编辑，无法迁移的依赖明确返回。

节点归属、实际目标、端口与外部文件边界由执行层处理。替换后模型观察受影响输出与实际效果。

## 入口与验证

参数见[动词目录](tool-design.md)，方法见[模块资料](../skills/houdini-sop-workflow/references/module-design-collaboration.md)。

[交换回归](../tools/tests/dsh-component-exchange.test.py)、[公开帮助](../tools/tests/dsh-component-public-help.test.py)用隔离Houdini验证档案往返。独立评测进程由[isolated-worker.py](../tools/isolated-worker.py)管理；它是开发工具，不是用户模式。
