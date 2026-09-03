# dsh-houdini 开发进度与卡点

> 本文是 dsh-houdini 的**开发进度日志**，随开发同步维护（改了代码就顺手更新本文）。
> 设计宪法见 [`tool-design.md`](./tool-design.md)（动词词表、两轴模型、铁律、帮助文档三阶段）。
> §2 与 §4 保留当时的版本号、菜单名和实验结论作为历史证据；当前运行方式以 §1、§5、
> [`README.md`](../README.md) 与 [`setup.md`](./setup.md) 为准，不把历史措辞当作现行操作说明。
>
> 状态图例：✅ 完成 · 🔶 进行中 · ⛔ 卡点 · ⏳ 待办

---

## 1. 现状总览

| 模块 | 状态 | 关键产物 |
|---|---|---|
| 工具（host half） | ✅ | 5 个 `houdini_*` 工具 |
| 动词词表（bridge namespace） | ✅ | 49 个目录入口：47 个主动词（含 `verb_help`）+ 2 个 display 兼容入口；文档/Host/Bridge 三方契约测试 |
| 动词追踪 tracer（Phase 1） | ✅ 已激活（2026-08-17 会话实测 `verbs (N)` 段回传） | `verbs` 字段 + `[verb]` stdout 行 |
| 裸 hou advisory | ✅ | AST 观察层继续记录已覆盖裸调用与仓库写入风险 |
| raw-hou gate | ✅ 默认开启；已覆盖调用不可旁路 | 执行前 AST 拦截 + 低层缺口单次豁免；`dict.setdefault` 只读误伤已修（§2.17 / §2.36） |
| launcher：preset 同步 + 分阶段百分比 + 超时/日志诊断 | ✅ | `dsh_launcher.py`（§2.23 / §3.2） |
| 版本与诊断面板 | ✅ 双通道版本状态 + 安全激活 | `dsh_manager.py`（§2.24 / §2.33） |
| Houdini Trace 视图（Phase 2） | ✅ 已重写：全量调用 + 裸 hou hint 可见（§2.9） | `client.js` + `dsh.client` 声明 |
| Houdini trace 审计 skill | ✅（§2.20 / §2.36） | evidence schema v2：真实 adoption 指标 + vision semantic outcome + 完成风险 |
| Solaris/Karma workflow skill | ✅（§2.25） | `houdini-solaris-karma-workflow` + 版本化 Karma/MaterialX/COP 接口参考 |
| Rig/animation workflow skill | ✅（§2.26） | channel / packed pieces / KineFX skin / APEX 路由与完成门 |
| Houdini skill 治理 | ✅（§2.27） | `houdini-skill-governance` + evidence ingestion / lifecycle / deterministic audit |
| plugin persona 中性化 | ✅ | GUIDANCE 只保留稳定契约，目录由 `tool-design.md` 生成；身份/工作方式归 preset，领域 recipe 归 skill |
| houdini 模式 preset | ✅ | `~/.dsh/.agent-presets/houdini/` + `presets/houdini/`，校验通过 |
| houdini-dev 模式 preset（开发） | ✅ | `~/.dsh/.agent-presets/houdini-dev/` + `presets/houdini-dev/`，`standingKeyFor` 校验通过 |
| Houdini 侧一键启动/桥/WebView | ✅ | `dsh_launcher.py`（profile 模式）等 |
| GUI 启动线程边界 | 🔶 WebView/launcher 阻塞 preflight 已迁 worker；待完整重启 GUI smoke | QWebEngine async retry + launcher worker listener/PID preflight；普通 Open 不杀现有 Bridge |
| 视觉产图/relay/证据判定 | ✅ vision-toolkit 0.1.7 生产化 | 按需 skill 激活 10 个工具；本机 DashScope 配置保留；旧 router/fallback 退役；render_view/media 与语义失败识别可用（§2.35–§2.39） |
| Host / Bridge 词表握手 | ✅ 49 动词 live 验证；当前 Host 小修待 reload | 场景执行前比较独立 SHA-256，版本漂移 fail-closed；内部 `$HIP` probe 已强制 read-only |
| B0 评测协议 | ✅ 已冻结并跑完正式矩阵 | Protocol `b0-2026-09-02-v4`；brief/answers/seed/evaluation + run 交叉校验全通过；3×2 calibration 6/6 completed |
| 跨域质量闭环 | 🔶 B2 归因已记录（§10），B3/B4 待启动 | 6/6 coreSuccess、0 hard failure、0 泄漏；B3 候选五项按门槛标注；holdout 未解封 |

---

## 2. 已完成

### 2.1 工具（host half）

`src/index.ts` → `lib/index.js`，Cordis 插件形状 `{ name, inject, Config, apply }`：

- `name = 'dsh-houdini'`，`inject = ['tools', 'systemPrompt', 'skills']`
- 注册 5 个工具：`houdini_exec` / `houdini_query` / `houdini_job_submit` /
  `houdini_job_status` / `houdini_job_cancel`（见 `src/tools.ts`）
- 系统提示词 guidance 段（order 150，**persona 中性**）：只讲工具用法（动词词表、`hou` 预导入、桥报错），不含「你正在驱动 Houdini」的身份——身份归 preset

### 2.2 动词词表（bridge namespace）

`houdini/python3.11libs/dsh_hou_helpers.py` 定义、`dsh_bridge.py` 注入 exec 命名空间：
45 个主目录动词 = vocabulary（`verb_help`）+ scene（info/timeline/bookmark 5 个）+ 类型目录（`search_tab_menu`/`search_tab_entries`/`resolve_latest_type`）+ node 域
（原 node CRUD + SOP output/OBJ visibility 拆分 + `layout_nodes` + 兼容 display wrappers）
+ parm 域（`list_parms`/`read_parms`/`set_parm`/`set_parms`/`create_spare_parms`）
+ asset 域（`hda_create`/`hda_info`/`hda_get_section`/`hda_set_section`/
`hda_patch_section`/`hda_set_interface`）
+ geometry 域（`geo_attrib_stats`/`geo_piece_stats`/`geo_frame_diff`）
+ stage/USD 域（`usd_stage_summary`/`usd_prim_info`）+ render/sim 域（`render_frame`/`render_check`）
+ viewport 域（`viewport_screenshot`）+ 视觉验证主干（`render_view`）。
bridge 另保留旧 `set_display/display_node` 两个兼容 wrapper：不进 guidance 主词表，
但留在独立 compatibility catalog 域以诚实回放历史 trace。

### 2.3 动词追踪 tracer（Phase 1）—— 已实现并激活

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
（拦截/只读放行/豁免放行+留痕/拦疑似修改）。**历史实验用法**：当时从 DSH-Houdini
菜单重启桥后，还需在 Python Shell `import dsh_bridge; dsh_bridge.set_raw_gate(True)`；
观察豁免记录 → 补缺口（首个候选 `create_parm`）→ 逐步收紧。

**2026-08-23 生产收紧**：session `c6481bf1` 在 46 个动词和两个 workflow skill
均已曝光的前提下仍产生 20/20 纯裸 Houdini 调用；16 个 mutation exec 连续收到 advisory
仍未切换，证明默认关闭的实验 gate 是 fail-open。桥现默认开启，重启恢复开启；
`allow_raw` 只放行未覆盖的低层修改，不能旁路 `createNode/parm().set/cook/destroy` 等已覆盖
调用，低层几何必须与外层 scene operation 分 batch。`setPosition` 因 receiver 可为
GeoPoint，不再错误映射成 `layout_nodes`。工具 schema/guidance 同步真实契约。

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

**2026-08-21 warm-start 超时纠正**：用户点击更新/重启后 3081 始终未监听；外层 `cmd.exe`
和 `npx-cli.js` 都存活且无输出，launcher 因而把 npm registry/cache 解析死等误判成“仍在
启动”，直至 600 秒。同期 `.dsh-web.log` 是追加文件，顶部/中部历史
`Cannot find package '@deepseek-ai/schemastery'` 没有尝试边界；本次实际检查中依赖目录存在，
从 HIP 工作区直接导入 `E:/dsh-houdini/lib/index.js` 成功，所以不能把历史错误当成本次根因。

- 默认 spec 且 project-local npx cache 已有有效 `@deepseek-ai/dsh/lib/bin.js` 时，launcher
  直接以 Node 执行该 CLI（`shell=False`），不再让 warm start 接触 npm registry；60 秒未
  监听即停止。只有首次无缓存或显式 `DSH_HOUDINI_DSH_SPEC` 才走 npx，保留 600 秒冷下载。
  `DSH_HOUDINI_DSH_BIN` 可显式固定已有 CLI，版本更新通道没有被取消。
- `ensure_dependencies()` 从“两个目录存在”升级为 Node ESM 真实导入编译后插件；只有明确
  module-resolution 失败才运行 npm install，语法/插件初始化错误直接失败，避免无意义联网。
- `.dsh-web.log` 每次启动写 timestamp/source/cwd/timeout/command 分隔头；进程早退记录 exit
  code，GUI 按实际 60/600 秒显示原因，不再统一报“10 分钟”。
- 新增 `houdini/tests/regress_launcher.py`。H21 hython 十一项回归通过；实际 warm 启动约 4 秒
  达到 ready，`3081` 持续监听，HTTP 返回 200，cwd=`E:/tmp/test3`，source=`cached-cli`。

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

### 2.25 Karma 续跑 trace：Tab 菜单真实性与领域知识分层（2026-08-21，已完成）

用户在 `session-71d76525` 的草地任务后追加“拿到 Karma 里去渲染”。单帧最终成功，
但网络使用 Material Library 根层直接创建的 `principledshader` 和一体式 `karma` LOP；
H21 用户真实 Tab 菜单中的标准入口应是 **Karma Material Builder** 与
**Karma (Setup)**（后者同步创建 Karma Render Settings + USD Render ROP）。这次问题
不是一句“优先 Karma”的 prompt 缺失：preset 已要求 LOP/Material Library/Karma，agent
也在调用 #51 搜到 `karmarendersettings`，但当前目录只枚举 node type、没有 setup tool，
`tab_create` 又会 fallback 到 `createNode()` 绕过 Material Library 的 tab mask。

**确定性事实**：

- 第二个渲染请求实际有 58 个唯一 tool call、97 个 verb call、5 个硬失败；整条 session
  实际 108 个唯一 tool call。当前 evidence 报 116，是 compaction 在 seq 22231–22245
  重放 8 个历史 `tool/result`，脚本没有按 callId 去重。
- H21.0.440 本机 `ExtraLopTools.shelf` 的 `lop_karma_setup` 创建
  `karmarenderproperties::2.0`（名 `karmarendersettings`）+ `usdrender_rop`，并设置
  render settings、motion blur、CPU/XPU renderer 表达式。
- `ExtraTools.shelf` 的 `vop_karmamtlxsubnet` 调用 `createMaskedMtlXSubnet`；内部默认有
  MtlX Standard Surface、displacement、Karma Material Properties、outputs/AOV 节点及
  `outputs:kma` render context。传统 Principled 即使经 preview 转换出图，也不能证明
  XPU/当前 Material Library 工作流正确。
- trace 只渲染 Karma frame 25；`authortimesamples=always` 和 SOP 时序数据不能替代最终
  Karma A/B，因此最终“1–240 麦浪序列已验证”属于证据外推。

**按第一性原理分层，不把整本 Karma 手册注入 system prompt**：

1. P0 evidence：tool result 以 callId 去重，replay 单列 diagnostics；本 trace 固化回归。
2. P0 Tab 地基：查询以 parent 为主、区分 node/tool；单节点 `tab_create` 与多节点 setup
   tool 执行拆分；后者初期 allowlist 非交互工具并返回所有新增节点/连线/状态恢复。
3. P1 USD 自省：stage summary + prim detail，覆盖 material context/binding、camera/light、
   RenderSettings/Product/Var、time samples；停止反复猜 Pixar USD API。
4. P1 render 边界：`render_frame` 只接受可执行 ROP；LOP 在提交 job 前报可操作错误。
5. P1 新增 `houdini-solaris-karma-workflow`：承载 CPU/XPU/MaterialX、SOP Import、材质
   绑定、灯光、Karma Setup、AOV/产物和动画完成门。常驻 guidance 只负责触发 skill 与
   “不得绕过 parent Tab 过滤”的短不变量。
6. P2 Copernicus：先复用 parent-aware Tab/setup/USD 地基；等材质、bake、slap comp 三类
   真实 trace 后再决定 COP 专用自省/保存动词，不先堆节点名。

**第一批验收**：H21 GUI 空 `/stage` 上发现并执行 `lop_karma_setup`，得到两个标准节点及
官方表达式；Material Library 内执行 `vop_karmamtlxsubnet`，得到标准内部网络；strict
Tab 创建拒绝当前 parent 不可见的 Principled；USD Render ROP 经 `render_frame` 出图且
恢复 frame。H22 保留同一语义回归，允许具体 type/version/tool id 不同。

**2026-08-21 首批实现进度**：

- ✅ evidence/report 共享 `uniqueToolResultEvents`；当前 session 回归
  108 calls / 232 verbs / 8 replays，另有纯事件单测。
- ✅ 正式目录 41→45（43 主动词 + 2 compatibility）：新增 `search_tab_entries`、
  `tab_apply`、`usd_stage_summary`、`usd_prim_info`；`tab_create` 拒绝 hidden/deprecated
  与 Material Library 根层直建 shader；`render_frame` 普通 LOP 预检。
- ✅ H21 headless scene/geometry 回归 11/11，HDA 回归全绿；`npm run build` 生成
  11 domains / 45 verbs；新 Solaris/Karma skill 通过 quick_validate。
- ✅ H21 GUI 已按两个 shipped tool 的真实 context/recipe 执行非交互 adapter：Karma Setup 创建
  `karmarendersettings + usdrender_rop` 与三条官方表达式；Karma Material Builder
  内部节点、tab mask、`kma` context 均通过。独立测试使用 `/obj` 下 disposable LOP
  Network，不碰用户 `/stage`。
- ✅ 重启后 GUI 复验完成：同一 exec 连续应用 Karma Setup + Material Builder 时共享首个
  用户 pwd/current/selection 基线，SideFX 节点创建的 deferred selection 通过 Houdini
  两阶段 event callback 最终恢复；`regress_solaris_gui.py` 全部通过且无 probe 残留。
- ✅ 标准 USD Render ROP 实际出图：发现并修复 `render_frame` 先命中 `lopoutput`（USD）
  而非 `outputimage`（图像）、以及未临时启用 `soho_foreground` 的两个契约 bug。H21 用
  已有草地 stage 在 frame 25 渲出 88,133-byte PNG，3.77 秒、errors 空；frame 128 与
  foreground=0 恢复，临时 settings/ROP 和测试 PNG 均已清理。

### 2.26 魔方 trace：Rig / Animation 第一性原理路线（2026-08-21，计划已拍板）

`session-a41c853a` 用 66 个 tool call / 251 个 verb call 创建魔方并保存 HIP；静态模型、
54 个贴纸点、单个 R 层中间转动和固定相机 A/B 成立。但最终 wrangle 永远按初始
`gx/gy/gz` 叠加六个绝对角度，不能表达非交换的连续魔方状态；frame 1/220 相同只是所有
通道归零，不证明逆序还原。视觉只覆盖 frame 25/31，却外推为 16 步全部通过。

本次不按魔方任务加专用补丁，也不把 KineFX/APEX 手册注入 system prompt。SideFX 官方
资料与本机 H21 help 共同确认：channel、packed/Transform Pieces、KineFX skeleton/skin、
APEX rig graph 分别解决不同数据模型；“绑定”必须先分类。完整事实、假设、约束、路由矩阵、
工具预算、分阶段计划与第一验证见 [rig-animation-design.md](rig-animation-design.md)。

拍板边界：

1. 新增 `houdini-rig-animation-workflow` 承载领域路由/官方模式/完成门；常驻 guidance 只放
   skill dispatch 与“路径依赖序列必须验证状态迁移/非交换转折”两个短不变量。
