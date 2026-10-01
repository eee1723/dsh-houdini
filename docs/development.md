# 开发与文档维护规范

入口见[文档索引](README.md)和[系统架构](architecture.md)。这里维护开发方法、生成规则和验证入口；尚欠动作只放[交接](handoff.md)。

## 设计原则

系统负责让模型获得准确信息、充分操作能力、真实执行反馈、可观察结果和清楚的错误。模型负责理解需求、选择方法、组织步骤和判断效果。领域知识按任务读取，执行接口只落实平台与操作合同。

已完成的功能、工具数量、历史测试和目录结构都可以调整。新增检查应解决实际接口条件或已观察到的失败；模型的一次遗漏或方法选择错误不应成为永久准入门槛。删除策略时同步删除只证明该策略的断言。

继续使用 DSH 的会话、模型、通用 Agent 循环、上下文组合、压缩和原生工具能力。插件维护 Houdini 适配；不要在插件重建一套通用 Agent 状态机或提示词历史。

## 单一维护源

| 内容 | 维护位置 | 派生或验证入口 |
|---|---|---|
| Host 工具职责与参数 | [tool-catalog](../src/tool-catalog.ts)、[tools](../src/tools.ts) | gen-tool-docs 生成 docs 工具表；工具注册与前端共用目录 |
| Houdini 动词签名、执行版本 | [工具设计](tool-design.md)，实现同步 helpers/Bridge | gen-client-catalog 生成 Host 契约和客户端目录；verb-contract 回归 |
| 动词按需结构与例子 | [verb-operation-contracts.json](../houdini/verb-operation-contracts.json)，签名仍来自运行函数 | gen-verb-contract-docs生成[结构合同](verb-contracts.md)，verb_help按需返回；说明不参与执行校验 |
| 节点操作知识 | [node-operation-contracts.json](../houdini/node-operation-contracts.json) | gen-node-card-docs 生成[节点卡](node-operation-cards.md)；node-knowledge 验实际参数和几何 |
| DSH 组合与角色 | 精确 DSH 标准组合及 [Houdini persona](../presets/houdini/persona.md) | [gen-agent-presets](../tools/gen-agent-presets.mjs)生成唯一 Houdini patch |
| 运行版本与安装组合 | [兼容清单](../dsh-runtime-compatibility.json)、[runtime](../deployment/runtime.json)、[部署锁文件](../deployment/package-lock.json) | 安装、启动、修复共用 preferred 精确组合 |
| 执行与恢复事实 | Houdini 实际执行/结果模块 | [执行契约](execution-contract.md)；Host 和前端消费 Bridge 回执 |
| 领域方法 | 对应 [skills](../skills/) 的入口和 references | 按需知识；docs 链接原文，不重复 recipe |
| Trace 解析与展示 | [Trace 设计](houdini-trace-design.md)、client/ | 使用真实请求和工具记录；按需加载诊断 |
| 开发评测 | [评测原则](product-modeling-evaluation.md)、evaluation/、tools/ | 公开题面与评审答案隔离；生产面不读取评审材料 |

新增长期生产模块必须加入架构代码地图。新增文档必须加入索引，说明它的职责及源码、验证入口。

## 构建与生成

```powershell
npm install
npm run build
npm run docs:check
```

只用 npm。build 刷新节点卡、动词结构合同、唯一Houdini preset、工具文档、客户端目录和Trace资源指纹，再编译TypeScript。`lib/`、生成区、`presets/houdini/cordis.patch.yml`不手改。

角色在 persona.md 维护；组合继承锁定版本 DSH 的标准插件，关闭其他内置 preset，只注册 Houdini。插件以 DSH 0.2 的 `bundle.patch` 装载配置：根级bare package `dsh-houdini`承载前端，preset内`dsh-houdini/agent`提供工具和原生context producer。DSH客户端模块图识别bare package，不能以preset scope或包子路径导入成功替代根客户端注册。客户端使用DSH的conversation/trajectory注册接口。

