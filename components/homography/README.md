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
  __init__.py   对外导出标定、映射与单位绘制接口
  geometry.py   标定矩阵、尺寸估算、坐标转换
  image.py      图像读取与透视拉正
  units.py      带单位 ID 的托盘四角映射与俯视绘制
  corner_picker.py   手动点选四角、显示原图坐标
tools/homography.py   接收图像与四角、解析命令行参数和保存文件
tools/pick_table_corners.py   点选四角工具
tools/project_units.py   在俯视战场上显示托盘矩形与单位编号
```

组件与工具均仅依赖 OpenCV 和 NumPy，不导入或调用桌角检测；角点由调用者提供。原有 `from tools.homography import ...` 也可继续使用。

## 接口

- `compute_homography(corners, output_size=None, *, board_size=None)`：只计算标定，不处理图像。
- `warp_table(image, corners, output_size=None, *, board_size=None)`：计算标定并拉正图像，结果增加 `image` 字段。
- `transform_points(points, matrix)`：用指定矩阵变换坐标。
- `order_corners(points)`：四个无序点 → TL／TR／BR／BL 字典。先用凸包建立环序，再在四种旋转对应中选择与归一化包围框四角最贴合的一组；保留原始像素精度，不要求角点分布在图像四个象限。重复、共线或非凸四点报错。角名按画面方向推断，接近菱形时仍需人工确认。视频前端的手动桌角使用此接口；独立图片点选工具仍保持原有顺序操作。

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

## 托盘矩形显示在俯视战场

默认覆盖层显示托盘边框和 A1、A2 等单位编号；mask 作为可选调试图层，独立开关。输入矩形须已拟合并绑定单位 ID，本组件不重新分割或拟合，也不自动检测桌角。

```python
from components.homography import compute_homography, rectify_units

calibration = compute_homography(table_corners, output_size=(1200, 800))
units = [
    {"unit_id": "A1", "corners_image": fitted_a1["best"]["corners_image"]},
    {"unit_id": "A2", "corners_image": fitted_a2["best"]["corners_image"]},
]
result = rectify_units(original_bgr_frame, units, calibration)
rectified_background = result["rectified"]
display_frame = result["overlay"]
mapped_units = result["units"]
```

独立接口：`project_units(units, matrix)` 只变换四角；`draw_units(rectified, mapped_units)` 只绘图；`rectify_units(image, units, calibration)` 用同一标定变换背景和四角。函数不修改输入、不保存文件、不加载模型。单位记录中的其他元数据（如 `object_id`、`type_id`）保留。

### 独立调试图层

背景始终保留；矩形层（含编号）与 mask 层独立控制，可只开其一、同时开或全部关闭。矩形绘在半透明 mask 之上，同一单位两个图层使用相同颜色。默认矩形开、mask 关。

- `--rectangles`／`--no-rectangles`：开关矩形及编号。
- `--masks`／`--no-masks`：开关 mask。
- `--mask-alpha 0.4`：mask 不透明度，范围 0～1。
- `--show`：预览窗口提供 `Rectangles`、`Masks` 两个 0/1 开关，鼠标可操作。`R`／`M` 分别切换，`S` 保存当前组合的原尺寸覆盖图及图层状态 JSON，`Esc`／`Q` 关闭。切换不自动保存。

每个有 mask 的实例增加 `"mask_path": "相对于几何JSON目录的路径.png"`，也可使用绝对路径。图像必须是与原图尺寸一致的二值 mask（0/1 或 0/255），不是裁剪图、透明切图、概率或 logits。没有 mask 的实例可不填写；mask 图层只显示已提供的实例，终端报告数量。如果全部缺少 mask，命令行 `--masks` 会报错，预览尝试打开 mask 时则提示并关回该开关。不会用矩形自动制造一个替代 mask。

```python
result = rectify_units(original_bgr_frame, units, calibration,
                       masks={"A1": a1_full_frame_binary_mask},
                       show_rectangles=True, show_masks=True, mask_alpha=0.4)

