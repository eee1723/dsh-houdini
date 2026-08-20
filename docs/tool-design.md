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
| **node / network**（场景图） | ✅ 已实现（含 SOP/OBJ 显示语义 + layout） | network box / sticky note |
| **parm**（依附 node） | ✅ 已实现 | 表达式 / keyframe / spare parm / lock |
| **geometry**（几何数据） | ✅ 部分实现（属性/piece/跨帧） | `geo_export` |
| **scene**（工程/会话） | ✅ info/timeline/bookmark | `scene_save` `scene_load` |
| **viewport**（视口/UI） | ✅ 部分实现（`viewport_screenshot`） | `viewport_frame` `viewport_camera` |
| **asset**（HDA） | ✅ 已实现（2026-08-20，OTL 会话复盘 P0） | `hda_install` `hda_list` |
| **render / sim**（重型） | ✅ job 通道 + `render_frame`/`render_check` | `render_start` `sim_step`（走 job） |
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
6. **失败不留半成品**：GUI exec 自动进入唯一 undo group，异常时只在栈顶 label
   精确匹配时 performUndo，并回报 `rollback`；文件 I/O/HDA 库等非 undoable 副作用
   不伪称已回滚。headless undo stack 关闭时明确回报 unsupported。

---

## 4. 动词表（当前已实现）

### vocabulary 域（回答「动词怎么调用」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `verb_help(name)` | 返回已注入动词的准确 signature 与 docstring；未知名列相似项。用于在调用前发现契约，不靠失败或读取仓库源码猜参数/返回形状 | dict |

### 类型目录（回答「能建什么」）

| 动词 | 语义 | 返回 |
|---|---|---|
| `search_tab_menu(category, query)` | 列出某 context 下匹配的节点族 + 最新版 | dict |
| `resolve_latest_type(category, base)` | 某族最新版全名（内部为主） | str |

### node 域（场景图）

| 动词 | 语义 | 返回 |
|---|---|---|
| `tab_create(parent, type_name, name=, inputs=[...])` | 建节点：最新版 + shelf 初始化；parent 接受 `hou.Node` 或 path 字符串 | `hou.Node` |
| `find_nodes(pattern="*", category=None, node_type=None, root=None)` | 找**已存在**节点（扁平清单） | path 列表 |
| `graph(node, depth=1, direction='both')` | 围绕**该数据节点**查 inputs / outputs / parm_refs；检查最终 SOP 网络应对 `OUT` 向上查，不要对父 OBJ 容器调用 | dict |
| `describe(node)` | 状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删——MMB 节点信息里「这个节点对数据干了什么」的固化）+ 帮助元数据 | dict |
| `connect(src, dst, index=0)` | 连线（src 输出 → dst 输入）；落口与请求不一致时返回里带 `note` | dict |
| `rename_node(node, name)` | 重命名 | 新 path |
| `delete_node(node)` | 删除（返回被表达式引用的上游） | dict |
| `cook_node(node, force=False)` | cook + error/warning；另给 `ok/warning_free/healthy`，warning 未解释不得当完成 | dict |
| `sop_set_output(node, render=True)` | 把 SOP singular display/render 旗标移到输出节点；属于用户 viewport/交付状态，不是 render_view 前置条件 | dict |
| `sop_output_node(parent)` | 报告 SOP 网络 display/render 输出；旗标不在链尾时提醒 | dict |
| `set_object_visible(node, visible=True)` | 设置单个 OBJ 的 viewport visibility（OBJ 没有 SOP 式 render flag） | dict |
| `visible_objects(root='/obj')` | 列出 OBJ 层 plural visibility/effective visibility | dict |
| `layout_nodes(parent, nodes=None, horizontal_spacing=-1, vertical_spacing=-1)` | 用 Houdini 原生 layoutChildren 布局全部或指定网络项 | dict |

### compatibility 域（仅历史回放，不进新 guidance）

| 动词 | 语义 | 返回 |
|---|---|---|
| `set_display(node, render=True)` | deprecated 兼容 wrapper：按节点 context 路由 SOP output / OBJ visibility | dict |
| `display_node(parent)` | deprecated 兼容 wrapper：按父网络 context 路由 SOP output / OBJ visibility | dict |

### parm 域（依附 node）