2. 第一批最多新增一个通用动词：候选 `set_keyframes`；先扩展 `read_parms` 动画摘要与
   `create_spare_parms` 显式 controller spec，修搜索、advisory、evidence，不增平行动词。
3. 不新增 `rubik_*`、`piece_*`、`kinefx_*`、`apex_*`；KineFX/APEX 先走真实 Tab + 现有
   primitive + skill，等多任务 trace 证明 setup 封装必要后再议。
4. 第一验证不是再渲染当前第一步，而是 H21 disposable HIP 的 R→U 非交换 packed-piece
   基准：第二步必须使用 R 后 logical state，inverse 后逐 piece transform 恢复。
5. 当前 online 文档以 H22 为主；运行时类型/recipe 以 H21/H22 各自 Tab 与本机 help 为准。

计划状态：Phase A/B 与 H21/H22 Phase C 三类基准已完成；当时正式 catalog 为 46 verbs
（44 主动词 + 2 compatibility；§2.34 后为 47）。正确 Houdini session 的 46/46 verbs、5/5 skills 曝光和
ordered 魔方固定构图 GUI A/B 和 H21/H22 APEX evaluation 均已通过；剩余发布门是更多真实用户 trace。

**2026-08-21 Batch A 实现进度**：

- ✅ `evidence-helpers.mjs` 统一 batch/validation coverage；同节点唯一 parm 才算 batch，
  魔方 trace 误报清零；JSON/HTML 同时报 geometry `[1,25,31,121,220]`、render/vision
  `[25,31]`，不再隐藏验证覆盖缺口。
- ✅ `search_tab_menu` 同时匹配 internal name、base、operator label 的原始/紧凑 token；
  `copy to points` 命中 `copytopoints`。Repo advisory 将过宽 `render/save/dump` 文本收窄为
  实际写调用；relay `render_check` 只读不报警，真实 repo write 仍报警。
- ✅ Governance `GOV-001` 建立 observable dry-run：必须 UPDATE trace/确定性 bug、保留
  rig/`set_keyframes` 为 candidate、NO_CHANGE COP/SIM/tool catalog；本批实际副作用符合。
- ✅ 新增 `regress_rig_state_model.py`：H21.0.440 6/6。27 个 packed pieces 显式 Attribute
  Copy point `name` 后交给 Transform Pieces；正确 R→U 更新 logical membership，错误绝对
  通道使用 initial membership，两者第二步分叉；两者最终都回 rest。轴心 piece 仅 orient
  变化，证明 P diff 单独不足。
- ✅ HTA-017 从 S1 候选升级为 S2 确认；暂不新增 piece-state verb，现有
  `geo_frame_diff(P)` + `geo_frame_diff(orient)` 已覆盖基准。
- Batch A 结束时，rig/animation skill 与 `set_keyframes` 尚未发布；该历史状态已由下面
  Batch B 取代。跨批次一直未完成的是 Restart Services + 新 DSH session 曝光门。

**2026-08-21 Batch B 实现进度**：

- ✅ H21 channel/KineFX foundation 7/7：`constant/linear/bezier`、frame 单位、3-joint
  name/topology/transform、Rig Pose、boneCapture、Joint Deform 多帧。
- ✅ 正式新增 `set_keyframes`（唯一新 verb）；`read_parms` 动画摘要；
  `create_spare_parms(spec=...)` controller interface。桥注册/raw advisory/guidance/
  `tool-design.md`/README/catalog 同步，build 生成 11 domains / 46 verbs。
- ✅ `houdini-rig-animation-workflow` + reference 已注册；governance audit 现为 5 skills /
  5 registrations / 0 issue / 0 warning。
- ✅ 原 `E:/tmp/test3/魔方.hip` 保持 212,197 bytes / 14:02:40；新副本
  `E:/tmp/test3/魔方_ordered_rig.hip` 235,770 bytes，`OUT_ORDERED` 保存。重开验证：27
  packed pieces；first P/orient 非零；scramble P max 2.828；loop P/orient 约 1e-32。
- ✅ packed attribute class 规则细化：Copy-to-Points packed instances 与展开 polygon→Pack
  的 name class 不同；Pack warning 不得忽略。
- ✅ H22.0.368 / Python 3.13：animation foundation 7/7、rig state 6/6、scene/geometry
  11/11；新 verb/skill 的跨 ABI 基线成立。
- 该批结束时仍待 Restart/session/GUI/APEX；其中 Restart、46 verbs / 5 skills 曝光与 GUI
  render/vision 与 APEX graph evaluation 已在后续验收完成，当前只剩更多真实任务。

**2026-08-21 部署态 agent 验收**：

- ✅ Restart 后 live bridge 的 `verb_help('set_keyframes')` 返回新签名/文档；Web 200。
- ⚠️ 用户从 UI 新建的空 session `session-bab6df3b...` 实际 `agentPreset='cordis'`，不是
  Houdini；确认 Phase 0“菜单打开默认切 Houdini 模式”仍是产品缺口，不能用该 session
  验证插件。
- ✅ 通过正式 Host RPC `session.create(cwd='E:/tmp/test3', agentPreset='houdini')` 创建
  `session-8fe0e669...`，再用 `session.prompt` 投递只读测试；不是直接写 session 文件。
- ✅ 新会话 system reminder 精确列出 5 个 Houdini skills；agent 成功加载
  `houdini-rig-animation-workflow`，只调用 1 次 `houdini_query`，其中使用
  `verb_help('set_keyframes') + scene_info()`；0 mutation / 0 failure / 0 rollback / 0 advisory，
  最终正确解释 channel 与 ordered pieces/KineFX 边界。
- ✅ Evidence 新增 `skillCatalogSnapshots`：skill catalog 实际位于 plugin system-reminder
  user message，不在 request header；此前 `availableSkills=null` 只是 schema 位置未知。
- ⚠️ 首轮 request header 精确命中 44/46 catalog names；缺的 `list_bookmarks`、
  `create_bookmark` 是 guidance 写成缩写 `list/create/delete_bookmark`，非桥能力缺失。现已改为
  三个完整名字并 build。
- ✅ 第二次 Restart 后，通过 Host RPC 创建正确 Houdini preset session
  `session-872f6d34...`，使用显式 UTF-8/ASCII 只读 prompt；request header 精确命中
  **46/46 catalog verb names**，system reminder 精确列出 5/5 Houdini skills。
- ✅ 第二轮 agent 再次成功加载 rig skill，只用 `skill ×1 + houdini_query ×1`；query 内
  `scene_info + verb_help(set_keyframes/list_bookmarks/create_bookmark/delete_bookmark)` 五个 verb
  全部 `[ok]`。0 mutation / failure / rollback / advisory，HIP/frame 保持 `魔方.hip` / 115。
- ✅ 部署态 verb/skill/activation/只读行为门完成。ordered 魔方 GUI A/B/vision 与
  H21/H22 APEX graph evaluation 也已完成；剩余领域门为后续真实用户任务。

**Ordered 魔方 GUI 视觉结果与 HIP load 事故**：

- ✅ 获得用户授权后，在 ordered 副本上逐帧 `render_view(OUT_ORDERED, framing_frame=31)`：
  25/31/121/169/217 全部 stale=false、无 warning/error、camera/framing 完全一致。
- ✅ render diff：25→31 meaningful 31.395% / RMSE 20.927；25→121 26.984% / 24.278；
  121→169 29.420% / 25.149；25→217 identical=true、RMSE=0。人工中性查看确认 solved、
  首层中间转动、scramble、recovery、最终 solved，piece/sticker 无明显丢失。
- P0：bridge exec 内 `hou.hipFile.load()` 不能作为事务步骤。单 exec load→render→restore 丢失
  result/images；拆分 load 的请求结果也不可靠；UTF-8 恢复 load 最终关闭连接并启动新 Houdini
  进程，bridge 消失，无法由 finally 完成恢复确认。记录为 HTA-018。
- 已拍板：禁止 live bridge exec 调 `hipFile.load`；不新增薄 `scene_open` verb。打开用户 HIP
  走 UI，离线工程分析用 hython；未来自动化必须是 Host 侧可重连 handshake。
- ✅ 桥级 P0 守卫已实现：AST 在执行前精确拒绝 `hou.hipFile.load(...)`，不受 rawGate 或
  `allow_raw` 豁免；H21/H22 回归验证请求失败且 HIP 不变。`hipFile.save()` 不受专项守卫。
- 文件安全：原 `魔方.hip` 与 ordered 副本均存在；渲染 PNG 已落盘；本轮未保存任何 HIP。
  新 Houdini 进程当前场景需用户目视确认并重新启动 DSH 服务。
- 边界：测试期间 live HIP/frame 保持 `魔方.hip` / 115；trace 无 mutation。用户共享 UI 当前
  display 为 `normal1`，不能归因于只读 agent，符合“viewport/display 可漂移”定位。

**OpenGL 环境记录（非开发项）**：本次崩溃发生在低配置、无独显的 agent 开发机；用户已
说明实际运行 Houdini 的机器配置不会太差，因此不为这个开发机追加 GPU 探测、兼容层、开关
或专项调试。`render_view` 保持正常设计；若开发机偶发 OpenGL 不稳定，只停止本轮视觉重试，
保留节点语义证据。HTA-018 的 `hipFile.load` 生命周期守卫是独立、已确认的安全边界，继续保留。

**APEX 非交互 evaluation 发布门（已完成）**：没有自动化 Animate State，也没有新增 APEX
动词，而是使用两版 `$HFS` 随安装的 SideFX `APEXGraphExamples.hda` 建立 graph-engine smoke：

- H21.0.440 与 H22.0.368 均发现 `apex::graph` / `apex::invokegraph`；帮助 fixture 目录分别为
  `apex--editgraph` / `apex--graph`，证明在线最新路径不能写死到旧版本。
- 官方 Add graph 接收 detail dict `a=2,b=3.5`，输出 `output_parms.result=5.5`；改为
  `10,-4` 后重算为 `6.0`，两版均 0 warning/error。
- 无 graph 输入时两版均抛 cook failure，`node.errors()` 为 `Not enough sources specified.`；
  `errorhandlingmode` 菜单均为 `ignore/warn/abort`。
- 新增 `houdini/tests/regress_apex_evaluation.py`，只在 disposable hython 场景安装/卸载官方
  fixture，不碰 live HIP。该门只证明输入 binding、求值、输出和失败读取；不冒充 controls、
  constraints、FK/IK、components 或 Animate State 已完成，也不批准 APEX setup adapter。

### 2.27 Houdini skills 治理与长期自进化（2026-08-21，首版已实现）

新增随包 `houdini-skill-governance`，统一未来 SOP、Solaris/Karma、rig/animation、COP、SIM、
project-analysis 等领域 skill 的创建、更新、拆并、弃用和版本维护。所谓“自进化”不是每次
trace 后递归改写生产知识，而是：

```text
observation → candidate → accepted → verified → released → deprecated/removed
```

任何 trace、SideFX 官方文档、本机帮助/源码、用户视频、HIP/HDA 工程都可产生 candidate，
但必须记录 provenance、Houdini 版本、权限/隐私、适用条件、反例和下一验收。单 trace/视频/
工程默认 E1；两个独立任务或官方资料 + 目标版本复现达到 E2；三个多样任务、跨版本和反例
达到 E3。可复现 P0 工具 bug 可立即修，但必须有回归。

结构：

- `SKILL.md`：授权边界、入口路由、知识分层、受控自进化和输出契约；
- `references/quality-standard.md`：skill 准入、标准结构、泛化、拆并/弃用和验证；
- `references/evidence-ingestion.md`：trace/官方资料/视频/工程的来源吸收、隐私和版权；
- `references/maintenance-lifecycle.md`：事件驱动维护、健康指标、Houdini 版本刷新、发布/回滚；
- `scripts/audit-houdini-skills.mjs`：确定性检查 frontmatter/name、reference 可达性、孤儿资源、
  `src/skill.ts` 注册和入口体积。

长期路线：M0 治理地基；M1 标准化当前五个 skills；M2 以真实任务证据准入 COP/SIM/
project-analysis；M3 随 Houdini 版本、trace、视频和工程持续刷新。M1 审计与版本矩阵见
[skill-governance-m1-audit.md](skill-governance-m1-audit.md)。明确不预建空壳领域 skill，
不把整本手册、长转录、专有 HDA/代码或项目路径复制进 bundled skills。

`houdini-trace-analysis` 现区分权限：只要求分析时输出 skill delta proposal；用户明确要求
更新/修复 skills 时才加载 governance 执行变更。插件 guidance 只新增一条稳定 dispatch，
不注入完整治理手册。

**M1 完成（2026-08-21）**：五个 skills 的触发、正反例、唯一维护位置和 H21/H22 claim
已完成统一审计，见 `docs/skill-governance-m1-audit.md`。决策为全部 KEEP，窄 UPDATE SOP
视觉门、Solaris H22 未验证边界、rig APEX reference 与 GOV-002；无 merge/split/deprecate。
新 `session-83a553e7...` 发布态验证为 5/5 Houdini skills，成功激活 rig 并读取 reference，
3 tool calls / 2 verbs / 0 failure/mutation/advisory。该 trace 另暴露并修复 HTA-019：ledger
result 内 signature 的 `->` 不得被 greedy regex 当调用分隔；extractor/report/client 改为
字符串与 JSON 容器感知的结构扫描，真实 evidence 回归恢复准确 args/result。

### 2.28 Houdini 菜单默认 session 路由（2026-08-21，已完成）

**问题**：DSH 全局默认 preset 是用户设置；Houdini 菜单只打开通用 Web UI 时，UI 的 New
Session 会沿用 `cordis`，不能靠用户记得手工切换，也不能把 DSH 的全局默认改成 Houdini。

**官方边界确认**（本机 `E:/deepseek-harness` 与当前缓存 CLI 同版本实现）：

- Host `session.create` 正式接受 `agentPreset`，解析后写入 session header，resume 继续使用；
- `session.list` 返回 `cwd/agentPreset/updatedAt`；`workspace.list` 返回 path/account；
- client 的公开导航是 `sessions.refresh()` + `sessions.open(id)`；
- session 文件、浏览器 store 和 profile manifest 都不是插件应直接写的接口。

**实现**：完整 launch 在 3081 ready 后调用正式 `/api/session.list` 与 `workspace.list`，按
“精确 cwd + 精确 `agentPreset='houdini'` + 未归档 + 最新 updatedAt”复用；没有才优先以
`workspaceId + agentPreset` 创建，否则用 `cwd + agentPreset`。WebView URL 只带一次
`dsh-houdini-session` hint；client 半等 `sessions` 服务后 refresh/open，成功才从 URL 消费。
健康服务下的 `Open Workspace` 不带 hint，只置前窗口，因此不改变现有会话。

**验收**：Python 回归覆盖错误 preset/cwd 排除、最新会话选择与 Workspace 精确匹配；Node
VM 回归覆盖 hint 的 refresh/open/成功消费和无 hint 零导航。真实 3081 复用
`session-872f6d34...`，未创建重复 session；WebView 初始目标 URL 携带该 id，随后恢复为根
URL，证明 client 已完成 open 后消费。前端/bridge 分别保持 3081/8765 listening，HTTP 200。
发布 forward-test 创建的 `session-83a553e7...` 已通过正式 `workspace.archiveSession` 归档；
launcher 回归证明 archived session 不参与复用，WebView 已恢复原用户会话 `session-872f6d34...`。

### 2.29 前端预热竞态：session 路由 RPC 可重试（2026-08-22，已完成）

**问题**：`Restart Services` 偶发 `DSH RPC session.list failed over HTTP 404: not found`。
dsh web 的 TCP 端口先于 `/api/*` 路由挂载开始监听，`_start_and_wait_frontend` 的
`_port_open` 一探通就立刻 `ensure_houdini_session`，命中预热窗口即整次启动失败；
同一 CLI（rc.7）稍后手动重放该 RPC 返回 200，证实是时序竞态而非版本缺失。

