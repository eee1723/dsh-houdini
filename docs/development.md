# dsh-houdini 开发进度与卡点

> 本文是 dsh-houdini 的**开发进度日志**，随开发同步维护（改了代码就顺手更新本文）。
> 设计宪法见 [`tool-design.md`](./tool-design.md)（动词词表、两轴模型、铁律、帮助文档三阶段）。
>
> 状态图例：✅ 完成 · 🔶 进行中 · ⛔ 卡点 · ⏳ 待办

---

## 1. 现状总览

| 模块 | 状态 | 关键产物 |
|---|---|---|
| 工具（host half） | ✅ | 5 个 `houdini_*` 工具 |
| 动词词表（bridge namespace） | ✅ | 39 个主目录动词 + 2 个 display 兼容入口 + `_resolve`（九域，§2.22） |
| 动词追踪 tracer（Phase 1） | ✅ 已激活（2026-08-17 会话实测 `verbs (N)` 段回传） | `verbs` 字段 + `[verb]` stdout 行 |
| 裸 hou advisory | ✅ | AST 扫描 → `advisory` 字段 + `hint:` 渲染（§2.8） |
| launcher：preset 同步 + 分阶段百分比 + 超时/日志诊断 | ✅ | `dsh_launcher.py`（§2.23 / §3.2） |
| 版本与诊断面板 | ✅ | `dsh_manager.py`（§2.24） |
| Houdini Trace 视图（Phase 2） | ✅ 已重写：全量调用 + 裸 hou hint 可见（§2.9） | `client.js` + `dsh.client` 声明 |
| Houdini trace 审计 skill | ✅（§2.20） | `houdini-trace-analysis` + evidence JSON + 审计量表/模式库 |
| plugin persona 中性化 | ✅ | GUIDANCE 只讲工具用法，persona 移入 preset |
| houdini 模式 preset | ✅ | `~/.dsh/.agent-presets/houdini/` + `presets/houdini/`，校验通过 |
| houdini-dev 模式 preset（开发） | ✅ | `~/.dsh/.agent-presets/houdini-dev/` + `presets/houdini-dev/`，`standingKeyFor` 校验通过 |
| Houdini 侧一键启动/桥/WebView | ✅ | `dsh_launcher.py`（profile 模式）等 |
| webview 设置页卡顿修复 | ✅ 6→61 FPS（2026-08-18，§2.13） | `dsh_webview.py` 注入禁 backdrop-filter |
| 视觉闭环（vision-toolkit + qwen-vl-max） | ✅ 全流程实测通过（2026-08-18，§2.13） | viewport_screenshot → 百炼识图 |

---

## 2. 已完成

### 2.1 工具（host half）

`src/index.ts` → `lib/index.js`，Cordis 插件形状 `{ name, inject, Config, apply }`：

- `name = 'dsh-houdini'`，`inject = ['tools', 'systemPrompt']`
- 注册 5 个工具：`houdini_exec` / `houdini_query` / `houdini_job_submit` /
  `houdini_job_status` / `houdini_job_cancel`（见 `src/tools.ts`）
- 系统提示词 guidance 段（order 150，**persona 中性**）：只讲工具用法（动词词表、`hou` 预导入、桥报错），不含「你正在驱动 Houdini」的身份——身份归 preset

### 2.2 动词词表（bridge namespace）

`houdini/python3.11libs/dsh_hou_helpers.py` 定义、`dsh_bridge.py` 注入 exec 命名空间：
39 个主目录动词 = vocabulary（`verb_help`）+ scene（info/timeline/bookmark 5 个）+ 类型目录（`search_tab_menu`/`resolve_latest_type`）+ node 域
（原 node CRUD + SOP output/OBJ visibility 拆分 + `layout_nodes` + 兼容 display wrappers）
+ parm 域（`list_parms`/`read_parms`/`set_parm`/`set_parms`/`create_spare_parms`）
+ asset 域（`hda_create`/`hda_info`/`hda_get_section`/`hda_set_section`/
`hda_patch_section`/`hda_set_interface`）
+ geometry 域（`geo_attrib_stats`/`geo_piece_stats`/`geo_frame_diff`）+ render/sim 域（`render_frame`/`render_check`）
+ viewport 域（`viewport_screenshot`）+ 视觉验证主干（`render_view`）。
bridge 另保留旧 `set_display/display_node` 两个兼容 wrapper：不进 guidance 主词表，
但留在独立 compatibility catalog 域以诚实回放历史 trace。

### 2.3 动词追踪 tracer（Phase 1）—— 已实现，待激活

`dsh_bridge.py` 给每个动词包 `_make_tracer`：

- exec 结果 envelope 多一个 `verbs` 字段：`[{verb, args, kwargs, ok, result/error, ms}]`
- `hou.Node` 入参/出参自动转 `{"node": path}`；失败调用 `ok:false` 且不改变抛错语义
- stdout 打印 `[verb] 名称(入参) -> 出参 (耗时)` 摘要行
- `src/bridge.ts` 加 `verbs?` 字段；`src/tools.ts` 的 `renderVerbs` 渲染成可读列表

### 2.4 Houdini Trace 视图（Phase 2 代码）

- **client 半**：`client.js`（手写 CJS factory，免 bundler），
  `window.__ModuleLoader__.load({ id: "dsh-houdini", factory })`，
  在 `conversation.view` 上注册 `id="houdinitrace"` 标签页，从
  `useSession(snapshot.nodes)` 过滤 `houdini_*` 的 `ToolResultNode`、
  抽取 `verbs (...)` 段渲染成调用卡。
- **声明**：`package.json` 加 `exports["./client"]` + `dsh.client: { platform: "web", inject: [...] }`。
- 已用动态插件 `hdtra-1` 验证同一条链路（Slot 注册 + `useSession` 读取）可跑通。

### 2.5 houdini 模式 preset（模式层）

- 通过 `agentPresets.copy("standard", "houdini")` 创建本地 preset
  `~/.dsh/.agent-presets/houdini/`；模板入库到 `presets/houdini/`。
- 改动：persona → 「Houdini automation agent」+「已连接 Houdini 会话、把场景当主目标、路由到专用工具」；新增 `- id: houdini` / `name: dsh-houdini` 行（只注册工具+提示词，不发布服务，无需 isolate realm）。
- 包名可解析：`dsh plugin --profile web add E:/dsh-houdini`（pnpm link）。
- `standingKeyFor("houdini")` 挂载校验通过。
- 启动路径收敛：`dsh_launcher.py` 改 profile 模式（去 `--patch cordis.dev.yml`），
  preset 是唯一挂 dsh-houdini 的地方。

### 2.6 plugin persona 中性化（关键修正）

问题：plugin 的 `systemPrompt` guidance 里硬编码了「你已连接 Houdini、把它当主目标」，
导致 plugin 一加载就把 Houdini 身份注入到**任何**会话（含其它 workspace 的创造模式）。

修正（对齐官方「组合包=能力层、preset=模式层」）：
- `src/index.ts` 的 GUIDANCE **去掉 persona**，只保留工具用法（动词词表、`hou` 预导入、桥报错）。
- 「你已连接 Houdini、路由到专用工具」这段**移入 preset 的 persona**（`presets/houdini/`）。
- 结果：plugin 是能力层（persona 中性），身份/上下文由 preset 提供。

### 2.7 首次端到端实测（自行车会话，2026-08-16）

会话 `session-1e45285c`（「给我做一个自行车」，Houdini 模式，64 步 / 66 次工具调用）
**跑通了全流程**：57 个 SOP 节点、Mantra 渲染出图、保存 hip、视口聚焦。但暴露 6 个问题：

1. **动词词表零使用**：GUIDANCE 确认已注入（request/header 含完整动词表），但 30 次
   exec/query **全部裸写 `hou`**，连类型探测都手写 try/except 重造（等价 `search_tab_menu`）。
   → 提示词约束力不足：preset persona 要强化「优先动词」，桥侧可在检测到裸 `createNode(`
   时在结果里追加提示。
2. **12/66 调用失败（18%）**：多为裸 `hou` API 臆测错误（`Vector3.tuple()`、
   `Matrix4.multiply`、`Parm.set(str)` TypeError、`ObjNode.isRenderFlagSet` 不存在等）——
   正是动词层和 hou API Skill 要消灭的浪费。
3. **loop guard 误报**：dsh 的重复调用卫士对 `houdini_job_status` 轮询（参数天然相同）
   触发 3 次「你在重复相同调用」警告。→ `houdini_job_status` 应加 `wait`/`timeout_ms`
   长轮询参数（对齐官方 `job_output` 形态）。
4. **两套 job 系统混淆**：模型把桥侧 jobId 传给官方 `job_output` → `unknown job`。
   → Phase 3 迁移 `ctx.jobs` 后消失。
5. **模型全程无视觉反馈**：`read_image` 被模型路由拒绝（deepseek-v4-flash 不声明 image
   输入），模型改用 pwsh + System.Drawing 读文件尺寸当「渲染探针」，12 次 pwsh 调用
   全在干这个。→ Phase 2（截图闭环）价值的实证，也实证了它受模型能力门控。
6. **Houdini Trace 标签页缺失根因**：`package.json` 的 `exports` 缺 `"./package.json"` →
   client-modules 的 `require.resolve(包名/package.json)` 抛 `ERR_PACKAGE_PATH_NOT_EXPORTED`
   → client 半静默 404。已修（见附录）。

### 2.8 动词采用率收尾 + launcher UX（2026-08-17）

trace 复盘（10:04 会话 `session-b49fe7e4`，「做193个颜色不同的圆锥」，4 次工具调用）：
探测阶段用了 `search_tab_menu`/`resolve_latest_type`，但**建场阶段 100% 裸 `hou`**
（193 次 `createNode` + `parm().set` + `setInput`），且 193 个独立 geo 对象本身就是
反程序化模式。针对性改动：

