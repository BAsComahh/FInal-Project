# Qt 注册与 Live 控制台

当前暂不使用实时facing，DVMNet不会加载，方向检查／恢复和矩形正面连续更新均停用；代码与初始注册F资料保留。直播侧栏隐藏facing和Missing提示，仅保留Estimated mask／可审核候选；后台失踪判定及自动／手动恢复不变。

`Masks`／`Trays` 胶囊仅控制静态叠加层绘制可见性，关闭 `Trays` 时后台矩形拟合与连续 `Distance`／`LOS`／`Move` 几何查询照常运行，不再暂停计算或回退到定帧快照模式。

客户端接入真实 MatchApplication，可重新注册，也可载入已完成注册的真实 mask／绑定再初始化追踪。保留 [独立注册预览](../../design/ui/registration/preview.py)；这里是新客户端入口。注册的部分受控接口与两页离屏加载已通过；新增 Live 单位菜单／信息与底部查询控制台，受控主路径已检查，真实模型与原生交互待验收，完整 UI 尚未迁移。

```powershell
cd 'C:\Users\vasco\Desktop\FInal Project'
# 已装过注册预览依赖可跳过安装。
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m pip install --target outputs/ui_preview/deps -r frontend/qt/requirements.txt
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m frontend.qt 'inputs\Ja5-2RIOBXU_full.mp4' --start 3600
```

完整视频为 9:35:57、1080p／60fps，已下载到 inputs，来源见 [记录](../../inputs/Ja5-2RIOBXU_full.source.json)，大视频不进入 Git。前半小时是待机画面，示例从 01:00:00 的该场第一回合开始，单位比原 02:30:00 片段分散；`--start` 为完整视频中的秒数，原片段仍可使用。

