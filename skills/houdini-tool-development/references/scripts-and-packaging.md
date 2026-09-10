# 脚本规范、生命周期与存放

适用：HDA/Python 工具源码组织、事件脚本和可交付工具包。普通一次性参数修改不需要建包。

## 决定代码归属

| 生命周期/用途 | 适合的位置 | 边界 |
|---|---|---|
| 跟随资产类型分发的逻辑 | HDA PythonModule；必要时其他内嵌 sections | 显式传入实例上下文，不把类型模块当每实例私有状态 |
| 多工具共享的 Python 包 | package 根下目标版本的 pythonX.Ylibs/包目录，或项目已有 PYTHONPATH 布局 | Python ABI、导入名冲突和加载来源需验证 |
| Shelf 或参数按钮 | 薄入口转发到模块 | 保留 kwargs/context；避免复制大段业务代码 |
| HIP 专用原型 | hou.session | 随 HIP 的逻辑，不作为可移机工具的隐式依赖 |
| HDA 创建/加载/升级事件 | 对应资产事件 section | 只处理该事件职责，不混入每次 cook 应有的数据计算 |
| 启动早期 / 资产就绪 / GUI 就绪 | pythonrc.py / ready.py / uiready.py | 按所需资源选时机；UI 就绪脚本不承担 headless 必需初始化 |
| 新场景或场景加载钩子 | scripts 下对应产品的启动/场景脚本 | 先核对触发频率，不把普通手动工具塞进全局钩子 |

以上机制见 SideFX [Python script locations](https://www.sidefx.com/docs/houdini/hom/locations.html) 和 [HDAModule](https://www.sidefx.com/docs/houdini/hom/hou/HDAModule.html)。选事件前核对目标版本；特别区分 Houdini FX/Core 的启动脚本，456.py 也可能在新场景后运行。

## 本项目建议的脚本规范

- 函数显式接收 node/parm/context 或必要 kwargs；模块导入不自动修改场景、开窗口或写文件。纯数据转换与 HOM/通知层分离，便于独立验证。
- 入口先校验选择、网络类别、目标可编辑性和输入，再做副作用；用户取消是正常结束。异常保留操作和目标信息，不吞错后显示成功。
- 回调明确语言为 Python；不要假设 shelf、菜单、事件拥有同样的 kwargs。参数菜单生成保持只读和低成本，避免打开 UI 时反复 cook、扫描全盘或联网。
- GUI 回调不阻塞 socket/进程探测；涉及后台工作时只把非 HOM 部分移出主线程，结果回到受控主线程入口应用。开发 reload 要区分模块缓存与旧回调引用，发布逻辑不默认每次 importlib.reload。
- 源码与内嵌 section 只选一个权威维护源；由源码生成 HDA 时记录同步命令及产物。不要让手改 section 在下一次构建时被无声覆盖。
- 声称可再生成时，入口须包含接口、内部网络、绑定、端口和定义保存步骤；仅保留VEX/layout常量不能称完整builder。用全新环境执行该入口验证，不依赖会话全局变量或历史exec片段。

## 工具包布局与依赖

按需使用 package 根下的 `otls/`、`toolbar/`、`pythonX.Ylibs/`、`python_panels/`、`viewer_states/`；不预建无用途目录。package JSON 用于把资源根加入 Houdini 搜索路径；先检查已有加载链，避免以相同导入名或工具标识遮蔽其他包。机制见 SideFX [Houdini packages](https://www.sidefx.com/docs/houdini/ref/plugins.html)。

资产内资源可使用内嵌 section/opdef 引用；外部资源使用已声明的可解析路径，不绑定开发机绝对目录。单 HDA、自带模块的 package、依赖共享工作室库都是有效交付方式，由用户用途决定；“单文件”承诺必须验证子 HDA、Python 包及外部资源都已覆盖。

更新前列出目标文件和恢复方式；在隔离偏好目录/测试进程验证导入实际路径、重复加载、新实例和缺依赖失败。源码 build、文件复制、runtime 已加载是不同事实。维护 DSH 安装器遵循仓库 setup 合同，不用新工具包模板替换现役安装布局。

交付或恢复仍不确定时保留备份。清场前列明确切文件及其来源，经用户确认后再删除；模板回读、文件存在和场景undo都不证明备份已无用途。
