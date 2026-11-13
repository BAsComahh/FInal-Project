# Qt 注册与 Live 控制台

客户端接入真实 MatchApplication，不使用预存 mask 或示例绑定替代 SAM。保留 [独立注册预览](../../design/ui/registration/preview.py)；这里是新客户端入口。注册的部分受控接口与两页离屏加载已通过；新增 Live 单位菜单／信息与底部查询控制台，受控主路径已检查，真实模型与原生交互待验收，完整 UI 尚未迁移。

```powershell
cd 'C:\Users\vasco\Desktop\FInal Project'
# 已装过注册预览依赖可跳过安装。
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m pip install --target outputs/ui_preview/deps -r frontend/qt/requirements.txt
& 'C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe' -m frontend.qt 'inputs\Ja5-2RIOBXU_full.mp4' --start 3600
```

完整视频为 9:35:57、1080p／60fps，已下载到 inputs，来源见 [记录](../../inputs/Ja5-2RIOBXU_full.source.json)，大视频不进入 Git。前半小时是待机画面，示例从 01:00:00 的该场第一回合开始，单位比原 02:30:00 片段分散；`--start` 为完整视频中的秒数，原片段仍可使用。

与 `python -m frontend` 共用视频、目录、segmentor、tracker、起点、时长及推理频率等参数；省略 `--seconds` 默认从起点播放到视频结尾，显式传正秒数才限定区间。完整默认值见 [启动参数](../README.md#启动参数默认值)。`--preview-width` 设定初始窗口宽度的画面部分；视频保持比例，黑边点击不作提示。Qt 不改变模型的自动设备选择。安装目录仅提供可选 Qt，不向模型环境自动安装依赖。

追踪默认不额外限速，worker 空闲时处理最新未消费帧；需要限制 GPU 工作量时可显式设置 `--inference-fps`，`--stride` 已移除。实际更新频率受模型耗时、视频帧率与界面 tick 影响，不保证逐帧处理，也不排队追赶旧帧。

A／B 类型列表使用 48 px 高的紧凑条目，只显示分类名称，例如 `Champion Hero (Inf)`；没有分类字段的目录回退到单位名／名称。名称最多换行两行，超出再省略，拖放预览同样处理。不再显示 Type 编号、详情或 Next；点击／拖放继续绑定原 type，同分类的不同配置不会合并。

1. 检查自动提出的 TL／TR／BR／BL；不准确时 Manual correction，任意顺序点四角，右键或 Undo 撤回，Clear 重选，Auto detect 重试。四点无效时不能继续。确认角点后填 Length／Width（英寸）；72×48 是默认测试值，需手工核对。
2. 模型从启动开始加载，桌面确认后准备拉正首帧特征；未就绪时点输入明确拒绝。可在加载期间分别 Import A／B 选择单方 PDF 或 JSON，取消不改变名单。
3. Points 模式左正右负；点击类型或拖类型到 mask 绑定成功后，自动切换到下一对象号，下一次点击开始新目标分割。N／New mask 仍可手动切换，Undo／Ctrl+Z 撤回上一点。Assign 模式先点 mask 再点类型，或拖类型到 mask，成功后仍保留当前目标以便重新分配。失败／落空／过期拖放不自动推进。注册不绘制选中外接框，mask／提示点与可切换的托盘叠加保留；直播选框不受影响。实例编号由应用分配，Unbind 解除绑定。两栏独立滚动。
4. 托盘尺寸只从 PDF 推导或导入目录读取，Qt 不再提供 Tray sizes 手动入口。PDF 中明确底座备注优先于标准表；信息不足保持未知并提示核对资料。旧 JSON 不会自动重算，需重新导入原 PDF 或提供含明确尺寸的目录。已绑定且托盘可用时，Front／F 后点托盘正面边。尺寸和正面进入正式保存。
5. Save／S 保存最终 references 一次并锁定点／类型编辑，仍留注册页；Start video／Space 会先完成注册，再初始化所选 tracker 并开始源播放。底部区分 Source、Observation 和 Age，mask／托盘可分别开关；后台错误及历史写盘警告保留。
6. Reset 显示确认框，开始新注册，保留已导入目录、桌面设置及原有导出。关闭统一释放应用资源、使在途任务失效，最终历史写入沿用 application 语义。

7. 直播默认 Select，点已绑定单位的 mask 或托盘选中。左侧只读 Damage／Speed，未知为 —；单位菜单统一采用竖排信息卡＋右侧 Distance／LOS／Move 半环，边缘整体平移／缩放，不切换横条；菜单不随单位移动，双框和引线随观测更新。再次点单位重新定位，点空白清除。不显示重复尺寸／朝向数值；mask／facing 不确定条目集中到右侧 A／B 列表；正常受监测连续追踪不常驻 Estimated，没有可用正面则在列表标 Unknown。
8. 点 Distance／D 再点第二个单位，inch／mm 数值直接显示在最近点连线中点，不打开抽屉；等待或失败原因及 Done 留在控制栏。LOS／L 选目标后仍用底部抽屉显示状态、原因、警告和观测时间。Move／V 提供 Advance、Double、Back、Sidestep、Change facing、Halt 的离散姿态候选；未知输入会明确提示。这不是完整合法性判定，也不移动正式单位。Estimated mask、失效位置或没有托盘时不作为可查询几何。
9. Done／Esc 退出当前工具，保留单位选择；Select 模式下 Esc、Clear selection、Q／Space 或点空白清除选择。mask／托盘开关独立于业务。菜单、查询和信息展示期间源播放／追踪／历史继续；连线数值与抽屉结果只对应其观测，过期结果暂时隐藏等待更新。

Live 控制台沿用 [半环原型](../../design/ui/unit-radial-console.html)，信息菜单格式与 Distance 线上数值以 [用户最新截图约定](../../design/ui/live/implementation.md) 为准。Missing 提示使用已有失败状态并隐藏 queued／searching；本节点未迁移完整恢复、B08、资料／地形、回放、观众窗口或 What-if，完整旧流程仍用 OpenCV 入口。

mask／facing 不确定信息现在集中在右侧 A／B 双栏，只有需要关注的条目才占用侧栏。正常 facing recovery_phase=tracking 不因连续性／DVMNet 来源而一直告警；pending／failed／waiting、无可用正面和没有监测状态的旧估计仍列出。选择列表单位只是查看信息，不确认恢复，也不重新绑定。信息卡和视频单位名不重复显示这些标签，后端来源及规则警告保留。

正式客户端固定 adaptive，不再提供 `--tray-search`：质心相对上次实际拟合仅小幅变化且面积／32×32 轮廓／可靠长轴稳定时复用矩形；明显变化先局部、失败再完整拟合。底层 full／local 接口保留作无窗口对照。门槛在 application/config.py 中，是试验值；空 mask、恢复目标、标定／尺寸变化及新注册不复用旧解。状态行显示 tray 用时及 reuse／refit 数量。稳定／累计位移／形状方向变化等受控几何和侧栏状态已检查；真实动态误差、会话取消／恢复交叉与持续历史仍待验收。Trays 复选框只控制显示，不停用规则／历史所需的几何计算。

窗口工厂：`frontend.qt.window.create_window(qgui_app, match, visible=True, preview_width=960)`，返回 `(engine, bridge)`。调用方保留两者至窗口结束；可传入已构造的 MatchApplication。`bridge.close()` 幂等关闭定时器、检测任务和应用。正常入口不创建第二份比赛状态。

2026-11-11 独立验收：CPU 真实视频解码配受控模型输出覆盖桌角／尺寸拒绝、点／多对象／撤回、A／B 导入／绑定、尺寸／正面、一次保存锁定、播放交接及 Reset。窗口加载的按钮同名冲突及 Flow 只读属性赋值已修正；用户报告后由 Terra-low 定向复查，桌面设置与注册两页均在 CPU offscreen/software 下加载，无属性绑定错误。当前窗口布局／实际点击拖放、取消文件选择、Reset 在途结果、真实模型／GPU及原生桌面未验证；受控播放不证明真实 tracker 或性能。证据在 `outputs/refactor_checks/qt_registration_terra_20261111`。

Live 后续集中验收检查了真实 QML 点选／半环／第二目标、两种窗口大小、公共几何距离／有正面 LOS／移动候选、固定菜单与更新选框、过期叠加及工具／Reset 清理、短段源推进。左边缘遮挡已修正并做局部 QML 复查。真实 tracker 持续输出／历史写入、所有 Estimated 组合、旧 OpenCV 完整绘制和原生桌面／GPU仍未完整验证，详见 [节点证据与范围](../../design/ui/live/implementation.md)。

代码导航：`window.py` 组装 Qt、`bridge.py` 适配输入／展示状态、`live.py` 维护窗口内 Live 选择并调用几何查询、`board.py` 复用 VideoLayers／QueryLayers 并提供拥有自身像素的 QImage、QML 管理窗口／表单／半环和抽屉。核心不导入 Qt。使用方式依据 Qt 官方 [Image provider](https://doc.qt.io/qtforpython-6/PySide6/QtQuick/QQuickImageProvider.html)、[Image](https://doc.qt.io/qt-6/qml-qtquick-image.html) 和 [FileDialog](https://doc.qt.io/qt-6/qml-qtquick-dialogs-filedialog.html)；同步提供图像、关闭缓存与点击版本校验是本客户端的选择。
