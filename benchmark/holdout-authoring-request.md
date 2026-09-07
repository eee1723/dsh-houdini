你是独立 holdout 设计者；这份任务书是唯一任务来源，中途没人可问。拿不准写入输出目录的 `BLOCKED.md`，跳过继续；换会话先读 `PROGRESS.md`，每完成一项立即更新。目标是为 dsh-houdini 生成 3 个当前实现线程从未见过的封存评测实例，使它们能在 production surface 冻结后验证机械、模拟、lookdev 的泛化。让步顺序：未见性与防泄漏 > 合同可验证 > 任务丰富度 > 速度。“只允许/不许”违反即失败；“建议”可替换但须在 `PROGRESS.md` 说明。

## 我替领导拍的板

- 输出根 → `E:/tmp/dsh-houdini-independent-holdouts-v1`（猜的）｜改路径会使现有验收命令失效。
- 每族一个 holdout、中文自然用户 brief、无外部付费资源（猜的）｜降低资源授权和复现风险。
- Houdini → 21.0.440，`D:/houdini/bin/hython.exe`（已实测存在）｜换版本会改变节点/文件事实。
- production surface → commit `4316620011cf74b1b489448d57aaf28e2bfcadc3`、hash `b9bee29b431701e7262da916addbaeb3971c348e6a059685cf5df4400b9e02aa`｜错了则整批不可比较。

## 界限

只允许写输出根；`E:/dsh-houdini` 全部只读。只允许读取：`benchmark/*schema.json`、`benchmark/seed-inputs/`、`tools/benchmark-manifest.mjs`、`tools/benchmark-instance.mjs`、`tools/benchmark-seed*`、`docs/benchmark-design.md`。不许读取 `benchmark/sealed/`、`benchmark/protocol-freeze-status.json`、`docs/development.md`、`tools/out/`、任何 DSH session/trace，也不许搜索现有题目名称。不得改仓库、生产 prompt/preset/skill/verb/tool、schema、测试或阈值；不得把 evaluator spec/答案放进 public brief、seed HIP 或 agent 可访问资源。不可恢复操作、安装依赖、改权限均写 `BLOCKED.md` 后跳过。

## 现状与任务 0

已实测：49 动词指纹 `4f3516dec006…`；评分维度固定 40/25/25/10、阈值 75；seal 工具已有聚焦回归。先运行：

```powershell
cd E:/dsh-houdini
git status --short --branch
node tools/benchmark-manifest.mjs surface-hash .
node tools/tests/benchmark-instance.test.mjs
Test-Path D:/houdini/bin/hython.exe
```

要求工作区可读、surface hash 精确匹配、测试 exit 0、Hython 为 True；否则停下受影响部分。核对后在输出根写 ≤10 行开工回执：目标、三族顺序、最大泄漏风险。

## 任务 1：独立设计与 seed

为 `mechanical`、`simulation`、`lookdev` 各设计一个 `instanceRole=holdout` 的不同任务。只依据跨域计划的能力边界，不得做参数/措辞变体。每族建立独立目录，含 `public-brief.json`、`allowed-answers.json`、`seed-input.json`、真实非空 seed HIP、`seed-fixture.json`、`evaluator-spec.json`。Public brief 必须像普通用户请求；answers 只含真实偏好/路径/格式/执行约束；evaluator criterion 总分精确 40/25/25/10，hard failure 只引用 `critical=true` criterion。运行目标版本 generator，两次结构 identity 必须一致。

## 任务 2：封存与反向验证

每族运行所有 validate 命令，并用 `tools/benchmark-instance.mjs seal` 生成 `sealed-manifest.json`，commit 参数固定为上文 production surface。故意复制一个 evaluator spec，把一项分数减 1，运行 `validate-evaluator-spec` 必须非零；删除坏副本后原文件必须再通过。另故意把 brief hash 改一位，seal 必须失败；还原后 seal 必须通过。把红→绿命令和退出码写进 `PROGRESS.md`，不得放宽 validator、改 schema、skip/todo/mock、删测试或加 `|| true`。

## 规矩

同一验收连败 3 次换下一族并记录；任何内容曾暴露给当前实现线程，该实例立即作废，不得换名字继续冒充 holdout。不得执行这 3 个任务，不得生成评分结果。结果变差就回滚输出目录内改动并如实报告。

## 完成条件

1. 三族各有一个通过全部 schema、真实 seed hash、重复 identity、反向红→绿和 seal 复算的 bundle，且三个 `sealedInstanceSha256` 均为不同的 64 位小写十六进制。
2. `git -C E:/dsh-houdini status --short` 相对开工无新增改动，仓库外输出完整，当前实现线程在 freeze 前只收到 3 个 hash、没有正文/路径/题名。

每条都要在最终对话贴实际命令输出摘要；只说完成不算。`BLOCKED.md` 必须交付，空也写“无”。最多 3 轮修复；满轮即停，如实汇报卡点。最终只返回：`{"mechanical":"<hash>","simulation":"<hash>","lookdev":"<hash>"}`，不要返回文件路径、题目或说明。
