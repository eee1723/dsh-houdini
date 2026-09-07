# 评测基础设施设计

本页描述长期评测机制，不保存模型排行、批次成绩、运行日记或优化小目标。
协议实例与运行状态以benchmark中的schema/manifest为准；不因文档清理修改冻结protocol/matrix或解封holdout。

## 执行信息防火墙

执行agent只接收正常用户brief、预注册歧义回答及通用skill，不接收隐藏评分、参考答案或实例专用recipe。
用户brief和evaluator spec分别封存；答案、诊断和评分材料不得放进任务$HIP或生产guidance/preset/skill。
生产面标识扫描是最低门，换措辞写入同一答案仍是泄漏。泄漏会使受影响run无效。

区分发现实例、未见留出实例、相邻/跨域反例。发现实例用于定位问题，只有未见留出实例能支持相应
泛化主张；原题改善不能证明通用能力提升。改进冻结前不得接触用于验证该改进的留出内容。
修改brief、fixture、模型/provider、评分或预算就属于另一协议条件，不能混作同批A/B。
没有可复现失败或明确风险，不为评估而无条件重跑大矩阵。

## 文件与代码合同

| 实现 | 职责 |
|---|---|
| [benchmark schema](../benchmark/) | public brief、allowed answers、seed、run、protocol、evaluation的结构合同；不进入npm包 |
| [benchmark-manifest.mjs](../tools/benchmark-manifest.mjs) | canonical JSON/hash、schema不变量、$HIP路径、completed证据门 |
| [benchmark-instance.mjs](../tools/benchmark-instance.mjs) | 实例材料分离封存和权限边界 |
| [benchmark-seed.mjs](../tools/benchmark-seed.mjs)、[benchmark-seed-hython.py](../tools/benchmark-seed-hython.py) | 通用seed结构与隔离Houdini生成；无题目答案 |
| [benchmark-smoke.mjs](../tools/benchmark-smoke.mjs) | 独立run工作区/工作HIP与输入资格检查 |
| [benchmark-run.mjs](../tools/benchmark-run.mjs) | 操作侧运行记录与产物组织 |
| [benchmark-evaluator.mjs](../tools/benchmark-evaluator.mjs) | 独立评审输入/结果归一、criterion/image/deterministic引用校验 |

baseline分开封存agent surface与compatibility surface；具体集合由benchmark-manifest代码定义，
不能把重封hash当作runtime已加载。runtimeVerification不明时保持未确认，不自动翻成true。
具体题面、sealed材料和run产物属于隔离评测存储；docs只保存机制，tools/out不打包。

## 评审与能力主张

依次取得确定性事实、匿名盲视觉描述、目标核验；执行agent不是独立评委。
目标核验包含原始目标与最终报告原文，逐项pass/fail/unverified；报告自述不是ground truth。
图像角色、文件/像素/语义结果分开记录，评委与人工分歧不能用语言置信度覆盖。

评分以当前schema/validator为准：核心交付40、客观证据25、独立视觉25、诚实交付10；
硬失败优先。比较核心成功、自主发现与有效修复、虚假完成、用户纠正依赖和评审一致性，
同时记录工具失败/回滚/耗时/token，而不是目录广度或字段填写率。

新增规则要抽象到数据模型/操作意图，验证原失败、未见同族正例与不该触发的反例；
没有独立新证据只声明局部回归，不上升为通用能力结论。
[开发规范](development.md)维护验证入口，[兼容设计](dsh-update-compatibility.md)维护运行资格，
这里不重复日常工程测试清单。
