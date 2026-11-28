# Qt 注册与 Live 控制台

当前暂不使用实时 facing，DVMNet 不会加载，方向检查／恢复和矩形正面连续更新均停用；代码与初始注册 F 资料保留。直播右侧 A／B 列表保留 Estimated 和待审核候选。缺失单位在正常传播中重新出现原 ID 的有效 mask 时恢复追踪并清掉提示，查询在取得有效托盘后恢复。

Live 工具栏右侧 `···` 更多菜单中的 **Debug snapshot** 会暂停视频并保留当刻已接纳状态，画布同步显示当前 mask、托盘、地形与名牌，且可通过工具栏的 `Masks`／`Trays` 胶囊即时切换。点 **Save snapshot** 默认保存到 `outputs/debug/instance_*/frame_*/`，按本局注册实例分组；自定义 `--output-dir` 时保存在该目录下的 `debug/instance_*/frame_*/`。界面显示完整路径。`frame.png` 与 `source.png` 是当前拉正图和原图，`mask_frame.png`、`geometry_frame.png` 分别对应 mask 和托盘的观测帧。每个对象一张二值 mask，`snapshot.json` 提供对应的源帧号／时刻、托盘坐标、拟合诊断、单位绑定、追踪状态和标定。**Resume Live** 或 Esc 返回 Live，视频从暂停位置继续。

Registration 可用 **Rectangle**（左键按住拖拽，半透明选区预览不遮挡单位）或 **Four corners**（点选四个凸四边形顶点）画 mask。画完后点击类型或将类型拖到目标上，绑定成功会自动进入下一对象，并保留当前绘图工具；若先切入 **Assign**／点 `Unassigned` 芯片或完成 **Front** 后再切回 **Rectangle**／**Four corners**／**Points**，也会自动推进到下一新对象，不再误覆写上一个已标记单位。先点 **New mask** 可显式新建对象；在 **Assign** 中主动点选已有 mask 且未重新绑定时切到作图工具，则替换该对象并在工具栏标黄提示。绘制时右键可撤未完成顶点或当前未确认的手绘草稿，**Undo**／`Ctrl+Z` 按操作顺序撤回已提交的形状。人工形状覆盖交叠的 SAM 像素；mask 变化的已绑定对象保留 ID，需重新确认类型才能拟合托盘。

Registration 工具栏现提供 **Terrain** 与 **Undo terrain**（桌角确认后即可使用，无需等待 SAM3 就绪）：进入 Terrain 后左键依次点多边形顶点、右键或顶部 **Undo** 撤回草稿点，满 3 点后点 **Save polygon** 填写名称、类别与可选 Height（Obstacle 自动固定为 1），保存后停留在 Terrain 模式以便连续标注，点 **Done** 或 `Esc` 返回单位注册；右侧同步切换为 `TerrainPanel`，列出全部已保存地形供随时点选修改属性或二步确认任意删除。在注册 **Assign** 模式下点选画布上未被单位遮挡的已有地形（或其地形名牌），也会像 Live 单位卡一样在旁弹出可拖动的 `TerrainHud` 数据卡，点卡上的 **Info** 即在右侧展开 `TerrainPanel` 进行配置或删除。**Undo terrain** 继续保留作为快速撤销最后一块地形的快捷入口。`Save`／`Start video` 锁定注册后，Live 与 Replay 只读显示已保存地形并用于规则查询。

各工具栏统一使用 `OverlayToggles.qml` 提供 `Overlays` 总开关（快捷键 `O`，记忆并恢复上次开关组合）与 `Masks`、`Trays`、`Labels`（胶囊名牌及引线，画布与 Replay 优先展示兵种名称如 `Mage`、`Ice Queen`，无名称时回退实例 ID）、`Terrain` 四项独立图层开关（Replay 显示 `Overlays`／`Trays`／`Labels`）。所有开关仅控制显示可见性：关闭 `Masks` 与 `Trays` 时仍可单独开启 `Labels` 查看单位名牌；关闭 `Trays` 时后台矩形拟合与连续 `Distance`／`LOS`／`Move` 几何查询照常运行。Live 中，仍有 mask 的单位拟合失败时以虚线保留最后接纳的框。新拟合通过后显示新的实线框。规则查询和历史使用当前验收结果。