1. **GUIDANCE 强化**（`src/index.ts`）：动词词表 = PRIMARY interface，裸 `hou` 只是
   逃生舱，并写明逃生舱边界（hip I/O、渲染、UI、底层几何属性操作）。
2. **persona 加程序化生成原则**（`presets/houdini/agent.cordis.yml`）：重复/变化/规模
   类需求用小型程序化网络（Copy to Points / For-Each / 实例化 + 属性驱动变化），
   留下的场景应是可重煮的「配方」，不是烤死的节点堆。
3. **裸 hou advisory**（`dsh_bridge.py`）：AST 扫描每次 exec 的代码，完全没走动词却
   用了词表覆盖的裸调用时在 envelope 附 `advisory`；`src/tools.ts` 渲染为 `hint:` 段。
4. **launcher UX**（`dsh_launcher.py`）：`sync_presets()` 每次启动自动同步 preset；
   netstat/taskkill/前端进程树全部 `CREATE_NO_WINDOW`（原 `DETACHED_PROCESS` 会让
   每个控制台子进程各弹一个可见终端窗口）；控制台输出压成单行、去掉完成弹窗；
   等待对话框换 QPainter 手绘圆弧 spinner（30ms tick 手动驱动）。
5. **webview 置前**（`dsh_webview.py`）：`_bring_to_front()`（raise/activate + 短暂
   置顶再取消），修复内嵌 UI 被 Houdini 主窗口压住。
6. **依赖失踪根因（npm/pnpm 混管）**：前端两次 `ERR_MODULE_NOT_FOUND`（缺
   `@deepseek-ai/schemastery`）。第一次确实是 `git pull` 引入新依赖后未 `npm install`；
   但补装后复发——实锤根因：本仓库 node_modules 历史上由 pnpm 安装（留有 `.ignored`
   目录），pnpm 再次在该目录操作时会触发 **hideAlienModules**——把「别的包管理器装
   的包」**挪进** `node_modules/.ignored/`（不是删除），npm 补装的 devDeps 集体失踪。
   修复：从 `.ignored` 挪回 + launcher 新增 `ensure_dependencies()` 自检（优先从
   `.ignored` 挪回，仍缺再 `npm install`），每次启动前端前在 worker 线程执行。
   **教训：本仓库 node_modules 只用 npm 管，不要跑 pnpm。**

### 2.9 trace 复盘第二轮：视觉闭环断裂 + display 旗标事故（2026-08-17 下午）

复盘 13:21 会话 `session-798b48dd`（「动态循环霓虹灯灯泡」，41 分钟，171 次工具调用，
preset 误选 houdini-dev，模型 deepseek-v4-flash）发现的问题与修复：

**发现**：

1. **视觉闭环断了**：`read_image` 报错「deepseek-v4-flash 不支持图像输入」，agent 此后再
   没看过任何渲染图，改用文件大小启发式 + exec 里手写 PNG 解码器（zlib+struct）盲验，
   导致 ~20 分钟盲调渲染（10+ 组 A/B 测试帧），并得出存疑结论「该 Karma build obj→stage
   不应用 shop 材质」。
2. **advisory 触发 59 次全被无视**：机制正常（含 job 结果内），模型不遵从——纯提示对
   deepseek-v4-flash 约束力不够。
3. **job 状态误导**：job 报 done 时渲染实际失败（ROP 参数错 / 输出文件缺失），agent
   转而用 pwsh `Start-Sleep` 45~70s + 文件轮询，26 次 pwsh 约 13 分钟纯等待；一次
   mantra 挂死靠 agent 手动 `Stop-Process` 收场。
4. **display 旗标事故**（用户实机发现）：geo 里建了完整 SOP 链，但 display/render 旗标
   停在一个 circle 上，所有测试渲染只出一个圆环——「最后建的节点」≠「被渲染的节点」。
5. **houdinitrace 视图过滤缺陷**：`client.js` 只抽 `verbs (` 段，纯裸 hou 会话显示空白，
   恰好漏掉最该监控的信号。

**修复**（本次）：

1. **houdinitrace 视图重写**（`client.js`）：显示全部 houdini_* 调用，顶部统计条
   「N 次调用 · X 次用动词（共 M 个）· Y 条裸 hou hint」，每卡标 `verbs ×N` / `raw hou` 标签。
2. **新增动词** `set_display(node, render=True)` / `display_node(parent)`
   （`dsh_hou_helpers.py`，后者在旗标不在链尾时带 `note` 提醒）；advisory 映射补
   `setDisplayFlag`/`setRenderFlag`→`set_display`；GUIDANCE 动词清单同步。
3. **persona 三条新规**（`presets/houdini/agent.cordis.yml`）：① 渲染/截图前必须用
   `set_display` + `display_node` 核对旗标；② 无特殊需求时在 /stage（LOPs）用 Karma
   做渲染测试，不默认走 /out Mantra 或 obj 级 shop 材质；③ 交付物不明确时先用
   ask_user_question 确认「只建场景还是要渲染」，不擅自烧时间做测试渲染。

**待办**：~~job_status 加 wait 长轮询~~（已完成，§2.11）；视觉闭环需换
有视觉能力的模型或桥侧出图描述（`render_check` 已提供无视觉盲验，§2.11）；
动词遵从度是否上硬机制（拦截/升级措辞）待决策。

### 2.10 houdini 模式对话窗口水印（2026-08-17）

`client.js` 新增 preset 感知的水印层：会话 `agentPreset` 以 "houdini" 开头时，
对话窗口铺居中 Houdini 旋涡（`assets/houdini_swirl.png`，由 SideFX Labs 官方
badge 的镂空旋涡**反相提取**——badge 本体是满幅橙色方块，直接低透明度铺会是一坨
色块）+ 右下角橙色径向氛围光，淡入动画。实现要点：

- 水印组件挂在 `conversation.composer.dock`（会话作用域插槽），`display:contents`
  零占位，本体是 `position:fixed` 覆盖层（`pointer-events:none`）；
- preset 读法用标准 kit：`props.useSessions(s => s.byId[sessionId]?.agentPreset)`，
  ui-agent-preset 已把 `agent-preset/selected` 事件写回该 store，切换实时生效；
- 旋涡图 2.6 KB，base64 内联进 client.js（webserver 只 serve `/plugins/<id>/client.js`，
  不 serve 插件静态目录；将来图多了可走 host 半 `ctx.webServer.register` 开路由）；
- CSS 在 factory 体注入（`data-plugin-css` 去重），与官方 ui-agent-preset 同一先例。

---

### 2.11 trace 驱动的工具面扩展：render 验证 + 属性统计 + job wait（2026-08-17 晚）

对 `session-798b48dd` 做 AST 级复盘（171 次调用的代码体统计），按「重复手写样板 =
该收编进工具」原则定位到三类缺口并补齐：

**证据 → 改动**：

1. **18 个渲染 job 全是同构样板**（设 picture → setFrame → try render → sleep 轮询文件
   → 报大小），且 `render()` 不报错 ≠ 产物存在（两次假成功）→ 新动词
   **`render_frame(rop, picture, frame, timeout=110)`**：输出参数按常见名自动解析
   （`picture`/`vm_picture`/`sopoutput`/…），等产物落盘非空 + 采集 ROP 错误，
   静默失败在 `errors` 里明说。同步语义，>110s 走 job 通道（host 桥超时 120s）。
2. **10 次手写 PNG 解码器**（deepseek-v4-flash 无视觉，agent 用 zlib+struct 盲验渲染：
   亮度/非黑像素/帧间一致性）→ 新动词 **`render_check(path, ref=None)`**：亮度统计、
   非黑像素占比、主色、内容 bbox；传 ref 算两图 diff（循环帧验证）。QImage 优先，
   hython 退回纯 Python PNG 解码（8-bit，含 Paeth 反滤镜）。
3. **26 次 geometry()/attribValue 手工循环**（验证 @Cd/@curveu 驱动数据）→ 新动词
   **`geo_attrib_stats(node, name, attrib_class)`**：min/max/mean/count，
   point/prim/vertex/detail，多分量按分量给；detail 类无批量 API 用 `attribValue` 特判
   （H21 实测 `globalFloatAttribValue` 不存在）。
4. **37 次 job 轮询 + 26 次 pwsh sleep（~13 分钟）**→ `houdini_job_status` 加
   **`wait` 参数**（秒，上限 600）：桥侧 handler 线程长轮询到终态一次返回。
   **坑**：第一版把等待循环写进了 `with _jobs_lock:` 块内——plain Lock 内层再取同锁
   立刻自死锁（handler 挂死，实测复现）；修复为锁外等待、锁内只读状态。
   host 侧（`src/bridge.ts`）长轮询请求自动延长超时（wait×1000+10s）。
5. **12 次裸 `setExpression`** 未被 advisory 点名 → 映射补 `setExpression`→`set_parm`
   （`set_parm` 本就支持表达式路由）。
6. **11 次手写 bbox 循环** → GUIDANCE 注明 `describe` 已给 bbox/点数/属性清单。

验证：hython 回归 17 项全过（新增 geo_attrib_stats/render_frame/render_check 三组和
detail 特判）；桥端 HTTP 实测 wait 三种场景（即时返回/长轮询到 done/超时返回现状）+
cancel 不受影响。词表现在 **18 个**。

### 2.12 视觉能力：viewport_screenshot + 社区 vision-toolkit（2026-08-17 晚）

路线决策：**「社区的眼睛 + 我们的视神经」**——通用「看图」能力不自研（dsh 生态
已有完整品类：Anionex/YYTbit 的 vision-toolkit、dsh-vision-LMstudio 等，全都走
「视觉模型转文字」绕过 deepseek-v4-flash 的图像预检拦截），Houdini 特有的视口
采集自己做。

