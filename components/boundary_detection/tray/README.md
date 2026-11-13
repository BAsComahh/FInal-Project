# 局部矩形托盘边界

这是 `boundary_detection` 的托盘策略，与桌面边界共用原始 LSD、短线合并、通用交点几何、线段绘制和图像／JSON 读写。托盘策略增加 mask 限定区域、固定尺寸矩形候选和分级回退；不使用桌面外围区域、横竖方向或全图长线门槛，也不读取桌面 `config.toml`。

## 最小百分比像素实验

正式 Qt／OpenCV 入口固定 adaptive（2026-11-11 用户后续要求），不再提供 `--tray-search`，单图 CLI 的 `fit_tray` 算法不变。`fit_registered_trays(frame, prediction, context, previous=..., reuse_stable=True, source_frame=...)` 从上一已接纳矩形的小型描述判断稳定性：质心相对上次实际拟合位移 ≤短边 2%、面积变化 ≤10%、32×32 归一化轮廓 IoU ≥0.90、可靠主轴变化 ≤3°。近方形主轴不作为独立判据。全部通过返回 `method=stable_reuse`，保留原拟合帧、方法与基准；否则先局部搜索再走已有完整回退。基准不随噪音更新，慢移可累计触发；阈值均为试验配置。

只复用同图像大小／映射／尺寸、身份仍有效的已接纳上一解；首帧编辑、恢复目标、R、实际缺失或标定变化不能用旧矩形。无上一成功拟合或持续不合格的 mask 仍需要拟合，不缓存一个假矩形。完整 mask 不另存，仅保存面积／矩和 128 字节压缩轮廓（以 hex 存储）；当前结果／profile 区分 `fit_sample.frame_index`、`observation_frame_index` 与 reuse_check。历史仍记录接纳时间及滤波后的几何，不把每条观测解释为一次新拟合，不改变历史 schema。

无窗口应用的 `tray_search="full"` 保留完整拟合基线，`"local"` 每次尝试上一解局部拟合，均保留完整回退；正式客户端不暴露这些对照选项。计时 stats 给 reused／refitted／unavailable 数量；静态计时或门控通过不表示定位精度已经校准。

2026-11-11 受控 CPU 检查覆盖稳定复用、慢移累计、10° 转动／面积变化、空 mask、尺寸／映射／图像大小变更及近方形方向退化。320×240 合成静态样例 full 约 194 ms，稳定 adaptive 均值约 0.184 ms；不计模型／动态遮挡，不能当作整场性能收益。局部失败完整回退、取消／迟到结果、R／恢复目标与连续历史的会话级交叉情况尚未完整检查，证据在 `outputs/refactor_checks/qt_uncertainty_adaptive_terra_20261111`。

```powershell
# 复用已有 SAM3 点分割组件生成一个 mask，随后运行局部 boundary 搜索。
conda run --no-capture-output -n sam3-demo python -m tools.tray_detector inputs/test5.png --point 530 555 --size-pct 17.02 6.38 --show

# 使用已保存的同一帧 mask，无需加载 SAM；强制查看 mask 备用分支。
conda run --no-capture-output -n sam3-demo python -m tools.tray_detector inputs/test5.png --mask outputs/tray_detection/test5_long_unit/test5_input_mask.png --size-pct 17.02 6.38 --mode mask --output-dir outputs/tray_detection/test5_mask --show
```

`--size-pct WIDTH DEPTH` 的两个值都以**完整输入图像短边** `min(height, width)` 为基准，`5` 表示 5%。`test5.png` 的短边为 940 px，示例约换算为 `160×60` px；这是单个长托盘的近似像素尺寸，用于观察方法，不代表真实毫米尺寸或标注真值。旧 `--size-px` 已删除并会报错，不会按百分比解释。输入 mask 必须与图片尺寸、坐标一致。`--point X Y` 仍使用原图像素坐标，每次只分割一个目标；核心检测组件直接接受现有 mask，不依赖 SAM。

## 几何长度的百分比基准

