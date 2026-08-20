# AGENTS.md

## 项目定位

dsh-houdini：DeepSeek Harness（dsh）插件，让 agent 驱动一个正在运行的 SideFX Houdini 会话。架构：`src/`（dsh 插件，注册 5 个 `houdini_*` 工具）→ HTTP → `houdini/python3.11libs/dsh_bridge.py`（跑在 Houdini 进程内，`hou` 只存在于那里）。

## 怎么跑

- 构建：`npm install && npm run build`（先跑 `tools/gen-client-catalog.mjs` 把词表目录从 `tool-design.md` 注入 client.js，再 tsc → `lib/`；`lib/` 是产物且已 gitignore，别手改）。
- 启动：Houdini 菜单 `dsh` → `启动 / 重启 dsh`（= `dsh_launcher.launch()`：同步 preset → 重启桥 → 重启前端 → 开内嵌 UI）。
- 验证：Web UI 新建会话选「Houdini 模式」，发「用 houdini_query 列出 /obj 下所有节点」。
- 测试：`houdini/tests/`（Python 侧回归，如 `regress_verbs.py`）。
- trace 复盘：`node tools/trace-report.mjs`（缺省取最新 session）→ 单文件 HTML 到 `tools/out/`：词表目录（解析 `tool-design.md`）+ 真实时序调用线 + 裸 hou/失败分析。
- 标准 trace 审计：加载 `houdini-trace-analysis` skill；先跑其 `scripts/extract-trace-evidence.mjs` 得到确定性 JSON，再按量表分析任务契约、工具机会、Houdini 模块与词表演化。

## 技术栈

TypeScript（ESM，tsc 直出无 bundler），Cordis 插件形状 `{name, inject, Config, apply}`；Houdini 侧纯 Python（H21=py3.11 / H22=py3.13 均可，靠 PYTHONPATH 注入）；client 半是手写 CJS factory（`client.js`，不做 TS 变换）。

## 目录与约定

- `src/` → `lib/`：host 插件（工具定义 + systemPrompt guidance + HTTP client）。
- `houdini/python3.11libs/`：桥（`dsh_bridge.py`）、动词词表（`dsh_hou_helpers.py`）、一键启动（`dsh_launcher.py`）、内嵌 UI（`dsh_webview.py`）。
- `presets/houdini/`、`presets/houdini-dev/`：agent preset 模板；点 dsh 菜单时自动同步到 `~/.dsh/.agent-presets/`。
- `tools/trace-report.mjs`：trace 复盘报告生成器（session.jsonl.zstd → 单文件 HTML），产物在 `tools/out/`（已 gitignore）。
- `tools/catalog-lib.mjs` + `tools/gen-client-catalog.mjs`：词表目录解析（唯一实现）+ 构建期注入 client.js 标记区；改动词后跑 `npm run build` 刷新视图目录。
- `skills/houdini-trace-analysis/`：随插件经 `ctx.skills.register()` 发布的 trace 审计 skill；`references/known-patterns.md` 随新 trace 追加跨任务证据。
- `skills/houdini-sop-workflow/`：SOP/VEX/Copy/属性契约、模块验证阶梯和多帧完成门；复杂 SOP 任务按需加载。
- `docs/tool-design.md` 是动词词表**唯一真相源**——改动词必须同步改它；`docs/development.md` 是进度日志——改代码顺手更新。

## 关键约束

- `hou` 只能在 Houdini 主线程调用：桥内所有执行经工作队列编组到主线程。
- GUI 线程禁止阻塞探测：本机 `connect()` 到关闭的 localhost 端口会阻塞 ~300ms（无即时 RST），socket/进程等待/netstat 必须放 worker 线程。
- 插件 persona 中性：身份与工作方式（如程序化生成原则）写进 preset persona，不写进插件 guidance。
- 动词是 exec 代码的主接口，裸 `hou` 只是逃生舱；桥对裸 hou 调用做 AST advisory。
- `node_modules` 只用 npm 管：本仓库若被 pnpm 操作，pnpm 会把 npm 装的包挪进 `node_modules/.ignored/`（hideAlienModules），前端随即 ERR_MODULE_NOT_FOUND；launcher 的 `ensure_dependencies()` 可自愈，但根源上别在本仓库跑 pnpm。
- agent 的 Houdini 产出锚定 `$HIP`，不写进 dsh workspace 或本仓库。机制保证（2026-08-19 结构性纠正）：前端启动目录=会话工作区=dsh 沙箱边界，launcher 把它对准当前 hip 目录（未保存时用 `E:/dsh-houdini-workspace`）；工作区 ≠ $HIP 时 host 在结果里附 workspace note；桥 exec 裸写仓库触发 `_repo_write_advisory`（advisory 层，不硬拦）。

## 当前状态（2026-08-20）

端到端链路可用；动词追踪、裸 hou advisory、houdinitrace、HTML/evidence trace 报告与两个随包 skills 已实现。**系统定位为「共享屏幕的副驾驶」**：用户 viewport/display/selection/frame 可漂移，不对抗；视觉验证必须 `render_view(EXPLICIT_SOP)`，经隐藏 Object Merge proxy + OpenGL ROP forceobjects 只渲染显式输出，保存/恢复用户 OBJ visibility、selection、frame，并返回 fingerprint/stale/render_check；动画 A/B 用相同 `framing_frame` 锁相机。`viewport_screenshot` 只诊断用户屏幕。主目录 39 个明确动词（新增 `verb_help`），bridge 另保留旧 `set_display/display_node` 两个兼容入口；覆盖 vocabulary、scene、类型目录、node、parm、asset、geometry、render、viewport，含 SOP/OBJ display 拆分、piece/frame 验证、spare 参数创建和 layout。HDA authoring 见 §2.19；trace skill 见 §2.20；全量修复与 SOP workflow 见 §2.21。GUI exec 异常自动 undo 并回报 rollback（仅 Houdini undoable scene edits）。已知环境坑：deepseek-v4-flash 无视觉能力；本机 hython 编译 VEX 栈溢出 0xC00000FD；GUI 回归走 H21 桥。下一步见 `docs/development.md` §5（jobs 迁 `ctx.jobs`、权限分层、卡片）。
