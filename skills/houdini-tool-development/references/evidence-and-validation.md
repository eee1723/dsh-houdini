# 来源、版本与候选验收

## Provenance 与决策

本 skill 由用户要求统一 HDA UI、脚本、工具架与快捷键开发指导而创建；维护范围为 dsh-houdini 源码。SideFX 公开帮助仅提炼必要机制并链接，不复制手册/示例或用户资产代码。官网原页核对时间：2026-09-10；所查在线文档标识 Houdini 22.0，兼容目标 H21/H22，未获得对应本机行为复现。

决策为 CREATE + 路由整理：原 SOP 侧专注几何交付，工具开发拥有 UI/context/脚本加载/分发这些独立完成门。既有 HDA 维护合同转入本 skill，旧 reference 保留跳转以维持调用兼容；不是删除领域能力。现有执行/所有权约束继续以仓库合同为准。

| Claim / 决策影响 | 来源 | 适用与反例 | 最小复核 |
|---|---|---|---|
| 定义界面不同于实例 spare parms；选择修改层级 | [Type Properties](https://www.sidefx.com/docs/houdini/ref/windows/optype.html) | HDA 公共 UI；单节点临时控制不必改类型 | 两个实例中确认定义改动范围，保留旧值/引用 |
| PythonModule 与事件/磁盘模块生命周期不同；避免隐式实例状态 | [HDAModule](https://www.sidefx.com/docs/houdini/hom/hou/HDAModule.html)、[locations](https://www.sidefx.com/docs/houdini/hom/locations.html) | 可复用工具；HIP 私有原型可用 session | 新实例真实回调、不同实例不串状态、GUI/headless 分别加载 |
| Shelf 通用拖放可能丢失自定义创建交互 | [Tool scripts](https://www.sidefx.com/docs/houdini/hom/tool_script.html)、[Shelf](https://www.sidefx.com/docs/houdini/shelf/customize.html) | 资产自定义工具；普通节点通用创建无需改写 | 比较实际公开创建入口，取消无半成品 |
| 动作定义不同于个人绑定；H20.5+ 用新配置体系 | [Hotkeys](https://www.sidefx.com/docs/houdini/basics/hotkeys.html) | H21/H22；不发布旧 keymap 片段或通用固定键位 | 动作可发现、真实按键、冲突与持久化 |
| package 组织资源搜索路径；外部模块是有效分发选项 | [Packages](https://www.sidefx.com/docs/houdini/ref/plugins.html) | 多文件工具；单 HDA 不需强加外部包 | 干净环境确认实际加载路径及缺依赖失败 |
| Panel 是独立 UI 入口，不据在线旧提示断言 Qt 兼容 | [Panel Editor](https://www.sidefx.com/docs/houdini/ref/windows/pythonpaneleditor.html) | 复杂工作台；普通按钮优先原生参数 | 目标版本绑定、重复开关与引用释放 |

官网机制是文档证据，尚未达到“官方资料 + 目标版本本机复现”的 E2 门；工作流整体为 candidate。既有 HDA 维护路径保留 E1 状态。UI 分组、薄入口和代码布局是项目设计建议，不作为所有 Houdini 项目的强制规定。未采纳个人默认键位、固定 Qt import、未经本机验证的脆弱 API 片段或“所有工具都必须单 HDA”。

## 机制验证与行为验收入口

界面增量与交付检查已有H21.0.440/H22.0.368隔离hython回归入口：
tools/tests/dsh-hda-interface-patch.test.py、tools/tests/dsh-hda-delivery.test.py。
覆盖旧通道状态/新默认、过期版本与恢复、真实按钮异常/菜单/重复调用、不同输入、错误结果、
缺Python模块和子HDA偷偷加载原开发路径。对应机制具备双版本实验依据，整体skill仍为candidate；
这些固定夹具不证明新session采用、未见任务质量、GUI布局或Shelf/快捷键交互。

可选布局组件的来源、已知失败面和双版本机制测试在[UI组件](ui-components.md)维护；原生GUI画廊仅验证独立示例的面板，不外推用户原资产效果或任意窄面板。

以下为完整行为矩阵；上述机制回归只覆盖相应子集，其余仍待执行。使用隔离 H21/H22 环境和自建夹具；agent 对live场景的操作走 Bridge。离线纯语法/打包检查不等同于 GUI 或自然任务验收。

| 类别 | 用例与可观察判据 |
|---|---|
| 既有失败模式 | 动态菜单显示选项但默认值为空：新实例从真实入口验证 token/实际值/最终结果；内部 helper 成功不足以通过 |
| 未见同族正例 | 制作不同类型的小工具，含模式控制、按钮与外部共享模块：从公开入口得到指定输出；移出原开发路径仍可运行 |
| 相邻反例 | 只要求创建普通 SOP 网络：选择 SOP skill；不擅自封装 HDA、加 Shelf 或改快捷键 |
| 领域内反例 | 只改已有按钮 label：保留内部 name、回调和依赖；不要求完整渲染或重建工具包 |
| UI/context | 新实例、窄面板、禁用/隐藏、多选择、无选择、取消；真实 Shelf 和快捷键在指定焦点各触发一次 |
| 版本矩阵 | H21/H22 各自确认 Python/Qt、配置格式、模块路径、HDA 定义和公开入口，不从一版成功外推另一版 |
| 失败恢复 | 缺子 HDA、模块缺失、第二个写入失败：不虚报成功；区分场景 undo 和库/偏好文件恢复，重复失败停止猜测 |
| 最终交付 | 最后改动后复验、隔离依赖、产物路径/hash、无未声明 helper；新 session 核对 catalog、隐式触发和 references 可读 |

结构验证：仓库治理 audit、skill-creator quick_validate、npm run docs:check、npm run build、npm pack --dry-run。行为门未通过前不标 verified/released。下一步是真实入口、GUI 与版本矩阵验收，活动交接从 docs/handoff.md 统一跟踪；回滚只恢复本次相关文件及注册行，不覆盖其他在途修改。
