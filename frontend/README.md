# 桌面视频界面

已完成注册可通过两客户端共用的 `--registration DIRECTORY` 或 `--registration DIRECTORY/prompts.json` 载入，Qt 注册页另有 `Load registration`。存档帧覆盖起点，恢复原ID／mask／标定／属性并锁定注册；模型就绪后播放，每次新建reference和history，不恢复中途追踪状态。Qt示例见 [Qt入口](qt/README.md)。

当前实时facing暂时停用，代码和注册初始资料保留；直播不再显示Missing及facing关注提示。后台失败锁／自动恢复／手动Recover仍有效，不能把隐藏提示理解为追踪正常。

`Masks`／`Trays`（以及旧客户端 `M`／`T`）仅控制叠加层绘制显示；隐藏托盘图层不停止后台矩形拟合，直播 `Distance`／`LOS`／`Move` 查询始终使用持续更新的已接纳托盘几何。

首帧先检测并确认桌面边界，再确认桌面长宽，用 Homography 拉正并聚焦战场，进入单位注册与传播流程。窗口显示和交互放在 `frontend/`，运行／业务流程归 `application/`，模型及算法留在 `components/`。界面文案使用英文。旧客户端使用 OpenCV；新 [Qt 客户端](qt/README.md) 已接入真实注册、Live 单位菜单／几何查询，以及恢复／B08／资料地形编辑／回放的辅助入口。部分受控路径已检查，真实模型、候选确认与重标定成功等路径仍待验收；完整验证前保留旧客户端。

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30
```

视频路径为必填；起点默认 0 秒，省略 `--seconds` 播放到片尾，显式传正的有限秒数才限定区间。无需传军表参数，注册界面通过 `Import list A`／`Import list B` 分别选择单方 PDF 或 JSON。默认 [ABC 测试资料](../inputs/units.video_estimate.json) 放在 A 栏：Type 1 为 155 × 50 mm，Type 2／3 为 205 × 80 mm；B 栏等待导入。这些值来自假定桌面尺寸的近似换算。独立 [read_unit_list](../components/registration/README.md#pdf-军表-reader) 工具及原命令行入口仍可使用。

## 启动参数默认值

Qt 与 OpenCV 共用 `frontend/arguments.py`，未传参数时的有效设置如下；手动指定的命令行值覆盖对应默认值。

| 参数 | 默认值／行为 |
| --- | --- |
| `video` | 必填，无默认视频 |
| `--start` | 0 秒，选作注册首帧 |
| `--seconds` | 不限时，播放到视频末帧 |
| `--units` | `inputs/units.video_estimate.json`，ABC 测试目录；可由 A／B 导入替换 |
| `--inference-fps` | 不额外限速；指定正数时才限制调度频率，源视频保持自身时钟／帧率 |
| `--preview-width` | 960 像素的初始画面宽度，提示仍用完整拉正帧坐标 |
| `--device` | 自动选显存最多的可用 GPU，无可用 GPU 时 CPU |
| `--segmentor` | `facebook/sam3`，初始分割模型 checkpoint |
| `--tracker` | `edgetam`，可选 `sam3`／`cutie` |
| `--tracker-model` | 使用所选后端默认模型；EdgeTAM 为 `yonigozlan/EdgeTAM-hf` |
| `--tracker-cache` | `outputs/model_cache` |
| `--profile` | 关闭额外 GPU 同步计时 |
| `--output-dir` | `outputs/sam3_registration` |

正式客户端不再提供 `--calibration`／`--board-size-in`，桌角和物理尺寸在界面确认（尺寸仍预填 72×48 英寸）。托盘搜索固定 adaptive：稳定时复用矩形，变化时局部拟合，失败完整回退。默认不额外限制追踪调度，worker 空闲时处理最新未消费源帧；只有显式 `--inference-fps` 才设置上限，`--stride` 已移除。串行执行和重复／已消费帧保护继续生效。`--tracker` 选择后端，`--tracker-model` 仅覆盖该后端权重。

算法试运行门槛另在 `application/config.py`：持续缺失 10 秒；EdgeTAM 单次自动恢复启用，相似度 0.85／分差 0.10；DVMNet facing 启用，候选角误差分差 20°。稳定托盘复用门槛为质心移动 2%／面积变化 10%／轮廓 IoU 0.90／可靠长轴 3°；动作记录为位置容差 10 mm／角度容差 10°／停稳 5 秒。这些与播放时限独立，属于现有试运行设置，不是精度校准结果。

## UI 重构设计与 Qt 接入（D33／D34）

最新 Qt 修订统一采用 [竖排信息卡／右半环参考](../design/ui/live/unit-info-reference.png)，边缘通过整体限位／缩放保持格式。Distance 数值直接标在测量连线上，不展开结果抽屉；LOS／Move 仍用抽屉，Distance 提示及完成操作留在控制栏。

前置的应用核心解耦已按 D35／I14 迁出主体，以 `292dc30` 保存阶段 checkpoint；完整验收仍开放，见 [前端解耦重构计划](../前端解耦重构计划.md)。现有 OpenCV 和新 Qt 客户端都通过 application 命令及快照工作。Qt 已接入注册及 Live 主交互；下文的恢复／回放及完整规则表单等操作仍描述 OpenCV 完整客户端。

2026-11-10 确认先设计、再实施／重构：操作者控制台沿用现有流程和视频为主结构，但重做交互；新增独立观众窗口，自动跟随控制台 Live／Replay／What-if 模式。Qt 当前为一个操作者主窗，完整旧流程另有 OpenCV 入口；双窗口和 What-if 没有因交互草图而成为现成功能。设计方案、待评审边界与实施状态分别见根目录《项目思路》《待澄清列表》及 TODO I13。

后续 D34 已选择底部抽屉：日常默认 Select，直接点单位展开环形 Move／Distance／LOS 及详情，不保留 Selected unit 下拉和重复尺寸／朝向字段；不确定项只按需显示 Estimated: mask／facing／mask + facing。手绘稿后的单位选中交互已认可为设计基线：左侧只读 Damage／Speed、右侧半环动作，菜单固定而选中框继续跟踪。Damage 编辑待后续；该版 Live 主交互现已接入 Qt，并完成受控主路径检查，其他模式及辅助流程继续另行迁移。

参考文件随仓库存档：以 [单位半环／底部抽屉](../design/ui/unit-radial-console.html) 为当前设计基线，[早期双布局比较](../design/ui/match-console-wireframes.html) 仅供查看取舍。两者是样例内联 HTML，详细适用范围见重构计划第 1.1 节。

### 单窗口 Qt 注册预览（D36）

独立样例位于 [design/ui/registration](../design/ui/registration/preview.py)，只读已有注册画面／mask，提供 A／B 示例类型、类型绑定及正负点／撤回；没有 SAM 推理或 reference 导出，不影响下文的正式 OpenCV 流程。用户已认可此技术方向，完整 UI 尚未迁移。

```powershell
# Optional Qt modules are isolated from the model environment.
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m pip install --target outputs/ui_preview/deps -r design/ui/registration/requirements.txt
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' design/ui/registration/preview.py
```

默认样例为本地 `outputs/sam3_registration/frame_458b250a48ea`，可传 `--reference` 指向其他包含 `frame.png`、`instances.json` 及对应 mask 的已完成注册目录。`Assign type` 下先点 mask 再点列表；`Point prompts` 下左正右负，仅显示提示点；`Undo`／Ctrl+Z 撤回草稿，`Finish preview` 只锁定预览，`Reset draft` 重来。数据始终只在内存。

## 操作流程

启动时立即在后台加载模型，同时读取区间首帧并执行现有 LSD 桌面检测。第一屏在原图上突出 `TL / TR / BR / BL` 四个桌角，下方大字询问 `Are the table corners aligned?`，提供两个主要操作：

- 准确：点击 `YES / Continue` 或按 `Y`／`Enter`，锁定四角并进入尺寸确认页。
- 不准确：点击 `NO / Manual correction`，或按 `N`／`M`，任意顺序点击四个桌角，程序自动排序并标注角名，再确认。
- 检测失败：直接进入手动模式；重复点、共线点或不能形成凸四边形的四点不能确认。
- 手动模式提供 `Undo` 和 `Clear` 按钮；也可用右键、`Ctrl+Z`／`U` 撤回，`R` 清空。四点齐全后仍可撤回；`A` 重新自动检测，`Esc` 退出。

尺寸页显示 `Length (in)` 和 `Width (in)` 两个输入栏，默认 72、48，分别对应 TL→TR 的横向长度和 TL→BL 的纵向宽度。点击输入栏或按 Tab 切换，输入数字会替换被选中的默认值，支持小数、退格、Ctrl+A 和 Enter；空值、零和非有限值不能继续。`Back to corners [B]` 返回四角检查，手动标记的 Undo 仍可用。尺寸在此界面确认，不再通过启动参数预填标定或尺寸。

确认尺寸后复用 Homography 组件，将桌面四边形拉正为矩形并填满战场画面，同时建立毫米坐标。默认 72 × 48 inches 是临时测试假设，尺寸确认不等于真实测量。注册显示、SAM 输入、mask 和 reference 裁剪使用拉正图像坐标；托盘、地形及正面另保存原视频像素锚点，毫米和显示坐标为带标定版本的派生值；每一版标定期间沿用同一变换和尺寸，镜头变化后需显式重新标定。修改外部标定的尺寸时同步缩放其两轴毫米坐标。

原始桌角和确认的英寸／毫米尺寸保存在最终 `prompts.json.table_boundary`，角点坐标空间为 `source_image_pixels`。注册元数据标明 `rectified_table_pixels`，保存原视频尺寸、拉正尺寸及正反矩阵；同样的信息会随每个 reference 保存。手动点不受图像四象限限制，强透视或接近菱形时仍需核对角名。

进入注册后：

侧栏上方点击 `Import list A [O]`／`Import list B [P]`，直接选择各方的 Mantic Companion PDF，或选择已有的单方类型 JSON。可在模型准备期间先导入。下方左右两栏分别显示 Type 1、Type 2…，附兵种／编制和配置摘要；鼠标滚轮只滚动所在的一栏。文件读完并通过验证后才替换该方列表；取消或失败保留原名单。重新导入某方会解除该方的旧类型绑定及正面标记，保留分割 mask 和另一方的绑定，按新名单重新对应即可。一个按钮一次只接受一方名单，不接受双方合并的 JSON。

1. 权重从启动即加载，首帧特征则等待桌角、尺寸确认和 Homography 完成后，在拉正首帧上计算；不预先计算原图特征。全部准备完成才接受单位提示。加载权重显示已完成项数和百分比，准备模型、转入 GPU 和首帧特征计算等阶段显示滚动条；就绪后自动隐藏。首次点击仍需提示解码和记忆编码，实际耗时需实测。
2. 默认是分割模式：左键添加正点、右键添加排除点，`N` 新建对象。可以先分割所有目标，不指定任何 type。
3. 按 `Tab` 或侧栏模式按钮切换到标注模式：点击 mask 再点击某方 type，也可以直接把 type 拖到 mask 上。List A 的 Type 1 对应内部类型 A1，实例依次生成 A1.1、A1.2；List B 的 Type 1 则生成 B1.1 等。按下 type 时不绑定，释放到目标才生效；拖到空白处取消。已绑定的 mask 可以重复选中并改绑，同 type 保留编号，换 type 释放旧编号而不重排其他单位。选中目标显示白色轮廓。
4. `S` 完成注册，或按空格完成并播放：统一保存一次最终 reference，锁定点及类型修改，然后传播 mask。
5. 首次成功播放后，自动隐藏类型侧栏、注册按钮和提示点，保留视频、MASK／TRAY、回放、重新标定和规则工具。播放期画面与源时钟持续运行，Space／Q 清除工具并回到最新实况，不提供 Hold／显示暂停；区间结束仍保持播放布局。`R` 恢复注册界面并开始新注册，实况页的 `Esc` 关闭窗口，回放页的 `Esc` 返回实况。开始播放后始终锁定 SAM 提示、type 和尺寸编辑。

首次播放前可用 `Ctrl+Z`／`U` 撤回点提示，`Unbind`／退格键仅解除类型绑定。`Tab` 回到分割模式可继续修点，`N` 会自动进入分割模式以添加新 mask。标注模式下点击只选 mask，不添加 SAM 提示；改绑只更新单位信息与尺寸相关托盘候选，不重新分割。选择类型或切换标注模式时退出当前规则查询，避免查询拦截拖放。`B` 保留为重复绑定当前 type 的快捷键，正常点击／拖放无需它。首次播放后导入和类型编辑一并锁定；R 重置注册保留两份名单。

点击注册侧栏的 `Tray dimensions (mm)`，在独立窗口中批量填写尺寸：List A／List B 各一列，每个 type 显示编号、兵种／编制，以及 `Width (mm)`／`Depth (mm)`。宽指正面边长，深指前后长度；同 type 的实例共用尺寸。已有尺寸预填，两列分别滚动；两格都空表示未知，只填一格、非正数或非有限数会阻止保存。

`Save` 整表验证后更新内存目录，已有 mask 自动重新拟合；修改尺寸的实例需要再次用 F 标记正面。`Cancel`、Esc 或关闭窗口保留原值。模型准备期间也可填写；S／首次播放后锁定尺寸编辑，最终尺寸随单位目录和 reference 保存，R 保留编辑后的目录。原始 PDF／JSON 不被覆盖，重新导入某方仍以新目录为准，不自动套用旧手填尺寸。PDF 导入已按官方 FAQ v0.1 的类别＋编制表自动填入标准尺寸，明确毫米底座备注优先；未知／冲突仍为空并提示，不套用 ABC 估算值。尺寸窗口可人工覆盖，导入原值与依据另存 `dimension_inference`；旧 JSON 需重新导入原 PDF 才取得映射。缺少已绑定单位尺寸时，TRAY 仍提示 `NO SIZES`。

红绿提示点只显示当前对象；按 N 或选择另一个对象时，上一对象的标记隐藏，点提示数据仍保留。右侧不再提供上一／下一 mask 按钮，注册时仍可点击 mask、使用数字键或 `[`／`]` 选择目标。

视频按源帧率播放；默认 worker 空闲时处理最新未消费帧，可显式用 `--inference-fps 2` 将提交频率限制为每秒最多两次。每个视频帧先应用固定 Homography，再用于显示或 SAM 推理。模型忙时显示上一份结果，图层可能落后于当前视频；调试文字仅在注册布局中显示，无上限状态显示为 uncapped。

## 显示图层

- `MASK [M]` 按钮或 `M`：开关 mask 色块、轮廓和编号。
- `TRAY [T]` 按钮或 `T`：开关拟合托盘的矩形边框和编号。

两个开关独立，默认均打开；关闭图层不影响推理、注册、reference 或单位 ID。图层只在新结果／标注变化时重建，正常播放混合缓存后的像素。

矩形层使用现有 `fit_tray`，需要类型表中的 `dimension.width_mm/depth_mm` 和属于同一视频视角、以毫米输入的桌面标定：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/你的录像.mp4 --units inputs/你的类型表.json --seconds 30
```

