# dsh-houdini

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)的Houdini插件。通过自然语言、参考资料和教程，在真实Houdini中完成高质量、可编辑、能持续修改的工程与工具。

DSH负责模型、会话和Agent循环；插件提供真实场景信息、批量操作、执行反馈、图像与文件。Houdini界面只显示 **Houdini 模式**，按任务读取领域知识。

## 工具

八个工具分别负责观察、执行、请求查回、历史资料、图像通道和长任务控制。每个工具为何存在、输入和返回详见[工具说明](docs/tools.md)，在界面的 **Houdini 工具** 页也可以查看。

Python能力目录见[动词词表](docs/tool-design.md)。陌生节点可用node_info，准确动词签名可用verb_help；对象父级使用set_object_parent。构造方法与操作顺序由模型根据任务选择。

## 启动

用户安装使用[正式发行包](https://github.com/eee1723/dsh-houdini/releases/latest)与[安装说明](docs/setup.md)。正式包、源码和当前已加载版本分别判断。

源码开发只用npm：

```powershell
npm install
npm run build
python houdini/install.py
```

完整重开Houdini，点击 **DSH-Houdini → Open Workspace**。已保存 `.hip` 的父目录成为DSH workspace；未命名场景使用仓库外scratch。切换HIP后再次打开工作区即可选择对应任务。

本项目锁定官方 **DSH 0.2.0-rc.2**，由[兼容清单](dsh-runtime-compatibility.json)决定启动/修复版本。唯一Houdini preset通过插件bundle声明式注册，源码在[presets/houdini](presets/houdini/)。

Host/Bridge/helper重载使用 **Version & Updates → 高级设置 → 运行诊断 → 修复并重启运行环境**；客户端、menu或package变化需要完整重开Houdini。构建通过不能证明已有进程加载了新代码。

## 领域资料

| 资料 | 用途 |
|---|---|
| [SOP](skills/houdini-sop-workflow/SKILL.md) | 程序化模型、局部修改和几何观察 |
| [COP](skills/houdini-cop-workflow/SKILL.md) | 程序化贴图和图层 |
| [工具开发](skills/houdini-tool-development/SKILL.md) | HDA、脚本、界面、回调和交付 |
| [参数界面](skills/houdini-parameter-ui/SKILL.md) | 共享控制与参数绑定 |
| [Rig与动画](skills/houdini-rig-animation-workflow/SKILL.md) | 动画、骨架和运动 |
| [Solaris与Karma](skills/houdini-solaris-karma-workflow/SKILL.md) | 材质、USD与正式渲染 |
| [视频教程](skills/houdini-video-tutorial/SKILL.md) | 资料读取与教学工程 |
| [Trace分析](skills/houdini-trace-analysis/SKILL.md) | 查看实际请求、工具调用与失败 |
| [知识维护](skills/houdini-skill-governance/SKILL.md) | 显式维护领域资料 |

## 开发

长期入口：[文档索引](docs/README.md)、[系统架构](docs/architecture.md)、[维护规范](docs/development.md)。未完成验证见[交接](docs/handoff.md)。

```powershell
npm run build
npm run docs:check
npm test
```

验证按实际改动选择；执行内核使用必要的隔离HOM回归。实际建模质量和运行耗时由真实任务测量，代码与测试数量不能代替成品结果。

HOM在Houdini主线程串行执行，长任务通过队列提交。请求未知时查回原回执，错误和恢复状态如实返回；几何测量、图像观察与文件保存各自说明范围。
