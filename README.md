# dsh-houdini

[English](README.en.md) · [发行与下载](https://github.com/eee1723/dsh-houdini/releases) · [使用指南](docs/setup.md)

在 DeepSeek Harness Desktop 里用自然语言操作真实的 Houdini 工程。得到的是可以继续改的节点网络、参数和数字资产，不是一张生成图。插件增加一个 **Houdini** 模式，不替换 Desktop，也不接管其他对话。

## 安装与更新

**Windows x64 · DSH 0.2.2-rc.5 · Houdini 21.0 / 22.0**。先在 Desktop 设置中查看宿主版本：仍使用 rc.3 时选插件 **0.1.12**，rc.1 选 **0.1.11**。[宿主下载与旧版对照](docs/setup.md)

1. 打开 Desktop → **插件 → 添加插件**，粘贴本版已发布的 GitHub 安装包地址，安装后点击 **立即启用**：

```text
https://github.com/eee1723/dsh-houdini/releases/download/v0.1.13/dsh-houdini-0.1.13.tgz
```

2. 也可先下载上述文件，再填写本地绝对路径。不要下载 Source code。npm 与大陆镜像的 0.1.13 尚未确认上架。

3. 新建 **Houdini 模式**对话，选择已打开的工程；也可在 Houdini 选择 **DSH-Houdini → Open Workspace** 回到同一对话。更新插件后先保存，再重开需要加载新组件的 Houdini 窗口。

## 试一个任务

> 在当前工程新建一套螺旋楼梯，把踏步数、楼梯宽度和总高放在一个控制节点上。改一次踏步数，检查首尾是否仍对齐，保留可编辑网络。

| 你想做什么 | 插件如何帮忙 |
|---|---|
| 建模和改稿 | 搭建原生网络、复用本地或已配置服务提供的部件，检查参数变化后的几何和接点。 |
| 排错和观察 | 在指定网络定位错误；查看模型预览、渲染结果和长任务的真实执行回执。 |
| 交付给其他人 | 整理节点入口、保存 HIP、封装 HDA；[交给 Unreal](skills/houdini-unreal-handoff/SKILL.md) 时提取依赖、检查迁移后的输出。 |
| 把教程变成工程 | 根据文字、视频或参考资料建立可调整的示例；转录、图像能力按需配置。 |

## 深入了解

[安装、更新及卸载](docs/setup.md) · [多窗口和现场恢复](docs/multi-instance.md) · [工具说明](docs/tools.md) · [领域技能](skills/) · [开发与测试](docs/development.md) · [问题反馈](https://github.com/eee1723/dsh-houdini/issues)
