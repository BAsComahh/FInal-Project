# 单位注册与 reference

本组件管理本局单位表、mask 绑定、reference 提取及最终快照保存，不依赖 SAM 或前端窗口。SAM 输出的对象编号通过 `UnitRoster` 绑定为 A1／A2／B1 等本局单位编号。

```python
from components.registration import UnitRoster, extract_references, save_registration

roster = UnitRoster.load("inputs/units.example.json")
roster.bind(1, "A")  # A1
roster.bind(2, "A")  # A2
references = extract_references(frame, prediction, source=metadata, roster=roster)
folder = save_registration(frame, overlay, references, metadata, "outputs/sam3_registration", roster=roster)
```

输入单位表只需 types；实例及数量在标注时生成，每种 type 单独计数。换绑或移除单位释放编号，其他单位不重排。重复绑定同 type 保留原编号。草稿的点提示及绑定在工作流内存中维护，S 或首次播放完成注册后锁定；暂停不开放修改，R 开始新注册。

```json
{
  "unit_types": [
    {"type_id": "A", "dimension": {"width_mm": 100, "depth_mm": 80}, "attributes": {}},
    "B"
  ]
}
```

尺寸值仅展示格式，需换成本局实测值。同 type 尺寸一致，属性随 reference 保存，界面只展示类型与编号。尺寸可选；毫米托盘拟合要求尺寸和相应标定均存在。

`UnitRoster.with_dimensions({type_id: {"width_mm": 100, "depth_mm": 80}})` 返回经过完整校验的新目录，保留实例 ID、属性、绑定、计数与来源；值为 `None` 时移除该 type 的尺寸，未知 type 或无效尺寸会拒绝整次修改。原目录不被修改，`snapshot()` 与实例 `annotation()` 均读取新尺寸。Qt 注册从 PDF 推导或目录读取尺寸，随最终注册保存。

## 双军表与分方编号

`UnitRoster.with_list("A" 或 "B", payload, source=...)` 返回替换该方的新 roster，在修改原对象前完成验证。该方记录重新编为 A1、A2…／B1、B2…，含 `list_id`、`type_number`、`source_type_id`，属性 `side` 按所选按钮写为 A／B。多方合并 JSON 会被拒绝作为单方导入。`payload.lists` 保存两方各自的来源及原目录元数据。

新 roster 仅继承另一方的实例、属性、绑定和计数；被替换一方需要重新绑定。对分方类型，A1 的实例为 A1.1／A1.2，B1 的实例为 B1.1；普通旧类型 A 仍使用 A1／A2。撤回／解除绑定继续释放本类型编号，不重新排序其他实例。原军表 `listed_count` 不限制注册数量。

桌面侧栏的两列和两个导入按钮调用此接口；PDF 直接交给下述 reader，JSON 用现有 catalog 校验。文件取消或解析失败不替换 roster，模型准备期间也可先导入。分割 mask、SAM 提示和会话继续沿用；首次播放后导入锁定，R 重置绑定但保留两个来源目录。

## PDF 军表 reader

`pdf_reader.py` 首版读取 Mantic Companion 导出的文字层军表，已用本项目两份 2026 US Masters PDF 实跑核对。使用 pypdf，不调用模型、OCR 或外部 PDF 命令。其他排版或扫描版不保证支持，无法识别或合计不一致时报错。

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.read_unit_list inputs/army_lists/us_masters_2026/Ryan_Lampien_Elves.pdf --sides Red --output outputs/unit_lists/ryan_lampien.json
```

可一次读取双方军表；`--sides` 顺序对应输入 PDF，不指定时 `side` 保持未知：

```powershell
conda run --no-capture-output -n sam3-demo python -m tools.read_unit_list inputs/army_lists/us_masters_2026/Sam_Moore_Northern_Alliance.pdf inputs/army_lists/us_masters_2026/Ryan_Lampien_Elves.pdf --sides Blue Red --output outputs/unit_lists/masters_2026.json
```

导出 JSON 可由 `UnitRoster.load` 或前端参数载入；普通界面操作可直接使用 `Import list A`／`Import list B` 选择 PDF 或单方 JSON，无需先转换文件。独立 CLI 转换不会替换运行中的名单。多方合并 JSON 可供独立接口使用，分方按钮每次只接受单方名单。重新导入该方时重新核对 mask 绑定，不能把旧 type 编号直接视为新军表对应。

```python
from components.registration import read_unit_list_pdf, read_unit_list_pdfs, UnitRoster

