# dsh-houdini

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）插件：让 agent 驱动一个正在运行的 SideFX Houdini 会话。

架构：`dsh-houdini`（dsh 插件，注册模型可见工具）→ HTTP → `houdini/python3.11libs/dsh_bridge.py`（跑在 Houdini 内部 Python 的桥，`hou` 模块只存在于那里）。

## 文档

- **[`docs/setup.md`](docs/setup.md)** — 新机安装步骤（换电脑/重装照做）。
- **[`docs/tool-design.md`](docs/tool-design.md)** — 设计宪法：动词词表、两轴模型、铁律、帮助文档三阶段、动词追踪。
- **[`docs/development.md`](docs/development.md)** — 开发进度与卡点（随开发同步维护）。

## 工具

| 工具 | 用途 |
|---|---|
| `houdini_exec` | 在 Houdini 里执行 Python（可改场景：建节点、设参数、cook、存 hip） |
| `houdini_query` | 只读检查代码（列节点、读参数、查错误），约定不修改场景 |
| `houdini_job_submit` | 提交长任务（渲染/模拟/重 cook），立即返回 jobId |
| `houdini_job_status` | 轮询后台任务状态 |
| `houdini_job_cancel` | 协作式取消：排队中的 job 直接丢弃（代码不会执行），运行中的杀不掉 |

执行的代码自带 `hou`；把 JSON 可序列化的值赋给 `__result__` 可返回结构化数据，`print` 的内容随 stdout 回传。

每次 exec 还会在结果里带一个 **`verbs` 字段**（动词追踪）：bridge 给每个动词包了运行时 tracer，记录每次动词调用的 `{verb, args, kwargs, ok, result/error, ms}`，`hou.Node` 自动转 path，失败以 `ok:false` 记录。stdout 同时打印 `[verb] ...` 摘要行。这是将来 `houdinitrace` 视图的数据层（见 `docs/tool-design.md` §8）。

反过来，如果代码**完全没走动词**却用了动词已覆盖的裸 `hou` 调用（`createNode`/`setInput`/`parm().set`/`destroy` 等），bridge 会对代码做 AST 扫描并在结果里附 **`advisory`** 字段，工具渲染为 `hint:` 段，点明可替代的动词（见 `docs/tool-design.md` §8）。

## Houdini 侧 helper（动词词表）

bridge 在 exec 命名空间里预置了一组**通用动词**（除 `hou` 外可直接用）。它们把 Houdini 的
惯例/校验/最新版本解析/错误处理固化，让 agent 写一句 `set_parm(...)` 而不是十几行裸 `hou`。
**动词是主接口**；`hou` 只是逃生舱，只在词表覆盖不了时（hip 文件 I/O、渲染、UI、底层几何属性操作）才直接裸写。

> 完整设计（两轴模型、铁律、帮助文档三阶段、后续路线）见 **[`docs/tool-design.md`](docs/tool-design.md)** —— 那是唯一真相源，本表只是速查。

| 域 | 动词 | 作用 |
|---|---|---|
| 类型目录 | `search_tab_menu(category, query)` | 只读：列出某 context 下匹配的节点族 + 最新版（查不猜，别猜类型名） |
| 类型目录 | `resolve_latest_type(category, base)` | 某节点族的最新版全名（内部为主） |
| node | `tab_create(parent, type_name, name=, inputs=[...])` | 建节点：**永远最新版本 + shelf 初始化** |
| node | `find_nodes(pattern="*", category=, node_type=, root=)` | 找**已存在**节点（扁平 path 列表） |
| node | `graph(node, depth=1, direction='both')` | 拓扑：inputs / outputs / parm_refs（含 `ch()` 隐形引用） |
| node | `describe(node)` | 状态 + 几何摘要 + 帮助元数据 |
| node | `connect(src, dst, index=0)` | 连线 |
| node | `rename_node(node, name)` / `delete_node(node)` | 重命名 / 删除（返回被表达式引用的上游） |
| node | `cook_node(node)` | cook + 采集 error/warning |
| parm | `list_parms(node)` | 参数**目录**（名字/标签/类型/帮助，不给值） |
| parm | `read_parms(node, changed_only=True)` | 参数**值**（默认只看非默认 + 带表达式 + 被引用的；表达式附 `referenced_parm`） |
| parm | `set_parm(node, name, value)` | 设参（数值参数收到字符串 = 设表达式；失败列相似名，自纠） |

```python
geo = tab_create(hou.node('/obj'), 'geo', name='my_geo')
box = tab_create(geo, 'box')
set_parm(box, 'size', [2, 2, 2])          # 元组名 + list 值
set_parm(box, 'divrate1', 4)              # 组件名
find_nodes(category='sop', node_type='box')  # -> ['/obj/geo1/box1']
graph(box)                                # -> inputs/outputs/parm_refs
describe(box)                             # -> 状态 + 点数 + bbox + 帮助 URL
read_parms(box)                           # -> 只看改过的参数
```