`TrayConfig` 和 CLI 使用显式 `*_pct`／`--*-pct` 字段。它们必须是有限正数；旧的 `roi_margin`、`*_fraction` 配置字段已删除。局部欧氏距离统一以 `min(view["size"])`（工作坐标中的托盘短边）换算，不以整张图或 ROI 的短边代替，也不叠加固定像素下限。

| 配置字段／对应 CLI | 默认值 | 基准或用途 |
| --- | --- | --- |
| `min_line_length_pct`／`--min-line-length-pct` | 12 | 托盘短边；LSD 线段最小长度 |
| `endpoint_gap_pct`／`--endpoint-gap-pct` | 18 | 托盘短边；交点到线段端部距离 |
| `edge_tolerance_pct`／`--edge-tolerance-pct` | 2.5 | 托盘短边；边缘支持的高斯距离尺度 |
| `merge_distance_pct`／`--merge-distance-pct` | 2.5 | 托盘短边；共线合并距离 |
| `merge_gap_pct`／`--merge-gap-pct` | 30 | 托盘短边；共线合并间隙 |
| `corner_dedup_pct`／`--corner-dedup-pct` | 3 | 托盘短边；角点去重距离 |
| `corner_nudge_pct`／`--corner-nudge-pct` | 1 | 托盘短边；角点候选平移步长，同时用作角点强度分母的长度正则项 |
| `candidate_dedup_pct`／`--candidate-dedup-pct` | 1.5 | 托盘短边；矩形候选中心去重距离 |
| `search_pct`／`--search-pct` | 35 | 分别沿托盘宽／深搜索 ±35%，局部细化继续缩小该范围 |
| `roi_margin_pct`／`--roi-margin-pct` | 25 | 保留原工作区语义：包围框最大跨度乘 25% 得到 padding，托盘对角线乘 `(0.5 + 25/100)` 得到搜索半径 |

底层合并函数仍接收工作像素长度，百分比仅在托盘入口换算一次。角度仍用度、覆盖率仍用 `[0,1]`；`max_work_size` 是工作图像的像素采样上限，模糊／形态学内核仍按像素定义。长度归一化不保证不同分辨率的 LSD 检测或重采样结果完全相同，极小目标仍受采样分辨率限制。

## 实际尺寸模式

类型表可以包含以下信息，同 type 实例继承：

```json
{"unit_types": [{"type_id": "A", "dimension": {"width_mm": 100, "depth_mm": 80}}]}
```

示例中的毫米值必须换成本局真实测量值。`inputs/units.example.json` 中的尺寸也只是格式示例。尺寸可选以兼容原注册流程；提供时必须是有限正数，托盘的毫米模式则要求目标类型有尺寸。