1. **新动词 `viewport_screenshot(path=None, frame=None)`**（viewport 域首个动词，
   词表 19 个）：走 `SceneViewer.flipbook` 单帧通道（不进 MPlay），所见即所得；
   GUI 限定，headless（hython）抛明确错误指向 `render_frame`。默认落盘
   `$HIP/screenshots/`。**注意**：GUI 捕获路径 hython 无法覆盖，只有 headless
   错误分支进了回归（#18），实机效果需在 Houdini GUI 里验证。
2. **安装 `@anionex/dsh-vision-toolkit` 0.1.7**（`dsh plugin --profile web add`，
   进 profile 的 cordis patch insert 层；profile 的 node_modules 由 dsh CLI 自己用
   pnpm 管——那是 profile 目录，与本仓库「只用 npm」的约束无关）。
3. **视觉提供方配百炼**（`~/.dsh/profiles/web/cordis.patch.yml` 同 id 覆盖）：
   `baseUrl=https://dashscope.aliyuncs.com/compatible-mode/v1`、`model=qwen-vl-max`、
   `protocol=openai`、`credential=VISION_API_KEY`。DashScope 密钥不落盘在 patch 里，
   需用户在 Settings → Plugins → Vision Toolkit 的只写密钥框粘贴（或预置
   `$DSH_HOME/.credentials.yaml`）。插件自带 vision-tools skill 会教 agent 何时用
   看图工具，无需改 preset。

目标闭环：`render_frame`（出图）→ `render_check`（客观指标）→ vision-toolkit
（语义验证：霓虹亮没亮/构图对不对）→ `viewport_screenshot`（视口侧对照）。

`viewport_screenshot` 实机踩坑与收尾（2026-08-17 晚，GUI 实测三轮）：

1. `FlipbookSettings.copy()` 是 `copy(from_settings)`（拷入），且类是**抽象无构造**
   ——settings 只能取自 `viewer.flipbookSettings()`；`flipbook(viewport=None,
   settings=None, ...)` 的 settings 是一次性覆盖，帧范围走 `settings.frameRange()`。
   第一轮 traceback 行号指着注释行报错 = Python Shell 缓存旧模块的指纹（
   `sys.modules` 不随 exec 重跑刷新），手动脚本必须 `importlib.reload`。
2. 视口装饰没有独立开关，全是 `hou.viewportGuide` 枚举 + `enableGuide/guideEnabled`；
   参考平面网格 = `XZPlane`（Y-up）。`clean=True`（默认）隐藏 13 种装饰 +
   强制开纹理，截完逐项恢复；`frame_target` 用 `frameBoundingBox` 取景，
   相机经 `defaultCamera()` 存/恢复变换（`setViewTransform` 不存在）。
3. uv* 系列设置属于 UV 编辑器视口，与 3D 视口无关；背面 tint 颜色 HOM 未暴露
   （只有 `removeBackfaces` 剔除），保持默认不动。
4. **flipbook 是异步渲染**：第一版 clean 在 `finally` 里立刻还原视口设置，还原
   发生在 flipbook 真正渲染之前——截图里网格/装饰一个都没少（2026-08-17 实机
   确认）。修复：所有还原挪到产物文件落盘确认**之后**。新增旋钮
   `textures`（None 不动 / True / False——模型 UV 贴图不想入镜传 False）和
   `backface_cull`（True = 临时背面剔除）。E:\edini 调研结论：其
   `media_manager.py` 只做三条捕获路径 fallback（saveImage/grabFrameBuffer/
   flipbook），**未做任何显示清理**，无可借鉴的网格处理；其
   `flipbookSettings().saveImage(buf,"JPEG")` 直出 JPEG 是将来免落盘的候选。
5. **地面网格的真凶是 `hou.ReferencePlane`**（H21 实机定位）：它**不是**
   `viewportGuide` 枚举（`XZPlane` 默认就是 False 网格照画）、不是
   `displayOrthoGrid`、也不在 viewopt* hscript 族（那是用户自定义显示选项的）。
   真身：`SceneViewer.referencePlane()` → `setIsVisible(False)`（hou.py:85795，
   "The reference grid (a.k.a. reference plane)"）。已收编进 clean 模式（隐藏+恢复）。
   排障过程中确认的两条死路：QWidget.grab() 对 Houdini GL 视口（RE_GLDrawable，
   非 QOpenGLWidget）只拿到黑图；viewopt* 族管的是用户自定义 option。

### 2.13 webview 设置页卡顿根因 + 视觉全流程实测（2026-08-18）

**Settings 页卡顿**。症状：内嵌 webview 里设置页点击/滚动都卡，对话页正常。
排查路径与结论：

1. 先排除前端应用本身：headless Chrome（CDP 探针）里设置页 DOM 仅 ~490 节点、
   idle 62 FPS，各 tab 都流畅——应用很轻，问题出在 Houdini 的 QWebEngineView
   环境（QtWebEngine 6.5.3 / Chrome 108，WebGL 上下文都建不起来 = 软件光栅路径）。
2. **在真实环境里测量**（关键方法）：经桥的 `/exec` 在 Houdini 主线程拿到
   `dsh_webview._view.page().runJavaScript(js, 0, callback)`，直接驱动用户面前的
   那个 webview 跑 rAF/滚动探针。注意 PySide6 签名是 `runJavaScript(str, int,
   object)`（worldId 在回调前）；JS 对象不回传（得 `JSON.stringify`）；桥 exec
   回值走 `__result__`。实测：idle 61 FPS，**滚动设置页（scrollBody 高 6018px）
   只有 6 FPS**，滚动期间 DOM mutation 仅 2 次 = 纯光栅瓶颈，不是 JS 重渲染。
3. 逐项 CSS 二分：box-shadow 无关；**`backdrop-filter` 一关即 45→61 FPS**。
   根因：设置弹窗遮罩的全屏毛玻璃（`--dsw-mask-blur: blur(2px)`）在 Chrome 108
   软件光栅下每帧重算整屏模糊。对话页无遮罩所以不卡。
4. 修复：`dsh_webview.py` 在 `loadFinished` 注入
   `* { backdrop-filter: none !important }`（SPA 注入一次即可；遮罩保留半透明
   底色，观感几乎无损）。实机复测 6 → **61 FPS**。

**视觉全流程实测通过**：桥 `viewport_screenshot`（clean 出图 1280x720）→
读 `~/.dsh/.credentials.yaml` 的 `VISION_API_KEY`（用户已在 Settings 凭据框配置）
→ DashScope `qwen-vl-max` 识图：模型对霓虹灯泡场景的描述（灰色中柱、弹簧线圈、
棋盘格底座、彩虹软管、无网格干扰）与图像逐项核对**准确**。约 921 prompt tokens
（图 882）。密钥明文不落任何仓库文件；测试脚本只在进程内读取使用。
（排障备注：Git Bash 里直接 print 中文响应会 GBK 乱码，`PYTHONIOENCODING=utf-8`
即可——纯显示问题，与链路无关。）

### 2.14 trace 复盘第三轮 + 截图窗口事故（2026-08-18 下午）

session-38bc1fdf（「看看我视窗中有什么」）复盘：

- **符合预期**：`viewport_screenshot`×2 + `render_check` + vision-tools skill +
  `vision_glance` 全链路走通；verb tracer 正常回传；最终回答把识图语义、场景
  结构、几何数据（2154 点/2150 面）综合得很好；agent 事后自觉清理临时文件。
- **动词采用率回退**：前 4 个 `houdini_query` 全是裸 hou 探索——手写枚举
  display 旗标踩 `'OpNode' object has no attribute 'isDisplayFlagSet'`（动词
  `display_node` 直接覆盖）、猜 `SceneViewer.currentViewport`（正确是
  `curViewport()`，异常被 try/except 吞掉继续跑）、手写节点树枚举（`find_nodes`/
  `graph` 可覆盖）。词表 19 个但「查询场景结构」场景 agent 仍首选裸 hou，
  guidance/preset 的约束对 deepseek-v4-flash 依旧偏弱（老问题，§2.9）。
- **API  usability 事故（已修）**：agent 直觉地传 `frame_target=True`（=取景到
  当前显示对象）直接报错——`viewport_screenshot` 现已接受 `True` = 「/obj 下
  当前挂 display 旗标的对象」。
- **产出落点**：一张截图被写进本仓库根目录（`E:/dsh-houdini/_viewport_check.png`，
  违反「产出锚定 $HIP」约束；agent 随后自己清理了）。低频，先观察。

**截图时 agent 窗口最小化**：桥驱动复现 3 轮（含激活窗口后截图）窗口状态均无
变化，窗口事件探针（QApplication eventFilter 记 WindowStateChange/Activate/Hide/
Show → `.window-events.log`）在截图期间**零事件**——`viewport_screenshot` 本身
不碰窗口。已上两道措施：① `viewport_screenshot` 收尾调
`_restore_webview_window()`，webview 若处于最小化则 showNormal + 置前（仅
isMinimized 才动，不抢正常焦点）；② 探针常驻，等真实 agent flow 再复现一次拿
实锤（根因嫌疑：Houdini 主窗口最大化盖住 webview 被感知为「最小化」）。

**热更新注意**：桥 exec 里 `importlib.reload(dsh_bridge)` 不安全（module 重载
重建 `_work_queue`，旧 pump 只 drain 旧队列 → 新请求挂死）。代码生效走
launcher 菜单重启（`restart_bridge` 先 stop 再 reload 再 start）。

**trace 复盘管道：`tools/trace-report.mjs`（2026-08-18，双向钢人论证后的决策）**。
目标是「观察 → 归因 → 词表进化」闭环；论证结论：复盘场景的重点是**分析逻辑**
而非展示层，静态词表 UI 面板会与本仓库 `tool-design.md` 漂移（否决），实时
webview 视图后置。实现：

