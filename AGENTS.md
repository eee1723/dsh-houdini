# AGENTS.md

## 项目定位

dsh-houdini：DeepSeek Harness（dsh）插件，让 agent 驱动一个正在运行的 SideFX Houdini 会话。架构：`src/`（dsh 插件，注册 5 个 `houdini_*` 工具）→ HTTP → `houdini/python3.11libs/dsh_bridge.py`（跑在 Houdini 进程内，`hou` 只存在于那里）。

## 怎么跑

- 构建：`npm install && npm run build`（先跑 `tools/gen-client-catalog.mjs` 把词表目录从 `tool-design.md` 注入 client.js，再 tsc → `lib/`；`lib/` 是产物且已 gitignore，别手改）。
- 启动：Houdini 菜单 `dsh` → `启动 / 重启 dsh`（= `dsh_launcher.launch()`：同步 preset → 重启桥 → 重启前端 → 开内嵌 UI）。
- 验证：Web UI 新建会话选「Houdini 模式」，发「用 houdini_query 列出 /obj 下所有节点」。
- 测试：`houdini/tests/`（Python 侧回归，如 `regress_verbs.py`）。
- trace 复盘：`node tools/trace-report.mjs`（缺省取最新 session）→ 单文件 HTML 到 `tools/out/`：词表目录（解析 `tool-design.md`）+ 真实时序调用线 + 裸 hou/失败分析。

## 技术栈

TypeScript（ESM，tsc 直出无 bundler），Cordis 插件形状 `{name, inject, Config, apply}`；Houdini 侧纯 Python（H21=py3.11 / H22=py3.13 均可，靠 PYTHONPATH 注入）；client 半是手写 CJS factory（`client.js`，不做 TS 变换）。

## 目录与约定

- `src/` → `lib/`：host 插件（工具定义 + systemPrompt guidance + HTTP client）。
- `houdini/python3.11libs/`：桥（`dsh_bridge.py`）、动词词表（`dsh_hou_helpers.py`）、一键启动（`dsh_launcher.py`）、内嵌 UI（`dsh_webview.py`）。
- `presets/houdini/`、`presets/houdini-dev/`：agent preset 模板；点 dsh 菜单时自动同步到 `~/.dsh/.agent-presets/`。
- `tools/trace-report.mjs`：trace 复盘报告生成器（session.jsonl.zstd → 单文件 HTML），产物在 `tools/out/`（已 gitignore）。
- `tools/catalog-lib.mjs` + `tools/gen-client-catalog.mjs`：词表目录解析（唯一实现）+ 构建期注入 client.js 标记区；改动词后跑 `npm run build` 刷新视图目录。
- `docs/tool-design.md` 是动词词表**唯一真相源**——改动词必须同步改它；`docs/development.md` 是进度日志——改代码顺手更新。

## 关键约束

- `hou` 只能在 Houdini 主线程调用：桥内所有执行经工作队列编组到主线程。
- GUI 线程禁止阻塞探测：本机 `connect()` 到关闭的 localhost 端口会阻塞 ~300ms（无即时 RST），socket/进程等待/netstat 必须放 worker 线程。
- 插件 persona 中性：身份与工作方式（如程序化生成原则）写进 preset persona，不写进插件 guidance。
- 动词是 exec 代码的主接口，裸 `hou` 只是逃生舱；桥对裸 hou 调用做 AST advisory。
- `node_modules` 只用 npm 管：本仓库若被 pnpm 操作，pnpm 会把 npm 装的包挪进 `node_modules/.ignored/`（hideAlienModules），前端随即 ERR_MODULE_NOT_FOUND；launcher 的 `ensure_dependencies()` 可自愈，但根源上别在本仓库跑 pnpm。
- agent 的 Houdini 产出锚定 `$HIP`，不写进 dsh workspace 或本仓库。

## 当前状态（2026-08-18）

端到端链路可用；动词追踪、裸 hou advisory、houdinitrace 视图（**已重写为词表观察台**：左栏词表目录按域分组 + 命中计数实时点亮，右栏真实时序时间线带时间戳/耗时/状态徽章，详情折叠；目录由 `tools/gen-client-catalog.mjs` 构建期从 `tool-design.md` 注入，见 `docs/development.md` §2.15）、houdini 模式对话窗口水印已实现；另有事后复盘报告 `tools/trace-report.mjs`（§2.14）；动词词表 19 个（node/parm/geometry/render/viewport 五域 + 类型目录——渲染/截图前必须核对 display 旗标用 `set_display`/`display_node`，渲染验证用 `render_frame`/`render_check`，视口抓取用 `viewport_screenshot`）；`houdini_job_status` 支持 `wait` 长轮询；视觉闭环已实测打通：`viewport_screenshot` → 社区插件 `@anionex/dsh-vision-toolkit`（百炼 qwen-vl-max，密钥走 Settings 凭据框），识图描述与实图逐项核对准确。内嵌 webview 设置页卡顿已修（QtWebEngine 6.5.3 软件光栅 + 全屏 backdrop-filter 毛玻璃是根因，`dsh_webview.py` 加载后注入禁用 CSS，滚动 6→61 FPS；排查方法见 `docs/development.md` §2.13——可经桥 `/exec` 驱动真实 webview 跑 JS 探针）。trace 第三轮复盘（§2.14）：视觉闭环在真实 agent 任务中走通；`viewport_screenshot` 的 `frame_target` 支持 `True`（=当前 display 旗标对象），收尾自动还原被最小化的 webview 窗口；裸 hou 探索回退仍在（guidance 约束力弱）。已知坑：deepseek-v4-flash 无视觉能力（read_image 被 host 预检拦截，客观验证用 `render_check`、语义验证走 vision-toolkit）；advisory 对该模型约束力弱。下一步见 `docs/development.md` §5（jobs 迁 `ctx.jobs`、`/screenshot` 视觉闭环、权限分层）。
