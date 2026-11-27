# 全局代码、架构与算法 SOTA 审查报告（2026-11-22）

> 本文档完整整理了 2026-11-22 只读全局审查与独立交叉核验的结果（未修改任何源码），用于后续逐批规划修复与重构。所有问题均已对照源码、Git 历史（含 `1db6d9c`）及 [AGENTS.md](../AGENTS.md)、[TODO.md](../TODO.md)、[待澄清列表.md](../待澄清列表.md)、[项目思路.md](../项目思路.md)、[追踪优化调研与执行计划.md](../追踪优化调研与执行计划.md)、[前端解耦重构计划.md](../前端解耦重构计划.md) 完成核实，并已剔除误报与既有待审批设计。

---

## 逐项复审进度（2026-11-27）

保留 11 月 22 日原报告作为历史基线。**舍弃**表示不再纳入本轮复审或修复；**待复审**不代表已批准实施。先补完已经讨论过的大项，再看未逐项讨论的大项。

| 大项 | 状态 | 本轮记录 |
| --- | --- | --- |
| 1.1 快照与刷新 | 部分已改 | Qt Live／Replay 重复刷新已修、离屏回归通过。应用快照重建及 Recovery 预览缓存待复审。 |
| 1.2 默认推理频率 | 已解决 | 已恢复每秒 1 次。 |
| 1.3 EdgeTAM 会话释放 | 部分已改 | 两个回调的循环引用已修，CPU 和 7900 XT 短测通过。其余释放路径及长局表现待复审。 |
| 1.4 B08 重标定 | 1.4.1／1.4.2 已改（未提交） | 1.4.1 失败后原地重试已修、Qt 离屏通过。1.4.2 已修坏种子迁移和漏种子原 ID 接回。复现了旧版拒绝，应用入口受控验证自动／手动接回、零可信种子保留旧会话。RX 7900 XT 以真实 EdgeTAM 权重、实拍帧和合成掩码验证同帧追加及下一帧接续。1.4.3 本轮舍弃，静态确认 B08 覆写 R 的回跳起点（未做整链路验证）。1.4.4 本轮舍弃，普通片尾落后时会主动请求末帧。受控检查确认末帧已提交但无合格观测时仍等待，未复现真实片尾卡死。Qt 已校验尺寸和角点排列，应用入口仍推迟完整校验。 |
| 1.5 Recovery | 1.5.1–3／1.5.6 已改（未提交） | 1.5.3 两条已修：切到无自动候选的单位时清除旧审核草稿；红色 Correct 只解除当前单位的自动候选关联。30 单位存档的 Qt 离屏受控验证通过。补验红色 Correct 期间新失败的目标不会自动排队或接回。其他 ID 可自动恢复。串行调度回归确认，A2 搜索期间 A1 仅排队就被 Correct 接管时，取消或切换仍保留 A1 的首次搜索资格。已派出的搜索和成功手动接回均未再次排队。1.5.1 已修。实际 Qt/QML 离屏用实拍文件末帧和模型替身验证无解时提示并解锁、可对齐时同帧接回、播放中等待、重试及模型故障保护。补验确认时候选从帧 35 追到 36 抛异常，经真实 EdgeTAM 适配器重置后窗口解锁，主追踪与历史保留。有效同帧草稿仍可在占用或输入校验拒绝后重试。1.5.2 已修。手动／自动区分校验拒绝与同帧写入失败，受控验证草稿、历史和拟合保护及迟到结果隔离。RX 7900 XT 的真实 EdgeTAM 短测通过未知 ID 拒绝及漏种子同帧追加。1.5.4 本轮舍弃：手绘 mask 与点提示是独立输入方式，不要求用正负点编辑手绘轮廓（D31）；评审提到的记忆槽未另作真实模型验证。1.5.5 同帧重复更新／异常回滚未跑真实模型。1.5.6 已修。手动／自动恢复及 B08 通过受控拟合复用检查，下一帧立即丢失记录一次追踪缺口。 |
| 1.6 较早的注册读档 | 舍弃 | 读档仅限开播前、注册未锁时，本轮不修。 |
| 1.7 并发与叠加层 | 部分已改（未提交） | 整批托盘异常已修，受控回归确认旧几何和时间戳保留、失败批次不入历史。1.7.2 暂停时旧异步图与名牌覆盖同步结果已修，Qt 离屏用受控 Future 和实拍文件末帧验证；连续播放仍发布已完成图层。模式键问题在当前 Live／Replay 往返未复现，Replay 跳过 Live 叠加渲染，返回后虚线托盘仍可见。另有独立复核指出 Replay 返回 Live 时可能短暂闪回旧图层和名牌，本轮舍弃。1.7.1 正面朝向相关的线程问题：舍弃（当前功能关闭，暂未找到合适的朝向记录方案）。 |
| 1.8 自动恢复算法 | 待复审 | 未逐项讨论。 |
| 1.9 LOS 与裁剪 | 舍弃 | LOS 为草稿，不纳入本轮修复；已有 TODO G13 记录人工对照与实测，不重复加项。 |
| 1.10 托盘几何与军表 | 待复审 | 未逐项讨论。 |
| 1.11 特定后端与休眠模块 | 待复审 | 仅涉及正面朝向（Facing）的子项本轮舍弃；其他子项未逐项讨论。 |

## 目录

