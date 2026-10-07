---
name: houdini-tool-development
description: 开发、维护和交付Houdini HDA、Shelf/Tab、Python Panel与Viewer State工具，发现已有工具和原生Package，明确源码及注册位置。用于制作可复用工具或维护既有工具；普通可调模型、独立保存HIP不触发，纯控制面板布局走houdini-parameter-ui。
---

# Houdini Tool Development

交付艺术家能找到、理解并持续使用的工具。普通模型的“可调、网络清楚、独立保存”默认普通网络与HIP，不自动封装。内部几何、rig或Solaris结果按对应领域skill验收；共享控制定义、中文UI与绑定按名加载houdini-parameter-ui。本skill负责工具意图、开发归属、原生入口、资产与脚本生命周期，以及JSON加唯一资源目录的Package交付。

Houdini原生Tab、Shelf、菜单与工具入口label使用ASCII英文；中文放在参数界面、help、Qt窗口和网页说明。节点类别、内部name和menu token保持兼容，不能把中文参数要求扩成原生菜单标签中文。新示例与旧工具并存时，联用houdini-network-handoff主动交付新容器、工具实例与必要输入，网络分框和Note由该skill统一维护。

## 对齐要做的工具

分清两项选择：工具是新建、基于已有工具独立制作（fork）还是原位维护；资源是加入已有包还是新建包。新工具也可以归入已有包。用户已指定对象、包和路径时直接沿用；只确认缺失且会改变结果或受影响内容的选择。官方或第三方工具默认作为只读参考或独立衍生来源；用户明确维护原工具时按指定范围处理，不强迫fork。

描述含糊时先只读发现当前加载的相关工具，给用户两三种具体操作方案，说明适合场景和影响；确认会改变结果的使用动作、输入/输出、修改范围与交付宿主。能从现场确认的Houdini/Python/Qt版本、现有选择和定义来源直接读取，不让用户填写技术表格。不确定的业务规则可以先做可回退的小原型，不能把对话答卷设为执行准入条件。

用package_catalog有界查看磁盘配置与当前进程加载记录，再用tool_catalog检索相关node_type/shelf/panel/viewer_state/radial；仅对候选调用package_inspect/tool_inspect核对配置、实际来源和定义。不给模型一次性灌入所有源码，也不重复盘点已明确的目标。目录可列出官方与自定义工具，不代表代码可读或允许修改；include_code仅在排查相关入口时开启。先verb_help获取当前签名，不按名称猜API。HDA独立衍生优先用hda_fork；原库维护沿用[HDA维护](references/hda-maintenance.md)。

发现相关自用包时给出“加入此包”或“新建独立包”的建议与影响，并确认唯一源码目录、Package JSON注册位置。已有搜索路径覆盖新资源时通常只添加工具文件，不改JSON。具体发现、路径和运行态动作只在[脚本与存放](references/scripts-and-packaging.md)维护。

## 选择入口

