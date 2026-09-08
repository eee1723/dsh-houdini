# DSH 更新兼容门

DSH 的 npm `latest` 只是可下载候选，不是 dsh-houdini 可运行版本。默认 launcher 只激活
[`dsh-runtime-compatibility.json`](../dsh-runtime-compatibility.json) 中精确列出的版本；未知版本即使已进入
npx cache，也不会成为日常 serving runtime。显式 `DSH_HOUDINI_DSH_BIN` / `DSH_HOUDINI_DSH_SPEC`
仅用于隔离资格验证，不代表发布。

## 两个独立 surface

| Surface | 内容 | 变更后的必跑门 |
|---|---|---|
| Agent surface | guidance、preset、skills、工具 schema/行为、动词合同 | Node + H21/H22 Houdini 回归；按风险运行模型 smoke/矩阵 |
| Compatibility surface | client UI、launcher/manager、Web auth/RPC、profile bundle、QtWebEngine 兼容 | Node + H21/H22 runtime、浏览器 RPC、Trace、workspace/session、第三方 bundle smoke；不因纯 UI 修复自动重跑模型矩阵 |

两者分别写入 `benchmark/baseline.json` 的 `agentSurfaceSha256` 和
`compatibilitySurfaceSha256`。一次变更可以同时触发两边，但不得用一边的通过冒充另一边。

## 新 DSH 版本的资格流程

保持当前 serving runtime 在线，依次完成：

1. **下载但不提升**：把候选放进 cache；不要改 `preferredVersion`，不要让普通 Open Workspace 选择它。
2. **组合加载**：用候选 CLI 启动隔离端口，确认 `web` profile、dsh-houdini 和锁定的 vision bundle
   完整加载，无 module-evaluation、peer API 或 settings migration 错误。
3. **Host transport**：验证根 token → signed cookie、无 cookie 401、带 cookie RPC 200；覆盖
   `session/list`、`workspace/create`、`session/create`、`session/cancel` 和活动状态读取。记录 endpoint 与 payload wire。
4. **Houdini 21/22 WebView**：由 live Houdini 持有 Node 前端，不用一次性外部 hython 冒充；页面内回读
   必需 Web API，验证发送/停止/重连。缺失 API 只能用规范、幂等、DocumentCreation polyfill，且必须实测。
5. **Client views**：打开一个已有 Houdini 工具调用的 completed session；Houdini Trace 的调用数、动词数、
   failure/rollback 与离线 evidence 一致。不得读取未声明的 client store 内部字段；只消费正式 standard props/target snapshot。
6. **Workspace/session**：已保存 HIP 父目录能幂等注册；同 workspace 正确复用，换 HIP 正确切换；未保存场景只进仓库外 scratch。
7. **第三方 bundle**：至少创建一个新 Agent，加载/卸载每个受管 bundle；检查 Session API、Settings API 和
   client module API。临时 repair 必须 exact-version、exact-callsite、幂等且 fail-closed，并登记删除条件。
8. **回归与提升**：`npm test`；H21/H22 launcher/manager 及 AGENTS.md 指定 HOM suites；记录真实 PID parent、
   DSH/plugin/bundle 版本和两个 surface hash。全部通过后才把精确版本加入 compatibility manifest，并显式设置 preferred。

任何一步失败都保持旧 serving runtime。回滚只改变兼容清单的 preferred release 或显式启动已验证旧组合；
不删除 Session、HIP、workspace 或插件仓库。若旧 DSH 需要不同第三方 bundle 版本，必须把整个组合视为另一条
release 记录，不能假设 RPC adapter 向后兼容就代表 profile 也向后兼容。

## 兼容适配的代码责任

[dsh_web_auth.py](../houdini/python3.11libs/dsh_web_auth.py)处理process-token cookie与
slash/generated-args RPC；[client.js](../client.js)消费公开Trajectory snapshot；
[dsh_webview.py](../houdini/python3.11libs/dsh_webview.py)在DocumentCreation注入必要Web API补丁；
[profile sync](../houdini/python3.11libs/dsh_profile_sync.py)只对精确toolkit版本/调用点做兼容修补。
WebView鉴权重定向已加载主页面；不能在loadFinished再导航一次以传session hint，否则可能中断
首个页面的inventory/inspect初始化请求。显式session通过同源DocumentCreation脚本写入URL，
供现有client消费，加载后撤销脚本；token不进入脚本，失败仍走异步重试。
隔离真实Qt入口见[dsh-webview-navigation](../tools/tests/dsh-webview-navigation.test.py)，
覆盖cookie重定向、单次app bootstrap、加载期间RPC、会话切换和普通重开；不替代live端到端验收。
支持组合来自兼容JSON；一次探测结果不能成为永久live状态，部署验证记录不保存在本设计文档。