`docs:check` 只检查生成漂移、文档索引、模块覆盖和 Markdown 链接，不自动修文档。改动生成源后先 build，再检查最终一致性。

## 修改与验证

按用户目标和实际问题选择修改范围。工具描述只讲能力和真实调用条件；persona 讲角色和知识路由；领域工作方法只放 skill；操作合同落在执行实现。同一事实不要复制到多层提示词。

验证与改动相称：先构建并运行直接受影响的回归。检查通过且没有新改动或未解问题时，不继续扩大测试。基线收口运行一次现有 Node 套件与文档门；日常无需每次全跑。

```powershell
# 单个受影响的 Node 回归
node tools/tests/verb-contract.test.mjs
# 完整 Node 回归（内部包含 build）
npm test
```

涉及 Houdini 执行内核时，使用隔离 hython 覆盖必要核心边界：

| 能力 | 验证入口 |
|---|---|
| Raw Gate | [dsh-bridge-raw-gate](../tools/tests/dsh-bridge-raw-gate.test.py) |
| 节点归属 | [dsh-node-ownership](../tools/tests/dsh-node-ownership.test.py) |
| 捕获失败与回滚 | [dsh-bridge-caught-failure](../tools/tests/dsh-bridge-caught-failure.test.py) |
| 创建失败清理 | [dsh-tab-create-failure](../tools/tests/dsh-tab-create-failure.test.py) |
| OBJ 父级 | [dsh-object-parenting](../tools/tests/dsh-object-parenting.test.py) |
| 场景、网络、渲染 | [dsh-scene-network-render-contract](../tools/tests/dsh-scene-network-render-contract.test.py) |
| 批量 SOP 构建 | [dsh-module-preflight](../tools/tests/dsh-module-preflight.test.py) |

通过 [houdini_test_environment](../tools/houdini_test_environment.py) 创建临时偏好、空 package 环境和目标安装路径；启动目录使用指定安装的 bin。Python 通过 PYTHONPATH/测试入口兼容 H21/H22，不继承用户插件、Qt override 或模型凭据。隔离检查不连接 live，也不加载用户 HIP。

领域改动选对应回归，例如 [node-knowledge](../tools/tests/dsh-node-knowledge.test.py)、[参数与绑定](../tools/tests/dsh-parameter-controls.test.py)、[控制恢复](../tools/tests/dsh-control-state-restoration.test.py)、[COP](../tools/tests/dsh-cop-contracts.test.py)。不机械把每个领域套件加到普通模块整理上。

功能回归验证真实接口和错误；GUI 验证页面及运行加载；模型任务评测验证自然采用与结果质量。三者按实际需要运行，结果不能相互替代。视觉验收区分文件与图像传输、显示、模型实际识图。

跨层修改应验证消费方最终取得的状态，局部函数返回或静态配置存在不足以证明链路可用。入口/preset/client改动用精确DSH的实际模块图确认根前端与工具scope，再由真实页面确认内容视图和选中任务；工作区切换同时核对DSH store中的session、preset、cwd及workspace成员。入口可用空会话验启动，但Trace页需要普通有内容会话验收。相关入口为[Host组合](../tools/tests/dsh-host-smoke.test.py)和[真实页面导航](../tools/tests/dsh-client-navigation.mjs)。

执行结果应同时核对原生与Code Mode嵌套事件、取消/未知/过期回执及现场runtime身份；展示投影不得丢失无execution的真实回执。trace用真实当前版本日志校验可见内容、调用关联和解析缺口，不以旧fixture或旧session文件名证明新格式可读。用例保持针对已观察到的边界，旧策略删除后保留操作、权限和恢复检查，移除只证明策略存在的断言。

## 隔离开发工具

[hda-delivery-check.py](../tools/hda-delivery-check.py)在新 hython 中加载声明 HDA，按 manifest 创建实例、设置参数、调用按钮并检查几何/参数/错误。判据应能区分正确与错误结果，例如尺寸控制检查 bounds_size，而非只有点面数。

