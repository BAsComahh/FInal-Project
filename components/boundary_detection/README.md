# 战场边界检测

主流程只使用 LSD，命令行、交互预览和桌面检测接口共用 `pipeline.compute_boundary` 的几何计算。正式桌角接口不绘图；默认命令行只生成最终边界图和结果 JSON；步骤预览／逐步导出才生成所有阶段图。Canny 保留为独立实验工具，未接入主流程。

桌角检测接口集中在 `table.detect_table(image, config=DEFAULT_CONFIG)`；`tools.table_detector.detect_table` 保留兼容导入和命令行。视频前端直接调用组件，对首帧结果进行人工确认，失败时由界面提供手动四点输入。

矩形托盘是同一 boundary 组件的另一种应用，实现在 [tray/](tray/README.md)。它复用 LSD、短线合并、`geometry.py` 中的交点、图像／报告读写和线段绘制；使用“mask 局部 ROI＋已知尺寸＋直角／单边／mask 回退”策略，不复用桌面外围及横竖筛选。独立入口为 `python -m tools.tray_detector --help`。

## 配置与启动

编辑 [config.toml](config.toml)，修改后重新启动。每项均有中文注释，`true` 开启、`false` 关闭。

```toml
[steps]
detection = true          # LSD 检测；关闭后没有候选线段
merge = true              # 短边拟合
length_filter = true      # 拟合完成后，再筛掉短候选线
search_region = true      # 限制各侧最长边的候选区域

[merge_checks]
source_length = false     # 允许短线段先参与拟合

[geometry]
min_line_length_pct = 39.0625
merge_min_length_pct = 3.90625
merge_distance_pct = 1.171875
merge_gap_pct = 9.765625
connection_distance_pct = 3.90625

[border_selection]
region_pct = 30.0         # 各侧靠边 30%；50 为各自半边
```

优先级：内置默认值 → 配置文件 → 显式命令行开关 → 当前窗口操作。`--config path/to/config.toml` 指定其他配置；窗口操作不改写文件，保存时会把有效开关记入 JSON。

从项目根目录运行，使用现有 `sam3-demo` 环境：

```powershell
# 逐步预览：Round 看拟合轮次，borders 阶段看各侧最长边
conda run --no-capture-output -n sam3-demo python -m tools.boundary_detection inputs/table4.png --interactive --stage merged

# 把合并角度容差临时改为 6 度
conda run --no-capture-output -n sam3-demo python -m tools.boundary_detection inputs/table4.png --interactive --merge-angle 6

# 只保存最终叠加图与报告
conda run --no-capture-output -n sam3-demo python -m tools.boundary_detection inputs/table.png

# 导出所有阶段，不打开窗口
conda run --no-capture-output -n sam3-demo python -m tools.boundary_detection inputs/test3.png --export-stages

# 原始 LSD 线段，不进行拟合与选边
conda run --no-capture-output -n sam3-demo python -m tools.boundary_detection inputs/table4.png --raw --show
```

`--show` 在完整流程中打开逐步预览，在原始模式显示原图与全部 LSD 线段。`--raw` 与 `--interactive`、`--export-stages` 分开使用；预览中的原始线段用 `--stage raw`。

## 流程与开关

0. 原图。
1. 灰度与可选高斯模糊。
2. 原始 LSD 线段。
3. 检查允许参与拟合的源线段：可选长度门槛与横／竖方向。
4. 共线短边拟合，默认重复到没有新合并。每次重新核对全部原始证据，原始线段也保留在候选池。
5. 最终长度筛选，默认开启。
6. 横／竖方向筛选。
7. 遍历全部候选，在上下左右各自区域中直接选最长线段；等长时选更靠近画面边界的一条。候选线段中点按配置限于各侧靠边的 30% 区域，不再进行内收组合搜索，也不以闭合作为选边停止条件。
8. 严格闭合检查：四个相邻接点均连接，每边使用不同端点，形成非退化凸四边形。
9. 延长线补全：只要最后选出了四条边，就延长相邻边求四角，不要求已有接点。相邻边平行、退化或交点无法形成凸四边形时失败。推算点用橙圈和 `*` 标记，严格闭合结果保持独立。

某侧没有合格候选时返回缺边结果，不会跨区域找边。补全只检查几何条件，仍可能产生狭长或位置不正确的框，需人工观察。

各步骤可关闭：`--no-blur`、`--no-detection`、`--no-lsd-refinement`、`--no-merge`、`--no-repeat-merge`（别名 `--single-pass`）、`--no-length-filter`、`--no-axis-filter`、`--no-border-selection`、`--no-search-region`、`--no-closure`、`--no-completion`。关闭上游时，需要其结果的后续步骤会跳过。关闭闭合检查仍可用最后四边延长求交，所有角会标记为推算角。

区域限制按线段中点判断，不要求整条线段处于该区域：`region_pct=30` 时，左边中点 x ≤ 图宽的 30%，右边 x ≥ 70%；上边中点 y ≤ 图高的 30%，下边 y ≥ 70%（以最大像素坐标为基准）。`search_region=false` 或 `--no-search-region` 关闭外侧限制后，横线仍按中点分到上／下半边，竖线分到左／右半边，避免同一条线同时充当相对两边。

合并约束独立关闭：`--no-merge-source-length`、`--no-merge-axis`、`--no-merge-angle`、`--no-merge-distance`、`--no-merge-gap`、`--no-merge-coverage`。源方向约束和最终方向筛选分别控制。