**修复**：`_start_and_wait_frontend` 在端口已开但 session 路由 RPC 失败时，仅对
预热类失败（HTTP 404 / transport）在同一 `wait_timeout` 预算内继续轮询，不再当场
判死；持续不恢复则抛原始错误。结构化 RPC 错误（`ok:false`）不可重试，立即上抛——
由 `_session_rpc_not_ready` 判定。此类失败不再杀前端进程（服务本身健康，只是接口
尚未就绪）。

**验收**：`houdini/tests/regress_launcher.py` 新增第 11 项（404/transport 可重试、
结构化错误不可重试），H21 hython 12/12 全绿。

**同轮行为统一**：前端启动命令全部加 `--no-open`（cached/configured/explicit CLI 与
npx-cold 四处）。浏览器自动打开是 dsh web-app 的默认行为（`openBrowser` 默认 true，
SSH 会话除外），与 launcher 的内嵌 WebView 重复；dsh-houdini 只保留内嵌窗口，
不同机器间不再因 dsh 版本/SSH 环境差异出现「这台双开、那台单开」。回归第 4 项
同步断言命令尾部为 `web --port 3081 --no-open`。

### 2.30 WebView 发起对话报 AbortSignal.any（2026-08-22，已修复）

**问题**：内嵌 WebView 里发起对话即报 `AbortSignal.any is not a function (internal)`，
外部现代浏览器正常。

**根因**（实机逐层确认）：`(internal)` 是 dsh-client-connection `transportError()` 的
catch-all code；其 C→S `postJson` 用 `AbortSignal.any([AbortSignal.timeout(...), signal])`。
该 client 代码跑在**浏览器侧**——H21 内嵌 QtWebEngine 6.5.3 = Chrome 108（经桥实测
UA 确认），`AbortSignal.any` 要 Chrome 116+，因此 WebView 里必炸（`timeout` 108 已有，
不受影响）。外部 Chrome 版本新所以正常；另一台开发机不报是因为缓存的 dsh 版本旧，
client-connection 尚未引入 `AbortSignal.any`。

**修复**：`dsh_webview.py` 在 view 创建时经 `QWebEngineScript`（DocumentCreation +
MainWorld，先于页面脚本）注入规范语义的 `AbortSignal.any` polyfill；已存在则不覆盖。
GUI 限定，hython 无法覆盖（同 backdrop-filter 注入）。

**验收**（经桥在真实 H21 WebView 实测）：注入前 `typeof AbortSignal.any = undefined`；
插入脚本并重载页面后为 `function`，且 `AbortSignal.any([新 signal]).aborted === false`
语义正确。live 会话已同步热修（scripts.insert + 当前页 patch + reload），用户无需
重启即可重试对话。

### 2.31 OpenGL Fatal 生命周期复现（2026-08-22，结论已纠正）

**确定性复现**：当前 H21.0.440 会话的 Qt global share context 为 OpenGL 4.6；新建共享
offscreen context 直接读到 `NVIDIA Corporation / RTX 3080 / 4.6.0 NVIDIA 591.86`。
一次 64×64 与连续五次 1280×720 `render_view` 均成功，显存稳定，首次初始化后的
handles/threads 平台化，未见逐次线性泄漏。随后通过 `delete_node` 删除
`/out/__dsh_houdini_opengl`，立即弹出完全相同的 OpenGL Fatal 对话框；桥 `/health`
仍正常，但主线程 exec 被模态框阻塞。

**历史 trace 对照**（session `e838ad97-a54f-4aa1-a74d-12edc3a5159f`）：

- #38/#39 多帧 `render_view` 全部成功；#43 的“清理 agent 渲染残留”依次删除
  proxy/camera/OpenGL ROP 时桥断开。
- 重启后 #55 再次多帧成功；#57 再次删除同一组基础设施时超时。
- 因此所谓“成功后 1-2 分钟延迟崩溃”实际包含明确的 teardown 动作，不是已经证明的
  资源耗尽等待期。历史清理先删 proxy，本次复现先删 ROP，两端都进入同一 fatal 路径。

**dump 证据纠正**：4.5GB 文件是错误对话框期间的 live dump，没有 exception stream。
`Microsoft Corporation / GDI Generic / 1.1.0 / GL_WIN_swap_hint / ...` 完整连续字符串块
位于 dump 的 `opengl32.dll` 映射静态数据（起始虚拟地址 `0x7ffe2ecd2658`），不能证明
创建过软件 GL context。`dump_*.py` 只是按 8 字节扫描栈内指针并映射 DLL，不是使用
unwind metadata/symbol 的调用栈回溯；TID 14012 只能确认 RIP 位于 `win32u.dll`。

**当前根因边界**：已确认的是“成功使用 OpenGL ROP 后，删除 owner render
infrastructure 会进入 Houdini 的进程级 GL fatal”；尚未二分 `delete_node` 的
`parmsReferencingThis()` 与原生 `destroy()` 哪一步触发，也未证明 WDDM/GDI 降级。

**落地决策**：

1. `render_view` 基础设施改为会话级持久服务，OBJ/OUT 两侧放进带说明的 Network Box，
   反复复用；任务收尾只清空 proxy live source，不删除节点。
2. `delete_node` 拒绝删除 owner-tagged render service 节点，在进入 Houdini teardown 前失败。
3. guidance 明示 `__dsh_houdini_*` 不是残留。用户接受这些节点随 HIP 留存；需要时可把
   Network Box 放到网络一侧，不以“干净场景”为由冒险销毁。
4. WER LocalDumps 继续保留；资源压力只作为可能放大因素，不再写成已证根因。

**验收与稳定策略**：H21 GUI 完整回归连续两次真实 OpenGL 输出逐像素一致
（RMSE=0、changed pixel=0%），frame/selection/visibility 全部恢复；OBJ/OUT Network Box
成员完整且跨调用复用。随后对 ROP、proxy、camera、target 的 `delete_node` 尝试均在进入
Houdini teardown 前被 owner guard 拒绝，普通 probe 节点仍可删除，桥 `/health` 与 GUI
继续响应。项目据此采用“保留并复用服务节点”作为正式稳定方案，不以 CPU fallback 取代
正常可用的 OpenGL 路径。若维护代码使用裸 `hou.Node.destroy()` 绕过动词守卫，仍须自行
承担同一 fatal 风险；agent 任务不得这样清理服务节点。

### 2.32 完整 profile 依赖同步与可信验收（2026-08-23，已实现）

**问题**：过去 `houdini/install.py` 只写 Houdini package，launcher 只同步 preset 和本仓库
Node 依赖；DSH web profile 的社区插件仍依赖每台电脑手工安装。于是装有视觉路由器的机器上，
纯文本模型可以完成视觉闭环，另一台机器上的同一 preset 却只有失败的 `read_image`，体验与
trace 结论均随机器漂移。同时，mutation exec 捕获异常后只打印而不重新抛出会让桥误判成功，
跳过已有的 undo rollback；`render_check` 也曾被误写成视觉语义验收。

**落地**：

1. 根目录新增 `dsh-profile.requirements.json`，声明完整 `web` profile 当前必需的 bundle：
   本地 `dsh-houdini` link 与锁定版本 `dsh-vision-router@1.6.0`。这是安装依赖清单，不承载
   任何具体 Houdini 任务策略。
2. 新增无 `hou` 依赖的 `dsh_profile_sync.py`：只读检查 profile manifest、实际安装包版本、
   bundle 激活状态与本地 link 目标；只有漂移时才调用官方 `dsh plugin --profile web add`，
   调用后重新读取并强校验，绝不手写用户 profile manifest。
3. `houdini/install.py` 默认同时安装 Houdini package 与完整 DSH profile；可显式传
   `--skip-dsh-profile` 只装 Houdini 部分。每次 `Restart Services` 也会在前端停止后、启动前
   运行同一幂等同步，因此升级清单可以自动补到已安装机器。
4. 桥在同一 undo group 内检查 verb ledger：若 agent 捕获并吞掉 verb 异常，exec 仍被强制判失败，
   从而触发 rollback；通用 guidance/preset 同时要求 mutation exec 捕获异常后重新抛出。
   `render_check` 只证明图像有效或像素变化，没有成功的 vision tool 就必须报告视觉语义未验。
5. trace evidence 把 `read_image` 与 `vision_*` 统一计入视觉证据，记录成功/失败，并自动输出
   `render_without_successful_vision` / `vision_tool_failed` 完成风险。

**本机验收**：profile 从仅有 `dsh-houdini` 收敛为两个 bundle，`dsh-vision-router` 实装
1.6.0 且进入 `dsh.profile.bundles`；profile 只读复查通过。Python 标准库回归覆盖完整状态与
“依赖存在但 bundle 未激活”状态，hython 回归确认吞掉的 verb 异常会强制失败；Node evidence
helper 回归、TypeScript build、DSH `--dump-config` 与 vision-router doctor 均通过。
同一 profile 在临时 3181 端口完成 runtime HTTP 200 启动，且配置中 `vision-router` row
恰好一份；未重启用户当前 3081 会话。视觉路由器的默认免费视觉链会把选中的图像与问题发送给外部视觉服务；
生产环境可在其设置中改为用户授权的后端。

### 2.33 Version & Diagnostics 双更新通道（2026-08-23，已重构）

**问题**：原面板虽然同时展示 npm DSH release channel 与插件 Git remote，但 `Check Updates`
只是只读比较，唯一的 `Copy Update Commands` 又只覆盖本仓库的 `git pull → npm install → build`。
用户很容易把“更新 Harness runtime”和“更新 dsh-houdini 插件”混成同一件事；新模型已经进入
DSH 目录时尤其明显——更新本仓库并不会改变缓存中的 DSH CLI。

**落地**：

1. 主界面改成两条组件轨道，只显示 `CURRENT / LATEST / ACTION`：DeepSeek Harness 与
   DSH-Houdini 各自一行，打开面板即自动检查；缓存列表、Git 细节、端口和日志入口移入折叠的
   `Advanced diagnostics`，删除底部按钮条与复制命令。
2. launcher 在 :3081 确认监听后原子写 `.dsh-runtime.json`（version/PID/source/bin），manager
   再用 `netstat` 的监听 PID 校验。标记缺失或 PID 不符只报 `Unknown`，不会把“最近缓存候选”
   冒充正在运行的 DSH。重启/启动失败会清理旧标记。
3. npm 精确版本下载后 touch 对应 `bin.js`，使 launcher 的 mtime 候选确定指向刚更新的 release；
   `DSH_HOUDINI_DSH_SPEC` / `DSH_HOUDINI_DSH_BIN` pin 仍 fail-closed。插件检查先 fetch
   `origin/main`，读取远端 `package.json`，并区分 current/behind/ahead/diverged，不再用 HEAD
   不相等粗暴等同“可更新”。dirty + behind 或 diverged 均禁止自动 pull。
4. 更新动作升级为“更新并在空闲时重启”。重启前用 DSH `session.list[].running` 检查 agent turn，
   并由 bridge `/health` 返回 `activeJobs/queuedJobs/runningJobs` 检查 Houdini job。任何活动或探测
   失败都暂缓激活，主按钮变成 `Restart when idle`；不会强杀正在执行的任务。
5. `Restart Services` 的能力仍保留，但降级到高级诊断中的 `Repair and restart runtime`，用途是
   本地开发代码刷新、桥/前端异常修复，不再是正常版本更新必须手点的第二步。只有菜单 XML 或
   安装脚本发生变化时才明确要求完整重启 Houdini。

**确定性验收**：`tools/tests/dsh-manager-update.test.py` 覆盖缓存 promotion、PID 标记校验、双组件
状态归纳、pin/dirty fail-closed、活动 session/job 重启门与空闲自动激活；H21/H22 hython 均做
compile/import 与回归。GUI tick 只消费 worker 状态，不再同步探测 localhost。

### 2.34 task-scoped 节点 provenance 与 foreign mutation guard（2026-08-23）

**触发事实**：创建 10 个 box 的测试 trace 里，`copytopoints2` 是用户临时手建节点。
它与 agent 产物处于同一父网络，但“在同一网络里”只说明拓扑位置，不说明创建者或修改授权；
让无参 `layout_nodes(parent)` 布局全部 children 会把用户状态误当成任务产物。

**落地契约**：

1. host 从真实 tool execution context 取得 `agent.id`/`callId`，作为隐藏的
   `owner_session`/`owner_call` 随 exec/job 提交给 bridge；它们不是模型参数。bridge 在唯一
   `_exec_lock` 内安装并 finally 恢复 owner context，后台 job 继承提交时身份。
2. `tab_create`/`tab_apply`/shelf recipe 的新增节点以进程内 `hou.Node.sessionId()` 登记；
   userData 只作持久审计，不能作为权限依据，因为复制节点会复制 userData。新增
   `node_provenance` 明确区分 `foreign`、当前/其他 session owner 与持久 dsh service。
3. node/parm/HDA mutation verbs 默认要求当前 session owner；读取、检查以及把 foreign node
   当作 connect source 仍开放。用户明确要求修改某个既有节点时，用单次
   `allow_foreign="理由"` 放行并打印 `[ownership]` trace；这不是接管。render service 永不豁免。
4. `layout_nodes(parent, nodes=None)` 在 host task 中只布局当前 session owner，返回
   `foreign_nodes_skipped`；显式 nodes 逐项检查。直接 Houdini Python Shell 没有 host owner 时
   保持原来的全布局语义，避免破坏维护/回归工作流。

**确定性验收**：`tools/tests/dsh-node-ownership.test.py` 用 H21 hython 模拟两次 agent call
之间用户手建 `copytopoints2`，并伪造相同 userData；验证 provenance 仍为 foreign、默认布局
不移动它、默认改名拒绝、另一 session 不可写，以及明确 `allow_foreign` 后单次放行并留痕。

### 2.35 视觉插件隔离 A/B：工具能力与 provider SLA 分层（2026-08-23）

生产 `web` profile 继续保留 `dsh-vision-router@1.6.0`，没有边测边替换。另建
`~/.dsh/profiles/vision-eval`，挂 `@deepseek-ai/dsh-web-app`、本仓库 link 与
`@anionex/dsh-vision-toolkit@0.1.38`，独立启动在 :3091。该候选提供 task-aware
glance/ground/detect/crop/OCR/pixel-diff 等契约，managed Python runtime、Pillow/Numpy/
vtracer、Chrome、artifact 目录和 built-in credential 均通过 health，profile compose/HTTP 也正常。

但真实 multimodal probe 对内置 `gemini-3.7-flash` 免费服务返回 HTTP 429
`rate_limit_exceeded`。因此结论不是“换包即修复”：插件决定输入整形、证据结构、失败可观测性，
provider 决定可用性/SLA。候选只进入隔离验收，不晋升生产；下一门是给它配置用户授权、
可计费/有配额的 OpenAI-compatible vision provider，再用同一组 Houdini render 做 A/B。

### 2.36 蜘蛛 trace：采用指标、版本握手与视觉完成门（2026-08-23）

**触发事实**：最新“大蜘蛛绑定动画” trace 表面上只有 65/111（58.6%）Houdini 调用含动词，
低于 10-box 的 73.9%；但它实际调用 224 个 verbs（密度 2.02），44 次无动词调用是只读几何
探针，2 次裸修改都在执行前被 Gate 拦截，成功 exec 的动词覆盖为 48/48。原报告把
`20/47` 目录广度和“任何无动词调用”同时当成低采用/裸修改信号，结论失真。

同一 trace 还暴露三个独立缺陷：运行中 Bridge 缺 `node_provenance`、与 Host 新目录不同代；
`dict.setdefault` 被通用 `set*` Gate 启发式误伤；`vision_bootstrap` 返回 `ok:false` 且
`vision_describe` 明确拒绝看图，但 transport success 和后续 `vision_present` 让 evidence 错判
视觉成功，todo 也被错误完成。

**修复**：