标定需要 `image_to_board` 和 `board_size`，格式来自已有 Homography 工具。也可在完成注册前点击右侧 `Load tray calibration [C]` 或按 C，选择对应视频视角的毫米标定 JSON；已有 mask 和尺寸时会在后台补算矩形。只有像素拉正矩阵、未提供实际桌面尺寸的标定不能用于毫米托盘拟合。

毫米标定仍按原视频坐标提供，界面将其与拉正逆矩阵组合，使托盘拟合输入的拉正图像正确映射到实际平面。

TRAY 按钮显示当前状态：`NO CALIB` 缺标定、`NO SIZES` 缺已绑定单位的尺寸、`WAIT MASK` 等待分割结果、`FITTING` 后台计算中、`ON (数量)` 已有矩形、`CHECK FIT` 拟合未通过需检查、`NO FIT` 暂无可显示候选。未绑定尺寸或 mask 消失的单位不生成矩形，不使用 mask 包围框代替托盘。示例类型表的尺寸是示例值，不能代替实际测量。

首次绑定类型后，后台为已有 mask 补算矩形；之后每次传播使用同一推理帧和对应 mask 更新托盘。类型改绑会清除旧矩形并补算。拟合与 SAM 在一个后台线程串行执行，不占用窗口线程；单位较多时会增加图层更新延迟。矩形仍是待审阅候选，尚无真实视频精度结论。