# 再次切换只合成已经投影好的图层，不重新变换 mask 或运行模型。
from components.homography import render_unit_layers
mask_only = render_unit_layers(result["rectified"], result["units"],
                               masks=result["masks"],
                               show_rectangles=False, show_masks=True)
```

`rectify_units` 的 `masks` 参数按单位 ID 接收原图 mask；返回的 `masks` 则是按同一 ID 保存的俯视二值 mask，供 `render_unit_layers` 使用。不会在 JSON 中写入整个 mask 数组。最近邻投影保留二值标签，输入 mask、矩形及 reference 文件不受显示开关影响。

命令行 `--units` 接收的是**实例几何文件**，与注册时只包含 type 和 dimension 的类型目录不同：

```json
{
  "image_size": [1428, 940],
  "units": [
    {
      "unit_id": "A1",
      "corners_image": [[612.88, 577.79], [453.41, 590.74], [448.55, 530.93], [608.02, 517.98]]
    }
  ]
}
```

每个单位使用原始图片像素坐标，四角沿边顺时针或逆时针排列，起点不限；无需是 TL/TR/BR/BL，但必须凸且无交叉。单位 ID 不可重复。`image_size` 可省略；提供时按 `[宽, 高]` 检查是否与原图一致。`corners_plane` 不能直接填进 `corners_image`。若拟合在已标定桌面平面进行，应取拟合结果中已经逆变换回原图的 `best.corners_image`。

```powershell
python -m tools.project_units inputs/test5.png --units outputs/project_units/test5_demo/test5_geometry.json --corners 8 4 1418 4 1420 938 8 938 --show
python -m tools.project_units inputs/table4.png --units path/to/table4_unit_geometry.json --calibration outputs/homography/table4_homography.json --show
```

首条是已有单个 test5 托盘候选的演示：A1 为显式指定，桌面四角是近似边界，未验证实际尺寸或定位精度。第二条展示已有标定的用法，需自行提供属于 table4 同一原图的单位几何文件。默认保存到 `outputs/project_units/`，`--output-dir` 可修改；`--size 宽 高` 只用于显式 `--corners` 模式，不覆盖已有标定尺寸。

test5 演示几何文件已补充对应的原尺寸 mask 路径，可同时显示两个图层：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.project_units inputs/test5.png --units outputs/project_units/test5_demo/test5_geometry.json --calibration outputs/project_units/test5_demo/test5_demo_homography.json --masks --show
```

输出 `<图片名>_rectified.png`（俯视背景）、`_overlay.png`（边框及编号）、`_units.json`（原始四角及浮点 `corners_rectified`、单位 ID、矩阵和输出尺寸）。坐标不裁剪；仅绘图时取整并由 OpenCV 裁切可见边线。保留旋转，绝不改用水平包围框；若标定或拟合不正确，变换后的四边形可能不具备直角，本层不强行修正。

这是独立单帧显示接口。用于视频时，每帧应传入该帧对应的已拟合托盘记录；静态几何文件不会自动追踪移动单位，相机移动也需要更新标定。

实现复用现有 `transform_points` 与 OpenCV `warpPerspective`／`polylines`。依据：[官方点映射示例](https://docs.opencv.org/4.x/d7/dff/tutorial_feature_homography.html)、[官方绘图接口](https://docs.opencv.org/4.x/d6/d6e/group__imgproc__draw.html)。

Mask 显示参考 [Meta 可视化源码 `render_masklet_frame`](https://github.com/facebookresearch/sam3/blob/main/sam3/visualization_utils.py) 的二值 mask 半透明叠加方式，以及 [HF 官方后处理接口](https://huggingface.co/docs/transformers/model_doc/sam3_tracker_video)。核对本机 Transformers `5.18.0` 的 `Sam3TrackerVideoProcessor.post_process_masks` 后，本层只消费已后处理的原尺寸二值 mask，不修改 SAM 模型和会话；Homography、按键及图层组合是本项目实现。
