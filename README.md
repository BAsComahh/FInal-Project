# Board game augmentation

[中文](#中文) | [English](#english)

## 中文

当前先探索战场边界检测。实现集中在 [components/boundary_detection/](components/boundary_detection/README.md)。

```text
tools/table_detector.py          图像 → 最终四角／四边，失败时返回手动矫正请求
tools/homography.py              图像＋四角 → 俯视图、正反坐标映射
tools/real_esrgan.py             备用托盘边缘增强：图像 → 4 倍超分图
components/real_esrgan/          官方 Vulkan 后端的独立图像增强组件
components/sam3/sam3_segmenter.py          图像＋miniature 提示词 → 实例分割
components/sam3/sam3_click_segmenter.py    点击多个目标 → 批量分割、界面预览与切图
tools/sam3_registration.py       自动检测 → 界面补充／移除 → 保存注册目标
components/sam3/                SAM3 模型复用、分割推理与预览
components/homography/           标定、坐标转换与图像映射组件
components/boundary_detection/   LSD 流程、config.toml、逐步预览；独立 Canny 工具
inputs/                         输入图片
outputs/                        实验结果
```

程序调用入口见 [tools/table_detector.py](tools/table_detector.py)：

```python
from tools.table_detector import detect_table
```

接口使用当前配置和默认参数，并检查四角是否位于图像中各自对应的象限。检测失败时返回手动矫正请求。

编辑 [config.toml](components/boundary_detection/config.toml) 开关 LSD 各步骤。源线段长度门槛关闭、最终长度筛选开启。在项目根目录运行逐步预览：

```powershell
python -m components.boundary_detection inputs/table4.png --interactive --stage merged
```

独立输入图像和四角，生成桌面俯视图和 Homography 标定（角点顺序：左上、右上、右下、左下）：

不知道角点坐标时，可先运行 `conda run --no-capture-output -n sam3-demo python -m tools.pick_table_corners inputs/table4.png`，依次点击四角后按 `S`，终端会打印可复制的映射命令。

```powershell
python -m tools.homography inputs/table4.png --corners 116 128 616 130 627 365 104 364
```

工具支持指定输出像素尺寸及桌面实际宽高，并提供坐标的正反转换。组件接口与用法见 [components/homography/](components/homography/README.md)。

独立运行 SAM3 分割，默认提示词为 `miniature`：

```powershell
python -m components.sam3.sam3_segmenter inputs/test.png
```

使用现有 `sam3-demo` 环境及本机缓存权重，输出到 `outputs/sam3/`。参数与接口见 [components/sam3/](components/sam3/README.md)。

点击多个目标，然后按 S 分割并在当前窗口显示结果：

```powershell
conda run --no-capture-output -n sam3-demo python -m components.sam3.sam3_click_segmenter inputs/test.png
```

每次左键选择一个独立目标；右键排除最近目标的区域，`U` 撤销，`R` 清空。`S` 批量分割、在窗口中显示叠加图及切图，并保存到 `outputs/sam3_click/`。

自动检测后打开注册审核界面：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.sam3_registration inputs/test.png
```

左键补充漏检目标，右键在 mask 或切图上移除目标，`U` 撤销，`R` 恢复初始检测，`S` 保存当前注册列表到 `outputs/sam3_registration/`。右侧切图用滚轮翻页。

左下角切换到 `Polygon` 可手动画多边形：依次点击顶点，最后点击起点 A 闭合并注册；至少三个顶点。`U` 撤销顶点，`C` 取消草稿，`S` 保存。可切回 `SAM point` 使用点分割。

托盘边缘增强备用工具：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.real_esrgan inputs/test.png
```

用于 DINO 无法判断时进一步探索托盘定位与尺寸匹配。当前提供独立图像增强接口，默认 4 倍放大，输出到 `outputs/real_esrgan/`。接口及运行时安装见 [components/real_esrgan/](components/real_esrgan/README.md)。

## English

The project currently explores battlefield boundary detection. The implementation is in [components/boundary_detection/](components/boundary_detection/README.md).

```text
tools/table_detector.py          Image → four corners and four edges; requests manual correction on failure
tools/homography.py              Image + four corners → rectified image and forward/inverse coordinate mappings
tools/real_esrgan.py             Optional tray-edge enhancement: image → 4x super-resolution
components/real_esrgan/          Independent enhancement using the official Vulkan backend
components/sam3/sam3_segmenter.py          Image + miniature prompt → instance segmentation
components/sam3/sam3_click_segmenter.py    Click targets → separate masks, in-window previews, and cutouts
tools/sam3_registration.py       Detect → review/add/remove → save registered targets
components/sam3/                Reusable SAM3 model, inference, and visualization
components/homography/           Calibration, coordinate transforms, and image rectification
components/boundary_detection/   LSD pipeline, config.toml, stage viewer, and a standalone Canny tool
inputs/                         Input images
outputs/                        Experiment results
```

The programmatic entry point is [tools/table_detector.py](tools/table_detector.py):

```python
from tools.table_detector import detect_table
```

The interface uses the current configuration and default parameters. It checks that each corner lies in its corresponding image quadrant and returns a request for manual correction if detection fails.

Edit [config.toml](components/boundary_detection/config.toml) to enable or disable individual LSD pipeline steps. The source segment length filter is disabled, while the final length filter is enabled. Run the stage viewer from the project root:

```powershell
python -m components.boundary_detection inputs/table4.png --interactive --stage merged
```

Supply an image and four corners independently to generate a rectified table image and homography calibration (corner order: TL, TR, BR, BL):

To get corner coordinates, run `conda run --no-capture-output -n sam3-demo python -m tools.pick_table_corners inputs/table4.png`, click the corners in order, and press `S` to save them and print a ready-to-run mapping command.

```powershell
python -m tools.homography inputs/table4.png --corners 116 128 616 130 627 365 104 364
```

The tool accepts an output pixel size and optional physical table dimensions, and provides forward/inverse point mapping. See [components/homography/](components/homography/README.md) for the component API and usage.

Run SAM3 independently with the default text prompt `miniature`:

```powershell
python -m components.sam3.sam3_segmenter inputs/test.png
```

Uses the existing `sam3-demo` environment and locally cached weights. Results are saved under `outputs/sam3/`. See [components/sam3/](components/sam3/README.md) for options and the Python API.

Click multiple targets, then press S to segment and preview them in the same window:

```powershell
conda run --no-capture-output -n sam3-demo python -m components.sam3.sam3_click_segmenter inputs/test.png
```

Each left click selects an independent target; right click excludes a region from the latest target. Press `U` to undo, `R` to reset, and `S` to segment all targets, show masks and cutouts in the same window, and save them under `outputs/sam3_click/`.

Detect first, then review registrations:

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.sam3_registration inputs/test.png
```

Left click adds a missed target; right click a mask or cutout to remove it. Press `U` to undo, `R` to restore initial detections, and `S` to save retained targets under `outputs/sam3_registration/`. Scroll over the cutouts to change pages.

Choose `Polygon` at the bottom left to draw a manual region: click at least three vertices in order, then click the starting point A to close and register it. Press `U` to undo a vertex or `C` to cancel the unfinished polygon. Switch back to `SAM point` for point-prompted segmentation.

Optional tray-edge enhancement:

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.real_esrgan inputs/test.png
```

This is a fallback image-processing component for investigating tray localisation and dimension matching after DINO cannot resolve a target. It currently provides independent 4x enhancement, saving results under `outputs/real_esrgan/`. See [components/real_esrgan/](components/real_esrgan/README.md) for the API and runtime setup.