1. 桥 verb ledger 加绝对时间戳 `ts`（epoch 秒）——单个 exec 内多个动词共享
   一条工具调用，没有 ts 无法跨 exec 重建真实调用顺序（trace 报告目前用
   工具结果时间 + ledger 顺序，ts 留给将来的实时视图/houdinitrace）。
2. `node tools/trace-report.mjs [sessionDir|file] [--out <file>]`：缺省取
   `~/.dsh/sessions` 最新 session，生成单文件 HTML 到 `tools/out/`（已
   gitignore）。内容：词表目录（**解析 `docs/tool-design.md` 生成**，按域
   分组 + 本次会话命中次数/未用标注，目录解析坑：「类型目录」标题无「域」
   字、返回列含空格——正则都要覆盖）、调用时间线（时间戳 + 耗时 + 折叠
   详情）、概览卡片（动词命中 x/19、纯裸 hou、失败、advisory）、纯裸 hou
   段落与失败调用专节（词表改进的直接输入）。
3. 排版验证方法：headless Chrome `--screenshot` 渲染产物再读图（HTML/CSS
   改动不要盲信）。

### 2.15 houdinitrace 实时视图重写：目录 + 时序（2026-08-18 晚）

把 §2.14 复盘报告验证过的信息架构搬进 client.js 的 Houdini Trace 视图
（实时第二落点）：

1. **目录数据通道的选型**：静态 client bundle 的 `require` 只认平台 seed
   word（`getStaticModules()`：react/cordis/ui-slots 等，**没有 host RPC
   符号**——`host.call` 只存在于动态 client-half 的 `new Function` 闭包
   参数里），webserver 也不 serve 插件目录 → 目录只能内联。方案：
   `tools/gen-client-catalog.mjs` 构建期从 `docs/tool-design.md` 解析并
   重写 client.js 的 `>>> houdini-catalog` 标记区（同 base64 旋涡的先例：
   内联的是机械派生物，不是手抄副本），挂进 `npm run build` 第一步。
   解析逻辑收敛在 `tools/catalog-lib.mjs`，trace-report 与生成器共用。
2. **视图重写**：左栏词表目录（按域分组，命中计数 ×N 随会话推进实时点亮，
   未用灰标），右栏真实时序时间线（结果事件时间戳 + 失败/裸 hou/advisory/
   动词徽章 + 动词 chip 带耗时，code 与完整返回折叠进 `<details>`），顶部
   统计条（houdini 调用数 / 动词命中 x/19 / 纯裸 hou / 失败 / advisory）。
   会话节点自带 `time`/`callTime`/`call.argsRaw`，数据全在 snapshot 里。
3. **验证路径**：前端页面重载即加载新 client.js（webserver 按请求读盘，
   不必重启前端）；`QWidget.grab()` 对 QWebEngineView 只拿黑图（合成器
   外渲染，同 Houdini GL 视口的死路）——视觉核对走 headless Chrome CDP
   （`Page.captureScreenshot`）连同一前端截图，DOM 断言走桥
   `runJavaScript`（§2.13 的探针法）。

### 2.16 产出落点：结构性纠正（2026-08-19）

**问题**：agent 产出反复写进插件仓库根目录（`_viewport_check.png`、
`_bike_preview.png`）。双向钢人论证 + dsh 源码调研后的结论：**根因不是
agent 不守规矩，是结构错位**——前端以 `cwd=仓库` 启动 → 会话工作区=仓库
→ workspace-write 沙箱（Windows ACL 受限令牌，**OS 级硬约束**，不止 fs
工具，pwsh 写工作区外直接 Access Denied）把仓库变成唯一合法写入点；
vision-toolkit 只能读会话工作区内文件（`sessionWorkspace(exec)` =
`exec.agent.session.header.cwd`，另有自有 `allowedDirs` 白名单）——agent
为让 `vision_glance` 读到截图，被迫把截图写进仓库。软规则（persona 的
「锚定 $HIP」）敌不过结构。

**调研确认的机制事实**（dsh 源码）：工作区注册可走
`ctx.workspaceRegistry.create(path)` / RPC `workspace.create`；
`workspace.json` 运行中手改无效（内存态权威，每次变更整文件原子写回）；
**preset 不能绑定工作区**（schema 无此字段；会话 cwd 创建时定、不可变）；
「前端启动目录 = 默认工作区根」。

**四层落地**（用户选定「结构性纠正」档，不建硬拦截）：

1. **launcher**：前端 cwd = `_hip_dir()`（当前 hip 目录；`untitled.hip`
   未保存 → 中立后备 `E:/dsh-houdini-workspace`（按需创建），再失败才回退
   项目根）。主线程解析后经 state 传给 worker 线程（hou 不碰 worker）。
   点 `DSH-Houdini → Version & Diagnostics... → Restart Services` 即重新对准当前 hip。
2. **host 侧**（`tools.ts`）：exec/query 结果经 `withWorkspaceNote`——
   会话工作区 ≠ $HIP 时往 advisory 通道追加提示（复用 `hint:` 渲染，
   trace 视图/复盘报告自动可见）；`bridge.hipDir()` 60s 缓存，untitled
   场景返回 null（不打搅，persona 已有「未保存先问用户」规则）。
3. **桥 advisory**：`_repo_write_advisory`——代码含仓库根路径字面量 +
   写语义关键词时附警告（纯 advisory，逃生舱不硬拦）。坑：`open(` 不能
   算写关键词（读文件也用它，误报），可靠信号是 `.write`/`save` 等。
4. **preset persona**：补「工作区 ≠ $HIP 时」的应对——别写仓库，请用户
   点 `DSH-Houdini → Version & Diagnostics... → Restart Services` 重 seed 或在 hip 目录工作区建会话。

**效果**：新会话默认落在 hip 目录工作区 → pwsh/fs 写仓库被 OS 级拒绝、
vision 直接读 `$HIP` 截图、桥 exec 裸写仓库有 advisory。存量会话（仓库
工作区）保持原样，可在侧栏切换。

### 2.17 自行车 trace 归因 + raw-hou gate（2026-08-19）

**session-4885627f「做一个程序化自行车」复盘**（7215 事件、25 次 houdini
调用、31 次动词调用、9 次失败）。对「词表设计有问题还是约束不够」的数据
回答：

- **采用率趋势其实在涨**：8-14/15 的早期 session 近 100% 裸 hou；自行车
  session 动词调用 31 次（resolve_latest_type×18、list_parms×8、
  viewport_screenshot×3…）。
- **裸 hou 三分归因**：①真缺口——spare parm 创建（FloatParmTemplate/
  IntParmTemplate），程序化工作流核心操作，parm 域无 create 动词；②已覆盖
  但模型不知道——裸写 setExpression（set_parm 字符串即表达式）、探测性
  createNode（tab_create 覆盖），advisory 触发但照旧被无视；③探测性试错
  噪音（猜节点类型/参数名的 9 次失败大半是这类）。
- **动词自身毛边**（顺手记下）：`resolve_latest_type` 不容忍大小写
  （"Object" 被拒）；obj 级节点无 setRenderFlag 引起的困惑。

**raw-hou gate**（软硬结合，用户拍板）：桥执行前 AST 拦截动词已覆盖 +
疑似改场景的裸 hou，真缺口走 `allow_raw="理由"` 豁免通道（豁免打印
[gate] 行进 trace，每条豁免=一份带理由的词表缺口记录）。设计细节与开关
方式见 `docs/tool-design.md`「raw-hou gate」节。hython 回归 19-22 覆盖
（拦截/只读放行/豁免放行+留痕/拦疑似修改）。**实验用法**：从 DSH-Houdini 菜单重启
重启桥后，Python Shell `import dsh_bridge; dsh_bridge.set_raw_gate(True)`；
观察豁免记录 → 补缺口（首个候选 `create_parm`）→ 逐步收紧。

### 2.18 草地 trace 复盘 → 「共享屏幕副驾驶」定位 + media relay + render_view（2026-08-19）

**session-f6689f05「做一片草地」复盘**（5571 事件、51 次工具调用、70 次动词
调用、11/19 命中）。核心事实：**搭建 15 分钟就成功了**（11:35 前网络完成、
#16 截图 dominant=[138,213,106] 明显是绿草地），失败全部发生在**验证与呈现**
环节——后 2 小时烧在：①视觉闭环两端断裂（read_image 被模型模态预检拦截；
vision_glance 被 "image escapes the allowed directories" 拦截——截图在
$HIP、vision 沙箱在工作区）；②徒手编程用户视口相机 4 次（Matrix4 猜错、
相机钻进地底 y=-9.8，~15 次调用）；③用户离开 110 分钟后视口状态漂移，
截图三连全黑（窗口状态污染），agent 无漂移感知。

经**双向钢人论证 + 用户拍板**，定位确定为「**共享屏幕的副驾驶**」：视口是
用户的领地，漂移是要共存的现实而非要对抗的噪声。由此落地：

- **media relay（P0）**：产图动词（render_frame/render_view/viewport_screenshot）
  经 `report_image()` 登记 → bridge envelope 带 `images` → host `GET /media`
  （新端点：只读、限图片扩展名、64MB 上限）拉回字节写进
  `<工作区>/.dsh-houdini-media/`，结果里渲染 `media` 段（from→to 映射，
  vision 工具用右侧工作区路径）。vision 通路与 $HIP 位置彻底解耦。
- **`render_view(node)` 新动词（P0，词表 19→20）**：agent 自有的
  `/obj/dsh_cam` + `/obj/dsh_cam_target` + `/out/dsh_opengl`（复用不重建）
  按显示几何 bbox 取景（距离按相机视场角反推），OpenGL ROP 离屏渲染 +
  render_check 一步到位。OpenGL ROP 而非 Karma（交付渲染器，不进验证闭环）、
  而非固定相机+视口截图（侵入用户视口/依赖窗口状态/分辨率绑面板）。
