# 注册后的候选视频追踪

首帧仍由现有 SAM3 点击分割、撤回、绑定 type，并一次保存 reference。可通过 `--tracker sam3|cutie|edgetam` 选择后续传播；默认 `edgetam`，显式选择 `sam3` 或 `cutie` 可作对照，LK 已移除。传播后端不要求预先认识本局兵种，只接收已注册实例的完整 mask 和 ID。默认运行前需准备下述 EdgeTAM 资产；此切换不表示取得了新的速度或准确率排名。

## 准备与启动

本机已准备好权重和独立依赖；新机器或缺失文件时先运行：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.setup_tracking --backend all
```

脚本将 Cutie 官方固定版本源码放入 `vendor/cutie`，模型放入 `outputs/model_cache`，可选包放入 `outputs/tracking_dependencies`。不会升级或替换当前 torch、torchvision、Transformers、NumPy；结果和哈希记在 `outputs/model_cache/setup_all.json`。这些资产不提交到仓库。

```powershell
# SAM3 首帧注册 → Cutie 持续传播
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30 --tracker cutie --inference-fps 10

# 同一注册流程 → EdgeTAM 视频传播
conda run --no-capture-output -n sam3-demo python -m frontend inputs/Ja5-2RIOBXU_02-30-00_02-35-00.mp4 --seconds 30 --tracker edgetam --inference-fps 10
```

每次仍先确认桌角／尺寸，再注册和绑定。所选候选模型在启动准备期间加载；首次播放先把最终 SAM3 masks 交给候选初始化，完成后才启动视频时钟，避免冷启动消耗整个短片区间。S 只完成保存，首次播放再初始化传播后端。R 清空本局会话，保留已加载权重；不自动编辑播放中的历史提示。

`--model` 指定注册用 SAM3；`--tracker-model` 覆盖候选 checkpoint，`--tracker-cache` 指定模型缓存根目录。`--inference-fps` 只是更新上限，实际速度依设备、对象数和输入尺寸而变；没有积累无界视频帧或使用未来帧。暂停显示／查询不暂停输入和追踪，Clear query／Return live 回到最新画面。

## 官方接口及实现选择

| 候选 | 接口／固定来源 | 当前配置 |
| --- | --- | --- |
| Cutie | [官方 InferenceCore 示例](https://github.com/hkchengrex/Cutie/blob/main/scripting_demo.py)，源码 `ec5cdd4cf16f75c73ad785a2f96fb97dbad4125a` | base-mega、FP32、generic streaming 配置，内部短边上限 480 |
| EdgeTAM | [Meta 实现](https://github.com/facebookresearch/EdgeTAM)、[HF 视频接口](https://huggingface.co/docs/transformers/model_doc/edgetam_video) | Transformers 5.18.0；[HF 转换权重](https://huggingface.co/yonigozlan/EdgeTAM-hf) `c266ce53b3fc00f0f495b583f6a116c4e57f53bb`，FP32、1024 输入 |

Cutie 使用官方 `CUTIE`／`InferenceCore.step`；初始标签背景为 0，实例映射到连续标签，输出还原原 ID。重叠像素按注册显示顺序由最后一个 mask 所有，不把类别标签做双线性插值。官方构造器还需两个 ResNet 初始化文件，设置脚本会一并准备；不用带硬编码 CUDA 的 convenience helper。

EdgeTAM 使用已安装 `Sam2VideoProcessor` 的 `input_masks` API 和持久流式 session。原 Meta `.pt` 不能直接当 HF checkpoint 使用。本机 5.18.0 的配置格式化会临时构造默认 vision config，触发额外 Hub 查询；适配器读取完整 checkpoint 配置，并对本次配置实例设置公开的 `has_no_defaults_at_init` 标记避免该查询。这是本项目的离线兼容处理，不是 Meta 要求；未修改已安装库或模型结构。传入 session 的 ID 列表使用副本，因为实际 forward 会消费提示 ID 列表。

两个适配器都保留原实例 ID、输出原分辨率 bool mask，内部处理帧号连续，原视频帧号另记；拒绝向后传播，reset 丢弃记忆而保留模型。存在 logits 只作为质量信号，不解释为身份正确概率；Cutie 不伪造该分数。

## 验证边界

两个候选均用真实权重，在 CPU 上对 `test5.png` 的同一个已有 SAM mask 做过初始化和同画面一次传播，尺寸与 ID 检查通过；EdgeTAM 另外检查了加载期间无在线模型请求。没有完成 GPU 视频吞吐、多对象扩展成本、长遮挡恢复或逐帧准确率评价。Cutie 的 480 与 EdgeTAM 的 1024 内部输入不同，单帧 CPU 时间不能直接当公平胜负结论。正式视频界面仍需人工试用；本轮检查不能证明 SAM3→候选的整段视频质量。
