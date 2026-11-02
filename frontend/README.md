# 桌面视频界面

首帧先检测并确认桌面边界，再确认桌面长宽，用 Homography 拉正并聚焦战场，进入单位注册与传播流程。窗口显示和交互放在 `frontend/`，模型及算法留在 `components/`。界面文案使用英文，使用现有 OpenCV 窗口，不增加依赖。

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30
```

视频路径为必填；起点默认 0 秒，区间默认 10 秒。无需传军表参数，注册界面通过 `Import list A`／`Import list B` 分别选择单方 PDF 或 JSON。默认 [ABC 测试资料](../inputs/units.video_estimate.json) 放在 A 栏：Type 1 为 155 × 50 mm，Type 2／3 为 205 × 80 mm；B 栏等待导入。这些值来自假定桌面尺寸的近似换算。独立 [read_unit_list](../components/registration/README.md#pdf-军表-reader) 工具及原命令行入口仍可使用。

## 操作流程

启动时立即在后台加载模型，同时读取区间首帧并执行现有 LSD 桌面检测。第一屏在原图上突出 `TL / TR / BR / BL` 四个桌角，下方大字询问 `Are the table corners aligned?`，提供两个主要操作：

- 准确：点击 `YES / Continue` 或按 `Y`／`Enter`，锁定四角并进入尺寸确认页。
- 不准确：点击 `NO / Manual correction`，或按 `N`／`M`，任意顺序点击四个桌角，程序自动排序并标注角名，再确认。
- 检测失败：直接进入手动模式；重复点、共线点或不能形成凸四边形的四点不能确认。
- 手动模式提供 `Undo` 和 `Clear` 按钮；也可用右键、`Ctrl+Z`／`U` 撤回，`R` 清空。四点齐全后仍可撤回；`A` 重新自动检测，`Esc` 退出。

尺寸页显示 `Length (in)` 和 `Width (in)` 两个输入栏，默认 72、48，分别对应 TL→TR 的横向长度和 TL→BL 的纵向宽度。点击输入栏或按 Tab 切换，输入数字会替换被选中的默认值，支持小数、退格、Ctrl+A 和 Enter；空值、零和非有限值不能继续。`Back to corners [B]` 返回四角检查，手动标记的 Undo 仍可用。`--board-size-in` 可预填其他英寸尺寸，外部 `--calibration` 则使用其毫米宽深换算后预填；两参数不能同时使用。

确认尺寸后复用 Homography 组件，将桌面四边形拉正为矩形并填满战场画面，同时建立毫米坐标。默认 72 × 48 inches 是临时测试假设，尺寸确认不等于真实测量。注册、播放、SAM、mask、托盘和 reference 都使用拉正图像坐标；每一版标定期间沿用同一变换和尺寸，镜头变化后需显式重新标定。修改外部标定的尺寸时同步缩放其两轴毫米坐标。

原始桌角和确认的英寸／毫米尺寸保存在最终 `prompts.json.table_boundary`，角点坐标空间为 `source_image_pixels`。注册元数据标明 `rectified_table_pixels`，保存原视频尺寸、拉正尺寸及正反矩阵；同样的信息会随每个 reference 保存。手动点不受图像四象限限制，强透视或接近菱形时仍需核对角名。

进入注册后：

侧栏上方点击 `Import list A [O]`／`Import list B [P]`，直接选择各方的 Mantic Companion PDF，或选择已有的单方类型 JSON。可在模型准备期间先导入。下方左右两栏分别显示 Type 1、Type 2…，附兵种／编制和配置摘要；鼠标滚轮只滚动所在的一栏。文件读完并通过验证后才替换该方列表；取消或失败保留原名单。重新导入某方会解除该方的旧类型绑定及正面标记，保留分割 mask 和另一方的绑定，按新名单重新对应即可。一个按钮一次只接受一方名单，不接受双方合并的 JSON。

1. 权重从启动即加载，首帧特征则等待桌角、尺寸确认和 Homography 完成后，在拉正首帧上计算；不预先计算原图特征。全部准备完成才接受单位提示。加载权重显示已完成项数和百分比，准备模型、转入 GPU 和首帧特征计算等阶段显示滚动条；就绪后自动隐藏。首次点击仍需提示解码和记忆编码，实际耗时需实测。
2. 默认是分割模式：左键添加正点、右键添加排除点，`N` 新建对象。可以先分割所有目标，不指定任何 type。
3. 按 `Tab` 或侧栏模式按钮切换到标注模式：点击 mask 再点击某方 type，也可以直接把 type 拖到 mask 上。List A 的 Type 1 对应内部类型 A1，实例依次生成 A1.1、A1.2；List B 的 Type 1 则生成 B1.1 等。按下 type 时不绑定，释放到目标才生效；拖到空白处取消。已绑定的 mask 可以重复选中并改绑，同 type 保留编号，换 type 释放旧编号而不重排其他单位。选中目标显示白色轮廓。
4. `S` 完成注册，或按空格完成并播放：统一保存一次最终 reference，锁定点及类型修改，然后传播 mask。
5. 首次成功播放后，自动隐藏类型侧栏、注册按钮和提示点，保留视频、MASK／TRAY、显示冻结／返回实时及规则工具。Space 冻结／恢复显示，视频源和追踪继续前进；区间结束仍保持播放布局。`R` 恢复注册界面并开始新注册，`Esc` 关闭。冻结不会重新允许编辑 SAM 提示或类型。

首次播放前可用 `Ctrl+Z`／`U` 撤回点提示，`Unbind`／退格键仅解除类型绑定。`Tab` 回到分割模式可继续修点，`N` 会自动进入分割模式以添加新 mask。标注模式下点击只选 mask，不添加 SAM 提示；改绑只更新单位信息与尺寸相关托盘候选，不重新分割。选择类型或切换标注模式时退出当前规则查询，避免查询拦截拖放。`B` 保留为重复绑定当前 type 的快捷键，正常点击／拖放无需它。首次播放后导入和类型编辑一并锁定；R 重置注册保留两份名单。

PDF 没有托盘毫米尺寸时，导入后 TRAY 会提示 `NO SIZES`；需另行提供真实尺寸或使用补有 `dimension` 的单方 JSON。不会把旧 ABC 估算尺寸自动套给真实兵种。

红绿提示点只显示当前对象；按 N 或选择另一个对象时，上一对象的标记隐藏，点提示数据仍保留。右侧不再提供上一／下一 mask 按钮，注册时仍可点击 mask、使用数字键或 `[`／`]` 选择目标。

视频按源帧率播放；`--inference-fps 2` 控制后台更新频率。每个视频帧先应用固定 Homography，再用于显示或 SAM 推理。模型忙时显示上一份结果，图层可能落后于当前视频；调试文字仅在注册布局中显示。

## 显示图层

- `MASK [M]` 按钮或 `M`：开关 mask 色块、轮廓和编号。
- `TRAY [T]` 按钮或 `T`：开关拟合托盘的矩形边框和编号。

两个开关独立，默认均打开；关闭图层不影响推理、注册、reference 或单位 ID。图层只在新结果／标注变化时重建，正常播放混合缓存后的像素。

矩形层使用现有 `fit_tray`，需要类型表中的 `dimension.width_mm/depth_mm` 和属于同一视频视角、以毫米输入的桌面标定：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/你的录像.mp4 --units inputs/你的类型表.json --calibration outputs/homography/对应标定.json --seconds 30
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
frontend/runtime/                    视频源、串行任务、观测接纳与历史
frontend/registration/               首帧提示草稿、军表、绑定及 reference 发布
frontend/calibration/                首次桌面标定与 B08 事务、四角和尺寸页面
frontend/live/                       LIVE／HELD 显示、播放布局和只读失败名单
frontend/geometry_tools/             查询选择、后台计算与测量叠加
frontend/scene_editing/              单位资料、初始正面和地形的受控编辑
frontend/shared/                     文字、坐标换算与 mask／托盘图层缓存
frontend/image/                      独立图片点选及注册窗口
components/video_io/source.py        视频解码、帧号和源时间
components/game_data.py              本局共享数据、观测快照及矩形状态历史
components/sam3/video/predictor.py    已有 SAM 模型与官方会话接口
components/registration/             单位表、mask 切图及最终快照保存
components/boundary_detection/table.py  可复用桌角检测接口
components/boundary_detection/tray/  已有托盘拟合及批量适配
```

