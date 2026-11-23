# 交接文档：EdgeTAM 推理速度慢与端到端延迟排查结论（2026-11-18）

> **用途**：供后续会话或接手人直接开展优化开发与实机验证。本文汇总了 2026-11-15 Gemini CLI 会话排查记录、2026-11-18 真实录播数据库与诊断日志统计、AMD Radeon RX 7900 XT 控制变量基准（含被否决的无效/高误差方向），以及面向代码修改的完整避坑清单与验收要点。  
> **当前仓库状态**：`HEAD = 105087a`（工作树干净，生产代码尚未做本轮加速改动）；此前从 Gemini CLI 拷入排查的临时目录 `final-project/` 已清理；详细实验附表另见 [edgetam-inference-speed-analysis.md](edgetam-inference-speed-analysis.md)。

---

## 一、背景与已确认现状

### 1.1 Gemini CLI 会话恢复与限流原因（已完结）
- 原 Gemini CLI 会话 `fe4d99d5-525d-492d-bbee-b32567337fa0`（2026-11-15 长会话）在 2026-11-18 `/resume` 时基础上下文已达 `309,900` tokens 且跨天服务端缓存失效（`cached: 0`）；随后 4 轮工具调用在 5 分钟内累计发送约 `1.58M` 未缓存 input tokens，触发模型限流并重试超时报错。
- 该会话内所有有效实验信息已完整提取至本文与 [edgetam-inference-speed-analysis.md](edgetam-inference-speed-analysis.md)，临时目录已删除。

### 1.2 长跑崩溃已根治，但实盘速度仍未达预期
- **稳定性已验证**：2026-11-15 修复（commit `0e53cb5`：`bind_cuda_device`、单帧视觉特征留 GPU、输出改用 `non_blocking=False` 可分页内存、按 HF `5.18.0` 真实窗口 `6` 空间帧 + `15` 指针裁剪会话）后，最新 30 对象长局 `frame_6b59223eebc5` 从 `3000.0s` 连续运行到 `4529.2s`（**25.5 分钟、772 条观测**）零崩溃，稳态会话内存恒定为 `cpu_mib: 80.25, gpu_mib: 100.5, pinned_mib: 0.0`。
- **实盘速度仍存在的两个突出问题**：
  1. 虽然 `DEFAULT_INFERENCE_FPS = 1.0`（目标步距 `1.0s`），且 11-15 曾测得 `519.1 ms/帧` 微基准，但 **11-18 实盘每步传播间隔（`obs_dt`）依然高达 `1.5s ~ 1.7s`（均值 `1.74s ~ 2.15s`）**；
  2. 11-15 之后引入异步 `TrayWorker` 后，**端到端几何延迟（`e2e_lat` = 业务接纳写入时间 − 采样帧时间）翻倍至 `3.0s ~ 3.6s`（P90 达 `4.4s`）**，并在多物体遮挡闪烁时出现 `10s ~ 33s` 的 `observation` 记录空洞。

---

## 二、5 场真实录播数据对比（`outputs/sam3_registration/`）

从各场次 `history.sqlite3`（`observations` 表）与 `runtime_diagnostics.jsonl` 提取的实测指标（硬件均为主机独显 `AMD Radeon RX 7900 XT`）：

| 场次归档 | 对象数 | 分辨率 | 代码状态 / 条件 | `obs_dt`（传播间隔）中位 / 均值 / P90 | `e2e_lat`（端到端几何延迟）中位 / 均值 / P90 | 稳态会话内存 |
| :--- | :---: | :---: | :--- | :---: | :---: | :--- |
| `frame_83cdb0ce313e` (483 obs) | 28 | `1533×1023` | `b79f83b`（11-15 前）：线程默认 `cuda:0` 核显回退 `MATH`，无界锁页内存（508 步崩溃） | **0.633s** / 0.681s / 0.750s | **0.617s** / 0.693s / 0.717s | ~7.1 GiB 锁页崩溃 |
| `frame_3fe3022f7627` (135 obs) | 28 | `1533×1023` | 11-15 修崩溃后（`set_device(1)` `gfx1100` 触发慢速 `EFFICIENT`，尚未加 `MATH`） | **1.483s** / 1.493s / 1.517s | **1.467s** / 1.494s / 1.500s | `cpu: 75.0, gpu: 100.47, pinned: 0.0` |
| `frame_d07270f7feba` (647 obs) | 26 | `1526×1017` | `0e53cb5..105087a`：`SDPBackend.MATH` + `FPS=1.0`，`cond_frames: 1→4`，`cands: 0→1` | **1.500s** / 1.742s / 2.083s | **3.017s** / 3.121s / 3.667s | `cpu: 70.0, gpu: 100.5, pinned: 0.0` |
| `frame_1afbbc55a210` (1099 obs) | 26 | `1526×1017` | `105087a`，`cond_frames: 1→4` | **1.600s** / 1.921s / 2.433s | **3.217s** / 3.312s / 3.950s | `cpu: 70.0, gpu: 100.5, pinned: 0.0` |
| `frame_6b59223eebc5` (713 obs) | 30 | `1528×1019` | `105087a`，连续 25.5 分钟，`cond_frames: 1→4`，`cands: 0→1` | **1.700s** / 2.148s / 2.467s | **3.450s** / 3.617s / 4.400s | `cpu: 80.25, gpu: 100.5, pinned: 0.0` |

