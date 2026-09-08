# 按需资产复核设计

实现：[Host review](../src/review.ts)、[Bridge review](../houdini/python3.11libs/dsh_review.py)、
[review skill](../skills/houdini-asset-review/SKILL.md)。普通建模不默认委派；
仅用户要求或具体疑点需要第二视角时发起。评审完成不是资产通过。

## 调用与材料

houdini_exec(review={parent,output,controller?})与code/allow_raw/review_test互斥，
绑定本任务拥有的SOP parent及直属output/controller。作者等待一次前台结果，结束后处理确认的问题。
foreign可读，不因评审而取得常规写权限。

Host按消息source.kind=user转交原始用户文本/图片、关联成功澄清问答和来源引用；
注入消息、自动续接和作者自述不作用户要求，缺少可靠用户来源时拒绝启动而不靠文本前缀猜测。
另转交至多8条/16K字符可信历史工具事实；
stdout自述不能伪造operation-evidence。事实带case/值/范围/时间/指纹，不是作者自评，
也不能证明后续修改后的当前依赖。Bridge begin在同一主线程项里获取实际几何、健康、控制和部件摘要，
明确截断与实验适用性。已有图片仍需实际读取；skill直接内联，不重复加载。

## 权限与生命周期

唯一child绑定短期token、作者、HIP/节点identity、基准网络参数与frame。
允许query及受控review_test，不允许任意exec修改、保存、删除、job或再委派。
作者修改在评审期间等待；基准改变、恢复失败、取消、异常或结束均停止并撤销租约。
Host与Bridge均限制四分钟；工具目标六次以内，全评审最多三个测试case。
权限不能由模型传owner/token字段自授，不能用于模块作者协作。

## 实验与恢复

review_test接受tests、可选views/interfaces/topology/domain。无expectations只说明响应/未响应，
保持语义unverified。views最多两个方向，含基准最多八图；空tests可仅取基准。
test_support不支持时只读，不转换几何迎合支持策略。测试白名单不限制普通作者建模。

支持的case在同一主线程中完成临时设参、cook、测量/截图和恢复，校验参数、keys、frame及完整bgeo；
截图用户状态恢复失败阻断下一case。任意VEX/Python/File/Solver等外部副作用不属于这个安全实验能力。
不同参数状态的预览可能重新取景，不能默认当作固定相机A/B。控制数值恢复不是所有外部状态恢复。

结果应包含可行动问题、检查范围、未测/unsupported及真实case恢复状态。
没有问题只报告限定范围未发现阻断项；少数样本不能整表pass。
数值和视觉检查的分层保证见[执行契约](execution-contract.md)。

## 维护入口

[review-state](../tools/tests/review-state.test.mjs)验证Host生命周期、材料、互斥和撤销；
[review-http](../tools/tests/dsh-review-http.test.py)与[review-service](../tools/tests/dsh-review-service.test.py)
覆盖传输、主线程、scope/预算/恢复边界。确定性child替身不证明真实模型审查收益。
独立设计协作只按[SOP协议](../skills/houdini-sop-workflow/references/module-design-collaboration.md)
返回候选设计，再由单作者执行，不复用review租约。