`VideoWindow` 通过 `window.app` 持有 `VideoApplication`。应用组装各控制器与视图，保留 TABLE／REGISTER／PLAYBACK／RECALIBRATE 四阶段；`app.session.data` 是唯一的本局 `GameData`。运行层不随当前工具关闭或重启，直播控制器独立管理冻结快照。显示冻结仍处于 PLAYBACK，显式重新标定进入 RECALIBRATE；最终保存目录存在即表示注册已锁定。组件不导入前端，不使用动态属性转发或 mixin 共享全部状态。

推荐启动入口保持 `python -m frontend VIDEO`，`python -m tools.sam3_registration VIDEO` 也可用。程序中创建窗口使用 `from frontend.window import VideoWindow`；程序化驱动使用 `frontend.app.VideoApplication`。单位与 reference 接口见 [registration](../components/registration/README.md)。

修改提示、撤回、编号或保存规则时先看 `registration/controller.py`；修改注册页布局和拖放时看同目录 `view.py`／`unit_panel.py`。修改直播页及失败名单时看 `live/`；修改几何查询调度和测量显示时看 `geometry_tools/`；修改属性、正面或地形输入时看 `scene_editing/`。初始标定和 B08 位于 `calibration/`，视频调度与模型队列位于 `runtime/`。只有跨流程的阶段切换、重置与输入优先级才需要改 `app.py`。

