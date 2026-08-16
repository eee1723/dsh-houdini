# dsh-houdini 新机安装步骤（setup）

> 换电脑 / 重装系统后，照本文从零复现 dsh-houdini。
> 原则：**仓库里的代码和模板完全可移植**（无功能性硬编码路径）；但下面第 4–6 步
> 是「机器态」（pnpm link、Houdini package、本地 preset），不跟随 Git，必须在新机上重做。
>
> 本文假设 Windows + Houdini 20.5+（21.x 更佳）。macOS/Linux 仅路径写法不同，步骤一致。

---

## 0. 前置要求

| 依赖 | 用途 | 检查 |
|---|---|---|
| git | 拉代码 | `git --version` |
| Node.js（≥18） | 构建插件 | `node -v` |
| Python 3（任意，仅标准库） | 跑 `install.py` | `python --version` |
| dsh CLI | `dsh plugin add` | `npx --yes @deepseek-ai/dsh --version` |
| SideFX Houdini | 运行桥/场景 | 打开一次确认能启动 |

> `dsh` CLI 无需全局安装：全文用 `npx --yes @deepseek-ai/dsh …` 即可（首次自动拉取）。
> 想固定版本可 `npm i -g @deepseek-ai/dsh`。

> Windows 上 `python` 可能是 Microsoft Store 占位 stub（报错 "Python was not found;
> run without arguments to install from the Microsoft Store"）：改用 `py -3`，
> 全文 `python xxx` 换成 `py -3 xxx`。

---

## 1. 拉代码

```sh
git clone https://github.com/eee1723/dsh-houdini.git
cd dsh-houdini
```

> 仓库是 **private**，clone 需要你能访问该账号（gh CLI 或 SSH key 已配好）。

---

## 2. 安装依赖 + 构建

```sh
npm install
npm run build          # tsc 编译 src/ → lib/
```

> `lib/`、`node_modules/` 已被 `.gitignore` 排除，构建产物本地生成、不提交。

---

## 3. 安装 Houdini 侧（菜单 + python 路径）

```sh
python houdini/install.py
```

作用：把**本机 checkout 的绝对路径**烘焙进 `Documents/houdini*/packages/dsh-houdini.json`，
并给每个已检测到的 Houdini 版本各装一份（package 按 pref 目录隔离）。

- 预览不写文件：`python houdini/install.py --print`
- 指定目录：`python houdini/install.py --packages-dir <dir>`
- **重开 Houdini** 后，菜单栏出现顶级 `dsh` 菜单（`dsh` → `启动 / 重启 dsh`）。

> 新装/切换 Houdini 大版本后要**重跑本脚本**（H21 读 `houdini21.0/packages`、H22 读 `houdini22.0/packages`）。

---

## 4. 链接插件进 profile（pnpm link，让包名可解析）

```sh
npx --yes @deepseek-ai/dsh plugin --profile web add "$(pwd)"
```

作用：把本地 checkout 以 `link:` 依赖加入 `web` profile 的 `node_modules`，使 `dsh-houdini`
这个**包名**可被 Node 解析。这一步是 client 半（`houdinitrace` 视图）能被发现的**前提**——

> dsh 的 client 模块系统靠 `require.resolve(包名/package.json)` 发现插件的 client 半，
> 只有「包名加载」才生效，`file://` overlay 不行。

---

## 5. 复制 houdini 模式 preset

把仓库里的模板复制到用户 preset 根：

```sh
# Windows (PowerShell)
Copy-Item -Recurse -Force presets\houdini "$env:USERPROFILE\.dsh\.agent-presets\houdini"
```

作用：注册一个名为 **「Houdini 模式」** 的 agent preset（persona = Houdini automation agent +
挂 dsh-houdini），与 `标准/创造/极简` 并列，互不覆盖。

---

## 6. 启动 + 选模式

1. 打开 Houdini，点菜单 **`dsh` → `启动 / 重启 dsh`**（= 起桥 + 起前端 + 等前端就绪后开内嵌 UI；
   首次运行 npx 需拉取 CLI，会显示进度对话框，可能要等几分钟）。
2. 在 Web UI **新建会话**时，模式选择器里选 **「Houdini 模式」**。

> 前端用 `npx @deepseek-ai/dsh web --port 3081`（profile 模式，无 `--patch`）；
> 桥默认 `http://127.0.0.1:8765`，跑在 Houdini 进程内。

---

## 7. 验证

选「Houdini 模式」后，随便发一句：

> 用 houdini_query 列出 /obj 下的所有节点，再用 describe 看看状态

预期：

- 工具结果里出现 `verbs (N):` 段（动词追踪，来自 bridge tracer）；
- 会话顶部标签页出现 **`Houdini Trace`**（与「对话」「轨迹」并列）；
- agent 回复里不再混入「你在驱动 Houdini」到**其它**模式（`标准/创造` 不挂 dsh-houdini）。

---

## 8. 日常更新（改代码后）

```sh
git pull
npm run build
```

然后点 Houdini 菜单 **「启动 / 重启 dsh」**（重载 bridge 的 Python + 重启前端）。

---

## 9. 卸载

```sh
# 从 web profile 移除插件（同时移除依赖和 patch 层）
npx --yes @deepseek-ai/dsh plugin --profile web remove dsh-houdini

# 删除本地 preset
Remove-Item -Recurse -Force "$env:USERPROFILE\.dsh\.agent-presets\houdini"

# 删除 Houdini package（删掉 Documents/houdini*/packages/dsh-houdini.json）
```

---

## 附：机器态 vs 仓库态（为什么换机要重做 4–6 步）

| 内容 | 归属 | 换机后 |
|---|---|---|
| `src/`、`client.js`、`houdini/python3.11libs/`、`presets/houdini/`、`docs/` | 仓库（Git） | ✅ 自动带过去 |
| pnpm link（`dsh-houdini` 包名解析） | `~/.dsh/profiles/web/node_modules` | ❌ 重做第 4 步 |
| Houdini package（绝对路径） | `Documents/houdini*/packages/` | ❌ 重做第 3 步 |
| 本地 preset | `~/.dsh/.agent-presets/houdini/` | ❌ 重做第 5 步 |
| 构建产物 `lib/`、`node_modules/` | 本地（gitignore） | ❌ 重做第 2 步 |
| Houdini 桥进程 | Houdini 进程内 | ❌ 点「启动 / 重启 dsh」 |