大多数开关去掉 `no-` 即可临时开启。合并角度、距离、间隙检查用 `--check-merge-angle`、`--check-merge-distance`、`--check-merge-gap`，避免与已有数值参数重名。

## 参数

几何长度统一为**图像短边百分比**：`5` 表示 5%，不是 0.05 或 5 px。入口用 `percent / 100 × min(height, width)` 换算一次，底层算法和输出角点仍使用原图坐标。横竖共用同一长度尺度，不改变欧氏角度。长度默认值从 TOML 的 `[geometry]` 读取；下表对应当前配置，在 `table4.png` 的短边 512 px 上保留此前调参的像素门槛。旧像素数值参数已移除，使用时明确报错。

角度仍为度、覆盖率仍为 `[0,1]`，模糊核和预览尺寸仍为栅格参数。归一化不保证不同分辨率下 LSD 生成完全相同的线段。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--blur-size` | 5 | 正奇数；1 关闭模糊 |
| `--refine` | std | LSD 内部细化：none／std／adv |
| `--merge-min-length-pct` | 3.90625 | 源线段长度百分比；512 px 短边时为 20 px，默认不启用 |
| `--merge-angle` | 6 | 原始线段之间的合并方向差容差 |
| `--merge-distance-pct` | 1.171875 | 到拟合直线的最大偏离百分比；512 px 时为 6 px |
| `--merge-gap-pct` | 9.765625 | 沿拟合线方向的最大空隙百分比，允许 0；512 px 时为 50 px |
| `--merge-min-coverage` | 0.5 | 原始观测对拟合跨度的最小覆盖率，重叠部分只算一次 |
| `--min-line-length-pct` | 39.0625 | 进入选边前的最短长度百分比；512 px 时为 200 px |
| `--angle-tolerance` | 15 | 横／竖方向容差 |
| `--connection-distance-pct` | 3.90625 | 端点与交点连接容差百分比；512 px 时为 20 px |
| `--border-region-pct` | 30 | 各侧靠边候选区域百分比，范围 (0, 50]；上下按图高、左右按图宽 |

例如 `--merge-gap-pct 5` 表示短边 512 px 时容许 25.6 px 的间隙，短边 1024 px 时容许 51.2 px。窗口滑块同样使用百分比，并标出当前图像的短边基准。

## 输出与接口

默认输出到项目根目录的 `outputs/boundary_detection/`，可用 `--output-dir` 覆盖：

- `<name>_boundary.png`：最终叠加图，失败时显示诊断候选。
- `<name>_stages.json`：参数、开关、线段、拟合轮次、选边信息与闭合／延长结果。
- 显式 `--export-stages`、`--interactive` 或 `--show` 时，阶段导出为 `_stage_00_input.png` 到 `_stage_09_completed.png`，另存拟合轮次。
- 原始模式输出 `<name>_lsd_raw.png` 与 `<name>_lsd_raw_report.json`。
- 窗口的 **Save current stages** 保存有效参数、所有阶段、最终叠加图和控件截图。

JSON 的 `output_polygon` 为最终 TL、TR、BR、BL 原图坐标，无结果时为空；`output_is_estimated` 表示含推算角。严格检查见 `final_frame`，补全见 `frame_completion`，各侧候选数量、选中长度与区域范围见 `side_selection`。`parameters` 保留有效百分比，`length_normalization` 记录基准，`resolved_lengths_px` 记录本图实际使用的像素门槛。选边实现在 `border_selection.py`。

```python
from components.image_io import load_image
from components.boundary_detection.lsd import detect_lsd_lines

lines = detect_lsd_lines(load_image("inputs/table4.png"))  # (N, 4)
```

只需结果时用 `compute_boundary(image, args, initial_switches(args))`，返回包含中间几何与阶段统计的报告，不创建诊断图。需要最终叠加图时调用 `render_result(image, report)`；需要所有阶段图时调用 `render_stages(image, args, report)`。`compute_stages(image, args, switches)` 组合计算与阶段绘图，供交互查看器使用。

组件参数直接由 `config.BoundaryParameters(...)` 创建，命令行使用同一对象的默认值，并接受显式参数覆盖；`initial_switches` 仍读取 TOML 并应用命令行开关。`table.detect_table` 不导入命令行模块。正式结果接口返回四角／四边或手动矫正请求；独立命令在 [tools.table_detector](../../tools/table_detector.py)，交互诊断窗口在 `frontend/boundary_viewer.py`。图像读取／保存来自 [image_io](../image_io/README.md)。

## 独立 Canny 工具

Canny 不参与 LSD 流程，也不读取主流程的 config。默认在原图上用青色显示 Canny 轮廓，不绘制角点或圆圈；同时保留原始黑白边缘图。

```powershell
# 原图叠加青色 Canny 轮廓
conda run --no-capture-output -n sam3-demo python -m tools.canny inputs/test.png --show
```

默认输出到 `outputs/canny/`：`<图片名>_contours.png` 为原分辨率青色轮廓叠加图，`_edges.png` 为黑白边缘图，`_edge_comparison.png` 为原图／边缘／轮廓对照。

`--show` 直接显示轮廓叠加图。阈值用 `--low`／`--high`，模糊用 `--blur-size`，边缘检测算法和默认阈值保持不变。Hough 默认关闭，需要时显式加 `--hough`。长度参数 `--min-line-length-pct`（别名 `--hough-min-length-pct`，默认 0，不限制长度）和 `--max-line-gap-pct`（默认 3.90625）均以图像短边为基准；`--hough-threshold` 仍为投票数。旧像素长度参数已移除，`--no-hough` 仍可使用。