## 结构

```text
frontend/__main__.py                 命令行入口
frontend/window.py                   OpenCV 窗口生命周期与事件循环
frontend/app.py                      流程组装、阶段衔接与输入路由
frontend/presentation.py             注册选择、几何工具／单位选择（不复制比赛事实）
frontend/registration/               首帧布局、提示点适配、军表拖放和尺寸表单
frontend/calibration/                桌角／尺寸草稿及绘制
frontend/live/                       LIVE 画面与只读失败名单
frontend/replay/                     历史场景绘制及键盘适配
frontend/recovery/                   候选绘制、点选和原实例拖放
frontend/geometry_tools/             几何工具控件和叠加缓存
frontend/scene_editing/              表单轮询、屏幕点收集及地形／正面绘制
frontend/shared/                    绘制、视口及图层
application/app.py                   无窗口比赛入口、tick、快照、reset／close
application/session.py               源时钟、结果接纳、generation、历史生命周期
application/task_worker.py           模型加载与串行任务
application/registration.py          点草稿、绑定、目录和一次 reference 发布
application/calibration.py           初始标定与独立 B08 事务
application/recovery.py              手动候选和目标确认
application/automatic_recovery.py    单次搜索、预算和审核阶段
application/geometry.py              同帧查询捕获、合并调度和结果版本
application/scene_editing.py          资料／地形／初始正面修改及失效
application/replay.py                历史索引／场景读取及游标
application/config.py                运行参数、模型门槛和项目根路径
application/contracts.py             FrameRef、命令回执与冻结快照
components/video_io/source.py        视频解码、帧号和源时间
components/game_data.py              本局共享数据、观测快照及矩形状态历史
components/history.py                独立后台历史写盘与按单位／源时间索引读取
components/motion_history.py         独立平移／旋转事件识别与中断分段
components/replay.py                 固定读取边界下的动作索引与历史场景重建
components/sam3/video/predictor.py   已有 SAM 模型与官方会话接口
components/registration/             单位表、mask 切图及最终快照保存
components/facing/                   源图去背景、DVMNet 适配与矩形正面边选择
components/boundary_detection/table.py  可复用桌角检测接口
components/boundary_detection/tray/  已有托盘拟合及批量适配
```

