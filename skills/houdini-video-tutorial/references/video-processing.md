# 视频处理运行与证据契约

## 范围与依赖

Applies when：用户提供可读的本地视频或分离音视频，允许抽取音频/画面，并在云转录时授权所选服务。
Do not use when：需要绕过平台访问控制、把原视频上传当作音频转录、或仅靠 ASR 证明视觉操作。
纯静音视频仍可 `prepare` / `frames`，`transcribe` 明确拒绝，`export` 不冒充转录完成。

使用当前Houdini安装内的普通Python 3.11+标准库进程与插件版本私有的FFmpeg/ffprobe，无需Whisper、PyTorch或第三方Python包。Host从HFS定位当前Houdini Python，不用全局PATH上的python；旧默认`python`/`python.exe`也按自动选择处理。
脚本在本机文件/进程工具中执行，不经 `houdini_exec`，不导入 `hou`。
FFmpeg/ffprobe默认位于插件的`runtime/video/ffmpeg/bin/`，不自动回退到全局PATH。可传`--ffmpeg`/`--ffprobe`绝对路径；找不到依赖时报告缺失。正式安装使用Version & Updates的同版修复恢复整份版本；源码开发运行`python tools/prepare-video-runtime.py`准备本目录锁定媒体工具，不擅自改全局环境。
缩略图标签需要 FFmpeg 的 drawtext/scale/pad/tile 滤镜和可用字体；默认查找系统常见字体，
找不到时传 `--font-file` 的绝对 TTF 路径，不自动安装字体。原分辨率证据不加文字或裁切。

正常插件入口使用 `video_models` / `video_process` / `video_transcribe`：根级「教程视频」设置只存默认 provider/model/Python，
Host 从 DSH 同一模型路由和凭据服务解析账户，将密钥仅传入子进程环境；Agent 看不到密钥，Python
继续维护唯一的 manifest/attempt/outcome，不另建 Host 转录状态账本。保存设置与本机依赖检查不会上传媒体。
任务内自动运行时从所选Houdini健康信息取得实际Python、版本与身份，不受共享Host父环境HFS影响；显式Python完整路径优先。
没有任务上下文的设置页检查只描述Host启动环境，不能证明选中任务的运行时。旧Bridge缺少运行时事实时如实诊断，不猜另一版本。
本地处理优先用`video_process`，options使用对应CLI的下划线参数名：`review`的`video/output/start/duration/interval`，
`read-index`的`index/module/section/offset/limit/max_chars`，`query-notes`的`index/subject/field/view`等；路径必须绝对。
Host只调用随包离线命令和私有媒体工具；读取直接返回原JSON，写入限定当前DSH策略允许的新output目录。它不经shell，不获取凭据、不调用云、不执行HOM；
实际退出码、错误和部分进度分别返回，失败不自动重试，不修改ACL或放宽策略。原CLI继续维护全部hash/格式/索引与文件，不另建记录。
独立CLI所有ingest/prepare/scan/export等命令必须使用`video_models.runtime`返回的`python`和`script`绝对路径；不以裸`python`从全局PATH启动。CLI默认从同一插件根定位私有FFmpeg，显式媒体工具覆盖仍使用绝对路径。
设置完整读取已配置供应商，转录模型下拉来自所选供应商当前模型目录；目录不认证转录协议。语音用途模型未进入聊天目录时，通过「其他转录模型」填准确ID，不把它注册成对话模型。
支持显式OpenAI兼容`/audio/transcriptions`，以及`qwen3-asr-flash`及日期快照的`/chat/completions + input_audio`协议。后者从同一已校验WAV bytes构造Data URL、`stream=false`、自动识别语种、关闭逆文本规范化以保留原话；要求完整`finish_reason=stop`结果。单片不超过5分钟和10MB Base64，超限在提交前拒绝。MiMo、实时语音及云厂商异步Filetrans仍未接入。服务的`api/baseURL/apiKeyEnv`配置和凭据仍在DSH「模型」维护。

`qwen-audio-3.0-asr-flash`与`qwen-audio-3.1-asr-flash`使用`dashscope-asr`原生同步协议：同域名`/api/v1/services/aigc/multimodal-generation/generation`、`input.messages`、WAV/16kHz参数及`X-DashScope-SSE: disable`。Host只从供应商明确的`/compatible-mode/v1`或`/api/v1`基址映射该路径，不猜其它网关，不切换模型或域名。完整正文读取`output.text`，缺累计正文不以当前句代替全片。成功原始响应、usage与request_id保存在唯一outcome，原生句词时间从音频毫秒转为秒，再加原片起点；只导出稳定且界内的词。句文本/词文本与累计正文分别核覆盖，不以收到时间字段就宣称全文对齐或准确。

