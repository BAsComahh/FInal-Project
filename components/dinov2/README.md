# DINOv2 type 特征更新

输入一份已完成注册的 reference，重新计算单位向量和 type 汇总向量，替换特征文件。模型保持冻结，不训练固定兵种分类器，也不修改 DINOv2 权重。

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.update_type_features outputs/sam3_registration/frame_你的保存标识
```

默认在输入目录写入 `type_features.npz`。重新运行会替换该文件；本次 reference 中移除的单位或类型不会残留在新特征中。也可固定一个本局特征库路径：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.update_type_features outputs/sam3_registration/frame_你的保存标识 --output outputs/current_match/type_features.npz
```

工具读取 `prompts.json` 的 `registration_complete: true`、`instances.json` 和每个对象的 `selection.json`／透明 `target.png`。标注草稿不会参与更新。缺少标签、文件或清单标签不一致时中止；空 mask 会跳过并记入元数据，全部为空则中止。验证或计算失败会保留原特征文件，成功后才替换。

## 官方依据与本项目选择

- [Meta 官方仓库](https://github.com/facebookresearch/dinov2) 提供通用预训练骨干及特征用途；本工具不使用分类头。
- [Transformers 官方文档](https://huggingface.co/docs/transformers/model_doc/dinov2#notes) 将输出第 0 个 token 作为整图 CLS 特征，用于分类／检索；其余 token 是局部 patch 特征。本版使用 CLS。
- 加载方式采用官方 `AutoImageProcessor`＋`AutoModel.from_pretrained()`；缩放、中心裁剪和归一化沿用 [small 权重的官方 processor 配置](https://huggingface.co/facebook/dinov2-small/blob/main/preprocessor_config.json)。默认 `facebook/dinov2-small`，输出 384 维向量，本机已有缓存。
- **本项目的处理策略**：先将透明背景合成到官方图像均值颜色上，再补成正方形并留足中心裁剪边距，避免长条单位被默认中心裁剪切掉两端。正式查询图片也应通过同一组件预处理。
- **本项目的汇总策略**：每个单位保留一条 L2 归一化向量。按 type 取这些向量的均值，再 L2 归一化得到 type 汇总向量。A1、A2 的独立向量仍保留，后续可做多参考匹配；均值并不是官方定义的兵种特征。

这里的 type 是单位表提供的标签，DINOv2 负责视觉编码。向量相似不保证能区分外观相近的 type，后续匹配阈值需要在实际素材上验证。

## 输出格式

单个 NPZ 内同时保存数组和 JSON 元数据，避免数组与清单错配。可用 `np.load(path, allow_pickle=False)` 读取。

| 字段 | 含义 |
| --- | --- |
| `sample_features` | N×D，各 reference 的单位向量 |
| `sample_unit_ids` | 与单位向量行对应的 A1／A2 等编号 |
| `sample_type_ids` | 每个 reference 的 type |
| `type_features` | K×D，各 type 的汇总向量 |
| `type_ids` | 与 type 向量行对应的类型编号 |
| `metadata` | JSON：模型、版本、输入处理、样本来源、单位属性、文件指纹、分组行号、空 mask 等 |

不同模型／输入处理得到的向量不能直接混用；元数据记录模型及预处理配置。更新只使用这份 reference，不把上一场比赛的 A1 混入本局，也不自动追加旧视角。匹配、训练、负样本判别和注册 UI 的自动调用暂不接入。

## Python 组件

```python
from components.dinov2 import DinoV2Extractor, update_type_features, load_type_features

extractor = DinoV2Extractor()  # 可复用加载后的模型
path = update_type_features("outputs/sam3_registration/frame_xxx", extractor=extractor)
gallery = load_type_features(path)
print(gallery["type_ids"], gallery["type_features"].shape)
```

单独编码 PIL 图像：

```python
from PIL import Image
from components.dinov2 import DinoV2Extractor

extractor = DinoV2Extractor()
with Image.open("target.png") as image:
    vectors = extractor.encode([image.copy()])
```

`--model` 可指定其他 DINOv2 骨干或本地模型目录，`--device` 指定设备，`--batch-size` 默认 8。默认只使用本地缓存；首次使用其他模型时加 `--download` 允许官方加载接口下载权重。默认自动选择显存最大的 GPU，FP32 推理；沿用现有 `sam3-demo` 依赖，无需另装 DINOv2 仓库或重新配置环境。
