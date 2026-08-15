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

---

## 5. 下一步

1. ✅ 收敛启动路径：`dsh_launcher.py` 改 profile 模式，preset 唯一挂 dsh-houdini。
2. ✅ plugin persona 中性化：GUIDANCE 去 persona，persona 移入 preset。
3. ⏳ 端到端验证：重启后，`houdini` 模式身份正确、`创造` 模式不再注入 Houdini 上下文。
4. ⏳ 新增 `houdini-dev` preset（standard + dsh-houdini + coding persona，用于开发/测试）。
5. ⏳ 「Houdini 菜单打开默认切到 houdini 模式」：查 default preset / 深链（`dsh web` 无 `--preset` flag）。
6. ⏳ 激活 Phase 1 tracer：重启 bridge/frontend，验证工具结果出 `verbs`、`houdinitrace` 标签页显示调用。
7. ⏳ 视图升级：纯文本块 → 结构化表格（状态色标 + 展开入参/出参）。
8. ⏳ 权限分层：query 自动放行 / exec 审批。
9. ⏳ 后续能力（见 `tool-design.md` §7）：batch 端点、undo group、`scene_*`/`viewport_*`/`hda_*` 域、Skill。

---

## 6. 文件清单

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
  且 `exports["./client"]` 指向 client bundle；bundle 必须以
  `window.__ModuleLoader__.load({ id: 包名, factory: (require) => exports })` 注册，
  `require(...)` 只解析 seed word（`react` 等）/ boot graph 行，**不得**跨插件 import 业务值。
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
