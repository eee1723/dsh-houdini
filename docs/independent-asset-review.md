# 按需快速资产复核 v10（候选）

2026-09-07。用户批准精简评审并同步修复作者端工具，要求评估评审是否值得保留。
结论：普通建模不默认委派。保留用户明确要求或具体疑点需要第二视角时的短复核；主要投入
放到作者执行成功率、输出质量与必要检查。五工具/57动词/六skills不变。

## 当前入口

`houdini_exec(review={parent,output,controller?})` 仍是一次前台spawn，与code/allow_raw/
review_test互斥。只绑定本任务拥有的SOP网络及直属output/controller；foreign/非SOP资产
仍走只读审查，不因评审身份扩大权限。作者等待一次结果，按确认的问题修正。

Host将原始用户消息/问答/附件转交；Bridge在begin同一主线程工作项中取得当前几何、健康、
有效控制（排除文件夹）、命名部件、point group实际涉及的piece及实验适用性。
摘要有明确截断标记、128直属节点及底层几何预算，名称分组不证明连通。
Host从当前session提取最多8条/16K字符历史工具事实：只读Host前缀中的operation-evidence，
拒绝stdout伪造、非Houdini来源、错误结果和重复回放。保留实际case/值/范围/时间/指纹，
不是作者自评，也不是当前依赖有效性的认证；历史事实需要按后续修改与范围解释。
已有render路径经media映射转交，图片仍需实际读取。没有注册、冻结合同或长期结果缓存。

评审的skill直接内联，仅提供query/exec/read_image，不再重复加载技能与接口全文。
优先已有相关图片；针对缺件、未覆盖关系或报告夸大等具体疑点补查，通常六次以内工具调用，
四分钟硬上限。返回“发现的问题、必要补查、检查范围”；无问题写限定范围未发现阻断项，
不用整表pass。Host另返回真实review_test批次的case/恢复/unsupported概况，明确评审完成
不等于资产通过。作者不能用少数自测覆盖其他未测项。

## 受控实验

`review_test={tests:[{id,values,expectations?}],views?,interfaces?,topology?,domain?}`。
整个评审最多三个针对性case；无expectations只返回responsive/unchanged并保留unverified。
views最多两个iso/front/side/top，含基准最多八张；空tests仅取基准图。不会为了拍图
重复完整建模验收。普通作者test_controls仍最多16case，支持Float/Int及Toggle整数0/1；
菜单、按钮、回调、multiparm测试目标仍拒绝。

`test_support.supported=false` 在开始时即可发现，直接只读，不规划无效实验、不换表示
迎合白名单。当前安全网络类型边界保留，任意VEX/Python/File/Solver仍未放开。
支持时每case在同一主线程内改参/cook/测量/产图/恢复，核对参数/keys/frame及完整bgeo。
无法支持/零写入不是恢复实验成功；截图用户状态恢复失败阻断下一case。
参数状态可能各自重新取景，固定相机跨参数比较仍不是保证；动画保留同framing_frame要求。

权限短期绑定唯一child、作者、HIP/节点身份/起始网络参数和frame；普通修改/保存/删节点/job/
再委派不可用，ownership与Raw Gate不变。改变基准或恢复失败必须停止，不覆盖用户值。
取消/结束/异常撤销；异常失联至多四分钟。不是任意Python安全沙箱。

## 作者端修复

- node_info展开有界静态multiparm实际实例（默认或声明count），明确父context错误；build_module
  先设置父/子count再严格设置实例字段。动态count及超预算显式拒绝，保留tab_create路径。
- cook_node对已有错误强制刷新一次；修正HScript后不再因旧错误被迫重复探针。
- build_module失败直接附具体节点cook_details，空CTRL用tab_create，保留非空交付门。
- geo_check_interfaces回包列source_pieces/target_pieces，不把组名当覆盖保证；Toggle用例支持0/1。
- hython缺GUI时不探测hou.ui；失败undo后只清理本调用journal记录的确切新建identity，
  不按路径、父网络或模型自述扩大ownership；有foreign后代则停止并报告恢复异常。

## 证据与评审必要性

真实v9会话7d145b95…作者61calls/评审18calls，总约42分钟；评审约6分53秒。作者三个数值
控制和开关有行为证据，评审实际0 writes，未发现实质缺陷仍总评pass；接口组漏左右围板。
用户确认手动调参/切换节点，基准变化不能据此判工具误报。真实委派/基准图/语义读图/回传
已验证，真实评审扰动恢复尚未验证。当前live health读到v9/57，v10没有自动重启。

本轮独立离线前向检查：只给新skill、实际当前快照/原始要求/历史工具事实和已有图片，不给
分析结论。检查者1次读取材料+2次读图，指出接口覆盖遗漏、保留未测控制和unsupported；
简单指定Box编辑正确不委派。这是不同模型的离线材料检查，不是新K3实会话或效率A/B。
原始表格、轨迹HTML/JSON和前向材料留在不打包的tools/out，生产skill不写实例答案。

评审去留：不为证明评审而重复建模或扩正式矩阵。后续正常任务只有确有需求才调用；记录
新增且可独立确认的缺陷、有效修正、误报、额外调用/耗时。若接下来的自然使用仍只复述
作者结果或反复unsupported、没有实际减少返工，继续收缩为显式只读复核，不恢复默认委派。
只有新问题发现与有效修正抵得上成本，才讨论扩大适用范围；本例不支持删除底层检查器。

## 验证与回退

Node17文件回归；H21.0.440/H22.0.368各25个Python脚本（结果见tools/out/v10-regressions-*.json）。
覆盖原始材料/附件、历史事实来源与去重、tool限制、publication race/清理、三case预算、
提前unsupported、主线程、恢复失败、动态参数、旧错误刷新、Toggle、headless Copy及嵌套
构建失败后的身份/参数恢复。真实Node→HTTP→主线程使用确定性child替身，不冒充模型增益。
身份残留防御另用部分undo故障注入验证；原trace的GUI/shelf异常根因尚未独立复现。
新K3任务/GUI扰动恢复、未见复杂正例与相邻领域行为发布门仍未全部验收，状态candidate。

原v9生产delivery清理仍有效：旧模块和专属回归在tools/prototypes/retired-delivery，不打包；
通用网络/接口/拓扑/domain/test_controls保留。回退需整体恢复v9源码/契约，重新生成/构建
并重启两端；不能只换提示或只撤销权限校验。冻结protocol/matrix/holdout本轮不变。
