# 外观资产与Houdini实例接入

## 目录

- 让生成资产承担外观细节
- 实测尺寸与安装anchor
- 原生SOP适配器
- 检查与换风格

## 让生成资产承担外观细节

把模型预算花在用户能看到的完整模块上：带材质墙、窗墙、门墙、转角和屋顶，而非把程序化瓦片逐个替成高模。先生成少量代表模块并试装，再扩展整套；不要一次为所有外观变体付费。

整套提示词共享一段明确风格合同，再只替换模块功能段。至少固定：

| 方面 | 应明确的内容 |
|---|---|
| 风格 | 时代、地区、形体语言、磨损程度、细节密度，不堆砌互相冲突的风格词 |
| 材质 | 主／辅材料、有限色板、粗糙与新旧程度、窗框／门框等共享部件语言 |
| 模块 | 单个完整物体、功能类型、安装面、开口位置及需要保持的接口轮廓 |
| 视图 | 同一中性光、背景、镜头和三分之四视角；完整入画，无遮挡，无地台／环境建筑 |
| 排除 | 文字、水印、人物、植物、散落零件、额外附件及非本模块的屋顶／墙体 |

可复用骨架：

```text
[SHARED STYLE] 同一<时代／地区／风格>，<有限色板和材料>，<统一细节和磨损程度>。
[MODULE] 仅一个完整<墙／窗墙／门墙／转角／屋顶模块>，<功能和接口>。
[PRESENTATION] 单体完整入画，统一三分之四视角，中性灰背景，柔和中性光，无遮挡。
[EXCLUDE] 不要文字、水印、人物、地台、场景建筑、额外零件或重复阵列。
```

将实际生成图作为后续模块的风格参考时，沿提供方支持的reference输入传递本地图片；URL文字不会自动上传像素。比较生成结果而非只检查提示词。来源生成、授权和材质接入分别使用提供方skill及`houdini-asset-integration`，本技能不另写厂商API或账号流程。

## 实测尺寸与安装anchor

模型进入Houdini后再测bounds，不把参考图或提示词中的比例当成事实。优先统一源文件的米制、Y-up和局部+Z前方；无法确认时先完成一次显式坐标适配，避免每个实例重复修正。

`anchor`是安装基准，不一定是几何中心。例如墙可用底部中心，转角可用两条安装面的交点。resolver把`P + yaw(scale * (source_point - anchor))`作为设计变换；world_bounds也由同一关系计算。用90°和离轴anchor检查实际输出，不能只验证0°。

小范围非等比缩放或有意穿插必须逐模块声明容差并观察结果。门洞、窗框、薄屋面、装饰线脚和标准五金可能不能承受同一拉伸；超限时优先修源或重新生成，不扩大全局容差。SideFX实例变换以`X*S*(O*R)*T`组合缩放、旋转和平移，pivot涉及局部`translate(-pivot)`，详见[实例属性](https://www.sidefx.com/docs/houdini/copy/instanceattrs.html)。

## 原生SOP适配器

先将每个resolved `piece`对应的真实模型导入并整理为当前装配SOP网络内的直接子节点。跨网络资产用原生Object Merge显式引入，保持可编辑源。然后在`houdini_exec`中执行（替换实际skill路径、JSON和piece映射）：

```python
import sys
sys.path.insert(0, r'C:/path/to/dsh-houdini/skills/dsh-wfc/scripts')
import houdini_bridge

root = tab_create('/obj', 'geo', name='wfc_assembly')
# 按houdini-asset-integration准备源；这里示意已有同网络源节点。
wall_a = tab_create(root, 'null', name='SOURCE_wall_a')
result = houdini_bridge.build_instance_network(
    root, r'C:/path/to/instances-brick.json',
    prototypes={'wall::a': wall_a}, api=globals())
__result__ = result
```

上例的Null只说明接口，不是可用模型；真实任务必须替成非空源。`prototypes`的key必须与本次JSON中选定piece完全一致。适配器不会根据asset路径猜测如何导入。

生成结构：

- `WFC_POINTS`：一个薄Python SOP，读取公开`instances`文件参数并创建点；没有WFC求解逻辑。
- 点属性：`P`、`pivot`、`scale`、`orient`、`cell_id`、`asset_key`、`variant`、`wfc_piece`、`asset`。
- `PIECE_*`／`PACK_*`：给源写相同`name`和`wfc_piece`，保留这两个属性并各打包一次。
- `PROTOTYPES`：多个原型时Merge。
- `OUT_WFC`：原生Copy to Points 2.0，以`useidattrib=True`、`idattrib='wfc_piece'`匹配源与点；输入已打包，所以`pack=False`，避免双层packed。
- 无`prototypes`时输出`OUT_WFC_POINTS`，不交替代理或自定义实例消费者。

H21.0.440与H22.0.368已用两种原生Box原型验证上述参数及最终解包顶点，包括90°旋转、非均匀缩放和非零pivot；这不等于任意Tripo模型或视觉接缝已经验收。节点行为依据[Copy to Points](https://www.sidefx.com/docs/houdini/nodes/sop/copytopoints.html)：piece属性必须同名并同时存在于源点／primitive与目标点。

## 检查与换风格

先用少量模块检查每个源本身，再检查最终实例。`verify_network(parent, output=...)`只负责cook与非空；另用真实几何测量、接口近景和整体图检查比例、开口、薄件、材质和穿插。packed外壳数量或整体bbox通过不等于内容齐全或接缝严密。

热替换风格时保持原layout，重新resolve到新JSON。若piece ID不变，替换相应源并将`WFC_POINTS.instances`指向新文件；若piece集合改变，重新运行适配器建立完整原型映射。无论哪种都重新检查最终几何与材质，不把结构layout复用当成新外观已合格。

出现极端bug时定位到具体模块和接口，决定修源、重新生成、改变结构模块或调整明确的局部容差。不要增加第二套实例变换、自动碰撞修补或隐藏回退来遮住源问题。
