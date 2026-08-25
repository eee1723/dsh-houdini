# dsh-houdini 新机安装与更新

本文描述当前受支持的 Windows 安装路径。仓库代码可移植；Houdini package、DSH profile、preset 和构建产物属于机器态，需要每台机器生成。

## 1. 前置条件

| 依赖 | 检查 |
|---|---|
| Git | `git --version` |
| Node.js 18+ 与 npm/npx | `node -v`、`npm -v` |
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

构建先从 `docs/tool-design.md` 生成浏览器目录和 Host 动词契约，再由 tsc 输出 `lib/`。`lib/` 和 `node_modules/` 不提交，也不要手改。

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
2. 点击 `DSH-Houdini` → `Open Workspace`。服务未运行时会同步 preset、启动 Bridge 和前端，并打开内嵌 UI；服务已健康时只唤起窗口。
3. 在 Web UI 新建会话并选择「Houdini 模式」。开发插件本身时选择「Houdini 开发模式」。

加载刚修改的 Host、Bridge 或 preset 时，打开 `Version & Diagnostics...`，展开 `Advanced diagnostics`，点击 `Repair and restart runtime`。它会先检查活动 DSH turn/Houdini job，忙碌时不会强制中断。

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
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-bridge-raw-gate.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-node-ownership.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-bridge-caught-failure.test.py
& 'C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe' tools/tests/dsh-tab-create-failure.test.py
```

Houdini 安装路径按本机版本调整。

## 6. 日常更新

```powershell
git pull --ff-only
npm install
npm run build
```

普通代码更新随后执行 `Repair and restart runtime`。只有 `houdini/install.py`、package 或菜单 XML 改动时需要完整重开 Houdini。

版本诊断面板分别管理 DeepSeek Harness npm 通道和 dsh-houdini Git 通道；不要把“更新 Harness”与“拉本仓库代码”混成同一动作。临时验证特定 DSH 根包版本可在启动 Houdini 前设置：

```powershell
$env:DSH_HOUDINI_DSH_SPEC='@deepseek-ai/dsh@0.1.0-rc.7'
```

该变量只固定 CLI 根包，不等于完整依赖 lockfile。

## 7. 视觉能力边界

当前安装清单仍使用锁定的 `dsh-vision-router`。它负责路由，不保证当前主模型或免费 provider 一定能读取图片。视觉工具的 transport、bootstrap 或 presentation 成功都不等于语义识图成功；插件只在 semantic inspection 真正成功后允许宣称视觉已验证。

替代视觉插件应先在隔离 profile 用同一组 Houdini render 做 A/B，并使用用户授权、可用且有配额的 provider。当前候选与未完成验收见 `development.md` §2.35 和 §5。

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
| 运行中 Bridge/前端 | Houdini/Node 进程 | `Repair and restart runtime` |
