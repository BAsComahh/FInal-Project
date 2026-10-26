# Real-ESRGAN 托盘边缘增强组件

作为低优先级的备用图像处理工具：DINO 外观匹配仍无法判断时，可再尝试增强托盘边缘，为后续托盘定位与尺寸匹配提供输入。当前组件只做图像增强，尚未实现 DINO 失败后的自动触发、托盘检测或尺寸匹配。

使用已验证的官方 ncnn Vulkan 后端与 `RealESRGAN_x4plus`，固定放大 4 倍。默认分块 128 像素、Vulkan GPU 0（本机 RX 7900 XT）；Vulkan 编号与 PyTorch 编号不同。

## 命令行

在项目根目录运行：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.real_esrgan inputs/test.png
```

也支持 `python tools/real_esrgan.py inputs/test.png`。不调用 SAM、DINO 或 Homography。

参数：

- `--gpu 0`：Vulkan 显卡编号。
- `--tile 128`：输入图像的分块尺寸，至少 32；显存不足时可减小。
- `--runtime-dir vendor/real_esrgan`：官方程序和模型目录。
- `--output-dir outputs/real_esrgan`：输出目录。

输出 `<图片名>_x4.png`、运行参数与尺寸信息 `<图片名>_x4.json`、后端日志 `<图片名>_x4.log`。

## Python 接口

```python
from components.real_esrgan import upscale_image

result = upscale_image("inputs/test.png")
enhanced = result["image"]
scale = result["scale"]  # 4

# enhanced 上检测到的位置先还原为原图像素坐标。
original_xy = enhanced_xy / scale
```

输入也支持 uint8 OpenCV 灰度、BGR 或 BGRA 数组，返回对应通道格式。BGRA 的颜色通道使用 Real-ESRGAN，alpha 使用最近邻放大以保留原有二值 mask。返回 `input_size`／`output_size`（宽、高）、模型、后端、GPU、分块尺寸、运行耗时和日志。Python 接口只使用临时输入输出文件，返回后清理，不生成永久文件。

增强图的像素长度是原图的 4 倍，不能直接当成桌面实际长度。后续应将增强图的坐标还原到原图，再接入已有 Homography 或物理尺寸计算。

## 运行时文件

```text
components/real_esrgan/
  __init__.py
  upscaler.py              图像输入、官方后端调用、结果返回
tools/real_esrgan.py        命令行和永久文件输出
vendor/real_esrgan/         本机运行时；已加入 .gitignore
  realesrgan-ncnn-vulkan.exe
  vcomp140.dll
  vcomp140d.dll
  models/
    realesrgan-x4plus.bin
    realesrgan-x4plus.param
```

本机已复用 Demo 下载的程序与权重，无需重新安装依赖，也没有改动 PyTorch／Transformers。运行时不放在 `outputs` 内，可独立清理实验结果。

新机器可下载[作者发布的 Windows 压缩包](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip)，将其内容解压到 `vendor/real_esrgan/`，或通过 `--runtime-dir` 指向已解压目录；保持程序、DLL 和 `models` 的相对位置。缺少程序或模型时，组件会给出路径提示，不自动联网下载。

官方来源：[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)、[ncnn Vulkan 后端](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan)。