- **`describe` 加 `attrib_delta`**：相对 input 0 的属性增删（MMB 节点信息
  里美术心算的那一步；草地 #13 的 pscale 困惑自此自文档化）。
- **顺藤摸出的存量 bug**：`describe` 的几何摘要因 `category().name() == 'sop'`
  大小写比较（实际返回 'Sop'）**长期静默缺失**——草地 trace 里 agent 在
  describe 后仍手写 bbox/点数循环（6 次），根因在此。改为类别对象比较。
  （同类环境坑：本机 hython 编译 VEX 即栈溢出 0xC00000FD，HEAD 原生问题，
  t15 起回归跑不通，新回归用 color SOP 规避。）
- **卫生项**：workspace note 每会话一次（原实现每次调用重复——30+ 次后
  alarm fatigue，模型对 hint 完全免疫的实证）；`tab_create` parent 兼容
  path 字符串（铁律 1 的实现漏洞补全）；persona 写入主干流程
  「搭建 → set_display → render_view 验证 → 迭代」与视口禁令，Karma 段
  重新定位为「用户要成片时的交付渲染器」。
- **明确不做**：`viewport_look_at`（编程用户视口=错误抽象）、按使用率删动词
  （render_frame 零使用恰是该用没用的解药）、viewport_state/parm_menu 独立
  动词（API 碎片，折进现有动词）。

hython 新回归 23-27 全绿（tab_create 路径 parent / attrib_delta / 非图片
不登记 / envelope.images / render_view headless 报错 / describe geometry
回归）。host 侧 `npm run build` 通过，词表目录 20 个已注入 client.js。

**重跑对比（session-be6367cd，同日「做一片草地」）——终局裁判**：

| 指标 | 旧（f6689f05） | 新（be6367cd） |
|---|---|---|
| 墙钟时间 | ~2.5h（含 110min 用户离开） | **4.5 分钟** |
| 工具调用 | 51 | **11** |
| 硬失败 | 4 + 动词 FAIL 若干 | 2，均一步自愈 |
| 视觉验证 | 全断（模态拦截 + 沙箱拦截） | render_view ×4 + read_image 直读回传图 |
| 视口编程 | 4 次徒手矩阵，1 次钻地底 | **0 次** |
| 手写几何循环 | 6 次 | **0 次** |
| 结局 | 未验证、疑似失败收尾 | 模型亲眼看图迭代一轮后交付，vision 复核确认是草地 |

仅有的两次失败直接产出两个修复：①`direction='iso'`（agent 的直觉词汇）
→ render_view 支持命名视角（iso/front/side/top）；②960×540 请求渲出
1280×720 → 分辨率开关真名是 `tres` 而非 `override_camerares`（两 parm
都试做版本兼容）。另顺手修：tracer stdout 行补 kwargs（原来只打位置参数）；
catalog 解析器容忍 CRLF（文件被转成 CRLF 后 `$` 锚点全不命中，报告 0/0）。
桥重载技巧：`importlib.reload(dsh_hou_helpers)` → `reload(dsh_bridge)` →
`dsh_bridge.start()` 可经 exec 完成，不必每次都点菜单。

### 2.19 project_init OTL trace 复盘 → HDA authoring 域（2026-08-20）

复盘 `session-f608bfab`（17 turn、75 次 exec）确认「造工具」是继造内容后的
第二类高频任务：59/75 exec 完全绕过动词，`HDADefinition` / `ParmTemplateGroup`
相关裸调用约 55 次；参数组增量修补曾连续 6 次越修越乱，PythonModule 全文重发
5 次约 55KB，conditional 被 `setParmTemplateGroup` 静默吞掉又浪费 5 次调用和
1 个用户回合。基于真实失败面新增 7 个动词，词表 **20→27**：

- parm：`set_parms`（逐项容错的批量赋值）；`set_parm` 对数值赋值先清表达式/
  关键帧并在 `note` 回报，修复 `$FEND` 把 `parm.set` 静默架空。
- asset：`hda_create`（默认 `$HIP/otls`，显式同名 replace；原生类型永不覆盖）、
  `hda_info`（definition/section/递归参数树自省）、`hda_get_section` /
  `hda_set_section` / `hda_patch_section`（PythonModule 语法预检 + 写后读回；局部
  修改不用全文重发）、`hda_set_interface`（JSON-safe 声明式整组重建）。
- `hda_set_interface` 遵循 Houdini 参数面板语义：subnet 标准页从原生 subnet
  类型重取；custom 模板打 managed tag；Float 菜单按 HOM 明确拒绝；Int 菜单
  `default` 强制为索引，避免服务器实跑出现 1 fps；folder conditional 明确拒绝；
  `hide_when` 提交后逐项读回，Houdini 若吞掉则自动补 DialogScript `hidewhen`；
  标准页隐藏走公开 `ParmTemplateGroup.hide`，生成用户 GUI 同构的 `invisibletab`。
- `search_tab_menu` 类别支持 Object/Driver/Stage 等 UI 别名，错误列完整合法类别；
  raw-hou advisory/gate 新增 `createDigitalAsset`、`setParmTemplateGroup`、
  `addSection`、`setConditional` 映射；GUIDANCE 同步暴露新词表。

验证：新增 `houdini/tests/regress_hda_verbs.py`，H21 hython **11/11 全绿**，覆盖
HDA 创建/显式替换/原生类型防误删、动画清除、批量容错、完整 spec、标准页隐藏、
conditional 与真实 DialogScript 兜底修复、菜单陷阱、整组重建、section 唯一锚点补丁、Python 语法失败零污染、
桥注册/advisory 映射。GUI H21.0.440 另跑一次真实临时 HDA 全链路，随后删除临时
node/definition/file；桥热重启后确认 27 个动词已注入、无 probe 残留。

### 2.20 新草地 trace → 标准审计 skill（2026-08-20）

`session-40054277`（用户目标：程序化草地 + 风吹麦浪）共 8,939 事件、77 次工具、
183 次动词（按当前目录 13/27；会话实际只曝光旧 20 动词，即 13/20），从请求到最后工具约
43.4 分钟（工具 span 39.3 分钟）；13 次硬失败、2 次 verb 失败、
26 段无动词 Houdini 调用、9 段一次 `set_parm` 3–18 次。会话最终仍有 2 个 todo
未完成且结束于 tool result，无交付。最严重的因果链：classic Copy + PolyWire 后手写
instance transform，把 PolyWire 前的中心线 `lp` 当最终 rest，导致每株草截面塌为零；
全场 bbox/点数掩盖局部退化，agent 在用户纠正前花约 20 分钟调 display、灯光、相机、
gamma 和视觉 prompt。frame 1/12 最终 diff `mean_abs_diff=0`、`max_abs_diff=1`，
动画目标也未证明。

本次不直接按单 trace 删除动词，而是建立三层 trace 体系：

1. `houdinitrace`：会话内实时观察调用。
2. `tools/trace-report.mjs`：确定性 HTML 事实报告。
3. 随包 `houdini-trace-analysis`：审计任务契约、阶段门、该用未用/误用/缺失/
   拆并、Houdini 模块/属性/cook/显示/渲染/动画，并维护跨 trace 模式库。

实现内容：

- `tools/trace-session-lib.mjs` 成为多帧 zstd session 读取共用实现，HTML 报告改用它。
- 修正 HTML 报告硬失败口径：除 `Execution failed` 外也读取 tool-result `isError`/
  `Error:`，补回手写相机阶段 5 次 lossless-JSON 失败（旧报告误报 8，正确为 13）。
- `extract-trace-evidence.mjs` 输出 user/assistant、tool/verb、硬失败、裸方法、无动词
  修改、exec/query 边界、batch 机会、render/vision、todo/terminal、多个 trace 聚合；
  另记录 request-header capability snapshot，避免用当前 27 动词倒查旧会话、把当时未曝光的
  `set_parms` 错判为漏用（本次草地唯一 snapshot 确认只曝光旧 20 动词）。
- skill 审计量表规定模块验证阶梯、动画 A/B 完成门、warning 零忽略、视觉中性 prompt、
  工具机会唯一标签和 S1/S2/S3 证据强度；删除工具需 ≥3 个多样 trace + 替代/反例。
- `known-patterns.md` 初始固化 9 个跨 trace 模式；每次新分析只追加可复用证据，
  不把 task-specific 节点写成通用规则。
- 插件通过 `ctx.skills.register()` 注册正文与目录 resource base；`skills` 已是 Houdini/
  Houdini-dev preset 的现有服务，故不引入与旧 `0.0.x` 工具族冲突的 dsh-skill npm
  代际依赖。`npm pack --dry-run` 验证 skill、references、scripts、catalog/doc 均随包。

验证：skill-creator `quick_validate.py` 在 `PYTHONUTF8=1` 下通过（Windows 默认 GBK 会
误读中文 UTF-8）；单 trace、compact、三草地 trace 聚合均通过；`trace-report.mjs`
重构前后事件/调用保持 8,939/77/183、硬失败 13；catalog 分母随词表演化，
capability snapshot 固定保留当时曝光 20；注册 stub 读到正文和正确 resource base；
`npm run build` 通过。

### 2.21 新草地 trace 全量修复：显式 SOP 视觉隔离 + 领域完成门（2026-08-20）

用户确认后按 HTA-001..010 和「用户随机切 display/render 节点」扩展问题实施。核心
决策：用户 viewport 允许漂移，agent 不争夺；`render_view` 必须绑定显式 SOP，通过
隐藏 agent proxy 渲染；用户改 display/visibility 要隔离，改真实 target 要 fingerprint
检测并标 stale。

**视觉主干 v2**：

- 新建 agent-owned `__dsh_houdini_render_proxy`，内部 Object Merge 直接指向显式 SOP；
  即使源 OBJ 隐藏、display/render 指向空 Null，也能 cook 指定几何。OpenGL ROP
  `forceobjects/vobjects` 只指 proxy，proxy 自身 display 关闭，不进入用户 viewport。