`VideoWindow` 通过 `window.app` 持有现有 `VideoApplication`。它组装窗口适配器并调用同一个 `MatchApplication`；TABLE／REGISTER／PLAYBACK／RECALIBRATE 来自应用快照。唯一 GameData 属于应用内部，UI 不能取得可写业务对象、worker 或视频句柄。S 锁定与开始播放分别处理；核心 tick 不依赖 render，恢复／B08／回放期间源时钟继续。

入口保持 `python -m frontend VIDEO` 和 `python -m tools.sam3_registration VIDEO`。无窗口驱动使用 `from application.app import MatchApplication`，接口说明见 [application](../application/README.md)。公共业务命令返回 accepted／rejected／pending；UI 显示拒绝原因，后台错误仍在对应流程中接纳。输入／文件错误转回执，内部合同违例不伪装为空结果。

业务修改先看 application 对应流程，界面修改看 frontend 对应 view／表单及 presentation.py。应用仅组合 components，不导入 frontend／Qt／Tk 或 HighGUI；独立图片与边界诊断窗口保持原有用途。回放由 application/replay.py 管理固定边界与游标，frontend/replay 只绘制；what-if、正式 Qt 迁移与观众窗口仍未实现。

本次核对了 Meta 官方跟踪源码、HF 文档和实际安装的 Transformers `5.18.0` 会话接口，继续使用现有提示更新和传播方法。参考：[Meta 跟踪源码](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_tracking_predictor.py)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)。目录拆分、图层开关及托盘结果衔接属于项目集成。

首帧准备调用公开的 `get_image_features` 和会话缓存方法；缓存键按本机后端源码对接，未添加虚拟对象或点提示。注册界面中的 `R` 仍回到同一首帧、保留已确认桌角，重新准备 SAM 会话；不会重新加载已就绪权重。

## 本局共享数据

[GameData](../components/game_data.py) 定义在一个文件中，每个工作流独立创建实例，不使用模块全局单例。新增公共业务数据在该类中增加明确字段，现有结构为：

```text
MatchApplication 内部的 GameData（不作为 UI 接口公开）
  board              原图大小、桌面毫米尺寸、桌角和 Homography
  units              UnitRoster：类型、单位实例、属性及 object_id 绑定
  rules              RuleState：人工／外观估计正面及地形
  current            最新显示帧、匹配的推理帧／结果／源帧时间、显示版本
  history            近 5～5.5 分钟矩形／状态缓存（另保留未写盘条目）
  history_store      当前注册的后台 SQLite 写入器，不属于分析快照
  global_history     进行中与近期的平移／旋转事件缓存
  motion_recorder    由有效几何源帧推进的事件识别器，不属于分析快照
  calibrations       各版本标定、源帧及 reference 来源
  tracking           按稳定 unit ID 保存可见性、缺失计时与失败锁定
  reference_folder   已完成注册的保存目录，也是注册锁定依据
```

`data.accept_observation(prediction, frame, metadata)` 接纳同一源帧的结果并更新正面估计；运行层核对任务 generation 后接纳后台结果；注册控制器在成功保存后启用失败判定和该次历史写入器。后续接纳传播结果或人工修改状态时记录历史。每条历史含独立 `sequence`、`kind`、接纳／操作时的 `frame_index`／`timestamp_seconds` 和几何自身的 `observation_frame_index`／`observation_timestamp_seconds`。两者可能不同，迟到几何不会把当前人工状态写到过去，也不能当作新的几何采样。按本局 `unit_id` 索引的 `units` 保存 type、有效属性、源坐标 `corners_source`／`center_source`、派生 `corners_mm`、`position_status`、追踪状态／可见性和 `state`（含 engaged／wavering／facing）。未知值保留 null，无有效托盘为 null／unavailable，available 不是准确率判断。相同源帧和内容不重复追加，同帧不同编辑按 sequence 保序。

`app.match.snapshot()` 发布冻结展示数据，图像／mask 共享只读引用；查询在应用内捕获同帧场景与来源信息，历史回放使用自身固定读取边界。Space／Q 清除工具并回到最新实况。R 清空当前观测、绑定及短缓存，保留类型目录、桌面标定、原有地形及旧数据库；旧待写批次继续重试。矩形历史包含 `calibration_version`，对应最终坐标变换和尺寸保存在数据库与 `data.calibrations` 中，旧历史不随重新标定改写。

## 短长历史存储

完成注册后，该次 reference 输出目录新增 `history.sqlite3`。现有 reference 文件不重写，数据库不存逐帧 mask／图像或选桌角中间记录。独立后台任务持续事务写入观测、人工状态／规则输入及最终标定版本；不占用模型队列。按接纳／操作源时间保留至少 5 分钟内存缓存，以 30 秒块淘汰已确认写盘的旧条目，正常约 5～5.5 分钟。

磁盘不可写／被锁时，各页面底部显示英文 `History not saved`，终端记录路径和原因；直播继续，每 5 秒重试。未写盘数据保留，内存可暂时超窗，恢复后再裁剪。关闭时等待在途批次并作最终写入尝试；若故障持续，会在终端报告尚未保存数量，退出后无法保证这些内存数据保留。

