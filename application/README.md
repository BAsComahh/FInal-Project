# 无窗口比赛应用

`MatchApplication` 拥有一份 GameData、一个源时钟与一个串行模型 worker。构造时即加载模型；`tick(now=None)` 接纳结果、推进源并调度，不等待模型 Future。`snapshot()` 返回冻结元数据和共享只读图像／mask，当前源帧与已接纳观测各有 FrameRef。反复读取同一 revision 不复制图像、不写历史。

默认 `seconds=None` 播放到视频结尾，`inference_fps=None` 表示 worker 空闲时处理最新未消费帧，不施加额外频率上限；显式正数可限定时长或调度频率。stride 参数已删除。快照的 `inference_fps` 与注册记录的 `inference_fps_limit` 无上限时对应 None／JSON null，串行、帧对齐和代次保护保持。

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

- 注册：`point(object_id, source_point, FrameRef, positive=True)`、`undo_point()`、`bind(object_id, type_id)`、`unbind(object_id)`、目录导入／尺寸更新、`finish_registration(overlay=None)`。未提供 overlay 时导出源观测的 mask 着色图；S 锁定后只允许 R 开启新注册。
- 启动：`start(overlay=None)` 在一次保存后初始化所选 tracker，再启动源；`reset()` 与 `close()` 统一作废旧工作及处理历史，关闭幂等。
- 标定：`confirm_table(corners, boundary, board_size_in=...)`；B08 使用 `begin_recalibration()`／`apply_recalibration(...)`／`cancel_recalibration()`，只读 status 不含初始化后端或草稿 GameData。
- 恢复：`open(unit_id=None)`、`point(source_point, positive, FrameRef)`、`clear_candidate()`／`cancel()`、`bind(unit_id, candidate_generation)`、`reject()`／`report_error(unit_id)`。`snapshot().recovery` 提供候选、阶段及代次；最终 mask 由应用同帧推进并验证，调用方不能提交任意旧 mask。
- 查询：`query(mode, unit_ids, observation_ref, view_revision)` 合并尚未启动的旧请求。result／result_request 是只读结果；`result_current(snapshot)` 检查叠加是否仍有效。源帧前进本身不伪造新观测。
- 资料：`update_unit_profile(unit_id, values, FrameRef)`、`set_front(unit_id, source_point, observation_ref)`、`add_terrain(source_vertices, values, FrameRef)`；表单与屏幕草稿留 frontend。
- 回放：`open()`／`refresh()`／`navigate(delta)`／`clear()`，通过只读 scene 与 steps 展示。它不暂停源，也不进入模型队列。

`present(source_ref)` 只固定实际显示的交互采样帧，不负责驱动追踪。点输入可使用该帧；过期代次／标定或已无法取得的帧明确拒绝。模型若已越过被点击帧，也不能回退记忆或把点击改解释到最新帧。采样帧／在途请求之外不缓存整段视频。

UI 只导入此层，application 只调用 components；没有 GUI 框架、事件总线、网络服务器或第二份比赛状态。配置在 config.py；现有 CLI 参数和保存格式保持。I14 的剩余验收见根目录重构计划。
