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
- **[`skills/houdini-solaris-karma-workflow/SKILL.md`](skills/houdini-solaris-karma-workflow/SKILL.md)** — Solaris/USD、MaterialX、Karma 与正式渲染交付工作流。
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

每次 exec 还会在结果里带一个 **`verbs` 字段**（动词追踪）：bridge 给每个动词包了运行时 tracer，记录每次动词调用的 `{verb, args, kwargs, ok, result/error, ms}`，`hou.Node` 自动转 path，失败以 `ok:false` 记录。stdout 同时打印 `[verb] ...` 摘要行。这是当前 `Houdini Trace` 视图和离线 trace evidence 的数据层（见 `docs/tool-design.md` §8）。

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

## Houdini 菜单与运行时刷新

顶部 `DSH-Houdini` 菜单只保留两个入口，职责明确分开：

- `Open Workspace`：健康服务存在时只唤起内嵌窗口，不重载页面、不切换当前会话；缺少前端时才执行完整启动。
- `Version & Diagnostics...`：检查 DSH npm 通道与 dsh-houdini Git 通道。开发后加载新 Host、Bridge 或 preset，展开 `Advanced diagnostics` 并执行 `Repair and restart runtime`。

显式 repair 会同步 preset、重载 Houdini 内 Bridge、替换 DSH 前端，并通过正式 Host RPC 复用或创建与当前 `$HIP` 工作区匹配的 `houdini` preset session。诊断面板会先检查活动 DSH turn/Houdini job，忙碌时不强制中断；普通 `Open Workspace` 不承担 repair 或工作区重建。等待前端期间会显示分阶段进度；日常启动直接使用 project-local npx cache 中已验证的 CLI，首次无缓存或显式指定版本才走 npx。启动来源、cwd、命令和错误写入 `.dsh-web.log`，就绪后 `.dsh-runtime.json` 记录实际监听 PID 与版本。

安装脚本给顶部菜单栏追加 `DSH-Houdini` 菜单，并通过 `PYTHONPATH` 把 `python3.11libs` 加进 `sys.path`。目录名不依赖 Houdini 当前 Python 小版本：同一份纯 Python 代码支持 H21 py3.11 与 H22 py3.13。脚本把本机 checkout 的绝对路径写入 package，并安装到检测到的每个 Houdini 版本 pref 目录：

```sh
python houdini/install.py
```

安装脚本现在同时完成两部分：写入所有已检测 Houdini 版本的 package，并把
`dsh-profile.requirements.json` 声明的完整能力同步到 DSH `web` profile。目前包括本地
`dsh-houdini` bundle 和锁定的 `@anionex/dsh-vision-toolkit@0.1.7`。后者按需加载
`vision-tools` skill，并提供 `vision_glance`、ground/detect、crop/trace、pixel diff、长图 OCR、
前景提取、主色分析和本地 HTML 截图共 10 个独立工具。同步会迁移移除旧
`dsh-vision-router` 和已退役的本地 `dsh-vision-fallback`，且始终通过官方 `dsh plugin`
命令修改 profile。

可先 `python houdini/install.py --print` 预览 Houdini package 内容；只安装 Houdini 部分、
不联网同步 DSH profile 时显式使用 `python houdini/install.py --skip-dsh-profile`。

> `vision_glance`、ground/detect 和非 split-only 的长图 OCR 会把 agent 明确选择的图片与问题
> 发送给所配置的外部视觉服务；crop/trace/pixel diff/前景提取/主色/HTML 截图走本地流水线。
> 请只使用你授权的数据、端点与 DSH Credential。

> ⚠️ **新装/切换 Houdini 大版本后要重跑本脚本**——package 位于版本隔离的用户 pref 目录（如 `Documents/houdini21.0/packages`），各版本互不可见。

版本面板中的 DSH 更新从 npm 获取；插件更新只在 Git 状态允许安全快进时从 `origin/main` 更新并执行 `npm install` / build。更新完成且运行时空闲时自动激活；忙碌时暂存为 `Restart when idle`。临时验证特定 DSH 根包可在启动 Houdini 前设置 `DSH_HOUDINI_DSH_SPEC`，也可用 `DSH_HOUDINI_DSH_BIN` 指向已有 CLI；前者只固定 CLI 根包，不等于完整依赖 lockfile。

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
`dsh plugin --profile web remove dsh-houdini @anionex/dsh-vision-toolkit`。