### 节点创建语义（`tab_create`）

动机：有些节点（如 `copytopoints::2.0`）通过 Tab Menu 创建时，shelf tool 脚本会额外做初始化（按 `Reset Attributes from Target` 按钮等），裸 `createNode` 不会做；且 `hou.preferredNodeType` 实测不可靠，所以版本用枚举取 `::N` 最大。

**初始化启发式**：`tab_create` 只在 shelf tool 脚本里有「实质场景操作」（`pressButton(` / `createNode(` / `setInput(` / `applyTabToolRecipe` / `.parm(`）时才跑 tool；只给 `kwargs` 设默认参数的（如 `box` 的 `divrate=2`、`grid` 的 `size=10`）会走直接 `createNode`，**这些 tool 默认参数不会应用**——需要时请显式设参（如 `set_parm(box, 'divrate1', 2)`）。这是用「快」换「tool 默认值」的取舍。

**已知边界**：跑 shelf tool 需要真实 Network Editor pane（GUI 才有）。GUI 里用 = 完整初始化；headless `hython` 里用 = 自动退化为「仅保证最新版、不保证 tool 初始化」。`tab_create` 返回 `hou.Node`，回传结构化数据时需手动转 JSON（如 `__result__ = {'path': node.path()}`）。

## 快速开始

> 下文示例中的 `E:/dsh-houdini`（含 `E:\dsh-houdini`）是作者的 checkout 路径，请替换成你本机的 checkout 目录。

```sh
npm install
npm run build
```

在 Houdini 里启动桥（菜单 Windows > Python Shell）：

```python
import sys; sys.path.append(r"E:/dsh-houdini/houdini/python3.11libs")
import dsh_bridge
dsh_bridge.start()          # http://127.0.0.1:8765
```

或无头模式：`hython E:/dsh-houdini/houdini/python3.11libs/dsh_bridge.py [scene.hip]`

然后用 link 插件并启动 dsh Web UI（profile 模式，不再用 `--patch` overlay）：

```sh
dsh plugin --profile web add E:/dsh-houdini
dsh web
```

新建会话时选 **「Houdini 模式」** preset（见下「安装 + Houdini 模式 preset」）。试一句：「用 houdini_query 列出当前场景 /obj 下的所有节点」。

## 一键启动（Houdini 菜单）

`houdini/python3.11libs/dsh_launcher.py` 提供一个**开发循环刷新按钮**：点一次 = 同步 preset（`presets/` → `~/.dsh/.agent-presets/`）+ 重启 bridge（停 → reload 模块 → 起）+ 重启 dsh web 前端（杀 3081 上的 node → 重拉）+ 打开内嵌 UI（自动置于 Houdini 窗口之上）。改完 `npm run build`、改了 Houdini 侧 Python 或改了 preset 后，点它即可全部生效，无需重启 Houdini。等前端就绪时显示可取消的加载动画对话框（前端重启与端口探测在 worker 线程，不卡 GUI）；辅助进程全部隐藏控制台窗口，状态只输出到 Houdini 控制台。

用 Houdini package 安装（给顶部菜单栏追加 `dsh` 菜单，同时通过 `PYTHONPATH` 把 `python3.11libs` 加进 `sys.path`——不用 `pythonX.Ylibs` 目录约定是因为 Houdini 只自动加载匹配自身 Python 版本的目录：H21=3.11、H22=3.13，而本插件是纯 Python、与版本无关）。脚本会把本机仓库的绝对路径烘焙进 package 文件（Houdini package 的相对路径不按 package 文件位置解析，必须用绝对路径），并自动装入检测到的**每个** Houdini 版本的 pref 目录（package 按版本隔离，H21/H22 各装一份）：

```sh
python houdini/install.py
```

（可先 `python houdini/install.py --print` 预览生成内容。）

> ⚠️ **新装/切换 Houdini 大版本后要重跑本脚本**——package 装在用户 pref 目录（如 `Documents/houdini21.0/packages`），各版本互不可见。目录名 `python3.11libs` 只是历史名字，靠 `PYTHONPATH` 注入，与 Python 版本无关（H21=3.11 / H22=3.13 均可）。

重启 Houdini 后，菜单栏出现 `dsh` → `启动 / 重启 dsh`。前端默认用 `npx --yes @deepseek-ai/dsh web`（即 `--profile web`，不再传 `--patch`，首次会拉取已发布的 CLI）；想改用本机固定安装，把 `dsh_launcher.py` 顶部 `SHELL` 设为 `False` 并填 `DSH_BIN`（`NODE` 会自动取 PATH 里的 `node`）。