| 用户意图 | 首先读取 | 最小路径 |
|---|---|---|
| 新建 HDA、整理参数布局或改善控件 | [HDA UI](references/hda-ui.md) | 确定类型/实例范围 → 一个控件驱动实际输出 → 扩展界面 |
| 借鉴布局、组合UI组件、检查条件引用 | [UI组件](references/ui-components.md) | 选择必要组件 → dry_run展开/诊断 → 原生状态与面板验证 |
| 修复 PythonModule、按钮、动态菜单或 HDA 依赖 | [HDA 维护](references/hda-maintenance.md) | 定位定义和真实回调 → 最小修正 → 原入口复验 |
| 已有包扩展、新包注册、Python源码与依赖 | [脚本与存放](references/scripts-and-packaging.md) | 发现相关来源 → 明确归属与两个路径 → 直接开发 → 干净环境加载 |
| Shelf、Tab、快捷键、面板或视口交互工具 | [工具入口与快捷键](references/shelf-and-hotkeys.md) | 一个动作函数 → 一个原生入口 → context/取消验收 |
| 观察已有pane、Python Panel或Qt窗口的实际呈现 | [界面观察](references/evidence-and-validation.md#观察实际工作界面) | 发现可见目标 → 明确目标捕获 → 针对使用问题读图与行为对照 |

只改一个 label 或回调时只读取相关文件并做同层验证；不自动要求整套打包、复杂建模或艺术渲染。
需要跨 UI/脚本/安装交付时，先用现有计划简记：使用者操作、目标类型/文件、调用上下文、预期输出和验收方法。

## 执行脊柱

1. 从现场读取目标Houdini/Python/Qt版本及宿主；可复用工具默认使用原生Package JSON加用户选定的唯一源码/资源目录，不生成ZIP或安装副本。依用户用途加入已有包或建立新包，用独立标识组织必要资源。注册、当前进程加载和重启各自遵循已有授权；不把一个动作的成功等同于其余动作完成。
2. 只读定位受影响的类型定义、参数、脚本、工具标识及加载路径。普通改动不遍历全盘 HDA。未知接口先查 verb_help/公开参数/目标版本帮助，再做一个隔离最小探针。
3. 按艺术家动作选原生入口：持续数值/模式用参数面板，空间编辑用Viewer State与handles，一次动作用Shelf/Tab/径向菜单，跨资产或批量工作流用Python Panel。高级组件须降低操作成本；原生参数不够才引入自定义窗口。新建HDA先按[HDA维护](references/hda-maintenance.md)验证公开控制→新实例→公共输出消费者，再扩展内部模块。
4. 分块修改并回读。HDA写入按维护reference的文件恢复合同；源码、构建产物、已加载模块分别核对。重复失败且没有新信息时回到已通过checkpoint，隔离原生机制、载体、绑定和业务层；先证明写入/保存确实发生，再判断状态丢失，不能以换实现代替根因证明。
5. 从最终公开入口运行相关用例。最后一次改动使受影响的回调/UI/输出/安装证据失效，仅重跑对应完成门。只测内部函数时不得宣布入口可用。
6. 交付实际JSON、唯一源码/资源目录或HDA及其原生入口，说明使用、持久配置与当前会话加载状态、依赖和已测/未测范围。临时验证材料放在最终源码之外，完成时按[脚本与存放](references/scripts-and-packaging.md#交付与验证)清理本次明确无用的文件，保留运行依赖、实际交付和用户文档。组件例子不能冒充完整业务工具；需要保持selection/frame/参数等状态时核对恢复。HDA、用户偏好和磁盘写入不由场景undo保证。

## 执行边界

agent 驱动 HOM 仍走 Bridge 主线程队列和现有动词，遵循仓库 docs/execution-contract.md。Shelf/回调代码是交付给 Houdini 的运行入口，不能拿它绕过 Raw Gate、所有权或用户授权；缺少受控入口时记录能力缺口。源码编辑本身不证明 live 加载，重启和 HIP 保存沿用仓库 docs/setup.md。
普通用户工具不写$HFS、不向Houdini自带Python安装依赖、不默认修改全局启动脚本/环境变量或无关用户偏好。HDA二进制由Houdini管理；内部节点/UI/section通过对应动词维护，不通过解压字符串替换重写资产库。

本库 `houdini/python3.11libs` 经启动器 PYTHONPATH 兼容加载，不是所有 Houdini 版本的标准目录模板。开发新用户工具采用目标解释器的目录约定；维护 DSH 自身时保留现有布局。

## 完成门与当前证据

| 承诺 | 最少证据 |
|---|---|
| 参数或Qt界面可用 | 实际数据/值与引用回读；目标GUI核对布局、当前状态和真实交互 |
| 动作可用 | 真实按钮/Shelf/快捷键入口、目标正确、结果正确、取消与无效输入无意外修改 |
| 可启动加载、可分享 | 在声明版本的隔离环境经交付JSON加载资源及声明依赖，创建新实例并执行公开入口；跨机器时验证路径配置 |
| 可维护 | 源码唯一维护源、生成/同步入口清楚、重复加载和更新恢复可解释 |

来源和候选验证见[证据与验收](references/evidence-and-validation.md)。当前整体为candidate：界面增量、回调和依赖已有H21/H22机制回归；特定中文参数画廊、Panel/Shelf/Viewer State资源与入口也有隔离GUI证据。未见自然任务、物理选择器/视口交互与快捷键仍需验收；设计建议不冒充SideFX强制规范。未成功语义检查界面时明确“视觉未验证”。
