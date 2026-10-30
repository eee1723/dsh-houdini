---
name: houdini-isolated-execution
description: 用houdini_isolated在一次性独立hython中构建或检查明确builder、已保存HIP副本及其依赖，取得实际输出、缓存或渲染证据。用于需要独立计算、可复现试验或团队成员自验证的工作；简单现场编辑和依赖未保存GUI状态的操作仍使用当前Houdini。
---

# Houdini Isolated Execution

`houdini_isolated`是Host工具，不是`verb_help`中的Houdini动词：为本次调用启动独立的Houdini Python进程（hython），执行完成后退出。它消费明确文件，不接管live现场，也不为子agent长期保留执行端。DSH团队负责分工和消息；各作者可在自己的任务中调用该工具，无需插件另建团队或完成账本。

## 何时使用

适用于能从明确输入独立复现的模块构建、方法试验、计算/缓存、已保存工程检查和有界ROP渲染。是否拆出去取决于依赖、计算和反馈成本；同一连续曲面、强耦合求解或当前未保存修改可能更适合留在live逐步完成。

团队成员可以准备输入、执行和检查自己的产物，报告实际发现；主作者负责将选定结果接入当前工程并检查组合后的关系。同一live现场仍由一个作者修改，不共享session身份或用allow_foreign绕过归属。普通任务不要求额外agent、固定团队人数或逐模块开启独立进程。

## 准备可复现输入

调用前明确本次问题、builder或已保存HIP、需要的依赖、实际输出和能回答问题的检查。输入与检查沿当前任务的已有计划表达，不另立验收台账。

- **builder**：用任务中的明确脚本生成所需网络。脚本在worker提供的HOM/动词环境中运行，`__file__`指向本次复制的脚本、`__name__`为`__main__`；声明的输入依赖可从`Path(__file__).parent`按保留的相对结构读取，不依赖进程cwd。使用已注入的动词，先发现不确定签名和节点接口，不猜参数、不吞掉构建或cook失败。
- **HIP副本**：检查指向明确保存版本；未保存live修改不会自动进入副本。需要这部分变化时，由现场作者按原授权保存或明确导出所需输入，再提交独立计算。
- **依赖与目的地**：声明脚本、贴图、HDA/模块和缓存实际需要的文件及相对结构。引用本次返回的实际文件路径；依赖worker临时目录的内容在交付前移入工程的受管位置。

构建与检查可以放在同一入口脚本；需要共用构建逻辑时，使用普通Python模块，由入口传入所需动词或API，并将模块列入依赖。不要用`exec(open(...).read())`或`eval`隐藏另一份构建源码。普通模块仍沿任务授权运行，独立进程和导入机制不是任意Python代码的安全沙箱。

在用户已授权的构建、计算与自验证范围内直接执行，不为换到独立进程再要求一次批准。独立进程不扩大原任务范围，也不自动授权额外服务、昂贵成图或修改原工程。

## 调用入口

`operation="run"`（默认）需要绝对`manifest`路径；省略`output_dir`时，工具在当前DSH工作区的`execution_run`目录中分配唯一运行目录，不查询现场HIP来决定目录。可显式指定新的绝对`output_dir`，已有位置不会被搬动或覆盖。

默认消费当前明确选择的Houdini所登记的安装信息，现场离线仍可运行。也可用`houdini_installation`指定绝对安装根目录（HFS），用于未选现场或旧登记缺少安装信息的情况；不按PATH或Host环境猜版本。无登记的固定Bridge配置仍需在线读取安装信息，离线时使用显式HFS。安装选择不修改现场目标、节点归属或旧请求状态。

`timeout_seconds`默认120，`memory_mb`默认4096；依据本次计算选择，内存上限不约束GPU或外部服务。`background=true`沿DSH原生作业运行，适合超过一轮交互等待的计算。

manifest至少声明`script`或`hip`之一。两者同时存在时，driver先加载声明的HIP副本并登记该次节点身份，再以同一隔离作者执行脚本作为准备操作，最后运行checks；脚本不自行load/clear。`hip/script/files`是输入根下的安全相对路径；输入根默认manifest目录，也可用`input_root`明确指定绝对目录或相对manifest的目录。这样HIP可留在工程根，准备脚本和manifest留在源码目录；不必为路径绕行复制源文件或把控制文件散放工程根。

`files`列出额外输入并保留相对结构。`checks`可省略或为空数组，适合接口发现、独立断言或只需builder返回值的试验；不为这类任务额外制造几何输出。需要检查SOP、缓存或ROP时再列明每项唯一`id`、`kind`（cook/cache/render）、实际`node`与`frame`；cache/render另给相对输出`file`。可选`expect`只支持cook/cache的`points`与`primitives`计数，部件关系和控制行为在builder中用相应动词实测。

例如自验证一个2米宽的可编辑源件，`build.py`使用worker已注入的环境：

```python
geo = tab_create('/obj', 'geo', name='part')
box = tab_create(geo, 'box', name='body', parms={'sizex': 2.0})
out = tab_create(geo, 'null', name='OUT', inputs=[box])
sop_set_output(out)
verify_network(geo, output=out)
width = float(out.geometry().boundingBox().sizevec()[0])
if abs(width - 2.0) > 1e-5:
    raise RuntimeError('Expected 2 m width, got %s' % width)
__result__ = {'output': out.path(), 'width_m': width}
```

相邻`check.json`：

```json
{"script":"build.py","checks":[{"id":"part","kind":"cook","node":"/obj/part/OUT","frame":1}]}
```

