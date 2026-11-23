# EdgeTAM 视频追踪推理速度与端到端延迟实验分析报告

> **硬件与软件环境**：AMD Radeon RX 7900 XT（20 GiB VRAM，RDNA3 `gfx1100`）、`PyTorch 2.13.0+rocm10.0.0`、`Transformers 5.18.0`、EdgeTAM 权重 `yonigozlan/EdgeTAM-hf`（`c266ce5`）。  
> **文档状态**：本文汇总了 2026-11-15 至 2026-11-18 的排查实验、真实长局 SQLite/诊断日志统计与 RX 7900 XT 控制变量基准测试，以及面向 `components/tracking/edgetam.py` 和 `application/session.py` 的可执行优化方案（当前仅作研究与方案归档，尚未修改生产代码）。

---

## 1. 历史实验与结论回顾（2026-11-15）

### 1.1 长跑 `0xc0000409` 原生崩溃根因与有界会话修复（commit `0e53cb5`）
- **崩溃原因**：
  1. 本机 HF `Transformers 5.18.0` 的 `Sam2VideoInferenceSession.store_output` 在 `inference_state_device="cpu"` 下硬编码 `non_blocking=True`（PyTorch 对 GPU→CPU 的异步拷贝强制分配锁页内存 `pin_memory=True`），且不淘汰历史帧；28 对象每帧累积约 `14 MiB` 锁页内存与 `12 MiB` `processed_frames`，508 步即耗尽 Windows WDDM 锁页内存上限，引发 `torch_hip.dll!CachingHostAllocator.cpp:80` 抛异常并在设备守卫析构期间二次抛异常终止进程（`0xc0000409`）。
  2. `sam3-video` 工作线程未调用 `torch.cuda.set_device(...)`，在同时存在核显（`cuda:0` `AMD Radeon(TM) Graphics`, `gfx1036`）与独显（`cuda:1` `AMD Radeon RX 7900 XT`, `gfx1100`）时，线程上下文设备停在 `cuda:0`。
  3. 仅容纳 1 帧的视觉特征缓存（`100 MiB`）跟随 `inference_state_device="cpu"` 卸到 CPU，导致同帧内第 0 个对象算完后拷回 CPU，第 1~27 个对象再重复 CPU→GPU 拷贝 27 次（`2.7 GiB/帧`）。
- **已实施修复**：
  - 新增 `bind_cuda_device`、`configure_video_session`（单帧 100 MiB 视觉特征缓存保留在 GPU，输出改用可分页内存 `non_blocking=False`）及 `prune_video_session`（按模型实际窗口裁剪 `non_cond_frame_outputs`：最近 6 步空间记忆 + 最近 15 步对象指针）。
  - 长局 `frame_6b59223eebc5` 连续运行 **25.5 分钟（772 条观测，3000s → 4529s）** 全程无崩溃，稳态会话内存恒定在 `cpu_mib: 80.25, gpu_mib: 100.5, pinned_mib: 0.0`。

### 1.2 ROCm SDPA 算子分发差异发现
- **反直觉现象**：修复 `bind_cuda_device` 将线程绑定到独显 `cuda:1`（`gfx1100`）后，实测反而比修复前（线程意外停在核显 `cuda:0` `gfx1036`）慢了约一倍。
- **原因**：PyTorch ROCm 的 `scaled_dot_product_attention` 按 **`torch.cuda.current_device()`** 的架构选择算子后端而非张量所在设备：
  - 当 `current_device()` 停在 `gfx1036` 时，由于核显不支持 ROCm `EFFICIENT_ATTENTION`（Aotriton），自动回退到 `SDPBackend.MATH` 在 RX 7900 XT 上执行；
  - 绑定到 `gfx1100` 后，分发器改用 `SDPBackend.EFFICIENT_ATTENTION`，在 FP32 下反而比 `SDPBackend.MATH` 慢约 2 倍（注意力部分慢近 4 倍）。
- **2026-11-15 8/28 对象局部实测数据**：
  - 28 对象 `1533×1023`（合成第 4~6 步，初始仅 1~6 步历史）：`set_device(1)` 默认 `EFFICIENT_ATTENTION` 耗时 **`1259.4 ~ 1345.7 ms/帧`**；显式加 `sdpa_kernel([SDPBackend.MATH])` + 单帧特征留 GPU 后降至 **`511.3 ~ 519.1 ms/帧`**，且二值 mask 输出逐像素差异 `diff_pixels = 0`。