独立读取基础接口无需模型、UI 或 GPU：

```python
from components.history import read_unit_history, read_history_context

records = read_unit_history("outputs/sam3_registration/frame_.../history.sqlite3",
                            "A1.1", start=30, end=90)
context = read_history_context("outputs/sam3_registration/frame_.../history.sqlite3")
```

时间区间为包含两端的**接纳／人工操作源秒数**，每条返回记录只含指定单位，几何观测源时间另见 `observation_timestamp_seconds`。这些磁盘读接口只见已提交记录。回放组件另外合并打开时捕获的内存更新，见下方回放说明。全局事件与局部片段读取见下节，整场续赛恢复仍待实现。

## 全局移动与旋转事件

H03 将有效局部观测整理为独立的平移与旋转事件，两者允许同时发生、各自停稳结束。修改 [config.py](config.py) 后重启生效：

```python
MOTION_POSITION_TOLERANCE_MM = 10.0
MOTION_ROTATION_TOLERANCE_DEG = 10.0
MOTION_SETTLE_SECONDS = 5.0
```

平移看托盘中心，旋转看无向托盘轴。相对参考姿态的变化超出容差时开始／继续对应事件，之后新有效几何采样在 5 秒内都未再超出容差，才标为 `completed`。例如最后显著变化在 10 秒、15 秒确认停稳，终点保留 10 秒观测，另存 15 秒确认来源。起点是触发前一有效观测的估计；同帧刷新、人工改状态和推理等候不推进计时。

前后源姿态和稳定性锚点均投影到同一当前毫米标定比较，避免把 Homography 的变化当作运动；源画布和变换兼容时，重新标定本身不中断。事件起终点各存原版本，事件级版本及截图属于几何终点。

`ongoing` 为尚未确认停稳，`interrupted` 为真实位置缺失、几何失败、源坐标不兼容、人工恢复接回、模型错误、R 或关闭造成的记录中断，不算已完成一步。恢复后重新建立起点，不补缺口运动；停稳后继续移动则生成新事件。事件及相关局部记录同事务写盘，沿用写盘失败提示、保留内存和重试；新库为 v2，已有 v1 局部历史仍可读，继续写入时加表迁移。

```python
from components.history import read_motion_events, read_event_history

events = read_motion_events(history_path, "A1.1", start=30, end=90)
segment = read_event_history(history_path, events[0]["event_id"]) if events else None
# segment["event"] 是事件，segment["records"] 是对应的原始单位局部记录。
```

事件区间筛选使用**几何观测源时间**，返回与闭区间相交的事件。上一节局部记录的时间筛选使用接纳／操作时间。片段通过序号关联，包含停稳确认及中断证据；源坐标事件允许跨标定，每条局部记录保留原版本，旧事件仍按原单一版本边界读取。并行事件可以引用同一批记录。这些磁盘接口只见已提交结果。

## 历史棋盘回放

播放页点击 `Replay` 打开本次注册的历史，默认定位最后一个已完成动作；没有已完成动作时为初始 Step 0。关闭重开会重新定位到当时的末步。回放占主画面，以毫米平面中的矩形和实例 ID 表示单位。后台的视频源、追踪和历史记录继续运行。点击 `Back to Live` 或按 `Esc` 返回最新实况。

每步背景使用该动作终点的 Homography 后源输入截图，矩形和 ID 叠在对应标定的画面上。初始 Step 0 也保存截图，同一终点的移动／旋转共用图片。截图后台保存到本次注册的 `replay_frames/v版本_s序号.jpg`。停稳确认前暂存活动终点帧，完成后写盘。旧历史因标定切换中断时，后台按固定读取边界只读重建派生动作，原数据库不改写；优先采用历史阈值，真实缺失仍中断。其新得到的步骤缺少截图时，用独立读取器从原视频帧及当时 Homography 还原，不移动直播读取器；视频或截图无法读取时，显示基础棋盘和 `Step image unavailable`。新格式记录直接使用已存事件，不重扫整场历史。

- 初始注册为 Step 0。每个已完成 Move 或 Rotate 各占一步，按动作结束的几何源时间排序。同一结束时间先列 Move，再列 Rotate，并保留各事件的独立身份。
- `Previous`／`Next` 按钮、`←`／`→` 或 `A`／`D` 切换步骤。回放中的 D 用于下一步，实况中的 D 仍用于测距。首尾会停在有效步骤范围内。
- 同时完成的移动与旋转可以显示相同棋盘，当前动作的实例与类型会分别高亮。进行中和记录中断事件保留在历史中，步骤列表只包含已完成事件。
- `Refresh` 重新捕获最新历史边界，并按事件 ID 保留当前选择。打开后步骤列表固定，后台新增动作会在刷新后出现。
- 每步显示动作终点对应的完整观测与标定版本。页面分别标示几何观测时间和状态记录时间。不可用或已移除单位列出 ID，有效单位使用当时的矩形。

读取由独立后台任务执行。`capture_replay_inputs(data)` 在运行层线程捕获源路径、序号边界、近期记录与事件更新，`read_replay_index(inputs)` 合并磁盘与内存并形成步骤列表，`read_replay_scene(index, step_index)` 按终点序号读取整盘记录。超过内存窗口的场景从 SQLite 按需读取。初始注册名单固定，因此旧场景可按实例 ID 与序号使用既有索引定位。

首次写入尚未完成或磁盘不可用时，完整内存记录可直接构建回放。如果较早记录已经淘汰且磁盘无法读取，页面显示读取失败，保留刷新和返回入口。R 开始新注册并清理回放，过期读取结果通过会话与请求版本过滤。

后续可行提升是从 5 秒停稳等待期内选择遮挡较少、整盘有效几何与终点一致的帧。此选帧策略保留为待实现项，设计见项目思路。

当前提供本次注册的离散切步。外部比赛选择、时间滑块、自动播放速度与运动插值保留在 TODO 中。v1 历史没有动作事件，可通过读取接口查看初始棋盘。

