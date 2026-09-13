# 多实例与任务恢复

本页是多Houdini执行端的唯一长期设计/运维说明；代码地图见[架构](architecture.md)，活动缺口只在
[交接](handoff.md)维护。默认启动、发行资格与数据迁移仍遵循[安装合同](setup.md)和[兼容门](dsh-update-compatibility.md)。

## 当前可用范围

源码已集成**显式共享模式**：一个DSH Host提供统一会话/账号入口，多个Houdini使用各自Bridge与进程身份；
每个任务只能绑定一个执行端，每个执行端只能有一个场景作者。H21.0.440/H22.0.368的隔离双实例、真实DSH
认证/浏览器选择/预留/落盘具有测试入口；不是任意DSH版本、任意平台或已发布安装的保证。

默认Open Workspace仍使用原单实例路线。受管安装保留安装级runtime锁，不能靠删锁或手改签名发行包启用。
源码集成不证明用户当前进程已加载；菜单/客户端更改需要在保存并结束现有任务后重新打开对应环境。

不包含：自动启动/接管共享Host、正常退出时的任务选择对话框、自动重开Houdini、跨进程节点ownership恢复、
未知操作重放、共享模式的跨路径Save As预留转移，以及GUI/外部程序的全部写入拦截。

## 身份与职责

| 标识/组件 | 职责 | 不能证明 |
|---|---|---|
| DSH session ID | 持久任务及历史；复用原生会话恢复 | HIP内容或现场状态已经恢复 |
| executor ID | Houdini进程随机身份，进程内reload保持，重开产生新值 | 节点编辑权限、密码或秘密认证 |
| Bridge runtime ID | 执行代际、一次入场票及回执范围 | 新进程可以继承旧请求 |
| registration ID | 用户选择的登记版本，防过期选择 | 记录对应进程仍在线 |
| HIP规范路径/文件身份 | 协作写入锁对象；Windows统一原生文件标识 | 所有GUI保存或外部写入都受保护 |
| 地址/端口 | 找到服务 | 找到的就是原任务目标或可以强杀的进程 |

登记仅是发现线索，列表返回unverified。所有现场路由、job控制与读图携带目标身份头；Bridge在派发前拒绝
错目标，Host核对版本/代际。没有首次绑定时不选择“第一个/唯一/最近”的实例，也不读取其他实例的环境现场。
此机制防正常任务串线，不是针对恶意本机Python或篡改本机安装的安全沙箱。

## 源码共享模式的启用顺序

先结束并保存原单实例任务。不要让两个Host同时使用同一个DSH_HOME；现有数据只由一个Host拥有，
本功能不复制、合并或迁移账号/会话。使用已按安装合同配置、插件解析到当前源码的web profile。
选择与兼容清单一致的精确DSH CLI，不能用一个旧profile去尝试未知最新版本。

1. 在独立终端启动共享DSH，而非由某个Houdini创建它。设置唯一的登记目录和现有DSH_HOME：

   ```powershell
   # 路径均替换为本机已确认位置；不要使用其他正在运行Host的数据目录。
   $env:DSH_HOME='D:/DSH/user-data'
   $env:DSH_HOUDINI_EXECUTOR_REGISTRY='D:/DSH/houdini-executors'
   node 'D:/runtime/node_modules/@deepseek-ai/dsh/lib/bin.js' web --patch 'D:/plugins/dsh-houdini/shared-host.cordis.yml' --port 3081 --no-open
   ```

   若端口已占用，先确认所属服务，或为新Host明确选择另一个端口；不能默认结束其他任务。
   该overlay在Host层挂载一次dsh-houdini/executor-host；houdini/houdini-dev preset只消费同一服务。
   没有配置登记目录时仍用原单实例路线，不隐式新建共享模式。

2. 在各个新Houdini实例中打开/保存各自HIP，使用候选菜单 **Register Shared Executor**，填写同一登记目录。
   先采集主线程实际HIP/版本，直接绑定动态Bridge端口，再由worker发布登记；不先探测端口后关闭重绑。
   已拥有单实例DSH前端的Houdini拒绝直接转换；不要趁agent短暂没调用HOM时切换工作模式。

3. 在共享DSH打开对应Houdini任务，展开输入框上方的 **Houdini执行端**，核对版本、HIP和占用状态，选择并确认。
   该入口必须在新任务第一条消息前可见；它不是模型工具，也不使用浏览器直连Bridge。

