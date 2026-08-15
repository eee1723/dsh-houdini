# dsh-houdini 动词词表设计（宪法）

> 本文是 dsh-houdini「场景操作动词」的**唯一真相源**（single source of truth）。
> 代码实现（`houdini/python3.11libs/dsh_hou_helpers.py`）是本文的快照。
> **改任何动词必须同步改本文**；README 只放指针，不复制细节。
>
> 设计对标三份参考：Houdini-Agent、fxhoudinimcp、kleer001/houdini-mcp（见 README 引用）。

---

## 1. 定位：动词层是「意图层」，不是「hou 的 1:1 包装」

agent 执行代码时，`hou` 本身可用（逃生舱）。动词层做的是把 Houdini 的
**惯例、校验、错误处理、最新版本解析**固化下来，让 agent 写一句 `set_parm(...)`
而不是十几行裸 `hou`。核心收益：

- **省 token**：返回精简、JSON 安全、无 traceback 噪音。
- **稳**：集中错误处理比 agent 每次手写 try/except 可靠。
- **准**：把「查不猜」、最新版本、命名冲突、引用检查等边界统一。

类比：`hou` 是 bash，动词是 `ls` / `find` / `sed` / `rm` 那套命令词汇。

---

## 2. 两轴模型：动词轴 × 域轴

分类按两个**正交**维度组织，不按一条线：

- **动词轴（语法，通用不变）**：find / create / read / update / delete / connect / verify
- **域轴（名词，逐域扩展）**：node → parm → geometry → scene → viewport → asset → render/sim → code

CRUD 对每个域都成立（能建节点、建参数、建 keyframe、建 HDA），所以
**「域」是扩展单元，「动词」是复用单元**。

### 8 个域

| 域 | 现状态 | 预留动词（将来，示意） |
|---|---|---|
| **node / network**（场景图） | ✅ 已实现 | network box / sticky note / layout（本质都是网络对象） |
| **parm**（依附 node） | ✅ 已实现 | 表达式 / keyframe / spare parm / lock |
| **geometry**（几何数据） | 预留 | `geo_summary` `geo_attrs` `geo_bbox` `geo_export` |
| **scene**（工程/会话） | 预留 | `scene_save` `scene_info` `scene_load` `context` |
| **viewport**（视口/UI） | 预留 | `viewport_screenshot` `viewport_frame` `viewport_camera` |
| **asset**（HDA） | 预留 | `hda_create` `hda_install` `hda_list` |
| **render / sim**（重型） | ✅ job 通道已有 | `render_start` `sim_step`（走 job） |
| **code**（逃生舱） | ✅ `houdini_exec` | — |

### 命名约定

1. **域编码进名字**：`geo_*`、`scene_*`、`viewport_*`、`hda_*` 前缀。
2. **node 是默认域，用简名**（`find_nodes` `connect` `cook_node`…），其余域一律带前缀。
3. 这样将来加域不冲突，agent 一眼看出动词属于哪个域。

---

## 3. 铁律（每个动词都必须遵守）

1. **统一引用约定**：动词里表示「节点」的参数一律接受 `hou.Node` **或** path 字符串，
   内部 `_resolve()` 统一转换；不存在则抛一条明确的中文错误。
2. **返回精简、JSON 安全**：只吐 path / 小 dict / list / None；`hou.Vector3/Matrix/Color`
   等转成 list；不吐 hou 对象、不吐 traceback 噪音。
3. **`hou` 永远是逃生舱**：动词覆盖不了的复杂场景，agent 可直接裸写 `hou`。
4. **只增不改**：签名一经发布即冻结；后续只加新动词、不改旧的。
5. **动词 = 语义动作**：一个动词一个语义，内部把校验/纠错/引用检查固化，
   不做 1:1 的 `hou` 转发。

---

## 4. 动词表（当前已实现）

### 类型目录（回答「能建什么」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `search_tab_menu(category, query)` | 列出某 context 下匹配的节点族 + 最新版 | dict |
| `resolve_latest_type(category, base)` | 某族最新版全名（内部为主） | str |

### node 域（场景图）

| 动词 | 语义 | 返回 |
|---|---|---|
| `tab_create(parent, type_name, name=, inputs=[...])` | 建节点：最新版 + shelf 初始化 | `hou.Node` |
| `find_nodes(pattern="*", category=None, node_type=None, root=None)` | 找**已存在**节点（扁平清单） | path 列表 |
| `graph(node, depth=1, direction='both')` | 拓扑：inputs / outputs / parm_refs | dict |
| `describe(node)` | 状态 + 几何摘要 + 帮助元数据 | dict |
| `connect(src, dst, index=0)` | 连线（src 输出 → dst 输入）；落口与请求不一致时返回里带 `note` | dict |
| `rename_node(node, name)` | 重命名 | 新 path |
| `delete_node(node)` | 删除（返回被表达式引用的上游） | dict |
| `cook_node(node)` | cook + 采集 error/warning | dict |

### parm 域（依附 node）

| 动词 | 语义 | 返回 |
|---|---|---|
| `list_parms(node)` | 参数**目录**：名字/标签/类型/帮助（导航用，不给值） | list |
| `read_parms(node, changed_only=True)` | 参数**值**：默认只看非默认 + 带表达式 + 被引用的（意图解读）；表达式参数附 `referenced_parm`，被引用参数标 `referenced_by` | list |
| `set_parm(node, name, value)` | 设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠） | dict |

