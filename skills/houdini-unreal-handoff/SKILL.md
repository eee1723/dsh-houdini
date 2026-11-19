---
name: houdini-unreal-handoff
description: 为 Unreal Engine 准备可迁移的 Houdini 数字资产，包括可调参数、材质槽、灯实例和接收端可核对的交付清单。只做 Houdini 侧资产，不接管 UE 编辑器。
---

# 把 HDA 交给 Unreal

先区分要在 UE 中继续调参的 HDA 和不再依赖 Houdini Engine 的烘焙成品；需要两者时分别验收。使用用户目标 UE、Houdini 和 Engine 插件的实际版本，不从作者机器推断接收环境。现有项目的材质库、内容目录和灯具蓝图是输入，不硬编码项目路径、渲染器、Nanite 或灯数。

**作者端。** 用 [HDA 开发](../houdini-tool-development/SKILL.md)发布定义和有意义的公共控制。在脱离作者 HIP 的干净目录按交付说明实例化、改变代表性参数并重新计算；检查的是定义的最终输出，不是 HIP 中相邻节点。读不到的外部文件要打包并让定义在迁移后解析到它，或声明为接收方提供的依赖。测试可用[隔离执行](../houdini-isolated-execution/SKILL.md)，不改用户现场。

**材质。** 有现成 UE 材质时向接收方取得真实资产引用，按面赋 `unreal_material`；需要实例参数时用 `unreal_material_instance` 和母材质实际暴露的参数名。没有母材质时，可选择 Engine 能翻译的着色器，或交付纹理与通道约定给接收方建材质。记录槽标识、对应面组、UV、色彩空间、法线方向、遮罩与打包通道；只记录用到的项。在改变参数后检查面组仍消费相同槽。不能把 Solaris 或视口中正确的外观直接当作转换结果。[SideFX 材质转换范围](https://www.sidefx.com/docs/houdini/unreal/materials.html)

**灯光。** 分开发光表面和真正照亮场景的灯。需要后者时可用独立几何 part 的点实例输出，以 `unreal_instance` 指向目标支持的 Actor 类或已有蓝图。交接稳定标识、坐标空间、方向、颜色、光强及单位、衰减和相关公共控制；不要假定 Actor 根属性会自动写入灯组件。请接收方读取实际组件值，不以点数或画面变亮代替。[SideFX 实例规则](https://www.sidefx.com/docs/houdini/unreal/instancing.html)

**生成交付包，不手填依赖。** 在独立的干净 hython 进程执行 `hython <skill-dir>/scripts/package-instance.py <源HDA> <新目录>`。输入是可信的独立 SOP 定义与它已能解析的资源，不是让程序递归打包整个目录。多类型库传 `--type`，非默认标量参数可传 `--values` JSON 对象；需要接入现场输入或其他类别的 HDA 不属于这个工具。新目录不得位于源包内。

- 生成的 `delivery.json` 记录实际类型、Houdini 版本、采样状态、文件与引用节点、各 SOP 输出及材质和实例引用。展开延迟加载的内部定义，从参数与嵌套库收集文件；glTF/GLB 的外部图片和缓冲区沿 URI 递归收集。保留源包相对布局，系统字体单列，不自动复制。包外或找不到的文件产生 `unresolved.json` 并停止交付；在作者副本修正引用，不凭同名文件猜路径。
- 在新进程执行 `hython <skill-dir>/scripts/package-instance.py <迁移后的HDA> <新证据目录> --verify`，复算并比对清单；`node <skill-dir>/scripts/check-package.mjs <delivery.json>` 输出每个文件的 SHA-256。二者分别证明当前实例能重建、文件字节可核对，不证明所有参数分支、序列、任意着色器／脚本的动态读盘或画面效果。
- 有已保存的 UE 项目材质或蓝图时，可在**拥有依赖的 UE 编辑器**内通过 Python 的 `runpy.run_path` 加载 `scripts/ue-content-files.py`，调用 `export_for_delivery(manifest, destination)` 只读导出。资产注册表从输出引用沿硬／软包依赖查找，将项目文件保留为 `Content/...`，非项目挂载点和引擎类列在 `content-files.json`；接收项目须已提供这些挂载点。在干净项目中保留 Content 路径，再导入交付目录内的 HDA，不能移动 HDA 却留下其同级资源。没有 UE 源内容就报告未提供，不能从材质名还原母材质。

**接收方。** 导入定义、实例化并等待 cook，再按输出查网格、槽与灯组件；用一个会改变输出的公开参数复算。需要脱离插件时才 bake（烘焙为 UE 原生资产），迁移到干净项目并重开；对照同机位近景，薄件消失时分开查源几何、材质遮罩与目标网格构建设置，不全局切换 Nanite。接收方可使用 [Houdini Engine Public API](https://www.sidefx.com/docs/houdini/unreal/publicapi.html)或自己配置的 [UE MCP](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor)，按实际能力读取输出与组件。未收到回执就报告“Houdini 侧已检查，UE 未验证”；本插件不实现编辑器导入、建材质、布灯或烘焙服务。

正式槽位比较使用已精化的 StaticMesh，不把仍在显示的代理算作缺材质。若实时点灯标签正确而 bake 后多盏灯被赋成同一标签，检查对应 Engine 版本是否按几何 part 重用标签；需要逐灯身份时可把它们发往不同 part，不要求所有灯具都拆分。迁移烘焙关卡时，以地图和实际绑定材质作为依赖遍历的起点；仅复制地图和网格可以正常打开但槽内材质为空。