### 1.3 自回归记忆滑窗跨度与 `DEFAULT_INFERENCE_FPS = 1.0`
- 核对本机 `modeling_edgetam_video.py` 源码确认：`maskmem_tpos_enc` 预训练权重形状固定为 `(7, 1, 1, 64)`（1 个条件帧 + 最近 6 个非条件传播步），`max_object_pointers_in_encoder = 16`（1 个条件帧 + 最近 15 个非条件步），无法在不重训时序位置编码的情况下直接扩槽。
- 对比 `frame_83cdb0ce313e`（步距 `~0.68s`）与 `frame_3fe3022f7627`（步距 `~1.49s`）发现：高频采样（`~0.7s/帧`）下 6 个空间记忆槽仅覆盖约 `4.2s`，人手遮挡或贴边时自回归污染会迅速写满全部 6 个槽形成吞并漂移；将采样间隔拉长到 `>= 1.0s` 后，6 个槽稳稳覆盖 `6~9s`，遮挡期间污染迭代次数减半。因此 `application/config.py` 将 `DEFAULT_INFERENCE_FPS` 设为 `1.0`。

---

## 2. 真实场次实测数据汇总（2026-11-15 ~ 2026-11-18）

从 `outputs/sam3_registration/` 下 5 场真实录播的 `history.sqlite3`（`observations` 表）与 `runtime_diagnostics.jsonl` 提取出的精确传播步距（`obs_dt` = 相邻 `observation_timestamp_seconds` 之差）和端到端几何延迟（`e2e_lat` = `timestamp_seconds - observation_timestamp_seconds`，即业务/规则拿到带托盘几何结果的时间减去采样帧时间）：

| 场次归档 | 对象数 | 矫正分辨率 | 版本与状态条件 | `obs_dt`（传播间隔）中位 / 均值 / P90 | `e2e_lat`（端到端几何延迟）中位 / 均值 / P90 | 稳态会话内存 |
| :--- | :---: | :---: | :--- | :---: | :---: | :--- |
| `frame_83cdb0ce313e` (483 obs) | 28 | `1533×1023` | 11-15 前 (`b79f83b`)：线程停在 `cuda:0` (`gfx1036`) 回退 `MATH`，未裁剪锁页内存（508 步崩溃） | **0.633s** / 0.681s / 0.750s | **0.617s** / 0.693s / 0.717s | 无界增长（`~7.1 GiB` 锁页） |
| `frame_3fe3022f7627` (135 obs) | 28 | `1533×1023` | 11-15 修崩溃后（`set_device(1)` `gfx1100`，加 `SDPBackend.MATH` 前，`inference_fps=None`） | **1.483s** / 1.493s / 1.517s | **1.467s** / 1.494s / 1.500s | `cpu: 75.0 MiB, gpu: 100.47 MiB, pinned: 0.0` |
| `frame_d07270f7feba` (647 obs) | 26 | `1526×1017` | 11-15 后 (`0e53cb5`..`105087a`)：`SDPBackend.MATH` + `DEFAULT_INFERENCE_FPS=1.0`，`cond_frames: 1→4`，`cands: 0→1` | **1.500s** / 1.742s / 2.083s | **3.017s** / 3.121s / 3.667s | `cpu: 70.0 MiB, gpu: 100.5 MiB, pinned: 0.0` |
| `frame_1afbbc55a210` (1099 obs) | 26 | `1526×1017` | 11-15 后 (`105087a`)，`cond_frames: 1→4` | **1.600s** / 1.921s / 2.433s | **3.217s** / 3.312s / 3.950s | `cpu: 70.0 MiB, gpu: 100.5 MiB, pinned: 0.0` |
| `frame_6b59223eebc5` (713 obs) | 30 | `1528×1019` | 11-15 后 (`105087a`)，25.5 分钟连续（`3000s→4529s`），`cond_frames: 1→4`，`cands: 0→1` | **1.700s** / 2.148s / 2.467s | **3.450s** / 3.617s / 4.400s | `cpu: 80.25 MiB, gpu: 100.5 MiB, pinned: 0.0` |

