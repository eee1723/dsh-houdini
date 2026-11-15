---
name: dsh-wfc
description: 在Houdini中用simple-tiled Wave Function Collapse生成可编辑的模块化建筑、房间、街区、道路、管线、迷宫及自定义邻接图。将结构约束、四向旋转、外观变体和风格热替换分离，把Tripo/Meshy等完整高细节模块经原生packed实例接入SOP。用于需要确定邻接规则、边界、固定单元、数量或连通性的WFC任务；普通重复散布用houdini-sop-workflow；重叠模型WFC需另行选择overlap方法，本技能不处理。
---

# DSH WFC

把WFC用于“哪些结构模块可以相邻”，不要用它代替所有散布或程序化建模。让求解器处理少量结构状态，让AI／手工资产承担完整墙体、门窗、转角和屋顶等外观细节；不要把每片瓦或每个高模变体都放进约束搜索。

## 先分清两层

- **结构原型**：`module + yaw`决定接口、功能和布局。墙体、带窗墙、带门墙可以有不同`asset_key`；窗墙的外观变体不再扩大CSP。
- **外观变体**：由样式catalog提供模型、实测bounds、anchor和权重。固定结构layout后重新`resolve`即可换风格，不重新求解。
- 默认从完整大模块生成资产，而非先做极细程序化屋顶再逐瓦替换。需要连续曲面、非模块接缝或自由穿插时选择普通SOP／重叠WFC方法，不把本技能伪装成通用几何布尔系统。

简单重复且无邻接约束时用`houdini-sop-workflow`；模型导入、材质和高低模用`houdini-asset-integration`。本技能不复制生成服务账户、下载或材质导入流程。

## 设计最小充分规则

1. 明确模块的安装面、局部Y-up、+Z前方和格元尺寸；先列出不可违反的接口，再考虑随机性。
2. 规则网格使用`shape`及可选`active`；非矩形、稀疏或任意连接使用`cells + edges`。需要网格／图、socket、旋转、固定与数量规则的准确格式时读[结构规格](references/spec-format.md)。
3. 默认同名socket匹配；仅在有明确接口语义时添加对称`socket_pairs`。不要靠大量名称变体表达本可旋转得到的模块。
4. 用`constraints`固定用户指定位置，用tags和`counts`控制门窗等数量，用`connectivity`要求道路等最终连通。权重只影响可行选择，不是需求保证。
5. 先求小代表样并检查接口，再扩大网格。复杂约束可能需要指数回溯；设置预算，`budget_exceeded`时调整规则或预算，不能报告成无解。

## 准备外观模块

读[资产与Houdini接入](references/asset-and-houdini.md)，为整套模块建立共同风格、材质、尺度、视角和接口说明。让每张参考图只表达一个完整模块，避免地面、背景建筑、文字和遮挡成为模型的一部分。

- 优先生成在功能上可替换的模块：同类墙保持相同安装轮廓，窗洞／门洞属于结构差异而非随机贴花。
- 生成后实际检查风格、形状和材质；提示词中的米数、Y-up或“无背景”不是实测事实。
- 导入后读取真实bounds并选择anchor。默认`fit.mode=none`；确有容差时用`uniform`，确需少量轴向拉伸时用`axes`并声明`min_scale/max_scale`。超限时修源模型或明确调整容差，不静默大拉伸。
- 允许的小穿插是美术取舍，不是几何正确证明。先检查代表接口和最终整体，再决定是否需要重新生成极端模块。

## 求解、复核、解析外观

在普通Python环境执行，无第三方依赖。将`$skillDir`设为本skill绝对目录，将`$work`设为本次已存在的输出目录；命令不依赖cwd，默认不覆盖文件。

```powershell
$skillDir = 'C:/path/to/dsh-houdini/skills/dsh-wfc'
$work = 'C:/path/to/wfc-output'
python "$skillDir/scripts/wfc.py" validate "$work/spec.json"
python "$skillDir/scripts/wfc.py" solve "$work/spec.json" --output "$work/layout.json"
python "$skillDir/scripts/wfc.py" verify "$work/spec.json" "$work/layout.json"
python "$skillDir/scripts/wfc.py" resolve "$work/layout.json" --catalog "$work/catalog.json" --style brick --output "$work/instances-brick.json"
```

可直接求解随包`assets/room-shell.spec.json`学习结构规则。`solve`返回0表示成功、1表示输入／校验错误、2表示已证明无解、3表示预算耗尽。仅复用成功且`spec_sha256`匹配的layout；只有明确替换旧结果时才加`--force`。

保持`layout.json`不变，换`--style`并输出新文件即可热替换砖墙、石墙或现代墙。保持各风格相同`asset_key`及对应variant ID；外观文件缺失或缩放超限会显式失败，不能回退到占位模型冒充成功。

## 接入原生实例

按[资产与Houdini接入](references/asset-and-houdini.md)把每个选定`piece`准备成同一SOP网络内的源节点，再在`houdini_exec`导入`houdini_bridge.py`并调用`build_instance_network(..., api=globals())`。适配器只负责JSON→点属性、原型name／`wfc_piece`、Pack、Merge和原生Copy to Points；WFC求解不藏在Python SOP中。

只需要模板点或自定义USD消费者时省略`prototypes`，使用`OUT_WFC_POINTS`。需要SOP实例时传入全部选定piece的源节点映射，使用`OUT_WFC`。AI文件路径只是元数据，适配器不会暗中重新导入或下载模型。

## 让证据约束下一步

- `verify`核对每条显式邻接、固定约束、数量、连通性及规格哈希；socket相同不证明几何接缝正确。
- `verify_network`只证明明确输出可计算且非空。另查代表性原型和最终实例的实际几何、朝向、安装anchor与接口。
- 至少用一个90°实例和非零anchor检查旋转、pivot和缩放；整体bbox不能发现窗洞错位、屋面穿插、薄件缺失或材质错误。
- 用整体和接口近景观察最终资产；没有成功识图就保留视觉未验证。夸张变形或明显接缝回到对应源模块，不用继续增加全局容差掩盖。
- 换结构规则后重新求解和检查受影响邻接；只换外观时复用layout，但重新检查新模型的比例、材质和接缝。

## 实现边界

求解器采用bitset域、MRV、约束传播、带恢复的加权回溯和确定性seed；没有全局数量／连通性约束时，独立连通分量共享同一预算分别求解，避免无关区域交叉回溯。它不是overlap模型、自动规则学习器或任意规模性能保证。样式变体由独立hash选择，同seed和cell可复现；结构权重在各yaw间平分，避免四朝向模块无意中获得四倍权重。

方法依据[mxgmn/WaveFunctionCollapse](https://github.com/mxgmn/WaveFunctionCollapse)的simple-tiled模型与SideFX[实例属性](https://www.sidefx.com/docs/houdini/copy/instanceattrs.html)／[Copy to Points](https://www.sidefx.com/docs/houdini/nodes/sop/copytopoints.html)。精确schema、旋转及适配规则以随包脚本和上述reference为准。
