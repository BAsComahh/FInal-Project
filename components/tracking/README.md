# 注册后的候选视频追踪

EdgeTAM现显式开启HF后处理`apply_non_overlapping_constraints=True`：同一像素仅归属于mask分数最高的对象，之后二值化，原object ID顺序保持。它不会自动纠正错误身份或保证恢复被吞并对象；真实视频效果仍待实测。

首帧仍由现有 SAM3 点击分割、撤回、绑定 type，并一次保存 reference。可通过 `--tracker sam3|cutie|edgetam` 选择后续传播；默认 `edgetam`，显式选择 `sam3` 或 `cutie` 可作对照，LK 已移除。传播后端不要求预先认识本局兵种，只接收已注册实例的完整 mask 和 ID。默认运行前需准备下述 EdgeTAM 资产；此切换不表示取得了新的速度或准确率排名。

## EdgeTAM 单实例手动恢复

视频前端已提供 `Recover units`，交互见 [前端说明](../../frontend/README.md#不停播的手动恢复edgetam)。初始候选由独立 SAM 会话分割，随后共享权重但独立状态的 Edge 会话传播和补点；原实例标签确认后，`update_mask` 用官方 `add_inputs_to_inference_session` 对指定已有 object ID 输入 mask，不重置其他对象。`correct_points` 只处理单对象候选，支持同帧累积及跨帧修正；同帧编辑必须使用同一图像，禁止回退源帧。提交失败仍保留已消费索引，业务层单独隔离目标。

本机 HF 5.18.0 的 mask 输出分数缺少普通解码分支的 object 轴，混合更新会在分数拼接处报错。`edgetam_compat.py` 仅继承并规范该分支的分数形状；不修改安装目录或复制完整 forward。依据为 [HF EdgeTAM 官方用法](https://huggingface.co/docs/transformers/model_doc/edgetam_video)、实际安装源码及 RX 7900 XT 对照短测。当前兼容与恢复不扩展到 SAM3／Cutie；后者仍可照常作传播对照。

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

`--segmentor` 指定注册用 SAM3 checkpoint；`--tracker` 选择传播后端，`--tracker-model` 覆盖该后端 checkpoint，`--tracker-cache` 指定模型缓存根目录。默认不额外限制调度频率，worker 空闲后处理最新未消费源帧；可显式 `--inference-fps` 限速，`--stride` 已移除。实际速度依设备、对象数和输入尺寸而变；串行任务与重复／已消费帧保护保留，没有积累无界视频帧或使用未来帧。暂停显示／查询不暂停输入和追踪，Clear query／Return live 回到最新画面。

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

## 单次自动恢复

恢复 mask 只清除目标旧正面，不直接恢复方向可信性；有初始 F 参考时，独立的 [DVMNet 辅助选边](../../frontend/README.md#dvmnet-辅助正面) 可在匹配观测重新选择当前托盘正面边。该组件失败不重置追踪会话。

`automatic_recovery.py` 复用 SAM3 文本模型与 DINOv2-small，参考只从当前注册的 Missing 实例读取／缓存，不写 NPZ 或追加图库。启动时准备模型；每个新失败实例只触发一次搜索。全部当前 Missing 参考用于竞争检查，只有本轮排队 ID 可接回；正常 mask 任意像素占用的候选排除，同一／重叠候选的实例竞争交人工。试运行相似度 0.85、分差 0.10 由用户选定，未校准为概率；单候选分差未知也交人工。

满足门槛的 mask 在搜索输入的同一已观测帧通过官方 `input_masks` 接回原 object ID；不回放整段视频或重建正常对象。其余候选仅建立独立 Edge 会话并共享权重，连续传播到人工审核，消失后作废。运行阶段／Correct／No／手动回退由 [前端恢复流程](../../frontend/README.md#追踪失败判定与只读名单) 管理；No 跨帧排除仍未定义。加载／搜索／目标更新异常独立隔离；B08／R／关闭取消任务，已消费的后端帧号保留。真实 GPU 同帧接回未改写其他对象既有记忆，随后两帧二值 mask 与对照一致；后续浮点记忆有微小差异，实测边界见根目录《项目思路》。