- agent camera/target/ROP 路径带 owner userData；同名用户节点不接管、不删除、明确报冲突。
- 保存/恢复用户 OBJ visibility、selection 和 frame；render_frame 自身也 finally 恢复 frame。
- ROP 固定 camera/object filter、排除 scene lights、smooth/usegeocolor、colorcorrect none、
  gamma 1、分辨率；`framing=full|detail` + `coverage` 取代手写 Matrix4。
- preflight 用显式 SOP `geometryAtFrame` 拒绝空/error；返回 source fingerprint 前后、
  `stale`、proxy/camera/ROP、eye/direction、实际 ROP 设置和 truthful restore 状态。
- 默认图片名用 `time_ns + frame`，避免同秒覆盖；Object Merge `xformtype=Into This Object`
  保留源 OBJ 世界变换。

**SOP/OBJ 状态拆分**：新增 `sop_set_output/sop_output_node`（singular SOP output）、
`set_object_visible/visible_objects`（plural OBJ visibility），旧 `set_display/display_node`
按 context 兼容路由；`display_node('/obj')` 不再调用不存在的 `displayNode()`。新增
`layout_nodes`。

**几何/时间/场景完成门**：

- `scene_info` 只读且不移动 playbar；`set_timeline` 管 fps/ranges/current frame，bookmark
  按 list/create/delete 拆分，关闭 OTL trace 的 6 次 API 考古缺口。
- `geo_piece_stats` 用内存 Connectivity SOP Verb，不污染网络；返回 piece local bbox/extent/
  area/degenerate。真实 9000 株、306k prim 草地压测 10.5s，识别 9000 pieces、0 退化。
- `geo_frame_diff` 用冻结 `geometryAtFrame` 比较 point 属性，不移动 playbar；旧草地 wind
  frame 1/12 被客观判定 100% unchanged。
- 进一步发现 HTA-011：wind snippet 引用了 amp/speed/wavenum/dir*，节点无 spare parms，
  agent 的 `if parm exists` 赋值全部跳过。新增 `create_spare_parms` 扫 `ch/chf/chi/chv/chs`
  创建类型化参数并应用显式 defaults；临时 Wrangle frame 1/12 mean delta=0.483。
- `render_check` diff 增加 8 位 mean、mean max-channel、RMSE、changed/meaningful pixel %；
  `cook_node(force=...)` 增加 `ok/warning_free/healthy`。

**失败原子性**：bridge GUI exec 用唯一 `hou.undos.group`；异常且栈顶 label 精确匹配才
`performUndo()`，envelope 回报 `rollback`。现场“建 geo 后主动 raise”返回 applied=true，
节点不存在。headless undo disabled 明确 unsupported；文件/HDA 库等非 undoable 副作用
不伪称回滚。

**工作流层**：新增随包 `houdini-sop-workflow` skill，固化 Tab 类型选择、Copy to Points、
deform-before-skin、属性 class/传播、piece/多帧模块验证、warning 完成门、显式 SOP 视觉
与交付卫生；trace skill 在 SOP 任务时要求联用。模式库扩展至 HTA-011 并把已修项标状态。

验证：

- headless `regress_scene_geometry_verbs.py` 8/8：scene/timeline/bookmark/display/piece/frame/layout/diff/spare。
- GUI `regress_visual_gui.py`：源 OBJ 隐藏且 output=empty、另有 8× 红色可见干扰物；
  两次显式绿色 GOOD_OUT 图像完全一致（dominant `[1,73,1]`），世界中心 X=2 保留，
  proxy hidden，frame/selection/flags 恢复；显式空 SOP 在渲染前拒绝。
- GUI rollback 与 spare-parameter animation probe 通过；这些 probe node/temp dir 已清理。
- 同类草地 disposable workflow：ribbon + Copy to Points + typed spare wind，625 pieces、
  0 退化、cook healthy；frame 1/12 geometry mean/max delta 0.0516/0.1636，0% unchanged；
  render changed/meaningful pixels 10.09%/8.80%。用户 output=empty、OBJ hidden 时两帧仍
  `stale=false`、state restored。Probe OBJ 自动删除；两张系统 TEMP 回归 PNG 因宿主删除
  策略拒绝保留为 54KB 一次性残留，不属于仓库/$HIP。
- H21.0.440 已验证；H22 同代码路径保留待有 H22 GUI 环境时复跑。

### 2.22 第二次草地 trace：可信时序证据与契约自发现（2026-08-20）

复盘 `session-71d76525`：50 次工具、135 次动词、8 次硬失败，结构/cook/piece/
spare/time dependency/保存均完成，但 frame 25/55 分别按动态 bbox 自动取景，camera
center/size/dist 不同，21.1% pixel diff 混入相机漂移；视觉 A/B 又判断“没有明显
行进波浪”，agent 却把 todo 与最终文本写成全部通过。另有 4 次动词签名/返回形状
误读和 2 次 `-0.0` 导致的 lossless JSON 整体拒绝。

本轮修复：

- bridge JSON-safe 边界把所有有限负零规范化为正零；`__result__`、verb ledger、
  hou Vector/Color/Matrix 与 job 共用，NaN/Infinity 仍转字符串；回归要求最终 envelope
  可被 `json.dumps(..., allow_nan=False)` 接受。
- 新增 `verb_help(name)`，返回准确 signature/docstring、未知名相似建议；无需先失败或
  读取仓库源码。主目录 38→39，两个 display compatibility wrapper 不变。
- `render_view(..., framing_frame=)` 可把 A/B 多帧锁到同一参考 bbox；返回 framing
  frame/source signature。空闲 proxy 仍清空真实 Object Merge 引用，避免隐形依赖，
  但保留 state/last target/frame/output userData 和 source comment，解释“为何现在为空但
  刚才可以渲染”。
- `geo_frame_diff` 增加 p50/p90/p99 和逐分量 min/max/mean，明确数值只证明时间依赖，
  不自动证明审美语义。
- guidance 明确 `graph(OUT, direction='up')`、`cook_node`/`describe` 字段边界、单属性
  `geo_attrib_stats` 和固定 framing。节点/数据/时间语义通过而静帧视觉难以裁定细微动态
  时，允许诚实交付“视觉力度待用户播放判断”，禁止无限追图，也禁止伪称视觉确认。
- trace evidence 修复 skill catalog 缺失时误报空列表、记录真实 skill activations，
  并补 exact `save()` 与 mixed verb/raw mutation 检测。

### 2.23 新机启动可观测性 + DSH 版本策略（2026-08-20）

新电脑首次启动时，npx 冷下载、插件 `npm install`、端口等待原本共用一个无限 spinner；
依赖恢复失败或前端命令未创建进程时还有继续轮询 3081 的路径，用户只能看到“永远加载”。

本轮修复：

- 启动面板改为 `环境 → 插件 → 前端 → 服务 → 界面` 五段管线，显示已完成阶段的
  离散百分比、当前动作和真实耗时；npm 未提供下载字节进度，因此不伪造线性百分比。
- worker 在依赖检查/安装、旧进程清理、进程创建、端口就绪时发布状态；依赖失败或
  没创建出 frontend process 立即进入失败态。
- 等待服务 90 秒提示网络诊断，600 秒停止本次进程树并显示“打开日志”；取消也停止
  本轮创建的进程树，不再留下后台下载。
- DSH 默认保留 `npx @deepseek-ai/dsh` 的 npm 发布通道和既有缓存；新增
  `DSH_HOUDINI_DSH_SPEC` 环境变量用于指定待验证的 CLI 根包。2026-08-20 npm `latest`
  为 rc.7、`next` 为 rc.8，本机 rc.7 已监听 3081 并返回 200。实测把已缓存的无版本 spec
  改成 `@rc.7` 会创建新的 npx 缓存项并重新下载，且根包的同族子包仍按 semver 范围
  解析到 rc.8，因此不伪称完整锁定；升级仍需整条 Houdini 链路回归。

### 2.24 Houdini 菜单与版本诊断收敛（2026-08-20）

- 顶级菜单从 `dsh` 改为 `DSH-Houdini`，并因 Houdini XML Unicode 标签兼容问题收敛为
  两个纯 ASCII 子项：`Open Workspace`、`Version & Diagnostics...`。完整重启移动到
  诊断面板的 `Restart Services` 按钮。
- `open_workspace()` 在 3081 健康时只唤起 WebView，保留当前 dsh 会话；服务缺失才走
  完整 launch。重新加载代码或切换 HIP 仍使用明确的重启动作。
- `open_ui()` 移除系统浏览器 fallback：内嵌 WebView 失败时在 Houdini 报错并指向诊断页，
  不再额外打开外部网页。
- 新增 `dsh_manager.py` 原生非模态面板：插件版本/Git revision、DSH 启动规格与本机
  npx 缓存、Bridge/Web 端口状态；只读检查 npm dist-tags 与 origin/main，支持复制安全
  更新命令和打开 `.dsh-web.log`。版本入口不依赖 Web UI，启动失败时仍可用。

## 3. 卡点（blockers）

### ✅ 3.1 静态 client 半的加载方式（已解决）

**根因**（已读源码确认）：dsh 的 client 模块系统 `dsh-client-modules` 通过
`require.resolve(包名 + "/package.json")` 发现插件的 client 半，因此**要求插件以包名加载**；
开发 overlay 的 `file:///...` URL 无法被解析。

**解决**：

1. `dsh plugin --profile web add E:/dsh-houdini`（pnpm link）→ `dsh-houdini` 包名可解析。
2. 新建 `houdini` 模式 preset，其 `dsh-houdini` 行用包名（非 file:// URL）。
3. `standingKeyFor("houdini")` 挂载校验通过。

