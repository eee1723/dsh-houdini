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
| Trace页面与同步语义 | [houdini-trace-design.md](houdini-trace-design.md)，展示在client.js | 内容复用目录/注册表/请求快照；当前源码、已加载能力和历史请求分开，不手抄提示词与技能正文 |
| Agent规则 | [AGENTS.md](../AGENTS.md) | 只保留命令、边界和知识路由，不写阶段履历 |
| 当前开发交接 | [handoff.md](handoff.md) | 唯一滚动入口；docs:check检查结构/体量，开发者按移除条件核销 |

## 2. 构建与生成

```powershell
npm install
npm run docs:generate
npm run docs:check
npm test
npm pack --dry-run
```

只用npm，不用pnpm。build自动生成节点卡文档、Host/client词表和Trace组件/来源清单，再运行tsc；不要手改lib或生成区。
Trace手写界面在client/trace-view.js与trace-view.css；guidance、persona、注册技能及资源从来源生成，
不在展示代码复制正文。生成漂移由trace-view回归与gen-trace-client --check验证。
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

### 交接文档生命周期

`docs/handoff.md`是过程信息进入docs的唯一有限例外，纳入Git与文档索引；跨电脑仍须提交/推送后拉取，
存在于工作区不等于已同步。只保留下一次接续必须知道的未完成动作、阻塞和验证缺口，不记已完成履历。

- 固定一份文件，原位更新“核对日期”；最多8个活动条目、120行、8000字符。超限先合并同一问题和删除已核销项，
  不另开按日期/批次命名的交接文档，也不把有效阻塞丢进不可同步的临时文件。
- 每项包含稳定H编号、状态（待修复/待验证/待决策）、现状、下一步、移除条件和仓库内源码/验证入口。
  状态只描述尚欠动作；仅缺live或模型验证就写具体缺口，不继续列已经实现的修复。
- 每次完成实现与所需验证、明确取消或替代该项时，在同一变更中删除整项；不要改成“已完成”继续留着。
  实现已完成但验收未完成时，只留下验收动作；稳定设计/边界先并回对应现役文档，历史由Git保留。
- 每次接续与收尾核对全表，不仅追加新条目；无活动项时保留标题、核对日期和“当前无待交接事项”。
- 不复制完整问题历史、测试计数/日志、私有trace、HIP内容或机器密钥。入口必须能随仓库找到；本机证据可以辅助，
  不能作为理解或复现该项的唯一材料。长期产品方向留在development-directions，不逐条复制进交接。

`docs:check`只读检查体量、字段、状态、唯一编号和链接，并拒绝已完成勾选项及额外交接副本；
它不能从代码自动判断业务完成，删项仍须实际核对移除条件。清理交接条目不等于授权删除临时实验、HIP或工作树。

## 4. 回归与发布