4. Host检查空闲任务、登记版本和用户看到的expectedHip。Bridge重新捕获当前HIP，worker取得该task的写入预留；
   然后DSH追加原生绑定消息并等待sessions.flush成功。无持久化后端、取消或落盘失败不派发现场操作。
   预留成功但后续绑定失败时保留预留，允许原任务核对后重试，不自动让另一个作者接管。

5. 每次工具从自己的持久绑定解析目标，在该次调用内固定Bridge；代码、返回图片及job控制不使用可变全局目标。
   配置与共享Host不一致、服务卸载、目标断联或代际变化时拒绝，不回退到固定端口或另一执行端。

## 写入、保存与Repair

共享修改exec在HOM执行前核对task及当前HIP。只读检查不授予写入权限，节点仍需符合原session创建identity规则。
同HIP通过规范路径和文件身份协作互斥，包含大小写、符号链接和硬链接的适用反例；OS租约随所属进程退出释放。
这是参与协议的执行端之间的锁，不阻止用户在其他软件写同一文件；外部替换、共享文件系统及GUI写入另验。

共享模式不同目标路径的scene_save_as在创建文件前拒绝，不能以普通Save As授权替代尚未实现的预留转移。
需要另一个工程时，先按明确的工程交接方案处理，不在同一exec中绕过raw load/clear/setName。

**Repair This Shared Executor**只重载本Houdini Bridge，并重新发布运行代际；不结束共享DSH或另一个Houdini。
活动请求/jobs/队列阻止重载。同进程helper重载保留精确节点identity登记，新进程不继承它。
普通单实例Repair在共享实例上拒绝并指向该入口，不能将“修复一端”变成“重启全部任务”。

共享Host层服务只挂载一次。卸载一个preset不会关闭它；卸载Host服务撤销其旧Bridge的网络请求，重新加载后
消费者重新获取服务。但网络取消不证明已入场的HOM未执行，旧回执仍按[执行契约](execution-contract.md)处理。

## 退出与恢复边界

独立终端启动的共享DSH不依赖某个Houdini的进程生命周期；正常退出登记为disconnected，崩溃可能留下陈旧记录。
锁释放不等于任务完成，也不授权把旧任务改绑到新进程。心跳超时只表示失联，不能据此杀Houdini或重发代码。

恢复目标顺序为：保留任务历史→核对检查点和依赖→确认新执行端→恢复可信节点身份→核对未知请求→明确授权续跑。
此闭环尚未实现。当前已有绑定不允许在选择面板直接换目标；手动新建任务也不是恢复授权。
后续退出选项、失败熔断、有限自动重开均依赖该闭环；不把DSH会话resume称为Houdini工程恢复。

## 维护与验证入口

- [登记/写锁](../houdini/python3.11libs/dsh_executor_registry.py)、[Houdini菜单入口](../houdini/python3.11libs/dsh_shared_executor.py)。
- [Host生命周期](../src/executor-host.ts)、[任务路由](../src/executor-routing.ts)、[Remote选择](../src/executor-controller.ts)、[持久绑定](../src/execution-state.ts)。
- [双实例HOM](../tools/tests/dsh-multi-executor.test.py)：H21/H21、H22/H22、H21/H22；身份/写锁/单端Repair/单进程退出。
- [共享Host路由](../tools/tests/executor-routing.test.mjs)、[绑定落盘](../tools/tests/executor-binding.test.mjs)、[面板行为](../tools/tests/executor-picker.test.mjs)。
- [实际DSH与浏览器](../tools/tests/dsh-shared-host-e2e.test.py)：由[准备器](../tools/tests/prepare-shared-host-fixture.mjs)创建无账号数据fixture，
  验认证、选择、真实Houdini领取和实际flush；精确参数和依赖见[开发规范](development.md)。

Qt真实菜单、正常退出/崩溃恢复、已加载发行版和未见模型任务分别验收。测试、源码、签名包、正式Release及live
加载状态不能互相替代；未通过冻结基准门时保留失败，不自动修改基线或评测协议。

设计依据：[DSH agent作用域/恢复](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/agent/README.md)、
[DSH持久会话](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/session/README.md)、
[Houdini服务生命周期](https://www.sidefx.com/docs/houdini/tops/services.html)、
[HIP保存边界](https://www.sidefx.com/docs/houdini/hom/hou/hipFile.html)。这些支持职责分离，不构成自动续跑的官方保证。