此外，在 `frame_6b59223eebc5` 与 `frame_d07270f7feba` 的 `runtime_diagnostics.jsonl`（每 30 步记录一次的墙钟差均值）中可以看到：
- **`frame_d07270f7feba`（26 对象）**：初始 `cond_frames=1, cands=0` 时，单步墙钟耗时为 `1.376s ~ 1.406s`；恢复提交使 `cond_frames` 增至 `3~4` 且存在待审核候选（`cands=1`）时，单步墙钟耗时升至 **`1.54s ~ 1.90s`**。
- **`frame_6b59223eebc5`（30 对象）**：`cond_frames=1, cands=0` 时，单步墙钟耗时为 **`1.60s ~ 2.11s`**；`cond_frames=4, cands=1` 时升至 **`1.99s ~ 2.26s`**。
- **关键异常**：
  1. 尽管 11 月 15 日测出了 `519.1 ms/帧`，但在加了 `SDPBackend.MATH` 之后，**实际运行时每帧依然需要 `1.4s ~ 1.9s`**（并未稳定在 `1.0s` 目标步距内）；
  2. 更严重的是，11 月 15 日之后（引入 `TrayWorker` 异步拟合后）的 3 场实测中，**端到端几何延迟 `e2e_lat` 突然翻倍到了 `3.0s ~ 3.6s`**（而 `frame_3fe3022f7627` 之前 `e2e_lat` 与 `obs_dt` 基本相等，都在 `~1.47s`）。

---

## 3. 为什么实际推理这么慢？四大根因深度拆解

### 根因 A：11 月 15 日 `519.1 ms` 微基准为何低估了真实稳态耗时（真实稳态为 `1152.5 ~ 1190.1 ms` 起）

1. **微基准未填满记忆窗口且存在多步对比偏差**：
   - 11 月 15 日脚本只跑了 `step 0..3` 预热（`non_cond_frames` 只有 `3..5` 帧，远未填满 `6` 帧空间记忆和 `15` 帧指针窗口）。
   - 在真实 30 对象存档 `frame_6b59223eebc5`（`1528×1019`）上实测第 1~18 步（单步精确 GPU 同步）：
     - `step 1`（1 个空间记忆）：`928.3 ms`
     - `step 6`（6 个空间记忆）：`1136.1 ms`
     - `step 7~18`（7 个空间记忆 + 7~15 个指针，进入稳态）：**`1180.8 ~ 1194.1 ms`**。
   - **为什么与 11 月 15 日差异这么大**：除历史记忆未满之外，还受 `28→30` 对象增量、以及当前真实工程下内存布局和满载指针计算叠加影响。在完全复现 11-15 合成脚本（28 对象 `1533×1023`，`step 4..6` 与 `step 7..10`）时，实测当前稳态也为 **`1022.4 ~ 1118.2 ms/帧`**（因此实际代码即使在 `cond=1` 满窗口下也确实需要 `1.12s ~ 1.19s`，而非 `0.52s`）。

2. **CUDA Event 算子级精准拆解（`frame_6b59223eebc5`，30 对象，Step 8，RX 7900 XT）**：

| 模块 / 子阶段 | 调用次数（每帧） | `FP32 MATH` 耗时 | `FP32 EFFICIENT` 耗时 | 占 `FP32 MATH` 总时间比例 |
| :--- | :---: | :---: | :---: | :---: |
| **`memory_attention` 总计（核心瓶颈）** | **30 次**（60 层） | **775.6 ms** | **1260.5 ms** | **67.3%** |
| ├─ `self_attn` SDPA `[1, 1, 4096, 256]` | 60 次 | `272.9 ms` | `539.5 ms` | 23.7% |
| ├─ `cross_attn` SDPA `[1, 1, 4096×3616, 256]` | 60 次 | `245.1 ms` | `472.0 ms` | 21.3% |
| ├─ 线性投影（Q/K/V/O）+ MLP + LayerNorm | 60 层 | `~248.5 ms` | `~241.4 ms` | 21.6% |
| └─ 2D RoPE (`rope_self` + `rope_cross`) | 120 次 | `9.1 ms` | `7.6 ms` | 0.8% |
| **`_encode_new_memory`（记忆编码 + SpatialPerceiver）** | **30 次** | **206.0 ms** | **216.1 ms** | **17.9%** |
| **`mask_decoder`（Prompt/Mask 解码）** | **30 次** | **89.9 ms** | **86.6 ms** | **7.8%** |
| **`_build_memory_attention_inputs` + `_process_object_pointers`** | **30 次** | **41.2 ms** | **46.0 ms** | **3.6%** |
| **`_prepare_vision_features`（RepViT + FPN 主干）** | **1 次** | **18.1 ms** | **0.4 ms*** | **1.6%** |
| **`processor` + `store_output` + `post_process` + `prune`** | **1 次 / 30 次** | **~35 ms** | **~38 ms** | **~3.0%** |
| **合计（独立进程 30 对象单帧传播）** | — | **~1152.5 ms** | **~1638.5 ms** | **100%** |

