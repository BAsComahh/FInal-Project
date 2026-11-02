# SAM3 视频模型

`VideoPredictor(profile=True)` 可同步 GPU 分段计时，返回 `timings_seconds` 中的预处理、模型调用和 mask 后处理／回传时间；正常模式不额外同步，此时 `model_call` 可能只包含异步提交，不能单独解释为 GPU 推理时延。对象存在原始 `object_score_logits` 按 `object_ids` 返回；不是身份正确概率。工作线程另外记录完整 SAM 操作、托盘和总耗时，不再把托盘耗时全部标作 SAM。

`initialize(frame, object_ids, masks, source_frame=...)` 使用本机 Transformers 5.18.0 官方 `init_video_session` 和 `add_inputs_to_inference_session(input_masks=...)`，为重新标定后的图像建立新会话。应用在独立的 predictor 副本上调用，复用模型／processor，成功后替换旧会话；不变换旧时序记忆，也不重新开放播放后的点击修改。已使用实际 processor/session 和替身模型检查 API，尚未以真实 SAM3 权重完成重新标定视频回归。官方依据：[Meta 跟踪器](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_tracking_predictor.py)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)。

前端 `--profile` 把各任务及错误记录到新的 `outputs/tracking_comparison/sam_.../`，目录在终端显示；不保存提示点、图像或中间 reference。原 session、FP32 和 CPU state 策略保持当前基准配置。RX 7900 XT 真实权重及实际视频短测已验证接入与日志输出，尚未进行公平性能或身份准确率评测，证据范围见 [项目设计记录](../../../项目思路.md)。

本目录只负责模型和官方视频会话接口：`predictor.py` 封装 `Sam3TrackerVideoModel`／`Sam3TrackerVideoProcessor`，`loading.py` 观察权重加载进度。后台任务调度位于 `frontend/runtime/task_worker.py`，单位和 reference 数据位于 [registration](../../registration/README.md)。

完整视频示范从 [frontend](../../../frontend/README.md) 启动：

```powershell
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --units inputs/units.example.json --seconds 30
```

先确认原图桌角，再 Homography 拉正，在拉正帧中注册并传播。权重启动即加载；首帧特征等变换确定后准备。界面和导出规则见前端及 registration 文档。

```python
from components.sam3.video import VideoPredictor
from components.video_io import VideoSource
from components.registration import extract_references

source = VideoSource("inputs/example.mp4")
try:
    frame = source.read_at(0)
    predictor = VideoPredictor()
    predictor.load()
    predictor.prepare_initial_frame(frame, source_frame=source.frame_index)
    prediction = predictor.click(frame, [100, 200], object_id=1, source_frame=source.frame_index)
    references = extract_references(frame, prediction, source=source.metadata())
finally:
    source.close()
```

这个直接组件示例以原视频坐标工作；前端会先变换输入帧，并标记拉正坐标空间。每份 reference 必须使用与 prediction 配套的同帧图像。

模型只读取本地缓存，默认使用显存最大的 GPU、FP32，会话状态和视频存于 CPU。`load()` 重复调用不重新加载权重。`prepare_initial_frame` 使用真实首帧的 `add_new_frame`、`get_image_features` 和 `cache.cache_vision_features`，不添加虚拟对象；GPU 同步完成才报告准备就绪。缓存键按已核对的 Transformers `5.18.0` 后端源码对接。这是项目集成，首个真实点仍需提示解码和记忆编码，提速幅度尚未测量。

首次播放前的点编辑使用 `clear_old_inputs=True` 替换首帧提示；删除对象时用 `reset_tracking_data()` 保留图像缓存，再按点数分组提交剩余对象，避免补齐提示影响多 mask 选择。播放后锁定点及 type 编辑，暂停不回滚时间状态；后续矫正由未来算法负责。

加载进度通过官方源码中的 `logging.set_tqdm_hook` 观察已加载项数，百分比不是下载字节或启动总耗时。钩子退出时恢复，无总量的准备阶段由界面显示滚动条，就绪／失败后隐藏。

依据：[Meta 跟踪源码](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_tracking_predictor.py)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)、[HF 后端源码](https://github.com/huggingface/transformers/blob/main/src/transformers/models/sam3_tracker_video/modeling_sam3_tracker_video.py)、[官方加载进度示例](https://github.com/huggingface/transformers/blob/main/src/transformers/cli/serving/model_manager.py)。Meta 与 HF 的会话 API 分别核对，不假定二者相同。
