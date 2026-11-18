# Qt 真实注册接入节点（2026-11-11）

用户已授权先提交 I14 阶段 checkpoint，再实现 Qt 主窗口骨架和真实注册。基线提交为 `292dc30`；I14 的完整验收及已记录问题保持开放。当前独立预览继续作为设计样例保存。

2026-11-18：旧视频客户端已退役。本文保留首次接入节点的设计与证据，当前注册操作见 [Qt 客户端](../../../frontend/qt/README.md)。

## 设计与范围

沿用 Registration.qml 的浅灰蓝、视频主区和 A／B 类型栏。正式入口为 `python -m frontend.qt VIDEO`，与 OpenCV 入口并存。一个 Qt 窗口对应一个 MatchApplication；QTimer 驱动 tick，QObject 只适配命令及展示状态，QML 不访问 GameData／worker／Future。使用 Qt 官方 QQuickImageProvider 向 Image 提供独立 QImage，不让渲染线程访问比赛核心。Image 使用同步提供器和递增 URL、关闭缓存；点击携带所显示图像版本，旧版本拒绝，源坐标与 FrameRef 由适配器提交。

本节点包括自动桌角检查／手选四角、英寸尺寸确认、启动即加载模型、正负点及逐点撤回、多对象、A／B PDF／JSON 导入、点击或拖放类型绑定／解绑、托盘尺寸编辑、初始正面、一次保存及锁定／重置；开始播放后显示基础连续视频、mask／托盘与加载／错误／历史提示。保留源帧与观测时间差提示。不把基础直播画面当作完整新控制台：恢复、B08、规则工具、资料／地形、回放、双窗口及 What-if 留待后续迁移，现有完整入口继续可用。

## 执行清单

- [x] 提取共享 CLI 参数，不改变现有入口；增加独立 Qt 启动与可注入比赛实例的窗口工厂。
- [x] 实现展示适配器、图像提供器、桌角草稿和所有注册命令；只保留屏幕选择／草稿，不复制比赛事实。自动检测任务只能在当前检测模式接纳，关闭后不再接纳。
- [x] 将认可的布局变成真实桌面／注册／基础播放页面，列表独立滚动，表单和文件选择用 Qt 控件；锁定后禁用编辑，错误显示明确回执。
- [x] 同步启动、范围及实现状态文档。此阶段新代码保留工作区供查看，不自动再提交或 push。
- [x] 节点完成后统一交独立上下文 Terra-medium，提供入口和以下验收要求，不提供实现说明或疑似问题位置。

本轮结果：两段受控验收共 22 项通过，1 项窗口加载失败；使用真实解码与受控模型输出，未跑真实模型／GPU。按钮同名冲突及 Flow 只读属性赋值已修正；用户报告后 Terra-low 定向确认桌面设置／注册两页在 CPU offscreen/software 下加载通过，无属性绑定错误，证据在 outputs/refactor_checks/qt_startup_20261111/low_recheck.log。布局／真实点击与拖放、文件取消、Reset 在途结果仍待下次统一验收；不能将接口通过算作完整窗口或 I14 通过。证据在 `outputs/refactor_checks/qt_registration_terra_20261111`，当前 UI 改动未再次提交。

## 本节点验收

无原生桌面操作、不新增测试文件；可用 CPU 受控 worker 配真实解码、Qt offscreen／software，另有资源时才做真实 GPU 路径并打印 AMD Radeon RX 7900 XT 物理名称。检查窗口加载与缩放、两种桌角模式／无效四点／尺寸拒绝、模型未就绪输入、点选／撤回／多对象、A／B 导入失败不替换、类型绑定与原 ID／编号、尺寸和 F、S 一次保存锁定、首次播放持续 tick／观测时间提示、R／迟到结果、关闭清理和旧入口参数。报告复现失败项、证据和简短覆盖计数。未覆盖项目须明确列出，不宣称整体 I14 或整套 UI 通过。

官方依据：[QQuickImageProvider](https://doc.qt.io/qtforpython-6/PySide6/QtQuick/QQuickImageProvider.html)、[Image](https://doc.qt.io/qt-6/qml-qtquick-image.html)、[FileDialog](https://doc.qt.io/qt-6/qml-qtquick-dialogs-filedialog.html)。本节点只调用既有应用注册 API，不修改 SAM 后端或模型会话。