调用Host工具：

```json
{"operation":"run","manifest":"D:/project/dsh-artifacts/scripts/part/check.json"}
```

检查已有工程时使用`hip`并列出所需依赖；这是保存版本的副本，不会复制未保存现场。需调整副本的参数、相机或渲染设置时，同时声明准备`script`，沿原动词修改。运行器先复制并校验实际输入字节，不自动回写源HIP。需要工程文件或实际节点快照时，在builder中用相应保存/导出动词明确生成，并消费其返回路径；只声明cook不产生可编辑工程文件。保存仍遵从原任务授权与`scene_save_as`的目标、当前HIP和覆盖合同；已授权保存回本轮源文件无需另绕行scratch副本。独立执行不回滚文件副作用。团队交付可直接提供已检查的builder，由主作者在当前工程执行后产生真实节点。

只需独立查询接口时可以使用`{"script":"inspect_api.py","checks":[]}`，在builder的`__result__`返回需要的事实。builder成功只证明该脚本完成；未执行的几何、控制和视觉检查仍未验证。

## 执行与自验证

根据要证明的性质选择检查：明确SOP输出的cook与非空、指定实体的关系、代表性控制变化、缓存回读或ROP产物。数值断言应能区分正确与错误结果；`verify_network`通过不替代部件关系或美术质量。

worker没有用户视窗；`render_view`与viewport截图要求GUI，不能用于无头检查。需要图像时，在输入工程或builder中建立所需相机、灯光、材质和ROP，由render检查调用`render_frame`产图并查看返回的原生附件。需要直接查看时输出PNG/JPEG；EXR保留为原始产物，另生成合适的本地预览。正式渲染方法按需加载Solaris/Karma工作流；低成本观察只覆盖本次画幅能看清的范围。

后台提交返回`job_id`、`run_directory`和`report_path`，用DSH原生`job_output`等待、`job_kill`取消；提交成功不等于执行结束，执行超时不等于取消。read必须使用原调用返回的`run_directory`作为`output_dir`，读取已有报告/进度并附上可用图片，不连接live、不猜最新run、不重新计算。大执行详情使用builder或check的`details.sha256`调用`houdini_resource(kind="result", ref=..., pointer="/result", offset=0, limit=6000)`，分页读取该次执行的原结果；其他会话消费时先read原run以取得同源引用。`details.path`也可用通用文件工具读取。详情不可用、归档失败与原执行结论分别报告，不因摘要没有展开字段而重跑探针。进度文件可变，不证明进程当前存活。消费原任务的结果，不通过重复提交未知计算探测状态。

需要并行继续迭代时，保持已提交脚本和声明依赖的版本稳定，在下一版文件中修改后续方案。运行器会核对源输入变化；worker完成而源已改并不能证明当前源码通过，也不表示本次几何一定失败。读取原run的输入与执行事实后再决定下一次计算，不为这种版本错位重复重渲染未受影响的内容。

运行器的`released`仅表示已发送GO执行信号；`tree_reaped`才表示该次拥有的进程树已确认退出。独立prefs位于运行器独占临时目录，确认退出后仅清理本次临时环境；不清理工程、输入快照、报告或产物。未确认退出或清理失败时保留临时路径和原因。工具返回的进程退出、执行结果、检查与文件事实分别判断；没有完成回执保留未知。

## 结果范围与接入

报告本次输入版本、运行环境、实际输出路径、执行与检查结果，以及仍未观察的部分。结果属于这次builder/HIP副本和依赖；输入变化后，旧结果不能证明新状态。文件、像素或附件送达不证明语义正确；没有实际看图时明确视觉未验证。

`inputs`和snapshot hash记录开始执行时逐文件复制并校验的版本，不是原子化的整工程快照；未归档或绝对引用依赖不在该保证内。`inputs_unchanged`单独观察运行后的原来源：true表示各声明来源两次观测均可读且同hash，不证明期间从未改变；false表示至少一项确认改变；null表示没有已确认改变但有来源不可读、未完整staging或未能观察。逐文件的`input_observations`保留source_path、before/after hash及changed/unchanged/unavailable与原错误；未完成复制的项没有已核对before hash，不可读不冒充已改变。

源文件在执行期间改变、删除或由获授权的脚本保存，都不覆盖真实的执行成功/失败；后台摘要提示来源差异，完整事实沿同一run的read取得。工作副本可以合法继续修改，初始hash不声称它在运行结束后仍未改变。

独立图片与live数值冲突时，先固定产图报告中的输入快照、检查帧和实际输出，再在同一输入副本上检查最终几何、stage与消费者。live读数可作对照，不能替代已渲染副本的值。常量材质或简化输入能正常出图只缩小故障范围；是否修复，仍看原数据链的实际输入与输出。

独立计算不自动导入、合并或替换live节点。团队默认交付builder、实际入口与依赖、本次输入版本和检查范围；主作者通过`houdini_exec`的`script`入口执行选定文件，具体接入方式见[模块文件与复用](../houdini-sop-workflow/references/module-design-collaboration.md)。实际节点快照与显式迁移另按需要选择，不是保留可编辑网络的前提。主作者核对坐标、单位、实际端口、材质与文件引用，再验证受影响消费者；局部独立通过不外推为总装通过。

工具参数与返回以当前工具schema为准；实现与验证入口见[架构](../../docs/architecture.md)和[开发维护](../../docs/development.md#隔离执行与开发工具)。