1. 构建器从 `tool-design.md` 生成 Host 动词名、摘要和 SHA-256；Bridge 从实际 `_VERBS`
   独立计算 `/health.verbCatalog`。Host 在 `/exec`/`/jobs` 前比较，不一致 fail-closed；
   `verb-contract.test.mjs` 与 `bridge-contract.test.mjs` 覆盖三方漂移和零执行副作用。
2. Raw Gate 安全集排除 `dict.setdefault`，H21 hython 回归覆盖真实聚合形状。
3. evidence schema 升到 v2：视觉分 `setup/inspection/presentation`，分别记录 transport 与
   semantic outcome；结构化 `ok:false`、中英文拒绝看图不再算成功，完成视觉 todo 会产生风险。
4. 新增 `verbAdoption`：目录广度、调用含动词率、密度、无动词只读、成功 exec 覆盖、
   Gate 拦截和成功裸修改分开；HTML 报告同步改名，不再用 `used/47` 代表合规率。
5. 常驻 GUIDANCE 从逐动词手册压缩为稳定边界，目录摘要机械生成；Houdini persona 删除重复
   render/skill recipe，只保留身份、程序化工作方式和用户共享屏幕边界。

**验证**：`npm run build`、全部 Node tests、H21 raw-gate/ownership/caught-failure 回归通过；
蜘蛛 trace 重提取后显示成功 exec 动词覆盖 100%、成功裸修改 0，并产生
`render_without_successful_vision`、`vision_tool_failed`、
`completed_vision_todo_without_evidence` 三个完成风险。运行中服务尚未重启，因此 live
Bridge 仍是旧代；这是部署状态，不再会被新 Host 静默接受。

### 2.37 魔方 trace 修复与轻量视觉 fallback（2026-08-24）

> 2026-08-26 纠正：本节的 fallback 生产决策已由 §2.39 撤销；保留本节只作为当时实验与错误
> 方向的历史记录。

最新“带绑定动画的魔方” trace 完成了 ordered piece 状态、非交换 R→U、recovery、cook 与
HIP 保存，但暴露四个可复现缺口：`verb_help(create_spare_parms)` 没给 `spec` 精确 schema；
调用方把 `geo_frame_diff.mean_delta/max_delta` 误读成 `mean/max`；状态求值器修复后没有重跑
完整 first/noncommutative/mid/end/recovery 证据；固定 f1 构图在 f21 的
`render_check.content_bbox` 上下触边。evidence 的 verb ledger 摘要还会截断 render output，
导致报告里的路径为 null。

本轮修复：helper docstring 与 `tool-design.md` 写入精确参数/返回键；rig/SOP/audit 契约要求
核心求值变更使旧序列证据失效并全量重跑，固定相机同时覆盖验收帧 bbox 包络和安全边距；
evidence 从 tool result 的完整 `__result__` 恢复被 ledger 截断的 render 字段，并记录
`content_bbox` 是否触边。

视觉侧用随仓库发布的 `plugins/dsh-vision-fallback` 替换旧 `dsh-vision-router`。新插件在
`设置 → 插件 → 视觉备用` 注册独立客户端页，并通过 `vision-fallback` settings namespace
持久化 Key/模型；工具执行时读取 live settings，无需重启。新插件设置面
只有 secret `apiKey` 与 `供应商/模型` 两项，默认 `qwen/qwen3-vl-plus`；它只注册
`vision_describe`，不注册 adapter/provider directory、包装模型、免费链、OCR/截图工具或
“+ 自动识图”分组。profile 同步通过官方 CLI 移除旧插件并 link 新插件；当前还需授权 Key 的
实机同图 A/B，成功 transport 仍不等于视觉语义通过。

### 2.38 DSH 更新取消总时限并公开真实下载进度（2026-08-26）

**触发事实**：`Version & Diagnostics` 更新 DSH `0.1.1-rc.2` 时，冷 npm cache 实际从
10:08:35 运行到 10:29:43 并以 exit 0 完成；manager 的固定 600 秒 `subprocess.run`
先报超时，Windows 外层 `cmd.exe` 被结束后 npm 子进程仍继续下载，形成“界面失败、缓存稍后成功”的
假失败。等待期间 UI 又因 `busy` 分支不渲染而没有任何包数、字节或速度证据。

**落地契约**：

1. DSH 精确版本下载改为流式 `Popen`，取消总时限；npm 进程正常退出、CLI 回报目标版本，或明确
   非零退出才形成终态，耗时长本身不再等于失败。
2. npm 使用无颜色 `silly` 输出。tracker 以待拉取 tarball URL 集合作为总数，以成功 fetch 的唯一
   tarball URL 集合作为已完成数；依赖图尚未解析完时显示 `已完成/?` 和不定进度条，避免伪造百分比。
3. 接收字节按 project-local npm `_cacache/content-v2` 相对启动基线的实际增长统计；速度使用最近
   5 秒样本的滑动平均，同时显示阶段、当前包与累计耗时。该口径是本地缓存实收量，不冒充 registry
   的 `Content-Length`。
4. npm stdout/stderr 由独立 reader 持续排空，worker 每 0.5 秒发布快照；Qt timer 在 `busy` 时仍只
   读取状态并刷新专用进度条，不做网络、磁盘遍历或进程等待。错误只保留有界输出尾部，避免大日志
   占满内存。

**确定性验收**：`tools/tests/dsh-manager-update.test.py` 覆盖两个待下载 tarball/一个完成 tarball
的计数、MiB/速度/耗时格式及更新状态收口；H21 hython 回归通过。另以真实已缓存 rc.2 执行流式
路径，CLI 返回目标版本并产生多帧进度快照。

### 2.39 生产视觉回归 vision-toolkit，退役轻量 fallback（2026-08-26）

**本机实测事实**：`~/.dsh/profiles/web/package.json` 同时激活了
`@anionex/dsh-vision-toolkit@0.1.7` 与本地 `dsh-vision-fallback`；用户明确反馈当前 toolkit
更好用。toolkit 的已安装 manifest 和中文 README 证明它不是单一描述接口：默认只暴露
`vision_toolkit_activate`，加载 `vision-tools` skill 后按当前 agent 挂载 `vision_glance`、
ground/detect、crop/trace、pixel diff、长图 OCR、前景提取、主色和 HTML screenshot 共 10 个
独立 schema，并提供受控 Artifact 目录与 Web 预览。

当前 `web/cordis.patch.yml` 把 provider 指向 DashScope OpenAI-compatible endpoint、模型
`qwen-vl-max`、凭据引用 `VISION_API_KEY`。审计只读取了 endpoint/model/credential 名称，没有读取
或输出密钥值；用户对当前体验的确认成为生产选择证据。版本先精确锁定 0.1.7，避免第三方包升级
无声改变 schema、runtime 或 provider 行为。

**替换契约**：

1. `dsh-profile.requirements.json` 的第二个生产 bundle 改为
   `@anionex/dsh-vision-toolkit@0.1.7`；`removePlugins` 同时列出旧
   `dsh-vision-router` 和 `dsh-vision-fallback`。同步只通过官方 `dsh plugin` 修改 manifest，
   不覆盖用户 profile patch 或 DSH Credential。
2. 删除仓库自带的 `plugins/dsh-vision-fallback` host/client、设置页和专属测试；package 发布清单
   不再携带 `plugins/`。旧 fallback 不再与 toolkit 重复注册视觉入口，也不再维护另一套 provider
   映射与 secret 存储。
3. profile-sync 回归改为验证 scoped npm 包、精确版本、缺失/重复 bundle，以及 router/fallback
   双迁移；trace semantic refusal fixture 改用生产 inspection 工具 `vision_glance`。
4. 当前机同步后应只保留 `dsh-houdini + @anionex/dsh-vision-toolkit` 两个项目管理的生产能力，
   同时原 DashScope patch 保持不变。视觉完成门不放宽：transport、bootstrap、Artifact
   presentation 均不能替代 `role=inspection && semanticOk=true`。

**本机部署验收**：官方 profile sync 返回 `removed dsh-vision-fallback`；同步后依赖只有
`dsh-houdini` 与 `@anionex/dsh-vision-toolkit:^0.1.7`，bundle 层为 base/web-app 加这两个能力。
同步前后 `cordis.patch.yml` SHA-256 相同，证明 DashScope `qwen-vl-max` 配置与 Credential 引用
未被覆盖。用 rc.2 CLI 在临时 :3099 启动真实 `web` profile，端口持续监听且首页 HTTP 200，随后
正常停止测试进程；生产 :3081 留给 Houdini launcher 启动。

### 2.40 DSH rc.2 类型对齐与五工具展示卡片（2026-08-27）

生产 runtime marker 当前指向 DSH `0.1.1-rc.2`，其 `dsh-tools` 与 `dsh-system-prompt` 也都是
`0.1.1-rc.2`；仓库原开发图仍混用 `dsh-tools 0.0.1-rc.1` 与
`dsh-system-prompt 0.0.1-rc.5`，旧的 Phase 1 `0.1.0-rc.6` 目标已经过时。本轮把两个直接接口
依赖及 `dsh-system-prompt` peer 范围统一到 `^0.1.1-rc.2`，lockfile 中由 `dsh-tools` 引入的
开发期 peer 类型图也统一到 rc.2。首次编译立即抓到 `presentationMeta` 必须是可持久化
`JsonValue`、不能是宽泛 `Record<string, unknown>`，证明对齐不是纯版本号整理。

五个 `houdini_*` 工具均补纯函数展示契约：exec 为 `generic/edit`，query/status 为
`generic/read`，job submit/cancel 为 `generic/execute`；调用卡展示 Python 代码或 job id，结果卡
保留原模型内容，只用最小 `presentationMeta`（`ok`、`jobId/status`、verb/media 数量）恢复语义
标题。presenter 不读取 Houdini、时钟、会话或文件，非法/旧 schema 回放参数由 `defineTool`
安全退回通用卡片。新增 `houdini-tool-presentation.test.mjs` 直接审计五个注册定义、成功/失败/
running 状态、非法回放与重复纯投影；`npm test` 现为 6 个 Node 测试文件全绿。现有 Houdini/DSH
进程仍需 `Repair and restart runtime` 后才会加载新 host 代码；本轮未把“代码契约通过”冒充已在
当前 WebView 完成视觉验收。

### 2.41 模糊任务前置合同与程序化资产质量门（2026-08-27）

最新 baseline `d6df94d7-d778-4d35-8529-a6f3e9f4e804` 的原始请求只有“细节丰富的程序化
自行车”。Agent #3 正确询问并确认山地车与 SOP + render_view 交付，但没有外部参考、LOD、允许
简化或参数化完成门；随后把共享位置硬编码进多个 VEX。首轮 cook、piece 与整车语义读图通过后
即宣布完成，用户纠正才触发 #26 的局部检查并发现前叉脱开、63% 胎齿位于内圈/侧壁、链条不绕
导轮和 BB 间隙。修复证明现有 bridge/动词/rollback/视觉链路足以支持局部迭代，也证明主要缺口
位于 build 前的外部质量模型和 build 后的部件关系门，而不是继续扩节点创建 API。

按 governance E1 边界做窄修：生产 Houdini preset 仅对会实质改变方案的开放式歧义要求
`research/clarify/contract`，简单规格完整任务直接执行；`houdini-sop-workflow` 新增按需
`procedural-quality-contract.md`，定义参考/LOD/允许简化、共享尺寸与 anchor、模块关系、局部
特写和关键控制扰动门，不写入自行车专用尺寸或节点 recipe；trace rubric 扩展前置阶段，并把
“自生成规格再凭模型记忆证明真实”登记为 HTA-023 候选。没有新增 skill 或 verb，`hip_save`、
通用关系自省仍只是后续候选，等待重复任务证据。

当前状态是 **verified（结构/构建/打包），未 released**：skill quick validation、strict governance
audit、`npm test`、`npm pack --dry-run`，以及 H21.0.440 的 raw-gate / ownership /
caught-failure / tab-create-failure 四项强制回归均通过；仍需要 `Repair and restart runtime` 后新建
Houdini session，用完全相同原始提示词跑 A/B，不能追加“检查比例/连接”的用户提醒。首个验收看
是否在大 batch 前形成参考/质量/关系合同，首次完成前是否主动发现同类结构问题；第二个开放式
模拟或渲染任务复核后，HTA-023 才能从 E1 升 E2 并讨论更强执行守卫或结构化合同工具。

### 2.42 自行车 A/B 后的 P1 强完成协议与 HTA-023 确定性审计（2026-08-27）

新 session `e0bc309b-ab8b-4a40-b636-14217cd2b91f` 用与 baseline 完全相同的“细节丰富的程序化
自行车”提示，system hash 从 `f5d00dee1ea6eb96` 变为 `b8d90bbae480fd78`，证明 P0 preset 已加载。
Agent 确实在 mutation 前选择山地车、披露无参考假设、建立 14 个对象级控制和 6 个 named anchors，
模块结构也比 baseline 更集中；但可用工具中已有 `web_search`/`read`，它仍未检索参考或读取
`procedural-quality-contract.md`，没有质量/LOD 与允许简化，首张 render 前创建 116 个节点，未做
任何对象级控制的扰动恢复。最终报告又复用了牙盘修改前的 5740 点/4561 prim；末次 render 的
真实 fingerprint 已是 6027 点/4848 prim。五次 render/read_image 证明视觉链路可用，但远景可辨认
仍被升级成局部关系和总体质量通过。

这次同领域重复把 HTA-023 从单 trace 候选提升为 S2 同领域证据，且说明主因不是缺 Houdini 动词：
P0 让 agent 会复述合同，强制 checkpoint 却藏在“按需阅读”的 reference，因而没有进入执行上下文。
P1 保持域中立，不加入自行车尺寸或专用 verb：

1. `houdini-sop-workflow/SKILL.md` 对开放式、质量敏感、机械关系复杂或可调资产强制在大规模 mutation
   前读取质量合同，并内联研究/合同、骨架、关系账本、视觉批评、扰动恢复和新鲜证据六个 checkpoint。
2. 生产 preset 把合同改为持续证据账本；完成前逐项标 `pass/fail/unverified`，可调交付要扰动并恢复
   一个关键控制，最后一次 mutation 后刷新依赖证据。节点数、primitive 数、无 warning、成功 render
   或完成 todo 均不能补足质量证据。
3. evidence schema v2 新增 `qualityLoopEvidence`，并从 request header 保留真实 available tools；
   HTA-023 确定性风险覆盖合同缺字段、质量合同未加载、可用 research 未用、无来源外部真实性、
   首次视觉过晚、无控制扰动、关系合同无 probe 和最终点数/prim 陈旧。用户已给参考是明确反例。
4. `trace-report.mjs` 增加质量闭环卡片与风险明细；`read_image.file_path` 纳入帧提取，修复实际完成
   5 次语义 inspection 而 HTML 仍显示 `vision-inspection=[]` 的报告缺口。

确定性 fixture 同时覆盖缺门 trace 与完整 trace：完整路径必须包含 web/reference、质量合同加载、
对象级 `set → cook/query → restore`、关系 probe 和末次修改后的匹配统计。下一次仍先重启 runtime，
再用相同自行车提示做第三次无追加纠错 A/B；之后用开放式模拟或渲染任务验证跨域行为。两者仍跳门
时才把合同状态下沉 Host/工具层，不继续无上限堆 prompt。

当前 P1 状态为 **verified locally，未 released/未完成行为 A/B**：两个目标 skill 均通过 UTF-8
`quick_validate.py`，strict governance audit 为 5 registrations / 0 issue / 0 warning；`npm test`
完成构建并通过 6 个 Node 测试文件，`npm pack --dry-run` 包含质量合同和 trace 资源；H21.0.440
的 raw-gate、ownership、caught-failure、tab-create-failure 四项强制回归全绿。旧 trace 重提取确认
新版报告把 5 次 `read_image(file_path=...)` 正确记为 frame 1 semantic inspection，并稳定检出上述
六项质量闭环风险。生产 Houdini/DSH 进程仍须 `Repair and restart runtime` 才能加载 P1。

