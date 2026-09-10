# DSH 与插件发行兼容门

## 正式发行单元与发布门

正式产品的更新单位是一个经过验证的完整组合，不是 Git 分支或独立 DSH npm latest。安装体验与目录/失败合同见[安装与更新](setup.md#正式发行与受管安装合同)。
兼容JSON是源码运行时选择源；受管发行使用签名release.json和完整离线包。兼容记录、自动测试和草稿资产都不等于正式发布或live验收。

release.json绑定插件精确版本、源码commit、stable/candidate通道、精确Node/DSH、平台/架构、支持的Houdini版本、managerProtocol、
全量文件inventory摘要、npm锁摘要和payload名字/大小/SHA-256；严格字段/schema校验见[dsh_deployment.py](../houdini/python3.11libs/dsh_deployment.py)。
Python/Qt实际支持面仍由H21/H22资格验证决定，不以版本列表代替实测；数据按安装实例独立快照，无跨版本自动合并。
发现 Release 仅证明作者已发布，不证明资产完整、适用当前机器或可以启用。激活前必须校验清单/资产/实际运行身份；缺项、损坏、来源异常、未知 schema 均拒绝。
在线安装先确认官方不可变Release，再取release.json与release.sig.json，通过安装器内置公钥验证RSA-3072/4096 PKCS#1 v1.5 SHA-256签名，
随后校验签名绑定的payload和逐文件inventory；离线执行同一签名门。发布私钥不入仓库/包，未知key拒绝并要求可信新安装器。
公钥轮换须先分发含新公钥的安装器，不能从待验证Release自动信任新钥匙；撤销公钥同样需要可信安装器更新。
HTTPS/摘要不是签名，签名也不防御本机用户主动替换整个安装器/信任库；不得声称这是抵抗本机账户失陷的安全沙箱。

发布资格顺序：选定提交 → 锁依赖并构建 → Node/安装回归 → H21/H22 隔离与实际用户路径验收 → 生成可复验的资产 → 上传 Draft → 作者明确发布。
普通 push 只做开发同步/测试，tag 可触发候选打包但不自动转正式。Draft 和 prerelease 不进入默认正式通道；版本比较使用语义版本，不按字符串或 commit 时间推断升级。
发布包保留许可证与依赖清单；干净环境必须覆盖无 Git/Node/外部 Python、中文/空格路径、自定义 Houdini 偏好目录、受限网络、本地包安装、磁盘不足/中断/损坏包、多实例、重启启用与数据迁移回退。
用户机器不重建正式包；发布构建以冻结 lockfile 组装并验证完整依赖树，不能用仅固定 DSH 根包的 npx cache 代替发行锁。

## 源码运行时的兼容选择

DSH 的 npm `latest` 不是 dsh-houdini 的独立更新目标。安装器、launcher和manager默认只选择
[`dsh-runtime-compatibility.json`](../dsh-runtime-compatibility.json) 的精确preferred版本；其他已验证版本、未知版本即使更新进入
npx cache，也不会替换当前插件要求的版本。未命中preferred缓存时只下载对应精确根包，不选择最近修改的缓存。显式 `DSH_HOUDINI_DSH_BIN` / `DSH_HOUDINI_DSH_SPEC`
仅用于隔离资格验证，不代表发布。

面板的[dsh_release_policy.py](../houdini/python3.11libs/dsh_release_policy.py)只查询官方仓库指定的latest稳定Release，
拒绝Draft、prerelease和非vMAJOR.MINOR.PATCH标签，未发布和网络不可用分别处理。
源码和受管安装共用独立主面板与高级运行时诊断入口，按模式显示路径与有效操作。源码模式仅提供发布页链接、磁盘版本和Git/npm更新说明；受管模式经过签名/资产门后暂存安装，二者不混用路径或状态。

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
2. **组合加载**：用候选 CLI 启动隔离端口，确认 `web` profile、dsh-houdini 及原生图像附件通道
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

## 源码候选的完整用户路径验收

每个目标H21/H22版本分别在独立测试HIP/workspace、新session中执行；用户先保存自己的工作并完整重开
Houdini以加载WebView变更。仅Host/Bridge/helper变化才可用Repair and restart runtime。记录诊断中的
Host/Bridge/helper版本、执行合同与词表hash，区分磁盘源码与已加载身份；原生与Code Mode分开验收。

| 顺序 | 用户路径 | 必须核对的结果 |
|---|---|---|
| 1 | Open Workspace、重开同workspace、重连、新session | workspace与HIP关联正确，工具可用，Trace能展示新请求；旧历史不回填新源码 |
| 2 | 在新建控制节点设值/动画、同批追加参数组，再让另一节点修改失败 | 每个请求前后回读值、keys、frame、identity；只恢复失败调用，之前提交不丢失 |
| 3 | 原生与Code Mode分别调用合法0、错误表达式、缺失引用和已存在cook错误 | 写入、求值、warning/cook与几何效果分层；失败回包能显示原因与恢复状态 |
| 4 | 任务执行中使用Host停止/重连；另测排队job取消和长job提交回包丢失 | 先用request_ref或index按owner_call查原请求；不重提修改；job提交与完成分开，迟到回包不复活任务 |
| 5 | 结果未查回前过期、查回后过期、runtime更换 | 未知不冒充未执行；已保留历史不被过期抹除；新runtime不沿用旧身份和当前有效性 |
| 6 | 读取source_ref索引/原文分页，再中途纠正并续跑 | 原用户材料、澄清答案和修改可追溯；索引/局部页不当作全部要求已消费或验收完成 |
| 7 | 简单单参编辑与多部件资产各一次默认/边界扰动、集成复验 | 核对实际输出/关系和参数恢复；未测范围如实报告，局部通过不外推全局 |

停止按钮的回包是否被Host保存必须从实际session事件判断，HTTP AbortSignal回归不能替代。
控制漂移定位需要异常前后的连续回读与GUI操作；历史只有两次不同读数时不得凭空归因。
收费模型比较和外部媒体另行确定输入/预算，不由本矩阵自动启动。正式质量/成本比较须固定模型、
工具版本、任务信息和预算，只改变一个因素；信息不足短请求与信息等价短/长输入分别评价。

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
每个插件窗口使用自有内存QWebEngineProfile，页面先于profile销毁，退出时回收窗口；不共享Houdini默认磁盘profile，防止不同GUI进程争用浏览器存储。

