# DSH ChatGPT Subscription

这是安装在**Windows x64 官方 DeepSeek Harness Desktop 0.2.1-rc.3**中的独立模型插件。它增加 `chatgpt-subscription` 提供方，使用真正的 Sign in with ChatGPT（SiWC）及官方 `https://api.openai.com/v1/responses`；与 OpenAI API Key 和 `openai-codex` 是不同路线。

在设置中连接ChatGPT账户，再从DSH原生模型菜单选择可用模型。支持范围和额度由服务端及所选账户决定；页面分别说明账户连接、计划权限与模型目录，目录可见不代表一次推理已经成功。

## 安装与使用

本插件可用于DSH的不同模式，与Houdini插件独立安装、更新和启停：

1. 准备完整的 `dsh-chatgpt-subscription-<version>.tgz`，在官方Desktop原生插件页填入本地绝对路径安装并启用。
2. 打开「设置 → ChatGPT 订阅」。如果同时使用Houdini，可另行安装并启用dsh-houdini，二者没有安装先后依赖。
3. 在本插件设置页明确开始登录，在系统浏览器完成 OpenAI 授权。系统浏览器未能自动打开时，可重新打开或复制**仅当前登录期间有效的本机安全入口**。界面不接收、不返回 OAuth 原始授权 URL、token 或手填授权码。
4. 阅读首次启用计划用量的说明，在 ChatGPT 用量页管理应用权限和额度。模型仍从 DSH 原生模型菜单选择；本插件不自动更换当前或默认模型。

普通第三方插件更新遵循官方管理入口及其重启提示；不会自行重启 Desktop 或 Houdini。禁用或卸载只撤回自己的模型／授权服务，不自动删除账户凭据、其它提供方、会话或设置。没有读取、导入或迁移旧插件／Codex 授权的入口；旧授权保持原样。

## 实现边界

- 后端是标准 Cordis 插件，仅注册自己 `chatgpt-subscription` 路由和凭据 key，不覆盖全局 `openai`、`openai-codex` 或 `llm-pi-ai/openai`。
- `store.ts` 用 DSH 原生凭据服务保存唯一事实：安装 host ID／当前选择一个 metadata record，每个账户一个独立 record。账号目录直接枚举自己 namespace，不维护第二份账号数据库。所有自有 payload 用 Windows 当前用户 DPAPI 保护，没有明文回退。
- `oauth.ts` 使用公开 SiWC 协议和 `jose` 验签；首次保存稳定 host ID、保留签发 client ID；每次使用新 state／nonce／PKCE，校验 issuer、audience、签名、时间、subject 和计划用量 scope。回调使用 `127.0.0.1` 的随机端口，不注册系统协议。
- 最终登录由原生 `AuthorizationSession.commit` 提交。取消不能在提交后伪装为未提交。刷新用公开 `withFileLock` 锁定插件自身的对应账户；锁目录只存进程标识，不存凭据。准入时通过不改值的原生 `modifyRecord` 读取最新记录，网络请求期间释放原生凭据文件锁；收到替换后短暂 CAS 保存加密 checkpoint，再验证身份，避免暂时的 JWKS 故障丢失有效替换，也不阻塞其他提供商写入。
- `adapter.ts` 组合公开 `PiAiAdapter`。外层是唯一 DSH 路由，内部使用私有 OpenAI 路由，保留原生消息、工具、图片和 provider replay 转换，不复制 encoder 或会话实现。账号在准备调用时捕获；全局切换账户只影响之后的准备，不打断已准备的另一账户调用。重连／断开才使该连接的旧准备失效，普通 token 轮换不失效。跨账号保留 canonical 消息，但不复用另一个账号的 opaque replay。
- 通过精确 peer 使用官方 Desktop rc.3 自带的 pi-ai 1.1.0 和 DSH adapter，不另装或升级宿主 SDK，不修改共享依赖解析。能力元数据、消息转换器和流 decoder 都消费该版公开接口；目录中的未知模型显示不可解析原因，不按名称猜测能力。
- `transport.ts` 用公开 pi 消息转换器／流 decoder 加官方 OpenAI SDK处理窄 SiWC HTTP策略，显式隔离 `OPENAI_ORG_ID`、`OPENAI_PROJECT_ID`、`OPENAI_CUSTOM_HEADERS` 与 debug logging，不修改进程环境；拒绝重定向。host ID 和签发 client ID 属于 OAuth query／form，不臆造推理账号请求头。
- 本提供方图像策略为最多 2048×2048 总像素预算及 1MiB 编码目标，与 Native pi adapter 默认相同，使用公开 `requestImageDimensions`，在外层 `imageRequestTarget` 与实际发送层保持一致；不是宣称自动继承所有 Native 提供方的图像设置。
- 目录读取当前账户 `/v1/models` 的 `.models`，保留服务端显示顺序。DSH 原生模型菜单只提供当前目录与已安装 pi-ai 能力元数据的交集；未知能力不会伪称支持图片或工具。
- 每次 Responses 请求固定 `store:false`、`stream:true` 和完整输入历史；按 SiWC 要求处理工具声明及禁止字段。只有 `response.completed` 才成功，未完成／失败／中断不冒充完成。
- 文本、图片和本地执行的函数工具按所选模型能力提供。此路线不提供音频转录、Files 上传、图像生成或 hosted MCP。现有教程 ASR／生图不能从此处获得 token 或环境变量回退。

