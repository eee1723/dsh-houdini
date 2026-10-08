# 文件与图片交付

节点导航归本skill，文件使用DSH `present`。先核对实际文件与必要依赖，再发布权威路径；Session workspace可能不同于$HIP。HDA、HIP、贴图、缓存或脚本各自说明使用和加载条件，不把其中一个存在当成整项完成。

工程目录按用途统一，实际位置读取`scene_info()['project_layout']['directories']`：网络参考使用`reference_downloaded`，生成辅助参考使用`reference_generated`，材质依赖使用`texture`，成图使用`render`，过程检查使用`visual_check`。目录角色与生命周期合同见[工程文件](../../../docs/project-files.md)，不要另建资料清单来替代原始来源或DSH回执。自动输出返回实际路径后再交付；不因另存为而移动历史图片或重写旧卡片。

需要交付视觉结果时，给用户已经核对的整体图和必要局部图，避免只交隐藏工程。`render_view`针对明确SOP结果，`viewport_screenshot`针对SceneViewer当时显示，`houdini_ui_screenshot`针对明确界面的当前实际显示；用途不同，不互相代替。已有表面的选择与捕获边界见[通用界面观察](../../houdini-tool-development/references/evidence-and-validation.md#观察实际工作界面)。

最终图片用`output_policy='delivery'`生成到已命名HIP旁的`dsh-render/`，消费回执的实际文件后再present。picture只传安全basename，分配器追加frame/capture标识，不猜文件名。普通managed观察图在`dsh-visual-checks/<run-id>/`，不自动全部交付。未命名HIP的临时UI观察可用explicit绝对路径；不为截图强制Save As。

```python
__result__ = render_view('/obj/example/OUT', picture='overview.png', output_policy='delivery')
# 核对返回的实际文件及图片内容后，通过DSH present声明该路径。
```

正式ROP图片可在渲染前选择`$HIP/dsh-render/asset_final.png`；临时picture覆盖不证明持久ROP设置已保存。已有用户目的地和ROP优先，不为统一目录默默重设。无识图能力时不能宣称视觉通过；用户需要的图片仍可交付并注明观察范围。

已发布卡片指向源文件，不复制内容。移动、删除或改写源文件会影响历史入口；明确迁移时核对新文件并发布新路径，不重写历史回执。

任务内收尾只处理本次创建、确认不再用于运行/恢复/交付的明确临时探针、画稿和图片，保留依赖、参考、在途捕获和执行归档。普通文件用DSH通用文件工具，Houdini对象用Bridge动词。未知来源保持不动，不建立另一套交付或清理账本。
