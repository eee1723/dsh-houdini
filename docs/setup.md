# dsh-houdini 安装、更新与开发

Windows x64受管安装把插件、Node、DSH和完整依赖作为一个签名发行单元。普通用户不运行npm/build，不单独升级DSH。
源码checkout、预构建包、已选版本与正在运行的版本分别判断。发布前尚欠的真实用户路径见[交接](handoff.md#h-01-部署更新改造与完整运行态验收)。

## 普通安装

1. 从[正式发行页](https://github.com/eee1723/dsh-houdini/releases/latest)下载完整 `dsh-houdini-版本-offline.zip`，解压后双击 `Install.cmd`。
2. 安装器按用户权限注册H21/H22菜单，不修改系统Node、Python或全局PATH。
3. 完整重开Houdini，选择 **DSH-Houdini → Open Workspace**。后台校验并准备隔离profile后启动配套DSH。
4. 首次在DSH页面配置模型/API凭据。受管安装不自动迁移或清空既有 `~/.dsh`，此前独立DSH原样保留。

完整包包含运行依赖，可离线安装；模型服务仍依赖用户配置与网络。
轻量 `dsh-houdini-installer.zip`，或clone/源码ZIP中的Install.cmd，只部署管理器；在面板检查正式Release并安装完整组合。
仓库尚无正式Release或公钥未配置时，管理器如实报告，不将main或测试候选伪装成可安装正式版。
GitHub自动生成的Source code.zip不是完整运行包；源码构建是下文的显式开发路径。

### 注册位置与引导修复

默认安装根为 `%LOCALAPPDATA%/DSH-Houdini`，偏好目录使用Windows真实Documents文件夹，支持重定向/OneDrive。
默认注册21.0和22.0；支持指定偏好目录与安装根：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PrintOnly
powershell -NoProfile -ExecutionPolicy Bypass -File installer/install.ps1 -PackagesDir 'D:/HoudiniPrefs/packages' -Root 'D:/DSH-Houdini'
```

`HOUDINI_USER_PREF_DIR`优先，必须含`__HVER__`占位符，否则Houdini会忽略它；显式目录可用-PackagesDir。ExecutionPolicy只作用于该次引导进程，不永久改系统策略；
企业策略禁止脚本时遵循管理员要求，不关闭安全功能绕过。此前package原子备份到安装根的package-backups。
重复运行可信安装器可修复损坏管理器：复制到新目录再切换注册，不覆盖已加载模块。
完整包在检测到标准Houdini安装中的内置Python时直接暂存；未检测到时，在面板选择原解压目录的release.json。
已完成安装不依赖原下载解压目录，不要求系统Git、Node、额外Python或管理员权限。
启动桩按[SideFX脚本位置](https://www.sidefx.com/docs/houdini/hom/locations)分别生成在python3.11libs/pythonrc.py和python3.13libs/pythonrc.py，共享同一份Python模块实现。

## Version & Diagnostics

受管模式顶部两列分别是 **This Houdini process** 与 **Next Houdini start**，不是两个独立更新的产品。
源码和受管安装共用此主面板及 **Advanced runtime diagnostics** 入口；面板明确显示安装模式和路径。
源码模式右列为 **Source on disk**，只展示磁盘package版本，当前运行态标为未核验；实际加载身份在高级诊断中检查。
源码模式提供正式发行页、源码版本刷新和Git/npm更新说明，不创建受管安装状态，安装修复/回退/取消切换按钮不可用。
源码模式可直接打开高级诊断来检查尚未启动的运行时；以下操作表描述受管模式。

| 操作 | 行为 |
|---|---|
| Check for a release / Install | 只查明确发布的稳定Release；在线安装要求不可变Release、受信签名与完整资产 |
| Install local package | 选择与ZIP、release.sig.json同目录的release.json；离线也要求受信签名，没有忽略签名按钮 |
| Repair current version | 重新下载并暂存当前版本的完整包，不升级DSH/latest、不覆盖损坏目录；离线时选择同版本地包 |
| Verify installation | 检查全量文件哈希、缺失/多余文件、包版本和依赖锁；通过不证明live加载 |
| Prepare rollback | 下次启动使用上一套程序及它的独立数据，新版数据保留但不自动合并 |
| Cancel pending change | 取消下次切换，不删除任何版本、数据或下载 |
| Advanced runtime diagnostics | 运行态加载后才可进入Host/Bridge诊断；repair仍受活动任务保护 |

网络失败/限流不冒充已是最新。Draft、prerelease、push与tag不进入默认更新通道；目前没有面向普通用户的预览通道。
后台下载/解压可取消；提交pending是原子步骤，提交后使用Cancel pending change取消下一次切换。
独立管理器不依赖Node、DSH或插件lib，缺依赖时仍可打开。

## 正式发行与受管安装合同

下载 → 签名/资产摘要验证 → 新目录安全解压 → 全量文件检查 → 原子记录pending。
Houdini启动时只读取小型状态并固定本进程选择，不在GUI线程执行哈希、网络或进程探测。
首次Open Workspace在worker里校验/准备，主线程只接收状态并加载HOM模块；安装完成后必须完整重启，不能热切换已打开的Houdini。

新版首次启用从当前受管版本复制独立DSH数据快照，不跟随依赖junction，再由发行包的DSH API初始化profile并检查Node、DSH和插件。
用户自建preset随数据保留，只重新生成产品拥有的houdini/houdini-dev。state.json损坏时不能猜测当前版本；保留旧目录恢复数据，选择新安装根，不把重装程序当作状态恢复。
失败保留当前选择及旧数据；未完成快照另存，重试重新采集仍在用的旧版数据。
回退恢复旧版保留的数据，新版会话仍在新版data目录；这不是数据格式转换，也不承诺跨版本自动合并。
预检后选择current不等于前端/Bridge/模型已验证，运行身份仍需独立检查。

同时只允许一个Houdini进程使用受管DSH工作区；其他实例可管理/暂存更新，待前一实例退出后再启动工作区。
动态loopback端口隔离独立DSH/开发Bridge，Windows Job Object只管理自有Node进程树，退出时收回，不按端口停止外部服务。
WebView使用独立的内存浏览器profile，不争用Houdini默认磁盘profile或其他版本的浏览器锁；浏览器cookie/缓存随窗口生命周期结束，DSH会话与配置仍在受管data目录持久化。
H22.0.368的Qt helper依赖启动目录查找原生DLL；使用Houdini常规快捷方式或以安装bin为工作目录启动。不要把Houdini进程cwd改成源码/安装暂存目录；DSH工作区仍独立跟随HIP目录，插件不改Houdini的cwd或关闭浏览器沙箱。
安装器不删除旧版本、旧数据、HIP或工作区。清理下载、暂存及旧版本须另行确认。

| 安装根下的位置 | 职责 |
|---|---|
| bootstrap/内容标识 | 独立菜单、管理器、公钥；损坏后旁路重装 |
| releases/版本-摘要-实例 | 不可变签名元数据、全量文件清单、Node及固定依赖 |
| data/安装实例 | 对应版本的DSH配置、凭据、会话、附件与profile |
| runtime/进程实例 | 端口/路径上下文、前端日志、实际运行标记 |
| downloads、staging | 下载与中断暂存，不作为运行版本 |
| state.json | current/previous/pending选择，不证明服务在线 |

## 工作区使用

先保存HIP，再Open Workspace：HIP父目录成为DSH workspace；切换HIP后再点一次切换边界。
未保存场景使用仓库外中立scratch，源码与发行目录不是任务工作区。新会话选择「Houdini模式」，开发插件选择「Houdini开发模式」。
首次请求houdini_query调用scene_info并列出/obj节点，确认工具、Trace和合同握手。
图像使用DSH原生附件，不安装额外视觉工具；没有成功语义识图仍需报告视觉未验证。
视频教程等可选能力的FFmpeg和云服务凭据不属于核心离线运行依赖，仍需按对应skill准备；Houdini和模型服务授权不随插件分发。

## 显式源码开发安装

此路径保留供开发者使用，不是正式发行安装。需要Node/npm、Python或Houdini内置Python；clone/pull时需要Git。

```powershell
git clone https://github.com/eee1723/dsh-houdini.git
Set-Location dsh-houdini
npm install
npm run build
python houdini/install.py
```

`houdini/install.py --print`只预览package；`--skip-dsh-profile`只注册源码package。
lib和node_modules不提交，生成区不手改；更新源码执行git pull --ff-only、npm install、npm run build。
源码安装仍使用系统Node与项目npx缓存，只锁DSH根包，不具有完整受管发行保证。共用面板不拉main、不原地构建。
开发者命令行构建仍是明确路径，受管界面不提供构建源码或启用未发布checkout按钮。

默认安装/启动/修复共用[兼容清单](../dsh-runtime-compatibility.json)的preferred精确DSH。
隔离资格验证可设置 `DSH_HOUDINI_DSH_SPEC=@deepseek-ai/dsh@精确版本` 或 `DSH_HOUDINI_DSH_BIN`；
受管模式忽略这些开发覆盖，只用签名组合。源码Host/Bridge/helper/preset更新可用Advanced diagnostics中的Repair and restart runtime，
WebView、菜单和package变更完整重开Houdini。构建通过、诊断存在和live加载分别验收。

## 卸载与保留数据

受管安装：关闭使用它的Houdini，移除目标偏好目录的packages/dsh-houdini.json；需要恢复此前注册时使用package-backups对应备份。
数据与版本保留在安装根，删除它们须单独确认并备份，不处理用户HIP、工作区、独立DSH或其他插件。
源码安装：通过所用精确DSH的官方plugin命令移除web profile中的dsh-houdini，并移除Houdini package，不连带删除共享内容。

发行维护和验证命令见[开发维护](development.md#发行操作与信任配置)，兼容边界见[兼容设计](dsh-update-compatibility.md)。