复用标注：注册页顶部点 `Load registration`，选择原存档内的 `prompts.json`；等待模型就绪后点 `Start video`。也可直接启动：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend.qt inputs/Ja5-2RIOBXU_full.mp4 --registration outputs/sam3_registration/frame_5b58dfca4481
```

该存档包含24个对象，自动定位到45:00；存档帧覆盖 `--start`，`--seconds` 从该帧计时，省略则播到结尾。载入恢复初始mask、原单位ID／类型／属性、桌面标定、地形及已有矩形，注册保持锁定。每次载入新建reference／history目录，原存档不改写；不恢复上次播放进度、追踪器内部记忆或中途失败状态。视频帧不匹配、文件不全会显示拒绝原因；要换存档先Reset。

与 `python -m frontend` 共用视频、目录、segmentor、tracker、起点、时长及推理频率等参数；省略 `--seconds` 默认从起点播放到视频结尾，显式传正秒数才限定区间。完整默认值见 [启动参数](../README.md#启动参数默认值)。`--preview-width` 设定初始窗口宽度的画面部分；视频保持比例，黑边点击不作提示。Qt 不改变模型的自动设备选择。安装目录仅提供可选 Qt，不向模型环境自动安装依赖。

追踪默认不额外限速，worker 空闲时处理最新未消费帧；需要限制 GPU 工作量时可显式设置 `--inference-fps`，`--stride` 已移除。实际更新频率受模型耗时、视频帧率与界面 tick 影响，不保证逐帧处理，也不排队追赶旧帧。

A／B 类型列表使用 48 px 高的紧凑条目，只显示分类名称，例如 `Champion Hero (Inf)`；没有分类字段的目录回退到单位名／名称。名称最多换行两行，超出再省略，拖放预览同样处理。不再显示 Type 编号、详情或 Next；点击／拖放继续绑定原 type，同分类的不同配置不会合并。

1. 检查自动提出的 TL／TR／BR／BL；不准确时 Manual correction，任意顺序点四角，右键或 Undo 撤回，Clear 重选，Auto detect 重试。四点无效时不能继续。确认角点后填 Length／Width（英寸）；72×48 是默认测试值，需手工核对。
2. 模型从启动开始加载，桌面确认后准备拉正首帧特征；未就绪时点输入明确拒绝。可在加载期间分别 Import A／B 选择单方 PDF 或 JSON，取消不改变名单。
3. Points 模式左正右负；点击类型或拖类型到 mask 绑定成功后，自动切换到下一对象号，下一次点击开始新目标分割。N／New mask 仍可手动切换，Undo／Ctrl+Z 撤回上一点。Assign 模式先点 mask 再点类型，或拖类型到 mask，成功后仍保留当前目标以便重新分配。失败／落空／过期拖放不自动推进。注册不绘制选中外接框，mask／提示点与可切换的托盘叠加保留；直播选框不受影响。实例编号由应用分配，Unbind 解除绑定。两栏独立滚动。
4. 托盘尺寸只从 PDF 推导或导入目录读取，Qt 不再提供 Tray sizes 手动入口。PDF 中明确底座备注优先于标准表；信息不足保持未知并提示核对资料。旧 JSON 不会自动重算，需重新导入原 PDF 或提供含明确尺寸的目录。已绑定且托盘可用时，Front／F 后点托盘正面边。尺寸和正面进入正式保存。
5. Save／S 保存最终 references 一次并锁定点／类型编辑，仍留注册页；Start video／Space 会先完成注册，再初始化所选 tracker 并开始源播放。底部状态栏统一显示模型就绪进度、状态提示与 Source／Mask／Geom 时间（以及历史写盘警告），mask／托盘开关改为统一样式的图层胶囊；目录列表使用独立的 `catalogA`/`catalogB` 信号，避免状态刷新打断拖拽绑定。
6. Reset 显示确认框，开始新注册，保留已导入目录、桌面设置及原有导出。关闭统一释放应用资源、使在途任务失效，最终历史写入沿用 application 语义。

7. 直播顶部提供模式徽标（区分 LIVE／REPLAY／RECOVERY／RECALIBRATE／TERRAIN）及 `Live | Replay` 分段切换；主画面使用深色舞台衬底并按活动流程着色边框（回放时为琥珀色外框）。默认 Select，点已绑定单位的 mask 或托盘选中。左侧只读 Damage／Speed（带 A 蓝／B 红侧边色条与快捷 `Info` 编辑入口），未知为 —；单位菜单统一采用竖排信息卡＋右侧精确椭圆弧线排列的 Distance／LOS／Move／Correct，边缘整体限位／缩放，不切换横条；菜单不随单位移动，双框和引线随观测更新。再次点单位重新定位，点空白清除。不显示重复尺寸／朝向数值；mask／facing 不确定条目集中到右侧 A／B 列表；正常受监测连续追踪不常驻 Estimated，没有可用正面则在列表标 Unknown。
8. 点 Distance／D 再点第二个单位，inch／mm 数值直接显示在最近点连线中点，不打开抽屉；等待或失败原因及 Done 留在控制栏。LOS／L 选目标后仍用底部抽屉显示状态、原因、警告和观测时间（附状态色条与状态徽标）。Move／V 提供 Advance、Double、Back、Sidestep、Change facing、Halt 的离散姿态候选；未知输入会明确提示。这不是完整合法性判定，也不移动正式单位。Estimated mask、失效位置或没有托盘时不作为可查询几何。
9. Done／Esc 退出当前工具，保留单位选择；Select 模式下 Esc、Clear selection、Q／Space 或点空白清除选择。mask／托盘开关独立于选择状态。菜单、查询和信息展示期间源播放／追踪／历史继续；连线数值与抽屉结果只对应其观测，过期结果暂时隐藏等待更新。

Live 控制台沿用 [半环原型](../../design/ui/unit-radial-console.html)，信息菜单格式与 Distance 线上数值以 [用户最新截图约定](../../design/ui/live/implementation.md) 为准。2026-11-13 接入辅助流程：红色 Correct 打开当前单位的隔离矫正，正／负点生成黄色候选，再把右侧原 ID 卡片（带 A／B 色标与类型名）拖到候选上确认；Recover units 可选择自动候选并 Correct／No，Clear／Cancel 保留原追踪。候选时间显示在工具栏，确认等待核心完成对齐后生效。B08 的 Recalibrate 在连续原视频上选择四角并提交尺寸，Cancel 保留原标定；Unit information 仅在选中单位时启用并弹出表单（含 `unit_kind`／地形 `kind` 下拉选择与独立校验错误提示，不混用后台追踪提示）；Terrain 点多边形后 Save polygon 填资料，右键撤点，Undo terrain 仅在存在已保存地形时可用并弹出确认框；已保存地形会在舞台中按类别半透明绘制。Replay 替换主画面为深色毫米棋盘，顶部与工具栏清晰显示 `REPLAY` 徽标、当前步数、时间戳、标定版本及无位置单位提示；Previous／Next 或 A／D 切步，Refresh 保持事件，Cancel／Esc 返回最新实况。上述流程中 tick、追踪和历史继续；观众窗口及 What-if 尚未实现。

mask／facing 不确定信息现在集中在右侧 A／B 双栏，只有需要关注的条目才占用侧栏。正常 facing recovery_phase=tracking 不因连续性／DVMNet 来源而一直告警；pending／failed／waiting、无可用正面和没有监测状态的旧估计仍列出。选择列表单位只是查看信息，不确认恢复，也不重新绑定；侧栏底部另提供进入恢复视图的快捷按钮。信息卡和视频单位名不重复显示这些标签，后端来源及规则警告保留。

正式客户端固定 adaptive，不再提供 `--tray-search`：质心相对上次实际拟合移动 ≤5% 且原图像坐标二值 mask IoU ≥0.90 时复用矩形（旧面积／32×32 轮廓／长轴条件已于 2026-11-13 P0 移除）；需要重拟合时，质心位移超过托盘短边的 50% 则直接完整搜索，其余先用旧框局部拟合。拟合失败时，以尝试帧压缩 mask 为基准等待变化。底层 full／local 接口用于无窗口对照。稳定门槛见 application/config.py，重拟合见托盘组件文档；空 mask、恢复目标、标定／尺寸变化及新注册不复用旧解。状态栏显示 Source／Mask／Geom 时间。

窗口工厂：`frontend.qt.window.create_window(qgui_app, match, visible=True, preview_width=960)`，返回 `(engine, bridge)`。调用方保留两者至窗口结束；可传入已构造的 MatchApplication。`bridge.close()` 幂等关闭定时器、检测任务和应用。正常入口不创建第二份比赛状态。

2026-11-11 独立验收：CPU 真实视频解码配受控模型输出覆盖桌角／尺寸拒绝、点／多对象／撤回、A／B 导入／绑定、尺寸／正面、一次保存锁定、播放交接及 Reset。窗口加载的按钮同名冲突及 Flow 只读属性赋值已修正；用户报告后由 Terra-low 定向复查，桌面设置与注册两页均在 CPU offscreen/software 下加载，无属性绑定错误。当前窗口布局／实际点击拖放、取消文件选择、Reset 在途结果、真实模型／GPU及原生桌面未验证；受控播放不证明真实 tracker 或性能。证据在 `outputs/refactor_checks/qt_registration_terra_20261111`。

Live 后续集中验收检查了真实 QML 点选／半环／第二目标、两种窗口大小、公共几何距离／有正面 LOS／移动候选、固定菜单与更新选框、过期叠加及工具／Reset 清理、短段源推进。左边缘遮挡已修正并做局部 QML 复查。真实 tracker 持续输出／历史写入、所有 Estimated 组合、旧 OpenCV 完整绘制和原生桌面／GPU仍未完整验证，详见 [节点证据与范围](../../design/ui/live/implementation.md)。

代码导航：`window.py` 加载可用字体并组装 Qt、`Theme.qml` 集中管理深色控制台配色、字体及字号/圆角刻度、`ConsoleButton.qml` 提供统一按钮样式（`visualFocus` 仅在键盘导航显式描边）、`BoardBadges.qml` 在矢量层渲染圆角胶囊名牌与地形标签、`bridge.py` 适配输入／展示状态与独立目录/名牌信号、`live.py` 维护窗口内 Live 选择与侧别投影并调用几何查询、`workflows.py` 适配辅助流程表单校验／交互叠加及带起止虚影与运动轨迹箭头的 Replay 棋盘绘制、`board.py` 拆分为纯视频帧、后台线程（`qt-overlay`）按紧密包围盒及二维积分占用图自动避让摆放名牌并输出布局的透明静态叠加层，以及瞬时响应选框／查询／提示点／桌角的透明交互层，分别通过 `BoardImages` 提供拥有自身像素的 QImage，QML 三层叠放交由 Qt 场景图合成，不再在每帧视频播放时逐像素混色。核心不导入 Qt。使用方式依据 Qt 官方 [Image provider](https://doc.qt.io/qtforpython-6/PySide6/QtQuick/QQuickImageProvider.html)、[Image](https://doc.qt.io/qt-6/qml-qtquick-image.html) 和 [FileDialog](https://doc.qt.io/qt-6/qml-qtquick-dialogs-filedialog.html)；同步提供图像、关闭缓存与点击版本校验是本客户端的选择。