恢复、what-if 和 replay 尚未实现，不创建占位目录。未来恢复只处理失败的已有实例，可复用注册控件，但不能重新分配实例 ID 或解锁整场注册。what-if／replay 分别提供布局副本／重建历史场景，几何组件继续消费显式场景；这些边界不代表已具备对应功能。

本次核对了 Meta 官方跟踪源码、HF 文档和实际安装的 Transformers `5.18.0` 会话接口，继续使用现有提示更新和传播方法。参考：[Meta 跟踪源码](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_tracking_predictor.py)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)。目录拆分、图层开关及托盘结果衔接属于项目集成。

首帧准备调用公开的 `get_image_features` 和会话缓存方法；缓存键按本机后端源码对接，未添加虚拟对象或点提示。注册界面中的 `R` 仍回到同一首帧、保留已确认桌角，重新准备 SAM 会话；不会重新加载已就绪权重。

## 本局共享数据

[GameData](../components/game_data.py) 定义在一个文件中，每个工作流独立创建实例，不使用模块全局单例。新增公共业务数据在该类中增加明确字段，现有结构为：

```text
app.session.data
  board              原图大小、桌面毫米尺寸、桌角和 Homography
  units              UnitRoster：类型、单位实例、属性及 object_id 绑定
  rules              RuleState：人工正面和地形
  current            最新显示帧、匹配的推理帧／结果／源帧时间、显示版本
  history            矩形位置和当时状态的独立副本
  calibrations       各版本标定、源帧及 reference 来源
  tracking           按稳定 unit ID 保存可见性、缺失计时与失败锁定
  reference_folder   已完成注册的保存目录，也是注册锁定依据
```

`data.accept_observation(prediction, frame, metadata)` 接纳同一源帧的结果并更新朝向连续性；运行层核对任务 generation 后接纳后台结果；注册控制器在成功保存后启用失败判定并记录初始观测。完成注册成功保存后记录初始历史，后续接纳传播结果或人工修改已注册单位状态后调用 `data.record_history()`。每条历史包含 `frame_index`、`timestamp_seconds` 及按本局 `unit_id` 索引的 `units`；单位条目为 `corners_mm`、`position_status` 和 `state`。`state` 当前包含 `engaged`、`wavering`、`facing`，未知值保留为 null。没有有效托盘时位置为 null／unavailable；available 仅表示有几何结果，不是正确率判断。相同帧、矩形及状态不重复追加。