*注：`EFFICIENT` 测试复用了 `MATH` 步骤已写入 `session.cache` 的 `frame_idx=8` 特征，实际首次图像编码为 `~18.1 ms`。*

3. **为什么 `EdgeTamVideoMemoryAttention` 在 `FP32 MATH` 下特别慢**：
   - 与 SAM2（8 个注意力头、`head_dim=32`）不同，EdgeTAM 将内存注意力设为了 **单头（`num_heads = 1`）、`head_dim = 256`**（张量形状 `[1, 1, 4096, 256]`）。
   - `SDPBackend.MATH` 是非融合算子，每调用一次都要在显存里完整物化 `4096×4096`（`67.1 MiB`）与 `4096×3616`（`59.2 MiB`）的 FP32 注意力权重矩阵并做 softmax 读写——**单帧仅注意力矩阵显存读写就高达约 `48 GiB`**。
   - 此外，实盘长跑中还有三项额外叠加耗时把 `1.15s` 进一步推高到 **`1.4s ~ 1.9s`**：
     - **恢复提交增加永久条件帧（`cond_frames: 1 → 4`）**：每次自动或手动 `update_mask` 成功都会新增 1 个永久条件帧，给全部 30 个对象的 `cross_attn` 各自额外增加 `+512` 空间 token 与 `+4` 指针 token（`k` 从 `3,616` 涨到 `5,164`），每帧额外增加 **`+120 ~ 160 ms`**；
     - **存在待审核恢复候选（`cands = 1`）**：`TaskWorker._run` 会串联推进第二个隔离 `EdgeTamTracker` 单对象会话，每帧再增 **`+100 ~ 180 ms`**；
     - **多线程 CPU/GIL 竞争**：在 Qt 客户端实际播放时，HF `EdgeTamVideoModel.forward` 内部 `for obj_idx in range(30)` 每帧在 Python 侧派发 **~3,500 次独立小算子调用**，与 60 FPS 视频解码 + `cv2.warpPerspective` 主线程、`TrayWorker`（CPU 矩形拟合）、`BoardRenderer`（`qt-overlay`）争抢 Python GIL 与 CPU 核心，带来 **`+150 ~ 250 ms/帧`** 的额外调度与提交开销。

---

### 根因 B：`Layer 0` 自注意力在同帧 30 个对象之间被纯浪费地重复算了 30 遍（纯浪费 `~168 ms/帧`）

查看本机 `transformers.models.edgetam_video.modeling_edgetam_video.py` 可知：
- `EdgeTamVideoModel.forward` 对所有对象串行循环 `for obj_idx in range(num_objects):`，每次都从头调用 `self.memory_attention(...)`。
- `EdgeTamVideoMemoryAttention` 共 2 层（`layers[0]` 和 `layers[1]`）。其中 **`layers[0]` 的整个前半段**——`output + 0.1 * current_vision_position_embeddings`、`rotary_emb`、`layer_norm1`、`self_attn(q, k, v)`、`dropout1` 残差相加以及 `layer_norm2`——**输入完全只依赖当前帧的 `current_vision_features` 与 `current_vision_position_embeddings`，与 `obj_idx` 和历史记忆毫无关系！**
- 但当前每帧对 30 个对象都把完全相同的 `[1, 1, 4096, 256]` 图像自注意力计算了 **30 遍**，白白浪费了整个模型 50% 的 `sdpa_q4096_k4096` 和线性投影开销（实测可无损省去 **`168.0 ~ 178.6 ms/帧`**，数学输出零误差）。

*(注：我们也测试了将 30 个对象合并为 `Batch=30` 一次性送入 `memory_attention` / `mask_decoder` / `memory_encoder`，实测在 RX 7900 XT `FP32 MATH` 下为 `1159.7 ms` vs 串行 `1151.8 ms`，几乎没有提速，因为单对象特征规模 `4096×256` 本身已能打满算力且每层存在大量维度变换与内存碎片拷贝，而复用 `Layer 0` 自注意力则能直接砍掉计算量。)*