正式发布必须经过[发行单元与发布门](dsh-update-compatibility.md#正式发行单元与发布门)：main push不是发布，tag/Draft也不使更新对普通用户可见。
用户发行包与开发checkout分离；只在发布端构建正式包，Node/DSH/完整依赖树绑定精确组合。安装实现见[setup](setup.md)，尚欠实际验收见[交接](handoff.md)。

部署策略离线回归：[Release边界](../tools/tests/dsh-release-policy.test.py)、[安装/启动精确选择](../tools/tests/dsh-install-runtime.test.py)、
[兼容清单](../tools/tests/dsh-runtime-compat.test.py)可在Python 3.11+运行，无网络/安装/用户目录写入；
[管理器](../tools/tests/dsh-manager-update.test.py)、[启动预检](../tools/tests/dsh-launcher-preflight.test.py)及[profile同步](../tools/tests/dsh-profile-sync.test.py)
用下述隔离H21/H22 hython环境分别执行。各测试使用临时fixture；这组检查不代替真实Qt页面、干净机器安装或已加载身份验收。

[表达式分层诊断](../tools/tests/dsh-expression-diagnostics.test.py)在H21/H22验证合法0、原生写入失败、
错误函数/语法/Python求值、缺失引用warning、无关cook错误和参数/批次动画恢复；求值成功
但空输出的反例仍由verify_network拒绝，不由set_parm冒充几何验收。

控制恢复用[dsh-control-state-restoration](../tools/tests/dsh-control-state-restoration.test.py)验证几何相同但
参数/动画错误的反例、恢复cook期间变值、OBJ主控同批设值/追加folder与后续独立undo；请求恢复用[dsh-request-recovery](../tools/tests/dsh-request-recovery.test.py)
及[Host回包恢复](../tools/tests/request-recovery.test.mjs)覆盖队列、运行中、断联、坏JSON、超时、重复身份、
结果过期、runtime变更、jobs提交回包丢失、回执索引、队列取消和不重复修改。查回jobId只证明提交，
迟到提交回执不复活已结束job；迟到running/unknown或Bridge结果过期不抹除Host已收到的完成回执。
AbortSignal取消后的查回验证HTTP客户端，不能代替实际Host停止按钮、丢弃结果与新session用户路径验收。

npm test发现并运行tools/tests下全部Node测试。涉及HOM时在隔离hython、隔离偏好目录中运行
tools/tests/*.test.py，目标版本覆盖H21/H22；不要连接用户live会话或load/save源HIP。
至少覆盖Raw Gate、node ownership、caught-failure、tab-create-failure、object-parenting、
scene/network/render contract；节点知识、构图、控制变更再跑相应回归。

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
参数默认值更新用[dsh-spare-defaults](../tools/tests/dsh-spare-defaults.test.py)检查当前值/动画、ownership和失败恢复；
编译后新增参数用[dsh-spare-dependency](../tools/tests/dsh-spare-dependency.test.py)检查源码刷新、动画保持和失败恢复。
局部源码更新用[dsh-parameter-patch](../tools/tests/dsh-parameter-patch.test.py)检查版本/锚点零写入、
整批恢复与真实cook失败；[dsh-module-boundaries](../tools/tests/dsh-module-boundaries.test.py)
区分独立提交保留、同批原子回滚及签名绑定/内部实现错误。
执行观察用[dsh-execution-observation](../tools/tests/dsh-execution-observation.test.py)检查实际连线/表达式
依赖、无额外cook、删除和同调用检查顺序；[execution-state](../tools/tests/execution-state.test.mjs)验证
事件乱序/replay、runtime更换、未返回修改和job状态不复活旧证据。两者不替代GUI外部修改观察。
结果分层用[result-details](../tools/tests/result-details.test.mjs)验证canonical可读回、分页/防篡改、
保存失败不触发修改重试，以及默认文本与完整审计各自的统计口径。
任务来源用[task-sources](../tools/tests/task-sources.test.mjs)验证用户/注入来源隔离、澄清失败与replay、
原文分页回读、session隔离及超预算；[scene-context](../tools/tests/scene-context.test.mjs)覆盖首轮claim、
按需指代、普通查询零追加、独立提醒去重/解除、surface替换恢复、上下文抑制与模板转义，
并用DSH Session实际deriveMessages检查消息不累积；不以这些测试替代live模型输入及复杂任务规划验收。
控制摘要用[dsh-quality-contracts](../tools/tests/dsh-quality-contracts.test.py)
覆盖基准失败及Bridge证据，[dsh-interface-evidence](../tools/tests/dsh-interface-evidence.test.py)
保留真实实例、合法间隙和顶点距离不能证明无碰撞的反例。
恢复指纹用[dsh-geometry-fingerprint](../tools/tests/dsh-geometry-fingerprint.test.py)区分组目录排列
和真实成员/ordered顺序/属性变化；[dsh-module-preflight](../tools/tests/dsh-module-preflight.test.py)
覆盖零写入拒绝、同批其他修改及创建后失败，防止恢复状态被错误降级。
module-preflight同时覆盖circle.divs、tube.height/cols、polywire.radius/div的标量、表达式及实际回读，
并保留单值列表拒绝、真tuple、非有限值和动画恢复反例；不能只验证单独set_parm而漏掉模块预检。
quality-contracts用“局部变化但整体bbox不变”和“面积响应通过但部件脱离”区分测量与关系覆盖；
[modeling-identity](../tools/tests/dsh-modeling-identity.test.py)用外包络缩放正确但内部部件额外位移的反例，
验证stable-ID max_transform_error会拒绝错误均匀缩放，而真实均匀变换可通过。
聚焦模块的执行基础用[module-integration](../tools/tests/dsh-module-integration.test.py)验证：局部输出健康但下游
漏件、实例变换造成脱离、独立模块失败保留旧提交、共享控制在实际装配输出上的测试和恢复。
这只是HOM机制回归；SOP skill的顺序聚焦仍是工作流候选，需同模型/版本/预算的自然任务对照，
另含简单编辑、单部件、相邻领域和接口未定的反例，不以固定脚本通过证明LLM采用或视觉质量。
构建后检查npm包资源、git diff --check及知识引用；测试流水不回填本页。
baseline中的surface hash反映代码快照；重封时保留runtimeVerification真实状态，不把它改成已部署。
冻结protocol、matrix、holdout不随普通开发改写，参见[评测设计](benchmark-design.md)。
冻结protocol-manifest的字节摘要以已提交LF内容为准，由.gitattributes固定检出格式；不得为Windows换行转换改动协议或放宽摘要校验。

### 发行操作与信任配置

运行依赖唯一锁在[deployment/package-lock.json](../deployment/package-lock.json)，根DSH版本与兼容preferred必须一致；
[runtime.json](../deployment/runtime.json)固定Windows x64、Node版本与官方分发摘要。发布前核对依赖许可证与包内third-party-notices.json；不省略上游LICENSE。
维护者可用 `node tools/release-sign.mjs import-lock 路径`导入已验证的完整npm锁；生成后必须用npm ci和真实包smoke资格验证，不能只锁根包。

受信发布身份以[公钥清单](../installer/release-trust.json)为准，日常发布复用对应私钥；不重复生成同一key ID，也不提交私钥。
仅首次建立身份或轮换时使用keygen，并为新身份选用新路径与新key ID：

```powershell
node tools/release-sign.mjs keygen D:/Secure/dsh-release-next.pem D:/Secure/dsh-public-next.json release-key-next
# 仅新身份/轮换时执行上行；审核新公钥后合入installer/release-trust.json，不覆盖仍受信的旧key。
# 以下使用已配置的release-key-1发布，私钥路径换成本机安全存放位置：
python tools/build-release.py --unsigned --output tools/out/release --key-id release-key-1
# 在独立签名环境、同一已审核tag checkout中放入上一步产物：
$env:DSH_RELEASE_SIGNING_KEY='D:/Secure/dsh-release.pem'
python tools/finalize-release.py --directory tools/out/release --key-id release-key-1
```

正式构建要求干净checkout、匹配package版本的已存在vMAJOR.MINOR.PATCH标签，以及已提交的公钥。
构建器生成unsigned payload与release.json，独立finalize才签名并生成release.sig.json、轻量安装器和offline.zip；两者均不发布GitHub Release。
当前受信key ID为release-key-1；实际私钥不随源码分发，维护者须单独安全备份并配置受保护签名环境。缺少公钥或未知key仍fail-closed。
显式 `--candidate --trust 临时公钥文件`可对未提交源码做隔离测试；candidate签名包不被普通面板接受，也不可冒充正式验收。

```powershell
python tools/run-deployment-tests.py
python tools/run-deployment-tests.py --hython 'C:/Program Files/Side Effects Software/Houdini 21.0.440/bin/hython.exe' --hython 'C:/Program Files/Side Effects Software/Houdini 22.0.368/bin/hython.exe'
python tools/tests/dsh-deployment-e2e.test.py --bundle tools/out/release --trust installer/release-trust.json --hython 'C:/Program Files/Side Effects Software/Houdini 21.0.440/bin/hython.exe' --hython 'C:/Program Files/Side Effects Software/Houdini 22.0.368/bin/hython.exe'
```

离线回归覆盖签名拒绝、路径穿越/别名/重复/特殊文件、取消、磁盘/原子写入失败、进程互斥、数据快照/回退、引导损坏修复和真实Qt控件。
e2e从真实签名包安装到隔离目录，使用包内Node启动DSH并验证profile、全局/会话端口、401/200鉴权RPC、自有进程回收；
指定hython后还在实际安装目录执行Node→HTTP→Houdini主线程只读调用及合同握手，不调用收费模型、不访问用户HIP。
测试产物和截图留在临时目录或tools/out；发行包中不携带测试私钥、会话或测试基准。

真实GUI发行验收使用[GUI测试](../tools/tests/dsh-gui-release.test.py)：

```powershell
python tools/tests/dsh-gui-release.test.py --bundle tools/out/release --trust installer/release-trust.json --houdini 'C:/Program Files/Side Effects Software/Houdini 21.0.440/bin/houdini.exe' --houdini 'C:/Program Files/Side Effects Software/Houdini 22.0.368/bin/houdini.exe'
```

测试只新开自有GUI进程、临时偏好和测试HIP，清除模型凭据及系统Node/Git的PATH；覆盖进程启动钩子、Open Workspace、Houdini模式会话、
真实Qt WebView鉴权、Node→GUI主线程只读调用、重复打开不重启/不新增会话和正常退出码。通过不代表另一台物理机器或模型质量已验证。
退出测试必须走Houdini主窗口关闭路径，不能从PySide timer抛SystemExit后把崩溃的进程当成功；截图/通过标记也不能代替退出码。
GUI按厂商快捷方式以对应Houdini安装bin为启动目录，HIP与DSH工作区另用临时目录；H22 Qt子进程的DLL查找不能用任意cwd假设替代，不通过禁用沙箱掩盖环境错误。

[普通CI](../.github/workflows/ci.yml)在push/PR上只做源码检查；[发行流程](../.github/workflows/release.yml)仅显式workflow_dispatch，
使用Windows/Houdini自托管runner、仓库变量H21_HYTHON/H22_HYTHON/RELEASE_KEY_ID及受保护release环境中的RELEASE_PRIVATE_PEM。
assemble、sign、verify-signed、draft为分离job：构建/验收只在无签名密钥的自托管环境运行，签名在干净托管runner且不执行payload/npm，草稿上传也不执行payload。
Actions引用固定commit，签名任务只接受当前审核tag的版本/commit/Node/DSH身份。通过后只上传Draft；启用仓库immutable Releases并完成真实Houdini用户路径后，维护者才明确发布。
PR不得在持有许可证的自托管runner上任意执行；不能让依赖安装脚本或安装客户端接触发布密钥。
首发也可由维护者手动执行同样的构建、独立签名、双版本CLI/GUI验收，再上传Draft并验证下载字节；不要求先部署常驻runner。
手动路径同样先准备全部资产、启用immutable Releases，再明确发布；Git凭据仅用于官方仓库API，私钥不进入构建环境或上传到Git。

## 5. 领域与真实运行验收

视频解析离线回归使用 `python tools/tests/video-tutorial.test.py`（宿主 Python 3.11+，不需要 HOM、
密钥或网络），覆盖授权、分片覆盖、续跑、失败/未知请求、证据损坏和抽帧边界。
真实媒体/云验证使用[video skill](../skills/houdini-video-tutorial/SKILL.md)的准备与小片段路径，
在仓库外运行，云提交需当前用户授权；FFmpeg、服务响应、语义识图和教程复现分别验收。
不得把默认离线回归改为联网上传教程，测试数据与转录不进入包。

Rig的可执行入口是[rig skill](../skills/houdini-rig-animation-workflow/SKILL.md)、
[rig参考](../skills/houdini-rig-animation-workflow/references/rig-animation-patterns.md)及
[隔离KineFX回归](../tools/tests/dsh-kinefx-fk.test.py)，不依赖删除的一次性probe。
Render真实像素使用[OpenGL smoke](../tools/camera-opengl-smoke.py)或
[Karma smoke](../tools/camera-karma-smoke.py)，需区分文件/像素与语义识图。
新技能/提示只有新session能验证曝光；可复现功能测试与未见建模任务的质量/效率证据分开。

Host/Bridge/helper更新使用诊断中的Repair and restart runtime；package/menu/WebView变更完整重开Houdini。
只有实际进程版本、工具握手与目标用户路径验证后才能声明live已加载。
源码检查不授权重启服务；安装与操作流程见[setup](setup.md)，升级兼容门见[兼容设计](dsh-update-compatibility.md)。
