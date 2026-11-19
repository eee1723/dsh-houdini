# WFC构件目录与Houdini实例接入

导航：[构件与测量](#构件与实测目录) · [原生适配器](#原生sop适配器) · [检查与换风格](#检查与换风格)

## 构件与实测目录

本页只负责已构造模块怎样进入WFC消费者。风格目标、部件参考图、成组微差变体、生成／原生分工、尺寸域与构造方法统一见[程序化部件构造](../../houdini-kit-workflow/SKILL.md)；文件／材质导入见[资产接入](../../houdini-asset-integration/SKILL.md)。源可以是完整外部模型，也可以是Houdini由小部件拼装的完整构件，不要求一份云生成对应一个WFC cell。

catalog记录导入并统一坐标后的**真实构件输出**，而不是内部某片瓦或设计代理。区分总包络`bounds_min/max`和实测安装主体`fit_bounds_min/max`，不能用期望格子尺寸倒填测量。准确字段及变换语义见[规格说明](spec-format.md#外观变体与适配)，不向当前schema添加未实现的接口字段。

已按目标尺寸构造的模块通常使用`fit.mode=none`；不因resolver支持`axes`就再次拉伸高模。anchor可位于几何外，应对应真实安装基准；有旋转或偏置时检查相应实例。布局变换为`P + yaw(scale * (source_point - anchor))`，world_bounds只包围相同变换后的AABB角点，不证明接口贴合。

同一个piece对应的asset、bounds、anchor与实际原型须来自同一有效源版本。构件参数或部件替换改变输出后，更新有关测量／缓存与catalog，再检查消费者；只改内部外观不等于总包络或接口一定没变。WFC不在resolver内进行自动修形、裁切或碰撞修复。

## 原生SOP适配器

先将每个resolved `piece`对应的真实构件整理为当前装配SOP网络内的直接子节点。跨网络资产用原生Object Merge显式引入，保持可编辑源。然后在`houdini_exec`中执行（替换实际skill路径、JSON和piece映射）：

```python
import sys
sys.path.insert(0, r'C:/path/to/dsh-houdini/skills/houdini-wfc-workflow/scripts')
import houdini_bridge

# 已由本任务创建、构造或导入真实资产的装配网络与源出口。
root = hou.node('/obj/wfc_assembly')
wall_a = hou.node('/obj/wfc_assembly/SOURCE_wall_a')
result = houdini_bridge.build_instance_network(
    root, r'C:/path/to/instances-brick.json',
    prototypes={'wall::a': wall_a}, api=globals())
__result__ = result
```

`prototypes`的key须覆盖本次JSON中选定piece，可以预备尚未被选中的变体，以便切换外观seed时复用原型库。适配器不会根据asset路径猜测如何导入，也不自动调用构件生成器。

生成结构：

- `WFC_POINTS`：薄Python SOP，读取公开`instances`文件参数并创建点，没有求解逻辑。实例模式显式连接原型输入，每次cook核对所需piece是否存在，源被清空或新JSON缺原型不能悄悄少放模块。
- 点属性：`P`、`pivot`、`scale`、`orient`、`cell_id`、`asset_key`、`variant`、`wfc_piece`、`asset`。
- `PIECE_*`／`PACK_*`：只写`wfc_piece`作为匹配身份，每个构件原型打包一次，Pack pivot显式为origin；保留源内部`name`、材质和几何。构件内部若已有packed部件，要另查嵌套消费者，不能用外层中心代替真实顶点判断偏移。
- `PROTOTYPES`：多个原型时Merge。
- `OUT_WFC`：原生Copy to Points 2.0，以`useidattrib=True`、`idattrib='wfc_piece'`匹配源与点；输入已打包，所以此Copy用`pack=False`，不在这一层再次打包。显式将`cell_id/asset_key/variant/asset`传至最终packed primitive，后续选件与诊断读取最终输出属性。
- 无`prototypes`时输出`OUT_WFC_POINTS`，不交替代理或自定义实例消费者。

H21.0.440与H22.0.368的原生回归覆盖偏心原型、90°旋转、非均匀缩放、外部anchor、风格切换后的最终解包顶点与primitive身份，以及动态缺件；这不认证任意嵌套构件、Tripo模型、贴图或视觉接缝。节点依据见[Copy to Points](https://www.sidefx.com/docs/houdini/nodes/sop/copytopoints.html)：piece属性必须同名并存在于源点／primitive与目标点。

## 检查与换风格

先观察源构件，再检查代表性相邻组合和最终实例。`verify_network(parent, output=...)`只负责cook与非空；用实际几何测量及可辨近景判断比例、端面、全高接缝、开口、薄件、材质与穿插。离散射线／截面只证明已采样范围，少量命中不是完整净空证据。视觉遮缝、实体贴合和单一水密网格是不同要求。

热替换兼容风格时保持原layout，重新resolve到新JSON。若所需piece已在原型库中，替换相应源并将`WFC_POINTS.instances`指向新文件；若出现缺少的piece，补充原型并接入Merge或重建映射。始终检查最终几何和材质，不把layout复用当成新外观合格。

完整构件改了占位、坡度、开口或socket兼容性时，不能当成纯外观替换；回到结构规格重新求解或调整布局。共享源／缓存及部件层面的重算范围见[换源方法](../../houdini-kit-workflow/references/dimensions-and-assembly.md#变体和换源)。具体问题定位到源、构件、规则或消费者，不增加第二套实例变换和隐藏修补来遮住问题。