---

### 根因 C：会话状态放在 CPU 并强制 `non_blocking=False` 同步拷贝（额外拖慢 `69 ~ 88 ms/帧`）

- 在 commit `0e53cb5` 中，为了规避 HF 5.18.0 对 CPU 状态硬编码 `non_blocking=True` 触发 `hipHostMalloc` 锁页内存泄露，`configure_video_session` 将状态保留在 `cpu` 并改用 `_store_output_pageable(..., non_blocking=False)`。
- 副作用：
  1. 在 `for obj_idx in range(30)` 的循环内，每次 `store_output` 都执行同步 `hipMemcpyDtoH`（每帧触发 **60 次 GPU→CPU 管线强制同步停顿**）；
  2. 下一帧 `_build_memory_attention_inputs` 又要把 `30 × 7 × 2 = 420` 个记忆张量从可分页内存重新拷回显存。
- 既然 `prune_video_session` 已经把 `non_cond_frame_outputs` 严格限制在模型实际需要的 **6 帧空间记忆 + 15 帧对象指针**，直接把会话记忆留在 GPU（`inference_state_device = self.device`）：
  - 30 对象会话总显存占用仅从 `100.5 MiB` 增至 **`163.5 MiB`**（在 RX 7900 XT `20,464 MiB` 显存中仅占 **0.8%**，恒定不增长，`pinned_mib = 0.0`）；
  - 可立即消除全部 420 个张量的往返拷贝和 60 次流同步停顿，实测直接提速 **`69 ~ 88 ms/帧`**。

---

### 根因 D：`MatchSession` / `TrayWorker` → `TaskWorker("facing")` 串行锁步阻塞（使端到端几何延迟从 `1.5s` 翻倍到 `3.0s ~ 3.6s`）

