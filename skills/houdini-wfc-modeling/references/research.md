# 研究依据与适用范围

这里只保留会影响表示、求解或编辑方式的依据。具体对象的配方、风格与尺寸在任务中确定。

## 原始算法与约束求解

**Gumin 的 WaveFunctionCollapse** 提供 overlapping 与 simple tiled 两种模型。`SimpleTiledModel.cs` 和示例 XML 展示显式邻接、对称变体、权重和子集。`Model.cs` 展示候选传播与位置选择，`Program.cs` 在单次失败后尝试重跑。Circuit 等非 Wang 示例说明仅靠边标签匹配可能表达不了所需组合，需保留成对例外。仓库中的核心示例实现为二维，三维建模需相应的占用和方向表达。 [原始仓库与代码](https://github.com/mxgmn/WaveFunctionCollapse)

**Merrell 与 Manocha 的 Constraint-Based Model Synthesis（2009）** 用局部几何邻域和约束生成三维模型，讨论尺寸、关联及连通等控制。可借鉴把尺度和结构要求显式加入可行性模型，并用简化表示驱动复杂几何替换。其局部状态基于平面交汇处的几何描述，接入预制模块时需要设计自己的占用和接口表示。论文允许的几何适配也需按任务的固定规格要求重新判断。 [论文](https://gamma-web.iacs.umd.edu/papers/documents/articles/2009/merrell09.pdf)

**Karth 与 Smith 的 WaveFunctionCollapse is Constraint Solving in the Wild（2017）** 将 WFC 解释为有限域约束搜索，并以 ASP 代理实现分析传播、启发式和回溯。在其加入全局模式出现条件的图像实验中，局部回溯改善了整轮重启难解的情况。工程上据此区分约束模型与搜索策略，出现全局条件时实测回溯和更强剪枝的收益。实验规模和耗时不直接预测 Houdini 三维任务。 [论文](https://adamsmith.as/papers/wfc_is_constraint_solving_in_the_wild.pdf)

## 模块化、编辑与分层

**Marian Kleineberg 的三维 WFC** 演示模块原型、面接口、方向变体与例外邻接。可借鉴从模块数据生成兼容表和将源件替换传递到成品。无限生成的后续设计有专门的边界与离线准备条件，有限生成器按需要采用。 [三维原型](https://marian42.de/article/wfc/) · [无限生成的后续设计](https://marian42.de/article/infinite-wfc/)

**Tessera 与 DeBroglie** 提供预放模块、区域筛选、多格占用及路径和数量约束的实践。可借鉴多格内部一致性、用户锁定与全局约束的分工。涉及不规则网格的几何形变时，按任务的刚体或可形变资产要求选择。局部编辑须维护与固定区域的边界条件。 [Tessera 论文](https://www.boristhebrave.com/permanent/21/08/Tessera_A_Practical_System_for_WFC.pdf) · [DeBroglie 约束](https://boristhebrave.github.io/DeBroglie/articles/constraints.html) · [Editable WFC](https://www.boristhebrave.com/2022/04/25/editable-wfc/)

**Hierarchical Semantic WFC（2023）** 将抽象区域与具体模块选择分层，提供用户从粗到细参与生成的方法。采用分层时应声明各层负责的选择，保留低层失败反馈到高层的路径，实际几何仍需装配验证。 [作者论文](https://research.tudelft.nl/files/151542125/3582437.3587209.pdf)

## Houdini 与评估

**SideFX WFC Dungeon Generator** 展示二维求解到资产实例的工作流。**Project Titan Building Tool** 展示体块驱动的模块装配。可参考输入、实例源和输出的编辑组织，再按任务补充实际需要的三维或全局约束。 [WFC Dungeon](https://www.sidefx.com/tutorials/wfc-dungeon-generator/) · [Project Titan](https://www.sidefx.com/tutorials/project-titan-building-tool/)

**Expressive Range Analysis** 用输出特征的分布检查生成器的偏向和表达范围。选择与用户预期相关的结构指标，结合图像观察近似重复、缺失类型及失败分布。具体统计门槛由任务决定。 [Smith 与 Whitehead 论文](https://www.pcgworkshop.com/archive/smith2010analyzing.pdf)

以上工程取舍是对来源的归纳。方法的适用性、当前节点版本和效果需要在实际输入与消费者上验证。
