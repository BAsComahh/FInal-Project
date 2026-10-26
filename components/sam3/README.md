# SAM3 图片分割

输入单张图片，以 `miniature` 为默认文字提示，输出实例 mask、框和置信度。组件与 tool 均独立运行，不调用桌角检测或 Homography。

## 命令行

在项目根目录，使用现有 `sam3-demo` 环境：

```powershell
conda activate sam3-demo
python -m components.sam3.sam3_segmenter inputs/test.png
python -m components.sam3.sam3_segmenter inputs/test.png --prompt miniature --threshold 0.3
```

也支持 `python components/sam3/sam3_segmenter.py inputs/test.png`。只读取本机已缓存的 `facebook/sam3` 权重；可用 `--model` 指定本地模型目录。自动选择显存最大的 GPU，本机为 RX 7900 XT；可用 `--device cpu` 或 `--device cuda:1` 指定设备。沿用本机已验证的 FP32 精度。

默认输出到 `outputs/sam3/<图片名>_<本次运行标识>/`，可用 `--output-dir` 修改上层目录：

- `overlay.png`：彩色 mask、框、实例编号和分数。
- `masks/000.png` 等：与输入图像同尺寸的二值 PNG，255 为前景。
- `instances.json`：原图路径、图像尺寸、提示词、阈值、每个实例的 xyxy 框、分数及 mask 相对路径。

每次运行生成独立目录，避免上次的 mask 混入本次结果。未检测到实例也会输出原图预览和空实例列表，正常退出。

## Python 接口

```python
from components.sam3.sam3_segmenter import segment_image

result = segment_image("inputs/test.png")
masks = result["masks"]    # bool, (N, H, W)，原图坐标
boxes = result["boxes"]    # float32, (N, 4)，x1/y1/x2/y2 像素坐标
scores = result["scores"]  # float32, (N,)
```

处理多张图片时复用模型，避免反复加载：

```python
from components.sam3 import Sam3Segmenter

segmenter = Sam3Segmenter()
first = segmenter.segment("inputs/test.png", "miniature", threshold=0.5)
second = segmenter.segment("inputs/test2.png", "miniature", threshold=0.5)
```

模型在首次 `segment` 时加载，之后复用。图片也可传入 uint8 的 OpenCV BGR、BGRA 或灰度数组；返回的 `image` 为 BGR 数组。Python 接口不保存文件或弹窗。

`threshold` 是实例分数阈值，默认 0.5；像素 mask 阈值固定为 0.5。暂不添加面积筛选、DINO 分类、追踪或跨帧 ID；图上的编号仅用于对应本张图的 mask。结果是候选分割，仍可能漏检或把杂物选入。

## 结构

```text
components/sam3/
  segmenter.py       模型复用、图片读取、文字提示推理
  visualization.py   彩色分割预览
  point_segmenter.py 点提示分割、复用当前图像特征
  point_viewer.py    多目标选择、窗口预览和批量导出
  registration_viewer.py   自动检测候选的人工增删审核
  polygon.py         手动多边形区域转 mask，不调用 SAM
components/sam3/sam3_segmenter.py   图片输入接口与文件输出
components/sam3/sam3_click_segmenter.py   点击目标分割工具
```

## 点击多个目标分割

```powershell
conda run --no-capture-output -n sam3-demo python -m components.sam3.sam3_click_segmenter inputs/test.png
```

显式指定环境，避免不同命令执行会话之间 `conda activate` 不持续生效。工具会在打开窗口前检查依赖；无需给 base 环境安装 SAM3。

打开图片后逐个点击目标，然后按 S。每次左键点击是一个独立目标，不会把所有点击合成同一个目标的正点。它使用同一份本地 SAM3 权重里的点提示分支（`Sam3TrackerModel`），不需要文字提示、不先运行 `miniature` 检测，也不做追踪。

- 左键：选择一个新的独立目标，显示编号。
- 右键：给最近选择的目标添加排除点。
- `U`：撤销上一次点击。
- `R`：清空当前所有目标和预览，磁盘已保存的结果保留。
- `S`：对所有选中目标分别分割，在当前窗口左侧叠加彩色 mask、右侧显示切图，同时保存全部结果。
- `Esc`：关闭窗口。