> ⚠️ 点这个按钮会杀掉当前 dsh 会话（前端进程重启），请在新 UI 里继续对话。

不装菜单也可以，直接在 Python Shell 里：

```python
import dsh_launcher
dsh_launcher.launch()
```

## 安装 + Houdini 模式 preset

dsh-houdini 是**插件（能力层）**，挂到 **agent preset（模式层）**。仓库带一个 `houdini` 模式 preset 模板（`presets/houdini/`），复制到用户 preset 根即可：

```sh
npm run build
dsh plugin --profile web add E:/dsh-houdini            # pnpm link，让包名可解析（client 半依赖）
# 把 presets/houdini/ 复制到 ~/.dsh/.agent-presets/houdini/（仅首次；之后每次点 dsh 菜单自动同步）
dsh web                                                 # 起前端（profile 模式）
```

在 UI 新建会话时选 **「Houdini 模式」**。`dsh plugin` 用 pnpm link 本地目录，改代码后 `npm run build` 即可（HMR 热重载）。卸载：`dsh plugin --profile web remove dsh-houdini`。

仓库另带一个 **`houdini-dev` 模式 preset**（`presets/houdini-dev/`）：工具集与 `houdini` 完全相同，仅 persona 换成 coding/development——以插件仓库为主目标、把运行中的 Houdini 会话当**测试目标**（改 `src/`/`client.js`/`houdini/python3.11libs/` 时用 `houdini_*` 工具做端到端验证）。开发/测试插件本身时选 **「Houdini 开发模式」**，复制方式同上（`presets/houdini-dev/` → `~/.dsh/.agent-presets/houdini-dev/`）。

> 为何用 preset 而不是 `--patch` overlay：dsh 的 client 模块系统靠 `require.resolve(包名/package.json)` 发现插件的 client 半，`file://` overlay 无法被解析；preset 用包名加载，client 半（`houdinitrace` 视图）才生效。

## 配置

`cordis.patch.yml`（或被 profile 引用的 bundle 层）里的 `config`：

- `bridgeUrl`（默认 `http://127.0.0.1:8765`）— 桥的地址
- `requestTimeoutMs`（默认 `120000`）— 单次桥调用超时；长任务用 `houdini_job_submit`，不受此限

## 健壮性

桥对失控 agent 做了资源上限：stdout/stderr 各截断到 1 MiB、`__result__` 序列化超过 4 MiB 时丢弃、请求体超过 16 MiB 拒绝；后台 job 结束后保留 10 分钟供轮询、最多保留 1000 个（超限自动清理）。桥还提供 `GET /health`（返回 `{"ok": true, "houVersion": "..."}`）用于诊断。

## 已知限制

- `hou` 只能在 Houdini 主线程调用：桥把全部执行编组到主线程（GUI 下是 QTimer 泵，headless 下是 `__main__` 主循环泵），因此严格串行——后台 job 是排队异步而非并行，且代码执行期间 GUI 会像原生 cook 一样冻结；取消是协作式的——排队中的 job 在执行前被丢弃（零场景副作用），运行中的杀不掉
- 桥绑定 `127.0.0.1`，未做鉴权——不要在不可信网络上暴露端口
- 客户端超时/取消不会中断 Houdini 内已在执行的代码：调用方看到失败或取消时，场景可能已经被改——重试前先用 `houdini_query` 确认场景状态
- `dsh-tools` 的 npm 发布版本落后于 dsh 源码仓库：本包 devDependency 是 `^0.0.1-rc.1`，而当前 dsh 运行时用 `0.1.0-rc.6`。二者的 `defineTool`/输出 schema DSL 已实测一致（必填字段按属性写 `required: true`，而不是 JSON-Schema 的 `required` 数组）；若未来对不上，按你实际安装的 dsh 版本对齐 devDependency

## 后续路线（按价值排序）

1. **视觉反馈闭环**：桥加 `/screenshot`（viewport 截屏或 flipbook 帧），工具返回 image 内容块——原生插件路线相对 MCP 的核心优势
2. **`ctx.jobs` 后台运行时**：把 job 管理从桥侧迁移到 dsh 的 jobs 服务，获得 `job_kill` 等通用控制工具（参考 `docs/cookbook/adding-a-tool.md` 的 Long-running work）
3. **UI 卡片**：`presentCall`/`presentResult` 声明渲染意图（比如参数修改的 diff 卡）
4. **权限分层**：`tools/pre-execute` 监听器实现"query 自动允许、exec 需审批"（参考 `docs/cookbook/extension-cookbook.md` 的 permission-gate 示例）
5. **Skill 文档**：随插件发布 Houdini 工作流知识（SOPs/VEX 惯例、hou API 陷阱），按需加载而非占用系统提示词