### 2.43 两模型自行车复核、选择题优先交互与审计误报修正（2026-08-27）

同一原始提示在 `937bfa1e-f183-46e2-a717-d930bd701c34`（qwen3.8-max）和
`73bc9795-d45c-4774-ae32-c2a6291dd2b8`（k3）上复核。两者都收到 P1 preset、读取 SOP 质量合同、
建立集中控制/骨架、做关系检查，并真实执行 `wheel_radius` 改值、受影响检查、恢复和新鲜统计；
Qwen 另执行 web 调研和 goal/todo 账本，K3 检出后胎/车架从 `-17.76mm` 穿插并修到 `+3.33mm`。
这证明自然语言 P1 已跨模型改变实际轨迹，暂不需要把合同立即下沉 Host 阻断执行。共同剩余缺口是
mutation 前未明确 LOD/允许简化，且视觉展示门不可靠：Qwen 四张 render 的平均灰度仅
`0.17–1.66/255`，错误 side 轴向与近空传动特写仍被标成文件/像素 pass；K3 只查看了触顶/触右的
viewport 局部。Qwen 视觉工具因无 image modality 和 toolkit HTTP 401，正确降级为 unverified。

人工审计同时证明旧 `qualityLoopEvidence` 有五类确定性误报/漏计：只认 OBJ 根参数导致
`CTRL/CONTROLS` 扰动漏检；只读 assistant prose 导致 mutation 前 goal/todo 的关系和证据计划漏检；
骨架关键词固定词序漏掉“数值验证骨架”；明确 `unverified` 的已完成视觉 todo 被当成伪完成；stdout
与 `14,189 点 / 12,510 面` 格式无法进入新鲜统计。提取器现从 `create_spare_parms` 识别声明的
控制节点和 spec defaults，合并 pre-mutation goal/todo，双向匹配骨架 checkpoint，识别明确视觉
失败边界并扩展中英文/逗号统计格式；两条真实 trace 重提取后，K3 只保留合同缺字段风险，Qwen
只保留视觉失败和质量/简化缺字段，不再错误声称两者未扰动。

用户补充的交互要求放在唯一正确层：生产 Houdini preset 对重大用户选择强制 choice-first，使用
`ask_user_question` 声明 schema，每题提供 2–4 个互斥选项、推荐项和影响说明，保留 custom 文本补充
及合理的“由 agent 决定”；最多一次组合三个相关选择，路径/节点名/精确数值等天然唯一答案才用纯
文本。SOP skill 给 LOD、交付深度和简化的领域选项示例。视觉门另要求先声明资产轴向，读取
`render_view.check` 或 `render_check`；近黑、内容极少、空 bbox、触边、错误轴向或目标不在特写时
像素展示失败，不能用 `stale=false`/文件存在/无 error 代替。下一验收不再重复自行车，而用开放式
模拟或渲染任务检查选择题、合同字段和像素降级门的跨域采用。

首次部署尝试 `645cd673-b9f7-4e99-a547-d8bf7270c7e0` 进一步证明 prompt 规则不够：K3 在
tool/call seq 262 确实生成了三题、每题三选项及完整影响说明，但把字段写成 `"header "`、
`"options "`。上游 ask tool schema 的 `additionalProperties:true` 接受这些字段，执行器只读取精确
key 并静默忽略，最终 UI 三题都退化为“输入你的答案”。由于 DSH 明确禁止 pre-execute 改写已记录
参数，本轮在 dsh-houdini agent scope 加 fail-closed guard 而不 fork/覆盖上游工具：question/option
未知字段或尾空格 key 在 UI 前被拒；选择型问句缺 2–4 options 也拒绝；精确路径/名称/数值和自由
补充仍允许文本。反馈要求模型用精确 schema 重试，UI 不再承受静默降级。新增纯函数 fixture 后
`npm test` 增至 7 个 Node 文件全绿。旧 pending 调用不可追溯修复，需取消后 Repair/restart 并新开
session；该部署验收记录为 HTA-024。

### 2.44 沙尘跨域部署验收与体积语义完成门候选（2026-08-27）

Repair/restart 后的新会话 `bbaedb46-60f0-40c9-b59a-52795c727895`（K3）用原始提示
“有电影感、可以调节的沙尘冲击效果，并给出可靠验证”完成了 48 次工具调用、85 个动词、约
14.4 分钟。choice-first 的真实 UI/trace 验收通过：tool #5 / seq 216 的三题使用精确
`header/options`，分别提供 3/2/3 个互斥选项和影响说明，result 完整记录用户选择；本次模型首次
即生成合法 schema，因此只能证明合法 UI 路径，畸形 key 的 guard 拒绝/重试仍由纯函数回归覆盖。

强完成协议也出现跨域正向采用：首个 mutation 前加载 SOP skill/质量合同，合同声明无参考、
中远景镜头级轮廓、集中控制和多帧验证；网络用 CONTROLS → emit/turbulence → VDB/composite/
soften → OUT，完成 `ring_speed 12→24→12` 与最终 `12→6→12` 两轮扰动恢复，末次修改后重跑
24/60/120 帧数据、渲染、语义读图和最终 frame diff。最终 `geo_frame_diff(24→120)` 为
`mean_delta=15.05`、`unchanged=0%`，cook 无 error/warning，HIP 成功保存。Raw Gate 对首次
`hou.hipFile.save()` 先拦截，模型用“词表无保存 verb、文件 I/O 不回滚”的单次理由豁免，未出现
已覆盖裸 mutation 回归。

人工同图复核没有接受模型的艺术结论。f24/f60/f120 的 transport、亮度、nonblack 和 bbox 都有效，
但三张图主要是黑底中性灰椭圆尘团；f60/f120 的环孔、沙浪墙和中心柱不足以可靠分辨。K3 在实际
读取图片后仍把 f60 描述为“clear ring/donut”，两次返工后的 f60 仍接近实心团块。数据证据也只
证明 source 公式半径和点位随时间变化，不能证明合成后的 VDB 密度保留承诺形态。最终报告又把用户
原始核心“电影感（颜色/光影/体积光）”列为 `unverified`，却以“完成”开头，因此按任务契约只能判
**部分完成**。无地面碰撞、SOP 点云近似等允许简化直到最终才披露，也是 mutation 前合同缺口。

确定性审计已做窄修：开放式质量触发覆盖电影感/镜头级/可靠验证和可调效果；最终完成文本若把用户
原始质量维度列为 `unverified`，新增 `requested_goal_reported_unverified` 风险。重新提取本 trace
应稳定产生 `quality_contract_incomplete(simplifications)` 与
`requested_goal_reported_unverified(cinematic)`。生产 persona 同步补齐完成状态不变量：任何用户
核心维度仍为 fail/unverified 时只能交付 partial/incomplete，不能以“完成”开头；明确不在合同内的
可选边界才允许保留 unverified。HTA-025 仅登记 E1 候选：体积/合成效果需要一种
独立于整体 hero 图的形态证据（隔离层、正交/切片诊断或密度采样），但具体 `volume_*` 工具形态等待
第二个独立模拟任务，当前不把单个沙尘 recipe 写进生产 skill。

### 2.45 仓库基线清理与跨域 benchmark 决策（2026-08-28）

进入下一轮前对 78 个非依赖/非生成文件、Host TypeScript、Houdini Python、两个 preset、五个 skills、
打包清单和当前文档完成一致性盘点。工作树起点与 `origin/main` 一致；`npm test`、skill governance、
`npm pack --dry-run`、Python compile 与 profile sync 基线通过。审计发现并修正的都是可直接证明的
事实漂移：README 同时描述旧“一键全重启”和新 `Open Workspace` 语义，Host/preset/install/launcher
仍引用退役菜单，launcher 顶层 docstring 与实际双路径不一致，README 漏列 Solaris skill，choice guard
对非对象 question/option 没有兑现 fail-closed。新增 current-docs consistency 回归，Node 测试增至 8 个。
最终验证为：8 个 Node 文件、5/5 skill 注册治理、npm pack（含新计划文档）、7 个 Python 源文件
compile、H21 raw-gate/ownership/caught-failure/tab-create-failure、manager update 与 profile sync 全部通过。

本地忽略目录分成三类处理：当前 runtime marker/log 不动；trace、session、media 与 `tools/out` 作为
仍可复核证据保留；只删除孤儿 `__pycache__`、空退役 plugin/artifact 目录和 2026-08-18 的窗口调试日志。
历史开发记录保留当时菜单名/版本号，并在文首声明不能当作当前操作说明，避免为了表面整洁破坏证据链。

路线选择为能力证据优先，不先实现生产级结构化任务合同。新建
[`cross-domain-benchmark-plan.md`](./cross-domain-benchmark-plan.md) 作为唯一评测计划：在程序化机械资产、
真实 solver/cache 模拟和 Solaris/Karma lookdev 三个能力族运行双模型发现矩阵；执行 agent 与评委分离，
先确定性检查，再做无目标词盲语义描述，最后目标核验。主矩阵前冻结 protocol/fixture/评分，不并行迁移
jobs、权限层或大范围 GUI 回归；只有跨任务重复证据达到 governance 门才新增动词、skill 或最小结构化
ledger。

### 2.46 Benchmark 反过拟合与信息防火墙（2026-08-28）

用户进一步明确：目标是通用 agent，不能为校准矩阵中的个别建模、模拟或 lookdev 任务增加额外提示。
因此原“三道固定题 + 原题复测”设计被收紧为三层实例：校准/发现、未见留出、跨域反例。生产
`GUIDANCE`、preset、skills、verb/tool 和错误提示在全部实例间保持相同，不得出现 benchmark ID、
对象配方、目标参数、评分 rubric 或失败补丁；执行 agent 只收到正常用户 brief，evaluator-only 合同
与隐藏检查不进入会话或 `$HIP` workspace。

新增 `benchmark-generalization-policy.test.mjs`，扫描 `AGENTS.md`、`client.js`、`src/`、`presets/`、
`skills/` 与当前路线文档中的已登记实例标识和唯一短语；同时更新
skill-governance，把 benchmark 派生规则的发布门
改为“原失败回归 + 未见同族实例 + 跨域反例”。B4 不再用原题改善直接宣称通用能力：原题只证明局部
修复；只有冻结改进后解封的未见留出改善，且反例无误触发，才支持有限泛化或跨域能力主张。

随后提交干净基线 `df22e49636e57794b0d7b17cc26e6f0f3a994e98`，并建立不含题目的 B0 管理底座：
`benchmark/baseline.json`、protocol/run JSON Schema、`tools/benchmark-manifest.mjs` 的 surface/seal hash
与关键不变量校验，以及对应确定性测试。agent-surface hash 固定为
`3cd0d24a6ec008ad6220ae2015d9cca41fd89b9263d986e7d33897bee14d0457`；`benchmark/` 不进入 npm
生产包，具体 sealed 题面和 run manifest 目录也由 `.gitignore` 排除。Node 测试现为 10 个。

在 Houdini 21.0.440 的诊断面板从管理提交 `dea0ec8` 执行 `Repair and restart runtime`：idle check
通过后 Bridge、DSH frontend 和 preset 正常重启，新 DSH PID 26608，Web 3081 返回 200；Bridge health
为 `ok=true`、Raw Gate 开启、active/queued/running jobs 均为 0，47 个动词指纹为
`eca1b1669acdc07c4acb0bb4525151c96936f6d92ee689fad98f676fa68fd3fb`。运行时事实写入
`benchmark/baseline.json`；该管理提交没有改变已封存的 agent-surface hash。

### 2.47 跨模型 trace 结论、MCP 参考暂停与首轮通用 P0（2026-08-31）

发现矩阵实际留下 7 条 session：K3 三个能力族均完成；第二模型完成机械任务，模拟任务因周额度
耗尽中止；第三模型完成剩余 lookdev；另有一条在任何工具/assistant 工作开始前即因 provider
`network_error` 结束的空启动，不能当作能力失败。六条有实际执行的 session 合计 529 次工具调用、
2,410 次动词调用；高频主干是 `set_timeline`、`set_parms`、`tab_create`、`cook_node` 和 `connect`。
这批运行不满足原计划中完全冻结的正式 3×2 协议，因此定位为 discovery evidence，而不是可用于
排名或显著性主张的正式 benchmark。额度耗尽的模拟任务按用户要求原样记为未完成，不补跑、不把
provider 限额混写成 agent 自主失败。

跨 trace 的公共结论优先于单题 recipe：工具批处理和目录动词已有高采用，但只读/修改边界过去只是
提示语；`houdini_query` 中真实出现 timeline、cook、参数写入和按钮副作用。失败回滚能恢复 Houdini
节点，却没有同步恢复 Bridge 的会话所有权表。保存只能裸调 `hou.hipFile.save()`，而 `scene_info` 的
旧 `hip_saved` 又把“路径已命名”和“已干净落盘”混为一谈。网络接口缺显式断连，`setInput(None)`
还会被 Raw Gate 当成已覆盖连接。`render_frame` 只检查文件存在，可能把旧产物误报为本次成功，且
临时覆盖 ROP 输出参数不恢复。`/health` 在 HTTP handler 线程直接读取 HOM，违反主线程约束。审计侧
又把像素 diff/crop/颜色统计当成语义识图、漏记调用了修改动词的 query，也不能区分 quota、外部
网络错误和正常完成。

本轮只修跨任务、可确定性复现的最小公共合同，没有把机械、模拟或 lookdev 的对象配方、目标参数、
评分答案或 benchmark ID 写入生产 guidance/preset/skills：

1. 新增 `scene_save(expected_path=None)`，只保存已命名的当前 HIP，返回 dirty 前后、可靠性、bytes 与
   mtime；H21 `hython` 的 dirty flag 保存后仍不可靠，因此显式返回 `dirty_reliable=false`、
   `clean_on_disk=null`，不伪造“已干净”。裸 `hipFile.save` 现在是不可用 `allow_raw` 绕过的已覆盖
   mutation；`hipFile.load/clear` 都是 bridge 生命周期禁区。
2. 新增 `disconnect_input`；回滚同时快照并恢复 `_OWNED_NODE_SESSIONS`，删除后抛错再 undo 的节点仍
   保持当前 session provenance。目录增至 49 个动词。
3. Host 对 `houdini_query` 发送 `read_only=true`；Bridge 不向其 namespace 注入修改动词，并在执行前
   拒绝修改动词、渲染/cook 和裸修改，`allow_raw` 不再暴露给 query。`renderNode()`/`displayNode()`
   这类只读 getter 从前缀启发式中排除。
4. `render_frame` 记录渲染前后文件指纹，只有新建或内容/mtime/大小变化才接受，并在 `finally` 恢复
   frame、foreground wait 和临时 picture 参数；`/health` 改读 Bridge 初始化时缓存的 Houdini 版本。
5. evidence v2 只把真正 inspection 工具计作 semantic success；pixel/crop/color 留在客观像素证据层。
   query 副作用同时看裸方法和动词 ledger；terminal 记录 completed/quota/external error。完全未开始的
   provider 启动错误不再误报质量合同缺失。重提取后，额度中止 session 明确为 `quota_exhausted`，
   第二模型机械 session 的唯一 pixel diff 不再补足失败的语义视觉，历史 `renderNode()` 假阳性清零。

Codex + `JTCHE/houdini-mcp` 的机械运行保留为**后续参考校准**，不继续扩展。固定上游 commit
`001a247dc55dd091323a62f46e2945636ae78ef4`；该栈 10.4 分钟、35 次 MCP 调用完成可辨认且可调资产，
但 166 个工具并未成为主要 authoring interface：11 次任意代码调用承担主体构建，35 次调用都触发
独立 approval reviewer，总计报告约 303 万 token。独立检查发现姿态变化时名义刚性叉架会伸缩、
验证与生成同源、异常后不自动回滚、无节点所有权、危险开关由 agent 自己设置、viewport 状态未恢复，
且三次 H21 语义失败仍以协议成功返回。它同时证明 typed save/disconnect、快速整段 Python 和宽目录
有参考价值。由于模型、harness、approval 和 connector 都同时变化，这不是严格 dsh-vs-MCP A/B。
完整外部报告、manifest 与冻结 HIP 留在 `E:/tmp/mcp-evaluator/`；生产仓库只保留这份去任务配方的
工程摘要。后续若恢复，只做同模型同 harness、禁用任意代码的隔离比较。