**已收敛**：`dsh_launcher.py` 的 `start_frontend` 改为 profile 模式（`dsh web --port`，
去掉 `--patch cordis.dev.yml`），preset 是唯一挂 dsh-houdini 的地方；`cordis.dev.yml`
（file:// overlay）退役。

### ✅ 3.2 launcher 冷启动竞态（已修，2026-08-16）

**现象**：`dsh_launcher.launch()` 原顺序是 `start_frontend()` → 立即 `open_ui()`。
npx 冷缓存首次拉取 `@deepseek-ai/dsh` CLI 需数分钟，期间 3081 未监听，但
webview/浏览器已打开 → `ERR_CONNECTION_REFUSED`。进程下完依赖后自己会起来
（实测：手动再起一份同样的命令报 `EADDRINUSE: 3081`，原进程已监听并返回 200）。

**修复**：`launch()` 拆成两步——`start_frontend()` 后调用 `open_ui_when_ready()`：
GUI 下弹一个可取消的 `QProgressDialog` + `QTimer` 每 0.5s 轮询端口（H21 实测
`hou.ui` 无进度对话框 API，用 `hutil.Qt.QtWidgets.QProgressDialog`），就绪才
`open_ui()`。**等待无时间上限**（初版 300s 超时实测不够——npx 冷下载可能更久；
2026-08-16 二次修正），出口是两个：取消按钮 + 前端进程死亡检测（进程退出且
未监听 = 启动失败，报日志路径）。headless 退化为阻塞轮询（同样检测进程死亡）。
前端日志在项目根 `.dsh-web.log`。

**2026-08-17 二次修复（等待期间卡顿的根因）**：spinner 和拖动窗口都卡——实测本机
`connect()` 到**关闭**的 localhost 端口不会立即 RST，而是阻塞到超时（~300ms）。
原实现在 GUI 线程的 tick 里同步探测（30ms 一轮、每轮堵 ~300ms），事件循环被堵死。
修复：前端重启 + 端口轮询整体挪进 worker 线程（`_start_and_wait_frontend`），
GUI 线程的 tick 只转动画 + 读标志位；`QProgressDialog` 同时换自绘 `QDialog` +
QPainter 圆弧 spinner。

**2026-08-20 三次修复（新机无限等待）**：上述“无时间上限”策略改为 600 秒上限；
无限 spinner 改为阶段百分比面板，并为退出、超时、依赖失败提供明确错误态和日志入口。

---

## 4. 决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | 动词拆两层：`list_parms`（导航）+ `read_parms`（意图） | 两个语义动作，合并会互相污染 |
| 2 | 动词是「shell 里的命令词汇」，tool 是「agent 的 API 面」 | 层级不同；动词活在 `houdini_exec` code 内 |
| 3 | 拓扑独立成 `graph`，不塞进 `find_nodes` | 先扁平清单、再按需放大，避免 token 爆炸 |
| 4 | `hou.Node` 统一引用约定（`_resolve` 接受 Node/path） | 让词表「像一门语言」 |
| 5 | 「trace」= `dsh-client-ui-trajectory` 的轨迹视图 | 查包源码 + `conversation.view` Slot 契约确认 |
| 6 | verb 追踪走**运行时 tracer**，不解析 code 字符串 | code 字符串无真实入参/出参/成败 |
| 7 | client 半手写 CJS factory，不引入 bundler | 匹配 `__ModuleLoader__.load` 约定，最小改动 |
| 8 | plugin 去 persona 化，身份归 preset | 组合包=能力层（中性）、preset=模式层（persona）；否则污染其它模式 |
| 9 | 两模式：`houdini`（用）+ `houdini-dev`（开发），差别只在 persona | 工具集相同（都继承 standard），身份不同 |
| 10 | bundle / profile / preset 三层区分 | 官方文档：bundle 是分发的能力包、profile 是宿主组合、preset 是会话模式 |
| 11 | 图片结果走 `ctx.attachments.saveImage` + 模态校验 | 规范禁止裸 base64；会话日志只存 `sha256:` 引用（§6） |
| 12 | Skill 走 `ctx.skills.register()` 编程注册 | npm 包目录不在 skill 默认发现根，文件发现路走不通（§6） |
| 13 | agent 产出锚定 `$HIP`（Houdini 工程目录），不用 dsh workspace，也不造 `dsh-houdini/` 混合子目录 | workspace 只是 shell/fs 工具的 cwd，不该污染插件仓库；`render/`/`geo/` 子目录是 Houdini 工程惯例，与管道预期一致；规则写进 preset persona（2026-08-16，自行车会话把 hip/png 存进了插件仓库的教训） |
| 14 | 动词 = PRIMARY interface，裸 `hou` 仅逃生舱，边界写进 GUIDANCE | 「prefer」措辞约束力不足（§2.7-1、§2.8 trace 复盘）；明示分工边界才有效 |
| 15 | 裸 hou 检测走 AST 静态扫描，不走正则 | 注释/字符串里的同名文本会误报；语法错误可静默跳过 |
| 16 | GUI 线程零阻塞：socket 探测 / 进程等待 / netstat 全在 worker 线程 | 实测本机 connect 关闭端口阻塞 ~300ms，GUI tick 里探测 = 事件循环堵死（§3.2 二次修复） |
| 17 | preset 同步收进 launcher（`sync_presets`），不再靠手动 Copy-Item | 提示词迭代是高频动作，手动步骤必被遗忘（2026-08-17 改 persona 后未生效的实测） |
| 18 | HDA 参数面板走声明式整组重建，不做增量 merge | OTL trace 中增量 remove/append 造成 folder_init2、残参散落，6 次调用后只能推倒重建 |
| 19 | HDA conditional 必须提交后读回验证，丢失才补 DialogScript | H21 实测 API `setConditional` 可在 `setParmTemplateGroup` 后静默消失；只信“调用成功”会把返工推给用户 |
| 20 | HDA replace 永不覆盖原生类型，definition 用 `destroy()` 精确删除 | uninstall 整个 HDA 文件会连带同库其它定义；原生 subnet 的 instances 更绝不能按同名 HDA 替换语义销毁 |
| 21 | trace 审计走“确定性 evidence + Houdini 领域裁判”，不按调用频率直接改词表 | 频率分不清不适用和该用未用；节点模块、局部几何、cook/显示/动画需要语义证据，删除工具还需跨 trace 反例分析 |

---

## 5. 下一步（分阶段计划，2026-08-16 按 dsh 官方规范重排）

> 规范依据见 §6；与 `tool-design.md` §7 的技术项（batch 端点、undo group、
> `scene_*`/`viewport_*` 域；`hda_*` 已于 §2.19 落地）互补，可穿插进行。

### Phase 0 — 收尾与稳定性

1. ✅ 修 launcher 冷启动竞态（§3.2）：等 3081 就绪再开 UI（QProgressDialog + QTimer）。
2. ✅ 端到端验证（自行车会话，见 §2.7）：preset 身份正确、工具链路全通、
   `houdinitrace` 未显示的根因已修（exports 缺 `./package.json`）；verbs 缺席的根因
   是**模型不用动词**（guidance 已注入但被忽略），非管道断裂——转化为 Phase 1 第 8 项。
3. ✅ 新增 `houdini-dev` preset（`presets/houdini-dev/`：standard 工具集 + dsh-houdini + coding persona，用于开发/测试；已 `standingKeyFor('houdini-dev')` 校验通过）。
4. ⏳ 「Houdini 菜单打开默认切到 houdini 模式」：查 default preset / 深链（`dsh web` 无 `--preset` flag）。
5. ✅ P0 修 `render_view`（§2.21）：proxy isolation + 保存/恢复 OBJ 可见性，agent camera/target 不抢用户对象；
   确定性 headlight/geometry color；增加 detail/coverage 构图并返回 eye/direction。
6. ✅ P0 修 display 契约（§2.21）：SOP 是 singular display child，OBJ 是 plural visibility；
   `display_node('/obj')` 不得调用不存在的 `displayNode()`。
7. ✅ P1 几何自省补 local/piece extent（§2.21，识别“全场 bbox 正常但每个实例宽度为 0”）；
   动画任务 guidance 增加 A/B 完成门，`render_check` diff 提高精度并给非零像素比例。

### Phase 1 — 合规对齐（不改行为，只贴规范）

5. ⏳ devDependency `dsh-tools` 对齐运行时 `0.1.0-rc.6`（消除 schema DSL 漂移风险）。
6. ⏳ 5 个工具补 `presentCall`/`presentResult`（terminal/generic 卡片）+ `presentationMeta`
   （§6 硬约束：必须是 args 的纯函数，UI 格式不进模型结果）。
7. ⏳ TS 侧最小测试（现状仅 Python 侧 `houdini/tests/regress_verbs.py`）。
8. ✅ 提升动词采用率（§2.8，2026-08-17）：GUIDANCE 改「动词 = 主接口 / hou = 逃生舱」
   + persona 程序化生成原则 + 桥侧 AST 裸 hou advisory（比原设想的 createNode 检测更通用）。

### Phase 2 — 视觉反馈闭环（README 路线 #1）

8. ✅ 2026-08-19 已实现且实测走通，形态与原设想不同：`render_view`（OpenGL ROP
   离屏验证，不碰用户视口）+ media relay（图片字节经桥 `/media` 回传工作区，
   vision/fs 可读）——比 `/screenshot` + image 内容块更简单且对有/无视觉模型
   都成立。草地重跑 4.5min/11 调用收尾（§2.18）。

### Phase 3 — 迁移官方 jobs 服务（README 路线 #2）

9. ⏳ `houdini_job_*` 迁到 `ctx.jobs`（§6 红线），获得 `job_list`/`job_kill`/`job_output`
   + 完成通知；桥侧 job 端点退役。迁移前的小改：`houdini_job_status` 加
   `wait`/`timeout_ms` 长轮询参数（§2.7-3 的 loop guard 误报，对齐 `job_output` 形态）。

