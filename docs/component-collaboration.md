# 节点片段交换

本页维护普通SOP节点片段的文件交换与替换，入口是[component_contracts](../houdini/python3.11libs/dsh_component_contracts.py)。它可以复用模块、备份局部网络和显式替换；Houdini只有一种模式，插件不注册另一套子Agent调度。

## 片段表示

普通Subnet或一组明确节点都可以作为片段。导出保存实际节点、参数、接线与公开控制；模型选择表示并说明输入、输出、空间与外部依赖。

`component_export`产生档案、文件摘要与修订；`component_import`导入明确选取的档案。摘要绑定实际读取内容，检查只证明档案和所声明接口。

## 显式替换

`component_replace`先观察当前对象与消费者，生成计划，再应用到指定范围。已支持的参数、表达式、keys和连接迁移由回读说明；无法迁移的依赖明确返回。

节点归属、实际目标、端口与外部文件边界由执行层处理。替换后模型观察受影响输出与实际效果。

## 入口与验证

参数见[动词目录](tool-design.md)，方法见[模块资料](../skills/houdini-sop-workflow/references/module-design-collaboration.md)。

[交换回归](../tools/tests/dsh-component-exchange.test.py)、[公开帮助](../tools/tests/dsh-component-public-help.test.py)用隔离Houdini验证档案往返。独立评测进程由[isolated-worker.py](../tools/isolated-worker.py)管理；它是开发工具，不是用户模式。
