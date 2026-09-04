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

## 本轮基准证据

DSH `0.1.2-rc.1` 的破坏面包括 process-token cookie、slash/generated-args RPC、Session
`snapshotEvents()`、Conversation/Trajectory target snapshot，以及 QtWebEngine 108 缺少的
`Promise.withResolvers` / `AbortSignal.any`。K3 completed session `429506d9…` 的离线证据为
936 events、35 tool calls、29 Houdini calls、117 verbs；修复后的 live Houdini Trace 精确显示
29、23/29、117、16/50 和 5 个只读探针，浏览器内 `session/list` / `session/cancel` 均 HTTP 200。

