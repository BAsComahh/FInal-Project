# Board Game Augmentation

[中文](#中文) | [English](#english)

---

## English

### Overview

A desktop prototype for augmenting tabletop wargame match videos. Built around a Qt Quick console (English UI), it performs table calibration and homography rectification, first-frame unit segmentation and army-list binding, video mask propagation, tray rectangle fitting, KoW4 mini geometry queries, failure recovery, and step-based historical board replay.

### Core Workflow & Capabilities

1. **Table Calibration & Rectification** — Automatic LSD corner detection (with manual 4-point correction), physical table size confirmation (prefilled with `72 × 48 in` test defaults), and perspective rectification.
2. **First-Frame Registration & Army Lists** — SAM3 point prompting plus manual rectangle / 4-corner polygon masks; `Import list A` / `Import list B` loads Mantic Companion PDFs or single-army JSON catalogs (defaulting List A to [units.video_estimate.json](inputs/units.video_estimate.json)), infers standard base dimensions, allocates per-type IDs (`A1.1`, `B1.1`), optionally marks initial fronts (`F`), commits references once (`S` or `Start video`), and supports reloading completed archives via `Load registration` or `--registration`.
3. **Tracking & Adaptive Tray Fitting** — Registers with **SAM3** and propagates masks with **EdgeTAM** by default (`--tracker sam3` or `--tracker cutie` available for comparison). Tray fitting runs asynchronously on a dedicated CPU worker in `adaptive` mode (reusing stable geometry, falling back from local to full directional Chamfer Beam search with >85% mask fill, and showing dashed last-accepted trays while a tracked unit temporarily fails fitting). `Masks` and `Trays` toggles control display only.
4. **Tracking Failure & Recovery (EdgeTAM)** — After continuous mask loss (default 10 s in [application/config.py](application/config.py)), EdgeTAM runs one automatic search per newly failed unit (SAM3 text detection + DINOv2-small retrieval; trial gates: cosine ≥ 0.85, margin ≥ 0.10, no occupancy/competition conflicts). Unresolved units appear in the A/B review list for `Correct`, `No` (one retry), or isolated manual recovery via the unit menu's red `Correct` action retaining the original ID.
5. **Live Geometry Tools & Auxiliary Flows** — Unit radial menu for `Distance` (in-canvas measurement label), `LOS`, `Move` (sampled Advance / At the Double / Back / Sidestep / Change facing / Halt poses; Charge deferred), and `Info` profile view/editing; non-blocking `Recalibrate` (fixed-camera assumption), terrain annotation, and `Debug` snapshot capture.
6. **History & Board Replay** — Continuous SQLite logging (`history.sqlite3`) anchored in original video pixels with metric rule calculations; independent translation/rotation event detection (10 mm / 10°, 5 s settle); read-only `Replay` while live playback, tracking, and recording continue in the background.
7. **Disabled by Default / Pending** — Live DVMNet facing tracking is disabled (`FACING_TRACKING_ENABLED = False`; initial `F` registration data is retained). Audience window, What-if simulation, and moving Terrain into Registration are tracked in [TODO.md](TODO.md).

### Setup & Cross-Machine Portability

- **Requirements**: Python ≥ 3.12 (verified on Windows, Python 3.13.16). A CUDA or ROCm GPU is strongly recommended (the largest-VRAM GPU is selected automatically; CPU fallback works via `--device cpu`).
- **Memory footprint**: With default settings (SAM3 + EdgeTAM + automatic recovery SAM3/DINOv2 in FP32), measured steady GPU usage is ~5.4–6.6 GiB VRAM (~8 GiB peak RAM). **12 GB+ VRAM / 16 GB+ RAM** is recommended; on **8 GB GPUs**, set `AUTO_RECOVERY_ENABLED = False` in [application/config.py](application/config.py) if OOM occurs (manual recovery remains available).

#### 1. Install GPU-Compatible PyTorch First

> **Important**: On Windows, running `pip install -r requirements.txt` directly installs **CPU-only** PyTorch from PyPI. Install matching `torch==2.13.0` and `torchvision==0.28.0` for your target GPU (NVIDIA CUDA or AMD ROCm) *before* installing `requirements.txt`.

```powershell
# Example with NVIDIA CUDA (adjust cu128 to match the machine's CUDA driver)
python -m pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cu128
```

#### 2. Install Core & Qt Dependencies

> **Important**: Keep the exact `transformers==5.18.0` pin in [requirements.txt](requirements.txt); EdgeTAM acceleration, bounded session pruning, and SAM3 feature caching rely on this version's internals.

```powershell
python -m pip install -r requirements.txt
python -m pip install -r frontend/qt/requirements.txt
# Optional isolated Qt install:
# python -m pip install --target outputs/ui_preview/deps -r frontend/qt/requirements.txt
```

#### 3. Prepare Model Weights & Tracker Assets

All model loaders default to `local_files_only=True` and do not auto-download during app startup:

```powershell
# Download EdgeTAM checkpoint (outputs/model_cache) and timm==1.0.30 (outputs/tracking_dependencies)
# Use --backend all if you also want Cutie
python -m tools.setup_tracking --backend edgetam
```

- **`facebook/sam3` (required, gated repo)**: Request access on Hugging Face, authenticate (`hf auth login`), and pre-download into the local Hugging Face cache — or copy an existing local snapshot folder and pass `--segmentor <local_dir>`.
- **`facebook/dinov2-small` (for automatic recovery)**: Public model; pre-cache via Hugging Face Hub. If absent, the app still starts and falls back to manual recovery only.
- **Not suggested - Optional assets**: Real-ESRGAN ([setup](components/real_esrgan/README.md)) and DVMNet facing (`python -m tools.setup_facing`) are not needed for the default workflow.

### Quick Start

`python -m frontend.qt`, `python -m frontend`, and `python -m tools.sam3_registration` all launch the Qt desktop client (the legacy OpenCV video client has been retired):

```powershell
# 5-minute clip tracked in Git
python -m frontend.qt inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4

# Full match video (5.9 GB, gitignored; see inputs/Ja5-2RIOBXU_full.source.json)
python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --start 3600

# Reload a completed registration archive
python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --registration outputs/sam3_registration/<archive_dir>
```

---

## 中文

### 项目简介

面向桌面战棋对局视频的增强原型系统：基于 Qt Quick 桌面客户端（界面为英文），完成战场桌面标定、首帧单位分割与军表绑定、视频实例追踪、托盘矩形拟合、基础规则几何查询、追踪恢复与动作历史棋盘回放。

### 核心流程与当前能力

1. **桌面标定与拉正**
   - 首帧自动 LSD 检测桌角（支持手动四点矫正）→ 确认桌面物理长宽（默认预填 `72 × 48 in` 测试值）→ Homography 透视拉正。
2. **首帧单位注册与军表导入**
   - 结合 SAM3 点提示分割与手绘矩形／四点凸四边形标注；侧栏通过 `Import list A` / `Import list B` 导入 Mantic Companion PDF 军表或单方 JSON 目录（默认先载入 [ABC 测试目录](inputs/units.video_estimate.json) 到 A 栏，Type 1 约 155 × 50 mm，Type 2/3 约 205 × 80 mm）。
   - 自动按 FAQ 标准底座表与备注推导托盘尺寸，按双方独立生成实例编号（如 `A1.1`、`B1.1`），支持 `F` 标记初始正面。
   - 草稿保存在内存中，`S` 或首次 `Start video` 仅提交一次最终 reference 并锁定注册；支持通过 `Load registration` 或 `--registration` 复用已完成注册存档。
3. **视频追踪与自适应托盘拟合**
   - 默认由 **SAM3** 完成首帧注册，再将已注册 mask 交给 **EdgeTAM** 持续传播（可通过 `--tracker sam3` / `--tracker cutie` 对照，详见 [追踪说明](components/tracking/README.md)）。
   - 托盘拟合固定为 `adaptive` 模式并由独立 CPU 线程异步运行：稳定 mask 复用几何，变化时优先局部拟合、大位移或失败后回退至完整[方向 Chamfer Beam 搜索](components/boundary_detection/tray/README.md#逐级回退)（要求矩形填充率 > 85%）。Live 中仍有 mask 但暂时拟合失败的单位以虚线保留上次接纳框。`Masks` / `Trays` 开关仅控制叠加显示。
4. **追踪失败与身份恢复（EdgeTAM）**
   - 持续无 mask 达到阈值（默认 10 s，见 [application/config.py](application/config.py)）后进入内部 Missing，后台对每个新失败实例执行一次自动搜索（SAM3 文本检测 + DINOv2-small 外观匹配，试运行门槛：余弦相似度 ≥ 0.85、分差 ≥ 0.10 且无占用／竞争冲突）。
   - 未自动接回的结果进入右侧 A／B 审核列表，可 `Correct` 确认、`No` 发起一次新搜索，或通过单位菜单红色 `Correct` 进行保留原 ID 的隔离手动恢复。
5. **直播规则查询与辅助流程**
   - 选中单位弹出右侧半环菜单，提供 `Distance`（连线直接标注最近距离）、`LOS`、`Move`（Advance / At the Double / Back / Sidestep / Change facing / Halt 采样姿态；Charge 延期）与 `Info`（军表完整属性只读展示及状态编辑），规则范围见 [game_rules](components/game_rules/README.md)。
   - 支持播放期间不停源的 `Recalibrate`（固定相机假设）、地形标注（计划后续移至注册页）以及 `Debug` 诊断快照导出。
6. **历史记录与棋盘回放**
   - 本局数据由 [GameData](components/game_data.py) 与无窗口核心 [MatchApplication](application/README.md) 管理，以原视频像素为基准持续写入 `history.sqlite3`（规则运算仍使用毫米）。
   - 独立识别平移／旋转事件（容差 10 mm / 10°、停稳 5 s 计为一步）；`Replay` 按已完成步数重建历史棋盘，回放期间后台追踪与记录照常推进，`Back to Live` 返回最新实况。
7. **默认关闭与待开发项**
   - 实时正面追踪（DVMNet，`FACING_TRACKING_ENABLED = False`）默认停用，仅保留注册初始 `F` 资料与实验代码，详见 [正面说明](frontend/README.md#dvmnet-辅助正面)。
   - 独立观众窗口、What-if 推演及 Terrain 迁入注册页见 [TODO.md](TODO.md)。

### 环境配置与跨机迁移

- **硬件与系统建议**：
  - Python ≥ 3.12（开发环境为 Windows + Python 3.13.16）。
  - 推荐使用支持 CUDA / ROCm 的独立 GPU（自动选择显存最大的设备，无 GPU 时回退 CPU，也可用 `--device` 指定）。
  - 显存参考：默认配置（SAM3 + EdgeTAM + 自动恢复 SAM3/DINOv2，FP32）实测稳态占用约 5.4–6.6 GB 显存、峰值内存约 8 GB，推荐 **12 GB+ 显存 / 16 GB+ 内存**；若为 **8 GB 显存**且出现 OOM，可在 [application/config.py](application/config.py) 中将 `AUTO_RECOVERY_ENABLED` 设为 `False`（仍保留手动恢复）。

#### 1. 安装 PyTorch（先装与目标显卡匹配的版本）

> **重要**：Windows 下直接运行 `pip install -r requirements.txt` 会从默认 PyPI 安装 **CPU 版** PyTorch。请先按目标机器显卡安装匹配版本的 `torch==2.13.0` 与 `torchvision==0.28.0`（例如 NVIDIA CUDA 机器使用 PyTorch 官方 CUDA wheel 源；AMD ROCm 机器使用对应 ROCm wheel）。

```powershell
# 示例：创建虚拟环境（Conda 或 venv 均可）
conda create -n tabletop-aug python=3.13 -y
conda activate tabletop-aug

# NVIDIA GPU 示例（按本机 CUDA 驱动调整 cu 版本，如 cu128）
python -m pip install torch==2.13.0 torchvision==0.28.0 --index-url https://download.pytorch.org/whl/cu128
```

#### 2. 安装项目核心依赖与 Qt 桌面运行时

> **重要**：请保持 [requirements.txt](requirements.txt) 中的 `transformers==5.18.0` 精确版本，EdgeTAM 加速、有界会话裁剪与 SAM3 特征缓存依赖该版本的内部接口。

```powershell
# 安装核心依赖（已安装的 +cu / +rocm 构建满足 torch==2.13.0 / torchvision==0.28.0）
python -m pip install -r requirements.txt

# 安装 Qt Quick 桌面客户端依赖（二选一：直接装入当前环境，或装到隔离目录 outputs/ui_preview/deps）
python -m pip install -r frontend/qt/requirements.txt
# 或隔离安装：
# python -m pip install --target outputs/ui_preview/deps -r frontend/qt/requirements.txt
```

#### 3. 准备模型权重与追踪依赖

所有模型加载器均默认开启 `local_files_only=True`，启动程序时**不会**自动联网下载权重；首次在新机器部署需提前准备以下资产（均位于 `.gitignore` 忽略目录或 Hugging Face 全局缓存中）：

```powershell
# 1) 准备 EdgeTAM 权重（outputs/model_cache）与 timm==1.0.30（outputs/tracking_dependencies）
#    如需同时准备 Cutie 对照后端，可将 edgetam 改为 all
python -m tools.setup_tracking --backend edgetam
```

- **SAM3 权重（`facebook/sam3`，必需）**：该仓库在 Hugging Face 上为**受限模型（gated repo）**。需使用已获 Meta 授权的账号执行 `hf auth login` 后预下载到本机 Hugging Face 缓存，或直接复制已有机器的缓存／模型目录并在启动时传入 `--segmentor <本地目录>`。
- **DINOv2 权重（`facebook/dinov2-small`，自动恢复需要）**：公开模型，预下载至 Hugging Face 默认缓存即可（例如使用 `huggingface_hub.snapshot_download("facebook/dinov2-small")`）。若缺失，程序仍可正常启动，自动恢复会自动降级为仅手动恢复。
- **不建议(未实装)可选资产**：Real-ESRGAN 超分（独立 Vulkan 工具，见 [real_esrgan](components/real_esrgan/README.md)）与 DVMNet 正面实验（`python -m tools.setup_facing`）在默认流程中不需要。

### 快速启动

桌面客户端统一由 Qt 启动（`python -m frontend.qt`、`python -m frontend` 与 `python -m tools.sam3_registration` 等价；OpenCV 视频客户端已退役）：

```powershell
# 1. 使用随仓库提供的 5 分钟测试片段
python -m frontend.qt inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4

# 2. 使用完整对局录像（约 5.9 GB，未入 Git，来源见 inputs/Ja5-2RIOBXU_full.source.json）
python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --start 3600

# 3. 直接载入已完成的注册存档（自动定位存档帧并锁定注册，新建本次输出与历史）
python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --registration outputs/sam3_registration/<存档目录>
```

> 若使用 Conda 且未手动激活环境，可在命令前加 `conda run --no-capture-output -n <环境名>`。

**常用命令行参数**（完整列表与默认值见 [启动参数](frontend/README.md#启动参数默认值)）：

| 参数 | 说明 |
| --- | --- |
| `--start <sec>` / `--seconds <sec>` | 起始秒数与播放时长；省略 `--seconds` 默认播放至视频末尾 |
| `--registration <dir\|prompts.json>` | 载入已完成注册存档并定位到存档帧 |
| `--device <cuda:0\|cpu>` | 指定 PyTorch 推理设备（默认自动选择显存最大的 GPU） |
| `--segmentor <id\|path>` | 首帧注册用 SAM3 模型 ID 或本地权重目录（默认 `facebook/sam3`） |
| `--tracker <edgetam\|sam3\|cutie>` | 传播后端（默认 `edgetam`） |
| `--inference-fps <hz>` | 追踪推理频率上限 |
| `--profile` | 导出同步计时与运行配置日志到 `outputs/tracking_comparison/` |

### 目录导航

```text
application/                无窗口比赛核心（MatchApplication、MatchSession、串行模型队列、异步托盘与历史）
frontend/
  qt/                       Qt Quick 桌面客户端（注册、Live 控制台、恢复、重标定、地形、Replay、Debug）
  arguments.py              视频命令行参数定义
  shared/layers.py          规则几何查询叠加层
  image/                    独立单图分割与注册查看器
components/
  game_data.py              本局共享状态与观测快照
  history.py                后台 SQLite 历史写盘与索引查询
  motion_history.py         独立平移／旋转事件检测
  replay.py                 历史索引与步进场景重建
  recalibration.py          桌角、mask 与标注跨标定坐标迁移
  registration/             军表 PDF 解析、单位目录、绑定与 reference 导出
  boundary_detection/       LSD 桌角检测、托盘拟合（tray/）与 Canny 诊断
  homography/               俯视拉正与坐标变换
  sam3/                     SAM3 图像／点提示／视频模型接口
  tracking/                 EdgeTAM / Cutie 视频传播与自动／手动恢复
  dinov2/                   冻结 DINOv2 特征提取与候选匹配
  facing/                   实验性 DVMNet 正面选边（默认停用）
  game_rules/               独立 KoW4 mini 距离、LOS 与采样移动规则计算
  image_io/                 支持 Unicode 路径的图像读写
  video_io/                 本地视频解码与时间戳读取
  real_esrgan/              可选 Vulkan 4× 超分工具
tools/                      独立命令行入口（见下表）
design/                     Qt UI 交互稿与独立注册预览
inputs/                     示例视频片段、测试图片与军表示例（大视频已忽略）
outputs/                    运行输出、模型缓存与隔离依赖（已忽略）
```

> 算法组件不导入 `frontend/` 或 `tools/`，可直接从 `components/` 调用（例如 `from components.boundary_detection.table import detect_table`）。LSD 配置位于 [config.toml](components/boundary_detection/config.toml)，几何长度参数以百分比配置（`5` 表示短边的 5%），物理尺寸统一使用 mm / in。

### 独立命令行工具

在项目根目录运行 `python -m tools.<工具名> --help` 查看完整参数：

| 工具 | 用途 |
| --- | --- |
| `setup_tracking` | 准备 EdgeTAM / Cutie 固定版本源码、权重及隔离依赖 |
| `setup_facing` | 准备实验性 DVMNet 源码、权重及依赖 |
| `read_unit_list` | Mantic Companion PDF 军表转注册类型 JSON |
| `table_detector` | 单图桌角与四边自动检测 |
| `pick_table_corners` | 单图手动选取桌角坐标 |
| `boundary_detection` | LSD 原始结果、逐步交互诊断与导出 |
| `canny` | 轮廓及可选 Hough 对照实验 |
| `homography` | 图像与四角到俯视拉正图及坐标变换矩阵 |
| `sam3_segmenter` | 单图文本提示（默认 `miniature`）实例分割 |
| `sam3_click_segmenter` | 单图多目标点击分割与透明切图 |
| `sam3_image_registration` | 单图自动检测、人工增删与多边形注册 |
| `tray_detector` | 从 mask 与物理尺寸拟合托盘矩形候选 |
| `project_units` | 俯视战场托盘、mask 投影与图层导出 |
| `update_type_features` | 从已完成注册生成／更新 DINOv2 参考特征库（NPZ） |
| `evaluate_recovery` | 离线评估 SAM 候选与缺失单位的 DINOv2 检索表现 |
| `query_rules` | 对导出的 `scene.json` 执行距离、LOS 或移动查询 |
| `super_resolution` | Real-ESRGAN Vulkan 备用 4× 图像增强 |
| `image_io` | 支持 Unicode 路径与通道保留的图像读写转换 |

### 延伸文档

| 文档 | 内容 |
| --- | --- |
| [Qt 客户端操作说明](frontend/qt/README.md) | 注册、Live 控制台、恢复、重标定、地形、Debug 与 Replay 交互细节 |
| [前端架构与参数说明](frontend/README.md) | 命令行默认值、工作流边界、DVMNet 实验记录与共享数据结构 |
| [无窗口应用核心](application/README.md) | `MatchApplication` 命令接口、快照契约与异步调度 |
| [视频追踪与恢复](components/tracking/README.md) | EdgeTAM / Cutie 接口、裁剪策略与自动／手动恢复边界 |
| [军表与注册数据](components/registration/README.md) | 双军表编号规则、PDF reader 与 reference 导出格式 |
| [边界与托盘检测](components/boundary_detection/README.md) | LSD 桌角流程与[托盘拟合回退策略](components/boundary_detection/tray/README.md) |
| [规则原型](components/game_rules/README.md) | 距离、LOS、采样移动定义与[示例场景](inputs/rules.example.json) |
| [项目思路.md](项目思路.md) / [TODO.md](TODO.md) / [待澄清列表.md](待澄清列表.md) | 设计 rationale、算法实验记录、实施进度与已确认需求基线 |
