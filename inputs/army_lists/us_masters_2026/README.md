# 2026 US Masters — Sam Moore / Ryan Lampien

原始公开军表，获取日期：2026-10-31。

| 选手 | 军队 | 单位数 | 总积分 | 原始 PDF |
| --- | --- | --- | --- | --- |
| Sam Moore | Northern Alliance（北方联盟） | 13 | 2300 | [Sam_Moore_Northern_Alliance.pdf](Sam_Moore_Northern_Alliance.pdf) |
| Ryan Lampien | Elves（精灵） | 15 | 2300 | [Ryan_Lampien_Elves.pdf](Ryan_Lampien_Elves.pdf) |

来源为选手本人发表的 [The Sams go to Masters](https://honest4s.com/posts/first-masters-experience/)，其中同时链接两份军表，并记录双方在直播中进行 Control 对局。Sam 的 PDF 内部标题为 `We have orc at home`，选手身份由其本人文章中的链接确定。Ryan 的军表也由 [Counter Charge 868](https://www.countercharge.net/counter-chargeccx/868) 链接。

原始下载链接：[Sam](https://honest4s.com/lists/Sam_Moore_-_Northern_Alliance_-_Northeast.pdf)、[Ryan](https://honest4s.com/lists/Ryan_Lampien_-_Elves_-_West.pdf)。来源、SHA-256 与文件基本信息保存在 [sources.json](sources.json)。选手复盘将该场称为 Game 4，本地视频字幕为 Game 3；保留这一编号差异，双方姓名、阵营及 Control 场景吻合。

军表包含兵种名、编制、类别、Sp（移动速度）、Me（近战命中）、Sh（射击命中）、De（防御）、US（单位强度）、Att（攻击次数）、Ne（士气）、Ht（规则高度）、Pts（积分），并列出装备、法术与特殊规则。Sam 的版本未附完整特殊规则释义，Ryan 的第二页附有部分释义。

后续导入时需要保留同名单位的不同编制和配置，例如 Palace Guard 的 Horde／Regiment，以及同一 Horde 是否带 Chant of Hate。标题中的 `[2]` 不能直接当作本局数量，例如 `Army Standard Bearer [2]` 实际只有一条所选单位记录；应按属性条目计数并核对 `Total Units`。这些 PDF 没有直接给出托盘毫米尺寸。

桌面注册界面通过 `Import list A`／`Import list B` 分别直接选择两份 PDF，即可显示两方类型并手动对应 mask。独立命令 `python -m tools.read_unit_list` 仍可将一份或多份 PDF 转为 JSON，详见 [reader 用法](../../../components/registration/README.md#pdf-军表-reader)。导入不自动识别画面对应，PDF 未给出的托盘毫米尺寸仍需补充。