```powershell
python tools/hda-delivery-check.py --manifest path/to/tool-check.json --hython D:/houdini/bin/hython.exe --output path/to/report.json
```

[isolated-houdini-check.py](../tools/isolated-houdini-check.py)在新场景执行可信 builder，经 Bridge 完成明确 cook/cache/ROP 检查。manifest 指定 script 和 checks；`--trusted` 表示调用方授权执行该脚本。产物目录是仓库外的新目录，报告保留实际执行与文件证据。

```powershell
python tools/isolated-houdini-check.py --trusted --manifest path/to/check.json --hython D:/houdini/bin/hython.exe --output-dir D:/checks/run-001 --timeout 120 --memory-mb 4096
```

[isolated-worker.py](../tools/isolated-worker.py)及 [Houdini worker](../houdini/python3.11libs/dsh_isolated_worker.py)是开发评测使用的自有新进程入口；[worker 回归](../tools/tests/dsh-isolated-worker.test.py)验证明确 IPC、启动与回收。[delivery-audit](../tools/delivery-audit.mjs)只在开发评测中从会话回执读取交付事实。它们不进入模型的生产工具目录。

隔离工具通过自有进程句柄和 Windows Job 管理超时、取消及进程树内存。报告与退出状态都要读取；不把启动成功当作负载完成。任意 Python、回调、绝对路径文件和外部服务的副作用不属于场景恢复保证。

收费任务只在用户授权的模型与预算范围内运行 [run-modeling-trial.py](../tools/run-modeling-trial.py)。使用隔离任务目录、精确 DSH/Node/Houdini 和选定模型配置；自然试验不修改用户 live。评审答案不进入生产提示词或用于未见题调参。

## 分支与接续入口

接续或合并前先核对 `git status --short`、`git branch -a -vv`、`git worktree list` 和相关提交，再读目标分支 handoff。不同工作树的文档描述各自提交，main 不代表全部尚未合并的工作。

现役设计原位替换，不在 docs 追加版本叙事、试验流水或 session 记录。历史保留在 Git；日志、耗时、截图、评测 HIP 和本机材料放会话、CI、tools/out 或仓库外目录。

### 交接文档生命周期

handoff 是唯一滚动交接入口，只保留下一次接续仍需完成的动作、阻塞和验证缺口。每项写现状、下一步、移除条件和仓库内入口；完成后删除整项。保持一份文件，不按日期分叉，不把历史成功继续标为活动项。没有待办时写“当前无待交接事项”。

## 运行与发行

Host/Bridge/helper 变更通过 `Version & Diagnostics → Advanced diagnostics → Repair and restart runtime` 加载；package/menu/WebView 变更需要完整重开 Houdini。源码构建通过与 live 已加载分别判断；只有实际版本、握手和用户路径验证后才声明运行更新生效。重启用户进程和修改用户 HIP 需要当前授权。

### 发行操作与信任配置

正式安装流程见 [setup](setup.md)，支持组合及发行门见 [兼容设计](dsh-update-compatibility.md)。发行包使用 deployment 锁定的完整依赖树和 Node 分发摘要；普通源码 build 不等同用户发行安装。

正式发布前覆盖 H21/H22 必要执行和安装入口。发布使用 [build-release](../tools/build-release.py)、独立 [finalize-release](../tools/finalize-release.py)和受信公钥；私钥只存在于签名环境。main push、tag、Draft 均不构成正式发布。

```powershell
python tools/run-deployment-tests.py
python tools/run-deployment-tests.py --hython D:/houdini/bin/hython.exe --hython D:/Houdini22/bin/hython.exe
```

这是发行/部署回归入口，日常按改动选择检查。真实安装与 Qt 页面验收在新的自有进程和临时目录中执行；当前缺口只记 handoff，不在这里积累每次尝试。
