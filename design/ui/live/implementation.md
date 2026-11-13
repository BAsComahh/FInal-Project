# Qt Live 控制台接入（2026-11-11）

用户明确要求按 design 的思路接入直播菜单、单位信息和控制台。当前视觉与交互依据为 [已认可半环设计](../unit-radial-console.html)，不重新改版。实现基于未提交的 Qt 注册客户端，保持单个 MatchApplication；不自行提交、新增测试文件或操作原生桌面。

## 本节点范围

- 默认 Select，直接点当前已绑定 mask／托盘选择真实 unit ID。左侧只读 Damage／Speed，未知用 —；不重复尺寸／朝向数值。不确定项统一放在右侧 A／B 单位列表，信息卡及视频名不重复标注。Facing 正常 tracking 不因非人工来源而常驻 Estimated；只列可疑／待恢复／失败／未知，旧估计没有监测状态时仍标 unchecked。列表选择仅检查原单位，不替换身份或确认恢复。
- 菜单统一采用 [用户截图](unit-info-reference.png) 的左侧竖排卡片、右侧半环 Distance／LOS／Move，不翻转或切换为横条。菜单以点击锚点定位，边缘时整体限位／必要缩放，利用画面留白保留结构；双框与短引线随最新观测更新。再次选择可重定位；空白清除。
- Distance、LOS 选择第二个单位；Distance 的 inch／mm 数值标在同观测最近点连线中点，不打开抽屉。Distance 等待／失败信息及 Done 留在控制栏，旧查询隐藏数值；LOS／Move 保留底部抽屉。Move 提供已有 Advance、Double、Back、Sidestep、Change facing、Halt 候选；显示离散候选，不移动正式单位。缺失、失败或未接纳 mask 不作为可用几何。
- 查询结果必须与当前观测引用／标定版本匹配，旧结果不绘成当前。等待查询、选择菜单或查看信息期间，视频、追踪和历史继续。保留 Source／Observation／Age、后台错误及历史警告，控制台提供清除选择和现有图层开关。人工 Missing 名单继续隐藏 queued／searching。
- 本节点为 Live 控制台；恢复／B08／Replay 的完整 Qt 流程、资料／地形表单、观众窗口及 What-if 继续独立迁移，不引入原型样例动作或无效按钮。

## 文件与执行

- [x] `frontend/qt/live.py`：窗口内 Live 展示选择、信息投影和真实查询命令；不保存业务事实。
- [x] `frontend/qt/UnitHud.qml`、`LiveConsole.qml`：固定半环／信息与底部结果抽屉；接入 Main.qml 的实际画面坐标与键盘。
- [x] `frontend/qt/bridge.py`、`board.py`：衔接 Live，保留显示版本与源帧引用、关闭／Reset 清理；复用共享查询叠加，避免复制 OpenCV 业务。
- [x] 同步根记录及启动说明，旧注册路径继续可用。
- [x] 节点完成后由独立上下文 Terra-medium 统一验收；主实现期间不主动跑回归或测试。

## 本轮证据与剩余范围

最新截图与距离标签修订取代下面旧版本的 compact 排布和 Distance 抽屉；旧批次证据保留其当时范围，本次仅做局部展示检查。

最新修订的局部 CPU 离屏检查覆盖两种画布尺寸的左／中／右位置：卡片保持竖排、半环始终在右、控件在边界内且不互相遮挡；Distance 标签位于毫米映射投影后的连线中点，旧结果隐藏标签，Distance 无抽屉而 LOS／Move 保留抽屉，QML 无错误。证据在 `outputs/refactor_checks/qt_live_menu_revision_20261111/checks.json`；未重复全节点回归。

Terra 的同一批验收检查注册／Live 加载、实际点选与 Distance 目标、两种窗口截图、未知资料、真实距离／有正面 LOS、Move／Double 候选、观测更新及过期叠加、Done／Esc／清除／Reset、两侧六按钮和短段源推进。复现一处左边缘信息卡／Distance 遮挡，已按原型的左缘紧凑布局修正；主实现只做该局部修正的 QML 检查，左／右／窄画面按钮均在范围内、无信息卡重叠。证据在 `outputs/refactor_checks/qt_live_terra_20261111`（包括 `edge_fix.json`）。

没有实际模型／GPU／原生桌面，短段源推进没有持续 tracker 输出或历史存储；完整持续追踪／历史、所有 Estimated 组合及旧 OpenCV 有效结果绘制未完整覆盖，保留后续集中验收。当前代码未再次提交。

右侧不确定列表后续修订已由独立 Terra-medium 检查正常 tracking、pending／failed／waiting、Unknown、旧 unchecked 及 queued／searching／inactive 过滤，两个尺寸根窗口加载与原 ID 点选通过。双栏溢出已修正，主实现定向复查 260／300 px 均在内边距内且无 QML 错误；完整 Live 场景中的侧栏显隐及动态布局仍未完整覆盖。证据在 `outputs/refactor_checks/qt_uncertainty_adaptive_terra_20261111`（含 `panel_fix.json`）。

## 集中验收要求

公开入口仍为 `python -m frontend.qt VIDEO`；窗口工厂见 Qt README。使用 CPU 受控模型输出、真实视频解码和 Qt offscreen/software，不新增测试文件、不操作原生桌面；实际 GPU 非本节点必需。

检查两种窗口尺寸、注册／Live 加载无 QML 错误、点选与空白取消、菜单固定／选框跟踪、边缘按钮可达、Damage 未知不补零与 Speed 来源、三种条件 Estimated 与正面未知、真实 Distance／LOS／Move 结果及不可用原因、工具切换／Done／Esc 清理、过期查询不显示、source/history 持续、Reset／关闭失效。真实模型准确率及原生交互性能未实测时须明确未覆盖。只给 Terra 验收要求、公开入口及必要约束；返回复现失败／证据及覆盖统计，主实现独立定位修正。
