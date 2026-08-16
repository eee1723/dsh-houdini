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
| 动词词表（bridge namespace） | ✅ | 13 个动词 + `_resolve` |
| 动词追踪 tracer（Phase 1） | ✅ 已实现、待激活 | `verbs` 字段 + `[verb]` stdout 行 |
| Houdini Trace 视图（Phase 2） | ✅ 代码完成 | `client.js` + `dsh.client` 声明 |
| plugin persona 中性化 | ✅ | GUIDANCE 只讲工具用法，persona 移入 preset |
| houdini 模式 preset | ✅ | `~/.dsh/.agent-presets/houdini/` + `presets/houdini/`，校验通过 |
| Houdini 侧一键启动/桥/WebView | ✅ | `dsh_launcher.py`（profile 模式）等 |

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
13 个动词 = 类型目录（`search_tab_menu`/`resolve_latest_type`）+ node 域
（`tab_create`/`find_nodes`/`graph`/`describe`/`connect`/`rename_node`/`delete_node`/`cook_node`）
+ parm 域（`list_parms`/`read_parms`/`set_parm`）。

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

---

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

---

## 5. 下一步（分阶段计划，2026-08-16 按 dsh 官方规范重排）

> 规范依据见 §6；与 `tool-design.md` §7 的技术项（batch 端点、undo group、
> `scene_*`/`viewport_*`/`hda_*` 域）互补，可穿插进行。

### Phase 0 — 收尾与稳定性

1. ✅ 修 launcher 冷启动竞态（§3.2）：等 3081 就绪再开 UI（QProgressDialog + QTimer）。
2. ✅ 端到端验证（自行车会话，见 §2.7）：preset 身份正确、工具链路全通、
   `houdinitrace` 未显示的根因已修（exports 缺 `./package.json`）；verbs 缺席的根因
   是**模型不用动词**（guidance 已注入但被忽略），非管道断裂——转化为 Phase 1 第 8 项。
3. ⏳ 新增 `houdini-dev` preset（standard + dsh-houdini + coding persona，用于开发/测试）。
4. ⏳ 「Houdini 菜单打开默认切到 houdini 模式」：查 default preset / 深链（`dsh web` 无 `--preset` flag）。

### Phase 1 — 合规对齐（不改行为，只贴规范）

5. ⏳ devDependency `dsh-tools` 对齐运行时 `0.1.0-rc.6`（消除 schema DSL 漂移风险）。
6. ⏳ 5 个工具补 `presentCall`/`presentResult`（terminal/generic 卡片）+ `presentationMeta`
   （§6 硬约束：必须是 args 的纯函数，UI 格式不进模型结果）。
7. ⏳ TS 侧最小测试（现状仅 Python 侧 `houdini/tests/regress_verbs.py`）。
8. ⏳ 提升动词采用率（§2.7-1）：preset persona 强化「优先动词」+ 桥侧检测到裸
   `createNode(` 时在结果追加提示。

### Phase 2 — 视觉反馈闭环（README 路线 #1）

8. ⏳ 桥加 `/screenshot`（viewport 截屏 / flipbook 帧）；经 `ctx.attachments.saveImage()`
   返回 image 内容块；执行前校验模型路由声明 image 输入模态（§6 约束，写进文档）。

### Phase 3 — 迁移官方 jobs 服务（README 路线 #2）

9. ⏳ `houdini_job_*` 迁到 `ctx.jobs`（§6 红线），获得 `job_list`/`job_kill`/`job_output`
   + 完成通知；桥侧 job 端点退役。迁移前的小改：`houdini_job_status` 加
   `wait`/`timeout_ms` 长轮询参数（§2.7-3 的 loop guard 误报，对齐 `job_output` 形态）。

### Phase 4 — 权限分层（README 路线 #4）

10. ⏳ `tools/pre-execute` 小插件：`houdini_query*` → `next()`，`houdini_exec*` → `ask`（§6 约束）。

### Phase 5 — 卡片与知识沉淀

11. ⏳ houdinitrace 视图升级：纯文本块 → 结构化表格（状态色标 + 展开入参/出参）；
    优先 host 半渲染意图，不够再写 client 半 keyed renderer（`'tool.call.toolview'` slot）。
12. ⏳ `ctx.skills.register()` 打包 Houdini 工作流 skill（SOPs/VEX 惯例、hou API 陷阱）。

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
| `src/tools.ts` | 5 个工具定义 + `verbs` 渲染 |
| `src/bridge.ts` | HTTP client（`ExecResult.verbs`） |
| `client.js` | **client 半**：手写 factory，注册 `houdinitrace` 视图 |
| `package.json` | `exports["./client"]` + `dsh.client` + `dsh.bundle.patch` |
| `cordis.patch.yml` | 组合包 patch 层（`dsh.bundle.patch`，包名加载） |
| `houdini/python3.11libs/dsh_bridge.py` | 桥 + 动词注入 + tracer |
| `houdini/python3.11libs/dsh_hou_helpers.py` | 13 个动词 + `_resolve` |
| `houdini/python3.11libs/dsh_launcher.py` | 一键启动/重启/WebView |
| `docs/tool-design.md` | 设计宪法 |
| `docs/development.md` | 本文：进度 + 卡点 |
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
