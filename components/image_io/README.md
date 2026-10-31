# 图像读写

统一提供中文路径安全的 OpenCV 图像读取与保存，只依赖 NumPy 和 OpenCV，不加载模型。

```python
from components.image_io import load_image, save_image

image = load_image("inputs/test5.png")              # 默认 uint8 BGR
mask = load_image("path/to/mask.png", mode="gray")  # 二维灰度
cutout = load_image("path/to/target.png", mode="unchanged")  # 保留透明通道
save_image("outputs/example/target.png", cutout)
```

`load_image(source, *, mode="color")` 接收路径或 uint8 数组。`color` 转为 BGR，`gray` 转为灰度，`unchanged` 保留灰度／BGR／BGRA；尺寸与坐标不变。无需转换的数组不复制，调用者若需独立修改可使用 `.copy()`。不是分割或阈值化接口，读取 mask 不会自动二值化。

`save_image(path, image)` 按扩展名选择编码器，创建父目录并返回输出路径；没有扩展名时使用 PNG 编码。无效／无法解码的输入、编码或写入失败均报错，不静默跳过。PNG 支持保存 BGRA 透明通道；输出格式本身需支持所需通道，JPEG 不保存透明度。

单张图像读取／另存工具（默认保留原通道）：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.image_io inputs/test5.png outputs/image_io/test5.png
conda run --no-capture-output -n sam3-demo python -m tools.image_io inputs/test5.png outputs/image_io/test5_gray.png --mode gray
```

也支持 `python tools/image_io.py ...`。不增加缩放、裁切或批处理功能。

Boundary、Homography、SAM 的 PNG 导出与输入转换，以及 Real-ESRGAN 的临时文件读写共用本组件。SAM 仍在送入官方 processor 前转换 BGR→RGB；Real-ESRGAN 使用 `unchanged` 保留灰度／透明度，超分后的 alpha 仍由原组件按最近邻放大。旧内部 `_load_image`／`_save_png` 名称按原位置保留为同一函数的导入别名。

SAM 输入约定已核对本机 Transformers `5.18.0` 的 `Sam3Processor` 源码，以及 [HF 官方接口](https://huggingface.co/docs/transformers/model_doc/sam3)、[Meta 图像 processor 源码](https://github.com/facebookresearch/sam3/blob/main/sam3/model/sam3_image_processor.py)。本次共享的是本项目的文件读写，不改变官方预处理、模型或会话。