- [概览与审查基线](#概览与审查基线)
- [一、已交叉核实的 P0 / P1 高优先级缺陷（按根因归类）](#一已交叉核实的-p0--p1-高优先级缺陷按根因归类)
- [二、P2 / P3 问题与实测性能瓶颈](#二p2--p3-问题与实测性能瓶颈)
- [三、架构、模块解耦、死代码与工程卫生](#三架构模块解耦死代码与工程卫生)
- [四、六大算法线 SOTA / 更优解深度调研（2024–2026）](#四六大算法线-sota--更优解深度调研20242026)
- [五、核验排除与需求约束对照表](#五核验排除与需求约束对照表)
- [六、分阶段实施路线图](#六分阶段实施路线图)

---

## 概览与审查基线

- **审查范围**：`application/`（16 个文件）、`frontend/`（Qt Quick Python/QML、共享层、独立查看器）、`tools/`（20 个 CLI 脚本）、`components/` 全业务与算法包（第三方 `vendor/cutie/` 仅审查 `components/tracking/cutie.py` 封装边界）。
- **基线状态**：当前工作区存在 20 个已修改文件与 4 个未跟踪 QML 文件（Qt 近期 Live/Terrain/Recovery/Replay 迭代）；本机默认运行环境为 Windows + Python 3.13 + PyTorch 2.13 + `transformers==5.18.0` + AMD Radeon RX 7900 XT (ROCm)。
- **架构与安全正面评价**：
  - **依赖方向健康**：AST 扫描确认 `components/` → `application/` → `frontend/` 严格单向无反向导入；`frontend/qt/` 未直接接触 `MatchApplication._session` 或 `GameData`。
  - **I/O 与序列化安全规范**：全仓无裸 `cv2.imread`/`cv2.imwrite`（统一经 Unicode 安全的 [image_io/io.py](../components/image_io/io.py)），无 `pickle`/`shell=True`，统一使用 `torch.load(..., weights_only=True)` 与 `np.load(..., allow_pickle=False)`，存档与特征加载带有路径穿越校验（`_inside()`）。
- **核心风险汇总**：

| 严重度 | 核实数量 | 集中表现 |
| --- | --- | --- |
| **P0 / P1** | 11 组（已按根因去重） | 60 Hz 快照重冻结击穿缓存、`DEFAULT_INFERENCE_FPS=5` 回归、EdgeTAM GPU 会话自环与漏释放、B08 与 Recovery 锁死/串对象/状态失步、`load_archive` 崩溃、跨线程与叠加层竞态、LOS/裁剪数学漏洞、托盘拟合面积矛盾、自动恢复 NMS 与竞争误杀 |
| **P2 / P3 & 性能** | 40+ 项 + 6 大性能热点 | `describe_mask`（150ms/帧）、`fit_tray` 无效 LSD、Qt 60 Hz 重绘与 `Theme` 冗余、SQLite 每帧开关连接与 WAL 崩溃恢复陷阱、军表解析边界、双份常驻 FP32 SAM3 显存 |
| **架构 / 工程** | 7 大类 | 4 个上帝对象、`sam3` 反向依赖 `edgetam`、前端直调 `detect_table`、坐标契约不统一、`requirements.txt` 缺 `PySide6`、`.gitignore` 忽略 `docs/` |

---

## 一、已交叉核实的 P0 / P1 高优先级缺陷（按根因归类）

### 1.1 [P0/P1] 60 Hz 快照递归重冻结 + `id()` 缓存键失效风暴

- **涉及位置**：[app.py](../application/app.py#L104-L135)、[board.py](../frontend/qt/board.py#L552)、[bridge.py](../frontend/qt/bridge.py#L139-L152)、[bridge.py](../frontend/qt/bridge.py#L195-L213)、[workflows.py](../frontend/qt/workflows.py#L628)、[workflows.py](../frontend/qt/workflows.py#L649)、[workflows.py](../frontend/qt/workflows.py#L1250)、[registration.py](../application/registration.py#L442-L499)
- **问题机制**：
  1. `MatchApplication.snapshot()` 将 `session.source.frame_index` 放入 `_snapshot_key`。60 fps 播放时每帧缓存必未命中，触发对整个静态 `UnitRoster`（含完整 PDF 附录 `payload`）、30 个托盘（含十六进制 `mask_bits`）、`tracking`、`board` 和 `rules` 的深度递归 `freeze()`，每帧重新分配全新的 `MappingProxyType` 实例。
  2. 前端多处把 `id(...)` 当作内容未变的缓存键：
     - `BoardRenderer.overlay_key`（[board.py](../frontend/qt/board.py#L552)，2026-11-21 新增）使用 `id(state.units.types)` → **2026-11-16 三层异步叠加缓存被彻底击穿**，`qt-overlay` 后台线程每帧都在全分辨率烘焙 BGRA mask/托盘/积分图避让名牌并反复上传纹理。
     - `MatchBridge`（[bridge.py](../frontend/qt/bridge.py#L195-L213)）`catalog_key` 使用 `id(state.units.types)` → 每帧（以及注册阶段模型加载进度刷新时）发射 `catalogChanged`，销毁重建 `CatalogPanel.qml:135` 的 `Repeater` 代理，直接破坏拖拽绑定稳定性。
     - `Workflows`（[workflows.py](../frontend/qt/workflows.py#L1250)）`interactive_key` 使用 `id(state.recovery["preview"])` → Recovery 阶段以 60 Hz 对静态预览 mask 重跑全分辨率 `findContours`/`drawContours` 与 `QImage` 上传。
     - `Workflows`（[workflows.py](../frontend/qt/workflows.py#L628)）`replay_steps_key` 使用 `id(state.units.types)` → 后台播放期间以 60 Hz 重构 Replay 步骤列表（虽然 `:649` 发信号前做了值比较）。
  3. Replay 模式下 [bridge.py](../frontend/qt/bridge.py#L139-L152) 的 `video_key` 包含 `state.source_ref` 和 `state.revision`，导致每帧把静态 ~4.7 MB 的 `_replay_image` 执行 `QImage.copy()` 并重传 GPU，还对未展示的帧调用 `match.present(state.source_ref)`。
  4. `_snapshot_key` 漏掉 `debug_paused`、`data.reference_folder`、`worker.facing.error`、`session.tray_status()`；同时 `Registration.finish_registration()` 未调用 `self._session.mark_changed()`，锁定注册时不递增 `view_revision`。另 `_snapshot_key` 读取 `worker.models_loaded`（`app.py:106`），而 `MatchSnapshot.model_loaded` 读的是 `worker.predictor.model is not None`（`app.py:127`）。
- **修复建议**：
  - 在 `MatchApplication` 内为 `Board`、`Roster`、`Rules`、`Current`、`Tracking` 分别按独立变更版本号缓存只读子快照，60 Hz 播放仅浅替换外层 `MatchSnapshot` 的 `source_ref` 与 `source_image`，并在发布点将 numpy 图像/mask 设为只读（`write=False`）。
  - 前端彻底禁用 `id(...)` 做缓存键，改为显式单调 revision（如 `catalog_revision`、候选观测序号）或值键。

---

### 1.2 [P1] `DEFAULT_INFERENCE_FPS = 5` 意外回归

- **涉及位置**：[config.py](../application/config.py#L8)、[arguments.py](../frontend/arguments.py#L18)（由 Git 提交 `1db6d9c` 引入）
- **问题机制**：一次无关的 Live 虚线托盘 UI 提交将 `DEFAULT_INFERENCE_FPS` 从 `1.0` 意外改写为 `5`。当前 `frontend/arguments.py:18` 输出自相矛盾的帮助文本 `"default: 5 Hz = 1.0s interval"`，更重要的是将 EdgeTAM 固定的 6 个非条件空间记忆槽所覆盖的抗遮挡时间窗口从 **~6 秒骤缩到 ~1.2 秒**（违背 [TODO.md](../TODO.md#L15) 与 [项目思路.md](../项目思路.md#L187) 约定），同时把 GPU 推理压力拉高 5 倍。
- **修复建议**：恢复 `DEFAULT_INFERENCE_FPS = 1.0`，并将 `arguments.py` 帮助文案中的间隔改为根据配置动态计算。

---

### 1.3 [P1] EdgeTAM GPU 会话显存泄漏（自引用环 + 漏调 `release()`/`reset()`）

- **涉及位置**：[edgetam.py](../components/tracking/edgetam.py#L221-L229)、[tracking/recovery.py](../components/tracking/recovery.py#L27-L38)、[application/recovery.py](../application/recovery.py#L61-L84)、[application/recovery.py](../application/recovery.py#L180-L185)、[application/automatic_recovery.py](../application/automatic_recovery.py#L49-L155)、[task_worker.py](../application/task_worker.py#L335-L406)、[calibration.py](../application/calibration.py#L155-L172)
- **问题机制**：
  1. `configure_video_session`（`edgetam.py:227-228`）将 `types.MethodType(_cache_vision_features_pageable, session.cache)` 和 `types.MethodType(_store_output_pageable, session)` 直接绑定在实例自身 `__dict__` 上，构造了 `obj -> __dict__ -> MethodType.__self__ -> obj` 的强引用循环（已禁用 GC 用 `weakref` 验证）。一旦候选未被显式释放，~100–168 MiB GPU 张量在引用计数归零时无法即时释放，只能等待 Gen-2 GC。
  2. `RecoveryCandidate.cancel()` 仅设置布尔标记 `self.cancelled`；而 `candidate.release()` 目前仅在 `TaskWorker._run` 处理 `"propagate"` 或 `"recovery_commit"` 时调用（`task_worker.py:335, 344, 406`）。主线程侧 `Recovery` 和 `AutomaticRecovery` 取消/失效/替换候选后立即清空引用，未在 `propagate` 队列中的被取消候选永远不会经过 `TaskWorker` 调用 `release()`；`RecoveryCandidate.seed_mask` 空 mask 分支（`tracking/recovery.py:27-29`）也只调 `cancel()` 漏调 `release()`。
  3. B08 `commit_recalibration()`（`calibration.py:169-172`）替换 `worker.tracker`/`predictor` 时从未对旧后端调用 `.reset()`，且 `accept_result()`/`session.advance()` 在取消、mask 迁移失败或代次过期时也未对已创建的 `request["new_backend"]` 调用 `.reset()`。
- **修复建议**：使用 `weakref` 代理或在统一的 `release_video_session()` 中删除绑定方法并清空字典；所有取消/丢弃/替换候选或 B08 后端的路径必须显式调度或执行 `release()`/`.reset()`。

---

### 1.4 [P1] B08 重标定四联问题（UI 锁死 / 漏种子单位变砖 / 破坏 `R` 重置 / EOF 卡死）

- **涉及位置**：[workflows.py](../frontend/qt/workflows.py#L566-L568)、[workflows.py](../frontend/qt/workflows.py#L1150)、[WorkflowControls.qml](../frontend/qt/WorkflowControls.qml#L395)、[calibration.py](../application/calibration.py#L45-L49)、[calibration.py](../application/calibration.py#L102-L178)、[recalibration.py](../components/recalibration.py#L28-L35)、[edgetam.py](../components/tracking/edgetam.py#L629-L632)、[session.py](../application/session.py#L617)、[app.py](../application/app.py#L80-L81)
- **问题机制**：
  1. **失败后 UI 永久锁死**：`Workflows.publish()`（`workflows.py:566-568`）只在 `match.calibration.status is None` 时清除 `_calibration_pending`。当 `prepare_recalibration()` 或 `"recalibrate"` 后台任务失败时（`calibration.py:131-135, 157-161`），故意保留 `_context` 以显示报错，此时 `status` 返回 `{"draft": None, "pending": None, "error": "..."}`（非 `None`），导致 `_calibration_pending` 永久为 `True`，角点点击与 `Apply` 按钮被锁死直至用户取消退出 B08。
  2. **漏种子单位永久不可恢复 + 误带入失效/非活跃单位**：`prepare_recalibration()`（`recalibration.py:28-35`）直接跳过重投影后 mask 为空的绑定单位（`unseeded_units`），使新初始化的 `EdgeTamTracker.object_ids` 不包含这些 ID；此后对这些单位做任意自动或手动 `update_mask()` 都会触发 `edgetam.py:629-632` 的 `ValueError("Recovery requires a nonempty mask for an existing object")`，使其永久无法恢复。同时 `prepare_recalibration()` 未过滤 `unavailable_ids` 或 `inactive_ids`，会把处于 failed/corrupt 或 `routed`/`removed` 状态的非空 mask 重新塞进新追踪器。
  3. **覆写初始帧破坏 `R` 重置**：`commit_recalibration()`（`calibration.py:177-178`）把 `session.registration_start_frame` 和 `session.initial_frame` 改写成 B08 发生的帧号。之后按 `R` 重置会跳到 B08 帧而不是 `--start`；若启动时带 `--seconds`（固定 `end_index`），在片尾重标定后再按 `R`，`source.frame_index >= end_index` 会永久死在 `"End of video interval. R restarts."`。
  4. **EOF 提交卡死 + `apply_recalibration` 跳过校验**：`Calibration.submit_pending()`（`calibration.py:119-127`）在 `metadata["frame_index"] < context["frame_index"]` 且片尾无法继续读出新帧时永远无法提交；`apply_recalibration()`（`calibration.py:102-111`）未同步校验桌角和尺寸就先返回 `"pending"`。
- **修复建议**：区分 `status is None` 与 `not status["pending"] and not status["draft"]` 以正确解锁 `_calibration_pending`；B08 初始化必须保留全部已注册 `active` 单位 ID 契约（对空掩码或已缺失单位保持非激活/缺失槽位而非从 `object_ids` 除名），且过滤 `inactive_ids`/`unavailable_ids`；不再修改 `registration_start_frame` 和 `initial_frame`；在 `apply_recalibration()` 先做同步校验并处理片尾帧复用。

---

### 1.5 [P1] Recovery 死锁、前置标志误置、连带清库、切换目标串对象、EdgeTAM 提示缺陷与 `_geometry_visible` 失步

- **涉及位置**：[application/recovery.py](../application/recovery.py#L41-L252)、[session.py](../application/session.py#L258-L510)、[task_worker.py](../application/task_worker.py#L212-L405)、[workflows.py](../frontend/qt/workflows.py#L766-L1128)、[tracking/recovery.py](../components/tracking/recovery.py#L26-L95)、[edgetam.py](../components/tracking/edgetam.py#L253-L254)、[edgetam.py](../components/tracking/edgetam.py#L608-L646)
- **问题机制**：
  1. **EOF 提交死锁与忽略 `model_failed`**：`Recovery.take_request()`（`application/recovery.py:219-222`）在 `observed["frame_index"] < candidate.backend.source_frame` 且 `source.frame_index <= worker.tracker.source_frame`（例如片尾之前已有过一次失败提交）时返回 `None`，却让 `self.committing` 永远停在 `True`；Qt 层（`workflows.py:766, 1032`）在 `committing=True` 时拦截 Cancel/Esc/Clear/工具操作，必须 `R` 重开才能脱困。此外 `MatchSession.schedule()`（`session.py:289, 331`）调度 `recovery.take_request()` 和 `recovery_advance` 时漏查 `not self.model_failed`，且 `session.py:506-510` 在触发 `model_failed` 时不取消在途或正在提交的恢复。
  2. **参数校验前误标已消费**：`TaskWorker._run("recovery_commit")`（`task_worker.py:403`）在调用 `self.tracker.update_mask(...)` 校验输入之前就置 `request["recovery_applied"] = True`（`automatic_recovery` 在 `:212` 同理提前写入 `automatic_consumed`）。一旦前置校验报错（如 B08 后不在 `object_ids`），`MatchSession._accept_recovery_result()`（`session.py:349-363`）误以为底层已修改成功而调用 `fail_recovery()` 并抹掉 `_preview`。
  3. **Qt 红色 `Correct` 连带清空其他自动候选 + 审核切目标串对象**：
     - `workflows.py:795-804` 对存在自动候选的单位点红色 `Correct` 时，先调 `match.recovery.open(uid)` 激活 `review_unit_id`，紧接着调 `match.recovery.report_error(uid)`。因为 `uid` 仍在 `automatic_recovery.records` 中，`report_error` 会触发 `application/recovery.py:124-125` 全局 `automatic_recovery.invalidate(...)`，把**场上其他缺失单位的自动候选全部清零**，同时把 `review_unit_id` 残留在激活态。
     - `workflows.py:1101-1128`（`selectCandidate`）在审核 `A1` 时点击另一缺失单位 `B1`，只修改 `_recovery_target = "B1"` 并提示用 `Points/Rectangle/Four corners`，未调用 `clear_candidate()`。此时用 `Points` 点击会调用 `Recovery.point()`（`application/recovery.py:146-156`），直接往 **`A1` 的候选**上加点。
  4. **手绘 `seed_mask` 同帧补点丢失四边形 + `correct_points` 写入短期记忆槽**：
     - `seed_mask` 用手绘矩形/四边形初始化 EdgeTAM 后，`prune_video_session`（`edgetam.py:253-254`）立刻弹出 `mask_inputs_per_obj[0][0]`。若操作员同帧再点正/负点微调，`RecoveryCandidate.correct()`（`tracking/recovery.py:87-95`）仅向 `EdgeTamTracker.correct_points()` 传 `[seed_point(质心), user_point]`，导致 2 个点重新预测并**完全覆盖手绘四边形**。
     - `EdgeTamTracker.correct_points()`（`edgetam.py:617-624`）未像 `update_mask:635-636` 那样移除 `frames_tracked_per_obj[0][self.index]` 和 `non_cond_frame_outputs[0][self.index]`。因前一步已跑过推理，HF `5.18.0` 会把人工点提示存进 6 帧后即淘汰的 `non_cond_frame_outputs`，而非 `cond_frame_outputs`；直接调用且 `source_frame > self.source_frame` 时还会白跑一次完整 `propagate()` 再同帧重算 `_infer()`。
  5. **同帧重复 `update_mask` 与异常后污染会话**：`EdgeTamTracker.update_mask`（`edgetam.py:635-646`）未执行 `cond_frame_outputs.pop(index, None)`，同一帧重复更新同一 ID 或更新第 0 帧时失效；若 `_infer()` 中途抛异常，会话里会遗留脏的 `obj_with_new_inputs` 与 `mask_inputs_per_obj` 污染下一帧（注：`finally:` 推进 `self.index`/`self.source_frame` 是 `待澄清列表.md` CL18 的刻意要求，应保留）。
  6. **`_geometry_visible` 恢复/B08 后未同步**：`session.py:258, 355, 381, 460-467` 只在 `start_stream()` 与 `_queue_geometry()`（`propagate`）更新 `_geometry_visible`。恢复或 B08 接纳后的下一帧 `propagate` 会把刚恢复单位判为刚出现（`visible ^ _geometry_visible`），调用 `trays.invalidate(...)` 误删其新托盘基线；若刚恢复的单位紧接着在下一帧又消失，`lost = _geometry_visible - visible` 会漏抓它从而跳过 `tracking_gap`。
- **修复建议**：按以上 6 点逐一收紧状态转换（先校验后置消费标志、片尾超时/错误保护、`report_error` 定向清理单 ID、`selectCandidate` 切换时清理旧审查草稿、`seed_mask` 同帧保留或转提示、`correct_points`/`update_mask` 清理条件帧字典与异常回滚、恢复/B08 提交同步 `_geometry_visible`）。

---

### 1.6 [P1] `Registration.load_archive()` 残留旧 `prediction_metadata` 导致 Qt 崩溃

- **涉及位置**：[application/registration.py](../application/registration.py#L106-L118)、[game_data.py](../components/game_data.py#L75-L79)、[bridge.py](../frontend/qt/bridge.py#L697)
- **问题机制**：`load_archive()` 仅将 `data.current.prediction = None`，未清空 `prediction_metadata`、`prediction_frame` 和 `geometry_frame`。如果用户加载存档前曾在更高帧号（例如 `--start` 大于存档帧）或更高 `calibration_version` 上产生过草稿预测，那么 `data.accept_observation(..., disappearance_seconds=...)` 会被单调性保护静默拒绝返回 `False`，`prediction` 维持 `None`，`record_history(kind="registration")` 也返回 `False`，但 `load_archive()` 依然返回 `CommandReceipt("accepted")`，随即 `frontend/qt/bridge.py:697` 访问 `prediction["object_ids"]` 时抛出 `TypeError` 崩溃。
- **修复建议**：将状态重置集中到 `MatchSession.replace_state(...)`，确保 `load_archive()` 彻底清空所有单调帧号/代次元数据；且若 `accept_observation` 为 `False` 应拒绝提交并报错。

---

### 1.7 [P1] 并发竞态、叠加层状态错乱与 `TrayWorker` 吞异常清空托盘

- **涉及位置**：[session.py](../application/session.py#L207-L227)、[session.py](../application/session.py#L271-L276)、[session.py](../application/session.py#L419-L433)、[session.py](../application/session.py#L591-L596)、[task_worker.py](../application/task_worker.py#L284-L315)、[tray_worker.py](../application/tray_worker.py#L110-L116)、[board.py](../frontend/qt/board.py#L391)、[board.py](../frontend/qt/board.py#L538-L617)
- **问题机制**：
  1. **跨线程读写 `TaskWorker` 属性**：`MatchSession.schedule()` 在 `if self.worker.busy: return`（`session.py:276`）之前就直接写入 `worker.facing_fronts`/`worker.facing_excluded`（`session.py:271-274`），且 `reset()`/`load_archive()`/`capture_facing_references()`/`commit_facing()` 也在主线程直接修改 `tracker_initialized` 与 `facing_*`；与此同时 `sam3-video` 工作线程正在 `TaskWorker._run("reset")` / `"start_tracker"`（`task_worker.py:284-315`）读写同一组字段，构成数据竞争。
  2. **`BoardRenderer` 异步/同步竞态 & `overlay_key` 漏 `state.mode`**：`BoardRenderer` 缺少单调 sync 序号。从播放切换到暂停（如进入 Debug 关掉 Masks）时，`sync_overlay` 同步烘焙新图并发布，但同 `generation` 已在途的 `qt-overlay` future 晚一拍在 `poll_overlay()` 完成并覆盖 `_overlay_key`、`badges` 与画面，造成闪烁。此外 `_bake_static_overlay`（`board.py:391`）仅在 `state.mode == "live"` 时画虚线托盘（`held_ids`），而 `overlay_key` 漏了 `state.mode`（目前被 1.1 的 60 Hz 缓存击穿掩盖；一旦修好 1.1，从 Replay 切回 Live 时会命中缓存导致所有虚线托盘消失）。
  3. **`TrayWorker` 吞异常清空全部托盘**：`TrayWorker.take_ready()`（`tray_worker.py:110-116`）捕获 `future.result()` 异常后包装成 `error=None, trays={}` 的空预测交给 `_accept_geometry()`。`session.py:428-433` 的错误分支被完全绕过，系统直接接纳空托盘集合、清空全部 `trays.attempts` 并把所有 30 个单位标为 `unavailable`，瞬间打断所有进行中的移动事件。
- **修复建议**：`facing_*` 改为通过 `submit()` 载荷单向传入 worker、禁止主线程直改 worker 内部字段；`BoardRenderer` 增加单调 `_sync_seq` 并在 `overlay_key` 补齐 `state.mode`；`TrayWorker.take_ready()` 保留真实 `error` 字符串上抛至 `_accept_geometry()` 错误保护分支。

---

### 1.8 [P1] 自动恢复算法实现缺陷（直接关联 [TODO.md](../TODO.md#L23) P1）

- **涉及位置**：[automatic_recovery.py](../components/tracking/automatic_recovery.py#L21-L36)、[automatic_recovery.py](../components/tracking/automatic_recovery.py#L46-L56)、[automatic_recovery.py](../components/tracking/automatic_recovery.py#L68-L79)、[matching.py](../components/dinov2/matching.py#L21)
- **问题机制**：
  1. **缺少 SAM3 输出 Mask-IoU NMS**：`Sam3Segmenter("miniature", threshold=0.30)` 经常对同一个实体产出多个高度重叠的分片或重复框（例如余弦分别达到 `0.94` 和 `0.91`）。`rank_candidates` 直接比较全局前两名得出 `top_two_margin = 0.03 < 0.10`，把本来极其确信的唯一匹配误杀为 `"Low similarity or small margin"`。
  2. **无门槛竞争拦截**：只要两个缺失单位各自 top-1 候选存在 ≥1 像素重叠，就无条件判为 `"Competing missing instances"` 并冻结，不考虑分数高低。某个已彻底离场的单位只要在场上随便抓到一个 `cosine=0.25` 的背景噪声，正好和另一真实在场单位的 `0.95` 候选挨着或重合 1 px，就会锁死高分匹配。
  3. **粘滞 `load_error`**：`AutomaticRecoveryEngine.load()` 重试成功加载后没有将 `self.load_error = None` 清空。
  - *(注：自动恢复中对正常单位的 1 px 重叠排斥 [automatic_recovery.py:16](../components/tracking/automatic_recovery.py#L16) 在 [项目思路.md](../项目思路.md#L24) 中属既有待审批设计，非代码回归，但建议审批后复用手动恢复的 `RECOVERY_OVERLAP_REJECT_RATIO = 0.20` + 边界裁剪逻辑，否则近战接敌单位必拒。)*

---

### 1.9 [P1] `game_rules` 视线（LOS）与裁剪数学错误

- **涉及位置**：[queries.py](../components/game_rules/queries.py#L36-L44)、[queries.py](../components/game_rules/queries.py#L70-L104)、[game_rules/geometry.py](../components/game_rules/geometry.py#L164-L168)
- **问题机制**：
  1. **LOS 沿弧外与背向射线穿透自身底座返回 `clear`**：`line_of_sight`（`queries.py:70`）只把 `front_arc_clip(b['corners_mm'], ...)` 当布尔判断；第 87 行仍沿着目标**未裁剪的完整四条边**采样终点 `targets`，既不校核 `q` 是否在前弧内，也不拒绝穿过观察者自身底座的射线。当目标仅一角进入 45° 前弧且该前弧路径被 Height 5 障碍完全挡死时，算法会从前边向后穿过自身底座连到目标的弧外背边并返回 `status='clear'`。
  2. **LOS 在边界接触时穿透实心 `blocking` 地形**：`queries.py:93`（`if terrain and (g.inside(p, poly) or g.inside(q, poly)): continue`）与 `_edge_samples`（`:39-43`）使用 `boundary=True` 的多边形包含检测。只要单位底座边缘贴靠在 Height 10 `blocking` 实心墙外表面，就会触发 `inside == True` 跳过阻挡体直接看穿整面墙。
  3. **`front_arc_clip` 数值外推爆炸**：`game_rules/geometry.py:164-168` 用 `va >= -EPS` 判定顶点在半平面内，却用 `t = va / (va - vb)` 求交；当 `-EPS <= va < 0` 且 `vb < -EPS` 时，随着 `vb -> va⁻`，`t` 越出 `[0, 1]` 暴涨至 `1e7+` 乃至 `1e16`，给完全位于身后的目标凭空外推出一个“前弧交集多边形”。
- **修复建议**：将采样终点改到裁剪后的前弧交集多边形上，且拒绝穿过观察者内部；`kind == 'blocking'` 地形永不走 `inside` 豁免（非阻挡 see-in/see-out 地形也应使用严格内部 `boundary=False` 或正面积交叠）；`front_arc_clip` 对 `t` 严格钳位 `[0, 1]` 或统一阈值基准。

---

### 1.10 [P1] 托盘拟合部分可见区间矛盾、角点去重 Bug 与双军表 `with_list()` 缺陷

- **涉及位置**：[tray/detector.py](../components/boundary_detection/tray/detector.py#L42-L43)、[tray/detector.py](../components/boundary_detection/tray/detector.py#L134-L135)、[tray/detector.py](../components/boundary_detection/tray/detector.py#L176-L397)、[registration/units.py](../components/registration/units.py#L181-L198)
- **问题机制**：
  1. **边缘 `[0.80, 0.85]` 可见区间数学不可达**：`min_visible_fraction = 0.80` 允许画面边缘只露出 80% 投影面积的托盘，但 `_Scorer.mask_scores` 和 `_acceptance` 使用**完整托盘面积**作为分母并严格要求 `mask_fill > 0.85`。因为画面外像素不可能出现在 `work_mask` 中，任何平面可见度在 `80%–85%` 的托盘数学上最高填充率也不会超过其可见比例（实测 82% 可见干净合成 100×80 托盘得 `best_fill=0.8404 -> success=False`）。*(注：`[项目思路.md](../项目思路.md#L93-L97)` 分别记过 0.80 与 0.85，修改该门槛或改用可见面积分母需明确对齐确认。)*
  2. **角点去重误杀 T/X 交叉点并保留乱序重复**：`_corners()`（`tray/detector.py:134-135`）用 `abs(item["rays"][0] @ old["rays"][0]) > 0.97` 去重，忽略射线正负方向、`rays[1]` 与边序。在 T/X 型交点处，射线方向 `(+x, -y)` 会被当作 `(+x, +y)` 的重复误删；而同一角点调换边序成 `(+y, +x)` 时内积为 0 反倒绕过去重并占满 `max_corners` 名额。
  3. **`UnitRoster.with_list("B", ...)` 冲突与静默丢弃 A 方附录**：旧单军表未标 `list_id` 时默认为 `"A"`，若旧目录里本来有名为 `"B1"` 的 type，后续调用 `with_list("B", ...)` 会产生重复键抛出 `ValueError: Duplicate type_id: B1`；此外当 A 方通过 `UnitRoster(sam)` / `UnitRoster.load()` 载入后调用 `with_list("B", ryan)`，第 192 行只写入 `metadata["A"] = {"source": self.source}` 漏掉 `"metadata"` 键，静默丢弃 A 方的 `sources`/`appendix`（法术、神器、特殊规则）。

---

### 1.11 [P1（特定后端 / 休眠模块）] `VideoPredictor`、`VideoSource` 与休眠 Facing Bug

- **涉及位置**：[sam3/video/predictor.py](../components/sam3/video/predictor.py#L125-L163)、[video_io/source.py](../components/video_io/source.py#L39-L53)、[facing/recovery.py](../components/facing/recovery.py#L41-L73)、[registration/rule_state.py](../components/registration/rule_state.py#L42-L117)
- **问题机制**：
  1. **`--tracker sam3` 路径隐患**：`VideoPredictor.propagate()` 在 `_infer()` 前就修改 `self.index`/`self.source_frame`，且缺少 `EdgeTamTracker`/`CutieTracker` 均有的 `try/except: self.reset(); raise` 异常保护；同时未启用 `SDPBackend.MATH`，在 RX 7900 XT ROCm 上走 `--tracker sam3` 会命中慢速 `EFFICIENT_ATTENTION` 分支。
  2. **`VideoSource.read_frame` 游标失步与冗余寻帧**：顺序跳帧中若 `grab()` 失败（`:43-45`）或 `CAP_PROP_POS_FRAMES` 定位后 `read()` 失败（`:47-50`）抛出异常，底层 `cv2.VideoCapture` 内部位置已经改变，但 `self.frame_index` 未置为无效（如 `None`），之后以相对 `grab()` 读取会静默返回错位帧；且未校验 `capture.set(...)` 返回值与实际 PTS/帧号；重复请求 `index == self.frame_index` 会落入昂贵的 keyframe seek 分支。
  3. **休眠功能（仅在 `FACING_TRACKING_ENABLED` 重新开启后触发 P1）**：
     - `FacingRecovery.evaluate`（`facing/recovery.py:41-73`）：只要出现单帧托盘拟合失败或空 mask，`phase="failed"` 就被改写为 `"waiting"`；下一正常帧中若 `front is None`（`:71`）会跳过 `retry_change`/`retry_seconds` 限制每帧狂调 DVMNet，若存在 `front`（`:73`）则直接把 `"failed"` 洗白回 `"tracking"`。
     - `RuleState` 正方形托盘 `parity` 90° 跳变（`rule_state.py:42, 73, 80, 84, 117`）：`tray/detector.py` 对方形托盘（40×40 / 50×50 / 75×75 mm）按 `period = pi/2` 求解，跨过 `0°/90°` 时角点编号顺/逆时针循环移位（`edge 0 <-> edge 3`），奇偶性反转；但 `RuleState` 始终锁死 `parity = edge % 2` 从不设为 `None`（尽管源码已写了 `options = range(4) if front["parity"] is None`），导致方形托盘轻微摆过 0° 就使朝向瞬间暴跳 `±86°`。

---

## 二、P2 / P3 问题与实测性能瓶颈

### 2.1 实测 CPU / GPU / Qt / SQLite 性能瓶颈

1. **`describe_mask` 静态门控拖慢（实测 30 静态 `1920×1080` 单位 ~146–158 ms/帧，~5 ms/单位）**：
   - [tray/temporal.py](../components/boundary_detection/tray/temporal.py#L39-L51) 与 [tray/batch.py](../components/boundary_detection/tray/batch.py#L34-L53) 每帧对每个静态全分辨率 mask 扫 5 遍 `2.07M` 像素：`mask.any()`、`np.isfinite(mask).all()`（对 `bool`/`uint8` 完全多余却耗 ~10 ms）、`(mask != 0).astype(np.uint8)`（每帧分配 ~60 MB）、全图 `cv2.moments(binary)`、全图 `cv2.boundingRect(binary)`；随后 `tobytes().hex()` 转成十六进制字符串并在 `compare()` 中立刻 `bytes.fromhex()` 解回。
   - **优化**：跳过 `bool`/`uint8` 的 `isfinite`；`bool` 使用零拷贝 `mask.view(np.uint8)`；先求紧凑 bbox 仅在裁剪 ROI 上算 `cv2.moments`（减少 ~250 倍像素量）；内存态保留 `bytes`/`uint8`，仅 JSON 导出时转 `.hex()`。预计静态帧可提速 **5–10 倍**。

2. **`fit_tray` 冗余算力与 搜索盲区（实测单遮挡 Horde `250×100mm` 耗时 252 ms，profile 376 ms）**：
   - **最大浪费（[tray/detector.py](../components/boundary_detection/tray/detector.py#L367)）**：即使 `method == "mask"` 从不使用 `edge_support` 或 `corner_support` 做排序或验收，第 367 行仍对多达 20 个堆候选运行**完整精确 LSD 边打分**！
   - `_Scorer.score`（`detector.py:211`，占 48% 累计时间、444 次调用）每个姿态重复计算 `np.linspace`、`line_delta`、对边重复投影，并在每次被淘汰的候选上调用两次 `transform_points(work_to_plane)`（实际仅是纯均匀缩放+平移）。
   - `_Scorer.mask_scores`（`detector.py:170`，占 24%、1271 次调用）在 Python 循环里对 4096 个 float64 点做单姿态点积，而非按相同角度对 8 个 Beam 邻域一次投影或用积分图/`boxFilter`。
   - `polygons()`（`detector.py:195`）在 `view["visible"].all()` 已确定可见度为 `1.0` 时仍把每个候选点映射回原图（`transform_points` 占 12.5%、2041 次调用）。
   - `DirectionalChamfer`（[directional_chamfer.py](../components/boundary_detection/tray/directional_chamfer.py#L29-L51)，16.3 ms）在 `local` 模式仍计算全部 ~31 路全 ROI 距离变换，且 `detector.py:186` 每次只传 `batch=1` 查询。
   - `make_work_view`（[tray/geometry.py](../components/boundary_detection/tray/geometry.py#L10-L41)，14.8 ms）先扫全图 `np.nonzero(mask)`（重复 `describe_mask` 的 bbox 工作），又分配并 `warpPerspective` 一整张 `1920×1080` `np.ones` 数组仅为了求可见四边形（改为 `cv2.fillConvexPoly` 投影 4 个图角即可）。
   - **精度/搜索结构漏洞**：
     - Beam 步长固定短边 `10%`（最大半步误差 `5%`），而局部精调 `_local_proposals` 只试 `{-2, 0, +2} × 1%`（最大 `±2%`），在 **`[2%, 5%]` 留下不可达盲区**（`detector.py:276-310`）。
     - `_rank`（`detector.py:383`）对正方形仍按 `mod 180°` 而非 `mod 90°` 角度去重。
     - `DirectionalChamfer` 对 `> 12°` 仅做软惩罚而 `score()` 硬淘汰，`beam[0]` 贪心早停（`detector.py:425`）会让不对齐的粗搜榜首抢先截胡更优的 `beam[1]`/`beam[2]`。
     - 小托盘（40×40 mm ~20–32 px）`_Scorer.mask_scores`（`detector.py:174-178`）双边 `<=` 含入 `(w+1)(d+1)` 个整数像素中心，导致 `mask_fill` **系统虚高 `+6%` 至 `+10%`** 并产生 0.5 px 阶跃抖动。

3. **`game_rules` 碰撞与射线检查（`advance` 30 单位 + 5 地形耗时 85 ms；324 条受阻射线耗时 10.6 ms）**：
   - [movement.py](../components/game_rules/movement.py#L153-L175) 和 [queries.py](../components/game_rules/queries.py#L93) 全量跑纯 Python SAT `convex_overlap` 与 `ray_hits` 且**无 AABB 粗筛**；`queries.py:93` 在最内层 `(p, q, poly)` 重复算 36×/9× `g.inside`；`movement.py` 在 `speed_in == 0` 时仍枚举全部 1,715 条路径。

4. **`boundary_detection/merge.py` 线段合并 `O(N³)`（1500 段耗时 430 ms）**：
   - [merge.py](../components/boundary_detection/merge.py#L114-L168) 开启 `source_length=false` 时内层循环每次增边都重扫全量剩余簇并做 `O(k²)` 矩阵乘。

5. **Qt 60 Hz 信号风暴与图形渲染浪费**：
   - `bridge._publish()`（[bridge.py](../frontend/qt/bridge.py#L128-L301)）与 `workflows.publish()`（[workflows.py](../frontend/qt/workflows.py#L748)）每视频帧构造完整 `QVariantMap` 并发射 `ui.changed` / `flow.changed`：
     - [UnitHud.qml](../frontend/qt/UnitHud.qml#L45-L317) 在选中单位时每帧（60 Hz）触发全窗 2D `<Canvas>` 软件重绘（`leader.requestPaint()`）并销毁重建 8 个 stat-cell `Repeater` 代理。
     - Replay / Recalibrate 隐藏 `boardOverlay` 时，`bridge._publish()` 仍在调 `sync_overlay()` 后台烘焙；`bridge.py` 每帧重复序列化 `typesA/typesB/types`、`workflows.py` 重复塞入 `rows`，且 `bridge.py:298-300` 每帧解析两次 `Path(__file__)` 与 `QUrl.fromLocalFile`；`bridge.py:129` 以 60 Hz 重算 `live.uncertainty(state)`。
   - [board.py](../frontend/qt/board.py#L500-L501) 使用 `Format_BGR888` 和非预乘 `Format_ARGB32`，强制 Qt 场景图每次上传都做像素格式转换（改为 `Format_ARGB32_Premultiplied` 可省转换）。
   - [Theme.qml](../frontend/qt/Theme.qml) 未声明为 `pragma Singleton`，导致含 `ConsoleButton.qml` 在内各处共创建 ~40–60 份重复 `Theme` 对象。
   - [frontend/shared/layers.py](../frontend/shared/layers.py)（`QueryLayers`，仅 `board.py:691-697` 一个调用方）沿用退役 OpenCV 不透明 BGR 路径，导致 `board.py` 分配全图临时 BGR 缓冲、乘 `0.6` 再除以 `0.6` 并硬二值化 `alpha=230`，破坏 `cv2.LINE_AA` 抗锯齿并留黑边。

6. **SQLite 每帧开关连接与 Windows WAL `?mode=ro` 崩溃恢复陷阱**：
   - [history.py](../components/history.py#L128-L191) 在 `match-history` 后台线程对每一帧仅 1 条记录反复打开新连接、执行 `PRAGMA journal_mode=WAL` + `synchronous=FULL` + 6 条 `DDL`、提交后立刻关闭（触发 WAL checkpoint + fsync），且写连接与 [replay.py](../components/replay.py#L110) 读连接均只有 `timeout=0.2`。更严重的是，若进程因原生异常崩溃遗留未 checkpoint 的 `-wal`，Windows 下 `?mode=ro` 只读连接无法创建 `-shm`，导致崩溃对局的历史无法在 Replay 打开（必须先以读写模式打开完成 WAL 恢复）。

7. **双份常驻 FP32 SAM3 显存占用与自动恢复全盘解码**：
   - 默认配置下，`Sam3TrackerVideoModel`（仅首帧注册/手动种子用）和 `Sam3Model`（仅缺帧自动搜索用）同时常驻 GPU（合计约 5.4–6.6 GiB）；交接后卸载或按需加载可将稳态显存削减 ~3–4 GiB。
   - [automatic_recovery.py](../components/tracking/automatic_recovery.py#L59-L67) 每次自动搜索都调私有 `dinov2.type_features._references(folder)` 重解码全部 24–30 张 RGBA PNG 并计算 SHA-256，既未按 SHA-256 做增量缓存校验，在 `targets` 为空时还会先跑完一次全图 SAM3 前向再失败。

---

### 2.2 P2 / P3 功能、解析与交互边界清单

#### A. `application/` 与核心状态（[arch-app], [critic]）
- **[P2]** `MatchSession._accept_recovery_result()`（[session.py](../application/session.py#L364)）`max(self.last_submitted_frame, self.worker.tracker.source_frame)` 缺少 `if consumed is not None:` 保护，在失败路径若 `source_frame is None` 会抛 `TypeError`。
- **[P2]** `MatchSession._accept_result()`（[session.py](../application/session.py#L522-L549)）在 `accepted` 为 `False` 时仍无条件覆盖 `self.prediction_raw_frame` 并执行 `start_tracker`/`mark_changed`/`note`。
- **[P2]** `GameData.accept_geometry()`（[game_data.py](../components/game_data.py#L131-L134)）将旧托盘批次的 `timings` 直接 `{**current, **batch}` 覆写掉更新的传播帧耗时并保留过期 `facing_results`；`update_trays()`（[tray_worker.py](../application/tray_worker.py#L23-L35)）恢复期间仅传 `old.get("trays", {})` 丢失 `attempts` 失败重试基线，且丢弃正常单位计数。
- **[P2]** `Recovery.report_error()`（[application/recovery.py](../application/recovery.py#L124-L125)）和 `AutomaticRecovery.observe()`（[application/automatic_recovery.py](../application/automatic_recovery.py#L43-L44, #L149-L158)）全局调用 `invalidate()` 导致无辜同批次缺失单位的搜索/候选连坐作废或跳去人工。
- **[P2]** `SceneEditing.changed()`（[scene_editing.py](../application/scene_editing.py#L14, #L31-L33, #L83-L90)）修改属性（如 `Engaged`/`Wavering`/`Speed`）或地形时全局调用 `trays.invalidate()` 清空全部 30 单位托盘基线；`update_unit_profile()` 把未校验的额外键写入 `attributes`；`add_terrain()` 漏了 `label.strip()`。
- **[P2]** `Registration.undo_point()`（[registration.py](../application/registration.py#L258, #L266, #L372-L380)）未检查 `pending_clicks`/`updating_points` 导致删点后旧 SAM 异步结果回闪；`point()` 越界报错返回无关 `session.note` 并记录 `source.frame_index` 而非推理快照帧号。
- **[P2]** `@command` 装饰器（[contracts.py](../application/contracts.py#L47)）仅捕获 `(ValueError, OSError)`，`cv2.error` 会直接击穿 Qt 槽函数；`MatchSession.__init__`/`close()`（[session.py](../application/session.py#L37, #L637, #L646)）切换进程全局 `faulthandler` 互相覆盖；`TaskWorker.close()`（[task_worker.py](../application/task_worker.py#L570)）使用 `shutdown(wait=False)` 可能导致 GPU 核还在跑就返回。
- **[P2/P3]** `debug_capture._json_value()` 未处理 `contracts.freeze()` 产生的 `set`/`frozenset`；`GameData.record_calibration()` 在 `confirm_table` 时记录 `reference_folder=None` 且 `R` 重置保留旧值；`MotionRecorder._axis_in_frame()`（[motion_history.py](../components/motion_history.py#L90-L96)）每帧重算 `argmax(edge_lengths)`，接近正方形的长方盘会因微弱斜拍变形产生 90° 假旋转；`Registration.load_archive()` 未重生成 `metadata["rule_scene"]` 留存未规范化的 `Obstacle` 高度和旧快照字段。

#### B. `frontend/qt/` 与 QML（[frontend-qt], [critic]）
- **[P2]** [Main.qml](../frontend/qt/Main.qml#L860-L886) `tableWidth.text` / `tableDepth.text` 绑定到 `ui.state`，后台模型加载进度每刷新一次就把用户输入还原回 `"72"`/`"48"`。
- **[P2]** 快捷键与焦点泄漏：[UnitInfoPanel.qml](../frontend/qt/UnitInfoPanel.qml#L16-L25) `loadFields()` 重建代理时不重置 `focusedInputs`，编辑中切单位会永久锁死快捷键；[Main.qml](../frontend/qt/Main.qml#L23, #L1107-L1113) `textInputActive` 漏统计 `tableWidth`/`tableDepth` 和 B08 输入框（打字时误触发 `Ctrl+Z` / `O`），`S`/`Space` 漏 `!window.terrainMode && s.ready` 保护，全局 `Tab` 抢占控件焦点导航。
- **[P2]** [live.py](../frontend/qt/live.py#L176-L293) 点击无托盘单位查几何失败后，`sync()` 即使后续托盘拟合成功也不自动重试查询；[live.py](../frontend/qt/live.py#L198) 与 [bridge.py](../frontend/qt/bridge.py#L437) 命中索引 `mask[y, x]` 未校验 `mask.shape` 边界；Live 点击忽略 `BoardBadges` 胶囊。
- **[P2]** [workflows.py](../frontend/qt/workflows.py#L1160-L1180) Recovery `Quad` 工具在 `busy`/`committing` 时仍累积隐形顶点；Replay `select()`（`workflows.py:185-187, 1325`）先清 `_scene = None` 造成每次切步/拖滑块必闪一帧黑屏。
- **[P3]** [RecoveryPanel.qml](../frontend/qt/RecoveryPanel.qml#L167-L199) 拖拽幽灵固定 `156×38` 导致抓靠右/靠下区域时偏移光标；[bridge.py](../frontend/qt/bridge.py#L606) `detectCorners` 遇上一轮 `manual` 态未完成探测会静默丢弃点击；[bridge.py](../frontend/qt/bridge.py#L691) `loadArchive` 缺 `path.isLocalFile()` 检查；[Main.qml](../frontend/qt/Main.qml#L35-L80) Debug 模式窗口标题/模式点仍显示绿色 Live 且画面残留青色选中框；[Main.qml](../frontend/qt/Main.qml#L744) 注册页关闭 Terrain 开关后 `TerrainHud` 悬空指向不可见多边形。

#### C. 视觉、追踪、视频 I/O（[vision-track], [critic]）
- **[P2]** `prune_video_session`（[edgetam.py](../components/tracking/edgetam.py#L249-L271)）：`cond_frame_outputs` 从不淘汰会在多次恢复后在 GPU 累积；跨设备 `.to(state_device).clone()` 产生双倍临时分配；若未来 HF 改名 `_obj_idx_to_id` 会静默退化成空操作（不裁剪内存）；`_store_output_pageable`（`:195-202`）缺少 `.setdefault(frame_idx, {})`。
- **[P2]** `edgetam.py:50-176, 515-550`：`_edgetam_layer0_cache` 挂在共享 `model` 上而非 `threading.local()`/`ContextVar`；缓存键 `(id, data_ptr)` 未保活原张量引用；`fast_ma_forward` 硬编码 HF `5.18.0` 拼写错误 `memory_posision_embeddings`、魔法常数 `0.1` 与 4 维假设而无 `inspect.signature` 断言。
- **[P2]** *(经核验从 P1 降级)* `RecoveryCandidate.seed`（[tracking/recovery.py](../components/tracking/recovery.py#L54-L55)）缺 `sam.session = None`，会破坏传入的活跃 `predictor.session`（主程序因 `start_tracker` 已重置而掩盖），且 `predictor.model` 未加载时会把权重加载在临时拷贝 `sam` 上造成泄露，亦缺空 mask 检查。
- **[P2 in-app / P1 standalone]** `CutieTracker`（[cutie.py](../components/tracking/cutie.py#L108-L194)）、`Sam3PointSegmenter`（[point_segmenter.py](../components/sam3/point_segmenter.py#L53-L78)）和 `FacingEstimator`（[dvmnet.py](../components/facing/dvmnet.py#L111-L131)）从未调用 `torch.cuda.set_device(...)`；`bind_cuda_device`（[edgetam.py](../components/tracking/edgetam.py#L40-L47)）和 `DinoV2Extractor`（[extractor.py](../components/dinov2/extractor.py#L37-L87)）在传入无索引 `torch.device("cuda")` 时沿用线程默认卡（在多卡 ROCm 机上可能停在核显 `cuda:0`）。
- **[P2]** [loading.py](../components/sam3/video/loading.py#L22-L38) 进程全局 tqdm hook 并发交错退出会泄漏 `predictor`/`tracker` 闭包；`VideoPredictor` 多处方法在推理前先改状态；`Sam3PointSegmenter` GPU `_embeddings` 无释放方法；`Sam3Segmenter` 缺 `output_loading_info` 校验；`CutieTracker` 漏 `source_frame_index`、空/全覆盖标签错位、`backbone_dir` 忽略 `torch.hub` 缓存、`GlobalHydra` 冲突；`VideoSource` 打开异常前处理 `NaN`/`Inf` 泄漏句柄、首读前 `timestamp_seconds` 为负、接受 `bool` 作秒数；`upscaler.py` 硬编码 `.exe` 且无 `subprocess.run` `timeout`；`image_io.save_image` 非原子写且透传 `cv2.error`。
- **[P3]** `_cache_vision_features_pageable` 在 `max_vision_features_cache_size == 0` 时 `min(keys)` 崩溃；`_last_frame = frame.copy()` 每个追踪器/候选常驻 4.7 MB 并做逐像素 `np.array_equal`；`edgetam.py:506` 用步长切片反转 BGR 而非 SIMD `cv2.cvtColor`；`facing/recovery.py:31` 对只读 `48×48×3` 数组做 `deepcopy`；`tracking/status.py:37` `zip()` 缺 `strict=True`。

#### D. 几何、规则与军表解析（[geom-rules], [critic]）
- **[P2]** *(经核验从 P1 降级为潜伏合同 bug)* [rule_state.py](../components/registration/rule_state.py#L109-L110) 将旧标定的 `corners_source` 经新 `source_to_plane` 投影后传入 [scene.py](../components/game_rules/scene.py#L44-L46) 严苛的 `1e-5`（`0.00057°`）正交校验，微小透视剪切就会抛 `ValueError`（实时 B08 因提交前重拟全部托盘而未触发，但对跨标定回放或未来 What-if 规则查询属显性炸弹）。同样，`rule_state.py:94-97` 对 `unavailable_ids` 未用 `.get()` 属潜伏防御缺陷。
- **[P2]** Homography 条件数/地平线/边界腐蚀：[tray/geometry.py](../components/boundary_detection/tray/geometry.py#L14, #L27-L41) 依赖缩放敏感的 `abs(det) < 1e-15`、单像素腐蚀 `visible` 但 `blur_size=3` 会将黑边抹入 2–3 px、`ceil + 1` 可超 `max_work_size` 1 px、1 px 细 mask 令 `native_scale` 爆炸；[tray/detector.py:195](../components/boundary_detection/tray/detector.py#L195) 缺 `w <= 0` 地平线检查导致单个异常候选整批崩溃。
- **[P2]** 军表解析（[base_sizes.py](../components/registration/base_sizes.py#L49-L78)、[pdf_reader.py](../components/registration/pdf_reader.py#L15-L202)）：特殊规则含 `"Base Contact"` 等词即误标 `invalid_note=True` 阻断查表；`Special Rules: ... Base Size: 50mm Traits: Elf` 单行混排解析失败；`_REVERSE_NOTE` 漏 `"50mm round base"`；仅匹配行首 `^Hero` 漏掉尾置 `"Champion Infantry Hero"`；多行 `Special Rules:` 续行内的 `Traits:` 丢失；第 202 行不支持 profile 守卫漏掉 `Aux|Auxiliary|Warlord|Commander|Hero`。
- **[P2]** [movement.py](../components/game_rules/movement.py#L87-L96, #L136) 浮点 `round(pose[2] % 360, 7)` 产出 `360.0` 造成重复位姿键与 `heading_deg == 360.0`；[scene.py:37](../components/game_rules/scene.py#L37) 未归一化面积校验与 `triangles()` 容差不匹配导致合法狭长地形多边形在 Move 时三角剖分报错；[pipeline.py:25](../components/boundary_detection/pipeline.py#L25) 与 [canny.py:47-57](../components/boundary_detection/canny.py#L47-L57) 遇 2D 灰度图直接崩溃；[units.py:70-101](../components/registration/units.py#L70-L101) 空 `units` 无法往返序列化；[references.py:20-35](../components/registration/references.py#L20-L35) 不校验重复 `object_id` 与 BGR 通道。
- **[P3]** [frame.py:30,56,63](../components/boundary_detection/frame.py#L30-L63) `relative=False` 交点判据与 `float32` 降精度；[visualization.py:63](../components/boundary_detection/visualization.py#L63) 先截断 `±1e9` 再 `clipLine` 改变斜率；[config.py:109-114](../components/boundary_detection/config.py#L109-L114) 原地改写输入参数；[rule_state.py:133](../components/registration/rule_state.py#L133) 未拷贝 `special_rules` 列表。

---

## 三、架构、模块解耦、死代码与工程卫生

### 3.1 拆解 4 个“上帝对象”与双向私有耦合

1. **`application/` 核心拆分**：
   - [session.py](../application/session.py)（620 非空行，`advance()` 113 行）同时承担源时钟、任务调度、恢复/自动恢复结果接收、托盘/正面流水线、历史轮询、JSONL 诊断与 `faulthandler`。应拆出独立诊断日志模块，并将结果接纳下放给各自控制器。
   - [task_worker.py](../application/task_worker.py)（543 非空行，`_run()` 219 行）混杂 Win32 内存探针、profiling、模型推理、重叠裁边与正面计算。宜改为操作分发表 + 独立诊断探针模块。
   - [registration.py](../application/registration.py)（536 非空行）中 `load_archive()` 手工篡改 25+ 个 `session`/`data` 字段（直接导致 1.6 崩溃），应收敛为统一的 `MatchSession.replace_state(...)`。
   - 清理 `MatchApplication.__init__`（`app.py:29-33`）与 `Recovery.__init__`（`recovery.py:23`）的反向猴子补丁；删除前端访问兄弟控制器私有字段的通道（`calibration._context`、`recovery._preview`）和允许前端覆写领域 `session.note` 的 `set_note()`（界面提示留在 `bridge.notice`）。
2. **`frontend/qt/` 拆分与未来 I13 观众窗口准备**：
   - [workflows.py](../frontend/qt/workflows.py)（1,339 行）杂糅 PDF 附录格式化、Replay 全画布绘制、地形 CRUD、单位表单、Recovery 叠加层与 B08/Debug。应拆分为 `replay_view.py`、`recovery_controller.py`、`terrain_controller.py`、`profile_form.py`。
   - 消除 `bridge.py ↔ workflows.py` 之间 20 余处跨文件修改私有 `_` 字段及从 `board.py` 导入 10 个私有 `_` 符号的现象。
   - **I13 观众窗口前置解耦**：目前 15 ms 驱动 `match.tick()` 的 `QTimer` 耦合在单窗口 `MatchBridge` 内，实现第二观众窗口前应将其提升为应用宿主层驱动。

### 3.2 修复剩余跨层边界、重复逻辑与依赖倒置

- **底层反向依赖与 GPU 管理收口**：[sam3/video/predictor.py](../components/sam3/video/predictor.py#L42, #L71, #L114) 反向导入可选追踪器 `components.tracking.edgetam` 的 `bind_cuda_device`/`configure_video_session`/`prune_video_session`；最大显存选卡逻辑在 5 个文件复制 6 遍；`sys.path` 注入在 4 个文件重复。建议抽出共享的 `components/torch_runtime.py` + `components/tracking/hf_session.py`；为 `VideoPredictor`/`EdgeTamTracker`/`CutieTracker` 统一输入校验、输出契约与显式 `clone_detached()`，取代各处手写 `copy(); session=None; reset()`。
- **前端直连 `components/` 收口**：将 [bridge.py:10,61,610](../frontend/qt/bridge.py#L610) 的 `detect_table` 和 `qt-table` 线程池收回 `application.calibration`（同时让 B08 与无头测试可用自动桌角）；消除 `workflows.py:113-142` 与 `MotionRecorder._compatible` 重复的跨标定数学和 `workflows.py:390-403` 内联毫米面积计算。
- **统一坐标与元数据契约**：`Registration.manual_mask()`（`registration.py:329`）和 `Recovery.manual_mask()`（`recovery.py:159`）接收**拉正后像素**，与 `point()`/`add_terrain()`/`set_front()`/`confirm_table()` 接收**原图像素**不一致，违反 [前端解耦重构计划.md](../前端解耦重构计划.md) §3.2 规范；另有初始标定与 B08 两种桌角元数据 schema、4 处各不相同的单位显示名回退顺序、5 处重复的凸四边形/矩阵求逆校验（应并入 [homography/geometry.py](../components/homography/geometry.py)，同时尊重 [TODO.md](../TODO.md#L376) 保持 `game_rules` 纯 Python 独立）、以及多处多边形投影/序号标签绘制重复。
- **解耦 `dinov2.type_features._references` 私有导入 & 统一重叠策略**：为 `type_features.py` 提供带 mtime/SHA-256 增量缓存的公共加载接口（同时供 `automatic_recovery.py` 与 `tools/evaluate_recovery.py` 使用），统一共享重叠比计算/裁剪工具函数。
- **拆分臃肿的 [tray/detector.py](../components/boundary_detection/tray/detector.py)（529 行）** 为提议、评分器（Visibility + Mask + Exact LSD）与搜索/验收三部分，便于向量化；统一视觉输入模块对 2D 灰度/3 通道 BGR 的校验。

### 3.3 死代码、残留、`tools/` 审计与跨切面工程盲区

- **可确认清理的死代码**：`MatchApplication.input_delay()`（`app.py:137-142`）、`GameData.snapshot()`（`game_data.py:139-153`）、`GameData.accept_manual_recovery()`/`fail_manual_recovery()`（`game_data.py:202-235`）、未使用的 `Recovery.preview` property（`recovery.py:25-27`）、`session.py:337-338, 370-371` 永假 `pending_trays` 分支与 `:534-537` 死三目、`registration.py:482` 重复 `import numpy as np`、`OverlayToggles.qml:38` 等值三目。
  *(注：`Registration.load_units()`、`Registration.update_dimensions()`、`Calibration.load_calibration()`、`components/history.py` `read_*` 均属有意保留的公共能力，勿删。)*
- **QML 组件重复**：`DarkField` 在 5 个 QML 文件中被复制或内联重画（`TerrainDialogs.qml`、`WorkflowControls.qml`、`Main.qml`、`UnitInfoPanel.qml`、`TerrainPanel.qml`），应抽为共享 `DarkField.qml` 与 `DarkComboBox.qml`。
- **退役 OpenCV 残留**：`frontend/` 下残留 8 个空目录及旧 `.pyc`（`calibration`, `geometry_tools`, `live`, `recovery`, `registration`, `replay`, `runtime`, `scene_editing`）。
- **`tools/`（20 个脚本）审计**：
  - [tools/setup_facing.py](../tools/setup_facing.py#L1-L16) 是唯一缺少 `sys.path` 根路径注入守卫的脚本，直接运行 `python tools/setup_facing.py` 会 `ModuleNotFoundError`。
  - [tools/setup_tracking.py:116](../tools/setup_tracking.py#L116) 下载 Cutie GitHub zip 时使用 `expected=None`，是供应链上唯一缺少 SHA-256 校验的下载项。
  - [tools/evaluate_recovery.py:21,180](../tools/evaluate_recovery.py#L21) 导入私有 `_references`、调用私有 `segmenter._load_model()`，并重复实现单应矩阵校验与读帧；[tools/tray_detector.py:116,129](../tools/tray_detector.py#L116) `--show` 时算两遍诊断图；[tools/super_resolution.py:24](../tools/super_resolution.py#L24) 帮助文本硬编码了本机 `"RX 7900 XT is 0 on this machine"`；独立工具混用了 HighGUI（`cv2.imshow`）与 Matplotlib。
- **跨切面工程盲区**：
  1. **根 [requirements.txt](../requirements.txt) 缺失 `PySide6`**：2026-11-18 已退役 OpenCV 并把 Qt 设为唯一桌面客户端，但新环境按根清单安装无法启动 `python -m frontend`；同时未标明 `timm==1.0.30` 需由 `setup_tracking.py` 准备。
  2. **[.gitignore](../.gitignore#L5) 与 [AGENTS.md](../AGENTS.md) 冲突**：`.gitignore` 整目录忽略了 `docs/`，而 `AGENTS.md` 规定将新维护文档和实验报告归档在 `docs/`（导致文档无法随 Git 追踪）。
  3. **文档失同步**：[TODO.md](../TODO.md#L312) `Q02` 勾选过时（`queries.py:100-102` 已实现 `geometry_complete is False` 检查）；[frontend/README.md](../frontend/README.md#L153) 存在旧 `config.py` 断链、引用已不存在的 `app.session.data` 且仍称 Terrain 在 Live 工具栏；[frontend/qt/README.md](../frontend/qt/README.md#L5) 仍写 Debug/Recovery 只有 `Masks`/`Trays` 开关；[components/sam3/README.md](../components/sam3/README.md#L57-L59) 仍列出已移至 `frontend/image/` 的旧路径。
  4. **纯手工回归风险**：近期连续出现 `1db6d9c` 帧率回归、`id(state.units.types)` 缓存击穿、`load_archive` 未清元数据等高影响问题，即便不增设测试文件，也建议对核心无状态契约保留可复现的一键冒烟命令。

---

## 四、六大算法线 SOTA / 更优解深度调研（2024–2026）

所有建议均已对照真实文献/开源仓库与本项目约束（固定斜拍/俯拍相机、24–30 个同外观自定义模型、多小时录像、AMD RX 7900 XT Windows ROCm / 12 GB+ 显存、纯离线权重、`transformers==5.18.0`、禁止自动强行分配冲突 ID）完成核验与避坑过滤。

### 4.1 桌面四角检测（目前：OpenCV LSD + 启发式拼边）

- **现状痛点**：[table.py](../components/boundary_detection/table.py) 在实拍 1920×1080 顶边贴近 `y=0` 裁切时易误锁桌内地形/垫边线（`y≈303`）或只抓到 3 条边退回手动；下采样 0.5× 时丢失右边。
- **推荐升级**：
  - **短期（纯 CPU 即可落地）**：**ELSED**（`iago-suarez/ELSED`, Pattern Recognition 2022, `pyelsed` C++ 梯度链跟踪，跨小断裂比 LSD/EDLines 更稳更快）+ **双灭点（2-VP）RANSAC 四边形联合评分**，融入已知 **`72:48` (`1.5:1`) 拉正纵横比先验**，并对贴近画幅边缘的缺边返回 `estimated=True` 钳位估算，替代逐边贪心最长线。
  - **中期**：**DeepLSD**（`cvg/DeepLSD`, CVPR 2023，纯 PyTorch ROCm 安全，仅首帧跑一次约 50–150 ms / <1 GB 显存后即刻卸载），泛化性显著优于容易过拟合室内建筑线框的 **HAWP**。
  - **长期（配合 4.4 升级 3D 托盘拟合）**：**GeoCalib**（`cvg/GeoCalib`, ECCV 2024），从首帧直接估计焦距、径向畸变与重力方向，用于求解完整相机位姿 `(K, R, t)`。
- **避坑提醒**：**不要用 SAM3 文本搜 `"gaming table"` 做启动桌角检测**——`detect_table()` 需要在程序启动时秒级响应，而此时 SAM3 仍在后台加载，且在关闭自动恢复或选用 `--tracker sam3|cutie` 时 `Sam3Segmenter` 根本未加载。

### 4.2 30 目标长视频遮挡追踪（目前：SAM3 首帧 + EdgeTAM HF 5.18.0）

- **现状痛点**：手部/卷尺遮挡 3–6 秒时，EdgeTAM FIFO 盲写将 6 个固定 `non_cond_frame_outputs` 记忆槽（由 `maskmem_tpos_enc (7,1,1,64)` 写死）全部污染成手掌特征；30 目标逐个串行耗时 ~420 ms/帧；同款单位靠拢易出现 ID 吞并/串号。
- **推荐升级**：
  - **短期零显存方案（Phase 1，直接改 [edgetam.py](../components/tracking/edgetam.py)）**：借鉴 **DAM4SAM**（CVPR 2025 / IJCV 2026, `jovanavidenovic/DAM4SAM`, 多目标 `alanlukezic/d4sm`）的**内省式遮挡门控**——在已经 hook 好的 `_store_output_pageable` 中检查 EdgeTAM 本身已经算出的 `object_score_logits` 以及 mask 面积相对已知物理底座预期面积的倍率（如 `[0.6×, 1.5×]`）：一旦检测到手部吞并或严重遮挡，**跳过把该帧写入非条件记忆槽**，以零显存、零耗时保护历史记忆。
  - **中期突破 `O(N)` 瓶颈与长程漂移**：
    1. **Meta SAM 3.1 Object Multiplexing**（`facebook/sam3.1`，2026-03-27 发布于 `facebookresearch/sam3`，`build_sam3_multiplex_video_predictor`）：每个共享显存多路复用桶打包 **16 个目标** → 24–30 单位从 **30 次串行降为 2 次联合推理**，并能统一首帧注册、视频追踪与自动恢复（省下双 SAM3 显存）。
    2. **SAM2Long**（ICCV 2025 无训练约束记忆树抗多小时漂移）与 **Competitive Memory Readout**（ECCV 2026 LSVOS 亚军，把同类竞品单位作为竞争 token 显式送入读出防止吞并）。
    3. **重测现有 Cutie 后端**（`hkchengrex/Cutie`, CVPR 2024，已接 `--tracker cutie`）：天生单次联合推理全部对象，建议补测 640–720p 分辨率 GPU 表现（480p 对小底座过糊）。
- **避坑提醒**：
  - HF `transformers==5.18.0` 的 `EdgeTamVideoModel.forward()` 只返回单一选中 mask，完整版 **SAMURAI**（`yangchris11/samurai`，3 候选 multimask 选优）与完整版 **DAM4SAM**（RAM/DRM 双池分流）都需要深层篡改私有方法，风险高于 Phase 1 的直接跳过写入策略。
  - **SAM 3.1** 目前位于原生 `facebookresearch/sam3`（不在 pinned `transformers==5.18.0` 中）且受限于门控权重与 FP16/BF16 + `torch.compile`。RX 7900 XT 在 Windows ROCm PyTorch 2.13 下曾出现 FP16 `Conv2d` MIOpen 慢 2–3 倍及 BF16 漂移问题，因此 Meta 官方的 `~4 GB` 与 `7×` 加速必须在实机上先行基准测试，切勿直接假设成立。
  - **不推荐**：**CoTracker3**（显存随像素体积膨胀，仅适合做辅助点可见性探针）、**SeC**（ICLR 2026，依赖 LVLM 概念推理过慢且帮不上同兵种区分）、**XMem++**（已被 Cutie 对象 Transformer 取代）、**EfficientTAM**（与 EdgeTAM 同级，投入产出不如内存门控和 SAM 3.1）。

### 4.3 缺失单位自动恢复 / Re-ID（目前：SAM3 `"miniature"` + DINOv2-small 全局 `[CLS]`）

- **现状痛点**：全局 `[CLS]` 余弦在实例旋转 90° 后直接崩塌（实测 A1 从 `0.9575 -> 0.7091 -> 0.6976`，分差跌至 `0.0023`）；全图文本搜索耗时 ~1.025 秒且产出 50–66 个噪声候选，缺少物理尺寸过滤。
- **推荐升级**：
  - **短期高 ROI（无须重模型，同时修复三大病灶）**：
    1. **旋转规范化 + 前景掩码稠密 Patch 匹配**（*FoundPose* ECCV 2024 / *SAM-6D* CVPR 2024 / *Patchify* WACV 2026 范式）：按候选 mask 主轴旋转对齐至规范朝向（`0°/180°`，近方形加 `90°/270°`），提取冻结 ViT 的中间-末层**前景区域稠密 patch tokens**，做**对称互近邻（MNN）或 Sinkhorn / EMD 匹配**（50 候选耗时 <5 ms）。模型可选 **`facebook/dinov2-with-registers-base`**（Apache-2.0，无门控）或 **`facebook/dinov3-vits16-pretrain-lvd1689m`**（Meta 2025-08 发布，HF 原生支持，RoPE + Register + Gram 锚定抑制背景伪影，注意 DINOv3 为受限自定义协议且要求 `"Built with DINOv3"` 署名）。
    2. **先加 1.8 核实出的物理底座尺寸门控 + SAM3 候选 Mask-IoU NMS**：利用各缺失单位已知的 `width_mm × depth_mm` 在拉正平面按面积/纵横比滤除明显错尺（50×50 英雄 vs 200×80 大方阵，留出视差裕度 `[0.65×, 1.8×]`），再用 IoU NMS 合并重复碎片避免把第一名的 `top_two_margin` 打死。
  - **中期**：
    - **ALIKED + LightGlue**（`cvg/LightGlue`, ICCV 2023 + `Shiaoming/ALIKED`，纯 PyTorch **ROCm 友好**、<300 MB 显存、<15 ms/对）对 DINO Top-3 候选做几何关键点 RANSAC 重排——既能靠微弱涂装/地台细节区分同兵种双胞胎，又能直接解出 2D 旋转角。
    - **SigLIP 2 NaFlex**（2025）：原生纵横比编码，避免 `155×50 mm` 长条托盘在正方形缩放中浪费 ~68% tokens。
- **避坑提醒**：
  - **切勿用“当前帧 vs 第 0 帧差分”生成候选**：比赛第 0 帧时单位已经在桌面部署完毕，**如果单位原地被手遮挡超过 10 秒后露出来，它和第 0 帧的差分为零**，背景差分会彻底漏检！光照变化、骰子和量尺也会把差分图搞花。
  - **禁止强制匈牙利匹配（`scipy.optimize.linear_sum_assignment`）**：直接违背 [待澄清列表.md](../待澄清列表.md) D14 与 [TODO.md](../TODO.md) T07“同外观多目标冲突必须全部交人工判断、严禁强行配对或串号”的硬性规则。
  - **RoMa v2**（注意正确仓库为 **`Parskatt/RoMaV2`**，非 `ParsnipFitting`）依赖 CUDA kernel 且 **MASt3R** 显存重，均不适合放入 12 GB 实时回路。

### 4.4 已知尺寸托盘拟合与斜拍视差（目前：自适应门控 + 方向 Chamfer Beam + 27 点网格）

- **现状痛点**：27 点离散网格带来 `2°` 量化噪声；更致命的是**物理几何失真**——在斜拍机位下，有一定高度 `H` 的 3D 兵人像素经 2D 地平面（`Z=0`）单应矩阵拉正后，会沿背离相机方向产生系统性径向外溢（`Δ ≈ H · tan(θ_view)`，如 40mm 模型在 35° 斜视下外溢 ~28 mm；已实测 A11.1 `150×100 mm` 被撑成 `157×104 mm`）。对称 `mask_fill > 0.85` 反而把托盘框往模型头顶外溢方向拉偏！
- **推荐升级**：
  - **短期（零新依赖，纯 CPU 立即可做）**：
    1. 先修完 2.1 中的 `describe_mask` 与 `mask` 分支无效 LSD + 向量化 `_Scorer`。
    2. **连续优化替代 27 点离散网格**：用纯 NumPy 手写 3–5 步阻尼高斯-牛顿 / Levenberg-Marquardt（不引入额外 `scipy` 依赖），在双线性插值 Chamfer 场 + mask 有向距离场（`cv2.distanceTransform`）上连续微调 `(cx, cy, θ)`，消除 2° 角度抖动。
  - **中期（解决斜拍视差根源）**：
    1. **相机射线非对称加权**：用已有的 4 个桌角直接算出地平面灭线 `l_∞ = v1 × v2` 即可在任意 `(x, y)` 处得到“朝向相机（未被遮挡的真实 `Z=0` 底盘前缘）”与“背向相机（被兵人躯干遮挡外溢）”方向。把近相机边权重设为远边的 2–3 倍，并用不惩罚背向相机方向外溢的覆盖指标。*(审批提示：改变 `mask_fill > 0.85` 门槛或定义需先征得你确认，见 2026-11-18 既定门槛。)*
    2. **单目 `(K, R, t)` + IPPE + 3D 长方体棱柱轮廓拟合**：从正交灭点解析焦距（顶边裁切时结合 GeoCalib），用 `cv2.solvePnP(..., cv2.SOLVEPNP_IPPE)`（IJCV 2014）求解桌子平面位姿，将单位建模为 `[W_mm, D_mm, H_phys_mm]` 的 3D 棱柱投回原图：用可见 `Z=0` 底边对 Chamfer 打分，用 3D 棱柱 6 顶点投影凸包去对齐整个微缩模型 mask，从物理模型上根除偏移。
- **避坑提醒**：当前 `fit_tray` 超过 72% 耗时在 Python/NumPy 而非释放 GIL 的 OpenCV C++，在向量化完成前直接开 `ThreadPoolExecutor` 可能加剧 GIL 争抢并拖卡 Qt 界面。

### 4.5 有向正面朝向估计（当前 `FACING_TRACKING_ENABLED = False`）

- **现状痛点**：DVMNet（287M、~1.2 GB 显存、背景敏感、180° 偏差大、无顶层开源许可证且上游为 CC BY-NC-SA 4.0）已按决定停用。
- **推荐升级（供将来重新开启正面功能时参考，须先获你确认）**：
  - **零额外显存方案（最稳）**：在 D32 架构下，托盘主轴已由 4.4 精确算出，正面判定严格简化为 **2 选 1（矩形 `0°/180°`）或 4 选 1（方形）分类**。只需将当前源图+mask 按候选正面边规范化旋转裁剪，**直接复用 4.3 已经在显存中的 DINOv2-reg / DINOv3 做单批次（~8–15 ms）空间对齐稠密 patch 匹配**（前排盾牌/武器 vs 后排披风/背影的空间分布明显区别于 48×48 裸 RGB），再融合 **KoW4 移动方向先验**（单次移动 > `0.5 × Speed` 沿法向大概率是前进 `Advance`/`Double`）。
  - **正统专用模型替代**：**Orient Anything V2**（`SpatialVision/Orient-Anything-V2`, NeurIPS 2025 Spotlight, **CC-BY-4.0** 清洁授权），内置支持 2 折矩形/4 折方形周期对称分布头与多帧相对旋转预测（~5.05 GB 权重：20 GB RX 7900 XT 可常驻，12 GB 显卡需按需卸载）。**FoundationPose** / **FreeZe** 因依赖 3D CAD 模型或扫描网面而不适用自涂微缩兵人。

### 4.6 动作切步与规则几何（`motion_history.py` & `game_rules/`）

- **现状痛点**：`motion_history.py` 用硬阈值 `10 mm / 10° + 5 s` 易受单帧托盘拟合跳变干扰，且停稳 5 秒窗口内未挑选无手遮挡的干净帧作回放截图（[项目思路.md:566](../项目思路.md#L566)）；`game_rules/` 用 9×9 采样射线算 LOS 常因无法证明被完全遮挡而退回 `uncertain`，Move 纯 Python 无粗筛。
- **推荐升级**：
  - **动作切步与选帧（~80 行 NumPy，保持 SQLite v2 结构不变）**：对 `(x, y, cos kθ, sin kθ)`（矩形 `k=2`、方形 `k=4` 规避周期跳变）做带新息门控的 SE(2) 卡尔曼滤波抑制单帧野值，配施密特双阈值迟滞（进入 `10 mm/10°`、停稳 `4 mm/4°`）+ 在线 CUSUM / FOCuS 缓慢拖拽漂移检测；停稳后用窗口中位数定最终位姿，并在 5 秒窗内按 **最高 `edge_support` + 最小相邻帧像素变化** 自动挑选无手遮挡的干净截图存入 Replay。
  - **规则几何（优先纯 Python，尊重 [TODO.md:376](../TODO.md#L376) 零第三方依赖边界）**：
    1. 短期在 `movement.py` 与 `queries.py` 加入 **AABB 包围盒粗筛** 与 **平移前缀树剪枝**（已阻断的前缀不再向下展开旋转）。
    2. 中期实现**精确 2D 临界公切线 / 弱可见多边形 LOS**——全场仅 ~30 单位 + ~10 地形（总共约 160–250 顶点），纯 Python 不到 `<2 ms` 即可给出数学精确的 `clear` vs `blocked` 结论，彻底消灭采样导致的假 `uncertain`（实现时需注意保留非 `blocking` 地形的端点内外看/看入规则差异）。
    3. 若未来决定放开 `game_rules` 零依赖限制，再引入 **Shapely 2.x**（GEOS `STRtree` + 批量多边形，加速 10–50 倍以支撑 `Charge`/`Individual`/`Fly`）与离线 **PELT (`ruptures`)** 战报分段。

---

## 五、核验排除与需求约束对照表

以下条目在交叉核验中明确**不列为 Bug 或不得静默违背既有决定**，重构时请保持对齐：

| 条目 | 核验结论 | 依据 |
| --- | --- | --- |
| `live.py:259` 读取 `rows[catalog.get("list_id", "A")]` 报 `KeyError` | **误报 / 已有保护** | `UnitRoster.__init__`（`components/registration/units.py:39-42`）入口已拒绝 `(None, "A", "B")` 之外的 `list_id` 并剥离 `None` |
| `EdgeTamTracker.update_mask` 的 `finally:` 在报错时仍推进 `index`/`source_frame` | **有意设计（保留）** | `待澄清列表.md` CL18 明确要求消费该帧槽位避免缓存键错位；需修的仅是 `cond_frame_outputs` 与脏输入回滚 |
| 自动恢复对正常单位采取 `1 px` 零重叠排除（`automatic_recovery.py:16`） | **既有待审批策略** | `项目思路.md:24, 436` 明确记录暂保留零重叠待用户审批；建议审批后统一改用 `0.20` 裁边规则 |
| 自动恢复不使用匈牙利最优分配 | **需求红线（保持）** | `待澄清列表.md` D14 / `TODO.md` T07 禁止多实例冲突时强制配对或串号，须交人工逐一确认 |
| 托盘拟合 `mask_fill > 0.85` 与非对称覆盖评分改动 | **需用户拍板** | `待澄清列表.md:123` / `TODO.md` 2026-11-18 既定门槛；放宽 0.85 或改分母须确认 |
| 正面朝向追踪（`FACING_TRACKING_ENABLED = False`） | **已决定默认停用** | 2026-11-14 用户决定停用，仅记录休眠 bug 供参考，重启须另行确认 |
| `components/game_rules/` 保持纯 Python 零第三方依赖 | **既有边界** | `TODO.md:376` 与 `game_rules/README.md`；先用纯 Python AABB + 精确公切线 LOS |
| `TODO.md:312` `Q02` 未勾选条目 | **文档本身过时** | `components/game_rules/queries.py:100-102` 已实际实现 `geometry_complete is False` 检查 |

---

## 六、分阶段实施路线图

### 第一批：立即止血（预计 1–2 天，高收益低风险）

- [ ] 恢复 `DEFAULT_INFERENCE_FPS = 1.0`（[config.py](../application/config.py#L8)），同步修正 [arguments.py](../frontend/arguments.py#L18) 提示文本。
- [ ] 在 [app.py](../application/app.py) 实现子快照分代缓存（只读 ndarray + 补齐 `_snapshot_key` 漏字段 + `finish_registration()` 触发 `mark_changed()`），彻底清除 `board.py`/`bridge.py`/`workflows.py` 的 `id(...)` 缓存键风暴、Replay 60 Hz 画面拷贝及隐藏烘焙；`BoardRenderer` 增加 `_sync_seq` 并在 `overlay_key` 补齐 `state.mode`。
- [ ] 修复 EdgeTAM 会话自引用环（`weakref`/显式解绑）、所有取消候选调 `release()` 及 B08 旧/废弃后端调 `.reset()`。
- [ ] 修复 `Registration.load_archive()` 清空全部预测元数据并在失败时阻止返回 accepted（彻底根除 Qt `prediction["object_ids"]` 崩溃）。
- [ ] 修复 `TrayWorker.take_ready()` 吞异常清空全队托盘的致命故障；将 `HistoryStore` 改为后台单持久连接（调高锁超时并缓解 Windows WAL 崩溃后只读打不开问题）。
- [ ] 修复 `game_rules` 三处 P1 数学漏洞：LOS 沿裁剪后前弧采样并拦截穿己身射线、`blocking` 地形禁止边界跳过、`front_arc_clip` `t` 钳位 `[0, 1]`。

### 第二批：流程稳健性与 CPU 性能大提速（预计 2–4 天）

- [ ] 彻底修通 B08 重标定四联 Bug：失败解锁 `_calibration_pending`、保留空掩码绑定单位的 `object_ids` 槽位且过滤 `inactive`/`unavailable`、不再覆写 `registration_start_frame`/`initial_frame`、补片尾与同步校验。
- [ ] 修通 Recovery 全状态机：EOF `committing=True` 解锁、`model_failed` 阻断/取消、先过 `update_mask` 校验再置消费标志、红色 `Correct` 仅清理单 ID 不误杀他人、审核切目标调用 `clear_candidate()`、同步 `_geometry_visible`、修补 `seed_mask` 同帧点修与 `correct_points`/`update_mask` 条件帧状态与异常清理、解除 `session` ↔ `task_worker` 跨线程 `facing_*` 数据竞争。
- [ ] 修复自动恢复：为 SAM3 `"miniature"` 输出加 Mask-IoU NMS、阻止极低分假候选卡死高分候选、重加载清空 `load_error`、增量按 SHA-256 缓存参考图库。（可同步确认是否对自动恢复开放 `0.20` 裁边规则。）
- [ ] 吃掉纯 CPU 性能红利：`describe_mask` ROI 化 + 字节直存、`fit_tray` 删 `mask` 分支无效 LSD + 向量化 `_Scorer` + 修复 `[2%, 5%]` 搜索盲区 / 角点去重 / 小托盘 `<=` 膨胀 / 对齐 `0.80` vs `0.85` 规则、`game_rules` 加 AABB 粗筛 + 前缀剪枝、`merge.py` 优化复杂度。
- [ ] 修复 Qt 交互与解析细节：表尺寸绑定被冲、焦点计数泄漏与快捷键守卫、无托盘几何自动重试、越界检查、Replay 黑屏闪烁、`UnitRoster.with_list()` 与 `base_sizes.py`/`pdf_reader.py` 解析边界、补上 `@command` 对 `cv2.error` 的捕获。

### 第三批：架构拆瘦与核心算法 SOTA 升级（预计 1–2 周）

- [ ] **架构与工程整理**：抽出 `components/torch_runtime.py` 与 `hf_session.py` 消除 `sam3 -> edgetam` 反向依赖及 6 处重复选卡/绑定代码；统一 Tracker 协议与 `clone_detached()`；拆瘦 `MatchSession`、`TaskWorker`、`Registration` 与 `workflows.py`，消除私有互改，统一 `manual_mask()` 为原图像素并收回 `detect_table`；完善 `requirements.txt`（补 `PySide6`）、清理 8 个空目录与死代码、修复 `tools/` 缺失的路径守卫与校验和、同步过时文档并处理 `.gitignore` 与 `docs/` 冲突。
- [ ] **算法升级落地顺序**：
  1. EdgeTAM `store_output` **遮挡跳过记忆写入门控**（零显存解决手部污染）。
  2. **旋转规范化 + DINOv2-reg/DINOv3 稠密 patch 匹配 + 物理底座尺寸过滤**（解决 A1 旋转崩塌，并为未来零显存正面判定铺路；视需求补充 `ALIKED + LightGlue` 精排）。
  3. **精确 2D 临界公切线 LOS** + **SE(2) 滤波/施密特迟滞切步 & 干净帧 Replay 挑选**。
  4. **连续高斯-牛顿托盘精调** → 经用户确认后推进 **ELSED + 2-VP 桌角检测** 与 **非对称视差 / IPPE 3D 棱柱托盘拟合**。
  5. 在 RX 7900 XT Windows ROCm 上独立基准对照 **Cutie 640–720p** 与 **Meta SAM 3.1 Object Multiplexing**，决定下一代统一追踪骨干。