仓库另带一个 **`houdini-dev` 模式 preset**（`presets/houdini-dev/`）：工具集与 `houdini` 完全相同，仅 persona 换成 coding/development——以插件仓库为主目标、把运行中的 Houdini 会话当**测试目标**（改 `src/`/`client.js`/`houdini/python3.11libs/` 时用 `houdini_*` 工具做端到端验证）。开发/测试插件本身时选 **「Houdini 开发模式」**，复制方式同上（`presets/houdini-dev/` → `~/.dsh/.agent-presets/houdini-dev/`）。

> 为何用 preset 而不是 `--patch` overlay：dsh 的 client 模块系统靠 `require.resolve(包名/package.json)` 发现插件的 client 半，`file://` overlay 无法被解析；preset 用包名加载，client 半（`houdinitrace` 视图）才生效。

## 配置

`cordis.patch.yml`（或被 profile 引用的 bundle 层）里的 `config`：

- `bridgeUrl`（默认 `http://127.0.0.1:8765`）— 桥的地址
- `requestTimeoutMs`（默认 `120000`）— 单次桥调用超时；长任务用 `houdini_job_submit`，不受此限

`@anionex/dsh-vision-toolkit` 在 Web UI 的 `设置 → 视觉工具` 中配置。远程视觉工具需要
OpenAI-compatible 或 Anthropic 视觉端点、模型和 DSH Credential，并应在设置页显式执行
“测试连接”；本地工具不需要视觉 API Credential。会生成文件的工具只写入当前工作区的
`.dsh-vision-toolkit/artifacts`，并返回可预览、下载或继续复用的 Artifact 描述。

模型上下文默认只暴露轻量的 `vision_toolkit_activate` 引导；agent 加载 `vision-tools` skill 后，
10 个 `vision_*` 执行工具才进入该 agent 的 schema，避免每轮提示词无条件膨胀。视觉 transport、
runtime bootstrap、Artifact presentation 与语义识图仍是四层独立证据；只有 inspection 工具返回了
真实图像语义，才能声称“视觉已验证”。

## 健壮性

桥对失控 agent 做了资源上限：stdout/stderr 各截断到 1 MiB、`__result__` 序列化超过 4 MiB 时丢弃、请求体超过 16 MiB 拒绝；后台 job 结束后保留 10 分钟供轮询、最多保留 1000 个（超限自动清理）。`GET /health` 除 Houdini 版本和 job 数外还返回运行中动词表的名称与 SHA-256 指纹；Host 在执行场景代码前与由 `tool-design.md` 生成的预期指纹比较，版本漂移时 fail-closed。`GET /media?path=` 只读、限图片扩展名和 64MB，把产图动词的图片字节回传给 Host。

## 已知限制

- `hou` 只能在 Houdini 主线程调用：桥把全部执行编组到主线程（GUI 下是 QTimer 泵，headless 下是 `__main__` 主循环泵），因此严格串行——后台 job 是排队异步而非并行，且代码执行期间 GUI 会像原生 cook 一样冻结；取消是协作式的——排队中的 job 在执行前被丢弃（零场景副作用），运行中的杀不掉
- 桥绑定 `127.0.0.1`，未做鉴权——不要在不可信网络上暴露端口
- 客户端超时/取消不会中断 Houdini 内已在执行的代码：调用方看到失败或取消时，场景可能已经被改——重试前先用 `houdini_query` 确认场景状态
- 开发期 `dsh-tools` / `dsh-system-prompt` 已与当前生产 DSH `0.1.1-rc.2` 对齐；升级 DSH 时须同步审计这两个直接接口依赖并跑 `npm test`，避免 schema DSL、输出 metadata 或 presenter 类型静默漂移

## 后续路线

下一阶段已选择“跨域能力证据优先”：在机械程序化资产、真实 solver/cache 模拟和
Solaris/Karma lookdev 三个能力族中，以两个模型完成发现矩阵，并用确定性检查、盲语义描述和
目标核验三层独立评审衡量实际成功、自主发现缺陷和有效返工。评测实例与生产 agent 信息严格隔离：
常驻 guidance、preset、skills 和工具不写 benchmark ID、对象配方、目标参数或评分答案；改进后必须
通过未见同族实例和跨域反例，原题回归只证明没有退化。主矩阵完成前不先扩成结构化任务本体，也不
并行迁移 jobs/权限层来改变实验底座。

完整任务、评分、停止条件和工具/skill 准入门见
[`docs/cross-domain-benchmark-plan.md`](docs/cross-domain-benchmark-plan.md)。`ctx.jobs` 迁移、query/exec
权限分层和最小 H21/H22/GUI 回归仍保留为工程 backlog，在 benchmark 基线稳定后恢复。