补充说明（来自 `runtime_diagnostics.jsonl`）：
- **`frame_d07270f7feba`（26 对象）**：初始 `cond_frames=1, cands=0` 时 30 步平均墙钟耗时为 `1.376s ~ 1.406s`；恢复提交后 `cond_frames` 增至 `3~4` 且 `cands=1` 时升至 `1.54s ~ 1.90s`。
- **`frame_6b59223eebc5`（30 对象）**：`cond_frames=1, cands=0` 时为 `1.60s ~ 2.11s`；`cond_frames=4, cands=1` 时升至 `1.99s ~ 2.26s`。

---

## 三、四大根因结论（已通过源码、日志与 CUDA Event 实测证实）

### 根因 A：11-15 `519.1 ms` 微基准低估了满窗口稳态耗时，核心瓶颈是单头 `head_dim=256` 的 FP32 注意力
1. **满记忆窗口下的真实独立前向耗时就是 `1.15s ~ 1.19s`**（在 RX 7900 XT 上对 `frame_6b59223eebc5` 30 对象实测）：
   - 11-15 测试仅预热 `step 0..3`，尚未填满 `6` 帧空间记忆和 `15` 帧对象指针；
   - 真实 30 对象逐帧递增：`step 1 = 928.3 ms` → `step 6 = 1136.1 ms` → `step 7..18`（稳态）**`1180.8 ~ 1194.1 ms`**；
   - 重新运行 11-15 的 28 对象合成脚本，`step 4..6` 也达 `1022.4 ms/帧`、`step 7..10` 达 `1118.2 ms/帧`。
2. **CUDA Event 算子拆解（`frame_6b59223eebc5`, 30 对象, Step 8, `FP32 MATH`）**：
   - **`memory_attention`（30 对象 × 2 层 = 60 层）= `775.6 ms`（占 67.3%）**：
     - `self_attn` SDPA `[1, 1, 4096, 256]`（60 次）：`272.9 ms`（若用 `FP32 EFFICIENT` 则暴涨至 `539.5 ms`）
     - `cross_attn` SDPA `[1, 1, 4096×3616, 256]`（60 次）：`245.1 ms`（若用 `FP32 EFFICIENT` 则暴涨至 `472.0 ms`）
     - 线性投影 + MLP + LayerNorm（60 层）：`~248.5 ms`；2D RoPE（120 次）：`9.1 ms`
   - `_encode_new_memory`（30 对象）：`206.0 ms`（17.9%）
   - `mask_decoder`（30 对象）：`89.9 ms`（7.8%）
   - `_build_memory_attention_inputs` + `_process_object_pointers`（30 对象）：`41.2 ms`（3.6%）
   - `_prepare_vision_features`（每帧 1 次 RepViT + FPN）：`18.1 ms`（1.6%）
   - 处理器前后处理 + 存储 + 会话裁剪：`~35 ms`（3.0%）
3. **实盘进一步从 `1.18s` 拖到 `1.5s ~ 2.2s` 的叠加项**：
   - **恢复写入永久条件帧（`cond_frames: 1 → 4`）**：每次自动/手动 `update_mask` 都新增 1 个永久条件帧，给全部 30 个对象的 `cross_attn` 各增加 `+512` 空间 token + `+4` 指针（`k` 从 `3,616` 增至 `5,164`），约 **`+120 ~ 160 ms/帧`**；
   - **待审核恢复候选（`cands = 1`）**：`TaskWorker._run` 在每次 `propagate` 中串联推演第二个隔离 `EdgeTamTracker` 会话（如 `frame_6b59223eebc5` 从 `4310s` 到 `4529s` 持续存在），约 **`+100 ~ 180 ms/帧`**；
   - **Qt 播放线程 GIL/CPU 竞争**：HF 循环每帧派发 ~3,500 次 Python PyTorch 调用，与 60 FPS 解码+透视变换、`TrayWorker`、`BoardRenderer`（`qt-overlay`）争抢 GIL，约 **`+150 ~ 250 ms/帧`**。