### Phase 4 — 权限分层（README 路线 #4）

10. ⏳ `tools/pre-execute` 小插件：`houdini_query*` → `next()`，`houdini_exec*` → `ask`（§6 约束）。

### Phase 5 — 卡片与知识沉淀

11. ⏳ houdinitrace 视图升级：纯文本块 → 结构化表格（状态色标 + 展开入参/出参）；
    优先 host 半渲染意图，不够再写 client 半 keyed renderer（`'tool.call.toolview'` slot）。
12. ✅ `ctx.skills.register()` 打包首个 `houdini-trace-analysis`（§2.20）。
13. ✅ `houdini-sop-workflow`（§2.21：SOP/VEX/Copy/属性/模块验证）；与 trace 审计量表分离。

---

## 6. dsh 官方规范基线（2026-08-16 调研）

> 来源：本机 `Z:/EEE_Project/deepseek-harness` 克隆。权威文档：
> `docs/cookbook/adding-a-tool.zh.md`、`docs/cookbook/extension-cookbook.zh.md`、
> `docs/user/develop/basic/`、各包 README（jobs / skill / tool-fs / client-modules）。
> 注意：`guide/quickstart`（使用 Web UI）是终端用户页，**不含外部插件要求**，别去那里找。

### 已符合（不需动）

- 插件形状 `name` / `inject` / `Config` / `apply`；ESM；Config 是 Schemastery schema（非普通对象）。
- `dsh.bundle.patch` 按包名引用；client 半 `dsh.client` + `exports["./client"]` +
  factory-form bundle（副作用全在 factory 闭包内，装载时只注册工厂）。

### 缺口与硬约束（后续开发必须遵守）

| 主题 | 规范要点 | 出处 |
|---|---|---|
| 展示意图 | `presentCall`/`presentResult`/`presentationMeta` 必须是 args 的**纯函数**（无 I/O/时钟/会话状态，否则破坏日志回放）；UI 格式不进模型结果；卡片类型只有 generic/terminal/diff/search/web，**无 image 卡片** | `cookbook/adding-a-tool.zh.md`、`packages/core/tools/src/presentation.ts` |
| 图片结果 | 不能塞裸 base64：先 `ctx.attachments.saveImage()` 拿内容寻址引用，`output.render` 返回 `{type:'image', attachment}` 块；执行前校验模型路由 `inputModalities` 含 image，否则拒绝（**DeepSeek 官方模型目前多为纯文本路由**，此限制要写进插件文档） | `packages/fs/tool-fs/src/read-image.ts` |
| jobs 迁移 | 软依赖 `ctx.get('jobs')`，缺失时响亮报错；`declare module` 合并 `JobKindMap` 加 `'houdini'`；`start()` 发布 id 后用任务自己的取消信号，**不再用 `exec.signal`**；组合需 `dsh-jobs-local` + `dsh-tool-jobs`（后者才提供 `job_list`/`job_kill`/`job_output`，缺它 agent 无法启动后台工作） | `packages/jobs/*/README`、`cookbook/adding-a-tool.zh.md` |
| 权限分层 | `tools/pre-execute` 是 waterfall：放行必须 `return next()`（直接 return 会短路全链）；审批请求只带工具名/原因**不带参数** → 分层按工具名做；只有一次性授权（allowed-once），无 allow-always；要单调拒绝用 `ctx.tools.guard()` | `cookbook/extension-cookbook.zh.md`、`packages/interaction/user-approval/README` |
| Skill 发布 | npm 包目录**不在** skill 默认发现根（发现根是 `.dsh/skills`、`.agents/skills`、`$DSH_HOME/skills` 等）；随插件发布必须走 `ctx.skills.register()` 编程注册（参考 `skill-badge`）；模型侧曝光需组合挂 `dsh-tool-skill` | `packages/skill/*/README` |
| 发布/安装 | profile manifest 由 `dsh plugin` 维护，**不要手写**；patch 替换目标行的整个 `config`（非深合并），覆盖别人行时必须重述全部键 | `develop/basic/publish` |

---

## 7. 文件清单

| 文件 | 职责 |
|---|---|
| `src/index.ts` | host 入口：注册工具 + systemPrompt guidance |
| `src/tools.ts` | 5 个工具定义 + `verbs`/`advisory` 渲染 |
| `src/bridge.ts` | HTTP client（`ExecResult.verbs`/`advisory`） |
| `src/skill.ts` | 随包注册 trace-analysis + SOP-workflow 两个 skill/resource base |
| `client.js` | **client 半**：手写 factory，注册 `houdinitrace` 视图（词表目录 + 实时时序，目录由生成器注入） |
| `package.json` | `exports["./client"]` + `dsh.client` + `dsh.bundle.patch` |
| `cordis.patch.yml` | 组合包 patch 层（`dsh.bundle.patch`，包名加载） |
| `houdini/python3.11libs/dsh_bridge.py` | 桥 + 动词注入 + tracer |
| `houdini/python3.11libs/dsh_hou_helpers.py` | 38 个 helper 主动词 + 2 display 兼容入口 + `_resolve`；bridge 另注入 `verb_help` |
| `houdini/tests/regress_hda_verbs.py` | HDA authoring 独立回归（不经过已知会触发 VEX 栈溢出的旧 t15） |
| `houdini/tests/regress_scene_geometry_verbs.py` | scene/display/piece/frame/layout/diff/spare headless 回归 |
| `houdini/tests/regress_visual_gui.py` | explicit SOP proxy、用户 display 漂移与状态恢复 GUI 回归 |
| `houdini/python3.11libs/dsh_launcher.py` | 打开/重启分流 + preset 同步 + 分阶段百分比/超时诊断（worker 线程探测） |
| `houdini/python3.11libs/dsh_manager.py` | Houdini 原生版本/端口诊断 + npm/Git 只读更新检查 |
| `houdini/python3.11libs/dsh_webview.py` | 内嵌 Web UI（QWebEngineView）+ 窗口置前 + backdrop-filter 性能修复注入（§2.13） |
| `docs/tool-design.md` | 设计宪法 |
| `docs/development.md` | 本文：进度 + 卡点 |
| `tools/trace-report.mjs` | trace 复盘报告生成器（session → 单文件 HTML，§2.14） |
| `tools/catalog-lib.mjs` | 词表目录解析唯一实现（trace-report 与生成器共用） |
| `tools/trace-session-lib.mjs` | session.jsonl.zstd 多帧解压/事件读取唯一实现 |
| `tools/gen-client-catalog.mjs` | 构建期把目录注入 client.js（`npm run build` 第一步，§2.15） |
| `skills/houdini-trace-analysis/` | 标准 trace 审计 skill：证据脚本 + 量表 + 累积模式库 |
| `skills/houdini-sop-workflow/` | SOP/VEX/Copy/属性/模块验证与多帧交付工作流 skill |
| `presets/houdini/` | houdini 模式 preset 模板（persona + dsh-houdini 行） |

---

## 附录：dsh 插件规范要点（本项目踩过的坑）

- **插件形状**：`export const name` / `export const inject` /
  `export interface Config` + `export const Config: Schema<Config>` / `export function apply(ctx, config)`。
- **host/client 半**：host 在 Node 进程（工具/服务），client 在浏览器（Slot/主题/页面状态）；
  二者通过 `harness.handle` + `host.call` 传**纯 JSON**。
- **client 半声明**：`package.json` 需 `dsh.client: { platform: "web", inject: [...] }`
  且 `exports["./client"]` 指向 client bundle；**`exports` 还必须含 `"./package.json"`**——
  client-modules 靠 `require.resolve(包名/package.json)` 读 `dsh.client` 声明，一旦定义了
  `exports` 白名单却没列出它，解析直接 `ERR_PACKAGE_PATH_NOT_EXPORTED`，client 半静默 404
  （2026-08-16 实测，官方包全部带此行）。bundle 必须以
  `window.__ModuleLoader__.load({ id: 包名, factory: (require) => exports })` 注册，
  `require(...)` 只解析 seed word（`react` 等）/ boot graph 行，**不得**跨插件 import 业务值。
- **会话日志分析**：`session.jsonl.zstd` 是**多帧拼接**（每次追加写一帧），Node
  `zlib.zstdDecompressSync` 只解第一帧——按魔数 `28 B5 2F FD` 切帧逐段解压；解压产物
  **不能放进 session 目录**（`.jsonl` 与 zstd 后端编码冲突，webserver 会拒绝启动，2026-08-16 实测）。
- **Slot**：`ctx.get('slots')`（可选依赖）+ `slots.inject(key, () => slots.register(opts, Component))`；
  视图注册进 `conversation.view`（`{id, order, label}`），组件经标准 prop `useSession` 读快照。
- **纯 JS**：client/host 代码不做 TS/JSX 变换（本项目静态 client 因此手写 JS factory）。
- **生命周期**：所有副作用（Service/Event/Tool/Slot/样式/定时器）必须挂到当前 Fiber，
  停用/更新时自动清理。
- **三层角色（bundle / profile / preset）**：
  - 组合包（bundle）= npm 包，`dsh.bundle.patch` 贡献 patch 层，是「分发的能力」；
  - profile = `$DSH_HOME/profiles/<name>`，`dsh.profile.bundles` 描述可启动的宿主组合；
  - agent preset = 每个会话的模式（persona + 挂哪些工具），在 `~/.dsh/.agent-presets/<id>/`。
  - 原则：**plugin（能力层）persona 中性，模式身份（persona/上下文）归 preset**。
- 官方文档：<https://deepseek-harness.github.io/deepseek-harness/develop/basic/>（基础）、
  <https://deepseek-harness.github.io/deepseek-harness/develop/basic/publish>（打包/安装）、
  <https://deepseek-harness.github.io/deepseek-harness/develop/practice/>（能力的三种角色）。