首次按 S 会加载模型、计算图像特征；后续目标复用当前图片的特征。支持工具栏缩放／平移，使用后退出相应模式即可继续选点。修改选择后预览会清空，重新按 S 更新。

每次按 S 保存到 `outputs/sam3_click/targets_<本次保存标识>/`：

- `overlay.png`：全部目标的分割叠加图。
- `cutouts.png`：与窗口右侧一致的切图预览。
- `instances.json`：各目标编号及结果路径。
- `target_001/`、`target_002/` 等：每个目标各自的全图二值 `mask.png`、透明背景 `target.png`、叠加图和 `selection.json`。

模型返回空 mask 时，预览标记 empty，结果清单记录空目标且不生成其透明切图。每个目标的 JSON 记录点击与正负标签、xyxy 框和预测 IoU；框的右下边界不包含在区域内。预测 IoU 不等同于文字分割的实例分数。可用 `--device`、`--model`、`--output-dir` 指定设备、本地权重和输出目录。

Python 组件的 `segment(points, labels)` 仍表示一个目标；多个目标分别调用，组件会复用图像特征：

```python
from components.sam3 import Sam3PointSegmenter

segmenter = Sam3PointSegmenter()
segmenter.set_image("inputs/test.png")
first = segmenter.segment([[999, 506]])
second = segmenter.segment([[357, 180]])
# 若需修正第一个目标，传它自己的正点和排除点。
refined = segmenter.segment([[999, 506], [0, 0]], labels=[1, 0])
```

## 自动检测后审核注册

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.sam3_registration inputs/test.png
```

流程：`miniature` 文字检测 → 自动打开审核窗口 → 人工补充和移除 → S 保存最终列表。可用 `--prompt`、`--threshold`、`--device`、`--model`、`--output-dir` 调整输入和输出。

- 自动检测出的非空 mask 默认进入待审核的注册列表，窗口左侧叠加 mask，右侧显示切图。
- 左键点击未注册目标：立即通过点提示分割并添加一个目标，预览同步更新。
- 左下角可切换 `SAM point`／`Polygon`：前者保留 SAM 点选补充，后者依次点击任意数量顶点，再点击起点 A 附近闭合注册；至少三个顶点，支持凹多边形。
- 多边形模式直接以圈定区域生成 mask，不调用 SAM。闭合后立即显示叠加图及切图，继续点击可绘制下一个目标。
- 多边形未闭合时 `U` 撤销最近顶点，`C` 取消草稿；只有再次点击起点才会闭合。`S` 不会自动闭合，需先闭合或取消草稿才能保存。
- 左键点击已有 mask：定位到对应切图页面，避免重复添加。
- 右键点击已有 mask 或右侧切图：从本次注册列表移除。mask 重叠时优先移除较小区域；也可通过切图明确选择。
- `U` 撤销上一次添加、移除或恢复操作；`R` 恢复初始自动检测结果。
- 在右侧切图区域滚动鼠标，每页最多显示 8 个目标。
- `S` 保存当前保留的全部目标；不会重新运行自动检测，移除的目标不会再次加入。
- `Esc` 关闭窗口，不会自动保存未确认的修改。

默认保存到 `outputs/sam3_registration/targets_<本次保存标识>/`，包含全部目标的 overlay、切图预览、总清单，以及每个目标各自的 mask 和透明 PNG。允许保存空列表。每个目标的 `origin` 记录 `automatic`、`manual` 或 `manual_polygon`；`score_type` 区分文字检测分数与点分割预测 IoU，避免混用。手动多边形保留按点击顺序排列的原图像素 `vertices`，`score` 和 `score_type` 均为 `null`，不虚构模型分数。

自动检测结束后释放其模型，再按需加载点提示模型；手动补充时复用当前图像特征。此处“注册”仅指确认保留分割目标，尚不包含兵种命名、属性填写或 DINO 特征提取。两个原有独立工具继续保留。