容差是尚未视频调参的初值。净位移／估计净转角不是实际路径长度，往返也可能形成净变化为零的事件。矩形轴有 180° 歧义，近方形另有 90° 歧义，无法保证识别所有真实转身。容差须为正有限数，旋转容差须小于 45°；采样稀疏或变化小于容差时，事件可能延迟触发或提前判断停稳。

## 追踪失败判定与只读名单

完成注册后启用持续无 mask 判定。修改 [config.py](config.py) 的 `TRACKING_DISAPPEARANCE_SECONDS` 可调整缺失阈值，默认 10 秒，须为正的有限数；程序启动时读取，不新增设置控件。首次无有效 mask 的源视频时间保存为 `disappeared_time`，不同源帧的后续缺失观测才推进计时。阈值前恢复非空 mask 自动清零；单纯卡顿、同帧刷新和显示冻结不累计新的失败证据。

`app.session.data.tracking[unit_id]` 保存 `visibility`（最近一次是否有非空 mask）、`status`（tracking／pending／failed）、`disappeared_time`、最近观测帧／时间／标定版本及 `last_accepted_position`。最后位置有自己的源帧与版本；它表示按当前业务假设曾被接纳，不是测得的身份置信度。显式 `routed=True`／`removed=True` 的属性令记录不在场并排除失败名单；正式移除编辑入口尚未实现。

EdgeTAM 超时先进入自动搜索，未能接回才在播放页出现 A／B 双列；名单显示 ID、type、Damage 摘要及最后位置时间，支持分别滚动，没有 Damage 时显示 `?`。失败后原追踪器自行返回的 mask 标为 `[Estimated]`，仍保持失败，不进入规则、朝向更新或有效位置历史；独立恢复流程确认后才解除锁定。已有 mask 但拟合失败只导致几何不可用，不进入这份失踪名单，旧位置不自动填回。非 EdgeTAM 后端保留原失败显示流程。

EdgeTAM 失败实例先进入内部 Missing；`recovery_phase=queued/searching` 时不列入人工名单。串行 worker 进行一次 SAM 文本搜索与 DINO 匹配，全部当前 Missing 参考用于防止实例竞争，但只有本轮 queued 实例收到尝试；不按帧重复搜索。正常实例 mask 有任意像素占用的候选即保守排除，其他实例争同一／重叠候选也不自动分配。可靠结果按原 ID 在同一观测帧接回；其余转 `review/manual` 并显示 A／B 人工名单。R 清空阶段，B08 作废旧候选并保留原 ID／失败锁。恢复不解锁首帧注册。