## 后端消费接口

原生 Remote namespace 为 `chatgptSubscription`。`status` 参数为空，其余方法的参数均放在 `args.input`：

| 方法 | 参数／结果 |
|---|---|
| `status` | 安全账号摘要、当前账号、登录状态、模型缓存是否已读取、用量链接；不刷新 token 或发起 HTTP |
| `beginLogin` | `{accountId? , newAccount?}` → 安全 `LoginView` |
| `loginStatus` / `cancelLogin` | `{attemptId}` |
| `reopenBrowser` | `{attemptId}`，由 Host 重开原始授权页，原始 URL 不经过 renderer |
| `selectAccount` / `disconnect` | `{accountId}`；不修改 DSH 默认模型 |
| `models` | `{refresh?:boolean}`，显式目录读取后通知原生模型菜单刷新 |
| `acknowledgePlanNotice` | `{accountId}`，同一账户 record 持久确认首次计划说明，不作为模型调用门槛 |

`LoginView.launchUrl` 只在有效 pending attempt 内提供不含 token、code、hint 的随机本机入口；该 listener 用 302 跳转。登录终态或回调结束时入口关闭。账号摘要中 `sharing` 表示已授予计划权限，不证明一次真实推理成功。

## 构建与验证

只使用 npm；依赖和 lock 独立于 Houdini 根包：

```powershell
npm ci --prefix packages/dsh-chatgpt-subscription --ignore-scripts
npm run --prefix packages/dsh-chatgpt-subscription test
node packages/dsh-chatgpt-subscription/tools/pack.mjs tools/out/chatgpt-subscription-candidate
```

测试需要本机 loopback socket 权限。测试 transport 对所有 OpenAI URL 提供假响应；真实 HTTP 只到自有的 `127.0.0.1` 回调，不需要 API Key、真实账户或云请求。Windows DPAPI 测试只使用测试字节。

打包器只生成本地 tgz，移除开发依赖与脚本，不运行 publish、创建标签或修改宿主。Koffi 是精确宿主 peer（3.1.1），开发测试另声明同版 devDependency；原生安装仍遵守官方依赖与构建批准策略。

源码入口：`src/types.ts` 为安全 DTO，`src/store.ts` 为受保护原生存储，`src/oauth.ts` 为协议，`src/accounts.ts` 为账号动作，`src/adapter.ts` 为模型组合，`src/transport.ts` 为窄协议请求策略，`src/index.ts` 为标准注册和 Remote controller。原生设置页在 `client.js`。当 pi 公开请求客户端工厂可接收安全 tenant／log／redirect 选项并通过同一 wire 验证时，可移除窄 transport，继续复用原编码器和 decoder。

官方依据：[SiWC 登录](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)、[账号与刷新](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)、[模型与推理](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)、[当前限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)、[UI 指南](https://developers.openai.com/siwc/ui-ux-guidelines)。