`app.live.presentation` 返回实时 `GameData` 或 `data.snapshot()` 生成的独立分析快照，后者只包含同一观测及其标定／单位资料，不复制历史或整个标定版本列表。冻结时追踪继续写实时实例及历史；Clear query／Return live 切回实时实例。R 清空当前观测、单位绑定及历史，保留类型目录、桌面标定和原有地形。矩形历史及帧元数据包含 `calibration_version`，可在 `data.calibrations` 中找到当时的矩阵和实际尺寸，旧历史不随重新标定改写。

历史仅在内存中累积，不保存逐帧 mask／图像，也不自动落盘或恢复；已有最终 reference 导出格式保持。模型会话及记忆由算法适配器管理，唯一模型队列由运行层管理。

## 追踪失败判定与只读名单

完成注册后启用持续无 mask 判定。修改 [config.py](config.py) 的 `TRACKING_DISAPPEARANCE_SECONDS` 可调整缺失阈值，默认 10 秒，须为正的有限数；程序启动时读取，不新增设置控件。首次无有效 mask 的源视频时间保存为 `disappeared_time`，不同源帧的后续缺失观测才推进计时。阈值前恢复非空 mask 自动清零；单纯卡顿、同帧刷新和显示冻结不累计新的失败证据。

`app.session.data.tracking[unit_id]` 保存 `visibility`（最近一次是否有非空 mask）、`status`（tracking／pending／failed）、`disappeared_time`、最近观测帧／时间／标定版本及 `last_accepted_position`。最后位置有自己的源帧与版本；它表示按当前业务假设曾被接纳，不是测得的身份置信度。显式 `routed=True`／`removed=True` 的属性令记录不在场并排除失败名单；正式移除编辑入口尚未实现。

超时才在播放页出现 A／B 双列，只列失败实例，显示 ID、type、Damage 摘要及最后位置时间，支持分别滚动；没有 Damage 时显示 `?`。名单与当前 LIVE／HELD 观测一致。失败后重新出现的 mask 标为 `[Estimated]`，仍保持失败，不进入当前规则位置、朝向更新或有效位置历史。已有 mask 但拟合失败只导致当前几何不可用，不进入这份失踪名单；旧位置不会自动填回。

本轮名单是只读信息入口；Correct / No、拖放绑定、自动恢复和只针对缺失实例的补标记尚未实现。R 开始新注册会清空状态；B08 保留原 ID 及失败锁定。恢复与桌面重新标定是独立流程，不通过解除首帧全局编辑锁来恢复单位。需求基准及未决问题见 [待澄清列表](../待澄清列表.md)。

## 比赛中重新标定

播放页点击 `Recalibrate [K]` 或按 K：

1. 暂停本地视频源，显示当前源帧的原图；等待在途追踪，必要时对该帧补一次传播。这里明确暂停输入，区别于 Space／规则查询的显示冻结。
2. 复用桌角确认、任意顺序手工标记和 Undo，确认当前实际长宽。Esc／`Cancel / Return` 返回之前的标定和显示状态；正在建立新会话时需等结果后再取消。
3. Continue 将当前 mask 映射到新拉正图，保留原 object ID 和单位绑定，以新的初始 mask 建立独立追踪会话。无需重新加载权重，点及 type 仍锁定；新托盘依据实际尺寸重新拟合。
4. 初始化成功后整体切换，从暂停帧重新计时继续播放。失败时不替换原会话／标定，可重试或取消。规则查询及旧显示缓存清除；地形按桌面坐标迁移，正面重新关联矩形轴并标为估计。

原 reference 保留初始图像与坐标来源，不重复导出。每次成功建立新标定递增版本，R 从最近一次标定帧重新注册，避免将新变换套到旧开局画面。原视频区间的结束位置保持。

