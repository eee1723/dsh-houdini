# Rig与动画设计

本页维护系统路由与交付边界，精确节点设置和配方由[rig skill](../skills/houdini-rig-animation-workflow/SKILL.md)
及[rig reference](../skills/houdini-rig-animation-workflow/references/rig-animation-patterns.md)单独维护。
执行层复用通用节点、参数、关键帧和几何动词，不新建一套rig专属工具协议。

## 路由

| 意图 | 系统选择与边界 |
|---|---|
| 新建几何父子机械/FK | KineFX SOP joints，修改前读reference中的最小路径 |
| OBJ场景装配、旧场景、用户明确要求或下游交付 | set_object_parent，说明reason并回读keep_world；不从“放在/obj下”推导层级授权 |
| 简单独立通道动画 | channel/keyframe，不强制建立骨架 |
| packed实例/刚性部件变换 | 稳定piece身份与实际transform检查，不把P-only当完整运动 |
| solver驱动 | 对应模拟生命周期和真实时间输出，不用预烘焙/静态代理冒充 |
| APEX/IK/控制器系统 | 明确该系统要求时使用；KineFX与APEX不是同一个节点接口 |

类型namespace必须保留；例如kinefx::rigpose与apex::rigpose接口不同，不凭裸别名猜测跨版本一致。
SOP节点创建于SOP parent；/obj下的OBJ subnet不是SOP容器。通用connect不负责OBJ parenting。

## 三层交付

driver skeleton → binding/evaluation → driven deliverable。

骨架在动、绑定metadata存在或混合总bbox变化都不能证明最终表面在动。
Attach Joint Geometry的control/capture shapes不等于蒙皮后的交付几何。
刚性捕获路径和Joint Deform输入/属性以rig reference为准，避免在本页维护第二份参数表。

每个piece保留稳定身份、局部轴、rest和驱动关系；测实际交付部件的位置、方向、刚体不变量和恢复。
连续变形与刚体motion使用不同判据，不能用所有点的混合均值当每件设计中心。
关键控制集中维护，参数变化需保留绑定及模块连接，不重复修改多份VEX常量。

## 验收与恢复

原型先过driver/evaluation/output检查再扩大结构。动画至少比较相隔帧，并按任务覆盖非交换转折、
中间状态、端点与恢复；固定构图A/B使用同framing_frame和包络。
driver/helper与最终几何分离，所有结果绑定实际OUT与frame；相关修改使旧证据失效。
文件、solver和外部脚本不属普通control实验恢复保证；没有实际语义识图就写视觉未验证。

维护验证：[KineFX回归](../tools/tests/dsh-kinefx-fk.test.py)、
[object parenting](../tools/tests/dsh-object-parenting.test.py)、
[模型身份](../tools/tests/dsh-modeling-identity.test.py)。
测试源码是可执行边界，单个回归通过不能证明所有未见机械结构或动画审美。
