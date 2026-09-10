# 缓存、材质接口与文件交付

Applies when：纹理导出、缓存排错、性能诊断或 COP→材质交付。
Do not use when：仅局部编辑不要求落盘；静态纹理路径不适用于反馈模拟。
版本：下列官方来源为 H22，精确 token 与执行行为需目标 runtime 确认。

## 缓存与分辨率：分层定位

- 记录网络默认、显式图层尺寸、有效 pixel scale/proxy、Cache 输出和 ROP 输出设置。
  ROP 默认分辨率不是强制 resize：File/几何转换等确定的尺寸可能不受其影响；
  需要固定尺寸时评估显式 Resample，并验证过滤对 ID/高度的影响。
- Cache 是内存结果，可关闭上游变化清理以保留快照；快照不保存对应上游参数。
  检查是否刻意保留旧状态，不把“最新 cook 请求”当“最新图层”。
- 排错固定路径与输入，一次只改变一个因素，分别读上游、Cache、ROP、落盘数据。
  mtime 更新或字节相同不能单独证明成功/未执行；超时先查回执，不盲目重复写盘。
- 只对授权范围采取已知刷新方式；不要为局部问题清空用户全局缓存，或默认重置全部模拟。

来源：[Cache](https://www.sidefx.com/docs/houdini/nodes/cop/cache.html)、
[ROP Image](https://www.sidefx.com/docs/houdini/nodes/cop/rop_image.html)。

## 性能只在需要时诊断

先用较低有效分辨率做交互诊断，交付前恢复并重验。Traditional cook 保留中间结果，
Compiled cook 可减少不需要的中间存储，但不是无条件更快，官方明确不支持模拟。
有性能问题才比较实际输出与耗时、RAM/VRAM，不用节点数量推断瓶颈；不自动改全局 OpenCL 配置。
精确 GPU timing 可能引入同步开销，仅在诊断时开启并恢复。
来源：[Cooking](https://www.sidefx.com/docs/houdini/copernicus/cooking.html)、
[Tips](https://www.sidefx.com/docs/houdini/copernicus/tips.html)。

## 材质接口

仅当需要查看实际材质才加载 `houdini-solaris-karma-workflow`。交接图层角色、输出定位、
坐标空间、颜色解释和预期效果；由它选择当前版本可用的 Texture Material Library / USD Material COP、
Quick Surface Material 或 Karma Material Builder 路径，不同时搭建多套接口。
`op:` 引用必须确认实际输出及消费端支持；不能假设外部进程、重开或其他渲染器都能解析当前会话引用。
可移植交付应验证依赖或使用获授权烘焙文件。SOP UV/材质绑定检查先于完整细节和最终渲染。

法线要区分 signed 与 offset 编码，并另外核对切线/世界等坐标基底与消费端约定。
Karma 的几何/渲染法线与 shader normal map 输入不能因同属 RGB 而直接互换；
位移还需核对高度单位、零点与幅度，不以预览 hillshade 证明真实位移正确。
来源：[Working with COPs](https://www.sidefx.com/docs/houdini/copernicus/working_with_cops.html)、
[Normals](https://www.sidefx.com/docs/houdini/copernicus/normals.html)。

## 文件合同

反复导出使用可复现的 Image ROP/ROP Image Output；回读源输出到文件 AOV/Port 的映射。
更新 AOV 列表可能替换现有配置，先看实际 multiparm，不把同名 AOV 当作端口已正确绑定。
输出按用途分别声明：尺寸、通道、数据精度/编码、颜色空间、路径/帧范围和允许误差。
颜色纹理按消费端色彩管理；高度/粗糙度/遮罩/ID 等数据不能烘入显示变换。
HDR、负值、精细高度优先评估浮点格式；受限整数格式需显式范围映射、还原方式与误差预算，
不默默 clamp 到 0..1。不要仅凭扩展名推断实际位深。

File 节点在线 H22 帮助的 Raw 标签与描述方向存在歧义；不根据标签猜 on/off。
H21.0.440/H22.0.368 的单通道浮点 EXR 已验证 File colorspace=raw、对应 AOV raw=1 的原值读取；
ROP colorconversion=raw、AOV raw=1、size=float32 可保存该范围。该窄路径不证明颜色纹理的
OCIO 转换或其他格式正确；目标版本仍发现实际菜单 token 与动态 AOV 参数，再以已知值读回。
来源：[File](https://www.sidefx.com/docs/houdini/nodes/cop/file.html)、
[ROP Image](https://www.sidefx.com/docs/houdini/nodes/cop/rop_image.html)。

写完逐文件读头并解码必要数据，与最后有效 COP 输出比较尺寸、通道、范围和编码误差；
只测一张不外推全部。按实际需求再查 U/V 平铺与最终材质。保存成功后的打印错误不撤销文件 I/O，
先核对回执和文件；重开与依赖验收缺失时明确未验证，不重复保存来掩盖未知。
