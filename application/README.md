# 无窗口比赛应用

当前`FACING_TRACKING_ENABLED=False`，保留实现但不构建／加载DVMNet，不更新实时有向正面。注册F资料仍可保存，开始播放后清除活动正面。`rules.track_facing`在快照中说明该状态，涉及正面的规则保持未知输入约束。

前端 `Trays` 开关仅控制托盘轮廓的显示可见性（与 `Masks` 相同）；后台托盘拟合与连续几何查询始终保持运行，不再暂停或使用一次性定帧快照。

`MatchApplication` 拥有一份 GameData、一个源时钟与一个串行模型 worker。构造时即加载模型；`tick(now=None)` 接纳结果、推进源并调度，不等待模型 Future。`snapshot()` 返回冻结元数据和共享只读图像／mask，当前源帧与已接纳观测各有 FrameRef。反复读取同一 revision 不复制图像、不写历史。

正常传播的 CPU 托盘拟合由 `tray_worker.py` 独立处理，最多一在算帧批次＋一最新待算批次。所有模型操作（包括几何完成后的 DVMNet）仍走原串行队列。`current.prediction_metadata` 是 mask 时间；`current.prediction.geometry_metadata` 和 `current.geometry_frame` 是托盘／正面的原始观测时间及图像。查询与历史使用几何时间，`geometry_revision` 独立于 mask 的显示 revision。迟到结果不倒退 mask，也不跨真实缺失、恢复、标定、尺寸、身份和重置边界接纳。注册与重标定／恢复提交仍作为完整事务处理。

注册与Live共用`tray_worker.update_trays`，请求的`tray_ids`指定更新范围。注册正负点和撤点只使目标几何失效，`registration.bind()`确认当前mask后才排该ID的拟合；其他单位的结果保留。绑定后再次编辑需重新赋予类型确认。注册拟合携带逐对象`tray_versions`，接纳时按当前版本过滤，继续改点／改绑不会复活旧结果。

默认 `seconds=None` 播放到视频结尾，`inference_fps=config.DEFAULT_INFERENCE_FPS`（`1.0` Hz，即 `1.0` 秒最小传播间隔，兼顾单帧快速完成与 6 帧非条件空间记忆的时间跨度）；显式传入 `None` 表示 worker 空闲时立即处理最新未消费帧，显式正数可调整上限。stride 参数已删除。快照的 `inference_fps` 与注册记录的 `inference_fps_limit` 无上限时对应 None／JSON null，串行、帧对齐和代次保护保持。

```python
from application.app import MatchApplication

app = MatchApplication(video, device=device, seconds=30, output_dir=new_output)
try:
    app.tick()
    state = app.snapshot()
    # 持续 tick，读取 startup_ready／load_progress；不访问内部 Future。
finally:
    app.close()
```

业务入口为 `registration`、`calibration`、`recovery`、`geometry`、`scene_editing` 和 `replay`。公共命令返回 `CommandReceipt(status, reason, request_id, value)`；预期输入／文件错误是 rejected，内部合同违例仍抛出。pending 只说明已排队，后台成功状态由后续快照／对应流程结果提供。文件目录等同步结果在 value 中；历史、模型和可写业务对象不返回。

`registration.load_archive(path)`（构造参数 `registration_archive=path`）载入已完成注册目录或其 `prompts.json`。`registration_archive.py` 独立读取并核对当前视频同帧像素、mask、ID绑定与标定，验证／发布成功后才更换会话；复用原ID和同帧tray。载入的新注册锁定，`startup_ready` 后调用 `start()`，串行后端通过公开 `initialize(..., masks, source_frame=...)` 重建记忆。源起点采用存档帧，显式seconds由该帧计算。新建reference和history，原文件不变；不续播旧历史／内部模型会话，换档先reset。

- 注册：`point(object_id, source_point, FrameRef, positive=True)`、`undo_point()`、`bind(object_id, type_id)`、`unbind(object_id)`、目录导入／尺寸更新、`finish_registration(overlay=None)`。未提供 overlay 时导出源观测的 mask 着色图；S 锁定后只允许 R 开启新注册。
- 启动：`start(overlay=None)` 在一次保存后初始化所选 tracker，再启动源；`reset()` 与 `close()` 统一作废旧工作及处理历史，关闭幂等。
- 标定：`confirm_table(corners, boundary, board_size_in=...)`；B08 使用 `begin_recalibration()`／`apply_recalibration(...)`／`cancel_recalibration()`，只读 status 不含初始化后端或草稿 GameData。
- 恢复：`open(unit_id=None)`、`point(source_point, positive, FrameRef)`、`manual_mask(corners, FrameRef)`、`clear_candidate()`／`cancel()`、`bind(unit_id, candidate_generation)`、`reject()`／`report_error(unit_id)`。`snapshot().recovery` 提供候选、阶段及代次；最终 mask 由应用同帧推进并验证（低于 `RECOVERY_OVERLAP_REJECT_RATIO` 的轻微贴边接触自动裁去，实质重叠则拒绝并保留候选草稿），调用方不能提交任意旧 mask。
- 查询：`query(mode, unit_ids, observation_ref, view_revision)` 合并尚未启动的旧请求。result／result_request 是只读结果；`result_current(snapshot)` 检查叠加是否仍有效。源帧前进本身不伪造新观测。
- 资料：`update_unit_profile(unit_id, values, FrameRef)`、`set_front(unit_id, source_point, observation_ref)`、`add_terrain(source_vertices, values, FrameRef)`、`update_terrain(terrain_id, values, FrameRef)`、`delete_terrain(terrain_id, FrameRef)` 与 `undo_terrain()`（地形编辑与初始正面仅在注册锁定前允许）；表单与屏幕草稿留 frontend。
- 回放：`open()`／`refresh()`／`select(index)`／`navigate(delta)`／`clear()`，通过只读 scene 与 steps 展示。它不暂停源，也不进入模型队列。

`present(source_ref)` 只固定实际显示的交互采样帧，不负责驱动追踪。点输入可使用该帧；过期代次／标定或已无法取得的帧明确拒绝。模型若已越过被点击帧，也不能回退记忆或把点击改解释到最新帧。采样帧／在途请求之外不缓存整段视频。`start_tracker` 交接独立追踪后端后立即释放首帧注册 SAM3 会话；运行期在输出目录启用 `crash_traceback.log`（`faulthandler`），并在当前会话目录持久记录 `runtime_diagnostics.jsonl`（阶段事件、每 30 步传播及首次异常的进程 RAM、物理 GPU 名称与显存、会话帧／锁页内存统计及完整 traceback）。

UI 只导入此层，application 只调用 components；没有 GUI 框架、事件总线、网络服务器或第二份比赛状态。配置在 config.py；现有 CLI 参数和保存格式保持。I14 的剩余验收见根目录重构计划。
