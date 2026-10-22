# Board game augmentation

[中文](#中文) | [English](#english)

## 中文

当前先探索战场边界检测。实现集中在 [components/boundary_detection/](components/boundary_detection/README.md)。

```text
tools/table_detector.py          图像 → 最终四角／四边，失败时返回手动矫正请求
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

## English

The project currently explores battlefield boundary detection. The implementation is in [components/boundary_detection/](components/boundary_detection/README.md).

```text
tools/table_detector.py          Image → four corners and four edges; requests manual correction on failure
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
