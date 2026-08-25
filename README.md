# dsh-houdini

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)（dsh）插件：让 agent 驱动一个正在运行的 SideFX Houdini 会话。

架构：`dsh-houdini`（dsh 插件，注册模型可见工具）→ HTTP → `houdini/python3.11libs/dsh_bridge.py`（跑在 Houdini 内部 Python 的桥，`hou` 模块只存在于那里）。

## 文档

- **[`docs/setup.md`](docs/setup.md)** — 新机安装步骤（换电脑/重装照做）。
- **[`docs/tool-design.md`](docs/tool-design.md)** — 设计宪法：动词词表、两轴模型、铁律、帮助文档三阶段、动词追踪。
- **[`docs/development.md`](docs/development.md)** — 开发进度与卡点（随开发同步维护）。
- **[`docs/rig-animation-design.md`](docs/rig-animation-design.md)** — Rig/animation 第一性原理、官方系统路由、最小工具预算与分阶段验收。
- **[`skills/houdini-trace-analysis/SKILL.md`](skills/houdini-trace-analysis/SKILL.md)** — Houdini trace 的标准审计流程、工具机会矩阵和词表演化规则。
- **[`skills/houdini-sop-workflow/SKILL.md`](skills/houdini-sop-workflow/SKILL.md)** — 程序化 SOP/VEX/Copy/属性/模块验证和动画交付工作流。
- **[`skills/houdini-rig-animation-workflow/SKILL.md`](skills/houdini-rig-animation-workflow/SKILL.md)** — Channel、刚体 pieces、机械层级、KineFX skin、APEX 路由与时序完成门。
- **[`skills/houdini-skill-governance/SKILL.md`](skills/houdini-skill-governance/SKILL.md)** — 创建/维护 Houdini skills，多来源证据吸收、受控自进化、版本与发布治理。

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

bridge 还会在执行前 AST 扫描裸调用。`createNode`/`setInput`/`parm().set`/`cook`/`destroy` 等已有动词覆盖的修改默认直接拒绝；没有动词的低层修改只能拆成独立调用，并在 Gate 首次拒绝后用一次性 `allow_raw="具体缺口"` 留痕。只读 HOM 探针仍可直接使用；`advisory`/`hint:` 保留为观察层（见 `docs/tool-design.md` §8）。

## Houdini 侧 helper（动词词表）

bridge 在 exec 命名空间里预置了一组**通用动词**（除 `hou` 外可直接用）。它们把 Houdini 的
惯例/校验/最新版本解析/错误处理固化，让 agent 写一句 `set_parm(...)` 而不是十几行裸 `hou`。
**动词是主接口**；`hou` 只用于词表表达不了的只读检查、UI 或底层几何操作。不得在 bridge exec 内调用 `hou.hipFile.load()`；已有动词覆盖的裸修改不能旁路 Gate。

> 完整设计（两轴模型、铁律、帮助文档三阶段、后续路线）见 **[`docs/tool-design.md`](docs/tool-design.md)** —— 那是唯一真相源，本表只是速查。