| 动词 | 语义 | 返回 |
|---|---|---|
| `list_parms(node)` | 参数**目录**：名字/标签/类型/帮助（导航用，不给值） | list |
| `read_parms(node, changed_only=True)` | 参数**值**：默认只看非默认 + 带表达式 + 被引用的（意图解读）；表达式参数附 `referenced_parm`，被引用参数标 `referenced_by` | list |
| `set_parm(node, name, value)` | 设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠）。参数上有表达式/关键帧时**自动清除再设值**，返回带 `note` 说明清掉了什么（2026-08-20 起，OTL 会话 seq 28944：`$FEND` 表达式把 set 静默架空）；想保留动画就请显式用字符串表达式 | dict |
| `set_parms(node, values)` | 批量设参：`{name: value}` 字典逐项走 `set_parm` 同一套语义，**逐项容错**——单项失败不中断，返回分 `set`/`failed` 两组（消灭循环裸 `parm().set` 的 advisory 噪音） | dict |
| `create_spare_parms(node, code_parm='snippet', defaults=None)` | 扫描代码参数的 `ch/chf/chi/chv/chs` 引用，声明式创建缺失 spare parameters 并应用显式默认值；复杂 `chramp` 等列 unsupported。修复「Wrangle 引用了 amp/speed 但参数不存在，ch() 全为 0、动画静止」 | dict |

### scene 域（工程/时间线）

| 动词 | 语义 | 返回 |
|---|---|---|
| `scene_info()` | 只读 HIP/version/fps/current frame/time/frame range/playback range/UI 状态；不移动 playbar、不遍历整张节点图 | dict |
| `set_timeline(fps=None, frame_range=None, playback_range=None, current_frame=None)` | 设置明确的时间线字段；至少一项，范围校验后回读 scene_info | dict |
| `list_bookmarks()` | 列出 bookmark id/name/start/end/enabled/visible/comment | list |
| `create_bookmark(name, start, end, replace=False)` | 创建整数帧 bookmark；同名默认拒绝，replace 精确替换 | dict |
| `delete_bookmark(name_or_id)` | 按精确名称或 session id 删除，失败列现有项 | dict |

### geometry 域（几何数据）

| 动词 | 语义 | 返回 |
|---|---|---|
| `geo_attrib_stats(node, name, attrib_class='point')` | 属性**值**统计：min/max/mean/count（`describe` 只给属性名清单）；point/prim/vertex/detail，多分量按分量给 | dict |
| `geo_piece_stats(node, piece_attrib=None, sample=16)` | primitive piece 的局部 bbox/extent/面积与退化统计；无 piece 属性时用内存 Connectivity SOP Verb，不污染网络，能发现「全场 bbox 正常但每个实例零宽/零面积」 | dict |
| `geo_frame_diff(node, frame_a, frame_b, attrib='P', sample=4096, tolerance=1e-6)` | 用 geometryAtFrame 比较两帧 point 数值属性，返回 mean/max、p50/p90/p99、逐分量位移与 unchanged%；不移动用户 playbar。证明数据是否随时间变化，不单独证明审美/运动语义 | dict |

### asset 域（HDA / 数字资产，2026-08-20 落地）

设计背景：project_init OTL 会话（trace f608bfab）——造工具是继「造内容」之后的第二高频场景，
但该会话 75 次 exec 中 59 次纯裸 hou，最大空洞就是 HDA authoring（parmTemplateGroup 系约
55 次裸调用、参数组重建泥潭 6 调用、conditional 被吞 5 调用 + 1 用户回合、PythonModule
全文重发 5 次约 55KB）。本域动词把这些教训固化：

| 动词 | 语义 | 返回 |
|---|---|---|
| `hda_create(node, name, description=None, hda_file=None, min_inputs=0, max_inputs=0, replace=False)` | 把已有节点（通常 subnet）转为数字资产：自动建 otls 目录、默认 `$HIP/otls/<name>.hda`。`replace=True` = 整体重建：销毁该类型的全部现有实例 + 卸载旧定义 + 覆盖文件（返回里列出被销毁的实例路径）；否则同名冲突报错并提示 replace | dict |
| `hda_info(node, max_depth=6)` | 资产/参数界面**只读自省**：类型名、定义文件、section 清单、参数模板树（名字/标签/类型/conditional/tags/嵌套 folder 递归）——替代手写 walk()（会话里重复写了 3 次）。普通节点也可用（只有 parm 树，无 section） | dict |
| `hda_get_section(node, section='PythonModule')` | 读 HDA section 内容；section 不存在时列出现有 section 名供自纠 | dict |
| `hda_set_section(node, section, code)` | 全量写 section。`PythonModule` 先 `compile()` 预检语法（带行号报错，不写脏）；写后读回校验一致 | dict |
| `hda_patch_section(node, section, old, new, count=1)` | 锚点局部替换：`old` 必须恰好出现 `count` 次（0 = 锚点没找到，>count = 锚点不唯一需加长），替换后同样过语法预检；**模块改局部时用它，不要全文重发** | dict |
| `hda_set_interface(node, spec, keep_std=True, hide_builtin_tabs=False)` | **声明式参数面板**（已拍板：整组重建语义，非 merge）：`spec` 是条目列表（folder/separator/toggle/int/float/string/button/menu），重建自定义参数组；subnet HDA 的 Transform/Subnet 标准页从 Houdini 原生 subnet 类型重新取得，避免夹带旧自定义参数。`hide_when` 字段写 conditional，**提交后读回验证**——被 `setParmTemplateGroup` 吞掉就自动改走 DialogScript `hidewhen` 补丁兜底（seq 124609 的教训）；folder 上设 `hide_when` 直接报错（Houdini 不支持，seq 98973 实测）。`hide_builtin_tabs=True` 通过公开 `ParmTemplateGroup.hide` 生成 `invisibletab` 隐藏标准页 | dict |