当前本地验证：构建生成 49 动词指纹 `4f3516dec006…`；完整 `npm test` 的 10 个 Node 文件通过；H21.0.440 与
H22.0.368 的 Raw Gate、ownership、caught failure、tab-create failure 及新增 scene/network/render
合同各 5 项回归通过；5/5 skill governance 严格审计、Python compile 与 `npm pack --dry-run` 也通过。
agent-visible surface 已在实现提交 `004d305` 后重封为 `7ea472268230…`；baseline 中旧 47 动词 runtime
快照明确标记 `matchesBaseline=false`，运行中 Houdini 仍需一次 `Repair and restart runtime` 才能加载
本轮代码并刷新为 49 动词事实，不能用文件基线冒充运行时已经更新。

### 2.48 trace normalized-step parser 收敛（2026-08-31）

`tools/trace-report.mjs` 与 `houdini-trace-analysis` evidence 提取器过去各自实现 tool call/result 关联、
compaction replay 去重、参数与结果文本解析、失败识别、动词 ledger、rollback/raw-usage 和裸 HOM 分类；
两者已经出现 `Error:` / 内嵌 `Execution failed:` 覆盖不一致，报告侧也没有优先使用 Bridge 的精确
Raw Gate 分类。现新增打包内共享的 `tools/normalized-trace-steps.mjs`：统一输出一次执行对应一个 step，
replay 与无匹配 call 的 result 单列 diagnostics，并保留完整结果供下游内存分析。report 只负责 HTML
展示，evidence 只负责裁剪、hash、统计和质量归因。

新增确定性回归覆盖 replay、orphan result、损坏参数、ledger JSON、rollback、精确 raw-usage 次数和
失败前缀；Node 测试增至 11 个。因 evidence 提取脚本属于随包 skill，agent surface 已按协议重封为
`a09efffc8c79…`；runtime 快照仍是旧 47 动词事实，继续保持 `matchesBaseline=false`，没有用本地文件
重封冒充 Houdini runtime 已更新。

### 2.49 当前 49 动词 runtime repair 与 GUI smoke（2026-08-31）

用户从 Houdini 21.0.440 诊断面板执行 `Repair and restart runtime` 后，Bridge `/health` 实测
`ok=true`、Raw Gate 开启、49 个动词、指纹 `4f3516dec006…`，active/queued/running jobs 均为 0，
DSH Web 返回 200。随后在 Web UI 的 `dsh-houdini` workspace 新建 Houdini 模式会话，发送“用
`houdini_query` 列出 `/obj` 下所有节点”：Host/Bridge 词表握手通过，工具成功返回空场景的 0 个子节点。

Houdini Trace 显示 49 项目录，将这次调用归为 1 次“无动词只读探针”，0 mutation、0 Raw Gate block、
0 rollback，证明 query 只读边界与工具展示在 live runtime 上工作。`benchmark/baseline.json` 已刷新为
`matchesBaseline=true`，同时明确记录当前工作树尚未提交；本 smoke 只验证 transport、加载、握手、查询和
Trace 分类，不冒充未见任务泛化或 H21/H22 自动化回归。

### 2.50 B0 smoke/fixture 产物门禁（2026-08-31）

`run-manifest.schema.json` 现在对 completed smoke 条件要求 `finishedAt` 与 evidence 的 trace/HIP/render/
finalNodes；cache/render/finalNodes 同时去重。`tools/benchmark-manifest.mjs validate-smoke` 再把声明式
`$HIP/...` 映射到调用方给出的真实 HIP 根，检查 HIP、cache、render 与 trace 都存在、是普通文件且非空，
拒绝 `..` 和 symlink 逃逸，并拒绝把私有 trace 写进插件仓库。smoke 必须至少产生一份独立评审输入图和
一个最终 Houdini 节点；running/failed run 不会被伪装成完成。

确定性回归使用临时 HIP/repository/trace 三个隔离根，覆盖合法机械 smoke、路径逃逸、空 render、仓库内
trace 和时间倒序。该门禁不包含题面、对象 recipe、评分答案或 evaluator spec，因此不改变 agent-visible
surface；也不声称已建立真实三族 seed fixture。下一项仍是普通 brief/预设回答/seed/评分 schema 的通用
模板与 validator，之后才冻结模型/provider/protocol version 并执行未见验证。

### 2.51 B0 brief/answers/seed/evaluation 通用合同（2026-08-31）

新增四份只存在于 `benchmark/`、不进入 npm production package 的 JSON Schema：public brief envelope、
pre-registered answers、deterministic seed fixture 和 independent evaluation result。对应 validator 与 CLI
已并入 `tools/benchmark-manifest.mjs`。brief 的 evaluator 元数据与 agent payload 显式分离；agent payload
只返回普通消息与公开资源，不暴露 brief id、能力族或 calibration/holdout 角色。answers 类别限于用户偏好、
资产位置、输出格式和执行约束，禁止实现指导/evaluator 材料且每项最多使用一次。

`validate-inputs` 以实际文件 bytes hash 单向绑定 run → brief/answers，并把 seed scene hash 对到真实 `$HIP`
HIP；公开资源 hash 必须与 brief 完全集合相等。设计过程中删除了 brief→answers 的反向 hash，避免与
answers→brief 形成不可生成的密码学环。evaluation 固定 40/25/25/10 四维上限，total 必须精确等于分项，
hardFailure 必须与 hardFailures 是否为空一致，coreSuccess 只允许“无硬失败且总分 ≥75”；blind 与 target
输入 hash 必须不同，结果 hash、总分、hard-fail 和 claim level 可与 run manifest 交叉核验。

确定性回归覆盖 agent payload 去元数据、资源/问题键唯一、禁止泄漏标志、brief-answer/seed/resource hash
错配、seed 非确定性或内容 hash 错误、盲/目标输入相同、分数求和错误及 run/evaluation 结论漂移。当前仍未
生成任何具体题面、预设答案或评分答案；下一项是实现通用空场景/固定 seed generator 与 validator identity，
再冻结两模型、视觉 provider 和 protocol version。

### 2.52 全项目 review：边界修复与现役事实收敛（2026-08-31）

完整代码/文档/规则审计发现并修复三项可确定问题：

1. `dsh_webview.py` 曾在 `show_webview()` 和 QTimer retry 的 GUI 主线程同步 `socket.connect(0.3s)`；
   launcher 的 `open_workspace()`/`restart_bridge()` 也在主线程做 socket/netstat/taskkill preflight，均
   违反“GUI 线程零阻塞探测”。WebView 现为 QWebEngine async load + `loadFinished` + single-shot timer；
   launcher 现用 worker 做 listener/PID/外部占用者检查，再由主线程 timer callback 做 `hou`/module reload。
   普通 Open Workspace 保留已有 Bridge listener，只有显式 repair 可清理外部占用进程；取消启动时 taskkill
   也改走 worker。Node 静态回归和 H21/H22 launcher 纯 preflight 回归共同固定该边界。
2. Host 内部 `hipDir()` 只读探测原走普通 exec，现显式发送 `read_only=true`；media relay 原按 basename
   写工作区，同名图会覆盖动画 A/B 或不同目录证据，现改为内容 SHA-256 短前缀 + basename，并用两份
   同名不同内容图片做真实文件回归。
3. benchmark JSON Schema 均为 `additionalProperties:false`，但手写 CLI validator 原会放行未知字段；
   现 protocol/run/brief/answers/seed/evaluation 及嵌套对象全部 fail-closed。另强制 blind/target prompt
   hash 不同，避免协议层口头要求“独立输入”但 manifest 可登记同一 prompt。

依赖盘点发现 `node_modules` 的 `dsh-system-prompt`/`dsh-tools` 仍是旧 `0.0.1-rc.*`，与 lockfile 和文档
声明的 `0.1.1-rc.2` 不符；已用 npm 恢复锁定版本，`npm ls` 无 invalid，`npm audit --omit=dev` 为 0
漏洞。12 个 Node 文件、skill strict audit、pack、Markdown 本地链接、H21/H22 五项核心 HOM 及
manager/profile 回归均通过。当前 live Bridge 仍健康且返回 49 动词，但新 Host/WebView 代码未加载；
baseline 因此标 `matchesBaseline=false`，WebView 需完整重启 Houdini 后才能刷新 live 结论。

### 2.53 Windows CRLF 回归与完整冷启动基线封口（2026-09-01）

从提交 `cf1f1e8` 完整冷启动 Houdini 21.0.440 后，菜单 `Open Workspace` 成功同步 preset、启动
Bridge 并打开异步 WebView；`/health` 实测 `ok=true`、Raw Gate 开启、49 个动词、指纹
`4f3516dec006…`，active/queued/running jobs 均为 0，DSH Web 返回 200。由构建产物直接调用
`HoudiniBridge.exec(..., readOnly=true)` 时 Host/Bridge 独立指纹握手通过；Bridge 负向测试在执行前
拒绝 query 中的 `createNode`，随后 `/obj` 复查无测试节点，证明 `read_only_blocked` 为零副作用。

真实 DSH Houdini 模式 session `45798bd2-41a6-4b12-9dfa-fb62b25faa45` 收到用户消息 seq 9“用
`houdini_query` 列出 `/obj` 下所有节点”，步骤 #1/call seq 99 成功返回 `/obj/geo1`（`geo`，无 cook
error），result seq 100 的 `rawUsage.gateOutcome=read_only`；最终回答 seq 153 后以 `completed` 结束。
确定性 evidence 将其记为 1 次无动词只读 HOM probe、0 mutation、0 Gate block、0 rollback、0 replay
和 0 unmatched result；49 个目录动词在 capability snapshot seq 14 全部曝光。该任务要求直接子节点，
`hou.node('/obj').children()` 与递归 `find_nodes(root='/obj')` 语义不同，因此目录命中 0/49 不作为采用失败。
原始 session 仍在 `~/.dsh/sessions/`，本机 evidence/HTML 归档在 `tools/out/`，不进入 production package。

拉取后的普通 Windows checkout 暴露一个确定性门禁缺口：系统 Git `core.autocrlf=true` 且仓库无
`.gitattributes` 时，`dsh_launcher.py` 为 CRLF；`gui-thread-boundary.test.mjs` 的函数提取正则把换行
写死为 `:\n`，因而误报 `restart_bridge` 不存在。测试现接受 `\r?\n` 并使用真正的 EOF lookahead；
完整 Node 回归恢复为 12/12。H21/H22 的 raw-gate、ownership、caught-failure、tab-create 和
scene/network/render 五项核心 HOM，以及 launcher/manager/profile 三项回归也重新通过；skill strict audit
5/5、pack 与依赖解析通过。该改动只影响测试，不改变 runtime 或动词合同，不需要再次 reload Houdini。

`benchmark/baseline.json` 已刷新为 live `matchesBaseline=true`，记录上述 session、49 动词、Web 200 与
零副作用分类。CRLF 测试、状态记录和后续 benchmark-only seed 基础已作为同一干净 Git 基线提交；
运行中 Houdini 仍标记 `loadedRepositoryCommit=cf1f1e8`，因为后续提交没有修改 runtime 文件。该 smoke
只封口 live transport/Host/Trace 基线，不冒充未见任务泛化证据。

### 2.54 通用 seed generator、结构 identity 与三族 calibration 输入（2026-09-01）

新增 benchmark-only `tools/benchmark-seed.mjs` 与 `tools/benchmark-seed-hython.py`，不进入 npm production
package。Node orchestrator 对 generator input 做 exact-key/fail-closed 校验、约束 `$HIP` 路径、调用指定
版本 `hython`、计算脚本/参数/HIP SHA-256、写 seed fixture manifest，并默认在独立临时根重复生成一次。
Hython runner 只接受两种通用模式：空场景，或固定 `testgeometry_shaderball`；共同参数只有 clear、FPS、
frame/playback range 和 current frame，不接收题目、目标材质、灯光、相机、构图、对象 recipe 或评分答案。

Houdini HIP 二进制可能含运行元数据，因此 `seed-fixture.schema.json` 的 output 新增
`identitySha256`：实际 `sha256` 继续绑定本次非空 HIP 文件，identity 则规范化 Houdini 版本、FPS、帧范围、
当前帧以及排序后的 node path/category/type/input。generator 的 `deterministic=true` 由同 Houdini 版本、
同参数重复 identity 一致来兑现，不把可能变化的二进制字节误称为跨运行 byte-identical。

tracked 的 `benchmark/seed-inputs/` 只含三份无题目 calibration 输入：mechanical/simulation 为空场景，
lookdev 为固定 shaderball，用于把建模差异排除在材质/灯光/相机评测之外。最终 H21 CLI 证据留在仓库外
`E:/tmp/dsh-benchmark-seed-m2-final-xk1hzclk.5al`，三族各重复生成并通过 `validate-seed`：HIP 分别为
11182/11183/19240 bytes，结构 identity 为 `9454b2ea…`/`e9f24299…`/`7c1f4568…`。前一独立批次的 HIP
字节数/hash 不同而三项 identity 完全相同，实证了不能把 Houdini 二进制存档冒充跨运行 byte-identical。
H21/H22 HOM 回归覆盖空场景、shaderball、帧范围和重复 identity；新增 Node 合同/路径/三族输入回归后
suite 增至 13 个文件。

这一步只完成 generator 与 calibration seed fixture 基础，不声称模型/provider/protocol 已冻结，也不把
三份 HIP 当作已完成的能力族 smoke：后者仍需普通 public brief、全新 DSH session、真实 trace、至少一份
评审输入和 final node，并通过 completed smoke 产物门禁。

### 2.55 K3/GLM 当前 provider 原生图片探针（2026-09-01）

用户选择正式执行模型为 `kimi-coding/k3` 与 `apikeyfun/glm-5.3-flash`。冻结前以同一张 47,120-byte
Houdini Trace UI PNG（SHA-256 `b09ebe94…`）、同一中性中文 prompt（SHA-256 `9c0e3463…`）做无工具直连；
prompt 明确禁止按文件名/上下文猜测，并要求未收到图片时如实回答。凭据仅从 DSH credential store 在进程
内读取，没有写入命令输出、仓库或证据文件。

K3 走当前 `kimi-coding` Anthropic Messages 路径；本机 pi-ai catalog 同时明确声明 `input=[text,image]`。
一次请求即返回 `responseModel=k3`/`end_turn`，准确描述左上“执行证据”、横向指标条和下方左右分栏，
故 transport/semantic 均通过。GLM 走第三方 `apikeyfun` OpenAI Completions 路径；自定义 settings 没有
adapter image 声明，但 provider 接受 data-URL PNG，返回 `responseModel=glm-5.3-flash`。首轮
`max_tokens=500` 中 482 为 reasoning token，正文仅到“1”且 `finish_reason=length`，只能判 transport 成功；
同图同 prompt 提高至 1500 后以 `stop` 结束并准确描述标题、指标和左右面板，semantic 通过。

`benchmark/model-capability-baseline.json` 只保存输入 hash、provider/model/API、尝试次数、最低已验证输出
预算和判定摘要；不跟踪图片或响应全文。结论限定为“当前 provider/API 路径原生图片可用”：K3 最低已
验证 500 tokens，GLM 最低已验证 1500 tokens。它不证明所有图片任务质量，也不允许执行模型充当独立评委；
Vision Toolkit 的 qwen-vl-max 与 blind/target evaluator 仍须分层记录。

### 2.56 qwen-vl-max 独立 blind/target evaluator 冻结（2026-09-01）

