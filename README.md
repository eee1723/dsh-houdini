# dsh-houdini

<img src="assets/dsh-houdini.png" alt="DSH-Houdini Logo" width="160">

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的 Houdini 插件，在官方 DSH Desktop 中绑定、打开和操作真实场景，帮助用户制作可编辑、能继续修改的工程与工具。

**当前处于维护者实测阶段，暂不发布新版。** `main` 已收敛为官方 Desktop 上的标准插件；本次标准插件尚未公开发布到 GitHub Releases 或 npm。测试包由维护者单独提供，[历史 Releases](https://github.com/eee1723/dsh-houdini/releases) 中的独立工作台包不对应当前安装方式。实测与发布待办统一维护在[交接](docs/handoff.md#h-01-标准插件发布与用户加载)。

DSH 负责模型、账户、会话、工作区和通用 Agent 任务；插件负责 Houdini 接入、操作工具与领域资料。Houdini 菜单进入同一个 Desktop、对话和现场，不另维护 Qt 聊天工作台或私有 DSH 运行时。领域控件仅在当前对话选择 **Houdini 模式** 时出现，其他模式和默认选择保持原样。

## 兼容与试用

| 项目 | 当前范围 |
|---|---|
| 平台 | Windows x64 |
| 官方宿主 | DSH 0.2.1-rc.3；以[精确兼容清单](dsh-runtime-compatibility.json)为准 |
| Houdini | 21.0 / 22.0；实际验证点为 21.0.440 和 22.0.368 |
| 交付形式 | 包含 Houdini 组件与私有媒体工具的完整 `.tgz` |
| 发布状态 | 等待维护者实测确认；代码推送和 CI 通过均不代表正式发布 |

取得维护者提供的候选包后：

1. 安装兼容的官方 DSH Desktop，并在原生模型设置中配置可用主模型。
2. 将完整 `.tgz` 保存到本机，在 Desktop 原生插件管理中填入其本地绝对路径安装，无须解压。
3. 点击 **立即启用**，或在插件列表启用 `dsh-houdini`；新装插件默认停用。
4. 新建或选择 **Houdini 模式** 的对话，从现场控件选择已连接窗口，或选择 Houdini 安装后新建、打开 HIP。
5. 后续也可从 Houdini 的 **DSH-Houdini → Open Workspace** 快捷进入同一宿主。

新开 Houdini 前会自动准备组件。已经打开但没有加载组件、或仍加载旧版组件的窗口，需要用户保存后重开。普通用户不需要安装 Node、编译源码或配置 FFmpeg PATH。推荐下载完整包后本地安装；远程直链及缓存复用仍有[待核对边界](docs/handoff.md#h-01-标准插件发布与用户加载)。完整步骤与卸载方式见[安装说明](docs/setup.md)。

旧用户升级时，安装器仅停用能确认属于旧版插件的入口并保存可恢复备份；未知或混合脚本保持原样。旧运行包、凭据、会话、附件和 HIP 保留，历史恢复另行核对。安装磁盘文件、进程已加载版本与用户现场测试分别确认。

## 教程分析与配置

可以直接在 Houdini 对话中说「帮我配置教程分析」，或从 **设置 → 教程视频 → 让 Agent 帮我配置** 开始。Agent 先读当前状态，只补缺少的服务、准确模型和必要参数；页面展示配置状态、凭据是否存在与本机依赖诊断。

API Key 由用户在安全输入框直接录入 DSH 原生凭据服务，不作为聊天或提问答案。已有 DSH 提供方可以明确复用，独立语音服务也可单独配置，无须添加假聊天模型。ASR / STT 在这里是同一项语音转文字能力；主聊天账户不自动代表拥有语音 API 授权。

FFmpeg / ffprobe 随完整包交付，普通 Python 自动从 Houdini 安装定位；只解析教程不必先连接场景。当前支持明确的文件转录协议，实时流、异步服务与本地推理部署按实际能力处理。配置存在不等于转录或画面识别已经验证，详见[教程配置](docs/setup.md#教程视频与转录设置)与[按需引导](skills/houdini-video-tutorial/references/transcription-setup.md)。

## 工具

工具分别负责现场观察、执行、原生界面截图、请求查回、历史资料、图像通道和长任务控制。每个工具为何存在、输入和返回详见[工具说明](docs/tools.md)。

Python能力目录见[动词词表](docs/tool-design.md)。陌生节点可用node_info，准确动词签名可用verb_help；对象父级使用set_object_parent。构造方法与操作顺序由模型根据任务选择。

## 领域资料

| 资料 | 用途 |
|---|---|
| [任务拆分](skills/houdini-task-decomposition/SKILL.md) | 按编辑目标和依赖逐模块构建、观察与集成 |
| [独立执行](skills/houdini-isolated-execution/SKILL.md) | 团队成员按需用一次性hython自验证构建、工程副本和渲染 |
| [SOP](skills/houdini-sop-workflow/SKILL.md) | 程序化模型、局部修改和几何观察 |
| [表面外观](skills/houdini-surface-workflow/SKILL.md) | 参考图分析、表面细化程度、UV与统一SOP贴图预览 |
| [COP（按需能力）](skills/houdini-cop-workflow/SKILL.md) | 程序化贴图和图层；完整材质与教程交付仍待验收 |
| [工具开发](skills/houdini-tool-development/SKILL.md) | HDA、脚本、界面、回调和交付 |
| [参数界面](skills/houdini-parameter-ui/SKILL.md) | 共享控制与参数绑定 |
| [网络交接](skills/houdini-network-handoff/SKILL.md) | 主动节点入口、跨领域分组说明与布局观察 |
| [Rig与动画](skills/houdini-rig-animation-workflow/SKILL.md) | 动画、骨架和运动 |
| [Solaris与Karma](skills/houdini-solaris-karma-workflow/SKILL.md) | 材质、USD与正式渲染 |
| [视频教程](skills/houdini-video-tutorial/SKILL.md) | 资料读取与教学工程 |
| [Trace分析](skills/houdini-trace-analysis/SKILL.md) | 查看实际请求、工具调用与失败 |
| [知识维护](skills/houdini-skill-governance/SKILL.md) | 显式维护领域资料 |

## 开发

长期入口：[文档索引](docs/README.md)、[系统架构](docs/architecture.md)、[维护规范](docs/development.md)。未完成验证见[交接](docs/handoff.md)。

```powershell
npm install
npm run build
npm run docs:check
npm test
```

开发和自动化测试使用自有 DSH_HOME、profile、缓存与浏览器资料；源码构建不等于用户已安装或进程已加载。验证按实际改动选择，执行内核使用必要的隔离 HOM 回归。隔离官方 Desktop、真实 H21/H22 和原生工具回执的机制检查不替代真实用户配置、厂商账号、教程识别和成品质量验收。

HOM在Houdini主线程串行执行，长任务通过队列提交。请求未知时查回原回执，错误和恢复状态如实返回；几何测量、图像观察与文件保存各自说明范围。