**`hda_set_interface` 的 spec 条目格式**（JSON 安全的 dict 列表，嵌套 folder 用 `parms`）：

- 公共字段：`name` `label` `default` `help` `hide_when`（如 `"{ manual_res == 0 }"`）`join_next` `tags`
- `{"type":"folder", "folder_type":"simple|tabs|collapsible", "parms":[...]}`
- `{"type":"int"|"float", "min":, "max":}`；菜单只支持 int：
  `{"type":"int", "menu":{"items":[...], "labels":[...]}}`
  ——⚠️ **int+menu 存的是菜单索引（0..N-1）不是值**（会话 seq 51814 服务器实跑 1 fps 事故），
  `default` 也必须填索引；回调代码里需自行做索引→token 映射。HOM 的
  `FloatParmTemplate` 构造器不接受菜单参数，动词会明确拒绝；想存真实 token 请用 string 类型
- `{"type":"string", "file":"dir|alembic|image|geo|any"}` → 文件选择器
- `{"type":"button", "callback":"hou.phm().xxx(kwargs)"}`（Python 回调）
- `{"type":"toggle"}` / `{"type":"separator"}`

### render / sim 域（渲染产物）

| 动词 | 语义 | 返回 |
|---|---|---|
| `render_frame(rop, picture=None, frame=None, timeout=110)` | 渲染单帧并验证产物；调用期间切到目标帧、结束/失败后恢复用户原 frame。>110s 走 job | dict |
| `render_view(node, direction='iso', frame=None, width=1280, height=720, picture=None, framing='full', coverage=0.82, framing_frame=None)` | **视觉验证主干 v2**：显式 SOP → agent-owned Object Merge proxy → agent camera/OpenGL ROP `forceobjects` 只渲染 proxy；不依赖/不改变用户 SOP output、OBJ visibility、selection、viewport 或 frame。传 OBJ 时只在调用开始解析一次 SOP并提醒。preflight 拒绝空/error 几何；返回 source fingerprint 前后、`stale`、eye/direction、ROP 设置和 render_check。动画 A/B 给所有调用传相同 `framing_frame`，用同一 bbox 锁定相机；空闲 proxy 清空真实引用但保留 last-target/frame/output userData 与解释 comment | dict |
| `render_check(path, ref=None)` | 亮度/非黑/主色/content bbox；A/B 另给高精度 mean、RMSE、changed/meaningful pixel %、max diff，微小非零不再被舍入成 0 | dict |

### viewport 域（视口/UI）

| 动词 | 语义 | 返回 |
|---|---|---|
| `viewport_screenshot(path=None, frame=None, clean=True, frame_target=None, textures=None, backface_cull=False)` | **用户屏幕诊断工具**：用户切空 display 节点时截到空是正确结果，不能用来证明 agent 产物；和 `render_view(explicit_sop)` 对照可区分 viewport 漂移与真实几何错误。flipbook 异步，设置/相机在落盘后恢复 | dict |

### 拆分决策：`list_parms` vs `read_parms`

两个动词回答**两个不同问题**，合并会互相污染：

- `list_parms` → 「我想改的参数叫什么名？」（导航，类似 `ls`）
- `read_parms` → 「这个节点实际在干什么？」（意图解读）

---