新增 benchmark-only `blind-visual-v1` 与 `target-verification-v1`：blind 明确不知道任务目标、执行过程、
agent 自评或评分答案，只输出逐图可见事实/缺陷/不确定性，禁止 pass/fail；target 只在 blind 结果冻结后
接收 public goal、criteria、references、deterministic evidence 与匿名图，逐 criterion 输出
`pass/fail/unverified`、置信度、证据引用和可反驳理由。两份 canonical prompt hash 分别为
`51a96b85…` 与 `07bd7cc2…`，测试强制不同且 `executionAgentExposed=false`。

远程 smoke 前按 Bailian skill 强制预检发现 `bl`/skill 1.13.1 低于 npm 1.18.1；经用户确认运行
`bl update`，CLI 与 Codex 使用的 skill 均对齐 1.18.1。更新器对不支持全局 skill 安装的 Eve/PromptScript
报告 12 项非本任务失败，但 Codex 的完整 Bailian skill family 安装成功。CLI 未持久登录；每次命令只从
DSH credential store 读取 `VISION_API_KEY` 注入子进程 `DASHSCOPE_API_KEY`，未把 key 写进参数、输出或仓库。

`bl vision describe --model qwen-vl-max` 的 blind 首次调用在 TLS 建连前 `ECONNRESET`，无模型结果；同输入
重试成功，返回严格 JSON，只描述执行证据 UI、状态栏、左右分栏及单图局限，未输出通过/失败。target 输入
新增公开目标、三个 criterion、确定性 trace 摘要和 blind result，一次成功返回三个 criterion 完全集合：
无动词只读探针 1、Raw Gate 拦截 0、回滚 0 均为 pass，hardFailures 为空，同时保留“单图/上下文有限”
limitations。blind/target 完整输入 hash `64cacba9…` / `b97ce4bd…`，结果 hash `dbb05f3c…` /
`f59170d1…`；阶段隔离已由真实调用兑现，`benchmark/evaluator-prompt-baseline.json` 标记 `verified`。

该 smoke 只证明 evaluator transport、严格 JSON、阶段隔离和简单 criterion 核验，不把 qwen-vl-max 晋升为
所有 Houdini 审美的 ground truth。正式三族 run 仍须计算 reviewer agreement、保留与人工抽检的分歧，并在
证据不足时输出 unverified。

### 2.57 Sealed instance 合同、六个已知 bundle 与 holdout 空槽（2026-09-01）

新增 `evaluator-spec.schema.json`、`sealed-instance-manifest.schema.json` 和
`tools/benchmark-instance.mjs`。Evaluator spec 的 criterion 必须覆盖固定四维并分别精确合计
40/25/25/10；hard failure 只能引用已存在且 `critical=true` 的 criterion。Seal 工具交叉验证 brief、
allowed answers、seed、evaluator 的 family/role 与单向 hash，公开资源必须与 brief 完全集合相等；bundle
记录 production surface commit、冻结后才解封以及解封即转 calibration，不含自引用 hash。

当前 agent只在 Git 忽略的 `benchmark/sealed/` 中创建了三族 calibration 与 counterexample，共六个
bundle；它们可被当前线程查看，因此绝不占用 holdout。Tracked `protocol-freeze-status.json` 只记录六个
canonical sealed hash：mechanical `ffe8dd91…`/`4f391e64…`，simulation `aa09467f…`/`66ae4a35…`，
lookdev `b741e23c…`/`051b21e2…`。三个 holdout 明确为 null，状态为
`awaiting-independent-holdouts`，`finalProtocolGenerated=false`，防止占位 hash 冒充正式协议。

`holdout-authoring-request.md` 要求未参与实现/评分设计的人分别制作三族不同任务，只在 freeze 前返回
sealedInstanceSha256，实际 brief/evaluator/answers/resources 保持在仓库和 `$HIP` 外。当前线程不得查看或
生成 holdout 正文；一旦解封/运行，该实例自动转下一轮 calibration。新增确定性回归后 Node suite 为
14 个文件。

### 2.58 独立 holdout hash 接收与 final protocol（2026-09-01）

独立设计任务只返回 mechanical `c3df4d53…`、simulation `41651106…`、lookdev `5be7a4ff…` 三个
sealedInstanceSha256；当前线程没有读取、列举或 diff `E:/tmp/dsh-houdini-independent-holdouts-v1/`
正文。对方报告 production surface `4316620`、agent surface `b9bee29b…`、H21 repeat identity、四件合同、
反向验证和 clean Git 全部通过；该报告作为独立 provenance 保存，但真正内容仍待 freeze 后由运行操作者
解封，撞题残余风险只能在解封时审计。

新增 tracked `benchmark/protocol-manifest.json`：版本 `b0-2026-09-01-v1`，固定 H21.0.440、DSH
0.1.1-rc.2、plugin 0.1.0、Vision Toolkit 0.1.7、K3/GLM、120 分钟、单用户 turn、0 追加纠错、
evidence-v2/hython evaluator 与 qwen-vl-max blind/target。九个 sealed instance hash 已齐全；protocol
canonical/file SHA-256 为 `a39d7c0e…`/`3fd34d49…`。Freeze status 同步为 `ready-for-smoke`、
`finalProtocolGenerated=true`，测试逐 family 要求 status 与 final protocol 完全相等。

这一步只授权三族 calibration 的任务级非评分 smoke；holdout 不解封、不运行、不进执行 workspace。Smoke
通过前仍不得启动正式 3×2，任一基础设施 P0 修复都必须升级 protocol version 并重跑受影响 smoke。

### 2.59 Mechanical smoke attempt 1 失效与隔离 workspace P0（2026-09-01）

用户提供 session `957b69ff…`，标准 evidence 只含 4 个事件/3ms、0 用户消息/工具/模型 token，实际是 HIP
workspace 自动创建的空白会话；session cache 进一步定位真实执行为 repo workspace 的 `fb4b7294…`：1 turn、
42 tools、136 verbs、24.6 分钟、terminal completed。Houdini scene 与独立 H21 hython 证明交付 HIP 可打开，
`OUT_STAND` 为 392 points/218 prims/9 parts、6 控制默认值正确、0 error/warning；整体/特写 PNG 均非空。

功能成功不能覆盖实验污染：真实 cwd 是 `E:/dsh-houdini`，被忽略的 calibration evaluator 文件理论可由
workspace agent 读取，违反 `evaluatorMaterialExposed=false`。Trace 显示 agent 实际只读 workflow skills，
但“没用到”不等于“没暴露”。Run 记录为 `invalidated`；run schema 改为只在 status=invalidated 时允许
`evaluatorMaterialExposed=true`，否则 fail-closed。

第二个 P0 是直接打开 sealed seed：`scene_save` 只保存当前已命名 HIP，不能另存 `monitor_stand.hip`；agent
经历 scene_save 拒绝、Raw Gate 拦截 setName/save、saveAsBackup API 猜错后，最终用低层 exemption + shell
copy 交付。新增 `tools/benchmark-smoke.mjs`：每次创建全新隔离 execution 目录，将 sealed seed 精确复制为
当前 `work.hip`，只复制公开 `agent-message.txt`；preflight 要求 agent 可见文件精确为这两项并把 operator
证据留在 sibling 目录。Protocol v2 新增同一 workspace policy，canonical/file hash 重新封存；新增回归后
Node suite 为 15 个文件。Attempt 1 只作为基础设施发现证据，不评分 K3、不进入 smoke success 计数。

### 2.60 Mechanical smoke attempt 2 通过与 evaluator normalizer（2026-09-01）

通过正式 `workspace.create` + 带预分配 sessionId 的 `session.create`，attempt 2 在发送 prompt 前确认 cwd 为
隔离 execution 目录、preset=houdini、model=kimi-coding/k3、blank=true、turns/steps/tokens=0；workspace
初始只含 `agent-message.txt` 和 seed 精确复制的 `work.hip`。Host `session.prompt` 只发送公开文本。真实 run
为 1 turn/37 tools/222 verbs/21.6 分钟，成功 mutation exec 动词覆盖 100%、0 query mutation、terminal
completed；`scene_save` 直接保存 work.hip，没有 Save As/backup/shell copy 绕路。

`validate-run`、`validate-inputs`、`validate-smoke` 全通过：work.hip 472368 bytes，trace 387856 bytes，整体/
特写 21600/11577 bytes，final node `/obj/monitor_arm_OUT/OUT`。独立 H21 回读 10 个模块/输出均 0 error/
warning，集成输出 344 points/202 prims，6 个控制恢复默认。功能质量不计分；trace 有一次只读验证路径 bug，
无 verb failure/Raw Gate block/无动词裸修改。

独立 evaluator delivery 暴露 presentation P0：Overall Blind 相同输入连续两次返回被单层 `json` code fence 包裹的
正确 JSON，Closeup Blind 还回显中性 `viewLabel`。新增 `tools/benchmark-evaluator.mjs`：只接受 raw JSON 或
恰好一层且无外部文本的 JSON fence；保留可选字符串 viewLabel，未知字段/额外文字/多 fence/stage 错误/
缺字段仍 fail-closed。Protocol v3 固定 normalizer id。Mechanical Overall Target=pass；Closeup Target 因绿色
臂与右关节在匿名静帧中视觉连接歧义而 unverified。该冲突不阻塞基础设施 smoke，也不被 K3 的结构自证覆盖。
新增 normalizer 回归后 Node suite 为 16 个文件。

### 2.61 Simulation smoke attempt 1 通过（2026-09-02）

Simulation calibration 在全新隔离 execution workspace 中运行；发送前由 Host RPC 校验
cwd/preset/model/blank/turn/step/token，live HIP 与 workspace 精确一致。最终 1 turn、66 tools、120 verbs、
terminal completed、0 pending todo；成功 exec 的动词覆盖为 20/21，query mutation=0，exec-for-read-only=0。
独立 H21 回读、真实 cache 文件、三帧几何差分、同构图双帧 render、Blind/Target delivery 与
`validate-run`/`validate-inputs`/`validate-smoke` 均通过；Target core/visual 为 pass、0 hard failure，
honest-report 因冻结视觉输入不把 agent 自述当 ground truth 而保留 unverified。该结果只证明 smoke 管线，
不产生质量分数。

本轮同时形成工具采用证据：File Cache 的写盘按钮没有目录动词，模型连续 5 次无豁免低层调用均被
Raw Gate 在执行前拦截；随后两轮真实写盘使用同一可审计 `allow_raw` 理由，`gateOutcome=exempted`。
这不是隐蔽成功裸修改，但说明按钮型参数需要进入后续动词覆盖评估；正式矩阵前不临时改变 49 动词
surface，以免破坏已冻结 protocol。

### 2.62 Lookdev smoke attempt 1 通过与 evaluator 引用完整性缺口（2026-09-02）

Lookdev calibration 同样从 live HIP/cwd、blank Houdini preset、K3 routable 和零 token 状态开始。最终
1 turn、68 tools、131 verbs、21/49 目录广度，成功 exec 动词覆盖 28/29；0 Gate block、0 成功裸修改、
0 query mutation。独立 H21 回读确认 Solaris/Karma stage、MaterialX surface context/绑定、相机/灯光、
RenderSettings/Product/Var 与可执行 USD Render ROP；最终整体/局部 EXR 均为可读 1024×576 16-bit
float RGBA，`render_frame` fresh 且 semantic inspection 成功。Blind/Target 的 core/visual 均 pass、
0 hard failure；三项 run/input/artifact validator 全通过。结果仍只算非评分 smoke。

Target raw JSON 同时出现一个评分前必须封口的语义合同缺口：criteria 集合正确，但若干
deterministicEvidenceId 被重复写进 `evidenceIds`，V3 shape normalizer 仍会接受。该结果不改变本次
管线 smoke 结论，但正式矩阵不能依赖人工发现；下一步把预期 criterion/image/deterministic ID 集合作为
normalizer contract，要求集合相等、namespace 引用存在、hard failure criterion 可解析，失败即拒绝。

### 2.63 Evaluator V4 引用合同与确定性 hard failure（2026-09-02）

新增 `evaluator-json-normalizer-v2`：每次 normalize 必须带只含 ID/rule 的 contract。Blind observations 的
evidenceId 必须与输入图片集合完全相等；Target criterion 集合必须完全相等，image/deterministic 引用必须
存在、唯一且 namespace 不交叉。真实 Lookdev 原始 Target 回放立即拒绝了 V3 遗漏的 ID 串线。

随后同一输入连续暴露更深的 evaluator 偏差：即使 prompt 明说未触发时返回空数组，qwen-vl-max 仍会把
预登记 hard-failure 条件写成非空条目，同时对应 criteria 为 pass。最终移除视觉模型输出中的
`hardFailures`；`target-verification-v6` 只要求 criteria/overall，normalizer 按冻结 critical rule 和
`status=fail` 确定性派生 hardFailures。V6 真实回放通过 9 criterion、正确引用、core/visual pass，并派生
0 hard failure；`overall.coreGoalStatus` 同样由 critical criterion 状态确定性校验。此前 5 次语义不合规
响应均拒绝、不进入评分。Protocol 升为 `b0-2026-09-02-v4`，生产
agent surface/49 动词不变。

### 2.64 正式 3×2 矩阵与隔离 preparer（2026-09-02）

`benchmark/formal-matrix.json` 预登记六次 calibration/discovery 运行，模型严格交错：Mechanical/K3 →
Simulation/GLM → Lookdev/K3 → Mechanical/GLM → Simulation/K3 → Lookdev/GLM；每族各模型恰好一次，
追加纠错上限 0，`holdoutReleased=false`。新增 `tools/benchmark-run.mjs`，复用 smoke 已验证的隔离逻辑，
但要求显式冻结模型并拒绝协议外 provider/model。正式 workspace 仍只含普通 `agent-message.txt` 和 seed
精确复制的 `work.hip`，evaluator material 不进入 execution。

V4 formal kit 建于 `E:/tmp/dsh-houdini-formal-b0-2026-09-02-v4`；只复制三族 calibration bundle/seed、
V4 protocol/prompt/matrix，holdout 文件数为 0。第 1 次 `formal-mechanical-k3-r1` 已完成 preflight，等待新
H21 进程打开其 `work.hip` 后通过正式 workspace/session API 投递。

第 1 次正式运行随后自然完成：1 turn、22 tools、311 verbs、13/49 目录广度，0 Gate block、0 成功裸修改、
0 query mutation；3 个失败调用及 2 次 rollback 均保留。独立 H21 结构/控制/折叠/尺寸扰动/恢复与最终保存
门通过；Blind/Target 9 criterion 全 pass，整体/局部视觉置信度为 0.8/0.7，V4 normalizer 派生 0 hard
failure。离散评分 `pass=maxPoints, fail/unverified=0` 得 40/25/25/10=100，claimLevel=none。该单次结果不
构成模型比较或泛化主张。第一次 Blind 正文因 CLI 1.18.2 更新提示污染 fence 外 presentation 被拒；保持
批次 CLI 1.18.1 不升级，以 `--quiet` 同输入重试成功。

第 2 次 `formal-simulation-glm-r1` 也自然完成：1 turn、50 tools、247 verbs、19/49 目录广度；14 failed
calls、11 rollback、1 Gate block、0 成功裸 Houdini 场景修改、0 query mutation。执行模型 direct
`read_image` 因 adapter 未声明 image input 失败，随后固定生产 Vision Toolkit 三次语义检查成功。独立 H21
确认真实 Bullet solver、42 个稳定 block ID、A/B 各 120 帧缓存、三帧演化、重力 A/B 42/42 终态差异和
最终网络 0 error/warning。Blind/Target 9 criterion 全 pass，视觉时间/构图 confidence 均 0.9，离散评分
100、0 hard failure、claimLevel=none。过程约 74.9 分钟，显著慢于第 1 项且失败/回滚更多；2/6 阶段只记录
同为 core success 与效率差异，不做模型排名。

