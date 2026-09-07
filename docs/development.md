# 开发与文档维护规范

本页是长期维护规则，不是开发日志。入口见[文档索引](README.md)和[系统架构](architecture.md)。

## 1. 单一事实源

| 内容 | 修改位置 | 派生/验证 |
|---|---|---|
| 工具签名、目录、执行版本 | [tool-design.md](tool-design.md)，实现同步helpers/Bridge | gen-client-catalog生成client目录与Host契约；verb-contract验证58 个目录入口 |
| 节点知识与决策 | [node-operation-contracts.json](../houdini/node-operation-contracts.json) | gen-node-card-docs生成[节点卡文档](node-operation-cards.md)，HOM验证参数与几何语义 |
| 配置、支持组合 | [src/index.ts](../src/index.ts)、两份runtime/profile JSON | 安装/兼容文档只解释机制，清单不手抄多份 |
| 权限与证据保证 | 实际guard/事务实现 | [执行契约](execution-contract.md)与失败/恢复反例 |
| 领域方法 | [skills](../skills/)的对应SKILL/reference | docs链接原文，不复制recipe |
| Agent规则 | [AGENTS.md](../AGENTS.md) | 只保留命令、边界和知识路由，不写阶段履历 |

## 2. 构建与生成

```powershell
npm install
npm run docs:generate
npm run docs:check
npm test
npm pack --dry-run
```

只用npm，不用pnpm。build自动生成节点卡文档与Host/client词表，再运行tsc；不要手改lib或生成区。
docs:check是只读漂移/索引/链接/模块覆盖检查，不偷偷修正文档；CI应在build前运行，防止生成步骤掩盖漂移。
node-operation-cards.md逐项映射JSON，schema新增字段须同时更新加载器、生成器和测试。
关键参数名对应runtime模板，不能从手册猜数字菜单值或把一次读取的默认值固化为全版本事实。

## 3. 代码变更的文档责任

新增或改变长期维护能力时，修改对应现役设计段落、源码索引和适用边界；不追加版本日志。
新生产模块须在architecture代码地图可找到；新文档须进入docs索引，并解释它的唯一职责。
变更词表签名/执行语义需同步Bridge版本和生成产物；仅整理文档不虚增执行版本。
节点卡变化要运行生成一致性和目标Houdini的参数/正反例测试。

单次运行的耗时、尝试、失败截图、session ID、token、临时目标等只放会话/CI或tools/out等非发布产物。
测试代码、稳定验证方法、已知未支持边界应保留；已完成计划、退役原型说明和历史审计不放docs。
停用功能先迁移有效约束到现役文档，再清理文件及调用者，不建立docs/archive。
不因为文档声称已修复就删除验证；机器内存和跨项目材料不属于默认同步范围。

## 4. 回归与发布

npm test发现并运行tools/tests下全部Node测试。涉及HOM时在隔离hython、隔离偏好目录中运行
tools/tests/*.test.py，目标版本覆盖H21/H22；不要连接用户live会话或load/save源HIP。
至少覆盖Raw Gate、node ownership、caught-failure、tab-create-failure、object-parenting、
scene/network/render contract；节点知识、构图、控制或review变更再跑相应回归。

```powershell
$env:HOUDINI_PATH='&'
$env:HOUDINI_NO_ENV_FILE='1'
# 设置到仓库外隔离偏好目录；路径按本机安装调整。
$env:HOUDINI_USER_PREF_DIR='C:/Temp/dsh-tests/houdini__HVER__'
& 'C:/Program Files/Side Effects Software/Houdini 21.0.440/bin/hython.exe' tools/tests/dsh-node-knowledge.test.py
node skills/houdini-skill-governance/scripts/audit-houdini-skills.mjs --strict
```

Python验证脚本在Windows使用UTF-8；若hython缺skill校验依赖，使用已有系统Python，不污染Houdini环境。
不同实例或renderer的正确性必须由相应行为检查证明，不能拿数值/HOM替身测试当成GUI/语义验收。
构建后检查npm包资源、git diff --check及知识引用；测试流水不回填本页。
baseline中的surface hash反映代码快照；重封时保留runtimeVerification真实状态，不把它改成已部署。
冻结protocol、matrix、holdout不随普通开发改写，参见[评测设计](benchmark-design.md)。

## 5. 领域与真实运行验收

Rig的可执行入口是[rig skill](../skills/houdini-rig-animation-workflow/SKILL.md)、
[rig参考](../skills/houdini-rig-animation-workflow/references/rig-animation-patterns.md)及
[隔离KineFX回归](../tools/tests/dsh-kinefx-fk.test.py)，不依赖删除的一次性probe。
Render真实像素使用[OpenGL smoke](../tools/camera-opengl-smoke.py)或
[Karma smoke](../tools/camera-karma-smoke.py)，需区分文件/像素与语义识图。
新技能/提示只有新session能验证曝光；可复现功能测试与未见建模任务的质量/效率证据分开。

Host/Bridge/helper更新使用诊断中的Repair and restart runtime；package/menu/WebView变更完整重开Houdini。
只有实际进程版本、工具握手与目标用户路径验证后才能声明live已加载。
源码检查不授权重启服务；安装与操作流程见[setup](setup.md)，升级兼容门见[兼容设计](dsh-update-compatibility.md)。
