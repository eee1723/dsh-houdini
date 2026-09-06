---
name: houdini-asset-review
description: 独立审查 Houdini 最终资产是否满足原始用户要求，核对实际输出、控制响应、部件关系和必要视觉/时序证据。用于任务收尾或明确要求评审现有资产；不用于制作资产、替主 agent 修模或离线 trace 效率复盘。
---

# Houdini Asset Review

审查交付物，不替作者复述完成总结。先用原始用户要求和后续选择建立短检查清单，再从实际
输出独立取证；作者的假设、todo、节点标签和自评pass均不是用户验收标准。不要为当前任务
没有要求的制造结构、写实细节、动画或正式渲染增加门槛。

## 评审路径与工具

主 agent 用 `houdini_exec(review={parent,output,controller?})` 委派一次独立前台评审并等待；
Host提供真实用户消息/问答与范围，不需要重新登记delivery合同。评审者独立决定并批量执行
测试，一次汇总返回。发现实质缺陷才交作者修正，修正后针对受影响项复审，不逐参数通信。

- `houdini_query`：读明确OUT、graph、describe、read_parms、属性和逐piece数据。不确定动词
  签名先verb_help；tab_create实际返回hou.Node，list_parms/read_parms返回list，不猜dict。
- `houdini_exec(review_test={})`：取得当前输出健康/分组/控制概况。
- `houdini_exec(review_test={tests:[{id,values:{参数名:测试值},expectations?:[...]}],views?:[...]})`：
  自主测试本次授权控制；最多16case/批。省略expectations只证明有响应/无响应，不能据此判
  行为正确。精确响应预期来自设计要求；不是每个滑块都要推导复杂面积公式。
- tests为空、views非空：取当前基准图。views为iso/front/side/top，最多2视角；一批最多8张
  图（含基准）。图片通过media映射读取，只有read_image实际成功访问才有语义视觉证据。

同一受控调用完成改参、cook、测量/产图、恢复及恢复核对。可以自行开展下一组测试，不请
主 agent 代执行。评审权限只作用于绑定控制上的数值spare参数；普通exec代码、保存、删改
网络、jobs、shell、再委派均不可用。对unsupported不换建模表示来迎合测试器、不用
allow_foreign/allow_raw绕过。恢复失败或用户改变交付基准时停止，明确报告，不覆盖用户值。

## 如何选择真正有用的检查

先看最可能否定核心承诺的证据，再补覆盖。不平均检查所有节点，也不把规则数量当质量。

未通过Host评审入口启动时，review_test并无权限。简单只读检查直接核对既有证据；用户明确
不要额外agent或渲染时，不为执行本skill再次委派。当前自动委派仅支持本任务拥有的SOP
parent/output/controller；foreign资产或非SOP交付用原有只读工具审查，不绕过ownership。

- **SOP/装配**：显式最终输出非空、无error；warning逐条解释。部件应在最终OUT，而不是只
  在上游存在。检查缺件、退化、重复/不合理穿插；整体bbox不能证明局部结构。
- **控制**：先核对可见控制及依赖，批测关键尺寸/数量和跨模块控制；明确记录哪些未测。
  响应检查能找dead control，但“有变化”不证明变化正确。用少量关键关系/不变量验证设计，
  不从实际测量反推合格线。修正错误预期须有独立理由，不能放宽容差掩盖坏几何。
- **连接**：独立表面选择实际接触端点到目标面的interfaces；融合Polygon才用topology共享
  边连通/闭合。距离0不证明实体包含或强度，拓扑连通不证明目标形状。详细字段需要时查
  `verb_help('geo_check_interfaces')`与`verb_help('test_controls')`，不另造重复合同说明。
- **rig/动画**：区分driver→binding/evaluation→最终driven geometry。选相隔帧和关键转折检查
  最终部件位置/姿态，不拿骨架bbox、首尾归零代替中间动作；纯control-shape不强制变形。
- **simulation**：核对实际时序、缓存/求解结果与承诺现象；外部文件、Python、solver状态
  不能当成可恢复数值控制实验，当前仅只读取证并披露缺失测试。
- **Solaris/渲染**：核对最终prim/material绑定、灯光/相机/产品与真实产物。SOP预览不能证明
  Karma/材质交付；若授权范围或工具不足则unverified，不擅自搭正式渲染管线。
- **视觉**：整体图看轮廓，局部关系需可辨认视角；先列可见异常，再对照目标。文件/像素成功
  不等于形态正确。参数实验可能各自自动取景，先比较camera/framing，不能把缩放差当效果
  或像素差证据；动画A/B需同一framing_frame。没有可用图就写“视觉未验证”。

当前受控测试支持有界原生无外部副作用SOP，其他任务仍可只读评审。普通测试/数据失败与
不支持、图像不可用分开。同一边界两次失败就查准确接口或结束该项，不陷入探测循环。
评审有10分钟上限；未覆盖项如实交代，不为赶时间伪造pass或扩展任务。

## 一次汇总

给出 `pass / fail / unverified` 总结及范围；核心承诺缺证据不能判pass。只列有实际影响的
问题，每项写“用户要求→实际证据（节点/参数/帧/图片）→影响→建议”；不在评审中修模。
另附紧凑的已测控制/关系、恢复结果、未测项与视觉边界。不要复述完整节点表、历史回包或
给出无来源的艺术/制造认证。报告后评审权限撤销，作者接收一次结果即可。
