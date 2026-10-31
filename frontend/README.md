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

确认尺寸后复用 Homography 组件，将桌面四边形拉正为矩形并填满战场画面，同时建立毫米坐标。默认 72 × 48 inches 是临时测试假设，尺寸确认不等于真实测量。注册、播放、SAM、mask、托盘和 reference 都使用拉正图像坐标；后续帧及 R 重置沿用同一变换和尺寸，假设镜头固定。修改外部标定的尺寸时同步缩放其两轴毫米坐标。

原始桌角和确认的英寸／毫米尺寸保存在最终 `prompts.json.table_boundary`，角点坐标空间为 `source_image_pixels`。注册元数据标明 `rectified_table_pixels`，保存原视频尺寸、拉正尺寸及正反矩阵；同样的信息会随每个 reference 保存。手动点不受图像四象限限制，强透视或接近菱形时仍需核对角名。

进入注册后：

侧栏上方点击 `Import list A [O]`／`Import list B [P]`，直接选择各方的 Mantic Companion PDF，或选择已有的单方类型 JSON。可在模型准备期间先导入。下方左右两栏分别显示 Type 1、Type 2…，附兵种／编制和配置摘要；鼠标滚轮只滚动所在的一栏。文件读完并通过验证后才替换该方列表；取消或失败保留原名单。重新导入某方会解除该方的旧类型绑定及正面标记，保留分割 mask 和另一方的绑定，按新名单重新对应即可。一个按钮一次只接受一方名单，不接受双方合并的 JSON。

1. 权重从启动即加载，首帧特征则等待桌角、尺寸确认和 Homography 完成后，在拉正首帧上计算；不预先计算原图特征。全部准备完成才接受单位提示。加载权重显示已完成项数和百分比，准备模型、转入 GPU 和首帧特征计算等阶段显示滚动条；就绪后自动隐藏。首次点击仍需提示解码和记忆编码，实际耗时需实测。
2. 默认是分割模式：左键添加正点、右键添加排除点，`N` 新建对象。可以先分割所有目标，不指定任何 type。
3. 按 `Tab` 或侧栏模式按钮切换到标注模式：点击 mask 再点击某方 type，也可以直接把 type 拖到 mask 上。List A 的 Type 1 对应内部类型 A1，实例依次生成 A1.1、A1.2；List B 的 Type 1 则生成 B1.1 等。按下 type 时不绑定，释放到目标才生效；拖到空白处取消。已绑定的 mask 可以重复选中并改绑，同 type 保留编号，换 type 释放旧编号而不重排其他单位。选中目标显示白色轮廓。
4. `S` 完成注册，或按空格完成并播放：统一保存一次最终 reference，锁定点及类型修改，然后传播 mask。
5. 首次成功播放后，自动隐藏类型侧栏、注册按钮、提示点及调试文字，保留视频、MASK／TRAY 开关与规则工具。暂停或区间播放结束后仍保持这一布局；空格播放／暂停，`R` 恢复注册界面并开始新注册，`Esc` 关闭。暂停不会重新允许编辑 SAM 提示或类型。

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
frontend/window.py                   窗口、输入事件、文件选择与绘制
frontend/workflow.py                 桌角确认、注册草稿、播放与坐标数据
frontend/task_worker.py              串行后台 SAM 操作及可选托盘计算
frontend/table_setup.py              首帧桌角检测确认及任意顺序手动标记
frontend/annotation_panel.py         A／B 双列类型侧栏与独立滚动
frontend/layers.py                   mask／矩形的独立显示缓存
frontend/image/                      独立图片点选及注册窗口
components/video_io/source.py        视频解码、帧号和源时间
components/sam3/video/predictor.py    已有 SAM 模型与官方会话接口
components/registration/             单位表、mask 切图及最终快照保存
components/boundary_detection/table.py  可复用桌角检测接口
components/boundary_detection/tray/  已有托盘拟合及批量适配
```

`VideoWindow` 通过组合持有 `RegistrationWorkflow`，不代理对方属性。窗口保存图层开关、拖拽和显示缓存；工作流保存 TABLE／REGISTER／PLAYBACK 阶段、模型准备、注册草稿及播放状态。暂停仍处于 PLAYBACK，最终保存目录存在即表示注册已锁定。组件不导入前端；旧视频组件中的窗口、侧栏和 source 转发文件已移除。

推荐启动入口保持 `python -m frontend VIDEO`，`python -m tools.sam3_registration VIDEO` 也可用。程序中创建窗口使用 `from frontend.window import VideoWindow`；无需窗口时可使用 `RegistrationWorkflow` 或各独立组件。单位与 reference 接口见 [registration](../components/registration/README.md)。

本次核对了 Meta 官方跟踪源码、HF 文档和实际安装的 Transformers `5.18.0` 会话接口，继续使用现有提示更新和传播方法。参考：[Meta 跟踪源码](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_tracking_predictor.py)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)。目录拆分、图层开关及托盘结果衔接属于项目集成。

首帧准备调用公开的 `get_image_features` 和会话缓存方法；缓存键按本机后端源码对接，未添加虚拟对象或点提示。注册界面中的 `R` 仍回到同一首帧、保留已确认桌角，重新准备 SAM 会话；不会重新加载已就绪权重。

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

选择单位时暂停视频以便查看；空格可继续播放。规则计算使用独立后台线程，输入是同一推理快照，并显示结果的 snapshot age。较新的待处理查询不会覆盖旧结果的时间标记。蓝色点表示采样到的可达**中心位置**，每个姿态的路径及朝向由组件返回；没有实心填充样本凸包，也没有宣称采样以外不可达。

LOS 找到清晰采样线时提供证据；没找到只能返回 `Uncertain`。原型只在目标完全不在前方弧时直接返回 `Blocked`；场景存在未拟合单位时不会将该不完整场景的射线升级为确定清晰。Hill、地形内外及 Height 等仅按已登记区域计算，未登记障碍仍可能改变结果。

当前支持普通单位、War Engine 的部分例外以及 Fly／Pathfinder／Leaper。Individual 移动暂不可用，未支持特殊规则会显示警告。矩形连续性只能估计后续正面，180° 转身以及方形底盘的 90° 对称仍有歧义。单位定位和规则输入未做实际视频精度评估；视频采用第三版或其他规则包时不可当作第四版完整裁决。
