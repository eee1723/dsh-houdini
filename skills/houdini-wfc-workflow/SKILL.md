---
name: houdini-wfc-workflow
description: 选择并实现Houdini的WFC邻接约束布局：模块接口、固定单元、数量／通路、结构求解、独立外观catalog与原生实例。用于确需约束选择的建筑、房间、道路或管线；部件库与程序化构件制作用houdini-kit-workflow，普通重复／散布用SOP，不要求WFC。
---

# Houdini WFC Workflow

WFC（Wave Function Collapse，按相邻规则逐步选择离散模块的约束生成方法）负责兼容选择，不负责修高模、设计所有建筑形体或保证艺术质量。Houdini构件和生成资产可以完全不经过WFC；本skill只维护需要求解的布局及其消费方法。

## 方法与模块尺度

先区分变化的是整体轮廓、模块排布还是同布局外观。[方法与规则设计](references/method-selection.md)比较随包simple-tiled求解器、Labs样例WFC、Building Generator和普通SOP。任意旋转、跨格大块、曲面和全局规划不假装被当前脚本覆盖；既定体块的立面任务不必使用搜索。

墙段、窗墙、转角和屋顶段可作为求解单元，其内部可以由高质量瓦片、柱头、木板等源程序化构成。**求解粒度与部件源粒度不同**，不让每个外观微差扩大状态空间，也不禁止小部件库。风格、成组变体参考、生成／原生分工与构件制作统一见[程序化部件构造](../houdini-kit-workflow/SKILL.md)。

已知要WFC时先设计模块安装尺寸、占位、开口、连接和旋转范围，再让构件生成器消费同源规格，并用实际部件试装回验。已有资产库先行时先测量再定兼容规格；两种入口都不以提示词尺寸代替真实接口。最有风险的直段—转角或屋面—屋脊组合先验证，不为WFC强制批量生成整套资产。

保持三个职责，不要求用户填写额外表单：

- **结构规格**：功能、接口、占位与布局约束，只有影响兼容性的差异进入搜索。
- **构件源**：Houdini或已有模型提供实际几何、公共尺寸、安装基准及外观包络。
- **外观catalog**：真实文件、测量、变体与权重；仅接口兼容的差异可以在固定layout后替换。

## 求解与外观解析

准确输入见[结构规格](references/spec-format.md)。同名socket默认匹配，需要时声明`socket_pairs`；固定位置用`constraints`，数量用`counts`，道路／管线连接同时描述通行socket。权重是选择倾向，不保证数量或布局质量。

随包脚本使用普通Python，无第三方依赖。在已有工程输出目录执行，默认不覆盖结果：

```powershell
$skillDir = 'C:/path/to/dsh-houdini/skills/houdini-wfc-workflow'
$work = 'C:/path/to/wfc-output'
python -E "$skillDir/scripts/wfc.py" validate "$work/spec.json"
python -E "$skillDir/scripts/wfc.py" solve "$work/spec.json" --output "$work/layout.json"
python -E "$skillDir/scripts/wfc.py" verify "$work/spec.json" "$work/layout.json"
python -E "$skillDir/scripts/wfc.py" resolve "$work/layout.json" --catalog "$work/catalog.json" --style brick --output "$work/instances-brick.json"
```

`python`须是实际可用的普通Python；`-E`避免继承Houdini的PYTHONHOME/PYTHONPATH，不修改全局环境。`assets/room-shell.spec.json`是结构示例，不是建筑资产库。退出码0成功，1输入／校验错误，2证明无解，3预算耗尽；预算耗尽不能报告无解，不反复换seed掩盖冲突。仅复用成功且规格哈希匹配的layout，明确替换时才用`--force`。

固定layout后改变外观seed可换同类变体，改变style可换兼容资产集；改变结构seed、约束或接口时重新求解。新增风格须覆盖实际使用的asset_key；缺件或超出声明适配范围明确失败。完整构件内部的部件变体由其生成器控制，不必把每片瓦映射为WFC cell。

## 原生接入与修改

[接入说明](references/asset-and-houdini.md)维护catalog测量、原生适配器和换源。`houdini_bridge.build_instance_network(..., api=globals())`经现有动词建立JSON模板点、共享原型及Copy to Points，不在Python SOP中隐藏求解。模型文件路径只是元数据，真实源由[资产接入](../houdini-asset-integration/SKILL.md)或构件生成器准备。

重复使用的任务在已有控制入口提供必要的布局、seed、风格与固定模块，方法见[参数界面](../houdini-parameter-ui/SKILL.md)。JSON是交换数据，不要求艺术家手改多份文件；明确的生成／重算动作调用求解，不在每次cook重跑搜索或云生成。一次模型交付无需另开发HDA、服务或面板。

`verify`只核对结构规则；socket一致不证明几何接缝或通行净空。检查实际原型、最终实例数量和`cell_id`，按需展开代表实例核对旋转、锚点、安装面、材质和洞口。只换兼容风格时应保留结构身份；最后相关修改后的观察才有效。数值、近景与整体分别判断，无成功识图则视觉未验证。

## 当前脚本边界

随包实现为bitset域、MRV（优先选择候选最少的单元）、约束传播与带预算的加权回溯，支持正交网格／显式方向图和四向yaw。数量会传播，连通性在完整赋值后复核；强全局约束仍可能昂贵。无全局约束的独立分量共用预算分别求解。外观选择使用独立hash，结构权重在yaw间平分。更大规模或其他拓扑按[方法选择](references/method-selection.md)评估现成实现，不继续叠加任务专用搜索补丁，也不另建WFC任务状态机。
