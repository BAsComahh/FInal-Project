# Board game augmentation

[中文](#中文) | [English](#english)

## 中文

当前示范流程：视频首帧 → 自动检测并确认桌角／手动矫正 → 确认桌面长宽 → Homography 聚焦战场 → 点击分割、绑定单位 type → 播放并传播 mask。界面全英文，mask 和托盘矩形图层独立开关。首版游戏工具提供最近距离、基础 LOS、普通移动和 At the Double 的采样估计；冲锋延期。EdgeTAM 已接入单次自动身份恢复、候选审核及保留原 ID 的手动恢复。

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30
```

模型权重启动即加载；确认桌角和尺寸后准备拉正首帧特征。单位提示与 type 绑定在首次播放前编辑，S 或首次播放只保存一次最终 reference。播放后持续显示并保持编辑锁定，Space／Q 清除工具并返回最新实况，R 开始新注册。注册侧栏的 `Tray dimensions (mm)` 提供 A／B 双列的 type 宽深编辑。

注册侧栏提供 `Import list A`／`Import list B`，直接选择各方 PDF 或单方类型 JSON，下方两栏分别显示 Type 1、Type 2…，支持点击／拖放绑定。内部类型 A1／B1 的实例分别生成 A1.1／B1.1。无需传军表参数；默认 [ABC 测试资料](inputs/units.video_estimate.json) 先放在 A 栏，Type 1 为 155 × 50 mm，Type 2／3 为 205 × 80 mm，B 栏等待导入。锁定桌角后通过 `Length (in)`／`Width (in)` 确认默认 72 × 48 inches 或修改尺寸。默认尺寸是测试估算；也可载入外部毫米标定。独立 PDF 转换工具见 [reader 用法](components/registration/README.md#pdf-军表-reader)。

首帧用 F 标正面后，平时按矩形连续性维护方向，轻量外观检查连续可疑才调用 DVMNet 恢复正面；精确角度仍取矩形。参考和当前目标都去背景填均值色。仅方向恢复失败保留旧 Estimated 并标失败，有新外观证据且间隔满足才重试；无旧方向则 unknown。此功能默认试运行，资源准备与配置见 [正面说明](frontend/README.md#dvmnet-辅助正面)，真实 180°／方形转向可靠性仍待验证。

操作说明见 [frontend](frontend/README.md)，单位表和导出格式见 [registration](components/registration/README.md)，设计、官方依据与实验结论见 [项目思路.md](项目思路.md)。

本局公共数据集中在 [GameData](components/game_data.py)：保留局部观测历史及全局平移／旋转事件，完成注册后持续写入该次输出目录的 `history.sqlite3`。平移与旋转独立判断，容差内停稳 5 秒完成，初始位置容差 10 mm、旋转容差 10°；位置以原视频像素为基准保存，距离等规则仍用毫米；仅标定切换不中断动作，真实追踪／几何缺失保存中断记录，不算完成一步。内存保留约 5～5.5 分钟及进行中／未写盘数据，R 保留旧数据库。播放页的 Replay 以步骤对应的 Homography 后截图为背景，叠加 ID 和矩形重建历史棋盘，每次已完成移动或旋转各为一步，支持 ←／→、A／D 和按钮切步。回放期间后台继续运行，Back to Live 返回最新实况。用法见 [历史棋盘回放](frontend/README.md#历史棋盘回放)。

完成注册后按源视频时间检测持续无 mask，默认 10 秒，通过 [application/config.py](application/config.py) 修改。EdgeTAM 超时实例先进入内部 Missing，后台只搜索一次；满足试运行门槛（相似度 0.85、分差 0.10、无竞争／正常区域占用）才接回，其他结果才显示在 A／B 人工名单。点击名单或 `Recover units` 可审核候选，`Correct` 确认、`No` 发起新一轮单次搜索，也可清空后补点。原追踪器自行返回的 mask 仍只作 `Estimated`。门槛尚未校准，流程见[前端说明](frontend/README.md#追踪失败判定与只读名单)。

播放页的 `Recalibrate [K]` 按固定相机理想假设处理，保持原始视频持续播放，不执行相机运动检测。重新选四角及确认尺寸后，以同帧原图和 mask 迁移到独立新会话，保留 ID、原始 reference 和失败回退，成功后切换标定并显示最新帧，源时钟不重启。初始化中也可 Esc 取消；详情见[重新标定流程](frontend/README.md#比赛中重新标定)。

规则查询使用尺寸确认页或外部毫米标定建立的尺度、托盘几何，以及相应的正面、Speed、Height、阵营和地形信息。按 F 登记正面、E 编辑规则属性、G 标地形；D／L／V／J 查询距离、LOS、普通移动／Double。详情和不确定性见 [游戏规则组件](components/game_rules/README.md) 与 [需求审计](docs/Game%20information%20requirements%20audit.md)。

运行核心现位于 [application](application/README.md)：一个比赛实例通过 `tick()` 无窗口推进，以明确命令及冻结快照供 UI 使用。Qt 已接入真实注册和 Live 单位选择／半环菜单、只读单位信息、Distance 连线读数、LOS／Move 底部查询抽屉及右侧 A／B 不确定单位列表；默认托盘更新为 adaptive，稳定 mask 复用几何。重拟合时质心位移超过托盘短边的 50% 则直接完整搜索，其余优先沿用旧框做局部搜索。局部与完整搜索共用[方向 Chamfer Beam 流程](components/boundary_detection/tray/README.md#逐级回退)和 70% mask 覆盖门槛；Live 主路径已做受控 CPU 离屏检查，真实模型／持续追踪与原生交互仍待验收。注册包含桌角／尺寸、点提示、类型绑定、初始正面、一次保存和连续播放；部分受控接口验收已通过，两页离屏加载已通过，实际界面交互待验收，完整 UI 迁移及 I14 验收仍未完成。使用相同模型环境与独立 Qt 依赖，启动见 [Qt 客户端](frontend/qt/README.md)：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --start 3600
```

复用完成的注册可在注册页点 `Load registration` 选原目录的 `prompts.json`，或在上面命令中用 `--registration outputs/sam3_registration/frame_5b58dfca4481` 替换 `--start 3600`。该存档自动回到45:00，保留24个对象及原ID，模型就绪后直接 `Start video`。每次载入新建测试记录，不覆盖原存档；这是复用初始注册，不是恢复中途进度。

完整直播已下载至 `inputs/Ja5-2RIOBXU_full.mp4`（9:35:57，1080p／60fps，约 5.9 GB；大文件已忽略，来源见 [记录](inputs/Ja5-2RIOBXU_full.source.json)）。上述命令从 01:00:00 的该场第一回合开始，单位较原 02:30:00 片段分散；可修改 `--start` 秒数。省略 `--seconds` 默认播放到视频结尾，短测可显式传入时长。原五分钟片段保留。Qt 注册不画选中外接框，Points 模式赋予类型成功后自动进入下一 mask。

### 目录

```text
frontend/
  window.py                  OpenCV window lifecycle and event loop
  app.py                     Workflow composition and input routing
  presentation.py            Window-local selection and tool state
  registration/              Registration layout, prompt input and catalog drag/drop
  calibration/               Corner and dimension drafts
  live/                      Continuous live view and missing-unit lists
  replay/                    Historical board display and discrete event navigation
  geometry_tools/            Query controls and measurement overlays
  scene_editing/             Unit profiles, initial facing and terrain inputs
  shared/                    Drawing, viewport transforms and cached layers
  image/                     Standalone image registration windows
components/
  game_data.py               Shared match data and rectangle/state history
  history.py                 Background SQLite history and indexed per-unit reads
  motion_history.py          Independent translation / rotation event detection
  replay.py                  Captured history index and endpoint scene reconstruction
  recalibration.py           Board, mask and annotation coordinate migration
  registration/              Unit catalog, bindings and reference export
  boundary_detection/        Shared LSD, table/tray fitting and Canny
  homography/                Rectification and coordinate transforms
  sam3/                      Image/video model interfaces
  tracking/                  Optional Cutie / EdgeTAM video propagation
  dinov2/                    Frozen feature extraction
  facing/                    DVMNet appearance selection of current tray front edge
  image_io/                  Image reading and saving
  video_io/                  Video decoding and timestamps
  real_esrgan/               Optional Vulkan super-resolution
  game_rules/                Independent KoW4 mini distance, LOS and sampled movement
tools/                       Independent command-line entry points
docs/                        Requirements and architecture documents
inputs/                      Input media and unit catalogs
outputs/                     Generated experiment results
```

### 独立工具 / Independent tools

在项目根目录运行 `python -m tools.<工具名> --help` 查看参数。桌面入口仍为 `python -m frontend`，也可使用 `python -m tools.sam3_registration`。

| 工具 / Tool | 用途 / Purpose |
| --- | --- |
| `table_detector` | 图像到桌角与四边 / Table corners and edges |
| `boundary_detection` | LSD 原始结果、逐步诊断和导出 / LSD inspection and export |
| `canny` | 青色轮廓及可选 Hough 对照 / Canny contours and optional Hough |
| `pick_table_corners` | 独立图片的手动四角坐标 / Manual image corner coordinates |
| `homography` | 图像与四角到俯视图及坐标矩阵 / Rectification and mappings |
| `sam3_segmenter` | 图片与 miniature 提示词分割 / Text-prompted image segmentation |
| `sam3_click_segmenter` | 图片点击分割及切图 / Point segmentation and cutouts |
| `sam3_image_registration` | 图片检测、增删及多边形注册 / Image registration |
| `tray_detector` | mask 与实际尺寸到托盘候选 / Tray proposals from masks and dimensions |
| `project_units` | 带 ID 的托盘、mask 投影与图层 / Unit projection and layers |
| `update_type_features` | 从已完成注册更新 DINOv2 特征 / Update DINOv2 reference features |
| `evaluate_recovery` | 离线验证 SAM 文本候选与仅缺失实例的 DINO 匹配；不接回直播 / Offline recovery retrieval diagnostics; no ID acceptance |
| `super_resolution` | Real-ESRGAN 备用边缘增强 / Optional edge enhancement |
| `image_io` | 支持中文路径及通道保留的读写 / Image conversion and saving |
| `query_rules` | 从 scene.json 查询距离、LOS 或普通移动／Double / Query a metric scene |
| `read_unit_list` | Mantic Companion PDF 军表转注册类型 JSON / Convert army-list PDFs to type catalogs |
| `setup_tracking` | 准备 Cutie／EdgeTAM 的固定源码、权重及独立依赖 / Prepare optional tracker assets |
| `setup_facing` | 准备 DVMNet 固定源码、权重及独立依赖 / Prepare experimental facing assets |

算法接口直接从组件导入，例如 `from components.boundary_detection.table import detect_table`；CLI 只处理参数、展示与导出。LSD 配置位于 [config.toml](components/boundary_detection/config.toml)，源线段长度过滤默认关闭，合并后长度过滤默认开启。几何长度配置使用百分比（`5` = 5%）：桌边以图像短边为基准，托盘局部容差以托盘短边为基准；实际尺寸仍用 mm／in。完整用法见各组件 README。

前端默认由 SAM3 完成首帧注册（`--segmentor` 指定其 checkpoint），再将 mask 交给 EdgeTAM 传播（`--tracker edgetam`）；可显式选择 `--tracker sam3`／`--tracker cutie` 作对照，详见 [视频追踪](components/tracking/README.md)。正式客户端固定 adaptive 托盘更新：稳定时复用，变化时先局部、失败再完整搜索；`--profile` 导出计时。几何结果持续更新并标注观测时间，资料／地形表单采用非阻塞轮询，B08 不停源；播放页已移除 Hold／HELD。EdgeTAM 自动／手动恢复已接入，what-if 仍待实现，LK 已移除。

### 环境

使用现有 `sam3-demo` 环境，Python 3.12 及以上；当前环境为 3.13.16。依赖版本记录在 [requirements.txt](requirements.txt)。

```powershell
conda run -n sam3-demo python -m pip install -r requirements.txt
```

新环境先安装与显卡匹配的 PyTorch／torchvision。本机使用 ROCm，依赖版本兼容现有的 `+rocm10.0.0` 构建。SAM3／DINOv2 权重需单独缓存，Real-ESRGAN 使用独立 Vulkan 程序与模型，安装方式见 [组件文档](components/real_esrgan/README.md)。

## English

The demo reads a video's initial frame, detects or manually corrects table corners, confirms the physical table dimensions, rectifies the battlefield with Homography, registers masks and unit types, then plays the video with propagated masks. All UI text is English. Mask and tray layers are independent. The KoW4 mini prototype adds base-to-base distance, sampled LOS and ordinary/At the Double reachable poses; Charge is deferred. EdgeTAM supports single-search automatic recovery, candidate review and manual recovery retaining existing IDs.

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30
```

Weights load at startup; rectified first-frame features are prepared after corner and dimension confirmation. Registration drafts stay in memory. S or first playback commits final references once and locks editing; pausing retains the playback layout. R starts a new registration.

EdgeTAM is the default propagation backend, initialized from the registered SAM3 masks; use `--tracker sam3` or `--tracker cutie` for comparison. Prepare tracker assets with `python -m tools.setup_tracking --backend all`. Geometry queries follow live observations and show their source time. Rule/terrain forms are non-blocking, and B08 keeps playback active. Hold/HELD has been removed; Space/Q clears tools and returns live. EdgeTAM searches once for failed instances before showing human requests. Trial gates are cosine 0.85 and margin 0.10, with conflict/normal-occupancy protection. Click a failed ID or Recover units to review; Correct confirms, No requests one new search, and Clear / Retry allows manual points. What-if remains pending. LK has been removed. See [tracker setup and limits](components/tracking/README.md).

Use `Import list A` / `Import list B` in the registration sidebar to select each army's PDF or single-army JSON directly. Two independent columns show Type 1, Type 2, etc., with click/drag binding. Instances of types A1/B1 become A1.1/B1.1; no catalog parameter is required. The [ABC test data](inputs/units.video_estimate.json) initially occupies List A: Type 1 is approximately 155 x 50 mm and Types 2/3 are 205 x 80 mm; List B awaits import. After locking the corners, confirm the `Length (in)` / `Width (in)` fields, prefilled with 72 / 48. These defaults are test assumptions, not verified measurements. External calibration and the standalone `tools.read_unit_list` converter remain available. The camera is assumed fixed between calibrations.

Confirm table corners and physical dimensions in the setup view; dimensions are initially prefilled as 72 by 48 inches. F marks the initial front edge, E edits unit rule information and manual states, and G annotates terrain. D/L/V/J query distance/LOS/ordinary movement/Double; Q clears the query. Results are based on registered geometry, not full match adjudication. See [the rule component](components/game_rules/README.md) and [illustrative scene](inputs/rules.example.json).

The directory tree and independent tool list above describe the current ownership. The window owns a VideoApplication, which coordinates workflow controllers and views; MatchSession schedules model and tray tasks. Algorithm components never import the frontend or command-line tools. Unit data and reference export are independent of SAM. Run `python -m tools.<tool> --help` for standalone tools; `python -m tools.sam3_registration` also starts the desktop app. Geometric length settings use explicit percentages (`5` means 5%): table thresholds use the image short side, while local tray tolerances use the tray short side. Physical dimensions remain in mm/in.

Each MatchSession owns one [GameData](components/game_data.py) instance for local observations and global translation/rotation events. The two event types run independently and finish after 5 seconds of sampled stability, initially using 10 mm / 10 degree tolerances. Original video pixels are the canonical spatial record; rule calculations remain in millimetres. Recalibration alone preserves action continuity, while actual tracking/geometry loss interrupts events without claiming a completed move. Records continuously write to `history.sqlite3`, with recent, ongoing and unsaved data cached in memory. R preserves the old database. Replay projects saved rectified step images onto the historical board and overlays unit IDs and rectangles. Each completed move or rotation forms one step, navigated with Left/Right, A/D or buttons. Source playback, tracking and recording continue in the background, and Back to Live returns to the latest view. Refresh includes newly completed events. See [replay controls](frontend/README.md#历史棋盘回放).

During playback, `Recalibrate [K]` assumes a stable camera and keeps the raw source view running without camera-motion detection. Matching source images and masks seed an independent tracking session using loaded weights, retaining IDs and references. Success switches calibration versions and displays the latest source frame without restarting its clock; Esc can cancel during initialization. Failures retain the old session, and unavailable masks retain their unit records without fabricated positions. See [the recalibration workflow](frontend/README.md#比赛中重新标定).

See [the UI guide](frontend/README.md), [registration data](components/registration/README.md), [SAM video API](components/sam3/video/README.md), [boundary detection](components/boundary_detection/README.md), [Homography](components/homography/README.md) and [DINOv2](components/dinov2/README.md). Design rationale and meaningful experimental findings are maintained in [项目思路.md](项目思路.md).

Use Python 3.12 or newer with the pinned [requirements](requirements.txt). For a new environment, install a GPU-compatible PyTorch/torchvision build first. This machine uses ROCm; the pins accept its installed `+rocm10.0.0` builds. SAM3/DINOv2 weights and the Real-ESRGAN Vulkan runtime/models are separate assets.

DVMNet facing is enabled as a trial: mark the initial front with F, then appearance selects a current tray edge while geometry supplies its exact angle. Both reference and query use masked mean-color backgrounds. Cheap appearance checks gate DVMNet recovery. Direction-only failures retain the previous Estimated front; retries require changed appearance and a minimum interval. Without a usable old front, facing stays unknown. See [facing setup and limits](frontend/README.md#dvmnet-辅助正面).
