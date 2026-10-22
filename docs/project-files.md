# 工程文件与图像目录

适用于参考资料、分析产物、使用说明、生成图、COP贴图、工程缓存、渲染和视觉检查的默认输出。目录角色由[project-layout.json](../houdini/project-layout.json)唯一维护，Houdini与Host读取同源；下面的目录表由[生成器](../tools/gen-project-layout-docs.mjs)更新。它不是用户资产数据库，不记录完成状态或替代DSH会话。

## 默认目录与用途

<!-- project-layout:generated:start -->
| 用途 | 工程相对目录 | 生命周期标识 |
|---|---|---|
| 下载的参考资料（`reference_downloaded`） | `dsh-artifacts/references/downloaded/` | `reference` |
| 生成的辅助参考（`reference_generated`） | `dsh-artifacts/references/generated/` | `reference` |
| 材质与工程依赖（`texture`） | `dsh-artifacts/textures/` | `project-dependency` |
| 几何、模拟与通道缓存（`cache`） | `dsh-artifacts/cache/` | `project-dependency` |
| 分析资料与诊断报告（`analysis`） | `dsh-artifacts/analysis/` | `analysis-evidence` |
| 供用户阅读的工程与工具说明（`documentation`） | `dsh-artifacts/docs/` | `user-documentation` |
| 供用户保留的成图与渲染输出（`render`） | `dsh-artifacts/renders/<HIPNAME>/` | `render-output` |
| 过程检查与诊断对照图（`visual_check`） | `dsh-artifacts/checks/previews/<HIPNAME>/` | `visual-check` |
| 独立运行输入、检查与执行证据（`execution_run`） | `dsh-artifacts/checks/runs/` | `execution-evidence` |
| 构建源码与任务脚本（`script`） | `dsh-artifacts/scripts/` | `project-source` |
| 原始执行回执（相对DSH工作区） | `dsh-artifacts/results/` | `execution-evidence` |
<!-- project-layout:generated:end -->

默认把新产物收在一个`dsh-artifacts/`目录，HIP保留在工程根目录。按用途选择子目录：生成图片直接用于材质时属于texture；生成的多视角草图属于reference_generated。渲染是否正式交付与目录位置分开，`present`负责明确交付。目录按实际写入需要创建，不预创建整套空目录。

`script`存放本任务的构建源码和维护脚本，临时探针用其`scratch/`子目录。用DSH文件工具编辑源码，再通过Bridge执行Houdini操作；不把普通文件改写塞进HOM事务，文件副作用不受Undo保证。运行时仍被HIP、表达式或回调引用的脚本属于依赖，不能作为临时文件删除。原生Package资源目录保持原生结构。

`documentation`用于用户接手工程或工具所需的说明及其专用资源，与分析证据分开。工程命名、版本、直接文件交付和说明格式由[文件交付方法](../skills/houdini-network-handoff/references/file-delivery.md)维护；目录投影本身不生成文档、不转换格式或整理旧文件。

`dsh-artifacts/renders`用于准备交给用户或作为渲染输出保留的成图，不能从目录名推断“已验收/已最终交付”。`dsh-artifacts/checks`用于建模过程中的观察、故障诊断和A/B对照，包含截图与测试渲染；不是只有截图才放这里。`render_view`等捕获默认选择检查用途，只有明确要保留/交付的图片才选择`delivery`。正式ROP尊重已配置的用户路径；用它做检查时明确把本次`picture`指向visual_check目录，不沿用成图目录存诊断图。相同图片也可能被重复渲染或显式写入不同目录，系统不按文件内容猜测用途或移动历史文件。

教程切片、转录、抽帧、索引、记录和资料交接放在`dsh-artifacts/analysis/<tutorial>/`，Trace分析报告也使用analysis角色。纯离线解析没有命名HIP时，按用户明确的任务工作区选择该目录；CLI仍接受显式输出，不强制保存HIP或改写用户目的地。导入媒体属于reference_downloaded，缓存属于cache。旧analysis或geo目录不自动迁移。