点击名单中的 ID 或 `Recover units` 打开恢复窗口；有候选时显示黄色 mask，`Correct` 确认、`No / Search again` 发起一轮新的单次搜索。`Clear / Retry` 丢弃候选并进入正负点手动补标；取消保留失败状态。候选尚未被接纳时持续传播但不写有效历史，一旦消失就作废；不能用旧确认接纳新候选。No 尚未实现跨帧排除被拒目标，因此可能再次提出同一区域，规则见 [CL08](../待澄清列表.md#cl08-单次自动尝试与-no-后的候选排除)。

配置位于 `application/config.py`：`AUTO_RECOVERY_ENABLED`（默认 True，仅 EdgeTAM）、`AUTO_RECOVERY_SIMILARITY=0.85`、`AUTO_RECOVERY_MARGIN=0.10`、`AUTO_RECOVERY_PROMPT="miniature"`、`AUTO_RECOVERY_DETECTION_THRESHOLD=0.30`。相似度与分差是用户选定的实验初值，不是概率或准确率；单个候选缺少第二名时交人工。SAM 文本模型与 DINO 在启动的串行加载阶段准备，加载失败保留普通追踪与手动路径，之后失败实例直接请求人工。搜索／确认期间源持续播放，额外推理可能增加观测年龄。

## 不停播的手动恢复（EdgeTAM）

播放页点击 `Recover units`。右侧 A／B 标签是本局已有实例，失踪单位可直接拖放；正常单位需先点 `Pick tracking error`，再点它当前的 mask，将其 ID 加入本次纠错草稿。不会新增实例或解锁最初注册。

1. 在直播画面左键点目标，SAM 生成初始 mask，独立 Edge 候选继续传播。之后左键正点、右键负点；等待一次补点结果期间不接受更多点，源和显示继续运行。
2. 满意后将原 ID 标签拖到黄色候选上；拖放就是确认，成功后返回实况，一次接回一个。候选丢失时不能提交，拖到其他正常单位占用的位置会被拒绝。
3. `Clear / Retry` 清空候选重来；`Cancel`／Esc／Q／Space 放弃未确认草稿。切工具、回放、B08 和 R 也会使草稿失效，迟到结果不生效。提交中的草稿按钮暂不可用。

**拖放前原关联仍照常记录和参与规则。** 取消主动纠错不新增失败或历史缺口，原本已失败的单位仍失败；这些是 D31 的明确选择。成功只解除目标的失败锁并清缺失计时，保留原 ID／属性／旧历史／初始参考。旧正面清除，mask 本身不恢复方向；有初始 F 参考且独立 DVMNet 选边成功时，可在对应观测重新取得实验性正面。运行期人工正面补充仍待 F06，方向未知时相关规则可能不可用。托盘拟合失败仍单独标为几何不可用。

候选显示观测时间；恢复计算可能增加观测延迟，但不停止视频源。手动点按实际已显示帧采样，确认前先让正常追踪与候选对齐，按同一帧正常 mask 检查占用，再接回原 ID；片尾也可使用。历史区分 `manual_recovery`、`reviewed_recovery` 与 `automatic_recovery`，保留操作／观测两种源时间和标定版本，只中断目标未完成动作，不把纠错跳转算作移动。图库追加及其他后端的恢复尚未实现。

## 比赛中重新标定

播放页点击 `Recalibrate [K]` 或按 K：

1. 按固定相机理想假设处理，直接显示持续播放的原始源画面；源时钟和旧标定下追踪继续。不执行相机运动检测，不因纹理不足拒绝进入或自动清空角点。打开时取消其他工具的未保存草稿，支持 k／K 和按钮。
2. Continue 等待最近有效观测及其同帧原始源图，将 mask 映射到新拉正图，保留原 object ID 和单位绑定，以原已加载权重建立独立新会话；新托盘依据实际尺寸重新拟合。
3. 新会话成功后切换标定，显示使用最新源帧，源时钟不重启。旧会话在成功前一直保留；准备新会话占用原串行模型队列，可能增加观测延迟，画面仍持续播放。
4. Esc／`Cancel / Return` 随时取消，包括初始化过程中；取消或被新一轮标定替代的结果不接纳。失败保留旧会话／标定，并持续显示失败原因，允许重试。地形和正面从原视频像素锚点投影到新标定；正面重新关联矩形轴并标为估计。

相机稳定是当前假设，运动检测及其专用配置已移除；桌角自动检测与手动选四角仍可使用。片尾主动发起 B08 时可请求迁移所需的同帧观测，不自动重启视频，也不加入通用片尾补算。

原 reference 保留初始图像与坐标来源，不重复导出。每次成功建立新标定递增版本，R 从最近一次标定帧重新注册，避免将新变换套到旧开局画面。原视频区间的结束位置保持。

迁移只使用当前可用 mask；完全丢失或移出旧画面有效范围的单位保留资料及历史，但不会凭旧位置补出新 mask，界面显示 `No tracking masks`。全部单位都无可用 mask 时拒绝应用，可取消后选择较清晰的帧重试。这不是 ID 恢复；仍需检查 mask 是否对应正确单位。源坐标接续沿用相机与桌面内容固定的理想假设；实际移动相机不属于单纯重选四角，不能把不同视角的原像素当作同一物理位置。

## 游戏信息与规则工具（首版）

当前采用 `KoW4 mini` 规则子集，提供托盘最近距离、基础 LOS 和普通移动／At the Double。冲锋、完整射击判断和自动战斗结算未加入；EdgeTAM 单次自动 ID 恢复已接入，见上文。规则来源与限制见 [game_rules](../components/game_rules/README.md)，需求核对见 [审计记录](../docs/Game%20information%20requirements%20audit.md)。

先确认物理比例。程序会在锁定桌角后显示默认 72 × 48 inches，在界面确认或修改：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30
```

完成尺寸确认后建立毫米平面和对应宽高比；也可继续载入原视频的有效毫米标定。没有有效托盘或缺少必要规则输入时工具返回 `Unavailable`。

完成 mask/type 绑定并获得托盘后：

1. 选中单位，按 `F`／`Set front`，点击托盘的正面边。这里只登记方向，不调用 SAM；再次 F 取消。正面需在第一次播放前登记，R 后重新登记；B08 保留兼容的源图参考，再按新托盘重选正面边。
2. 按 `E`／`Unit rules`，核对 `Speed (inches)`、`Rule Height`、`Side`、`Unit kind`、特殊规则及当前 `Engaged`／`Wavering`。type 属性作为默认值，实例属性覆盖它。表单 Save 明确确认状态；缺失字段保留未知，不把旧 `movement` 字段自动当作英寸 Speed。播放后仍可手动更新这些规则信息，已经保存的初始 reference 不会因此重写。
3. 按 `G`／`Terrain`，在拉正画面依次点出地形区域，点回起点闭合，填写 label、类别和规则 Height。`U`／Ctrl+Z／右键撤回草稿顶点，`Undo terrain` 按钮也可移除最后一个已登记地形；再次 G 取消草稿。仅玩家登记的地形参与计算，SAM 杂物不会自动成为障碍。
4. S 或首次播放保存初始规则输入。有毫米标定及已绑定单位时，最终目录额外生成 `scene.json`，可交给独立规则工具。

| 操作 | 用法 |
| --- | --- |
| `Distance [D]` | 点击两个单位，显示托盘最近点连线和 mm／inches |
| `LOS [L]` | 按观察者、目标的顺序点两个单位；显示可用视线或不确定原因 |
| `Move [V]` | 点击一个单位；重复 V 循环 Advance、Back、左右 Sidestep、Change Facing、Halt |
| `Double [J]` | 点击一个单位，估计 At the Double 的可达姿态 |
| `Q` | 清除规则查询和选择，返回原有交互 |

选择规则查询时画面继续播放，选中的实例随最新有效观测重新计算；一次查询中的托盘和规则输入仍取自同帧场景。结果显示 `Observed` 源时间与年龄，正在等待新结果时标为 `Updating`，过期几何图层暂不叠加。Space／Q 清除工具并回到最新实况，不解除注册锁。规则计算使用独立后台线程并合并待算观测，旧代次结果不能覆盖已清除或换标定后的结果。蓝色点表示采样到的可达**中心位置**，每个姿态的路径及朝向由组件返回；没有实心填充样本凸包，也没有宣称采样以外不可达。

Unit rules 和闭合地形后的资料窗口由主循环轮询，填写、校验报错和保存期间源播放、追踪及历史继续。Cancel／Esc／关闭窗口放弃草稿，R、切换标定、进入回放或关闭程序会取消尚未应用的编辑；保存针对原实例，迟到结果不能写给另一个绑定。

LOS 找到清晰采样线时提供证据；没找到只能返回 `Uncertain`。原型只在目标完全不在前方弧时直接返回 `Blocked`；场景存在未拟合单位时不会将该不完整场景的射线升级为确定清晰。Hill、地形内外及 Height 等仅按已登记区域计算，未登记障碍仍可能改变结果。

当前支持普通单位、War Engine 的部分例外以及 Fly／Pathfinder／Leaper。Individual 移动暂不可用，未支持特殊规则会显示警告。DVMNet 辅助正面选边已试接入，但真实 180° 转身、方形 90° 对称和拒判可靠性仍待验证。单位定位和规则输入未做实际视频精度评估；视频采用第三版或其他规则包时不可当作第四版完整裁决。

### DVMNet 辅助正面

**已接入按需恢复：**平时用矩形连续性维护正面侧和角度，并做轻量外观检查。仅方向可疑时调用 DVMNet，不运行 DINO 或替换 mask；实例恢复时先由 SAM／DINO 接回原 ID，再强制独立恢复方向，两者成功状态独立。

首帧用 F 标正面，完成注册后冻结该单位同帧参考。轻量检查将源图按托盘及候选正面归一化为 48×48 小图，在共同 mask 前景内比较颜色纹理；背景不参与分数。非方形比较相反两侧，方形比较四侧。当前方向匹配低、替代方向明显更好，或当前不可比而替代方向有支持，连续两次不同源帧满足才调用 DVMNet。前景／纹理不足时不给匹配分数，不将其当作已确认正确。

DVMNet 只选择当前矩形的正面边，**精确角度始终来自矩形**。模型参考和当前目标均从源图取图，用各自 mask 去背景并填 RGB(124,116,104)。轻量检查只触发恢复，不直接翻转正面；其基准只在初始 F 或成功接纳模型结果时更新，初始图库和模型冻结参考不追加。

仅方向可疑时，等待恢复以及恢复失败后均保留原正面侧关联为 Estimated，角度随有效矩形更新。箭头为琥珀色，状态区显示 Facing recovery pending／failed；规则可继续使用 Estimated，并提示警告。没有初始 F、真实追踪／几何不可用，或 mask 接回后独立方向恢复失败且无旧值可回退时，正面仍 unknown，不画箭头。方向失败不会加入 A／B 身份 Missing 名单，也不打断位置动作。

恢复失败后，目标外观相较失败样本明显变化、且满足最小源时间间隔才重试。正常检查和等待不会逐帧调用模型。显示的 facing n/m 是已有方向／参与检查实例数，不是准确率。

首次准备资源（本机已准备）运行：

```powershell
python -m tools.setup_facing
# 复用已有离线实验资源，避免重复下载
python -m tools.setup_facing --reuse-experiment outputs/dvmnet_experiment/20261110
```

配置在 `application/config.py`；下列数值均为可调整试验参数：

| 设置 | 默认值 | 用途 |
| --- | --- | --- |
| DVMNET_FACING_ENABLED／DVMNET_FACING_CACHE | True／outputs/model_cache/dvmnet | 启用及资源位置 |
| FACING_CHECK_MIN_SIMILARITY | 0.35 | 当前相关性过低，或当前不可比但替代方向获得支持 |
| FACING_CHECK_ALTERNATIVE_MARGIN | 0.15 | 替代方向领先当前方向的分差 |
| FACING_CHECK_CONSECUTIVE | 2 | 连续不同源帧的可疑观测数 |
| FACING_CHECK_MIN_COVERAGE | 0.25 | 小图共同有效前景占比下限 |
| FACING_RETRY_APPEARANCE_CHANGE | 0.12 | 失败后新外观证据的变化量下限 |
| FACING_RETRY_MIN_SECONDS | 2.0 | 失败后最小重试间隔，还须有新外观证据 |
| FACING_EDGE_MARGIN_DEG | 20.0 | DVMNet 粗方向选边的角误差分差保护 |

相关性使用前景 RGB 分通道去均值的归一化相关，范围 -1～1。新外观通常取前景平均绝对 RGB 差（像素为 0～1）；两样本各有足够前景但共同区域不足时，取 mask 的 1-IoU。参数不是方向概率；真实光照／遮挡和对称转向的误触发／漏检尚未校准。

模型在启动串行队列内加载并预热；播放中的轻量检查和恢复都使用同帧 mask／托盘，源持续播放。加载错误独立显示，普通追踪继续。B08 保留兼容参考及检测状态，R 清除并丢弃迟到结果；仅在对应观测被接纳后提交检测器状态。历史保存阶段、分数、是否调用模型及最近独立判定来源，不保存小图或改写旧记录。H03 仍按无向托盘轴识别旋转，不新增 180° 正面变化事件。关闭功能时沿用原矩形连续性，其自身仍有对称歧义。

资源、官方固定源码及依赖位于忽略缓存，权重校验和安全加载由组件执行，不复制进受版本管理代码。外部许可边界、实测和未验证范围见根目录《项目思路》2026-11-10 接入节。
## 追踪优化实验选项

正式客户端固定 adaptive：质心／形状稳定时复用上一接纳矩形，变化后先局部拟合，失败才完整搜索。更换类型尺寸／标定或 R 重置不复用不兼容的旧解。底层 full／local 接口保留作无窗口对照，不再提供客户端 `--tray-search` 参数。界面分别显示 SAM 操作与托盘耗时。

`--profile` 开启 SAM3 GPU 分段同步并导出任务计时到终端给出的 `outputs/tracking_comparison/sam_.../`；额外同步可能影响速度，和正常模式分开比较。候选后端记录包含后处理／回传的操作总时延，不伪造细分 GPU 时间。

`--tracker sam3|cutie|edgetam` 选择注册后的传播模型，默认 `edgetam`（`application/config.py` 的 `DEFAULT_TRACKER`）。首帧仍使用 SAM3；所选模型一起在启动时加载，首次播放交接 masks 后才启动视频源时钟。候选初始化和重置由同一工作线程串行执行。设置、权重来源和启动命令见 [tracking](../components/tracking/README.md)。LK 已移除。

2026-11-08 已完成现有播放后入口的持续显示／不停源改造。首帧注册仍按原约定编辑并一次保存；手动恢复、单次自动搜索及候选审核于 2026-11-09 接入。自动门槛的准确率验证、拒绝排除及 what-if 布局问题仍见根目录 [待澄清列表](../待澄清列表.md)。

桌角自动检测失败会保留橙色候选边、缺边原因及 Retry／Manual 按钮；不会直接跳到空白手动页，也不会把无效候选当成成功。手动页提供 Auto 重试，手动输入继续优先于迟到的自动结果。