### 根因 B：`memory_attention.layers[0]` 自注意力被无意义地重算 30 遍（纯浪费 `~168 ~ 178 ms/帧`）
- `EdgeTamVideoModel.forward` 对 30 个对象串行循环调用 `memory_attention`，而 `layers[0]` 的前半段（`current_vision_features + 0.1 * pos` → `rotary_emb` → `layer_norm1` → `self_attn` `[1, 1, 4096, 256]` → 残差 → `layer_norm2`）**完全不依赖对象或历史记忆**，在同帧内对 30 个对象输入完全相同，却被重复计算了 30 次。

### 根因 C：会话状态留在 CPU 并强制 `non_blocking=False` 同步拷贝（额外拖慢 `~69 ~ 88 ms/帧`）
- `prune_video_session` 已将非条件历史严格裁剪在 6 帧空间 + 15 帧指针；但 `initialize` 仍设 `inference_state_device="cpu"`，导致 `_store_output_pageable` 每帧执行 **60 次同步 GPU→CPU 流停顿**，下一帧又要把 **420 个张量**从可分页内存拷回 GPU。
- 改由推理 GPU 驻留（`inference_state_device = self.device`）：30 对象总显存仅从 `100.5 MiB` 增至 **`~163.5 MiB`**（在 20 GiB 显存中不足 1%，`pinned_mib = 0.0`），即使经历数次恢复新增条件帧也仅多占几十 MiB。

### 根因 D：`MatchSession` / `TrayWorker` → `TaskWorker("facing")` 串行锁步阻塞（使端到端延迟翻倍到 `3.0s ~ 3.6s` 且加剧闪烁丢帧）
问题位于 [application/session.py](../application/session.py) 第 276、310–330、440–448、555–556 行：
1. `propagate #k` 耗时 `> 1.0s`，结束时 `now >= self.next_inference_time` 已满足；
2. 同一轮 `advance()` 先调用 `_queue_geometry` 入队 `self.trays.pending`，第 555 行 `self.trays.start(...)` 启动 CPU 拟合，**0.1 ms 后**第 556 行 `self.schedule(now)` 见 `trays.take_ready()` 尚未完成、而 `next_inference_time` 已到期，于是**立即向 `TaskWorker` 提交 `propagate #(k+1)`**（使 `self.worker.busy = True`）；
3. `TrayWorker` 在 CPU 上只需 ~50–150 ms 就完成了第 `#k` 帧拟合，但结果必须等 `self.worker.busy == False` 后再在 `schedule()` 第 310 行提交为 **`TaskWorker("facing")`** 任务，才能到达 `_accept_geometry` 落盘——**即便当前 `FACING_TRACKING_ENABLED = False`（`self.worker.facing is None`，`"facing"` 是纯空操作）！**
4. 结果：第 `#k` 帧的托盘必须死等 `propagate #(k+1)` 完整跑完（`+1.5s`），且在此期间第 `#(k+1)` 帧也无法启动 `TrayWorker`，导致 `obs_ts[k+2] == acc_ts[k] + 0.02s`（延迟固定翻倍到 `3.0s ~ 3.6s`）。
5. **连锁副作用（解释长跑 `10s ~ 33s` 观测空洞）**：当遮挡导致下一帧 `visible != self._geometry_visible` 时，`_queue_geometry`（第 442 行）调用 `self.trays.invalidate(...)` 全局递增 `self.trays.epoch`；因为上一帧结果还被卡在 `self.trays.future` 中没能通过 `"facing"` 交付，一旦连续几帧发生单位可见性闪烁（如 `frame_6b59223eebc5` 第 758–764 条连续 7 条 `tracking_gap`），已算好的整帧托盘几何会在交付前被连环作废丢弃。

---

## 四、已验证的优化效果与被否决方案（RX 7900 XT 实测）

### 4.1 底层 SDPA 算子微基准（EdgeTAM 真实单头形状 `[1, 1, 4096, 256]` & `[1, 1, 3616, 256]`，各 60 次）
- `FP32 EFFICIENT`：`539.2 + 475.0 = 1014.2 ms`（最慢）
- `FP32 MATH`（当前基线）：`281.4 + 253.7 = 535.1 ms`
- `FP16 MATH`：`288.7 + 255.8 = 544.5 ms`
- **`FP16 EFFICIENT / FLASH`：`42.7 + 36.6 = 79.3 ms`（快 6.75×）**
- **`BF16 EFFICIENT / FLASH`：`41.2 + 35.8 = 77.0 ms`（快 6.95×）**