catalog = read_unit_list_pdf("army.pdf", side="Blue")
# catalog = read_unit_list_pdfs(["blue.pdf", "red.pdf"], sides=["Blue", "Red"])
roster = UnitRoster(catalog)
```

每个 type 含 `unit_name`、`formation`、`classification`、完整属性、`listed_count` 及 `source_entries`。后者保留来源索引、页码、行号、原始标题／属性／配置行。`sources` 保存 PDF 的路径、标题、SHA-256 和已核对的单位数、积分、Unit Strength；`summary` 为合并后的合计。

- 相同来源、相同属性及配置的条目合并；编制、装备、法术选项或属性不同则分别编号。同名的 Horde 和 Regiment 不合并。
- `listed_count` 只是原军表数量，不预先产生实例，也不限制注册数量；单位标题的 `[2]` 不作为数量。
- 属性键包含 `speed_in`、`melee`、`shooting`、`defence`、`unit_strength`、`attacks`、`nerve`、`height`、`points`、`unit_kind`、`side`、`special_rules`、`traits`、`options` 和 `weapons`。命中／防御的 `4+` 等保留字符串，缺失横杠转 `null`。
- `options` 保存带积分明细的原始名称；末尾 `(n)` 保存为 `value`，不凭它推断规则效果。`weapons` 读取明确写出的武器英寸射程；第二页的法术／特殊规则释义不转成可执行规则。
- 属性行的 Pts 已包含配置花费；合计只求和属性行，不重复加上明细积分。总单位数、积分和 Unit Strength 任一不符均停止导出。
- PDF 导入自动填充 `dimension.width_mm/depth_mm`（正面宽×深）：明确的毫米底座备注优先，其次按单位类别＋编制查 [官方 FAQ v0.1 首页面尺寸表](https://www.manticgames.com/wp-content/uploads/2026/02/KoW-v4-FAQ-v1.0.pdf)。支持 Inf／Lrg Inf／Cav／Lrg Cav、Hero 的单模型尺寸及明确的 Heavy／Monstrous／Titan 变体；不按名字猜变体。表中 n/a、未知类别、无法解析或相互冲突的底座备注保持无尺寸并逐 type 警告。没有明确尺寸的 War Engine／Legion 不套用其他编制。
- 底座备注支持 `Base Size: 75mm`、`Base Size (125x100mm)`、`Unit Footprint: 100 × 80 mm`、`75mm Base` 等明确声明；单个毫米值表示方形。`dimension_inference` 保留导入时原尺寸、方法、分类／编制及规则 URL／版本／页码或原始备注，修改当前 `dimension` 后该导入证据仍保留。Qt 已移除手动尺寸入口，只从 PDF／目录取得尺寸；旧 OpenCV 编辑窗口和共享尺寸更新接口保留。旧 JSON 不自动重算，请重新导入原 PDF 取得映射。
- 动态状态不补值。未处理的详情行保留到 `unparsed_details` 并警告。解析出特殊规则不表示规则引擎已支持它。

当前两个样本分别得到 Sam 的 13 条选兵记录／10 个 type／2300 分／US 25，以及 Ryan 的 15 条／11 个 type／2300 分／US 27。两份合并为 28 条／21 个 type；这只验证这两份样本，不代表任意军表的读取准确率。

文字层读取参考 [pypdf 官方文档](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。原始军表及来源见 [本局资料](../../inputs/army_lists/us_masters_2026/README.md)。

`extract_references` 接收与 mask 完全配套的 BGR 帧及 `object_ids`／布尔 `masks`，返回独立复制的全帧 mask、xyxy 裁剪框、BGR crop、BGRA cutout 和 source 元数据。空 mask 保留尺寸和记录，不生成 crop／cutout。加载单位表时，所有保留对象必须已经绑定 type。

`save_registration` 验证叠加图与帧尺寸匹配，先将全部文件写入临时目录，再发布为 `frame_<标识>/`。写入失败清理半成品，不锁定草稿；工作流成功后记录目录，重复完成不会创建副本。

```text
frame_<标识>/
  frame.png                 与 mask 配套的完整拉正帧
  overlay.png               同帧叠加图
  prompts.json              提示、帧号、Homography、原图桌角及坐标空间
  scene.json                有尺度与已绑定单位时的初始规则场景
  units.json                单位表、实例、编号计数和 mask 绑定
  instances.json            对象及 selection 路径清单
  object_001/
    mask.png                全帧二值 mask
    crop.png                保留背景的裁剪图；空 mask 不生成
    target.png              mask 作为 alpha 的透明切图；空 mask 不生成
    selection.json          边框、单位信息、来源和文件路径
```

视频前端的 source 使用 `rectified_table_pixels`，保留原视频帧号／时间、原图大小及正反 Homography；`table_boundary` 中的桌角使用 `source_image_pixels`。实例 ID 仅在本局有效，不能把不同比赛的 A1 当作同一对象。

注册提示同时保留模型输入用的 `point` 与原视频锚点 `point_source`。托盘／历史使用 `corners_source`／`center_source`，地形为 `polygon_source`，正面为 `source_ray`；规则场景统一经当前 `source_to_plane` 投影到毫米。reference 的 mask、裁剪边框和输入点仍属于其配套拉正帧，不将这些图像局部坐标直接当作原视频像素。注册期重载标定后的托盘重算保留原观测帧／时间，并更新其坐标版本。

`rule_state.py` 维护人工正面和地形记录，使用已拟合的毫米托盘构建规则场景；每实例属性覆盖 type 默认值。规则字段为 `speed_in`、`height`、`side`、`unit_kind`、`special_rules`、`engaged` 和 `wavering`，缺失值保留未知，不从旧 `movement` 字段猜测单位。规则 Height 不是模型物理高度。后续矩形正面属于连续性估计，不是方向识别或 ID 恢复。规则引擎与支持范围见 [game_rules](../game_rules/README.md)。

`save_references` 是显式调用的底层样本导出接口。DINO 特征计算和样本采纳属于后续组件，提取 reference 不会自动更新向量。操作与启动方式见 [前端说明](../../frontend/README.md)。