3.1可显式传`speaker_diarization=true`取得提供方的句数组；不会替用户隐式开启该选项。原生词表用`vocabulary:[{word:"Houdini",weight:3}]`，权重按官方为1..5或50，未知节点名不能强推成“纠错”。选项与模型/endpoint固定进任务配置，续跑不得混配。接口见[原生HTTP参考](https://help.aliyun.com/en/model-studio/fun-asr-flash-recorded-speech-recognition-http-api)。

独立 CLI 保留 SiliconFlow 默认值：密钥从进程环境变量 `SILICONFLOW_API_KEY` 获取；Windows 也支持同名用户环境变量。
`transcribe --endpoint <完整转录URL> --protocol openai-transcriptions|qwen-chat-asr|dashscope-asr --key-env <环境变量名>`可指定路由，endpoint/model/非默认protocol一起固定到任务。省略protocol的既有任务仍按兼容audio/transcriptions读取，不静默重写历史。
不接受命令行密钥，不打印密钥、鉴权头或原始异常正文。Host 不把当前聊天模型自动替换成转录模型。

官方接口：[Audio Transcriptions](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post)。
已核接口为 `POST https://api.siliconflow.cn/v1/audio/transcriptions`，multipart 的 `model` 和音频 `file`，
响应契约只依赖 `text`。请求限制按官方为单文件不超过 1 小时、50MB；本脚本使用更短音频切片。
Claim：该契约没有承诺逐句时间戳，所以本工具只标分片范围。边界：其他模型/接口将来若提供对齐，
须另行验证后接入，不能把本工具时间标注当作模型对齐。验证：响应字段校验与覆盖测试。
模型列表和价格需调用前核实，不固化“永久免费”或静默换模型。
千问官方接口：[Qwen-ASR API](https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference)。`qwen3-asr-flash`不返回句级/词级时间戳，本工具同样只标音频切片范围；官方Filetrans时间戳不能套用到Chat响应。普通百炼地址与地域配置见[安装设置](../../../docs/setup.md#教程视频与转录设置)，Token Plan不代替语音API。开源`Qwen/Qwen3-ASR-1.7B`须由实际服务提供方部署并公布兼容接口与准确ID，不假设硅基流动默认提供该模型。

## 最短执行路径

以下在 PowerShell 中执行；将路径替换为当前任务明确的绝对路径，`$videoScript` 指随包资源。
`prepare` 无网络写入；所有目录参数要求绝对路径且不能位于本插件目录。
新任务的派生分析资料统一进入任务根的 `dsh-analysis/<tutorial>/`，下载与合并后的源媒体
进入 `dsh-reference/downloaded/<tutorial>/`；子目录按步骤分工，不要求子目录再次带 `dsh-`。
有已命名 HIP 时读取 `project_layout.directories.analysis/reference_downloaded`；只做离线解析时
用明确任务根。脚本尊重显式 `--output` / `--work`，不改写旧目录或自动搬移用户资料。

```powershell
# 从 video_models.runtime 的真实结果填写，不照抄或猜测安装目录。
$videoPython = '<runtime.python 返回的绝对路径>'
$videoScript = '<runtime.script 返回的绝对路径>'
# 目录或分离轨输入：只在下载完成后导入，不修改原文件。
& $videoPython $videoScript ingest --input 'D:/task/downloaded-tutorial' --output 'D:/task/dsh-reference/downloaded/tutorial'
# 单个已含音轨的视频可直接 prepare；合并产物为 dsh-reference/downloaded/tutorial/media.mp4。
& $videoPython $videoScript prepare --video 'D:/task/tutorial.mp4' --output 'D:/task/dsh-analysis/tutorial/video-sample' --start 0 --duration 90
& $videoPython $videoScript transcribe --work 'D:/task/dsh-analysis/tutorial/video-sample' --model 'qwen3-asr-flash' --endpoint 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions' --protocol qwen-chat-asr --key-env DASHSCOPE_API_KEY --allow-upload --max-chunks 4
& $videoPython $videoScript export --work 'D:/task/dsh-analysis/tutorial/video-sample' --output 'D:/task/dsh-analysis/tutorial/sample-export'
& $videoPython $videoScript frames --work 'D:/task/dsh-analysis/tutorial/video-sample' --output 'D:/task/dsh-analysis/tutorial/sample-frames' --times 15 45 75
& $videoPython $videoScript scan --video 'D:/task/tutorial.mp4' --output 'D:/task/dsh-analysis/tutorial/overview' --interval 30
& $videoPython $videoScript review --video 'D:/task/tutorial.mp4' --output 'D:/task/dsh-analysis/tutorial/detail' --start 120 --duration 12 --interval 1
& $videoPython $videoScript changes --frames-dir 'D:/task/dsh-analysis/tutorial/overview' --output 'D:/task/dsh-analysis/tutorial/change-candidates'
& $videoPython $videoScript context --frames-dir 'D:/task/dsh-analysis/tutorial/detail' --transcript 'D:/task/dsh-analysis/tutorial/sample-export/transcript.json' --start 120 --end 132 --output 'D:/task/dsh-analysis/tutorial/evidence'
& $videoPython $videoScript check-notes --context 'D:/task/dsh-analysis/tutorial/evidence/context.json' --notes 'D:/task/dsh-analysis/tutorial/notes.json' --output 'D:/task/dsh-analysis/tutorial/checked-notes'
```

在 DSH 中，prepare 后优先使用 `video_transcribe({work:"D:/task/dsh-analysis/tutorial/video-sample",allow_upload:true,max_chunks:2})`。
省略 provider/model 时使用「教程视频」的选择；显式参数可覆盖本次调用，但不能更换已有任务固定的模型/endpoint。
`video_models` 返回配置与凭据是否存在、协议范围和诊断，不上传音频；Python/FFmpeg/ffprobe 检查入口在设置页。

`ingest` 支持 `--input` 目录，或明确 `--video` 与可选 `--audio`。按 ffprobe 实际流类型找唯一配对，
不依赖扩展名；多个候选明确要求指定路径。H.264/AAC等MP4支持的编码使用 stream-copy，不重编码改变画面。
源文件变化、截断或流不匹配返回失败，保留已有诊断产物，不发布成功清单；残留 `.aria2` 只作下载线索，
不单独判定媒体损坏。成功目录含 `media.mp4` 和 `source-manifest.json`，记录原路径/hash/流与合并结果。
两轨必须来自同一视频并有可对应的时间轴；时长相同不自动证明语义配对。未知来源先核对，不能靠文件名推断。

`prepare` 默认每片 30 秒、重叠 1 秒；`--duration` 必填，限制默认全片处理。
优先准备完整授权范围并先提交少量片，成功后在同一任务继续；局部问题才单独准备短段。不要重新提交成功音频来取文本。
`transcribe --max-chunks` 限制本次网络请求总数（包括重试），CLI与Host均缺省100，最大100；少量试转录应明确使用更小预算。
`--concurrency`限制同时在途请求，范围1..64，CLI与Host均默认64；`--requests-per-second`独立控制启动节奏，均默认8。429、5xx、实际传输断联或超时、临时DNS查询失败会立即暂停新派发；保存这一轮全部在途结果后，并发从64降32再降16，在本次预算内继续尚未尝试的新片。显式选择其它并发时，只向更低的32/16档降级；16及以下再次失败则停止。认证、证书/地址/永久DNS错误、模型/响应语义错误或本地文件错误直接停止，不降级掩盖；未分类的OS错误不推断成并发问题。已失败/未知片即使有本次重试预算也不会在降级阶段自动再发；所有结果按原片与尝试序号保留，最终仍报告本次失败。报告含实际submitted/completed/succeeded/failed/peak_inflight、final_concurrency、concurrency_transitions和逐项failure_details，不能把上限当实际峰值。强制取消仍可能留下已计费的unknown。
可用 `--chunks 00002 00005` 只处理指定 manifest 片 ID；实际按源时间顺序执行，不重传成功片。
未知/重复 ID、无效预算在读取凭据和发请求前拒绝。同一任务第一次请求固定模型；改模型应明确说明并
新建任务，不混合来源。已有尝试记录却丢失 asr-config.json 时拒绝猜补其模型身份。
应从已知备份恢复原配置；无法恢复时，只能另获授权后建新任务，保留原历史，不删除 attempt/outcome 解锁重发。

用户批准上传是运行 `--allow-upload` 的前提，标志本身不能制造授权。
确认价格后才提交；无余额、无模型或不支持的响应停止本次批处理。429、5xx或传输断联/超时仅按上述调度降级处理，不后台重试失败片。
使用相同命令可继续尚未尝试的片；失败/未知片默认记为 deferred，不重发，也不阻断其他未提交片。
只有用户已有授权覆盖可能的重复处理/费用才用 `--retry-failed`，不为预算内已授权重试反复询问；`--max-retries N` 是本次获授权的重试请求数，
不是历史尝试上限。有 retry-failed 时默认 1，否则 0；显式非零预算必须同时有 retry-failed，最大 100，
仍受 max-chunks 限制。一次调用每片最多提交一次，不在同批内自动再试；降级只继续尚未尝试的新片。
需要重试指定片时组合 `--chunks 00002 --retry-failed --max-retries 1`；排查后另次获准可继续第 3 次及以后，
按数值序号追加 attempt/outcome，旧日志不改写，成功片永不重发。
结果分别返回本次 submitted/retried/retry_budget、全任务 remaining_unsubmitted、失败/未知 deferred 列表与
合计 remaining；选择或延后不等于完成，export 仍保留缺失片并报告 partial。无可提交片时不读取凭据。
中途失败报告具体片 ID 及本批已成功数；先前成功和失败/未知日志保留，续跑仍按上述范围与授权预算选择。
每次提交先读取实际音频 bytes 并与 manifest hash 核对，再写 attempt、把同一份 bytes 交给网络；
本地音频被改写或无法读取时不创建该片 attempt，不把零网络失败记成可能收费的 unknown。已提交的片仍按回执处理。

运行中的工作目录持有排他 `.lock`；进程被强杀可能遗留。不要抢锁或删任务目录。
确认没有任务进程后，才人工移除该精确锁文件；保留 attempt 记录，仍按未知结果处理。
文件被破坏或 hash 不匹配时拒绝续跑，不把损坏当“缺失可重做”，不覆盖原证据。

`frames` 每次最多 24 个明确秒数，拒绝超出视频时长和重复时间；输出是原尺寸单帧与来源索引。
`scan` 支持 `--video` 或 `--work` 二选一，不必先切音频或调用云服务。默认全片每 30 秒取一帧，
加一个近片尾样本（结束前至多 1 秒，不声称是最后一帧）；可用 `--start/--duration` 限定范围。
总量上限 240 帧，超限要求增大间隔或缩小范围，不静默截断，也不静默改变用户间隔。
`review` 同样支持直接视频或已准备工作目录，`--duration` 必填，默认每秒一帧，最多 48 帧，
范围结束点不包含在采样内。分数秒可用，例如 `--interval 0.5`，不是固定只能每秒查看。

`scan/review` 产出原图、480 像素宽带时间标签的缩略图、每页至多 12 张的 PNG 联系表与 `index.md`。
索引列出请求时间和实际时间，可打开原图；Markdown 使用绝对本地文件链接，整个目录移动后需重新生成索引。
原图不加标签，不按图像相似度删除样本。相同帧可能被相邻请求重复命中，PTS 会如实记录。
先粗定位章节，再围绕端口/参数变化局部重看。脚本支持像素变化候选，不选“语义关键帧”、不做 OCR 或图像理解。
须用目标宿主实际提供的语义识图工具打开帧；没有该工具时标画面未验证。

### 变化候选定位

`changes` 读取已经完成的 schema-2 `frames.json`，校验原视频、所有原图 hash、实际 PTS、
时间顺序和统一尺寸；不使用带时间标签的缩略图作比较。旧时间索引、损坏文件或部分抽帧任务拒绝。
输入需有 2..240 张按实际时间排序的图。相同 PTS 的相同图保留记录，不生成零时长事件；
同一 PTS 对应不同图则视为证据冲突。比较完全本地运行，不需要密钥，不上传图像。

默认比较全画面。支持重复传入 `--region name:x:y:width:height`，使用左上角原点、0..1 归一化坐标，
最多 8 个名称唯一且不越界的矩形。显式提供区域时只比较这些区域，不暗中加回全图。
区域名称只是调用者标注，不证明脚本识别了窗口含义；应查看视频布局后选择，布局切换后重新划定范围。
不要把一段教程的 UI 坐标写成通用默认，也不要用区域筛选掩盖区外有意义的操作。

算法由 `--region-mode` 选择：默认 `frame-grid` 把整张原图缩到 RGB 网格（默认 320×180），
再按归一化坐标取区域；`crop-first` 先从原图裁出各指定区域，再分别缩到该网格，保留更多局部细节。
后者适合已定位的参数区，最多8区分别解码，增加本地计算；两种模式的分数/阈值不能直接作同口径比较。
原图保持不变，模式写入比较配置；区域变化或布局移动后重新取区。逐像素取三个通道绝对差的最大值，并除以 255。
每区域记录平均差 `mean_delta` 和超过单像素阈值的比例 `changed_fraction`。
以下任一条件达到就标记为该区域的候选：

- `mean_delta >= --mean-threshold`（默认 0.02）；
- `changed_fraction >= --fraction-threshold`（默认 0.08），单像素阈值为 `--pixel-threshold`（默认 0.08）。

阈值范围 `(0,1]`，是可调启发式，不是概率、精度保证或领域规则；所有分数和未入选比较也保留。
网格可用 `--analysis-width/--analysis-height` 调整，范围分别 32..640、32..360。
缩小图像可能漏掉细小数字变化，相邻采样可能漏掉出现后又消失的操作；crop-first也不识别参数名/新旧值。
提高网格密度不补足时间采样缺口。先粗扫，转录到达后按具体问题局部加密；不为捕捉所有操作统一缩小全片间隔。

输出 `changes.json` 保存来源索引 hash、区域/网格/阈值、全部相邻比较与候选 ID，`index.md` 提供
候选时间范围、触发区域和前后原图链接。`range_seconds` 仅为两个已采样实际帧时间之间的区间，
不声称精确事件时间、操作类别或节点变更。`semantic_inspection=not_performed`。
没有候选只表示当前样本/区域/阈值没有触发；候选很多时先缩小需要核对的章节，用 `review` 加密再比较，
不要为了得到某个固定候选数量反复调阈值，也不要自动执行所有候选对应的 Houdini 操作。

检查点：粗扫索引→本地比较→agent 看前后图→选定区间 `review`→再次核对，保留来源链。
对纯渲染/视口移动，像素变化是合法测量但不是建模动作证据。两轮局部重看仍无法判断时留作未知。
该方法针对已采样图像的可重复差异测量；跨教程的关键操作召回率尚无保证。

### 帧时间语义

抽帧使用 FFmpeg `-copyts`、准确输入 seek、`showinfo` 和 `-fps_mode passthrough`。
读取首个输出帧的整数 PTS 与 time base，而不是从平均帧率或请求时间猜测：
`actual_seconds = source_pts × time_base − container_start_time`。
原始起点为非零时仍归一化到媒体播放时间轴；以精确有理数计算，再导出秒数。
`requested_seconds`、`actual_seconds`、`source_pts`、`time_base`、`source_pts_seconds`、
`seek_delta_seconds` 和索引级 `origin_seconds` 一起保存。缩略图标签使用实际时间，显示到毫秒；
JSON 保留 PTS 精度。一般获得请求点之后的第一张可解码帧，不保证等于请求时间或最近帧。

缺少起始时间、可用 PTS，或请求处已经没有视频帧时拒绝，不能回退成假时间戳。
格式 duration 与视频流末端不一致时优先限制到可确定的视频跨度，避免用音频尾部冒充视频帧。
中断时保留 `frame-plan.json` 和已生成的 `evidence-*.json`，没有完整 `frames.json` 就不能称完成。
这类中断当前不自动续跑；原文件保留，诊断后用新输出目录重做需要的范围，不改写旧证据。

依据：[FFmpeg 时间戳/seek 选项](https://ffmpeg.org/ffmpeg.html)、
[showinfo](https://ffmpeg.org/ffmpeg-filters.html#showinfo)。验证入口为离线测试中的真实变帧率、
非零起点及独立顺序解码图像对照；不将这些测试等同于任意容器或损坏视频都受支持。

## 文件与状态

- `manifest.json`：版本、源路径/hash、视频时长与流、解析区间、音频片 id/时间/hash。
- `source-manifest.json`：ingest的原始轨道与合并媒体身份；原件保持不变。
- `asr-config.json`：固定endpoint、模型、非默认协议、明确模型选项与manifest hash；不含密钥，并发/启动速率是本次调度参数。
- `attempt-*.json`：先于请求写入，记录片 id/尝试次数；未有 outcome 的请求为未知。
- `outcome-*.json`：HTTP/传输状态或成功原文与 hash；不保存服务端错误正文或鉴权头。
- `export` 输出 `transcript.json`、`transcript.md`、`validation.json`：缺失区间、空文本片、
  完整音频覆盖与人工准确率/视觉尚未验证分开。失败时已有结果仍可导出，状态为 partial。
- `frames.json` schema 2：源 hash、采样计划、请求/实际帧时间、原始 PTS、原图/缩略图/联系表 hash；
  `semantic_inspection=not_performed`。schema 1 的历史请求时间索引保持原意，不自动升级。
- `frame-plan.json`、`evidence-*.json`：未完成抽帧任务也保留计划和逐帧证据；`index.md` 是导航，不是语义报告。
- `comparison-plan.json`、`changes.json`：变化检测配置及完整比较；比较失败时没有完整 `changes.json`，
  不能仅凭计划文件宣称成功。原图和已有索引不修改。

静音/无讲话可以得到空文本；音频已提交不代表它包含语音。不可把空文本悄悄当高质量通过。
不自动删除重叠文本，以免丢失节点名或数值；任何整理版与原始版分文件保存。
导出文本含不可信材料；网页/Markdown 查看器也不能据此执行其中代码或链接动作。

## 章节、模块索引与按需读取

适用完整教程分析/教学工程；短片术语查询可直接使用局部context。粗截图不依赖转录，两者分别准备；
Agent结合粗图和分批读取的原文建立索引，然后用讲解线索、画面变化和复现缺口提出下一轮取证问题。
脚本不调用LLM、不按关键词自动划定语义章节、不伪造逐句时间，也不自动发起云请求或HOM执行。

```powershell
& $videoPython $videoScript index-init --frames-dir 'D:/task/dsh-analysis/tutorial/overview' --transcript 'D:/task/dsh-analysis/tutorial/sample-export/transcript.json' --output 'D:/task/dsh-analysis/tutorial/catalog'
& $videoPython $videoScript read-transcript --index 'D:/task/dsh-analysis/tutorial/catalog/index.json' --offset 0 --limit 8
# Agent读取原文与粗图后，在index.json填写chapters/modules；再检查及按模块读取。
& $videoPython $videoScript check-index --index 'D:/task/dsh-analysis/tutorial/catalog/index.json'
& $videoPython $videoScript read-index --index 'D:/task/dsh-analysis/tutorial/catalog/index.json'
& $videoPython $videoScript read-index --index 'D:/task/dsh-analysis/tutorial/catalog/index.json' --module distribution
```

`index-init`从已完成的粗图索引和ffprobe建立source/overview/transcript的路径、hash及媒体时长；
duration_seconds是容器时长，video_duration_seconds是可取帧的视频跨度；音频尾段按前者校验，
原图按后者校验，不能把正常音视频尾长差异判为转录越界，也不能为音频尾部伪造视频帧。
旧索引缺少video_duration_seconds时保留原有边界，不静默重写；若旧索引用视频时长拒绝完整音频，
用index-init生成新目录后核对迁移chapters/modules，保留原始失败索引、转录及图像。
静音任务可省略transcript。章节/模块初始为空，是待Agent填写的草稿，不能通过check-index。
`read-transcript`允许读取草稿：默认8片/页，原始片段不截断，返回总数和next_offset；上下页需要上下文时
显式重读相邻片。speech ID按整份转录的数组序号稳定生成，不随分页变化。
已有索引后转录才到达时，Agent显式填写transcript路径和实际hash；旧context引用若使用旧转录必须重新核对。

索引顶层由命令生成，Agent只维护chapters/modules；这是一份可写导航，不是第二份完成证书。
章节按播放顺序，工程模块按依赖，二者ID在整个索引唯一。填写格式如下（示例时间/对象须换为实际来源）：

```json
{
  "chapters": [{"id": "chapter-distribution", "title": "建立分布", "ranges": [[0, 30]]}],
  "modules": [{
    "id": "distribution", "title": "分布及后续修正", "ranges": [[0, 12], [20, 30]],
    "purpose": "理解输入到分布输出的关系", "inputs": ["输入几何"], "outputs": ["分布点"],
    "depends_on": [], "questions": ["第二个输入接了什么？"], "unknowns": ["画面外的源节点待查看"],
    "evidence": []
  }]
}
```

章节每项只有id/title/ranges且只有一个范围；模块必须包含示例全部字段。范围有序、不重叠、在媒体时长内；
模块可含多个不连续范围以保留后段修正，不同模块可以共享来源范围。inputs/outputs/purpose是Agent解释，
不冒充可见操作；depends_on只引用模块ID，拒绝缺失依赖与循环。上限256章节、128模块、每项64范围。
不要求猜全片每个参数才创建索引；未查看/看不清/已定位未展示/版本差异按具体原因写unknowns。

问题由Agent结合上下文提出：这里/这个节点/这个参数→核对指代；连接/勾选/数值→核对对象和前后状态；
撤销/改回/回到前面→追踪最终采用值与受影响模块。候选时间保留整段ASR范围，必要时扩展相邻片，
不能按词序猜精确秒数。无讲解操作仍从粗图、变化候选和缺口发现，关键词不是排除其他片段的过滤器。

每个模块的evidence引用现有notes中的步骤，不复制观察正文：

```json
{
  "context": {"path": "D:/task/dsh-analysis/tutorial/evidence/context.json", "sha256": "实际context文件hash"},
  "notes": {"path": "D:/task/dsh-analysis/tutorial/notes.json", "sha256": "实际notes文件hash"},
  "step_ids": ["step-01"]
}
```

hash用本地SHA-256计算，例如PowerShell `(Get-FileHash -LiteralPath 'D:/task/dsh-analysis/tutorial/notes.json' -Algorithm SHA256).Hash.ToLowerInvariant()`。
notes指Agent填写的原始notes JSON，不是check-notes生成的报告。引用步骤须完整落在某个模块范围内。
check-index重新校验视频、粗图、转录、context、notes及步骤范围；来源跨视频、转录版本不一致或内容变化均拒绝。
新观察另存新的context/notes后更新引用，保留旧资料；不要只刷新hash来掩盖需要重新核对的内容。

read-index默认返回章节/模块导航、章节覆盖缺口、reference_summary及问题/未知/证据/证据待核与冲突数量；指定模块时返回模块资料、相关转录原文、
所引用步骤和对应原图路径/实际时间。原始ASR分片即使跨越模块边界也完整返回；多个范围命中同片只返回一次。
冲突/未知随原notes返回，结构通过不升级为复现ready。读命令默认24000字符预算，--max-chars可显式调整到
1000..160000；超限明确拒绝，不截断。大模块可用read-index的--section speech或observations分开读取，
配合--offset/--limit分页（默认每页8项、最多100项）。返回total_items、next_offset、index_sha256；
后续页传--index-sha256固定首批版本，索引发生修正则拒绝混读，重新从新版本开始。
每页保留模块questions/unknowns与来源，不把页末或空页当模块完成；原文片段和单条观察不拆断。
section=all保留原完整输出，不能混用分页；section读取必须指定模块。单项超预算仍需显式增加预算，
不能自动裁掉代码或观察。也可分批read-transcript配合局部context，
不为节省上下文删掉义务。磁盘详细保存、上下文按需读，不默认启用多Agent或多作者HOM。

## Agent 解析报告

### 证据包

`context` 按 `--start/--end` 选取帧索引中实际 PTS 位于范围内的图（包含端点），以及与该区间
重叠的转录分片。输入为 `--frames-dir` 和可选的 `--transcript`，静音/仅画面任务可不传转录。
支持本工具 export 的 `validation + chunks` JSON，以及同样明确 `source_sha256`、
`timestamp_basis` 和 `chunks[{start,end,text}]` 的顶层分片 JSON；不把其他字幕格式隐式转换成精确对齐。
转录 hash 与视频身份绑定，缺少来源身份或来自另一视频则拒绝。传入文件的 source hash 是
该转录产物声明的来源，不是服务端内容真实性签名；脚本不独立验证每个字确实出现在音轨。

输出 `context.json` 和可读 `index.md`，包含原图链接、原始转录、两类来源文件 hash 与语音缺口。
语音分片保留完整原始范围，不按截图时间裁切句子。稳定语音 ID 为输入分片数组序号
`speech-00000` 等，仅在该输入文件 hash 下成立；合并转录中重名原始 ID 不会相互覆盖。
上下文最多 48 帧、100 段转录、16 万转录字符，超限缩小范围，不静默截断。
语音缺口为空只表示区间被已有分片覆盖，不表示 ASR 逐字正确、视听精确对齐或画面完整覆盖。

### 结构化记录

新记录用schema 2，旧schema 1仍可读取，不自动补身份或最终值。先用`notes-init --context ... --output ...`
生成notes草稿和evidence-options.json（真实帧/转录候选）；加`--notes 旧notes.json`显式迁移到新目录，
原文件不变，新增上下文为null。草稿引用为空、状态unknown，不因为生成成功就宣称已看图。
以下schema-1基础字段在schema 2中完整保留；每条step另须有下文detail。一个step描述一个对象在一个
上下文的窄范围观察，多对象/不同时间值分条；非节点结果图可用subject.id=null。

报告由实际读过转录和画面的 agent 编写，不由脚本伪造“理解成功”。把记录写到独立 notes JSON，
不修改原始 ASR 或帧索引。以下格式对应 `check-notes`，`context_sha256` 使用 context 命令实际返回值：

```json
{
  "schema": 1,
  "context_sha256": "使用实际 context 文件的 SHA-256",
  "steps": [{
    "id": "step-01",
    "kind": "observed_state",
    "range_seconds": [120, 132],
    "intent": "解释本条观察的目的和范围",
    "speech_ids": ["speech-00004"],
    "visual": [{"frame_id": "frame-0000.png", "observed": "实际看到的面板/端口"}],
    "inferences": [],
    "conflicts": [],
    "unknowns": ["未展示的参数或创建步骤"],
    "evidence_state": "visual_checked",
    "reconstruction_readiness": "needs_more_evidence"
  }]
}
```

例子中的语音/图像 ID 必须换成该证据包真实列出的 ID；时间以证据包为准，不复制示例时间。
每包 1..48 条记录，ID 唯一。步骤范围在证据包范围内，原图实际时间位于该步骤范围，
语音分片与步骤范围有重叠。未展示/看不清的信息写 unknowns，不能猜值填入 observed。

Houdini原图的observed按“上下文/对象→接线→设置→状态→输出”记录可读细节：当前网络路径；
节点实例名与明确显示的type分开；起止节点及实际端口；参数标签/页/值、表达式、keys、ramp；
选中/旁路/显示标志、颜色、网络框与注释；外部文件、选区、Edit/Stash等数据；当前输出及可见结果。
颜色只作定位辅助，不据此认定类型、ownership或功能。画面外端点、遮挡字符、未知参数页如实注明。
同一对象可用名称加网络上下文定位，名称被改写、重名或无法跟踪时保留身份疑问。
重复状态可引用已有快照并记录新增变化，但每个新操作仍需前后原图；后段修正、试调、撤销单独留证，
不得覆盖早期状态或把最后一张采样图自动称为最终状态。详细原文与原图留磁盘，摘要只导航；
推断写inferences，无法确定的内容写unknowns，不能把为了复刻设计的补充方案写入observed。

`kind` 使用 `observed_state / ui_navigation / demonstrated_operation / inference`。
前两张不同实际时间的图是操作/导航记录的最低引用条件，不是操作真的发生的充分证明。
面板切换不能当参数修改，静态值不能当创建步骤；推断须说明推断内容。
`evidence_state` 使用 `speech_only / visual_checked / conflict / unknown`，不是成功概率。
有冲突就保留冲突，别用一张不同时间的画面直接“纠正”整个教程的最终值。
`reconstruction_readiness` 使用 `ready_for_runtime_check / needs_more_evidence / unsupported`；
有未解决冲突或 unknowns、没有画面观察、仅推断或 UI 导航的记录不能标 ready。
即使 ready 也仅表示本条的窄范围状态/操作可以开始 runtime 验证，不是完整模块已准备好，
更不是 Houdini 已执行或最终工程已完成。不要为标 ready 而删掉已知缺口。

`check-notes` 重新核对源视频、帧索引、转录与证据包内容，拒绝修改后的旧引用；随后校验记录字段、
范围、引用和状态一致性，生成 `checked-notes.json` 与可读索引。
通过时明确输出 `structural_validation=passed`、
`semantic_validation=agent_assertions_not_independently_verified`、`runtime_verification=not_performed`。
该命令不调用 LLM、不识图、不执行记录中的代码，也不能证明填写者确实看过图片。
这里只整理本次工程所需证据，不写生产流程、skill delta 或节点卡；更不据此获得修改 HIP 的授权。

#### 上下文、事实和修正（schema 2）

每条step的detail具有如下固定结构，空列表表示没有记录，null表示未知；不要求编造所有字段：

```json
{
  "subject": {"id": "source-filter", "name": "filter1", "type": null},
  "context": {"domain": "COP", "network_path": null, "panel_target": null,
    "panel_tab": null, "panel_locked": null, "displayed_output": null},
  "facts": [], "revisions": [], "gaps": [], "references": []
}
```

subject.id由作者分配、在同一视频内稳定；同名不同网络用不同ID。已有ID跨已知domain/network_path被拒绝，
对象移动/重建尚无身份映射合同时另建ID并保留疑问，不静默合并。节点type只写可见明确类型；
network_path是视频网络，不是本地工程路径。panel_target独立记录，锁定面板不一定属于选中节点。
身份与上下文仍是作者声明；结构检查不能验证屏幕识别正确。

- facts每项：`field,value,basis,frame_ids,speech_ids,state,reason`。field是稳定查询键（如`parameter.scale`、
  `input.1.source`），value是原样文本，表达式/ramp/代码仅作为不可执行文本保存，不猜HOM token。
  basis为visual/speech/inference，各自需要本step相应引用或inferences说明。state为observed/trial/
  final_claim/unknown；final_claim要求画面依据且无未决冲突/缺口，reason说明为何认为最终采用。
  同step不重复field；冲突值分观察保留。参数可信度限定于该画面、对象和时刻，不使用统一置信分数。
- revisions每项：`notes_sha256,step_id,fields,kind,reason`，引用先前不可变notes版本中的步骤。
  kind为changes/reverts/corrects/conflicts_with。check-notes校验形状，check-index校验目标已被模块引用、
  字段存在、对象/上下文相同、前后时间不重叠；由严格时间顺序拒绝循环。不删除旧记录、试调或冲突。
  同包修正先拆成新notes包，避免自引用文件hash；不只刷新hash掩盖旧证据变化。
- gaps每项：`field,status,checked_frame_ids,question`。status为not_reviewed/unclear/
  not_shown_in_reviewed_frames/version_difference，非not_reviewed须有实际已查帧。
  与step.unknowns共同保留、阻断ready。not_shown只限定所查帧，不证明视频从未展示；
  已查帧实际时间可追溯采样稀疏程度，版本差异理由另在观察/推断写清。
- references每项：`role,frame_ids,criteria,conditions,limitations,stage,reason`。role为overall/detail/
  material/intermediate/motion；stage为final_claim/intermediate/preview/unknown。criteria/conditions/
  limitations均为非空文本列表；未知灯光或无法判断隐藏结构也需显式记录。motion至少两张不同时间图，
  仍不证明完整动画；final_claim只是作者对参考阶段的判断，不是自动认证。按目标覆盖选图，不按片尾或美观排名。
  成品展示可在开头；先定位目标画面再提取实现步骤。目标原图清楚但隐藏参数未知时，两者分别记录：
  final参考不抹去方法unknowns，未知方法也不自动否定可见目标。作者方法、必要适配及可切回优化的边界见复现协议。

#### 多入口查询与资料交接

```powershell
& $videoPython $videoScript notes-init --context 'D:/task/dsh-analysis/tutorial/evidence/context.json' --output 'D:/task/dsh-analysis/tutorial/notes-draft'
& $videoPython $videoScript review-packet --context 'D:/task/dsh-analysis/tutorial/evidence/context.json' --frame-ids frame-0000.png frame-0001.png --region panel:0.7:0:0.3:1 --question '面板数值是否改变？' --output 'D:/task/dsh-analysis/tutorial/focus'
# 实际核对并填写notes后：
& $videoPython $videoScript check-notes --context 'D:/task/dsh-analysis/tutorial/evidence/context.json' --notes 'D:/task/dsh-analysis/tutorial/notes-draft/notes.json' --output 'D:/task/dsh-analysis/tutorial/checked'
& $videoPython $videoScript index-link --index 'D:/task/dsh-analysis/tutorial/catalog/index.json' --module distribution --context 'D:/task/dsh-analysis/tutorial/evidence/context.json' --notes 'D:/task/dsh-analysis/tutorial/notes-draft/notes.json' --step-ids observation-01 --output 'D:/task/dsh-analysis/tutorial/catalog-next'
& $videoPython $videoScript query-notes --index 'D:/task/dsh-analysis/tutorial/catalog-next/index.json' --module distribution --view issues
& $videoPython $videoScript query-notes --index 'D:/task/dsh-analysis/tutorial/catalog-next/index.json' --subject source-filter --field parameter.scale --view final
& $videoPython $videoScript query-notes --index 'D:/task/dsh-analysis/tutorial/catalog-next/index.json' --view references
& $videoPython $videoScript export-brief --index 'D:/task/dsh-analysis/tutorial/catalog-next/index.json' --output 'D:/task/dsh-analysis/tutorial/brief'
# 资料交接：同时回查作者方法与成品参考；需要已有成品候选时选此导出检查，不作为建网准入条件。
& $videoPython $videoScript export-brief --index 'D:/task/dsh-analysis/tutorial/catalog-next/index.json' --require-final-reference --output 'D:/task/dsh-analysis/tutorial/effect-brief'
```

示例区域仅为语法，不是默认布局。review-packet从已有context选1..12帧、一个显式归一化区域，
输出裁切图、原图链接、时间和review.json；不改原图、不增强/补画文字，不自动记录observed。
需要新时刻仍用review/frames，再生成context。画面布局变化重新选区域；派生图只辅助观察。

index-link接受已存在且通过校验的模块索引，在新目录追加已核notes引用，不替换或删除旧引用；
失败可能留下诊断候选index.json，无成功回执，原索引不动。模块草稿仍由作者填写语义字段。
必须继续使用返回的新索引路径；旧文件保持原义。历史目标必须保留在模块证据中才能验证修正链。

query-notes可组合`--module/--subject/--network/--domain/--field`精确过滤、`--start/--end`时间重叠过滤；
不按名字猜身份。view=history/issues/references/final。多模块同notes-hash/step去重，保留module_ids。
默认每页8项，--offset/--limit最多100；--index-sha256固定跨页版本，默认24000字符预算，超限拒绝不截断。
每页保留模块问题/未知；旧notes缺结构化上下文的数量显式返回，过滤无结果不证明不存在该对象。
final仍返回完整匹配历史和field_claims：只有明确final_claim、无未决问题且无竞争叶记录才返回
author_final_claim；否则unknown。不以最新时间选值，不消除历史冲突；摘要限于查询范围，不能外推全片。
修正解释尚不能机械消除旧unknowns，作者需核对记录后明确报告解决范围，不为得到通过删证据。

reference_summary在索引概览、view=references及导出回执中报告reference_count、final_candidate_count、
final_candidate_roles和status（final_candidates_present/no_final_reference）。查询摘要覆盖完整过滤集合，
不是当前页；跨模块共享记录去重。只统计stage=final_claim且role非intermediate的作者候选，
不自动挑选最新帧、不证明整体/局部/材质/运动目标已覆盖，也不认证语义。旧notes无references时如实报告缺失。

export-brief生成只读派生brief.json/brief.md：成品参考入口先于模块，保留每个候选的notes/step/modules、
原图路径/实际时间、判据/条件/限制；不丢弃preview/intermediate或竞争候选，Agent须实际看图决定适用范围。
--require-final-reference只在没有上述成品候选时于创建输出目录前拒绝；默认解析导出仍允许无参考并显式报告。
这个门不要求补造未知参数，也不是相似度或复刻完成门。报告不成为可写事实源；资料更新后重新导出。
JSON保留完整观察供查询；Markdown从同源记录展示对象/上下文、事实字段与依据、观察、推断和缺口，仍只是派生导航，不替代实际原图/原音核对。
模块概览和分页继续携带目的、输入、输出与依赖，不能因分段读取丢掉作者方法的数据语义。
runtime映射、必要适配、优化收益与切换方式留工程说明，不改写原始来源事实；选择规则由[复现协议](reconstruction.md)维护。

## 维护验收

入口：`python tools/tests/video-tutorial.test.py`，不依赖 HOM、密钥或网络。
覆盖分片时间、授权前零请求、hash 损坏、部分导出、续跑不重传、未知/失败重试预算、
无音轨与画面抽取边界。真实媒体还应检查中文路径、非零起点、末片裁切、抽帧可读；
实际云 smoke 在仓库外短段完成，不能让默认测试上传教程。
检测到本机 FFmpeg/ffprobe 时还运行合成变帧率视频的 PTS/像素一致性测试，缺少时显式 skip，
不因此宣称真实媒体验证通过。粗扫和局部索引另外检查页数、时间标签、原图入口及近片尾样本。
变化候选另验：静态/低幅噪声、颜色变化、区域排除、重复 PTS、证据损坏、阈值边界，
以及零候选不宣称无操作。真实 RGB 解码以本地合成图检查，不依赖第三方视频或云服务。
证据包与记录另验跨视频混用、源文件变化、时间越界、缺失引用、单图冒充操作、未解决冲突被标 ready，
以及“结构通过”不会自动变成语义或 runtime 通过。

索引离线回归另验草稿分页、多个不连续片段及原始范围保留、静音路径、缺依赖/循环、证据越界、
旧hash失效、冲突回读、预算拒绝不截断、音频尾长/真正越界、模块section分页及跨页版本变化。crop-first用本地合成的小区域变化及区外反例验证，
只证明裁切比较保留该样本细节，不证明真实参数识别率。入口仍为同一video-tutorial.test.py。
结构化notes另验null上下文迁移、事实逐项引用、同名异上下文、跨包修正目标/时间/字段、保留历史与冲突、
final查询不选最新试调、共享证据去重、参考图适用范围、成品候选缺失时导出零写拒绝、旧解析兼容、
明确成品与未知方法共存、多个候选不自动择新、只读派生交付与旧文件不变。以上是确定性合同，
不是跨视频识别率证明；真实人工基线与未见任务仍单独验收。

真实测试固定教程、模型、工具版本和预算，先比较原流程与索引/定向取证/按需读取；采样间隔、crop-first、
多Agent分别单因素比较。材料覆盖指示词+小数字、静默改线、试调撤销、后段修正、遮挡/画面外端点、
布局/鼠标干扰、长片续跑；另有只需讲解与静音反例。事先人工标注待核对操作和可见事实，记录找回/遗漏、
错误确定声明、取证原图数与实际送入模型图片数、原文重读、输入/cache/output token、耗时及复现返工。
工程侧核对首次分叉定位、受影响模块复验、参数实验、阶段输出和保存重开。另验成品在开头/后段试调、
方法明确时尽量还原、隐藏设置优先在原方法内补全、版本/软件/资源缺口在具体范围内适配、有明显收益时保留可切回优化；
不能用更多图片或节点数替代最终参考差异减少。结果留会话/CI，未见视频、
新session自然采用、语义判断与H21/H22工程验收保持独立待测，不能由离线通过核销。

行为验收包括：原音画冲突、不同时长/语言的未见视频、普通建模不触发、静音演示走视觉路径、
服务失败留证、最后状态与试调分离。H21/H22 HOM 验收对纯解析不适用；进入工程复现时另验。
单一视频样本不证明泛化；未完成新 session 曝光/触发和未见视频行为验证时保持候选状态。
