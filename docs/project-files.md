# 工程文件与图像目录

适用于参考资料、分析产物、生成图、COP贴图、工程缓存、渲染和视觉检查的默认输出。目录角色由[project-layout.json](../houdini/project-layout.json)唯一维护，Houdini与Host读取同源；下面的目录表由[生成器](../tools/gen-project-layout-docs.mjs)更新。它不是用户资产数据库，不记录完成状态或替代DSH会话。

## 默认目录与用途

<!-- project-layout:generated:start -->
| 用途 | 工程相对目录 | 生命周期标识 |
|---|---|---|
| 下载的参考资料（`reference_downloaded`） | `dsh-reference/downloaded/` | `reference` |
| 生成的辅助参考（`reference_generated`） | `dsh-reference/generated/` | `reference` |
| 材质与工程依赖（`texture`） | `dsh-texture/` | `project-dependency` |
| 几何、模拟与通道缓存（`cache`） | `dsh-cache/` | `project-dependency` |
| 教程与任务分析资料（`analysis`） | `dsh-analysis/` | `analysis-evidence` |
| 渲染输出（`render`） | `dsh-render/` | `render-output` |
| 过程视觉检查（`visual_check`） | `dsh-visual-checks/` | `visual-check` |
<!-- project-layout:generated:end -->

按用途选择目录：生成图片直接用于材质时属于texture；生成的多视角草图属于reference_generated。渲染是否正式交付与目录位置分开，`present`负责明确交付。目录按实际写入需要创建，不预创建整套空目录。

教程切片、转录、抽帧、索引、记录和资料交接放在`dsh-analysis/<tutorial>/`，Trace分析报告也使用analysis角色。纯离线解析没有命名HIP时，按用户明确的任务工作区选择该目录；CLI仍接受显式输出，不强制保存HIP或改写用户目的地。导入媒体属于reference_downloaded，缓存属于cache。旧analysis或geo目录不自动迁移。

`visual_check`的受管捕获继续在目录下使用`run-*`分组，保留唯一capture文件名和在途reservation。它是观察证据，不是自动可删除缓存。原生截图超时或中断后可能仍有晚到写入，不能删除其预留或复用路径。

## 工程锚点与显式目的地

`scene_info()`和固定现场metadata返回`project_layout`：`available`、`hip_path`、`project_root`及各角色的绝对`directories`。它只表达该次观察，不创建文件、不证明写入权限，也不持续追踪Save As。

自动工程输出取操作开始时实际命名HIP的目录，不能把DSH session workspace或启动cwd当作HIP。长时间生成/捕获固定最初目的地，期间Save As不改变在途输出；后续操作重新取得当前工程位置。回执是实际文件位置的依据，不猜测带唯一后缀的名字。

未命名HIP没有自动工程根。资料收集、离线生图或临时截图可以明确指定目的地，不为这些操作强制Save As。显式绝对路径或含子目录的原有目的地保持，不为统一结构重写用户选择。Host仍执行DSH文件策略；HIP与可写workspace不一致时，在请求提供方之前报告，不静默扩大权限。

现有`references/`、`textures/`、渲染和检查文件不自动迁移。Save As也不是依赖迁移指令；需要搬工程时显式复制所需依赖、核对引用与重开，再决定是否处理原文件。

## 各入口的默认行为

- `image_generate`默认`output_policy='managed'`、`purpose='reference'`。`output`省略或安全basename，生成到reference_generated；`purpose='texture'`进入texture。目录来自当前任务所选Houdini的实际现场，结果带角色、工程根、原HIP和观察身份。`output_policy='explicit'`必须给目的地，相对路径沿DSH workspace解释，不查询Houdini。
- 网络资料保存先读取`project_layout.directories.reference_downloaded`，再用可用的通用下载能力明确选择该目录。精确DSH的`web_fetch`只读取网页文本，不提供二进制下载；本插件没有把它伪装成下载工具或复制一套网络安全策略。取得链接不等于图片已下载或已经看过。
- `render_view`、`viewport_screenshot`与界面截图默认managed用于视觉检查；选择delivery生成到render。原有run-id、唯一分配、用户状态恢复和捕获验证保持不变。explicit裸文件名进入visual_check根目录；只有managed自动添加run分组。
- `render_frame`尊重持久ROP路径或本次显式覆盖。仅传裸文件名时，图像ROP默认render、COP的`copoutput`默认texture；SOP/DOP/CHOP缓存按cache角色进入`dsh-cache`。COP要保留可继续导出的工程设置，应同时保存ROP中的`$HIP`相对路径，不把一次临时覆盖当作持久配置已修改。

## 生命周期与交付

参考资料和贴图保留原文件；贴图是工程依赖，不能因已渲染一次就删除。检查图只在其确为本任务创建、已无观察/恢复/交付引用且无在途写入时按明确范围处理。目录名、时间或“看过图片”都不构成清理许可。

没有自动目录扫描交付、定时清理、搬运副本或独立资产账本。DSH原始附件、预览附件与`.dsh-houdini-results`继续承担各自的传输/恢复/历史职责，不迁进上述工程目录。读取成功、文件存在、颜色/通道正确、视觉效果正确与最终交付分别验证。

## 实现与验证

实现：[Houdini目录投影](../houdini/python3.11libs/dsh_project_paths.py)、[捕获路径分配](../houdini/python3.11libs/dsh_preview_paths.py)、[Host项目路径](../src/project-paths.ts)、[生图入口](../src/image-generation.ts)。领域方法分别在[COP文件交付](../skills/houdini-cop-workflow/references/cache-and-delivery.md)和[文件呈现](../skills/houdini-network-handoff/references/file-delivery.md)维护。

验证：[受管路径](../tools/tests/dsh-managed-preview-paths.test.py)、[现场metadata](../tools/tests/dsh-scene-context.test.py)、[输出恢复](../tools/tests/dsh-output-checkpoint.test.py)、[生图边界](../tools/tests/image-generation.test.mjs)、[真实DSH与前端消费](../tools/tests/dsh-image-generation-smoke.test.py)。重点覆盖HIP/workspace不同、未命名HIP、Save As前后、链接重定向、晚到writer、用户文件保留及实际返回路径。
