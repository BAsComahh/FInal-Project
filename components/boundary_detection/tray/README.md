# 局部矩形托盘边界

这是 `boundary_detection` 的托盘策略，与桌面边界共用原始 LSD、短线合并、通用交点几何、线段绘制和图像／JSON 读写。托盘策略增加 mask 限定区域、固定尺寸矩形候选和分级回退；不使用桌面外围区域、横竖方向或全图长线门槛，也不读取桌面 `config.toml`。

## 最小百分比像素实验

Qt 客户端默认 adaptive。`fit_registered_trays(frame, prediction, context, previous=..., reuse_stable=True, source_frame=...)` 用最后一次实际拟合的 mask 判断稳定性。质心位移不超过参考短边的 5%，且同一图像坐标中的二值 mask IoU 至少为 0.90 时，复用已接纳的结果并保留实际拟合基准。基准随实际拟合更新，慢移可累计触发局部重拟合。

局部初值和稳定复用都要求图像大小、映射、尺寸及身份相容。首帧编辑、恢复目标、R、实际缺失或标定变化重新建立几何。基准保存质心、面积、包围盒和裁剪后的原分辨率二值 mask 位串。失败的实际拟合也记录 mask 基准，等待后续 mask 有明确变化再重试。当前结果与 profile 区分实际拟合帧 `fit_sample.frame_index` 和观测帧 `observation_frame_index`。

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
| `search_pct`／`--search-pct` | 35 | mask 回退起点沿托盘宽／深的 ±35% 分量，包含对角偏移 |
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

1. 以 mask 位置和尺寸构建局部工作区，有标定时校正到桌面平面，运行 LSD 获取当前帧线段。
2. **local** 以上次接纳的四角为唯一初值。adaptive 里，两个 mask 质心在同一桌面平面的距离超过托盘短边的 50% 时，直接从完整搜索开始。没有标定时以像素换算。底层 `tray_search="local"` 仍可用来做总是先试上一框的对照。
3. **corner** 使用完整搜索的合并线池和直角配对。把矩形沿直角两条边贴合，尝试长短边对应。
4. **edge** 沿候选边的两侧分别贴上矩形长边／短边。沿边位置取 mask 质心在边线上的投影。
5. **mask** 从 mask 质心提出初始角度，失败时再试包围框中心及其八个周围偏移。
6. 每组起点都进入共用 Beam、精校和验收。上一组验收失败时进入下一组。`--mode corner|edge|mask` 可强制检查对应分支。

**Beam** 对每个位姿保留原位，并试同角度的八方向平移和固定中心的 ±5° 旋转。平移步长为托盘短边的 10%，对角和轴向平移等长。每轮去重后保留三个，默认六轮上限，前三个位姿集合稳定时提前停止。`beam_rounds` 为该分支实际执行的轮数，mask 分支的补充起点组另计。

方向 Chamfer 将原始 LSD 有限线段按无向切线角度每 5° 分桶，对每个非空桶做二维距离变换。矩形四边各取 24 点，查询空间距离和角差罚分的联合最小值。默认 12° 角差的罚分相当于一个边缘距离容差，单点代价截断在三个容差。纯 mask 分支的粗排使用覆盖率和 IoU。参见 [Liu 等，CVPR 2010，第 3、4.2 节](https://www.merl.com/publications/docs/TR2010-045.pdf)。

**精校** 对保留的位姿依次试 27 个候选，两轴平移 `-2、0、+2` 倍 `corner_nudge_pct`、旋转 `-2°、0°、+2°`。边缘分数来自原始 LSD 线段，最终覆盖率按完整工作区 mask 计算。某个位姿精校失败后仍可检查其余 Beam 候选。

矩形宽深固定。旋转角对矩形只定义到 180°，正方形还存在 90° 对称；它不代表已识别单位正面方向。

## 评分与输出

- `mask_coverage`：矩形覆盖的 mask 点比例。初筛最多采样 4096 点，保留候选用完整工作 mask 重算。
- `edge_support`：矩形各边与方向相近的原始 LSD 线段的贴合程度，距离用高斯衰减。分数不把合并填补的空隙当成真实边。
- `mask_iou`：工作 mask 与固定尺寸矩形的近似交并比。
- `visible_fraction`：完整矩形投影到拟合输入图像后，落在画面内的面积比例，默认下限为 `TrayConfig.min_visible_fraction = 0.80`。出画边缘采样计为无支持。通过的候选保留完整四角，mask 覆盖率仍只使用实际观测到的像素。
- local／corner／edge 综合分数：`0.55×edge_support + 0.35×mask_coverage + 0.10×mask_iou`；mask 分支：`0.8×mask_coverage + 0.2×mask_iou`。

这些权重和门槛是**可调启发式，不是模型置信概率，也不是定位准确率**。四路共用默认覆盖门槛 0.70。局部／直角分支平均边缘支持门槛 0.40，单边分支 0.20。没有达到门槛也保留最佳诊断候选，`success=false`；所有结果都设置 `needs_review=true`，供探索期人工检查。

默认写入 `outputs/tray_detection/`：原始 mask、局部区域、mask 叠加、LSD 线、候选角、各级候选框、原图叠加、组合步骤图，以及 `<图名>_tray.json`。四角按矩形边循环排列，**不是**原图固定的 TL/TR/BR/BL 顺序。JSON 保留原图／工作区／标定平面坐标、分支、评分和配置。`percentage_basis` 记录局部阈值、搜索与 ROI margin 的基准，`resolved_lengths_work_px` 记录实际使用的工作像素长度；百分比尺寸实验还记录 `requested_size_pct`、`size_percentage_basis` 和换算后的 `requested_size`，其 `length_unit` 为 `pixels`。

参数：`--no-merge`、`--max-work-size`、`--angle-tolerance`、`--angle-step`、`--refine-rounds`（每组起点的 Beam 轮数上限，0 只评分起点）、`--min-mask-coverage`。其他门槛可通过 `TrayConfig` 指定。视频工作流通过 `batch.fit_registered_trays` 对已绑定且有尺寸的 mask 调用相同拟合接口，候选可用于托盘图层及后续规则查询；未提供尺寸的单位不生成矩形。

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