| 域 | 动词 | 作用 |
|---|---|---|
| 类型目录 | `search_tab_menu(category, query)` / `search_tab_entries(parent, query)` | 类型注册表查询 / 真实 parent 可见的 node+tool Tab entries |
| 类型目录 | `resolve_latest_type(category, base)` | 某节点族的最新版全名（内部为主） |
| scene | `scene_info()` | 只读 HIP/version/fps/frame/playback range，不移动时间线 |
| scene | `set_timeline` / `list_bookmarks` / `create_bookmark` / `delete_bookmark` | 时间线字段与 bookmark 明确意图，不再猜 playbar/HOM API |
| node | `tab_create(...)` / `tab_apply(parent, tool_id)` | 建一个可见节点 / 应用 allowlist 多节点 Tab recipe；GUI 恢复用户状态、headless 同语义 |
| node | `find_nodes(pattern="*", category=, node_type=, root=)` | 找**已存在**节点（扁平 path 列表） |
| node | `graph(node, depth=1, direction='both')` | 拓扑：inputs / outputs / parm_refs（含 `ch()` 隐形引用） |
| node | `describe(node)` | 状态 + 几何摘要 + `attrib_delta`（相对 input 0 的属性增删）+ 帮助元数据 |
| node | `node_provenance(node)` | 区分 foreign、当前/其他 DSH session owner 与持久 service；读取开放、修改受控 |
| node | `connect(src, dst, index=0, allow_foreign=None)` | 连线；destination 是修改边界，foreign source 可读 |
| node | `rename_node(node, name)` / `delete_node(node)` | 重命名 / 删除（返回被表达式引用的上游） |
| node | `cook_node(node, force=False)` | cook + error/warning + `healthy`（warning 未解释不能算完成） |
| node | `sop_set_output` / `sop_output_node` | SOP singular display/render 输出（用户 viewport/交付） |
| node | `set_object_visible` / `visible_objects` | OBJ plural visibility |
| node | `layout_nodes(parent, nodes=)` | 默认只布局当前 session 创建节点，并报告跳过的 foreign 节点 |
| parm | `list_parms(node)` | 参数**目录**（名字/标签/类型/帮助，不给值） |
| parm | `read_parms(node, changed_only=True)` | 参数**值**（默认只看非默认 + 表达式/动画 + 被引用；动画附 key count/首尾帧/curve 摘要） |
| parm | `set_parm(node, name, value)` / `set_parms(node, values)` | 单项设参 / 逐项容错批量设参；普通数值赋值会清掉旧动画并回报 |
| parm | `set_keyframes(node, channels, replace=True)` | frame 单位批量关键帧，constant/linear/bezier，预检/回读/失败恢复原 keys |
| parm | `create_spare_parms(node, code_parm='snippet', defaults={...}, spec=)` | 扫代码引用或显式创建 controller folder/参数，避免驱动静默为 0 |
| asset | `hda_create` / `hda_info` / `hda_get_section` / `hda_set_section` / `hda_patch_section` / `hda_set_interface` | HDA 创建、自省、section 安全修改和声明式参数面板 |
| geometry | `geo_attrib_stats` / `geo_piece_stats` / `geo_frame_diff` | 属性值、局部 piece extent/面积退化、无 playbar 副作用跨帧差异 |
| stage/USD | `usd_stage_summary(lop)` / `usd_prim_info(lop, prim_path)` | USD 场景摘要 / 单 prim 属性、绑定和时间采样 |
| render | `render_view(EXPLICIT_SOP, direction='iso', framing='full|detail', coverage=, framing_frame=)` | **视觉验证主干 v2**：显式 SOP → 隐藏 Object Merge proxy → ROP forceobjects；用户 output/OBJ visibility/selection/frame 漂移不选渲染源；渲染基础设施作为带 owner tag 的持久服务收进 OBJ/OUT Network Box，任务收尾复用而不删除；动画 A/B 用同一 framing_frame 锁相机 |
| render | `render_frame(rop, picture=, frame=)` / `render_check(path, ref=)` | 渲染单帧并验证产物 / 图像客观统计（盲验） |
| viewport | `viewport_screenshot(...)` | **诊断**：「用户屏幕上现在是什么」（非验证手段——验证走 render_view） |

产图动词的产物自动经桥 `/media` 端点回传进会话工作区（`.dsh-houdini-media/`），
结果里带 `media` 段（from→to 映射）——vision/fs 工具用工作区路径，与 $HIP 位置解耦。

`render_view` 依赖 Houdini GUI/OpenGL；正常 Houdini 工作站按标准路径使用。低配置开发机若
偶发 OpenGL 不稳定，停止本轮视觉重试并保留 cook/属性/拓扑/多帧差异等语义证据即可；
这不是需要扩展工具或兼容层的产品开发项。

H21 已确认成功渲染后的 agent OpenGL ROP teardown 可能进入进程级 fatal，因此
`__dsh_houdini_*` 节点不是任务残留：它们由 `render_view` 跨调用复用，分别放在 `/obj`
和 `/out` 的 `__dsh_houdini_render_service` Network Box 中。普通任务清理不得删除这些
owner-tagged 节点；空闲 proxy 已自动清空 live source 引用。

## Houdini trace 分析 skill

