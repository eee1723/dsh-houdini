# 设计与维护文档

本目录只保存当前实现的设计规范、执行契约和长期维护说明。不记录迭代日记、任务小目标、
单次尝试、测试流水、模型成绩或退役原型。源码说明不等于已部署；运行态以实际诊断为准。

## 导航与唯一维护位置

| 文档 | 职责 / 对应实现 |
|---|---|
| [系统架构](architecture.md) | Host、Bridge、启动器、UI、视觉和所有生产模块的代码索引 |
| [Houdini Trace设计](houdini-trace-design.md) | 五看板信息架构、详情规范、提示词/工具/技能来源、版本同步与计数契约；明确生产接入边界 |
| [工具设计与词表](tool-design.md) | 58动词目录唯一源、版本握手、设计准入；生成Host/浏览器目录 |
| [执行与证据契约](execution-contract.md) | ownership、Raw Gate、事务、模块构建、几何/控制/渲染边界 |
| [节点操作卡](node-operation-cards.md) | JSON同源生成的全部节点卡、schema与维护约定 |
| [安装与更新](setup.md) | 机器态、工作区、配置、启动、重载和卸载 |
| [DSH兼容设计](dsh-update-compatibility.md) | 精确版本清单、鉴权/RPC/Qt/profile资格门 |
| [资产复核设计](independent-asset-review.md) | 按需评审、短期权限、测试与恢复，不是多作者入口 |
| [Rig与动画设计](rig-animation-design.md) | 领域路由、driver→evaluation→deliverable和动画完成门 |
| [评测基础设施设计](benchmark-design.md) | manifest/schema、信息隔离、评审与能力主张，不保存批次结果 |
| [开发维护规范](development.md) | 代码/文档同步、生成门禁、测试入口、发布及文档生命周期 |

领域操作方法的唯一维护源仍在[随包skills](../skills/)；本目录提供设计和实现入口，不复制另一份recipe。

## 文档准入

新增文档必须回答一个长期维护问题，并列出对应源码/配置、适用范围和验证入口。
优先修改上表现有文档；确需新增时同步索引。实现变更就地替换现行说明，不追加“vN本轮修复”章节。
稳定测试方法与保证边界应保留；某次运行的通过数量、耗时、截图、session ID和实验叙事不进入docs。
过程输出留在会话/CI或不打包的临时产物中，历史由Git保留；不建立docs归档库继续堆积。