### 拆分决策：`list_parms` vs `read_parms`

两个动词回答**两个不同问题**，合并会互相污染：

- `list_parms` → 「我想改的参数叫什么名？」（导航，类似 `ls`）
- `read_parms` → 「这个节点实际在干什么？」（意图解读）

---

> **实测 API 基线（H21.0.440 / py3.11 与 H22.0.368 / py3.13 一致）**：
> `Parm.set(str)` 对数值参数抛 TypeError（表达式必须走 `setExpression`）；
> `hou.Parm` 无 `isReferencedBy`，引用自省用 `parmsReferencingThis()` / `getReferencedParm()`；
> `Node.inputs()` 是紧凑元组（无 None 占位，但代码仍做防御）；`setInput` 只接受 `hou.Node` 对象。

---

## 5. 场景定向模型（LLM 在 Houdini 任务里需要哪些信息）

| # | 维度 | LLM 用它判断什么 | 动词 |
|---|---|---|---|
| 1 | 拓扑（DAG） | 我在链条哪、动谁影响谁 | `graph` |
| 2 | 生命周期状态 | 健康吗、能 cook 吗、被 bypass 吗 | `describe` |
| 3 | 有意义的参数 | 和默认比改了啥、有无表达式引用 | `read_parms` |
| 4 | 数据流（几何/属性） | 流过什么数据、要不要加操作 | `describe` |
| 5 | 工作上下文 | 人现在在看/选什么 | `scene.context`（预留） |
| 6 | 错误 | 哪里断了、怎么修 | `cook_node` + `describe` |

其中 #1（拓扑）、#3（有意义参数）、#2（状态）最容易被忽视但最能提升判断力。

---

## 6. 帮助文档能力（三阶段）

| 阶段 | 内容 | 成本 | 状态 |
|---|---|---|---|
| Stage 1 | `describe`/`list_parms` 顺带返回免费元数据：`defaultHelpUrl()`、`embeddedHelp()`（HDA 常有）、parm `help()` | 免费 | ✅ 已实现 |
| Stage 2 | `node_help(node_or_type, parm=None)` 动词，fallback：embeddedHelp → 本地帮助服务器 → SideFX 在线 URL（agent 用 `web_search` 抓） | 中等 | roadmap |
| Stage 3 | 离线全文检索（BM25 over `$HFS/help`），对标 fxhoudinimcp/kleer001 | 大 | roadmap |

> 实测结论：stock 节点内联帮助在 HOM 里基本是空的（`description()` 只回 label、
> `embeddedHelp()` 空、`parmTemplate.help()` 空、`helpUrl()` 需帮助服务器在线）；
> 真正文本在 `$HFS/houdini/help/`。所以 Stage 2/3 不是「顺手就有」，需专门建设。

---

## 7. 后续路线（与 README 对齐）

1. batch / 原子建图端点（fxhoudinimcp 实测：主线程 hop 底价 ~50ms，
   10 节点逐次 ~800ms vs 一次往返 ~66ms —— batching 值一个数量级）。
2. bridge exec 加 undo group 包裹（kleer001 的稳定性做法）。
3. `scene_*` / `viewport_*` / `hda_*` 域。
4. Skill 脚本（几何分析，对标 Houdini-Agent 的 `skill:xxx`）。
5. 权限分层（query 自动放行 / exec 审批）。

---

## 8. 动词追踪（houdinitrace）

为便于「看清动词词表调用情况、按观察调整词表」，bridge 给每个动词包了一层
**运行时 tracer**（`dsh_bridge.py`）：

- 每次 exec 的返回 envelope 里多一个 `verbs` 字段：列表，每项记录
  `{verb, args, kwargs, ok, result/error, ms}`。
- `hou.Node` 入参/出参自动转成 `{"node": path}`，其余递归转 JSON 安全形式。
- stdout 同时打印一行 `[verb] 名称(入参) -> 出参 (耗时)` 摘要。
- 失败调用以 `ok: false` + `error` 记录，不改变原抛错语义。

这是 **houdinitrace 视图的数据层**。Phase 2（已实现）：dsh-houdini 的 client 半
（`client.js`，手写 CJS factory，免 bundler）在 `conversation.view` 上注册
`id="houdinitrace"` 标签页（与 `chat`/`trajectory` 并列），从 `useSession(snapshot.nodes)`
里过滤 `houdini_*` 的 `ToolResultNode`、抽取 `verbs (...)` 段渲染成调用卡。

> 注：dsh 里用户说的「trace」即 `dsh-client-ui-trajectory` 的「轨迹」视图，本质是
> `conversation.view` 上的一个注册项；「并列」= 同 Slot 再注册一个 id。
>
> **加载前提**：dsh 的 client 模块系统（`dsh-client-modules`）靠
> `require.resolve(包名/package.json)` 发现 client 半，要求插件以**包名**加载
> （`dsh.client` + `exports["./client"]`）。开发 overlay（`cordis.dev.yml` 的
> `file:///...` URL）无法被它解析，需改用包名加载（profile/pnpm link）才能让
> `houdinitrace` 标签页出现。
