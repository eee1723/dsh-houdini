---
name: houdini-tool-development
description: 开发、维护和交付Houdini HDA/OTL、Python回调、Shelf/Tab工具、快捷键及Python Panel/Viewer State入口，管理脚本与打包依赖。用于资产封装和工具交付；纯控制面板/总控布局走houdini-parameter-ui，普通设参/建模/使用现成工具不触发。
---

# Houdini Tool Development

交付可安装、可找到、可操作且行为可验证的工具。内部几何、rig或Solaris结果按对应领域skill验收；共享控制定义、UI与绑定按名加载houdini-parameter-ui。本skill负责资产封装、脚本生命周期与分发。

## 选择入口

| 用户意图 | 首先读取 | 最小路径 |
|---|---|---|
| 新建 HDA、整理参数布局或改善控件 | [HDA UI](references/hda-ui.md) | 确定类型/实例范围 → 一个控件驱动实际输出 → 扩展界面 |
| 借鉴布局、组合UI组件、检查条件引用 | [UI组件](references/ui-components.md) | 选择必要组件 → dry_run展开/诊断 → 原生状态与面板验证 |
| 修复 PythonModule、按钮、动态菜单或 HDA 依赖 | [HDA 维护](references/hda-maintenance.md) | 定位定义和真实回调 → 最小修正 → 原入口复验 |
| 组织 Python 源码、事件脚本、可移机工具包 | [脚本与存放](references/scripts-and-packaging.md) | 确定源码权威位置与生命周期 → 薄入口 → 干净环境加载 |
| Shelf、Tab、快捷键、面板或视口交互工具 | [工具入口与快捷键](references/shelf-and-hotkeys.md) | 一个动作函数 → 一个原生入口 → context/取消验收 |

只改一个 label 或回调时只读取相关文件并做同层验证；不自动要求整套打包、复杂建模或艺术渲染。
需要跨 UI/脚本/安装交付时，先用现有计划简记：使用者操作、目标类型/文件、调用上下文、预期输出和验收方法。

## 执行脊柱

1. 明确目标 Houdini/Python/Qt 版本、GUI 或 headless、Houdini 或 Engine；确认交付是单 HDA 还是带外部模块的 package。已有约定优先，不凭经验固定目录、快捷键或 Qt import。
2. 只读定位受影响的类型定义、参数、脚本、工具标识及加载路径。普通改动不遍历全盘 HDA。未知接口先查 verb_help/公开参数/目标版本帮助，再做一个隔离最小探针。
3. 用最小闭环验证“输入与目标身份 → 动作/求值 → 公开输出”。按需组合参数界面、PythonModule、Shelf、Panel 或 Viewer State；不要为一个普通参数按钮引入整套自定义 UI。
4. 分块修改并回读。HDA 写入按维护 reference 的文件恢复合同；源码、构建产物、已加载模块分别核对。同一边界连续两次失败就回到已通过 checkpoint，定位加载、context、业务或呈现层，停止猜 API。
5. 从最终公开入口运行相关用例。最后一次改动使受影响的回调/UI/输出/安装证据失效，仅重跑对应完成门。只测内部函数时不得宣布入口可用。
6. 交付实际文件、安装位置、依赖、已测版本与未测范围。需要保持 selection/frame/参数等状态时核对恢复；HDA、用户偏好和磁盘写入不由场景 undo 保证。

## 执行边界

agent 驱动 HOM 仍走 Bridge 主线程队列和现有动词，遵循仓库 docs/execution-contract.md。Shelf/回调代码是交付给 Houdini 的运行入口，不能拿它绕过 Raw Gate、所有权或用户授权；缺少受控入口时记录能力缺口。源码编辑本身不证明 live 加载，重启和 HIP 保存沿用仓库 docs/setup.md。

本库 `houdini/python3.11libs` 经启动器 PYTHONPATH 兼容加载，不是所有 Houdini 版本的标准目录模板。开发新用户工具采用目标解释器的目录约定；维护 DSH 自身时保留现有布局。

## 完成门与当前证据

| 承诺 | 最少证据 |
|---|---|
| 参数 UI 可用 | 实际参数模板/值与引用回读；GUI 核对布局、禁用/隐藏和交互 |
| 动作可用 | 真实按钮/Shelf/快捷键入口、目标正确、结果正确、取消与无效输入无意外修改 |
| 可安装、可移机 | 在声明版本的隔离环境仅加载交付包及声明依赖，创建新实例并执行公开入口 |
| 可维护 | 源码唯一维护源、生成/同步入口清楚、重复加载和更新恢复可解释 |

来源和候选验证见 [证据与验收](references/evidence-and-validation.md)。当前整体为 candidate：界面增量、真实回调和隔离依赖已有H21/H22机制回归，GUI语义、Shelf/快捷键及新session自然触发仍待验收；设计建议不冒充SideFX强制规范。未成功语义检查界面时明确“视觉未验证”。
