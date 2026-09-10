# 图层、空间与端口

Applies when：创建/诊断 Copernicus 数据流、多输出引用或版本迁移。
Do not use when：只需使用现有纹理文件；旧 COP2 未经核对不能套用本页。
版本：官方在线 H22；具名连接与下述 Noise/UV 端口机制在 H21.0.440/H22.0.368 隔离回归。
其他节点/模式仍从当前 runtime 发现，不把局部支持外推整个 COP 目录。

## 先认数据，再认节点

每条关键边记录：源节点及输出、目标节点及输入、实际索引、Signature、数据角色与坐标空间。
Mono/UV/RGB/RGBA 表示通道布局，ID 表示整数身份；RGB 也可承载位置，不自动等于颜色。
Type Info 是解释信息；自动 Signature 与通道扩展可能让错误连接仍被接受。
Metadata Layer 可接受图层，但用于尺寸/位置等元数据，不证明像素值参与计算。
因此“类型兼容”只是入口检查，角色与下游响应仍要验证。

**官方例子，仅用于发现角色，不固定端口序号：**

- Fractal Noise 的 `size_ref` 提供尺寸/元数据，`pos` 才是替代默认采样坐标的 UV 图层。
- HSV Adjust 中 `hueshift`、`saturation`、`value` 对应不同控制；还要核对 Operation 与输入缩放参数，
  不能把接入任意辅助口都称作明度驱动。

来源：[Glossary](https://www.sidefx.com/docs/houdini/copernicus/glossary.html)、
[Fractal Noise](https://www.sidefx.com/docs/houdini/nodes/cop/fractalnoise.html)、
[HSV Adjust](https://www.sidefx.com/docs/houdini/nodes/cop/hsv.html)。

## 空间与采样

Texture space 覆盖 data window 的 0..1；Image space 按 display window 与像素长宽比解释，
不能对非正方形图、裁切图或世界坐标统一套一个 0..1→-1..1 公式。
比较或组合前确认 data/display window、变换、分辨率、采样/边界模式及像素对应关系。
相同数组长度不证明像素对齐；需要重采样时显式说明映射与过滤，不偷偷归一化数据。

SOP 几何进入 COP 时先检查世界空间和投影/栅格化；COP 图层与材质 UV 又是另一边界。
用双色方向图或 U/V 梯度检查两维独立变化、方向与覆盖，不按几何类型猜平面轴向。
ID/离散标签处理要验证身份没有被插值破坏；连续颜色/高度的过滤选择不能机械照搬到 ID。
来源：[Spaces](https://www.sidefx.com/docs/houdini/copernicus/spaces.html)、
[Tips](https://www.sidefx.com/docs/houdini/copernicus/tips.html)。

## 连接、动态参数与能力缺口

1. 对实际 parent 做 Tab 发现，读取当前节点模式、端口和参数菜单 token。
2. 先看 `connect` 的实际契约。当前 `index` 接受目标输入名/索引，keyword-only `output` 接受
   源输出名/索引；`describe(node).ports` 提供实际名称/索引/类型，名称不是label。
   默认源输出仍是0。新建 Cache 等动态端口可先为 undef；type_check 会标明动态签名，仍须 cook/关系检查。
   旧 runtime 不支持时不得猜 keyword 或借 raw 旁路。
3. mutation 后回读两端及源输出选择；注释、节点名和网络线条不代替实际连接证据。
4. Fetch 是跨 COP 网络引用的官方方案，不是所有多输出连接的默认绕路。
   使用时核对 source path 与输出映射；按钮/模式变更后用 `list_parms` 查看实际 multiparm 实例，
   不只遍历顶层参数模板。按钮可能改写现有配置，执行前明确影响和授权。
5. 工具无法表达目标关系时，报告精确缺口；仅在公开参数方案已验证等价时采用替代。
   不通过 raw 连线绕过已覆盖修改，不无限尝试无关节点。

来源：[Working with COPs](https://www.sidefx.com/docs/houdini/copernicus/working_with_cops.html)。
本流程的 checkpoint 是“实际映射 + 下游关系”，不是“Fetch 成功生成输出”。
