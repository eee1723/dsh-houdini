# AGENTS.md

## 项目定位

dsh-houdini 是 DeepSeek Harness（dsh）插件，让 agent 驱动一个正在运行的 SideFX Houdini 会话。链路：`src/`（注册 5 个 `houdini_*` 工具）→ HTTP → `dsh_bridge.py`（主线程工作队列）→ `dsh_hou_helpers.py`（49 动词）。`hou` 只存在于 Houdini 侧 Python 模块，Node Host 不直接调用 HOM。

## 怎么跑

- 构建：`npm install && npm run build`。生成器从 `docs/tool-design.md` 同时刷新 `client.js` 目录和 `src/generated-verb-contract.ts`，再由 tsc 输出 `lib/`；不要手改生成区或 `lib/`。
- 启动：Houdini 菜单 `DSH-Houdini` → `Open Workspace`。加载新代码/修复运行时时，打开 `Version & Diagnostics...` → `Advanced diagnostics` → `Repair and restart runtime`。
- 验证：Web UI 新建「Houdini 模式」会话，发「用 houdini_query 列出 /obj 下所有节点」。Host 会在第一次场景调用前比较自身词表指纹与运行中 Bridge；不一致会拒绝执行并要求重启服务。
- 测试：`npm test` 跑构建和全部 Node 确定性回归；需要 HOM 的回归在 `tools/tests/*.test.py`，目标版本用 `hython` 跑。至少再执行 raw-gate、node-ownership、caught-failure、tab-create-failure 和 scene/network/render contract；发布前同时跑 H21/H22。
- trace：先按 `houdini-trace-analysis` skill 跑 `extract-trace-evidence.mjs`，再跑 `node tools/trace-report.mjs`。报告必须区分目录广度、调用含动词率、动词密度、只读裸探针、被 Gate 拦截和成功裸修改。

## 技术栈与目录

- TypeScript ESM（tsc 直出，无 bundler）；Cordis 形状 `{name, inject, Config, apply}`；`client.js` 是手写 CJS factory。
- `houdini/python3.11libs/`：Bridge、动词 helper、launcher、版本诊断、WebView。纯 Python 通过 `PYTHONPATH` 同时支持 H21 py3.11 / H22 py3.13。
- `presets/houdini*`：生产/开发 persona；launcher 自动同步到 `~/.dsh/.agent-presets/`。
- `skills/`：trace、SOP、Solaris/Karma、rig/animation、skill-governance 五个随包 skills。
- `docs/tool-design.md` 是动词目录唯一真相源；`docs/development.md` 记录当前进度和历史证据。

## 关键约束

- `hou` 只能在 Houdini 主线程调用；所有执行经 Bridge 工作队列串行编组。GUI 线程不得做 socket/进程/netstat 阻塞探测。
- 插件 guidance 保持 persona 中性，只放稳定执行契约；身份和程序化工作方式放 preset；领域 recipe 放按需 skill。
- 动词是场景修改主接口，裸 `hou` 是只读/低层逃生舱。Raw Gate 默认开启；动词已覆盖的裸修改不可用 `allow_raw` 旁路。
- 节点可读不等于可写。mutation 默认只作用于当前 DSH session 创建的节点；foreign 节点只有用户明确指定时才可用单次 `allow_foreign`。render service 永不豁免。
- 视觉 transport、bootstrap、presentation 与语义识图是四件事。没有成功 semantic inspection 就必须写“视觉未验证”；`render_check` 只证明文件/像素事实。
- `render_view(EXPLICIT_SOP)` 使用持久 `__dsh_houdini_*` 服务；任务收尾复用、不删除。动画 A/B 使用同一 `framing_frame`。
- `node_modules` 只用 npm 管；不要在本仓库运行 pnpm。Houdini 产出锚定 `$HIP`，不写进 workspace 或插件仓库。

## 当前状态（2026-09-01）

端到端链路、49 个目录动词、五个 skills、ownership guard、Raw Gate、rollback、隔离 `render_view`、HTML/evidence trace 已实现。2026-09-01 从 `cf1f1e8` 完整冷启动 H21 后，Bridge 49 动词/指纹 `4f3516dec006…`、Web 200、异步 WebView、Host/Bridge 握手与真实 Houdini 模式 `houdini_query`/Trace 只读分类均通过；session `45798bd2-41a6-4b12-9dfa-fb62b25faa45` 为 1 次无动词只读 HOM probe，0 mutation、0 Gate block、0 rollback。13 个 Node 回归已兼容 Windows CRLF，H21/H22 核心 HOM/launcher/manager/profile/seed 回归也重新通过，当前没有待加载的运行时修复。

生产视觉能力固定为本机已验证好用的 `@anionex/dsh-vision-toolkit@0.1.7`：按需 skill 激活 10 个独立视觉工具，provider/model/凭据由 profile 设置管理；旧 `dsh-vision-router` 与本地 `dsh-vision-fallback` 均退役。每次任务仍须区分 transport、bootstrap、presentation 与 semantic inspection，升级 toolkit/provider 前做隔离同图 A/B。开发依赖已与生产 DSH 0.1.1-rc.2 对齐，五个 `houdini_*` 工具已有纯函数调用/结果卡片与回放回归。

跨能力族 discovery 已完成，但因模型替换、额度中止和 evaluator 输入未完全冻结，只作为发现证据。B0 smoke/brief/answers/seed/evaluation schema、真实产物与跨文件 hash validator 已实现；通用 seed generator 已支持空场景和固定 shaderball，三族 calibration seed 输入已用 H21 重复生成并通过结构 identity/真实 HIP hash 校验，H21/H22 HOM 回归通过。执行模型已选 `kimi-coding/k3` 与 `apikeyfun/glm-5.3-flash`；2026-09-01 同图、无工具直连探针验证两者当前 provider 路径均可原生看图，GLM 至少需要 1500 max tokens 才避免 reasoning 挤占正文。下一顺位：冻结独立 evaluator prompt/sealed 实例和最终 protocol version，再运行三族非评分 smoke 与未见留出。生产面不得写 benchmark 实例答案；`ctx.jobs`、approval 层和大规模模块拆分继续放在证据阶段之后。`houdini_query`/`houdini_exec` 暂时保留为两个工具，是否合并只按后续误选率、额外调用与安全收益证据评估。
