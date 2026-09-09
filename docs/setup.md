# dsh-houdini 新机安装与更新

本文描述当前受支持的 Windows 安装路径。仓库代码可移植；Houdini package、DSH profile、preset 和构建产物属于机器态，需要每台机器生成。

## 1. 前置条件

| 依赖 | 检查 |
|---|---|
| Git | `git --version` |
| Node.js 与 npm/npx | `node -v`、`npm -v`；使用所选DSH支持的Node，完整trace zstd工具需要提供zstd API的运行时 |
| Python 3（只需标准库） | `python --version`；Windows Store stub 可改用 `py -3` |
| SideFX Houdini | 至少启动过一次，以生成 `Documents/houdini*` 用户目录 |

本仓库的 `node_modules` 只用 npm 管理，不要运行 pnpm。

## 2. 拉取并构建

```powershell
git clone https://github.com/eee1723/dsh-houdini.git
Set-Location dsh-houdini
npm install
npm run build
```

构建先从节点卡JSON生成文档，再从 `docs/tool-design.md` 生成浏览器目录和Host动词契约，最后由tsc输出 `lib/`。`lib/` 和 `node_modules/` 不提交，也不要手改。只读同步检查使用 `npm run docs:check`。

## 3. 一次性安装机器态

```powershell
python houdini/install.py
```

安装器会：

- 给检测到的每个 Houdini 大版本写 `Documents/houdini*/packages/dsh-houdini.json`，把本 checkout 的 Houdini 菜单和 Python 路径注入进程；
- 按 `dsh-profile.requirements.json` 通过官方 `dsh plugin` 命令同步 `web` profile，包括本地 `dsh-houdini` 和锁定的视觉能力；
- 后续由 launcher 把仓库中的 `presets/houdini*` 同步到 `~/.dsh/.agent-presets/`。

只预览 Houdini package：

```powershell
python houdini/install.py --print
```

只安装 Houdini package、暂不同步 DSH profile：

```powershell
python houdini/install.py --skip-dsh-profile
```

新装或切换 Houdini 大版本后需要重跑安装器。目录名 `python3.11libs` 是历史名称；实际通过 `PYTHONPATH` 注入，同一份纯 Python 代码支持 H21 py3.11 和 H22 py3.13。

## 4. 启动

1. 完整重开 Houdini，让 package 和菜单生效。
2. 先把场景保存到目标工程目录，再点击 `DSH-Houdini` → `Open Workspace`。launcher 会把 `.hip` 的父目录幂等注册为 DSH workspace，并复用/创建该目录下的 Houdini 会话；服务未运行时同时同步 preset、启动 Bridge 和前端。切换到另一份 HIP 后再点一次即可切换工作区。未保存场景只使用仓库外中立 scratch，插件源码目录永不作为兜底任务工作区。
3. 在 Web UI 新建会话并选择「Houdini 模式」。开发插件本身时选择「Houdini 开发模式」。

加载刚修改的 Host、Bridge、helper 或 preset 时，打开 `Version & Diagnostics...`，展开 `Advanced diagnostics`，点击 `Repair and restart runtime`。它会先检查活动 DSH turn/Houdini job，忙碌时不会强制中断。`dsh_webview.py`、菜单 XML、安装 package 等由 Houdini 进程缓存的 UI/安装层改动需要完整重启 Houdini。

## 5. 验证

发送：

> 用 houdini_query 调用 scene_info，并列出 /obj 下所有节点。

预期：

- 工具结果出现 `verbs (N):`；
- 会话出现 `Houdini Trace` 标签页；
- 第一次场景调用没有 Host/Bridge contract mismatch；若有，执行一次 `Repair and restart runtime` 后新建会话重试；
- 其它不挂 dsh-houdini 的模式不会收到 Houdini persona。

开发侧最低验证：

```powershell
npm test
$env:HOUDINI_PATH='&'
$env:HOUDINI_NO_ENV_FILE='1'
# 仓库外隔离偏好目录；完整矩阵与边界见 development.md。
$env:HOUDINI_USER_PREF_DIR=($env:TEMP+'/dsh-regression/houdini__HVER__')
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-bridge-raw-gate.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-node-ownership.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-bridge-caught-failure.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-tab-create-failure.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-object-parenting.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-scene-network-render-contract.test.py
```

Houdini 安装路径按本机版本调整；发布前对支持的 H21/H22 各跑一遍。

## 6. 日常更新

```powershell
git pull --ff-only
npm install
npm run build
```

Host/Bridge/helper/preset 更新随后执行 `Repair and restart runtime`。`dsh_webview.py`、`houdini/install.py`、package 或菜单 XML 改动需要完整重开 Houdini；不要用 Bridge health 冒充 WebView 新代码已加载。

版本诊断面板分别管理 DeepSeek Harness npm 通道和 dsh-houdini Git 通道；不要把“更新 Harness”与“拉本仓库代码”混成同一动作。临时验证特定 DSH 根包版本可在启动 Houdini 前设置：

```powershell
$env:DSH_HOUDINI_DSH_SPEC='@deepseek-ai/dsh@<待验证的精确版本>'
```

该变量只固定 CLI 根包，不等于完整依赖 lockfile。

## 7. 视觉能力边界

受管profile仅安装dsh-houdini，并移除vision toolkit及旧视觉router/fallback。
渲染和截图经Bridge按产图来源取回字节，保存到DSH原生附件服务，作为image内容块进入当前模型；
不再调用额外识图工具，也不在会话工作区创建.dsh-houdini-media副本。
要求当前模型路由声明image输入且Host提供attachments服务；不支持的格式（例如EXR）保留工程文件，
视觉检查可生成PNG/JPEG预览。附件上传/像素检查不等于语义正确，失败明确保留未验证状态。

Houdini生产preset的skill-filesystem设置includeDefaultRoots=false、customSkillDirs=[]，
不扫描共享用户/项目技能目录。需要扩展时仅向customSkillDirs加入经过选择的目录；
插件自身的随包skills仍由src/skill.ts注册。其他全局插件贡献的技能应在对应profile/plugin配置中处理，
不能靠隐藏Trace条目改变模型可发现目录。已有历史请求保留原目录证据。

## 8. 卸载

```powershell
npx --yes @deepseek-ai/dsh plugin --profile web remove dsh-houdini
Remove-Item -Recurse -Force "$env:USERPROFILE\.dsh\.agent-presets\houdini"
Remove-Item -Recurse -Force "$env:USERPROFILE\.dsh\.agent-presets\houdini-dev"
```

再删除各 `Documents/houdini*/packages/dsh-houdini.json`。视觉插件是共享 profile 能力，不随 dsh-houdini 自动移除；确认没有其它 consumer 后再单独卸载。

## 机器态清单

| 内容 | 位置 | 换机处理 |
|---|---|---|
| 源码、docs、presets、skills | Git 仓库 | clone/pull |
| `lib/`、`node_modules/` | checkout | `npm install && npm run build` |
| Houdini package | `Documents/houdini*/packages/` | 重跑安装器 |
| DSH web profile | `~/.dsh/profiles/web/` | 重跑安装器 |
| 本地 presets | `~/.dsh/.agent-presets/` | launcher 自动同步 |
| 运行中 Bridge/前端 | Houdini/Node 进程 | Host/Bridge 用 repair；WebView/UI 模块改动完整重启 Houdini |
