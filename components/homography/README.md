# Homography 组件与工具

`components/homography` 使用 TL、TR、BR、BL 四角，把桌面映射到俯视矩形，并提供坐标的正反转换。支持带 TL/TR/BR/BL 键的角点字典，也支持按上述顺序排列的 `(4, 2)` 数组；不会自动交换角点顺序。

```python
from components.homography import warp_table, transform_points

image = "inputs/table4.png"
corners = [[116, 128], [616, 130], [627, 365], [104, 364]]  # TL, TR, BR, BL
calibration = warp_table(image, corners, output_size=(1200, 800))
rectified = calibration["image"]
table_pixels = transform_points([[400, 200], [500, 300]], calibration["matrix"])
original_pixels = transform_points(table_pixels, calibration["inverse_matrix"])
```

输入图像可为路径或 OpenCV 的 uint8 BGR、BGRA、灰度数组。函数调用不保存文件、不打开窗口。点转换支持单个 `[x, y]`、多个点及空点列表，不裁剪到桌面范围内。

## 结构

```text
components/homography/
  __init__.py   对外导出三个计算接口
  geometry.py   标定矩阵、尺寸估算、坐标转换
  image.py      图像读取与透视拉正
  corner_picker.py   手动点选四角、显示原图坐标
tools/homography.py   接收图像与四角、解析命令行参数和保存文件
tools/pick_table_corners.py   点选四角工具
```

组件与工具均仅依赖 OpenCV 和 NumPy，不导入或调用桌角检测；角点由调用者提供。原有 `from tools.homography import ...` 也可继续使用。

## 接口

- `compute_homography(corners, output_size=None, *, board_size=None)`：只计算标定，不处理图像。
- `warp_table(image, corners, output_size=None, *, board_size=None)`：计算标定并拉正图像，结果增加 `image` 字段。
- `transform_points(points, matrix)`：用指定矩阵变换坐标。

标定结果包含 `matrix`（原图 → 俯视像素）、`inverse_matrix`（反向）、`source_corners`、`target_corners`、`output_size`、`output_size_estimated`，以及可选的实际桌面映射。

目标角点为 `(0,0)`、`(width-1,0)`、`(width-1,height-1)`、`(0,height-1)`。不指定 `output_size` 时，由对边中较长一侧的像素长度估算尺寸；此模式适合预览，不能据此确定真实桌面长宽比。重复／共线、交叉或其他非凸角点会报错。

## 实际桌面坐标

`board_size=(宽, 高)` 使用调用者选定的统一单位；例如 `(72, 48)` 可表示 72 × 48 英寸，也可传厘米尺寸。工具不自动采用固定实际尺寸。

```python
calibration = warp_table(image, corners, board_size=(72, 48))
board_points = transform_points([[400, 200]], calibration["image_to_board"])
image_points = transform_points(board_points, calibration["board_to_image"])
```

提供实际尺寸时，增加 `image_to_board`／`board_to_image` 矩阵，分别映射到实际单位与原图像素；未提供时这两个字段及 `board_size` 为 `None`。实际桌面原点为 TL，x 沿上边向右，y 沿左边向下。

自动输出尺寸会遵循给定的实际宽高比。若同时指定 `output_size` 和 `board_size`，像素尺寸以显式输入为准；选取相同宽高比可避免预览被拉伸。实际单位映射与预览像素映射分别保存。

## 命令行

不知道四角像素坐标时，先打开手动点选工具：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.pick_table_corners inputs/table4.png
```

按左上 TL → 右上 TR → 右下 BR → 左下 BL 的顺序左键点击，图上和终端会显示每个点的 `(x, y)`。坐标原点在原图左上角，x 向右增大，y 向下增大。窗口缩放不改变记录的原图坐标；可用工具栏缩放／平移，退出工具栏相应模式后继续点选。

`U` 或右键撤销最近一点，`R` 重选，`S` 保存四角到 `outputs/homography/<图片名>_corners.json` 并在终端打印完整的 Homography 命令，`Esc` 关闭。点选工具只记录坐标，不自动运行 Homography；复制打印的命令即可测试映射。

保存前复用 Homography 的几何检查，重复、交叉或退化四角无法保存。程序不会自动调换点击顺序。JSON 中的 `corners` 字段也可直接传给 `warp_table()`。

从项目根目录运行，图像和 `--corners` 为必填输入。四角使用原图像素坐标，依次为左上、右上、右下、左下（TL、TR、BR、BL），每个点按 x、y 排列：

```powershell
python -m tools.homography inputs/table4.png --corners 116 128 616 130 627 365 104 364
python -m tools.homography inputs/table4.png --corners 116 128 616 130 627 365 104 364 --size 1200 800
python -m tools.homography inputs/table4.png --corners 116 128 616 130 627 365 104 364 --board-size 72 48
```

也支持 `python tools/homography.py ...`。使用现有 `sam3-demo` 环境，不增加依赖。

工具不会自动检测角点，也不接收检测配置。Python 调用可直接传入四角字典或数组。

默认输出到 `outputs/homography/`，可用 `--output-dir` 修改：

- `<name>_rectified.png`：拉正后的图像。
- `<name>_homography.json`：四角、尺寸和正反矩阵。

缺少必填参数、输入或标定无效时退出码为 2。成功退出码为 0。