### 4.2 30 对象端到端单帧传播实测对比（`frame_6b59223eebc5`，Step 8，RX 7900 XT）

| 测试方案 | 30 对象耗时 | 加速比 | 前景差异像素 (`diff_px / 179,310`) | 最大 logit 差 | 结论 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 当前基线（`FP32 MATH` + CPU 状态） | **1152.5 ms** | 1.00× | 0 (`0.000%`) | `0.00e+00` | 基线 |
| 仅复用 `Layer 0` `self_attn`（`FP32 MATH` + CPU） | **973.9 ms** | 1.18× | 0 (`0.000%`) | `0.00e+00` | 数学零误差 |
| 复用 `Layer 0` + GPU 会话状态（`FP32 MATH`） | **904.9 ms** | 1.27× | 0 (`0.000%`) | `0.00e+00` | 数学零误差 |
| 复用 `Layer 0` + 仅 SDPA `FP16` + GPU 状态 | **560.4 ms** | 2.06× | 3 (`0.0017%`) | `9.92e-04` | 已很显著 |
| 复用 `Layer 0` + `memory_attention` `FP16` autocast + GPU 状态 | **382.0 ms** | **3.02×** | 9 (`0.0050%`) | `1.44e-03` | 极佳 |
| **复用 `Layer 0` + `memory_attention` & `spatial_perceiver` `FP16` autocast + GPU 状态** | **372.8 ms** | **3.09×** | **9 (`0.0050%`)** | **`1.44e-03`** | **推荐主方案** |

### 4.3 已证实无效或不可取的方案（交接避坑，勿重复踩坑）
1. **不要直接改用 `Batch=30` 跨对象批处理（`1 × B=30`）**：
   - 实测 `FP32 MATH` 下 `1159.7 ms` vs 串行 `1151.8 ms`（**零提速**），且当各对象条件帧数量或输入不同时无法直接对齐；此外 `object_score_logits` 还出现了 `max_logit_diff = 4.61` 的偏差风险。
2. **不要在整模型外层直接套全局 `torch.autocast("cuda", ...)`**：
   - Windows ROCm 上 RepViT / FPN / MaskDecoder / MemoryEncoder 中的 `Conv2d` 在 `autocast` 下会触发 MIOpen 慢速搜索/回退：整模型 `FP16 autocast` 耗时 **`2160.3 ms`**、整模型 `BF16 autocast + EFFICIENT` 耗时 **`3120.6 ms`**（比基线慢 2~3 倍）。
   - 必须把 `torch.autocast("cuda", dtype=torch.float16)` + `sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH])` **严格限定在 `memory_attention` 与 `spatial_perceiver` 内部**，并在模块出口 `.float()` 转回 FP32。
3. **不要用 `BF16` 替代 `FP16`**：
   - `BF16` 只有 8-bit 尾数，在 30 对象实测中前景像素差异高达 `1,275 ~ 1,277 / 179,310`（`0.71%`）；而 `FP16`（11-bit 尾数）+ HF 内置 RoPE 的 `.float()` 升精度仅 **`9 / 179,310`（`0.005%`）**。
4. **不要试图把 EdgeTAM 记忆槽 `num_maskmem` 从 7 扩到 8~10**：
   - `maskmem_tpos_enc` 预训练参数形状固定为 `(7, 1, 1, 64)`，扩槽会破坏预训练时序位置编码并线性增加计算量。

---

## 五、下一步修改建议与关键工程细节（给接手实现者）

### 5.1 修改 [components/tracking/edgetam.py](../components/tracking/edgetam.py)
1. **有界 GPU 状态驻留**：
   - 仅当 `self.device` 为 CUDA/HIP（`torch.device(self.device).type == "cuda"`）时，在 `initialize()` 中传 `inference_state_device=self.device`（或解析后的 `torch.device(self.device)`），纯 CPU 环境仍保留 `"cpu"`。
   - 顺手修正 `prune_video_session` 第 121、139 行的设备比较：用 `tv.device != torch.device(state_device)` 替代 `str(tv.device) != str(state_device)`，避免传入 `"cuda"` 时与 `"cuda:0"` 字符串不匹配而无谓 `.clone()`。