插件通过 `ctx.skills.register()` 随包发布 trace、SOP、Solaris/Karma、rig/animation 和
skill-governance 五个 skills，在 Houdini / Houdini-dev
模式的 skill 目录中按需加载。它不是另一个 trace UI，而是 `houdinitrace`（实时观察）和
`trace-report.mjs`（事实报告）之上的审计规范：重建用户任务契约，检查工具该用未用/
误用/缺失/冗余/拆并，审计节点模块、属性数据流、cook warning、显示、渲染和多帧动画，
并要求所有产品建议带步骤证据和跨 trace 强度。

```powershell
node skills/houdini-trace-analysis/scripts/extract-trace-evidence.mjs <session.jsonl.zstd> `
  --out tools/out/trace-evidence.json
node tools/trace-report.mjs <session.jsonl.zstd>
```

证据脚本支持一次传多个 session 做纵向对比，并分别报告目录广度、调用含动词率、动词密度、无动词只读探针、Gate 拦截与成功裸修改；不能再把 `used/全部目录` 当作“动词使用率”。审计量表和累积模式库位于 trace skill 的
`references/`；SOP skill 固化 Copy to Points、deform-before-skin、属性契约、piece/多帧完成门；
governance skill 负责把 trace、SideFX 官方文档、视频和 HIP/HDA 工程提炼为有来源、版本、
反例和回归的受控 skill 变更。调用方式：让 agent「使用 houdini-trace-analysis 分析最新 trace」，
或显式调用 `/houdini-trace-analysis`。

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

推荐安装 Houdini package、DSH profile 和所需视觉 bundle：

```sh
python houdini/install.py
```

重启 Houdini，点击 `DSH-Houdini` → `Open Workspace`，新建会话时选 **「Houdini 模式」**。完整步骤见 [`docs/setup.md`](docs/setup.md)。

## 一键启动（Houdini 菜单）

`houdini/python3.11libs/dsh_launcher.py` 提供一个**开发循环刷新按钮**：点一次 = 同步 preset（`presets/` → `~/.dsh/.agent-presets/`）+ 重启 bridge（停 → reload 模块 → 起）+ 重启 dsh web 前端（杀 3081 上的 node → 重拉）+ 打开内嵌 UI（自动置于 Houdini 窗口之上）。改完 `npm run build`、改了 Houdini 侧 Python 或改了 preset 后，点它即可全部生效，无需重启 Houdini。等待前端时显示 `环境 → 插件 → 前端 → 服务 → 界面` 分阶段百分比、耗时与当前动作。已有 project-local npx 缓存时直接执行其中的 DSH CLI，绕开 npm registry 解析并限时 60 秒；只有首次无缓存或显式指定版本才走 npx 冷下载，限时 600 秒。前端重启、依赖真实导入和端口探测都在 worker 线程，不阻塞 GUI。`.dsh-web.log` 为每次尝试写入时间、启动源、cwd、命令和超时，旧错误不再与当前尝试混淆。

用 Houdini package 安装（给顶部菜单栏追加 `dsh` 菜单，同时通过 `PYTHONPATH` 把 `python3.11libs` 加进 `sys.path`——不用 `pythonX.Ylibs` 目录约定是因为 Houdini 只自动加载匹配自身 Python 版本的目录：H21=3.11、H22=3.13，而本插件是纯 Python、与版本无关）。脚本会把本机仓库的绝对路径烘焙进 package 文件（Houdini package 的相对路径不按 package 文件位置解析，必须用绝对路径），并自动装入检测到的**每个** Houdini 版本的 pref 目录（package 按版本隔离，H21/H22 各装一份）：

```sh
python houdini/install.py
```

安装脚本现在同时完成两部分：写入所有已检测 Houdini 版本的 package，并把
`dsh-profile.requirements.json` 声明的完整能力同步到 DSH `web` profile。目前包括本地
`dsh-houdini` bundle 和随仓库发布的轻量 `dsh-vision-fallback`。后者只注册一个备用
`vision_describe` 工具，不注册 LLM provider、包装模型或“+ 自动识图”分组；不具备图像输入
能力的主模型可把 relayed render 交给独立视觉模型检查。同步会迁移移除旧
`dsh-vision-router`，且始终通过官方 `dsh plugin` 命令修改 profile。

可先 `python houdini/install.py --print` 预览 Houdini package 内容；只安装 Houdini 部分、
不联网同步 DSH profile 时显式使用 `python houdini/install.py --skip-dsh-profile`。

> 备用视觉工具会把 agent 明确选择的图片和问题发送给所配置的外部视觉服务。默认模型标识为
> `qwen/qwen3-vl-plus`；请只使用你授权的数据与 API Key。

> ⚠️ **新装/切换 Houdini 大版本后要重跑本脚本**——package 装在用户 pref 目录（如 `Documents/houdini21.0/packages`），各版本互不可见。目录名 `python3.11libs` 只是历史名字，靠 `PYTHONPATH` 注入，与 Python 版本无关（H21=3.11 / H22=3.13 均可）。

重启 Houdini 后，菜单栏出现 `DSH-Houdini`，只保留两个纯 ASCII 子项：`Open Workspace` 只唤起已运行的内嵌窗口（服务未启动时才走完整启动），不创建或切换用户当前会话；`Version & Diagnostics...` 打开即自动检查，只用两行显示 DeepSeek Harness 与 DSH-Houdini 的当前版本、最新版本和对应更新动作。DSH 从 npm 更新，插件仅在 Git 状态允许安全快进时从 `origin/main` 更新并执行 `npm install` / build。更新完成且没有运行中的 DSH turn 或 Houdini job 时会自动重启服务；忙碌时只暂存更新，按钮变为 `Restart when idle`。独立的 `Restart Services` 不再占主界面，折叠到 `Advanced diagnostics` 并改名为 `Repair and restart runtime`，只用于开发后刷新或服务修复。启动器在 :3081 真正就绪后写带监听 PID 的 `.dsh-runtime.json`，因此面板展示的是已验证的运行版本，不再把缓存候选冒充当前版本。完整启动通过正式 Host RPC 复用当前 `$HIP` 目录最近、未归档的 `houdini` preset session，没有才创建并优先挂入已有 Workspace；WebView 用一次性 hint 调公开的 `sessions.refresh/open` 导航，绝不直接写 session 文件。启动器只打开 Houdini 内嵌 WebView，不再 fallback 到外部浏览器。前端首次无缓存时用 `npx --yes @deepseek-ai/dsh web` 拉取 CLI；日常启动直接用缓存内最近写入的 `lib/bin.js`，不再次等待 npx 联网解析。临时验证或更新指定版本可在启动 Houdini 前设置 `DSH_HOUDINI_DSH_SPEC`，例如 `@deepseek-ai/dsh@0.1.0-rc.7`；这会明确走 npx。也可用 `DSH_HOUDINI_DSH_BIN` 指定本机已有的 CLI。注意 SPEC 只指定 CLI 根包，DSH 子包仍按其 semver 范围解析，不等于完整 lockfile。

> ⚠️ 服务重启会替换前端进程；版本面板会先检查活动 turn/job，检测到忙碌就暂缓，不会强制中断。

不装菜单也可以，直接在 Python Shell 里：

```python
import dsh_launcher
dsh_launcher.launch()
```

## 安装 + Houdini 模式 preset

dsh-houdini 是**插件（能力层）**，挂到 **agent preset（模式层）**。仓库带一个 `houdini` 模式 preset 模板（`presets/houdini/`），复制到用户 preset 根即可：

```sh
npm run build
python houdini/install.py                              # Houdini package + 完整 DSH web profile
dsh web                                                 # 起前端（profile 模式）
```

在 UI 新建会话时选 **「Houdini 模式」**。安装器用 DSH 官方插件命令 link 本地目录并同步
所需 bundle；改代码后 `npm run build`，再从 Houdini 诊断面板展开 `Advanced diagnostics`，执行 `Repair and restart runtime` 即可
同步 preset 与新增依赖。卸载时分别执行
`dsh plugin --profile web remove dsh-houdini dsh-vision-fallback`。

仓库另带一个 **`houdini-dev` 模式 preset**（`presets/houdini-dev/`）：工具集与 `houdini` 完全相同，仅 persona 换成 coding/development——以插件仓库为主目标、把运行中的 Houdini 会话当**测试目标**（改 `src/`/`client.js`/`houdini/python3.11libs/` 时用 `houdini_*` 工具做端到端验证）。开发/测试插件本身时选 **「Houdini 开发模式」**，复制方式同上（`presets/houdini-dev/` → `~/.dsh/.agent-presets/houdini-dev/`）。

> 为何用 preset 而不是 `--patch` overlay：dsh 的 client 模块系统靠 `require.resolve(包名/package.json)` 发现插件的 client 半，`file://` overlay 无法被解析；preset 用包名加载，client 半（`houdinitrace` 视图）才生效。

