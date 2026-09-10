# 设计与维护文档

本目录保存当前实现的设计规范、执行契约和长期维护说明；[当前交接](handoff.md)是唯一滚动待办例外。
不记录迭代日记、单次尝试、测试流水、模型成绩或退役原型。源码说明不等于已部署；运行态以实际诊断为准。

## 导航与唯一维护位置

| 文档 | 职责 / 对应实现 |
|---|---|
| [当前交接](handoff.md) | 未完成动作的优先级、依赖、验证缺口与移除条件；完成即删，不积累历史 |
| [系统架构](architecture.md) | Host、Bridge、启动器、UI、视觉和所有生产模块的代码索引 |
| [主要开发方向](development-directions.md) | 四项产品方向、共用可靠性能力、目标交付与验收原则；不复制活动待办，不包含自动知识沉淀 |
| [Houdini Trace设计](houdini-trace-design.md) | 五看板信息架构、详情规范、提示词/工具/技能来源、版本同步与计数契约；明确生产接入边界 |
| [工具设计与词表](tool-design.md) | 动词目录唯一源、版本握手、设计准入；生成Host/浏览器目录 |
| [执行与证据契约](execution-contract.md) | ownership、Raw Gate、事务、模块构建、几何/控制/渲染边界 |
| [节点操作卡](node-operation-cards.md) | JSON同源生成的全部节点卡、schema与维护约定 |
| [安装与更新](setup.md) | 当前源码安装与正式受管安装合同、机器态、工作区、启动、重载和卸载 |
| [DSH兼容设计](dsh-update-compatibility.md) | 正式发行组合/发布门、精确版本清单、鉴权/RPC/Qt/profile资格门 |
| [Rig与动画设计](rig-animation-design.md) | 领域路由、driver→evaluation→deliverable和动画完成门 |
| [评测基础设施设计](benchmark-design.md) | manifest/schema、信息隔离、评审与能力主张，不保存批次结果 |
| [开发维护规范](development.md) | 代码/文档同步、生成门禁、测试入口、发布及文档生命周期 |
| [控制参数、界面与绑定设计](parameter-controls.md) | 跨建模/场景总控/HDA的分层职责、多种推进顺序与实施完成门 |

领域操作方法的唯一维护源仍在[随包skills](../skills/)；本目录提供设计和实现入口，不复制另一份recipe。

[COP workflow](../skills/houdini-cop-workflow/SKILL.md)维护 Copernicus 图层、关系验证与纹理交付，
由教程复现按当前阶段加载，不用于只解析视频或仅消费贴图；来源/版本与验证入口见其
[验收矩阵](../skills/houdini-cop-workflow/references/evidence-and-validation.md)，注册由 `src/skill.ts` 维护。

HDA封装、PythonModule/回调、脚本打包、Shelf/Tab、快捷键及Panel/Viewer State由
[Houdini 工具开发 skill](../skills/houdini-tool-development/SKILL.md)维护；共享控制定义、参数UI组件与绑定由
[参数界面skill](../skills/houdini-parameter-ui/SKILL.md)维护，适用于普通控制节点和HDA。注册入口为
[src/skill.ts](../src/skill.ts)，来源、版本范围与验证入口见其
[证据与验收](../skills/houdini-tool-development/references/evidence-and-validation.md)。

## 文档准入

新增文档必须回答一个长期维护问题，并列出对应源码/配置、适用范围和验证入口。
优先修改上表现有文档；确需新增时同步索引。实现变更就地替换现行说明，不追加“vN本轮修复”章节。
稳定测试方法与保证边界应保留；某次运行的通过数量、耗时、截图、session ID和实验叙事不进入docs。
过程输出留在会话/CI或不打包的临时产物中，历史由Git保留；不建立docs归档库继续堆积。
交接只在handoff.md原位更新，体量与清理规则见[开发维护](development.md#交接文档生命周期)；
不把它扩成所有产品方向的任务清单，也不把本机tools/out当跨电脑交接的唯一依据。