Qt 是桌面视频客户端。它通过 MatchApplication 提供注册及存档载入、Live、恢复、B08、表单和 Replay。真实模型、原生交互仍待完整验收。

```powershell
cd 'C:\Users\vasco\Desktop\FInal Project'
# 按根目录 README 先安装适合目标 GPU 的 PyTorch，再安装项目依赖。
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m pip install -r requirements.txt
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m frontend.qt 'inputs\Ja5-2RIOBXU_full.mp4' --start 3600
```

完整视频为 9:35:57、1080p／60fps，已下载到 inputs，来源见 [记录](../../inputs/Ja5-2RIOBXU_full.source.json)，大视频不进入 Git。前半小时是待机画面，示例从 01:00:00 的该场第一回合开始，单位比原 02:30:00 片段分散；`--start` 为完整视频中的秒数，原片段仍可使用。

复用标注：注册页顶部点 `Load registration`，选择原存档内的 `prompts.json`；等待模型就绪后点 `Start video`。也可直接启动：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --registration outputs/sam3_registration/frame_5b58dfca4481
```

该存档包含24个对象，自动定位到45:00；存档帧覆盖 `--start`，`--seconds` 从该帧计时，省略则播到结尾。载入恢复初始mask、原单位ID／类型／属性、桌面标定、地形及已有矩形，注册保持锁定。每次载入新建reference／history目录，原存档不改写；不恢复上次播放进度、追踪器内部记忆或中途失败状态。视频帧不匹配、文件不全会显示拒绝原因；要换存档先Reset。

`python -m frontend` 和 `python -m tools.sam3_registration` 均进入 Qt，参数见 [启动参数](../README.md#启动参数默认值)。`--preview-width` 设置初始画面宽度，视频保持比例。

追踪默认上限为 1.0 Hz。Worker 可提交时处理最新未消费帧，`--inference-fps` 可调整上限。实际更新频率还受模型耗时、视频帧率与界面 tick 影响。

A／B 类型列表使用最小 48 px 高的紧凑条目，上方优先显示兵种名称（`unit_name`／`name`），下方以小一号字附注托盘／分类类型（`classification`／`formation`，例如 `Champion Hero (Inf)`）。主副标题最多各换行两行，超出再省略，拖放预览同样处理。不再显示 Type 编号、详情或 Next；点击／拖放继续绑定原 type，同分类的不同配置不会合并。

1. 检查自动提出的 TL／TR／BR／BL；不准确时 Manual correction，任意顺序点四角，右键或 Undo 撤回，Clear 重选，Auto detect 重试。四点无效时不能继续。确认角点后填 Length／Width（英寸）；72×48 是默认测试值，需手工核对。
2. 模型从启动开始加载，桌面确认后准备拉正首帧特征；未就绪时点输入明确拒绝。可在加载期间分别 Import A／B 选择单方 PDF 或 JSON，取消不改变名单。
3. Points 模式左正右负；点击类型或拖类型到 mask／托盘／单位标签绑定成功后，自动切换到下一对象号，下一次点击开始新目标分割。若此时切回 Assign 且当前目标尚无 mask，会自动选中最近刚赋予类型的 mask，也可直接点图上的 mask 或单位标签重选。N／New mask 仍可手动切换，Undo／Ctrl+Z 撤回上一点。Assign 模式先点 mask 再点类型，或拖类型到 mask，成功后仍保留当前目标以便重新分配。失败／落空／过期拖放不自动推进。未分配或修改待确认的 mask 会在画布胶囊外框与右侧 `Unassigned`／`Re-confirm` 列表中标黄提醒，点击即可定位选中，全部确认后才可 Save／Start。注册不绘制选中外接框，mask／提示点与可切换的托盘叠加保留；直播选框不受影响。实例编号由应用分配，Unbind 解除绑定。两栏独立滚动。
4. 托盘尺寸只从 PDF 推导或导入目录读取，Qt 不再提供 Tray sizes 手动入口。PDF 中明确底座备注优先于标准表；信息不足保持未知并提示核对资料。旧 JSON 不会自动重算，需重新导入原 PDF 或提供含明确尺寸的目录。已绑定且托盘可用时，Front／F 后点托盘正面边。尺寸和正面进入正式保存。
5. Save／S 保存最终 references 一次并锁定点／类型编辑，仍留注册页；Start video／Space 会先完成注册，再初始化所选 tracker 并开始源播放。底部状态栏统一显示模型就绪进度、状态提示与 Source／Mask／Geom 时间（以及历史写盘警告），mask／托盘开关改为统一样式的图层胶囊；目录列表使用独立的 `catalogA`/`catalogB` 信号，避免状态刷新打断拖拽绑定。
6. Reset 显示确认框，开始新注册，保留已导入目录、桌面设置及原有导出。关闭统一释放应用资源、使在途任务失效，最终历史写入沿用 application 语义。

7. 直播顶部提供模式徽标（区分 LIVE／REPLAY／RECOVERY／RECALIBRATE／DEBUG）、`Light`／`Dark` 深浅色切换按钮（默认深色、不持久化）、`Live | Replay` 分段切换，以及以分隔线和红框样式区分的 `Reset`；主画面按活动流程着色边框（回放时为紫色外框），UI 强调色与选中高亮统一为琥珀色以与 A 蓝／B 红阵营色分离。Live 工具栏左侧为 `Select` 与紧凑图层条（`Overlays | Masks · Trays · Labels · Terrain`，快捷键 `O`），右侧为 `Unit information`、`Recover units`、`Recalibrate` 及收纳 `Debug snapshot` 的 `···` 菜单。默认 Select，点已绑定单位的 mask 或托盘选中。单位菜单保留右侧椭圆弧线排列的 Distance／LOS／Move 及轻量红框样式的 Correct；左侧独立数值卡（带 A 蓝／B 红侧边色条与快捷 `Info` 按钮）展示兵种名称、分类、`Engaged`/`Wavering` 状态、Kings of War 横排属性条（`Sp`/`Me`/`Sh`/`De`/`US`/`Att`/`Ne`/`Ht`，未知为 —）及特殊规则摘要。选中瞬间左卡结合 `Main.qml` 同步的实际画布视口尺寸，在紧贴半环四向候选＋局域多圈＋全屏超稀疏采样上硬排除半环菜单占位、避让其他单位与邻近名牌（`BoardBadges`），并以引线净距主导就近摆放，之后不随帧微动重跳，且可单独拖拽微调位置，琥珀色引线与边缘锚点自动吸附到左卡最近边缘。空闲或普通选中态隐藏多余的底部提示栏（选中 ID 与 `Clear` 收入定高底栏），仅在 Distance／LOS／Move 或查询受阻时展开 `LiveConsole`。再次点单位重新定位，点空白清除。不显示重复尺寸／朝向数值；mask／facing 不确定条目集中到右侧 A／B 列表；正常受监测连续追踪不常驻 Estimated，没有可用正面则在列表标 Unknown。
8. 点 Distance／D 再点第二个单位，inch／mm 数值直接显示在最近点连线中点，不打开抽屉；等待或失败原因及 Done 留在控制栏。LOS／L 选目标后仍用底部抽屉显示状态、原因、警告和观测时间（附状态色条与状态徽标）。Move／V 提供 Advance、Double、Back、Sidestep、Change facing、Halt 的离散姿态候选；未知输入会明确提示。这不是完整合法性判定，也不移动正式单位。Estimated mask、失效位置或没有托盘时不作为可查询几何。
9. Done／Esc 退出当前工具，保留单位选择；Select 模式下 Esc、Clear selection、Q／Space 或点空白清除选择。mask／托盘开关独立于选择状态。菜单、查询和信息展示期间源播放／追踪／历史继续；连线数值与抽屉结果只对应其观测，过期结果暂时隐藏等待更新。

Live 控制台沿用 [半环原型](../../docs/ui-archive/unit-radial-console.html)和[用户设计截图](../../docs/ui-archive/unit-info-reference.png)的布局。点 `Info` 或 `Unit information` 时，在舞台右侧停靠展开 `UnitInfoPanel`（优先覆盖右侧黑边、空间不足时再左移或压缩棋盘；内含共享横排属性条、完整军表只读详情、A／B 分段阵营选择、多行自动换行特殊规则与自定义下拉／复选控件，并随当前选中单位自动切换，关闭或 `Esc` 后恢复原有右侧提示栏）；2026-11-13 接入的其余辅助流程包括：Correct 或 Recover units 进入隔离恢复，操作对齐注册页，支持 `Points`（正／负点）、`Rectangle`（半透明拖拽）与 `Four corners`（四点凸四边形，右键／`Ctrl+Z` 撤未完成顶点）生成黄色候选，并配有 `Masks`／`Trays` 开关；右侧 `RecoveryPanel` 使用独立列表信号保持拖拽稳定，支持直接点击原 ID 卡片、拖到候选上（悬停绿框高亮）或点击工具栏 `Confirm <ID>` 确认，自动候选仍支持 `Correct`／`No`，`Clear / Retry`／`Back to Live` 保留原追踪。候选时间显示在工具栏，确认等待核心完成对齐后生效；轻微贴边重叠自动裁去不占正常单位像素，实质重叠则提示具体冲突单位并保留当前候选草稿。B08 的 Recalibrate 在连续原视频上选择四角并提交尺寸，Cancel 保留原标定；注册期保存的地形会在舞台中按类别半透明绘制；`···` 菜单中的 Debug snapshot 在播放期暂停源时钟与结果接纳、显示当前叠加层以导出对齐帧、mask 与托盘诊断包。Replay 替换主画面为深色毫米棋盘，顶部与工具栏清晰显示 `REPLAY` 徽标、当前步数、时间轴滑块（支持直接点击／拖拽跳步、按阵营着色的步骤刻度及悬停／拖拽预览）、`Overlays`／`Trays`／`Labels` 开关、时间戳、标定版本及无位置单位提示；Previous／Next 或 A／D 切步，Refresh 保持事件，Cancel／Esc 返回最新实况。上述流程中 tick、追踪和历史继续；观众窗口及 What-if 尚未实现。

mask／facing 不确定信息现在集中在右侧 A／B 双栏，只有需要关注的条目才占用侧栏。正常 facing recovery_phase=tracking 不因连续性／DVMNet 来源而一直告警；pending／failed／waiting、无可用正面和没有监测状态的旧估计仍列出。选择列表单位只是查看信息，不确认恢复，也不重新绑定；侧栏底部另提供进入恢复视图的快捷按钮。信息卡和视频单位名不重复显示这些标签，后端来源及规则警告保留。

正式客户端固定 adaptive，不再提供 `--tray-search`：质心相对上次实际拟合移动 ≤5% 且原图像坐标二值 mask IoU ≥0.90 时复用矩形（旧面积／32×32 轮廓／长轴条件已于 2026-11-13 P0 移除）；需要重拟合时，质心位移超过托盘短边的 50% 则直接完整搜索，其余先用旧框局部拟合。拟合失败时，以尝试帧压缩 mask 为基准等待变化。底层 full／local 接口用于无窗口对照。稳定门槛见 application/config.py，重拟合见托盘组件文档；空 mask、恢复目标、标定／尺寸变化及新注册不复用旧解。状态栏显示 Source／Mask／Geom 时间。

窗口工厂：`frontend.qt.window.create_window(qgui_app, match, visible=True, preview_width=960)`，返回 `(engine, bridge)`。调用方保留两者至窗口结束；可传入已构造的 MatchApplication。`bridge.close()` 幂等关闭定时器、检测任务和应用。正常入口不创建第二份比赛状态。

2026-11-11 独立验收：CPU 真实视频解码配受控模型输出覆盖桌角／尺寸拒绝、点／多对象／撤回、A／B 导入／绑定、尺寸／正面、一次保存锁定、播放交接及 Reset。窗口加载的按钮同名冲突及 Flow 只读属性赋值已修正；用户报告后由 Terra-low 定向复查，桌面设置与注册两页均在 CPU offscreen/software 下加载，无属性绑定错误。当前窗口布局／实际点击拖放、取消文件选择、Reset 在途结果、真实模型／GPU及原生桌面未验证；受控播放不证明真实 tracker 或性能。证据在 `outputs/refactor_checks/qt_registration_terra_20261111`。

Live 后续集中验收检查了真实 QML 点选／半环／第二目标、两种窗口大小、公共几何距离／有正面 LOS／移动候选、固定菜单与更新选框、过期叠加及工具／Reset 清理、短段源推进。左边缘遮挡已修正并做局部 QML 复查。真实 tracker 持续输出／历史写入、所有 Estimated 组合和原生桌面／GPU仍未完整验证，详见 [TODO I16](../../TODO.md#7-叠加层与解说交互)。

代码导航：`window.py` 加载可用字体、暴露窗口级 `Appearance` 深浅色状态并组装 Qt、`Theme.qml` 集中管理深／浅色配色（琥珀强调色＋A 蓝／B 红阵营色）、字体及字号/圆角刻度、`ConsoleButton.qml` 提供统一按钮样式与矢量图标（`visualFocus` 仅在键盘导航显式描边）、`ConsoleComboBox.qml` 与 `ConsoleCheckBox.qml` 提供深浅色一致的下拉框与复选框、`StatStrip.qml` 提供 `UnitHud` 与 `UnitInfoPanel` 共用的 Kings of War 横排属性条、`OverlayToggles.qml` 提供紧凑图层条（总叠加与四项细粒度图层开关）、`TerrainDialogs.qml` 提供新建地形弹窗与撤销确认、`TerrainHud.qml` 与 `TerrainPanel.qml` 提供注册期已有地形的浮动数据卡与右侧编辑／删除面板、`BoardBadges.qml` 在矢量层渲染圆角胶囊名牌与地形标签、`bridge.py` 适配输入／展示状态与独立目录/名牌信号、`live.py` 维护窗口内 Live 选择、避让半环与名牌的左卡定位并调用几何查询、`workflows.py` 适配辅助流程表单校验／交互叠加、地形列表／编辑及带起止虚影与运动轨迹箭头的 Replay 棋盘绘制、`board.py` 拆分为纯视频帧、后台线程（`qt-overlay`）按紧密包围盒及二维积分占用图自动避让摆放名牌并输出布局的透明静态叠加层，以及瞬时响应选框／查询／提示点／桌角的透明交互层，分别通过 `BoardImages` 提供拥有自身像素的 QImage，QML 三层叠放交由 Qt 场景图合成，不再在每帧视频播放时逐像素混色。核心不导入 Qt。使用方式依据 Qt 官方 [Image provider](https://doc.qt.io/qtforpython-6/PySide6/QtQuick/QQuickImageProvider.html)、[Image](https://doc.qt.io/qt-6/qml-qtquick-image.html) 和 [FileDialog](https://doc.qt.io/qt-6/qml-qtquick-dialogs-filedialog.html)；同步提供图像、关闭缓存与点击版本校验是本客户端的选择。