`dsh-artifacts/analysis`是按需产生的分析资料，不是工程状态数据库。视频资料在各教程子目录，执行复盘在`trace/`；其中可能有当时工程路径、节点和执行状态的快照，不持续代表当前HIP。恢复标识在HIP内，可信保存材料在安装根的`recovery/checkpoints/`，对话历史由DSH持久化。原始执行回执写入DSH工作区下的`dsh-artifacts/results/`；它独立于HIP锚点，两者不同时不会被错误搬到HIP旁。历史`.dsh-houdini-results`按已记录的原路径读取，不迁移、不重写旧回执。复盘本身可选择独立诊断输出根，无需每次向用户工程追加报告。

加载警告原文属于恢复诊断，保存在同一恢复根的`load-warnings/`，按内容hash复用；对话只记录有限预览和可核验引用。它不进入`dsh-artifacts/analysis`或渲染目录，也不随Save As搬动；读取沿DSH原生恢复历史定位，规则见[接续](multi-instance.md#单实例保存点恢复)。

`render`和`visual_check`在各自目录下按实际HIP的`HIPNAME`分组；它只去掉`.hip/.hiplc/.hipnc`扩展（忽略扩展大小写），保留版本后缀、Unicode、空格和点号，不猜测哪些版本属于同一工程。同stem的不同许可扩展共享命名组，精确来源以回执`hip_path`为准；目录名不作为工程身份。`visual_check`的受管捕获再使用`run-*`分组，保留唯一capture文件名和在途reservation。Save As只改变后续默认输出，不搬旧文件。

`execution_run`在DSH会话工作区的`checks/runs/`下承载独立运行输入、紧凑报告和检查产物；它不为分配目录额外查询live HIP，也不改变渲染和依赖的实际锚点。显式运行位置及历史路径保持，不自动迁移。

作者维护的builder、准备脚本和manifest留在`script`目录；运行器自动分配一次性运行目录。完整的大执行回执只在run的`executions/`中留档一次，报告携带同源事实投影、实际路径、内容摘要和JSON pointer；读取或归档失败不能替换原操作错误。运行prefs等机器状态放在运行器独占临时根，确认其拥有的进程树退出后再清理；用户工程、输入版本和观察证据不随环境清理。

检查和运行目录是证据，不是自动可删除缓存。原生截图超时或中断后可能仍有晚到写入，不能删除其预留或复用路径。正式图片选定后按现有文件呈现方式交付，位置不自动证明通过。

## 工程锚点与显式目的地

`scene_info()`和固定现场metadata返回`project_layout`：`available`、`hip_path`、`project_root`及各角色的绝对`directories`。目录按本次HIP路径作字面投影，不解析目录链接或访问网络服务器；`available`只表示有命名的绝对HIP锚点，不证明目录在线、文件存在或可写，也不持续追踪Save As。Host与实际写入器在文件操作时解析真实目录并核对权限及子目录重定向。

打开工作区、工程登记、自动metadata和执行回执只读取GUI原生HIP身份；`file_exists=null`表示没有观察磁盘，不能解释为文件存在或缺失。显式`scene_info()`、保存和输出操作仍读取真实文件状态。网络共享和映射盘使用原路径，不静默切到本地工作区；服务器不可用时文件操作仍可失败，但入口身份采集不等待网络探测。无GUI的Houdini对默认文件名的`isNewFile()`判断有歧义，只在该情况下保留磁盘核对。

自动工程输出取操作开始时实际命名HIP的目录，不能把DSH session workspace或启动cwd当作HIP。长时间生成/捕获固定最初目的地，期间Save As不改变在途输出；后续操作重新取得当前工程位置。回执是实际文件位置的依据，不猜测带唯一后缀的名字。

未命名HIP没有自动工程根。资料收集、离线生图或临时截图可以明确指定目的地，不为这些操作强制Save As。显式绝对路径或含子目录的原有目的地保持，不为统一结构重写用户选择。Host仍执行DSH文件策略；HIP与可写workspace不一致时，在请求提供方之前报告，不静默扩大权限。

现有`dsh-reference/`、`dsh-texture/`、`scripts/`等目录及用户指定路径不自动迁移；旧HIP、源码和历史交付可能仍引用它们。Save As也不是依赖迁移指令；需要搬工程时显式复制所需依赖、核对引用与重开，再决定是否处理原文件。

目录组织不证明工程内容连续：同工作区可有无关HIP，跨目录另存也可属于同一工程。
任务默认跟随成功Save As、可信保存点恢复与DSH原生目录迁移见[工程接续设计](multi-instance.md#工程接续设计)；仅有当前路径观察仍不能证明工程连续或恢复成功。

## 各入口的默认行为

- `image_generate`默认`output_policy='managed'`、`purpose='reference'`。`output`省略或安全basename，生成到reference_generated；`purpose='texture'`进入texture。目录来自当前任务所选Houdini的实际现场，结果带角色、工程根、原HIP和观察身份。`output_policy='explicit'`必须给目的地，相对路径沿DSH workspace解释，不查询Houdini。
- 网络资料保存先读取`project_layout.directories.reference_downloaded`，再用可用的通用下载能力明确选择该目录。精确DSH的`web_fetch`只读取网页文本，不提供二进制下载；本插件没有把它伪装成下载工具或复制一套网络安全策略。取得链接不等于图片已下载或已经看过。
- `render_view`、`viewport_screenshot`与界面截图默认managed用于视觉检查；选择delivery生成到render。图像先按HIPNAME分组；只有managed继续添加run分组，explicit裸文件名进入visual_check的HIPNAME目录。原有run-id、唯一分配、用户状态恢复和捕获验证保持不变。
- `render_frame`尊重持久ROP路径或本次显式覆盖。仅传裸文件名时，图像ROP默认进入render的HIPNAME目录、COP的`copoutput`默认texture；SOP/DOP/CHOP缓存按cache角色进入`dsh-artifacts/cache`。新建Karma Render Settings（含Karma Setup）的picture与checkpoint使用同源render目录和原生`$HIPNAME`，可随Save As继续求值；已有ROP的含目录路径不重写。COP要保留可继续导出的工程设置，应同时保存ROP中的`$HIP`相对路径，不把一次临时覆盖当作持久配置已修改。

## 生命周期与交付

参考资料和贴图保留原文件；贴图是工程依赖，不能因已渲染一次就删除。检查图只在其确为本任务创建、已无观察/恢复/交付引用且无在途写入时按明确范围处理。目录名、时间或“看过图片”都不构成清理许可。

没有自动目录扫描交付、定时清理、搬运副本或独立资产账本。DSH原始附件和预览附件仍由DSH管理；执行归档不是可随意清理的临时文件。读取成功、文件存在、颜色/通道正确、视觉效果正确与最终交付分别验证。

## 实现与验证

实现：[Houdini目录投影](../houdini/python3.11libs/dsh_project_paths.py)、[捕获路径分配](../houdini/python3.11libs/dsh_preview_paths.py)、[Host项目路径](../src/project-paths.ts)、[生图入口](../src/image-generation.ts)。领域方法分别在[COP文件交付](../skills/houdini-cop-workflow/references/cache-and-delivery.md)和[文件呈现](../skills/houdini-network-handoff/references/file-delivery.md)维护。

验证：[受管路径](../tools/tests/dsh-managed-preview-paths.test.py)、[现场metadata](../tools/tests/dsh-scene-context.test.py)、[输出恢复](../tools/tests/dsh-output-checkpoint.test.py)、[生图边界](../tools/tests/image-generation.test.mjs)、[真实DSH与前端消费](../tools/tests/dsh-image-generation-smoke.test.py)。重点覆盖HIP/workspace不同、未命名HIP、Save As前后、链接重定向、晚到writer、用户文件保留及实际返回路径。