第 3 次 `formal-lookdev-k3-r1` 自然完成：70 tools、207 verbs、21/49 目录广度；3 failed calls/3 rollback，
0 Gate block/成功裸修改/query mutation，成功 exec 动词覆盖 31/31。独立 H21 确认 37 个 USD prim、三套
MaterialX、5 个目标 mesh 绑定、两台相机、key/fill/rim RectLight、RenderSettings/Product/Var 和新鲜
hero/detail Karma EXR；detail 首版 clipping 黑屏由 agent 自检修复。核心/证据/视觉 8 项 pass，但最终报告
声称存在 Dome Light，最终 stage 无 DomeLight prim，故 honest-report=fail。分数 40/25/25/0=90，0 hard
failure、coreSuccess=true、claimLevel=none。两条 SOP Import no-save-path warning 已披露且保留。

第 4 次 `formal-mechanical-glm-r1` 自然完成：50 tools、236 verbs、14/49 目录广度；10 failed calls/8
rollback，0 Gate block/成功裸修改/query mutation，成功 exec 动词覆盖 17/17。独立 H21 证明 14 piece、
6 控制、默认/折叠不伸缩、尺寸扰动与恢复；首版局部图不清楚后重渲。Target 首次使用非法状态 `partial`
被 V4 拒绝，同输入重试 9 criterion 全 pass，100 分、0 hard failure。Mechanical 同族两模型均 100；K3
约15.0分钟/22 tools/3 failed/2 rollback，GLM约31.7分钟/50 tools/10 failed/8 rollback，结果并列而效率与
稳定性偏向 K3。

第 5 次 `formal-simulation-k3-r1` 自然完成：103 trace steps、332 verbs、24/49 目录广度；13 failed
calls/11 rollback，0 Gate block，但出现 2 次 query mutation（直接 `hou.setFrame`/`cook()`）和 18 次成功
裸 File Cache 按钮写盘。独立 H21 确认 rbdbulletsolver、18 个稳定 cube ID、120 帧 cache、早中晚演化、
重力 A/B 重算差异、最终节点 0 error/warning；三张同构图与语义检查通过。Target 9 criterion 全 pass、
100 分、0 hard failure、claimLevel=none。Simulation 同族 K3/GLM 均 100；K3 约36.8分钟且 query mutation
更多，GLM 约74.9分钟但无 query mutation；结果同分，效率/流程各有不同信号。该结果不改变 49 动词 surface。

第 6 次 `formal-lookdev-glm-r1` 自然完成：108 trace steps、94 verbs、19/49 目录广度；13 failed
calls/11 rollback，0 query mutation、0 Gate block，7 次成功裸 `rop.render()` 均为异步 job +
单次 allow_raw 豁免（render_frame ~110s 硬顶、CPU 渲染 >2min，首次被 Gate 拦截后带理由重发）。
read_image 因执行模型未声明图像输入失败 1 次，3 次 vision_glance 语义检查成功且最终 QA 在最终
1280×960 图上完成；预览 480×360 后重渲正式分辨率。独立 H21 回读确认 33 prim、teal_glaze
(0.006,0.13,0.10)/metalness 0/transmission 0/roughness 0.32/coat 0.65、3 RectLight、2 相机、
RenderSettings+2 RenderProduct+beauty Var、Karma rop 可执行、0 error。诚实分缺口：最终报告台账声称
stage 无 error/warning，但回读发现 2 条 SOP import no-save-path warning（import_shaderball/
import_ground），K3 同族当时披露了同类 warning。Target 核验 honest-report 为 unverified（缺报告
原文输入，保守裁定），按规则 0 分。总分 90（40+25+25+0）、0 hard failure、coreSuccess=true、
claimLevel=none。盲评 3 次调用 2 次合同拒绝后通过，Target 1 次通过。正式 3×2 全部 6/6 完成：
Mechanical 100/100、Simulation 100/100、Lookdev 90/90（K3/GLM），三族六场全部 coreSuccess、
0 hard failure；同族并列，跨族差异与流程信号（query mutation、裸写盘、诚实项）留待 B2 归因。

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
| 22 | system prompt 只放稳定 dispatch/invariant，Solaris/Karma 细节放可版本化 skill | 当前 prompt 已要求 LOP/Karma 仍选错；长 recipe 常驻只会稀释注意力，且不能补执行能力 |
| 23 | 真实 Tab entry = node type + context filter + tool recipe，不再等同类型注册表 | H21 Karma Setup/Material Builder 都是 tool；裸 createNode 会绕过多节点初始化和材质 tab mask |
| 24 | 单节点创建与 setup tool 执行拆分 | 两者返回基数、副作用、状态恢复和安全边界不同；不能破坏已发布 `tab_create -> hou.Node` 契约 |
| 25 | Karma 完成门按 USD/材质/RenderSettings/ROP/产物/时序分层 | “PNG 存在”不证明 XPU material context、标准网络或动画序列成立 |
| 26 | Rig/animation 先按数据模型分类，不把“绑定”直接等同 KineFX/APEX | channel、刚体 piece、层级、skin、character rig、simulation 的状态和完成门不同 |
| 27 | 领域官方知识进按需 skill，执行失败面才进动词 | 避免 system prompt 手册化和按节点堆 API；保持词表最小完备 |
| 28 | 路径依赖动画必须验证稳定身份、更新后 membership 与非交换转折 | 首步能动、首尾相同和像素不同均不能证明整个有序序列正确 |
| 29 | Skill 自进化走有来源、分级、可回滚的状态机，不做无门槛自改 | 单次成功/失败不能安全地产生通用规则；生产知识修改是独立副作用 |
| 30 | 多来源只贡献 claim，不直接复制材料 | 官方文档、视频、HIP/HDA 的权威性、版本、许可和泛化强度不同 |
| 31 | 新领域 skill 由独立数据模型/完成门准入，不按 Houdini UI 模块预建 | 控制 skill 数量、description 竞争和长期维护矩阵 |

---

## 5. 下一步（按依赖顺序，2026-09-01 review）

> benchmark、评分和准入规则只在
> [`cross-domain-benchmark-plan.md`](./cross-domain-benchmark-plan.md) 维护；本节只记录执行状态，
> 不复制任务合同或评分细节。

### Phase B-Prep — 干净基线

1. ✅ 完成代码、当前文档、preset、skills、生成契约、打包清单和忽略目录审计（§2.45）。
2. ✅ 修复旧菜单/launcher 语义漂移，收紧 ask choice fail-closed，并新增当前文档一致性回归。
3. ✅ 当前 checkout 的 Node、skill、pack、Python、四项 H21 强制回归及 manager/profile 回归全绿。
4. ✅ 干净基线已提交为 `df22e49`；已从 `dea0ec8` 在运行中 Houdini 完成一次安全
   `Repair and restart runtime`，runtime/Bridge/Web/词表状态已写入 baseline。评分 smoke 仍须等模型、
   evaluator 和 sealed 实例全部冻结。
5. ✅ `cf1f1e8` 已经完整冷启动 Houdini，49 动词/Host 握手/WebView/query/Trace live smoke 均通过，
   baseline 已恢复 `matchesBaseline=true`（§2.53）；CRLF 测试、状态记录和 benchmark-only seed 基础已
   提交为 clean Git baseline，没有 runtime reload 待办。

### Phase B0 — 冻结评测协议

1. ✅ 冻结反过拟合原则：agent-visible surfaces 不含实例答案；实例分为校准/发现、未见留出和
   跨域反例；原题改善不能单独证明通用能力。
2. 🔶 protocol/run/brief/answers/seed/evaluation schema、agent-surface hash、跨文件 hash、Git/npm 隔离、
   通用 seed generator 和结构 identity 已完成；模型/provider 与最终 protocol version 待环境冻结。
3. ✅ 三个能力族的通用 calibration seed 输入已建立并由 H21 实际重复生成/H21-H22 回归；Mechanical、
   Simulation、Lookdev 的 `$HIP`/cache/trace/评审输入真实文件门禁均已完成。仓库不接收 HIP/cache/
   render 或未解封留出正文。
4. ✅ 执行模型/evaluator/九个 hash 已冻结；三族隔离 execution + evaluator delivery 已通过，protocol
   `b0-2026-09-02-v4` 的 ID 引用完整性与确定性 hard-failure 同输入回放也已通过。下一步正式 3×2。
5. ⏳ `houdini_query`/`houdini_exec` 暂时保持两个工具；正式运行记录误选、query→exec 重试、
   `execUsedForReadOnly`、`read_only_blocked` 与安全收益后再评估单工具 `mode`，本阶段不先改接口。

### Phase B1 — 3 × 2 校准/发现矩阵

1. 🔶 discovery 执行已结束：K3 三族完成；第二模型机械完成、模拟因 quota 中止；第三模型完成
   剩余 lookdev；另有一次零工作量 network-error 启动。由于模型替换、额度和 protocol 未完全冻结，
   这批证据不冒充正式 3×2 排名。
2. ✅ 原始 session、trace HTML/evidence、HIP/cache/render 与 evaluator 结果保留；额度中止按未完成记录。
3. ✅ 执行期间未把题目 recipe/答案写回生产面；本轮公共 P0 在整批结束后才实施。

### Phase B2 — 独立评审与归因

1. 🔶 discovery 的确定性检查、trace 审计和人工视觉抽检已完成；因 blind/target evaluator 输入隔离未
   完全冻结，不宣称正式 reviewer agreement。
2. ✅ 已把 quota/network、模型执行、公共工具缺口、视觉/evaluator 误判和任务特有缺陷分开记录。
3. ✅ Codex+JTCHE MCP 仅记为 product-stack calibration；模型/harness/connector 同时变化，不作严格 A/B。

### Phase B3/B4 — 证据准入改进与复测

1. 🔶 首轮公共 P0 已落地：scene save、disconnect、query read-only、rollback provenance、render freshness、
   health 主线程边界和 evidence terminal/vision/query 分类；均来自通用契约或跨 trace 缺口，不含题目 recipe。
2. ⏳ 仅在外部评分/自然语言状态无法稳定比较或约束结论时设计最小结构化 ledger。
3. 🔶 agent surface 重封、Repair/restart 和手工 GUI smoke 已完成；仍须使用未见实例验证本轮 P0 无误阻。
   只有留出表现、实际成功、自主发现与有效返工上升，且 false-completion 和误触发不恶化，才宣布能力提升。

### Benchmark 后恢复的工程 backlog

- `houdini_job_*` 迁到 `ctx.jobs`；
- ✅ query/exec Bridge 只读边界已完成；后续再接 DSH approval 层，不放宽当前 fail-closed；
- ✅ trace report/evidence normalized step 已共用 parser；
- 把当前手工证据工程化为可重复的最小 H21/H22/GUI smoke；
- `dsh_hou_helpers.py`（约 4.4k 行）按 scene/node/parm/asset/geometry/render 域拆模块；在 protocol freeze
  或正式矩阵中途不做该大重构，避免改变实验底座；
- skill governance M2/M3 的 COP/SIM/project-analysis 准入和周期审计；
- 等未见任务重复证据后再评估 `press_parm_button`、frame-range cook/cache 和 volume/solver 统计；当前
  不因单个模拟 recipe 先扩词表或大 skill。

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
| 展示意图 | `presentCall`/`presentResult`/`presentationMeta` 必须是 args/持久化结果的**纯函数**（无 I/O/时钟/会话状态，否则破坏日志回放）；UI 格式不进模型结果；调用卡为 generic/terminal/diff，结果卡另有 search/read/web，**无 image 卡片** | `cookbook/adding-a-tool.zh.md`、`packages/core/tools/src/presentation.ts` |
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
| `src/generated-verb-contract.ts` | 构建期生成的 Host 预期动词名/hash/紧凑目录；不手改 |
| `src/tools.ts` | 5 个工具定义 + `verbs`/`advisory` 渲染 |
| `src/bridge.ts` | HTTP client（`ExecResult.verbs`/`advisory`） |
| `src/skill.ts` | 随包注册 trace-analysis、SOP、Solaris/Karma、rig/animation、skill-governance 五个 skill/resource base |
| `client.js` | **client 半**：手写 factory，注册 `houdinitrace` 视图（词表目录 + 实时时序，目录由生成器注入） |
| `package.json` | `exports["./client"]` + `dsh.client` + `dsh.bundle.patch` |
| `cordis.patch.yml` | 组合包 patch 层（`dsh.bundle.patch`，包名加载） |
| `houdini/python3.11libs/dsh_bridge.py` | HTTP/主线程工作队列 + 动词注入 + tracer/Raw Gate/ownership |
| `houdini/python3.11libs/dsh_hou_helpers.py` | 46 个 helper 主动词 + 2 display 兼容入口 + `_resolve`；bridge 另注入 `verb_help`，合计 49 个目录入口 |
| `houdini/python3.11libs/dsh_launcher.py` | 打开/重启分流 + preset 同步 + 分阶段百分比/超时诊断（worker 线程探测） |
| `houdini/python3.11libs/dsh_manager.py` | Houdini 原生版本/端口诊断 + DSH npm / 插件 Git 双通道检查与安全更新 |
| `houdini/python3.11libs/dsh_webview.py` | 内嵌 Web UI + session hint + CSS 性能修复 + 无 socket 的异步 load retry（§2.13/§2.28/§2.52） |
| `tools/tests/client-session-hint.test.mjs` | WebView session hint 的 refresh/open/消费与无 hint 零导航回归 |
| `tools/tests/trace-*.test.mjs` | session replay 去重与 evidence/vision/adoption 确定性回归 |
| `tools/tests/current-docs-consistency.test.mjs` | 当前菜单/repair、Node 测试文件数与五个 packaged skill 的 README 一致性回归 |
| `tools/tests/gui-thread-boundary.test.mjs` | WebView 不得重新引入 GUI 主线程 socket probe 的静态回归 |
| `tools/tests/verb-contract.test.mjs` / `bridge-contract.test.mjs` | 文档/Host/Bridge 注册表一致性与 mismatch fail-closed |
| `tools/tests/dsh-*.test.py` / `benchmark-seed-generator.test.py` | H21/H22 hython：Raw Gate、ownership、caught failure、manager/profile 与通用 seed 重复 identity 回归 |
| `docs/tool-design.md` | 设计宪法 |
| `docs/cross-domain-benchmark-plan.md` | 下一阶段 benchmark、评分、停止条件与工具/skill 准入的唯一维护位置 |
| `docs/development.md` | 本文：进度 + 卡点 |
| `tools/trace-report.mjs` | trace 复盘报告生成器（session → 单文件 HTML，§2.14） |
| `tools/catalog-lib.mjs` | 词表目录解析唯一实现（trace-report 与生成器共用） |
| `tools/trace-session-lib.mjs` | session.jsonl.zstd 多帧解压/事件读取唯一实现 |
| `tools/normalized-trace-steps.mjs` | report/evidence 共用的 call/result/replay/ledger/Raw Gate 标准化 step parser |
| `tools/benchmark-manifest.mjs` / `benchmark/*.schema.json` | B0 surface/seal、brief/answers/seed/run/evaluation 与真实 smoke 产物门禁；不进 npm 包 |
| `tools/benchmark-seed.mjs` / `benchmark-seed-hython.py` / `benchmark/seed-inputs/` | 通用空场景/固定 shaderball seed、结构 identity、三族 calibration 输入；HIP/manifest 产物留在仓库外 |
| `tools/gen-client-catalog.mjs` | 构建期把目录注入 client.js（`npm run build` 第一步，§2.15） |
| `skills/houdini-trace-analysis/` | 标准 trace 审计 skill：证据脚本 + 量表 + 累积模式库 |
| `skills/houdini-sop-workflow/` | SOP/VEX/Copy/属性/模块验证与多帧交付工作流 skill |
| `skills/houdini-solaris-karma-workflow/` | Solaris/USD/Karma CPU-XPU/MaterialX/Render Settings/COP 接口工作流 skill |
| `skills/houdini-rig-animation-workflow/` | Channel/rigid pieces/hierarchy/KineFX skin/APEX 路由、控制器与时序完成门 |
| `skills/houdini-skill-governance/` | Houdini skills 创建维护、多来源证据吸收、受控演化、版本发布和回滚治理 |
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