这是 11 月 15 日之后观测结果延迟（`e2e_lat`）突然翻倍到 **`3.0s ~ 3.6s`** 的直接软件架构原因，完整时序存在于 [application/session.py](file:///c:/Users/vasco/Desktop/FInal%20Project/application/session.py#L268-L335) 与 [application/session.py#L544-L558](file:///c:/Users/vasco/Desktop/FInal%20Project/application/session.py#L544-L558)：

1. **`t = t0` 提交 `propagate #k`**：`schedule()`（第 330 行）把 `self.next_inference_time = t0 + 1.0`。
2. **`t = t1 = t0 + 1.45s` 完成 `propagate #k`**：因为单步推理耗时超过 `1.0s`，`t1 >= next_inference_time` **此时已经成立**。
3. **同一帧 `advance()` 内连续触发死锁式抢跑**：
   - 第 512 行 `_queue_geometry(request #k)` 将第 `#k` 帧的 mask 放入 `self.trays.pending`；
   - 第 555 行 `self.trays.start(...)` 在后台 CPU 线程（`tray-fit`）启动第 `#k` 帧的矩形拟合；
   - **0.1 ms 后**，第 556 行调用 `self.schedule(now)`：由于 `TrayWorker` 刚刚提交（`self.trays.take_ready()` 为 `None`），而 `now >= self.next_inference_time` 已满足，`schedule()`（第 319~330 行）**立刻把 `propagate #(k+1)` 提交给了 `TaskWorker`**，使 `self.worker.busy = True`。
4. **CPU 托盘拟合完后被阻塞 1.5 秒无法交付**：
   - `TrayWorker` 在 CPU 上通常只需要 `50 ~ 150 ms` 就完成了第 `#k` 帧的矩形拟合，结果停在 `self.trays.future` 中等待接收；
   - 然而，当前架构规定 `self.trays.take_ready()` 必须在 `schedule()`（第 276 行 `if self.worker.busy: return`，第 310~315 行）中包装成 **`self.worker.submit("facing", ...)`** 才能交给 `_accept_geometry` 落盘！
   - 于是即使 **`FACING_TRACKING_ENABLED = False`（`self.worker.facing is None`，`"facing"` 在 `TaskWorker._run` 中是一个什么都不做的空操作）**，第 `#k` 帧已经算好的托盘几何依然必须在 `TrayWorker` 里**死等 `propagate #(k+1)` 完整跑完（`+1.5s`）**！
5. **下一个周期进一步连环滞后**：
   - 当 `propagate #(k+1)` 在 `t2 = t1 + 1.5s` 完成时，由于 `self.trays.future` 里还卡着第 `#k` 帧的结果未取走，`self.trays.start(...)`（第 555 行）**无法启动第 `#(k+1)` 帧的托盘拟合**（`self.future is not None`）；
   - 等第 310 行把第 `#k` 帧送进 `TaskWorker("facing")` 空跑一圈（耗时一个 Qt tick `~15 ms`）并在下一轮 `advance()` 调用 `_accept_geometry` 后，第 `#k` 帧才终于在 `t2 + 0.02s` 写入数据库与前端显示——这解释了为什么 `history.sqlite3` 中 **`obs_ts[k+2]` 精确等于 `acc_ts[k] + 0.02s`**，也解释了为什么 `e2e_lat` 恒等于 **`2 × 单步传播耗时 ≈ 3.0s ~ 3.6s`**。

---

## 4. AMD Radeon RX 7900 XT 控制变量优化实测结果

### 4.1 底层 SDPA 算子微基准（针对 EdgeTAM 真实单头形状：`[1, 1, 4096, 256]` 与 `[1, 1, 4096×3616, 256]`）

| 精度与 SDPA 后端 | 60 次 `self_attn` (`4096×4096`) | 60 次 `cross_attn` (`4096×3616`) | 120 次 SDPA 合计 | 相对 `FP32 MATH` 加速比 |
| :--- | :---: | :---: | :---: | :---: |
| `FP32 EFFICIENT` | 539.2 ms | 475.0 ms | **1014.2 ms** | 0.53× |
| `FP32 MATH`（当前生产基线） | 281.4 ms | 253.7 ms | **535.1 ms** | 1.00× |
| `FP16 MATH` | 288.7 ms | 255.8 ms | **544.5 ms** | 0.98× |
| **`FP16 EFFICIENT / FLASH`** | **42.7 ms** | **36.6 ms** | **79.3 ms** | **6.75×** |
| **`BF16 EFFICIENT / FLASH`** | **41.2 ms** | **35.8 ms** | **77.0 ms** | **6.95×** |

> **关键发现**：如果在全局整模型（含 RepViT / FPN / MaskDecoder / MemoryEncoder 的 `Conv2d`）外层套 `torch.autocast("cuda", dtype=torch.float16/bfloat16)`，Windows ROCm 上的 MIOpen 会触发 `Conv2d` 内核搜索/回退导致整帧暴涨至 `2.16s ~ 3.12s`；而将 `torch.autocast("cuda", dtype=torch.float16)` + `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH])` **严格限定在 `memory_attention` 与 `spatial_perceiver` 两个纯 Transformer 模块内部**，则既完全绕开了 MIOpen `Conv2d` 陷阱，又因为 `EdgeTamVideoModel` 内置的 RoPE 已经自带 `.float()` 升精度逻辑，可保持极高数值精度（`FP16` 尾数精度 11-bit，远优于 `BF16` 的 8-bit 精度）。

### 4.2 端到端 30 对象单帧传播实测对比（`frame_6b59223eebc5`，Step 8，RX 7900 XT）

| 优化组合方案 | 30 对象单帧总耗时 | 相对基线加速比 | 与基线逐像素差异 (`diff_px / 179,310`) | 最大存在分差 (`max_logit_diff`) |
| :--- | :---: | :---: | :---: | :---: |
| 1. 当前基线（`FP32 MATH` + 可分页 CPU 状态） | **1152.5 ms** | 1.00× | 0 (`0.000%`) | `0.00e+00` |
| 2. 仅复用 `Layer 0` `self_attn`（`FP32 MATH` + CPU 状态） | **973.9 ms** | 1.18× | **0 (`0.000%`)** | **`0.00e+00`** |
| 3. 复用 `Layer 0` `self_attn` + 有界 GPU 状态（`FP32 MATH`） | **904.9 ms** | 1.27× | **0 (`0.000%`)** | **`0.00e+00`** |
| 4. 复用 `Layer 0` + 仅 SDPA 转 `FP16`（CPU 状态） | **600.6 ms** | 1.92× | 3 (`0.0017%`) | `9.92e-04` |
| 5. 复用 `Layer 0` + 仅 SDPA 转 `FP16` + 有界 GPU 状态 | **560.4 ms** | 2.06× | 3 (`0.0017%`) | `9.92e-04` |
| 6. **复用 `Layer 0` + `memory_attention` `FP16` autocast（CPU 状态）** | **469.6 ms** | **2.45×** | **9 (`0.0050%`)** | **`1.44e-03`** |
| 7. **复用 `Layer 0` + `memory_attention` `FP16` autocast + 有界 GPU 状态** | **382.0 ms** | **3.02×** | **9 (`0.0050%`)** | **`1.44e-03`** |
| 8. **复用 `Layer 0` + `memory_attention` & `spatial_perceiver` `FP16` autocast + 有界 GPU 状态** | **372.8 ms** | **3.09×** | **9 (`0.0050%`)** | **`1.44e-03`** |

> 在 **`372.8 ms/帧`**（加上真实场景额外条件帧与多线程竞争后预计约 **`450 ~ 550 ms/帧`**）的算力耗时下，配合 `DEFAULT_INFERENCE_FPS = 1.0`（1.0 秒采样间隔）：
> - 每帧推理都能稳稳在 **`1.0s` 预算以内** 完成，**实际传播步距将从目前的 `1.4s ~ 1.9s` 恢复为精确的 `1.00s`（6 槽记忆稳定覆盖 6.0 秒）**；
> - 若再解除 Root Cause D 的空转 `"facing"` 管线阻塞，**端到端几何延迟（`e2e_lat`）将从 `3.0s ~ 3.6s` 直接降至 `~0.55s ~ 0.65s`（提速 5~6 倍）**。

---

## 5. 可直接落地的代码修改方案参考

以下为对应优化的具体工程实现思路（供后续直接改动时参考）：

### 5.1 `components/tracking/edgetam.py`：GPU 记忆驻留 + `Layer 0` 自注意力复用 + 局部 `FP16` 模块级 Autocast
1. **有界 GPU 状态驻留**：
   - 仅当 `self.device` 为 CUDA/HIP 设备时，将 `init_video_session(..., inference_state_device=self.device)` 传入 `configure_video_session`，依靠已有的 `prune_video_session` 将状态严格裁剪在 `6 帧空间记忆 + 15 帧指针`（30 对象总显存恒定 `~163.5 MiB`，零 CPU↔GPU 同步拷贝、`pinned_mib = 0.0`）。
   - 同时保留 `_store_output_pageable(..., non_blocking=False)` 作为纯 CPU 或兜底情况的安全实现。
2. **包装 `model.memory_attention.forward` 与 `model.spatial_perceiver.forward`**：
   - 在 `EdgeTamTracker.load()` 完成后（仅当使用 CUDA/HIP 设备时），对 `memory_attention.forward` 增加单次 `_infer()` 调用作用域内的 `layers[0]` 自注意力缓存（缓存 RoPE 位置编码、`self_attn` 输出及 `layer_norm2`，并在 `_infer()` 结束的 `finally` 中立即 `clear()` 清空）。
   - **重要避坑**：切勿跨帧仅按 `(current_vision_features.data_ptr(), ...)` 长期缓存！因为 `session.cache` 的 `max_vision_features_cache_size = 1` 会在计算下一帧特征前弹出旧帧，PyTorch 显存分配器极易将同一块显存地址 `data_ptr()` 复用于下一帧特征，导致跨帧命中错误缓存。将缓存生命周期严格限定在单次 `_infer()` 内（并在每次 `_infer()` 前后清空）即可保证在 `propagate`、`correct_points` 及 `RecoveryCandidate` 共享同一 `model` 时 100% 安全且零残留显存占用。
   - 在 `memory_attention` 和 `spatial_perceiver` 的局部作用域内启用 `torch.autocast("cuda", dtype=torch.float16)` 与 `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH])`，并在出口 `.float()` 转回 FP32（与下游 `mask_decoder`、FP32 权重和 `prune_video_session` 完全无缝兼容）。

```python
# 示例：EdgeTamTracker 中针对 CUDA/HIP 的局部加速包装（不改变 HF 官方 session/mask API 语义）
# 注意：请在 EdgeTamTracker._infer() 的 try ... finally 中于每次前向前后调用 layer0_cache.clear()，
# 避免跨帧或跨 session/RecoveryCandidate 复用同一 data_ptr() 导致命中陈旧缓存。
def _wrap_edgetam_cuda_modules(model):
    import torch
    from torch.nn.attention import SDPBackend, sdpa_kernel

    ma = model.memory_attention
    sp = model.spatial_perceiver
    orig_ma_forward = ma.forward
    orig_sp_forward = sp.forward
    layer0_cache = {}

    def fast_ma_forward(
        current_vision_features,
        memory,
        current_vision_position_embeddings=None,
        memory_posision_embeddings=None,
        num_object_pointer_tokens=0,
        num_spatial_memory_tokens=-1,
    ):
        with torch.autocast("cuda", dtype=torch.float16), sdpa_kernel(
            [SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH]
        ):
            key = (
                current_vision_features.data_ptr(),
                current_vision_position_embeddings.data_ptr()
                if current_vision_position_embeddings is not None
                else 0,
            )
            cached = layer0_cache.get(key)
            if cached is None:
                layer0_cache.clear()
                out0 = current_vision_features
                if current_vision_position_embeddings is not None:
                    out0 = out0 + 0.1 * current_vision_position_embeddings
                out0 = out0.transpose(0, 1)
                rope_pe = ma.rotary_emb(out0, ma.position_ids)
                rope_pe_k = ma.rotary_emb(out0, ma.position_ids_k)
                q0 = out0.unsqueeze(1) if out0.ndim == 3 else out0
                layer0 = ma.layers[0]
                q_norm = layer0.layer_norm1(q0)
                q_sa, _ = layer0.self_attn(
                    query=q_norm, key=q_norm, value=q_norm, position_embeddings=rope_pe
                )
                q_after_sa = q0 + layer0.dropout1(q_sa)
                q_ln2 = layer0.layer_norm2(q_after_sa)
                cached = (q_after_sa, q_ln2, rope_pe, rope_pe_k)
                layer0_cache[key] = cached
            q_after_sa, q_ln2, rope_pe, rope_pe_k = cached
            mem = memory.transpose(0, 1).unsqueeze(1)
            mem_pe = memory_posision_embeddings.transpose(0, 1).unsqueeze(1)
            layer0 = ma.layers[0]
            q_ca, _ = layer0.cross_attn_image(
                query=q_ln2,
                key=mem + mem_pe,
                value=mem,
                position_embeddings=rope_pe,
                position_embeddings_k=rope_pe_k,
                num_k_exclude_rope=num_object_pointer_tokens,
                rope_k_repeat=num_spatial_memory_tokens,
            )
            queries = q_after_sa + layer0.dropout2(q_ca)
            output = queries + layer0.dropout3(layer0.mlp(layer0.layer_norm3(queries)))
            for layer in ma.layers[1:]:
                output = layer(
                    queries=output,
                    keys=mem,
                    key_point_embedding=mem_pe,
                    rope_position_embeddings=rope_pe,
                    rope_position_embeddings_k=rope_pe_k,
                    num_k_exclude_rope=num_object_pointer_tokens,
                    rope_k_repeat=num_spatial_memory_tokens,
                )
            return ma.layer_norm(output).transpose(0, 1).float()

    def fast_sp_forward(hidden_states, positional_encoding=None):
        with torch.autocast("cuda", dtype=torch.float16), sdpa_kernel(
            [SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH]
        ):
            latents, pos = orig_sp_forward(hidden_states, positional_encoding)
            return latents.float(), (pos.float() if pos is not None else None)

    ma.forward = fast_ma_forward
    sp.forward = fast_sp_forward
    return orig_ma_forward, orig_sp_forward
```

*(注：推荐在 `EdgeTamTracker._infer()` 内用 `try ... finally` 清空 `layer0_cache`，将缓存严格限定在同一次 `_infer()` 调用的 `N` 个对象之间复用，不跨帧、不跨 `RecoveryCandidate` 保留张量引用。)*

### 5.2 `application/session.py`：解除停用 Facing 时的 `TaskWorker` 空转锁步阻塞
- 在 `MatchSession.advance()`（或 `schedule()` 之前）检查：当 `not self.model_failed` 且 **`self.worker.facing is None`（或 `not self.data.rules.track_facing` / 无 `facing_references`）** 时，一旦 `self.trays.take_ready()` 返回已完成结果，**直接在主循环里调用 `self._accept_geometry(request, prediction, None)` 完成几何提交并释放 `self.trays` 进入下一批**，无需等待 `self.worker.busy == False` 去排队跑空操作 `"facing"`。
- 效果：`TrayWorker` 算完一帧（`~50–150 ms`）后即可立即被接受并上屏/写入历史，再也不会被下一帧 `propagate` 卡住整整一个推理周期。