迁移只使用当前可用 mask；完全丢失或移出旧画面有效范围的单位保留资料及历史，但不会凭旧位置补出新 mask，界面显示 `No tracking masks`。全部单位都无可用 mask 时拒绝应用，可取消后选择较清晰的帧重试。这不是 ID 恢复；仍需检查 mask 是否对应正确单位。地形迁移假设桌面内容固定，新旧标定的物理桌角对应关系不变，镜头旋转导致角名对应改变时不能直接沿用旧标注。

## 游戏信息与规则工具（首版）

当前采用 `KoW4 mini` 规则子集，提供托盘最近距离、基础 LOS 和普通移动／At the Double。冲锋、完整射击判断、自动战斗结算和 ID 恢复未加入。规则来源与限制见 [game_rules](../components/game_rules/README.md)，需求核对见 [审计记录](../docs/Game%20information%20requirements%20audit.md)。

先确认物理比例。程序会在锁定桌角后显示默认 72 × 48 inches，供确认或修改；也可用参数预填其他尺寸，不要与 `--calibration` 同时使用：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --board-size-in 72 48 --seconds 30
```

完成尺寸确认后建立毫米平面和对应宽高比；也可继续载入原视频的有效毫米标定。没有有效托盘或缺少必要规则输入时工具返回 `Unavailable`。

完成 mask/type 绑定并获得托盘后：

1. 选中单位，按 `F`／`Set front`，点击托盘的正面边。这里只登记方向，不调用 SAM；再次 F 取消。正面需在第一次播放前登记，重置或载入新标定后重新登记。
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

选择规则查询时冻结显示，背景、mask、托盘和规则输入取自同一观测；视频源时钟和追踪继续前进。Space／Hold view 也只冻结显示。Clear query [Q] 或 Return live [Space] 清除分析快照并回到最新画面；不会恢复历史提示或解除注册锁。规则计算使用独立后台线程，并显示 snapshot age；旧查询完成后不能覆盖已清除的结果。蓝色点表示采样到的可达**中心位置**，每个姿态的路径及朝向由组件返回；没有实心填充样本凸包，也没有宣称采样以外不可达。

LOS 找到清晰采样线时提供证据；没找到只能返回 `Uncertain`。原型只在目标完全不在前方弧时直接返回 `Blocked`；场景存在未拟合单位时不会将该不完整场景的射线升级为确定清晰。Hill、地形内外及 Height 等仅按已登记区域计算，未登记障碍仍可能改变结果。

当前支持普通单位、War Engine 的部分例外以及 Fly／Pathfinder／Leaper。Individual 移动暂不可用，未支持特殊规则会显示警告。矩形连续性只能估计后续正面，180° 转身以及方形底盘的 90° 对称仍有歧义。单位定位和规则输入未做实际视频精度评估；视频采用第三版或其他规则包时不可当作第四版完整裁决。
## 追踪优化实验选项

默认 `--tray-search full` 保留全量托盘搜索；`--tray-search local` 先以上次成功姿态在当前 mask 和 LSD 上局部更新，失败才完整搜索。更换类型尺寸／标定或 R 重置会清除旧初值。界面分别显示 SAM 操作与托盘耗时。

`--profile` 开启 SAM3 GPU 分段同步并导出任务计时到终端给出的 `outputs/tracking_comparison/sam_.../`；额外同步可能影响速度，和正常模式分开比较。候选后端记录包含后处理／回传的操作总时延，不伪造细分 GPU 时间。

`--tracker sam3|cutie|edgetam` 选择注册后的传播模型。首帧仍使用 SAM3；所选模型一起在启动时加载，首次播放交接 masks 后才启动视频源时钟。候选初始化和重置由同一工作线程串行执行。设置、权重来源和启动命令见 [tracking](../components/tracking/README.md)。LK 已移除。

桌角自动检测失败会保留橙色候选边、缺边原因及 Retry／Manual 按钮；不会直接跳到空白手动页，也不会把无效候选当成成功。手动页提供 Auto 重试，手动输入继续优先于迟到的自动结果。