2. **局部模块加速包装（`memory_attention` & `spatial_perceiver`）**：
   - 仅在 CUDA/HIP 设备下生效；在 `EdgeTamTracker._infer()` 内（而非模块持久跨帧状态）维护 `layer0_cache`，**在每次 `_infer()` 开始与结束（`finally`）都必须 `layer0_cache.clear()`**。
   - **关键原因（两个必须注意的坑）**：
     1. `session.cache` 的 `max_vision_features_cache_size = 1` 会在计算下一帧前弹出旧帧特征，PyTorch CachingAllocator **常将相同 GPU `data_ptr()` 复用于下一帧特征**，因此绝不可跨帧按 `data_ptr()` 缓存；
     2. `RecoveryCandidate`（[components/tracking/recovery.py](../components/tracking/recovery.py) 第 22、61 行）通过 `copy(tracker)` **浅拷贝共享同一个 `tracker.model`**；在 `_infer()` 的 `try ... finally` 中清缓存既能让主会话 30 对象共享 `Layer 0`，也能确保主会话、`RecoveryCandidate`（1 对象）、`initialize`、`update_mask`、`correct_points` 互不串扰、且帧间不残留显存张量。
   - 在局部 `autocast` 外保留现有 `EdgeTamTracker._infer` 对非 CUDA 回退的 `nullcontext()`，避免在 CPU 上调用 `torch.autocast("cuda", ...)` 报错；对于 CUDA 设备，不再在外层强制全局 `SDPBackend.MATH`，改由局部包装器在 `memory_attention` 与 `spatial_perceiver` 内切换 `[EFFICIENT_ATTENTION, FLASH_ATTENTION, MATH]`（其他模块保留默认或 MATH）。

### 5.2 修改 [application/session.py](../application/session.py)
1. **解除停用 `facing` 时的 `TaskWorker("facing")` 阻塞**：
   - 先核对 [application/task_worker.py](../application/task_worker.py#L398-L431)：当 `self.worker.facing is None`（当前 `FACING_TRACKING_ENABLED = False` 的默认态）或无 `facing_references` 时，`"facing"` 任务在 `TaskWorker._run` 中除了复制返回和记录耗时外不做任何方向计算；而 `worker_operation` 与 `tray_fit` 耗时字段已分别由 `propagate` 与 `TrayWorker._fit` 写入 `prediction["timings_seconds"]`。
   - 因此在 `MatchSession.advance()` 中（**放在第 555 行 `self.trays.start(...)` 之前**，且独立于 `self.worker.busy`），当 `not self.model_failed` 且不需要运行方向评估（即 `self.worker.facing is None or not self.worker.facing_references`）时，直接轮询 `if (ready := self.trays.take_ready()) is not None:`：
     - 校验 `request.get("generation") == self.generation`，若一致则直接调用 `self._accept_geometry(request, prediction, None)`；若过期则 `self.trays.accept(request, valid=False)`。
   - 效果：`TrayWorker` 算完一帧（50–150 ms）立即完成交付并释放 `self.trays.future`，同 tick 内第 555 行立刻可以排下一批；**端到端延迟从 `3.0s ~ 3.6s` 降至 `~0.55s ~ 0.65s`**，且大幅降低跨帧 `tracking_gap` 作废已算完几何的概率。

---

## 六、验证环境与项目规则提醒（交接必看）

1. **必须使用项目环境与物理独显**：
   - Python 路径：`C:\Users\vasco\miniconda3\envs\sam3-demo\python.exe`（沙箱内默认 `python` 是 `2.9.1+cpu`，无 GPU）。
   - 验证 GPU 时必须显式检查 `AMD Radeon RX 7900 XT`（沙箱内看不到 GPU 属正常限制，不可据此误判驱动损坏；在受批准的沙箱外运行实卡验证）。
2. **开发与文档约定（来自 [AGENTS.md](../AGENTS.md)）**：
   - 不新增专门的测试文件，使用内联脚本和实机视频检查（涵盖：30 对象连续传播耗时与 `diff_px`、超过 16 帧窗口的内存 `cpu_mib / gpu_mib / pinned_mib`、同帧/跨帧 `update_mask` 恢复、`correct_points` 与 `RecoveryCandidate` 隔离传播、以及 `MatchApplication` 载入 `frame_6b59223eebc5` 短播确认端到端 `e2e_lat` 与 `history.sqlite3` 记录连续性）。
   - 修改完成后记得按 [AGENTS.md](../AGENTS.md) 同步更新根目录的 [TODO.md](../TODO.md) 与 [项目思路.md](../项目思路.md)。
