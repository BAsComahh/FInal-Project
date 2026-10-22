# 战场边界检测

主流程只使用 LSD，命令行、交互预览和桌面检测接口共用 `pipeline.compute_stages`。Canny 保留为独立实验工具，未接入主流程。

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

[border_selection]
region_ratio = 0.3333333333333333 # 各侧靠边的 1/3；0.5 为各自半边
```

优先级：内置默认值 → 配置文件 → 显式命令行开关 → 当前窗口操作。`--config path/to/config.toml` 指定其他配置；窗口操作不改写文件，保存时会把有效开关记入 JSON。

从项目根目录运行，使用现有 `sam3-demo` 环境：

```powershell
# 逐步预览：Round 看拟合轮次，borders 阶段看各侧最长边
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection inputs/table4.png --interactive --stage merged

# 把合并角度容差临时改为 6 度
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection inputs/table4.png --interactive --merge-angle 6

# 只保存最终叠加图与报告
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection inputs/table.png

# 导出所有阶段，不打开窗口
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection inputs/test3.png --export-stages

# 原始 LSD 线段，不进行拟合与选边
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection inputs/table4.png --raw --show
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
7. 遍历全部候选，在上下左右各自区域中直接选最长线段；等长时选更靠近画面边界的一条。候选线段中点默认限于各侧靠边的 1/3 区域，不再进行内收组合搜索，也不以闭合作为选边停止条件。
8. 严格闭合检查：四个相邻接点均连接，每边使用不同端点，形成非退化凸四边形。
9. 延长线补全：只要最后选出了四条边，就延长相邻边求四角，不要求已有接点。相邻边平行、退化或交点无法形成凸四边形时失败。推算点用橙圈和 `*` 标记，严格闭合结果保持独立。

某侧没有合格候选时返回缺边结果，不会跨区域找边。补全只检查几何条件，仍可能产生狭长或位置不正确的框，需人工观察。

各步骤可关闭：`--no-blur`、`--no-detection`、`--no-lsd-refinement`、`--no-merge`、`--no-repeat-merge`（别名 `--single-pass`）、`--no-length-filter`、`--no-axis-filter`、`--no-border-selection`、`--no-search-region`、`--no-closure`、`--no-completion`。关闭上游时，需要其结果的后续步骤会跳过。关闭闭合检查仍可用最后四边延长求交，所有角会标记为推算角。

区域限制按线段中点判断，不要求整条线段处于该区域：左边中点 x ≤ 图宽的 1/3，右边 x ≥ 2/3；上边中点 y ≤ 图高的 1/3，下边 y ≥ 2/3（以最大像素坐标为基准）。`search_region=false` 或 `--no-search-region` 关闭外侧 1/3 限制后，横线仍按中点分到上／下半边，竖线分到左／右半边，避免同一条线同时充当相对两边。

合并约束独立关闭：`--no-merge-source-length`、`--no-merge-axis`、`--no-merge-angle`、`--no-merge-distance`、`--no-merge-gap`、`--no-merge-coverage`。源方向约束和最终方向筛选分别控制。

大多数开关去掉 `no-` 即可临时开启。合并角度、距离、间隙检查用 `--check-merge-angle`、`--check-merge-distance`、`--check-merge-gap`，避免与已有数值参数重名。

## 参数

距离仍按原图像素处理，归一化留待后续；角度单位为度，覆盖率无量纲。合并默认参数从 `merge_collinear_segments` 函数签名读取。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--blur-size` | 5 | 正奇数；1 关闭模糊 |
| `--refine` | std | LSD 内部细化：none／std／adv |
| `--merge-min-length` | 20 | 源线段长度门槛，默认不启用 |
| `--merge-angle` | 6 | 原始线段之间的合并方向差容差 |
| `--merge-distance` | 6 | 到拟合直线的最大偏离，垂直于直线方向 |
| `--merge-gap` | 50 | 沿拟合线方向的最大空隙 |
| `--merge-min-coverage` | 0.5 | 原始观测对拟合跨度的最小覆盖率，重叠部分只算一次 |
| `--min-line-length` | 200 | 原始／拟合线进入选边前的最短长度 |
| `--angle-tolerance` | 15 | 横／竖方向容差 |
| `--connection-distance` | 20 | 端点与交点连接容差 |
| `--border-region-ratio` | 1/3 | 各侧靠边候选区域占比，可在 (0, 0.5] 内覆盖配置 |

## 输出与接口

默认输出到项目根目录的 `outputs/boundary_detection/`，可用 `--output-dir` 覆盖：

- `<name>_boundary.png`：最终叠加图，失败时显示诊断候选。
- `<name>_stages.json`：参数、开关、线段、拟合轮次、选边信息与闭合／延长结果。
- 阶段导出为 `_stage_00_input.png` 到 `_stage_09_completed.png`，另存拟合轮次。
- 原始模式输出 `<name>_lsd_raw.png` 与 `<name>_lsd_raw_report.json`。
- 窗口的 **Save current stages** 保存有效参数、所有阶段、最终叠加图和控件截图。

JSON 的 `output_polygon` 为最终 TL、TR、BR、BL 原图坐标，无结果时为空；`output_is_estimated` 表示含推算角。严格检查见 `final_frame`，补全见 `frame_completion`，各侧候选数量、选中长度与区域范围见 `side_selection`。选边实现在 `border_selection.py`。

```python
from components.boundary_detection.io import load_image
from components.boundary_detection.lsd import detect_lsd_lines

lines = detect_lsd_lines(load_image("inputs/table4.png"))  # (N, 4)
```

完整流程用 `compute_stages(image, args, initial_switches(args))`；`args` 可由 `cli.build_parser().parse_args([...])` 创建。应用接口见 [tools.table_detector](../../docs/table-detector.md)。

## 独立 Canny 工具

Canny 不参与 LSD 流程，也不读取主流程的 config。保留边缘图与可选 Hough 对照，便于后续探索边缘辅助检测。

```powershell
# 只查看 Canny 边缘
conda run --no-capture-output -n sam3-demo python -m components.boundary_detection.canny inputs/table4.png --no-hough --show
```

默认输出到 `outputs/canny/`。阈值用 `--low`／`--high`，模糊用 `--blur-size`。需要 Hough 对照时去掉 `--no-hough`，其参数为 `--hough-threshold`、`--min-line-length`（0 不限制长度）、`--max-line-gap`。