先使用现有 Homography 工具标定，`--board-size` 的宽高也必须按毫米输入；然后：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.tray_detector inputs/test5.png --mask path/to/mask.png --units inputs/units.example.json --type A --calibration path/to/homography.json --show
```

JSON 必须包含 `image_to_board` 和 `board_size`。相机、裁剪和图片坐标必须与标定一致，工具不会猜测旧标定的物理单位。先在桌面平面建立固定宽深的矩形，再将结果投回原图；结果的 `center_plane`／`corners_plane` 才按毫米解释。像素模式不输出真实距离。

## 逐级回退

1. 以 mask 粗位置和尺寸构建局部工作区，必要时用 Homography 校正平面。
2. LSD 检测局部任意朝向线段，复用现有共线短边合并；合并线只帮助提出候选，边缘分数使用原始观测。
3. **corner**：两条近似垂直的线，其交点必须接近实际端部。沿两条边展开固定尺寸矩形，尝试长宽对应并微调。
4. **edge**：直角候选不足时，沿单边方向、两侧及沿边位置提出候选。
5. **mask**：仍不足时，在 mask 质心和包围框中心附近搜索位置和角度。单边与 mask 分支再做局部逐级细化。
6. 每级按分数排序；通过该级覆盖／边缘门槛后停止回退。`--mode corner|edge|mask` 可强制检查某一级，`--mode auto` 为默认策略。

无窗口对照可传 `tray_search="local"`：以上次成功四角在当前工作视图初始化，先尝试沿两轴 ±2×`corner_nudge_pct` 的平移及 ±2° 旋转，共 27 个候选；仍按当前 mask 覆盖和当前原始 LSD 边缘评分，通过直角分支门槛才接受。成功时跳过短线合并和全量角点组合；失败才执行完整流程。`tray_search="full"` 保留全量对照。标定、尺寸变化或重置后不沿用不兼容的旧初值；没有成功候选的对象下一次也重新完整搜索。这是当前观测上的局部更新，不是缓存旧矩形冒充新测量。

矩形宽深固定。旋转角对矩形只定义到 180°，正方形还存在 90° 对称；它不代表已识别单位正面方向。

## 评分与输出

- `mask_coverage`：矩形覆盖的 mask 点比例。初筛最多采样 4096 点，保留候选用完整工作 mask 重算。
- `edge_support`：矩形各边与方向相近的原始 LSD 线段的贴合程度，距离用高斯衰减。分数不把合并填补的空隙当成真实边。
- `mask_iou`：工作 mask 与固定尺寸矩形的近似交并比。
- corner／edge 综合分数：`0.55×edge_support + 0.35×mask_coverage + 0.10×mask_iou`；mask 分支：`0.8×mask_coverage + 0.2×mask_iou`。

这些权重和门槛是**可调启发式，不是模型置信概率，也不是定位准确率**。默认覆盖门槛 0.55，直角分支平均边缘支持门槛 0.40，单边分支 0.20。没有达到门槛也保留最佳诊断候选，`success=false`；所有结果都设置 `needs_review=true`，供探索期人工检查。

默认写入 `outputs/tray_detection/`：原始 mask、局部区域、mask 叠加、LSD 线、候选角、各级候选框、原图叠加、组合步骤图，以及 `<图名>_tray.json`。四角按矩形边循环排列，**不是**原图固定的 TL/TR/BR/BL 顺序。JSON 保留原图／工作区／标定平面坐标、分支、评分和配置。`percentage_basis` 记录局部阈值、搜索与 ROI margin 的基准，`resolved_lengths_work_px` 记录实际使用的工作像素长度；百分比尺寸实验还记录 `requested_size_pct`、`size_percentage_basis` 和换算后的 `requested_size`，其 `length_unit` 为 `pixels`。

参数：`--no-merge`、`--max-work-size`、`--angle-tolerance`、`--angle-step`、`--refine-rounds`（0 关闭细化）、`--min-mask-coverage`。其他门槛可通过 `TrayConfig` 指定。视频工作流通过 `batch.fit_registered_trays` 对已绑定且有尺寸的 mask 调用相同拟合接口，候选可用于托盘图层及后续规则查询；未提供尺寸的单位不生成矩形。

## Python 接口

```python
from components.boundary_detection.tray import TrayConfig, fit_tray
from components.boundary_detection.scale import image_short_side, percent_to_length

short_side = image_short_side(image_bgr.shape)
size = [percent_to_length(value, short_side) for value in (17.02, 6.38)]
result = fit_tray(image_bgr, full_resolution_mask, size, config=TrayConfig(edge_tolerance_pct=2.5))
# fit_tray 的 size 接口仍接收几何坐标单位；未标定时是换算后的像素长度。
# 标定模式：size 与 image_to_plane 的目标单位必须相同。
# result = fit_tray(image_bgr, mask, (100, 80), image_to_plane=calibration["image_to_board"])
# 可选局部初值，必须是同一原图坐标系、宽度沿第 0→1 条边的循环四角：
# result = fit_tray(image_bgr, mask, size, initial_corners=previous_best["corners_image"])
print(result["best"]["corners_image"])
```

已对合成旋转矩形、只有单边／只有 mask、透视标定及 `test5` 单个单位做短测。没有人工角点真值、真实毫米尺寸或多场景定位误差统计，不能据此声称精确定位已解决。实验依据和结果路径持续记录在 [项目思路](../../../项目思路.md) 中。

官方参考：[OpenCV LSD／ROI](https://docs.opencv.org/4.x/db/d73/classcv_1_1LineSegmentDetector.html)、[Homography 点映射](https://docs.opencv.org/4.x/d7/dff/tutorial_feature_homography.html)。本项目的角点组合、分级候选搜索与评分属于自己的实现策略。
