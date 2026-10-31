# 单位几何追踪实验

首轮只验证清晰、连续可见的刚体运动。算法不依赖 SAM 推理，不认识固定兵种，也不更新 reference；读取人工／既有流程给定的实例 ID 和初始四角，独立输出实验视频及状态记录，尚未接入正式界面或规则局面。

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.track_units inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --initialization inputs/tracking.video_estimate.json --seconds 15 --show
```

提供的 ABC 示例来自剪辑第 5 秒人工估算的托盘四角，包含当时使用的桌面 Homography；不是 SAM mask、真实兵种认定或独立评测真值。工具从该帧开始；不能把 `--start` 改到别的时刻却继续使用原四角。`--max-width` 默认 960，工作画面和四角同步缩放；`--tracking-fps` 默认 15，实际采样率按源帧间隔记录，不能把较低采样率当作无代价提速。

初始化格式沿用投影工具的几何记录，四角必须按边循环排列：

```json
{"clip_timestamp_seconds": 5, "units": [{"unit_id": "A1", "corners_image": [[220,140],[380,140],[380,220],[220,220]]}]}
```

没有 `homography` 时直接使用原图像素，适合已经拉正的视频；有 `homography: {matrix, output_size}` 时，图像与四角一起映射。矩阵必须对应同一来源视频。可选 `source_video_sha256` 用于拒绝错误视频，运行记录始终保留视频和初始化哈希。

算法在每个单位局部区域做多点 LK 前向和反向光流，剔除不一致点，再用 RANSAC 估计旋转、平移和临时尺度。尺度变化超出门槛时拒绝更新；接纳时只保留旋转和平移，初始四角形状及尺寸固定。另检查点覆盖面积和相对初始外观的相关性。距离门槛均以托盘短边百分比定义；LK 窗口、特征块和外观重采样大小是栅格算法参数。

`tracked` 仅表示通过启发式检查，不是身份正确率或可见率。失败后变成 `uncertain`，保留最后接纳四角和 `pose_frame_index`；源帧号继续前进，旧位置不冒充本帧测量。输出橙框及 `pose@...` 明确标记旧姿态。本轮**不自动恢复** uncertain 对象；重新可见也不自动把它认回，不从失败原因断言一定是手或物理移除。需要新初始化才能继续这个对象。

默认输出新目录 `outputs/tracking_comparison/lk_.../`：

- `run.json`：代码哈希、环境、初始化、尺度、配置、对象数、采样率及计时摘要。
- `timings.csv`：解码／拉正、追踪、记录／叠加／编码耗时；按活跃追踪数量分开统计，避免丢失对象后少算任务造成虚假加速。
- `observations.jsonl`：每单位源帧、姿态帧、状态及质量分项。
- `overlay.mp4`：供人工复核；按源采样帧率播放，和程序处理吞吐分开解释。

`--output-dir` 必须是尚不存在的目录，以保留已有实验。没有 GPU/模型对照、人工真值或多场景测评时，不声称比 SAM 更准确或已解决遮挡恢复。模型上方纹理、相机变化、相似单位和拿起再放下仍可能误导光流；矩形轴也不能直接代表单位正面。

官方算法接口：[LK](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html)、[RANSAC 几何估计](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html)。局部范围、接纳门槛和失败状态是项目实现，实验现象记在根目录 `项目思路.md`。