> **实测 API 基线（H21.0.440 / py3.11 与 H22.0.368 / py3.13 一致）**：
> `Parm.set(str)` 对数值参数抛 TypeError（表达式必须走 `setExpression`）；
> `hou.Parm` 无 `isReferencedBy`，引用自省用 `parmsReferencingThis()` / `getReferencedParm()`；
> `Node.inputs()` 是紧凑元组（无 None 占位，但代码仍做防御）；`setInput` 只接受 `hou.Node` 对象。
>
> **HDA authoring 基线（H21 实测，project_init OTL 会话 trace f608bfab）**：
> ① `setParmTemplateGroup` 提交会**丢弃 API 侧 `setConditional` 设的 conditional**
> （GUI 设的能活）——写后必须读回验证，丢了就补丁 DialogScript `hidewhen` 行；
> ② conditional 对 **folder 无效**（只有 `invisibletab` 能隐藏整页）；
> ③ 删除内置 std 页会被 Houdini 自动重建，隐藏走 DialogScript `invisibletab`，
> 且 `setParmTemplateGroup` round-trip 会**保留**已有 `invisibletab`；
> ④ `parmTemplateGroup.remove(folder)` 可能留下内层残参、同名 folder 被自动改名
> （folder_init→folder_init2）——面板重建用整组替换，不要增量修；
> ⑤ Int 参数配菜单存**索引**不存值；⑥ `alembicTimeRange` 有归档缓存脏读
> （同路径重写的 abc 会读出错误单位），读前先 `alembicClearArchiveCache()`；
> ⑦ abc 时间戳是 Maya 约定 frame=t×fps，与 `hou.timeToFrame`（frame 1 = 0s）差一帧。

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
3. `scene_*` / `viewport_*` 域（`hda_*` 已于 2026-08-20 落地，见 §4 asset 域）。
4. Skill：`houdini-trace-analysis` + `houdini-sop-workflow` 已落地；随新 trace 更新模式库/领域参考。
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
里过滤 `houdini_*` 的 `ToolResultNode` 渲染成调用卡。视图展示**全部** houdini_* 调用
（2026-08-17 修正：原先只抽 `verbs (...)` 段，纯裸 hou 的会话会显示成空白，恰好漏掉
最该监控的信号）：顶部统计条给出「N 次调用 · X 次用了动词（共 M 个）· Y 条裸 hou hint」，
每张卡标注 `verbs ×N` / `raw hou` 标签并展示 verbs 段与 hint 段（无动词时退化为
stdout 摘要）。

### 裸 hou advisory（2026-08-17）

铁律 3（`hou` 是逃生舱）的配套 observability：光声明原则无法知道 agent 是否真的在逃。
bridge 对每次 exec 的代码做 **AST 静态扫描**（`_raw_hou_calls`），统计动词已覆盖的
裸调用（`createNode`→`tab_create`、`setInput`/`connectInputs`→`connect`、
`parm(...).set`→`set_parm`、`setName`→`rename_node`、`destroy`→`delete_node`、
`cook`→`cook_node`、`setDisplayFlag`→`sop_set_output` 或 `set_object_visible`、
`setRenderFlag`→`sop_set_output`、`layoutChildren/setPosition`→`layout_nodes`、
`addSpareParmTuple`→`create_spare_parms`、
`setExpression`→`set_parm`）；当代码**完全没走动词**却用了这些调用时，envelope 附
`advisory` 字段（文本，点明对应动词），工具渲染为 `hint:` 段。用 AST 而非正则：
注释和字符串里的同名文本不会误报；语法错误时静默跳过。

### raw-hou gate：拦 + 豁免通道（实验开关，2026-08-19）

advisory 的下一步：软提示被模型无视的天花板已反复实证（deepseek-v4-flash 读
完 advisory 继续裸写），gate 把它升级为**执行前拦截**，但带显式豁免通道
（软硬结合——纯硬墙会把「词表真缺口」变成任务卡死，并诱发 getattr/exec 等
更隐蔽的逃逸）。

- **开关**：桥模块级 `_raw_gate`，默认**关**；用户侧在 Houdini Python Shell
  `dsh_bridge.set_raw_gate(True)` 开启（不进 exec 命名空间）；`/health` 带
  `rawGate` 状态。桥重启（launcher 菜单）后复位为关。
- **拦截集**（AST，`_gate_message`）：①动词已覆盖的裸调用（`_RAW_HOU_VERB_MAP`
  全集 + `parm().set` 特判）→ 报错逐一点明对应动词；②疑似修改场景的方法
  调用（`set*/add*/create*/delete*/save*/render*` 等前缀启发式）→ 报错列出。
  拒绝发生在**执行前**，零副作用；语法错误放行给 exec 自己报。已知误伤面
  （python 侧的 `set.add`/`dict.setdefault` 形状相同）在 houdini exec 里罕见，
  报错信息自带豁免指引。
