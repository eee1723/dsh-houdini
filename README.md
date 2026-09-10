# dsh-houdini

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)插件，让agent驱动正在运行的SideFX Houdini会话。
5个houdini_*工具、61 个意图级动词、8个按需skills；Host通过HTTP调用Houdini主线程，不直接使用hou。

## 文档

[docs文档索引](docs/README.md)是长期设计入口：
[系统架构](docs/architecture.md)、
[工具词表](docs/tool-design.md)、
[执行与证据契约](docs/execution-contract.md)、
[节点操作卡](docs/node-operation-cards.md)、
[开发维护规范](docs/development.md)。

接续开发先看[当前交接](docs/handoff.md)：只保留待办、验证缺口及下一步，完成即移除，不作历史日志。

docs保存当前设计、实现和维护方法；当前交接是唯一滚动待办例外，不保存迭代日记或测试流水。节点卡由JSON同源生成，
其他设计随代码原位更新；构建产物和源码说明都不能证明live版本已加载。

## 快速开始

正式用户：从[正式发行页](https://github.com/eee1723/dsh-houdini/releases/latest)下载offline.zip，解压后双击[Install.cmd](Install.cmd)，重开Houdini即可进入独立安装管理器。
完整包包含固定Node/DSH/依赖，无需手动build；轻量安装器或源码ZIP先装管理器，再获取正式包。
只发现明确发布的稳定Release，不跟随main；安装、修复、旁路更新和回退见[setup](docs/setup.md)。尚无正式Release或发行公钥时不会安装未发布源码。
下面的命令仅用于显式源码开发：

```powershell
npm install
npm run build
python houdini/install.py
```

完整重开Houdini后，点击 **DSH-Houdini → Open Workspace**：已保存 `.hip` 的父目录成为 DSH workspace；
切换 HIP 后再次点击即可切换任务边界。未保存场景使用仓库外中立 scratch，不会扩大到 `dsh-houdini`。
在Web UI新建「Houdini模式」会话，先请求houdini_query列出/obj节点。

加载更新的Host/Bridge/helper/preset，用Version & Diagnostics → Advanced diagnostics →
**Repair and restart runtime**；菜单、package或WebView变更需完整重开Houdini。
活动任务不会被正常repair强制中断；失配时不要绕过Host/Bridge握手。

## 工具与工作流

| 工具 | 作用 |
|---|---|
| houdini_query | 只读观察 |
| houdini_exec | 场景修改与作者验证 |
| houdini_job_submit | 长操作异步排队 |
| houdini_job_status | 状态、等待和结果 |
| houdini_job_cancel | 协作式取消 |

修改使用动词，未知签名先verb_help，关键节点设置先node_info；所有结果都应消费失败和范围证据。
例如OBJ装配使用set_object_parent(child, parent, reason=...)，而不是generic connect。

| Skill | 职责 |
|---|---|
| [houdini-sop-workflow](skills/houdini-sop-workflow/SKILL.md) | SOP/VEX、模块、细化、接口与参数验证；SOP HDA内部几何输出 |
| [houdini-tool-development](skills/houdini-tool-development/SKILL.md) | HDA封装/代码/回调、脚本与依赖交付、Shelf/快捷键及工具入口开发 |
| [houdini-parameter-ui](skills/houdini-parameter-ui/SKILL.md) | 跨建模/场景总控/HDA的控制设计、共享布局组件、载体选择与参数绑定 |
| [houdini-rig-animation-workflow](skills/houdini-rig-animation-workflow/SKILL.md) | Channel、KineFX/rig、实际运动交付 |
| [houdini-solaris-karma-workflow](skills/houdini-solaris-karma-workflow/SKILL.md) | USD、MaterialX、Karma正式渲染 |
| [houdini-trace-analysis](skills/houdini-trace-analysis/SKILL.md) | 确定性trace取证、指标与审计 |
| [houdini-skill-governance](skills/houdini-skill-governance/SKILL.md) | 领域知识的来源、版本和发布边界 |
| [houdini-video-tutorial](skills/houdini-video-tutorial/SKILL.md) | 本地视频的云转录、画面核对与复现依据；不自动搭建工程或沉淀知识 |

## 配置与支持组合

配置源为[src/index.ts](src/index.ts)：bridgeUrl默认http://127.0.0.1:8765，
requestTimeoutMs默认120000，automaticContext默认true。
兼容DSH由[dsh-runtime-compatibility.json](dsh-runtime-compatibility.json)精确选择，
profile依赖由[dsh-profile.requirements.json](dsh-profile.requirements.json)管理。
升级遵循[兼容设计](docs/dsh-update-compatibility.md)，不把npm latest自动当serving版本。

图片直接作为原生多模态工具结果返回；不安装额外识图工具，不向工作区media目录复制文件。
文件存在、像素检查、图片展示都不等于语义识图成功，当前模型未实际查看图像时报告视觉未验证。

## 开发与验证

```powershell
npm run docs:generate
npm run docs:check
npm test
npm pack --dry-run
```

npm test运行构建和27 个 Node 确定性测试文件；文件数由文档一致性门禁核对。
HOM回归用目标版本的隔离hython跑tools/tests/*.test.py；稳定命令与发布门见[开发维护](docs/development.md)。
不手改lib或client生成区，不将测试运行结果追加到docs。

## 安全与能力边界

- Bridge仅绑定loopback，HOM主线程执行；job是排队异步，不是场景并行。AST不是恶意代码安全沙箱。
- ownership按session创建identity记录；foreign可读不等于可写，render服务不接受foreign豁免。
- 超时/取消不能强杀已执行的HOM，重试前回读状态。undo不恢复HIP/render/cache/HDA库等外部I/O。
- render_view持久服务应复用，不在任务收尾删除；正式交付相机与用户viewport各有边界。
- 几何/控制检查只能证明声明范围，不认证未测参数域、自交、制造强度或艺术质量。
- 源码、确定性回归、部署、新session曝光、真实任务质量分别验证；不互相冒充。

评测工具和信息隔离见[评测设计](docs/benchmark-design.md)。本插件不依赖其他Houdini MCP服务。