## 配置

`cordis.patch.yml`（或被 profile 引用的 bundle 层）里的 `config`：

- `bridgeUrl`（默认 `http://127.0.0.1:8765`）— 桥的地址
- `requestTimeoutMs`（默认 `120000`）— 单次桥调用超时；长任务用 `houdini_job_submit`，不受此限

`dsh-vision-fallback` 在 Web UI 的 `设置 → 插件 → 视觉备用` 中配置，保存后立即供
`vision_describe` 使用。配置刻意只有两项：

- `apiKey` — 当前视觉服务的 Key（设置页按 secret 字段遮罩）
- `model`（默认 `qwen/qwen3-vl-plus`）— `供应商/模型`；当前内置 `qwen`/`dashscope`、`openai`、`openrouter` 的 OpenAI-compatible 接口映射

它不会复制模型目录。以后增加供应商只扩展插件内部的接口映射，不增加设置项。

## 健壮性

桥对失控 agent 做了资源上限：stdout/stderr 各截断到 1 MiB、`__result__` 序列化超过 4 MiB 时丢弃、请求体超过 16 MiB 拒绝；后台 job 结束后保留 10 分钟供轮询、最多保留 1000 个（超限自动清理）。`GET /health` 除 Houdini 版本和 job 数外还返回运行中动词表的名称与 SHA-256 指纹；Host 在执行场景代码前与由 `tool-design.md` 生成的预期指纹比较，版本漂移时 fail-closed。`GET /media?path=` 只读、限图片扩展名和 64MB，把产图动词的图片字节回传给 Host。