- **豁免通道**：工具参数 `allow_raw="为什么动词覆盖不了"`（exec/query/
  job_submit 都有）——同一段代码带豁免重发即放行，桥打印
  `[gate] raw-hou exemption: <理由>` 进 stdout（进结果、进 trace）。
  **每条豁免 = 一份带理由的词表缺口记录**，这是实验的核心产出。
- **不拦**：纯读取/引用（`hou.node`/`hou.hipFile`/`print` 等）——词表不
  打算覆盖「取引用」这种语言级操作。
- 实验期望的首个产出：`create_parm`（spare parm 创建——自行车 trace 实证
  的真缺口，程序化工作流的核心操作）。

### 图片 media relay（2026-08-19，草地任务 trace 的直接产出）

「共享屏幕副驾驶」定位的管道地基：产图的动词（`render_frame` / `render_view` /
`viewport_screenshot`）把产物路径登记进 `dsh_hou_helpers._PRODUCED_IMAGES`
（`report_image()`，agent 手写产出也可登记），bridge 在 exec envelope 里带
`images` 字段；host 侧对每个路径 `GET /media?path=...`（桥新端点：只读、限
图片扩展名、64MB 上限）拉回字节，写进 `<工作区>/.dsh-houdini-media/`，并在
工具结果里渲染 `media` 段（from → to 映射）。**vision/fs 工具用右侧的工作区
路径**——$HIP 原路径对它们不可读（沙箱）。这修掉了草地 trace 里
`vision_glance` 被 "image escapes the allowed directories" 拦截的根因，也让
workspace note 从「每次调用都重复」降为「每会话一次」（alarm fatigue 实证：
同一条 note 重复 30+ 次后模型完全无视 hint）。

### trace-analysis skill（2026-08-20）

`houdinitrace` 回答“发生了什么”，`trace-report.mjs` 固化调用目录/时间线/失败事实；
随包 `houdini-trace-analysis` skill 负责“如何审判”：任务契约、阶段门、工具机会矩阵、
Houdini 模块/属性/cook/显示/渲染/动画语义、反事实最小轨迹和 P0/P1/P2 产品建议。
配套 `extract-trace-evidence.mjs` 从多帧 zstd 确定性提取硬失败、verb ledger、裸调用、
批量设参机会、render/vision、todo 和 terminal 状态，并支持多 trace 聚合。

词表决策不得由调用频率直接推出：未用先判 `NOT_APPLICABLE` 或 `MISSED`；删除候选需
至少三个多样 trace、明确替代和反例分析。每次新复盘若发现通用审计盲区，更新 skill
量表；若发现重复产品模式，带 session/步骤证据更新模式库。

### 「共享屏幕副驾驶」定位（2026-08-19，经双向钢人论证 + 用户拍板）

视口是**用户的**领地：漂移（移动/遮挡/最小化）是要共存的现实，不是要对抗的
噪声。由此确定的分工：

- **验证/交付走 agent 自己的渲染管线**：`render_view`（OpenGL ROP 离屏）是默认
  视觉验证路径；Karma 是用户明确要成片时的交付渲染器，不进验证闭环。
- **`viewport_screenshot` 降级为诊断**：只回答「用户屏幕上现在是什么」。
- **不新增编程用户视口的动词**（不做 `viewport_look_at`）：草地 trace 里 40 分钟
  的相机矩阵挣扎，根因是「试图编程一个不属于自己的东西」，正确解法是根本不碰它。
- **词表按意图而非 API 表面增长**：新动词的门槛是「一个 Houdini 用户会当成
  一个动作的事」（render_view 合格：取景+渲染+验证=一个意图；viewport_state /
  parm_menu 这类 API 碎片不合格，折进现有动词或不做）。

> 注：dsh 里用户说的「trace」即 `dsh-client-ui-trajectory` 的「轨迹」视图，本质是
> `conversation.view` 上的一个注册项；「并列」= 同 Slot 再注册一个 id。
>
> **加载前提**：dsh 的 client 模块系统（`dsh-client-modules`）靠
> `require.resolve(包名/package.json)` 发现 client 半，要求插件以**包名**加载
> （`dsh.client` + `exports["./client"]`）。开发 overlay（`cordis.dev.yml` 的
> `file:///...` URL）无法被它解析，需改用包名加载（profile/pnpm link）才能让
> `houdinitrace` 标签页出现。