## 已知限制

- `hou` 只能在 Houdini 主线程调用：桥把全部执行编组到主线程（GUI 下是 QTimer 泵，headless 下是 `__main__` 主循环泵），因此严格串行——后台 job 是排队异步而非并行，且代码执行期间 GUI 会像原生 cook 一样冻结；取消是协作式的——排队中的 job 在执行前被丢弃（零场景副作用），运行中的杀不掉
- 桥绑定 `127.0.0.1`，未做鉴权——不要在不可信网络上暴露端口
- 客户端超时/取消不会中断 Houdini 内已在执行的代码：调用方看到失败或取消时，场景可能已经被改——重试前先用 `houdini_query` 确认场景状态
- `dsh-tools` 的 npm 发布版本落后于 dsh 源码仓库：本包 devDependency 是 `^0.0.1-rc.1`，而当前 dsh 运行时用 `0.1.0-rc.6`。二者的 `defineTool`/输出 schema DSL 已实测一致（必填字段按属性写 `required: true`，而不是 JSON-Schema 的 `required` 数组）；若未来对不上，按你实际安装的 dsh 版本对齐 devDependency

## 后续路线（按价值排序）

1. **视觉 provider 实机验收**：轻量 fallback、render relay 和语义失败识别已完成；仍需填入授权且有配额的 Key 做同图 A/B，不能把 transport 成功当识图成功。
2. **`ctx.jobs` 后台运行时**：把 job 管理从桥侧迁移到 dsh jobs 服务，获得统一的 list/kill/output/通知。
3. **UI 卡片**：为工具补纯函数 `presentCall`/`presentResult`/`presentationMeta`。
4. **权限分层**：`tools/pre-execute` 实现 query 自动允许、exec 审批；ownership guard 继续作为 Houdini 内第二层边界。
5. **回归覆盖重建**：按当前 47 动词契约恢复最小 H21/H22/GUI smoke，不复刻已删除的历史大脚本。
