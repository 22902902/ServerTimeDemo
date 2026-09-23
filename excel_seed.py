# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 种子数据总入口
================================================================================
这里放三样东西，界面直接消费：

``CATEGORIES``      官方 12 个分类（与速查书章节对齐），左侧「函数宝典」树用
``LEARNING_PATHS``  七个学习阶段（能力阶梯），左侧「学习路径」用
``SEED_RECIPES``    20 条实战配方（组合套路），左侧「实战配方」用
``SEED_FUNCTIONS``  七个分片拼起来的函数库（191 条）

为什么阶段与配方要放在这一层而不是数据层
--------------------------------------------------------------------------------
它们是**教学设计**，不是你该编辑的数据 —— 顺序、分组、阶段目标都由这里定死。
放进数据库只会多出一张没人会改的表，还要处理「用户改了之后升级怎么办」。
所以它们是常量；而**掌握度、书页码、我的笔记**才是你的数据，那些进库。

三条硬约束（由 ``scripts/test_excel.py`` 守着）
--------------------------------------------------------------------------------
1. 每个 ``LEARNING_PATHS`` 里出现的函数名，库里都必须存在；
2. 每个 ``SEED_RECIPES`` 的 ``related`` 同理；
3. 每个函数条目的 ``related`` 同理 —— 界面上「相关函数」要能点。
"""

from __future__ import annotations

from excel_seed_date import SEED as _DATE
from excel_seed_extra import SEED as _EXTRA
from excel_seed_lookup import SEED as _LOOKUP
from excel_seed_math import SEED as _MATH
from excel_seed_misc import SEED as _MISC
from excel_seed_stat import SEED as _STAT
from excel_seed_text import SEED as _TEXT

# ======================================================================
# 官方 12 个分类（顺序即左侧树的显示顺序）
# ======================================================================
CATEGORIES = [
    {
        "name": "逻辑",
        "desc": "IF / IFS / SWITCH 与 AND / OR / NOT，一切公式的骨架。"
                "先把判断写对，后面所有函数都是往里面填内容。",
    },
    {
        "name": "数学与三角函数",
        "desc": "求和、取整、条件求和、SUMPRODUCT。"
                "日常 80% 的「算个数」都落在这里。",
    },
    {
        "name": "统计",
        "desc": "计数、平均、极值、排名、百分位、离散程度。"
                "报表里回答「多少个 / 多少平均 / 排第几」的那一类。",
    },
    {
        "name": "查找与引用",
        "desc": "VLOOKUP / INDEX / MATCH / XLOOKUP，"
                "以及全部动态数组函数。「把数据对起来」靠这一组，"
                "也是新手到高手的第一道分水岭。",
    },
    {
        "name": "文本",
        "desc": "截取、查找、替换、拼接、格式化。"
                "导入的脏数据九成都死在这里，清洗能力基本等于文本函数熟练度。",
    },
    {
        "name": "日期与时间",
        "desc": "日期本质是数字，时间是一天的小数。"
                "账期、工期、剩余天数、按月亮汇总都在这一组。",
    },
    {
        "name": "信息",
        "desc": "IS 系列与类型判断。看起来不起眼，"
                "但「区分真空与假空」「揪出文本型数字」这类判断只能靠它。",
    },
    {
        "name": "财务",
        "desc": "月供、利息与本金拆分、终值现值、收益率、折旧。"
                "最小的一组里含金量最高 —— 会算账和会 Excel 是两件事。",
    },
    {
        "name": "数据库",
        "desc": "D 系列老函数，靠「条件区域」工作。"
                "认识它就够了，新表请用 SUMIFS / FILTER 代替。",
    },
    {
        "name": "工程",
        "desc": "单位换算与进制、位运算。偶尔救命，平时用不上。",
    },
    {
        "name": "Web",
        "desc": "URL 编码等与链接打交道的小工具。",
    },
    {
        "name": "兼容性",
        "desc": "RANK / STDEV / PERCENTILE 这些被改名的老写法。"
                "看懂老文件、知道该换成哪个新名字用的。",
    },
]

# ======================================================================
# 七个学习阶段（能力阶梯）
# ======================================================================
# 设计原则：查找引用、动态数组、组合实战这「三关」占一半精力，
# 因为它们才是「会用」和「高手」的分水岭；其余阶段按性价比排。
# 推荐顺序是 L1 → L5 → L2/L4 → L3 → L6 → L7（见顶层 design 文档）。
LEARNING_PATHS = [
    {
        "key": "L1",
        "title": "地基 · 把表达式读对",
        "goal": "看懂一个公式在算什么，并写出第一个判断与第一个汇总。",
        "tip": "这一阶段不求多，只求「引用方式」和「条件写法」两件事形成肌肉记忆。"
               "重点理解相对引用与绝对引用（$）的区别 —— 后面所有公式下拉都靠它。",
        "codes": ["SUM", "AVERAGE", "COUNT", "COUNTA", "IF", "AND", "OR", "NOT",
                  "ROUND", "ABS", "INT", "MOD"],
    },
    {
        "key": "L2",
        "title": "文本与日期清洗",
        "goal": "把任何脏数据变成能算的数据：去空格、拆列、统一格式、转真日期。",
        "tip": "现实里拿到手的表八成是脏的，这一阶段决定你能不能开工。"
               "记住那条经验：看着一样却比不出来，先怀疑是文本。",
        "codes": ["TRIM", "CLEAN", "SUBSTITUTE", "VALUE", "TEXT", "LEN", "LENB",
                  "LEFT", "RIGHT", "MID", "FIND", "SEARCH", "REPLACE",
                  "TEXTAFTER", "TEXTBEFORE", "TEXTSPLIT",
                  "CONCAT", "TEXTJOIN", "UPPER", "LOWER", "PROPER", "CHAR", "EXACT",
                  "TODAY", "NOW", "DATE", "DATEVALUE", "YEAR", "MONTH", "DAY"],
    },
    {
        "key": "L3",
        "title": "查找与引用（分水岭一）",
        "goal": "任意两张表，都能按主键把字段对起来 —— 包括反向、多条件、区间匹配。",
        "tip": "这是「会 Excel」的分界线，值得反复练到不用想。"
               "路线是 VLOOKUP → INDEX+MATCH → XLOOKUP，"
               "三个都会写之后，你会自然明白为什么后两个更好。",
        "codes": ["VLOOKUP", "HLOOKUP", "XLOOKUP", "LOOKUP",
                  "INDEX", "MATCH", "XMATCH",
                  "OFFSET", "INDIRECT", "CHOOSE",
                  "ROW", "ROWS", "COLUMN", "COLUMNS",
                  "HYPERLINK", "TRANSPOSE"],
    },
    {
        "key": "L4",
        "title": "条件统计与聚合",
        "goal": "一句话回答「按大区按月份各是多少」，不用辅助列、不用透视表也写得出来。",
        "tip": "重点是**参数顺序**：SUMIFS 求和区域在前、COUNTIFS 全是成对区域条件、"
               "AVERAGEIFS 平均区域在前。把这三条线背下来，报表类需求就通关八成。",
        "codes": ["SUMIF", "SUMIFS", "SUMPRODUCT",
                  "COUNTIF", "COUNTIFS", "COUNTBLANK",
                  "AVERAGEIF", "AVERAGEIFS",
                  "MAX", "MIN", "MAXIFS", "MINIFS",
                  "LARGE", "SMALL", "MEDIAN", "MODE.SNGL",
                  "RANK.EQ", "PERCENTILE.INC", "STDEV.S", "CORREL",
                  "SUBTOTAL", "AGGREGATE"],
    },
    {
        "key": "L5",
        "title": "逻辑与容错",
        "goal": "用 IFS / SWITCH 替掉嵌套 IF，用 IFERROR / IFNA 给公式收口，用 LET 让长公式可读。",
        "tip": "**这一阶段最短、收益最大，建议放在 L2 之前学。**"
               "判断写对了，后面所有公式都会干净；判断写成六层嵌套，"
               "一周后连自己都改不动。",
        "codes": ["IFS", "SWITCH", "IFERROR", "IFNA",
                  "ISBLANK", "ISNUMBER", "ISTEXT", "ISERROR", "ISNA",
                  "ISEVEN", "ISODD", "LET", "LAMBDA"],
    },
    {
        "key": "L6",
        "title": "动态数组（分水岭二）",
        "goal": "从「查一个值」进化到「查一组行」，并能用函数式写法把循环干掉。",
        "tip": "动态数组是近十年 Excel 最大的一次升级："
               "以前「筛选 + 复制粘贴」这一整套手工动作，现在一个 FILTER 就够，"
               "而且源数据变了结果自动跟着变。"
               "**#SPILL! 是这一阶段最常见的报错**，把它当成「目标区域还被占着」的信号。",
        "codes": ["FILTER", "UNIQUE", "SORT", "SORTBY",
                  "SEQUENCE", "RANDARRAY",
                  "TAKE", "DROP", "CHOOSEROWS", "CHOOSECOLS",
                  "VSTACK", "HSTACK", "TOCOL", "TOROW", "EXPAND",
                  "MAP", "REDUCE", "BYROW"],
    },
    {
        "key": "L7",
        "title": "组合实战（分水岭三）",
        "goal": "把函数拼起来解决具体问题 —— 这才是高手与「认识函数的人」的差别。",
        "tip": "下面 20 条配方不是新函数，而是**套路**。"
               "每一条都值得照着在自己的表里敲一遍："
               "看懂别人写的公式叫「会读」，能自己拼出来才叫「会用」。",
        "recipes": True,
    },
]

# ======================================================================
# 20 条实战配方
# ======================================================================
SEED_RECIPES = [
    {
        "title": "精确查找一步到位（推荐写法）",
        "scene": "拿编号在另一张表里取名称 / 单价，查不到时显示「无此编号」。",
        "category": "查找与引用",
        "formula": '=XLOOKUP(A2, 价格表!$A$2:$A$500, 价格表!$C$2:$C$500, "无此编号")',
        "breakdown": "XLOOKUP(查找值, 查找列, 返回列, 查不到时返回什么)\n"
                     "第 1 个参数是要查的值；第 2、3 个参数行数一致即可，"
                     "**不需要管返回值在查找列的左边还是右边**；"
                     "第 4 个参数直接消化掉 #N/A，外面不用再套 IFNA。",
        "pitfalls": "① 只有 365 / 2021 支持，给老版本同事传文件前先转成值\n"
                    "② 第 2、3 个参数行数写歪了不会报错，只会给出错位的值",
        "related": "XLOOKUP|VLOOKUP|INDEX|MATCH",
        "difficulty": 2,
    },
    {
        "title": "老版本也能反向查找",
        "scene": "返回值在查找列的**左边**，或者要在 2016 及更早版本上打开。",
        "category": "查找与引用",
        "formula": "=INDEX($B$2:$B$500, MATCH(A2, $A$2:$A$500, 0))",
        "breakdown": "分两步：MATCH 找出「A2 在 A 列里排第几个」，"
                     "INDEX 再拿去「B 列的第几个」。\n"
                     "**这就是 VLOOKUP 做不到的事** —— VLOOKUP 只能向右查。",
        "pitfalls": "① MATCH 的第 3 参数一定写 0（精确匹配），省略会变近似匹配\n"
                    "② 两个区域都要用 $ 锁定，否则往下拉就错位\n"
                    "③ 顺序不要写反：是「MATCH 找位置，INDEX 取内容」",
        "related": "INDEX|MATCH|VLOOKUP|XMATCH",
        "difficulty": 3,
    },
    {
        "title": "多条件查找",
        "scene": "主键不止一个：要按「大区 + 月份」才能唯一确定一条记录。",
        "category": "查找与引用",
        "formula": '=XLOOKUP($F2&$G2, $A$2:$A$500&$B$2:$B$500, $D$2:$D$500, "无记录")',
        "breakdown": "把两个条件**拼成一个键**再查：\n"
                     "`$F2&$G2` 是要找的组合键，"
                     "`$A$2:$A$500&$B$2:$B$500` 是把数据区的两列拼成一列。\n"
                     "数据量不大时这样最直观；"
                     "数据量大或要往老版本兼容，就用 `SUMIFS`（数值）"
                     "或 `SUMPRODUCT`（通用）。",
        "pitfalls": "① 拼接键要防歧义：\"A\"&\"BC\" 与 \"AB\"&\"C\" 都是 \"ABC\"，"
                    "中间加个不会出现的分隔符（如 `&\"|\"&`）更稳\n"
                    "② 拼接会让公式变慢，几十万行建议改用辅助列",
        "related": "XLOOKUP|SUMIFS|SUMPRODUCT|INDEX|MATCH",
        "difficulty": 3,
    },
    {
        "title": "按区间给档位（0-60 不及格…）",
        "scene": "分数段、金额段、年龄段打标签，不用嵌套 IF。",
        "category": "查找与引用",
        "formula": '=XLOOKUP(B2, {0, 60, 80, 90}, {"不及格", "及格", "良好", "优秀"}, , -1)',
        "breakdown": "XLOOKUP 的第 5 参数（匹配模式）给 **-1**："
                     "「精确匹配，找不到就往前取最接近的较小值」。\n"
                     "配合升序的常量数组，就变成了「落在哪个档位」。\n"
                     "老版本等价写法：`=LOOKUP(B2, {0,60,80,90}, {\"不及格\",\"及格\",\"良好\",\"优秀\"})`",
        "pitfalls": "① 边界数组必须**升序**\n"
                    "② 常量数组用逗号是「横向」，用分号是「纵向」，"
                    "受区域设置影响，稳妥做法是写到单元格里引用区域\n"
                    "③ 边界值归属要写清楚：这里是「>=60 为及格」口径",
        "related": "XLOOKUP|LOOKUP|IFS|IF",
        "difficulty": 3,
    },
    {
        "title": "一对多：把命中的行全部拿回来",
        "scene": "一个客户有多笔订单，要一次性列出他全部订单，而不是只显示第一条。",
        "category": "查找与引用",   # 动态数组函数在函数库里就归「查找与引用」
        "formula": '=FILTER(A2:E500, A2:A500=$H$1, "该客户没有订单")',
        "breakdown": "FILTER(整块数据, 每行是否保留的条件, 一条都没有时显示什么)\n"
                     "条件是一个 TRUE/FALSE 数组，长度要和数据行数一致。\n"
                     "**第 3 个参数千万别省**，否则无结果时整片显示 #CALC!。",
        "pitfalls": "① 结果会溢出，下方必须留空，否则 #SPILL!\n"
                    "② 传给老版本用户前要「复制 → 选择性粘贴 → 值」\n"
                    "③ 要多列条件用 `*`（且）和 `+`（或）连接，"
                    "「或」记得写成 `((条件1)+(条件2))>0`",
        "related": "FILTER|SORT|UNIQUE|XLOOKUP",
        "difficulty": 3,
    },
    {
        "title": "动态去重 + 排序（做下拉菜单数据源）",
        "scene": "客户名 / 产品名清单要能自动跟随源表变化，还得是稳定顺序。",
        "category": "查找与引用",   # 动态数组函数在函数库里就归「查找与引用」
        "formula": "=SORT(UNIQUE(FILTER(A2:A1000, A2:A1000<>\"\")))",
        "breakdown": "从里往外读：FILTER 先滤掉空单元格 → "
                     "UNIQUE 去重 → SORT 排序。\n"
                     "**外面套 SORT 是为了让顺序稳定**："
                     "UNIQUE 的输出顺序取决于源数据出现顺序，源表插一行就可能变。",
        "pitfalls": "① 一定要先滤空，否则清单里会冒出一个空白项\n"
                    "② 「华东」与「华东 」（多了空格）会被当成两个值，"
                    "换数据源前先 TRIM 一遍\n"
                    "③ 数据验证（下拉）里直接引用动态数组区域，"
                    "365 可以直接写 `=H2#` 引用整片溢出结果",
        "related": "UNIQUE|SORT|FILTER|TRIM|SORTBY",
        "difficulty": 2,
    },
    {
        "title": "多张同结构表纵向汇总",
        "scene": "12 个月的表结构一样，要拼成一张总表再统计。",
        "category": "查找与引用",   # 动态数组函数在函数库里就归「查找与引用」
        "formula": '=VSTACK(一表!A1:D1, FILTER(一表!A2:D500, 一表!A2:A500<>""), '
                   'FILTER(二表!A2:D500, 二表!A2:A500<>""))',
        "breakdown": "先把表头拼进来，再把每张表的**数据体**用 FILTER 滤掉空行后接上。\n"
                     "比起用 INDIRECT 循环引用表名，这种写法不会因为改表名而崩，"
                     "而且 Excel 能追踪到依赖关系。",
        "pitfalls": "① **各块的列顺序必须一致**：VSTACK 按位置拼，不认表头名。"
                    "顺序不同的两块拼一起会静默错位 —— 这是最危险的地方\n"
                    "② 列数不同会补 #N/A；要统一列顺序可以给每块套 CHOOSECOLS\n"
                    "③ 拼 12 张表公式会很长，写成 LET 起名会好读很多",
        "related": "VSTACK|HSTACK|FILTER|CHOOSECOLS|LET",
        "difficulty": 3,
    },
    {
        "title": "跨表多条件汇总",
        "scene": "按「大区 + 月份 + 产品」三个条件汇总金额。",
        "category": "统计",
        "formula": '=SUMIFS(D2:D5000, A2:A5000, $H$1, B2:B5000, ">="&$H$2, B2:B5000, "<"&$H$3)',
        "breakdown": "SUMIFS(求和区域, 条件区域1, 条件1, 条件区域2, 条件2, …)\n"
                     "**求和区域写在第一个**，这最容易记错；"
                     "同列做区间（日期段）就把同一列写两遍，各给一个边界。",
        "pitfalls": "① 所有区域行数必须一致，否则 #VALUE!\n"
                    "② 条件是日期时别写 \"2026/1/1\" 这样的文本，"
                    "用 `\">=\"&DATE(2026,1,1)` 才不受区域设置影响\n"
                    "③ 条件引用单元格时别忘了 `&` 与引号：`\">=\"&H2`",
        "related": "SUMIFS|SUMIF|COUNTIFS|SUMPRODUCT",
        "difficulty": 2,
    },
    {
        "title": "「或」条件求和（SUMIFS 做不到的）",
        "scene": "统计「大区是华东**或**华南」的金额，SUMIFS 的并且逻辑不够用。",
        "category": "统计",
        "formula": "=SUMPRODUCT((($A$2:$A$500=\"华东\")+($A$2:$A$500=\"华南\"))*$D$2:$D$500)",
        "breakdown": "SUMPRODUCT 直接做数组运算：\n"
                     "两个条件各自产生一组 TRUE/FALSE，相加得到「命中 1 次或以上」，"
                     "再乘金额后求和。\n"
                     "想要严格的「恰好命中一个」就包一层：`--((...)+(...)=1)`。",
        "pitfalls": "① 区域行数必须一致，否则 #VALUE!\n"
                    "② 「或」用 `+` 会让同时满足两条件的行算 2 次，"
                    "多数场景期望的其实是 `>0`，写成 `--((A)+(B)>0)` 更稳\n"
                    "③ 别用整列引用（A:A），会明显拖慢文件",
        "related": "SUMPRODUCT|SUMIFS|COUNTIFS|AGGREGATE",
        "difficulty": 3,
    },
    {
        "title": "中式排名（并列不跳号）",
        "scene": "两个并列第 2 之后应该是第 3，而不是 RANK 给的「跳号第 4」。",
        "category": "统计",
        "formula": "=SUMPRODUCT(($B$2:$B$100>B2)/COUNTIF($B$2:$B$100,$B$2:$B$100))+1",
        "breakdown": "分子数「比自己大的有几个」，分母是「每个值的重复次数」—— "
                     "重复值会被按比例摊薄，所以并列的两个都得同一名次，"
                     "而且后面的名次不跳号。",
        "pitfalls": "① 区域里不能有空单元格，会 #DIV/0!\n"
                    "② 两处区域都要 $ 锁定，且必须是同一块区域\n"
                    "③ 区域有几万行时它比 RANK.EQ 慢不少，"
                    "大数据量建议加辅助列或用「数据透视 + 排名」",
        "related": "SUMPRODUCT|COUNTIF|RANK.EQ|LARGE",
        "difficulty": 4,
    },
    {
        "title": "取前 N 名，并带出对应的名字",
        "scene": "排行榜：按金额从高到低列出前 10 名和姓名。",
        "category": "统计",
        "formula": '=INDEX($A$2:$A$100, MATCH(LARGE($B$2:$B$100, ROW()-1), $B$2:$B$100, 0))',
        "breakdown": "LARGE 取第 k 大的金额（k 用 `ROW()-1` 自动递增），"
                     "MATCH 找出它在金额列里的位置，INDEX 再取同行的姓名。",
        "pitfalls": "① **金额有重复时会重复取到同一个人**："
                    "两个并列第一，LARGE 取第 1、第 2 都得到同一个值，"
                    "MATCH 也只找得到第一个。"
                    "解决办法是加一个「金额 + 行号/10000」的辅助列做唯一键\n"
                    "② ROW()-1 的偏移量要按公式实际所在行调整",
        "related": "LARGE|MATCH|INDEX|RANK.EQ|SORTBY",
        "difficulty": 4,
    },
    {
        "title": "查不到时不留 #N/A",
        "scene": "对外报表里出现 #N/A 很难看，但也不能把真错误一起吞掉。",
        "category": "逻辑",
        "formula": '=IFNA(VLOOKUP(A2, 表2!$A:$D, 4, FALSE), "未匹配")',
        "breakdown": "IFNA 只处理 **#N/A**（找不到），"
                     "其他错误（#REF!、#VALUE!）照旧暴露 —— "
                     "这样既好看又不会掩盖真问题。\n"
                     "XLOOKUP 可以用第 4 参数直接解决，不需要 IFNA。",
        "pitfalls": "① 别用 IFERROR 代替 IFNA 来「省事」："
                    "它会把列号写错、表名写错这类错误一起吞掉\n"
                    "② 兜底值给 0 还是给文字要考虑下游："
                    "给了文字后这一列就不能直接 SUM 了",
        "related": "IFNA|IFERROR|VLOOKUP|XLOOKUP|ISNA",
        "difficulty": 2,
    },
    {
        "title": "剩余天数与逾期提醒",
        "scene": "每行有个截止日期，要显示还剩几天、超了几天。",
        "category": "日期与时间",
        "formula": '=IF(A2="", "", IF(A2>=TODAY(), "还剩 "&(A2-TODAY())&" 天", '
                   '"已逾期 "&(TODAY()-A2)&" 天"))',
        "breakdown": "日期就是数字，`A2-TODAY()` 直接得到天数差。"
                     "先判空是为了避免空行显示成「已逾期 46282 天」。\n"
                     "想要纯数字便于排序，就用 `=DAYS(A2, TODAY())`。",
        "pitfalls": "① **TODAY() 是易失函数**，明天打开数字会变 —— "
                    "通常正是你要的，但做历史留痕时要转成值\n"
                    "② 结果是自然日；要工作日用 NETWORKDAYS\n"
                    "③ 想让「今天到期」单独标色，配条件格式"
                    "`=$A2=TODAY()` 并把公式写在整行区域上",
        "related": "TODAY|DAYS|DATEDIF|NETWORKDAYS|IF",
        "difficulty": 2,
    },
    {
        "title": "本月的最后一天 / N 个月后的同一天",
        "scene": "算月度区间、账期、还款日、复查日。",
        "category": "日期与时间",
        "formula": "本月末：=EOMONTH(A2, 0)　本月 1 日：=EOMONTH(A2, -1)+1　"
                   "3 个月后：=EDATE(A2, 3)",
        "breakdown": "`EOMONTH(日期, 0)` 给当月最后一天；"
                     "月数给 -1 是上月、1 是下月。\n"
                     "「本月第一天」没有专门函数，用 `EOMONTH(A2,-1)+1` 或 "
                     "`DATE(YEAR(A2),MONTH(A2),1)`。\n"
                     "`EDATE` 是「日号相同、往前推几个月」，适合账期。",
        "pitfalls": "① 结果可能显示成数字（46282），单元格格式要设成日期\n"
                    "② **月末会被自动贴到月末**：`EDATE(2026/1/31, 1)` 得到 2/28，"
                    "想要「严格同一天」的业务需确认能否接受\n"
                    "③ 月度条件用 `\">=\"&EOMONTH(A2,-1)+1` 与 `\"<=\"&EOMONTH(A2,0)`，"
                    "别用 MONTH() 比较（跨年会串月）",
        "related": "EOMONTH|EDATE|DATE|MONTH|DAY",
        "difficulty": 2,
    },
    {
        "title": "跳过周末与假日算工期",
        "scene": "承诺「5 个工作日内」发货 / 处理，要跳过周末和法定假日。",
        "category": "日期与时间",
        "formula": "截止日：=WORKDAY(A2, 5, 假日表!$A$2:$A$30)　"
                   "天数：=NETWORKDAYS(A2, B2, 假日表!$A$2:$A$30)",
        "breakdown": "WORKDAY 从起始日往后推 N 个工作日（**不含起始日**）；"
                     "NETWORKDAYS 数两个日期之间的工作日（**含首尾**）。\n"
                     "假日表就是你自己维护的一列日期，把法定假日和调休都列进去。",
        "pitfalls": "① Excel **不知道中国的法定假日**，必须自己给假日表\n"
                    "② 单休 / 大小周要用 `WORKDAY.INTL` / `NETWORKDAYS.INTL`，"
                    "用周末规则串指定哪天休（**串从周一开始，1 表示休息**）\n"
                    "③ 「调休上班的周六」这批函数处理不了，"
                    "需要精确到调休只能手工维护工作日历\n"
                    "④ NETWORKDAYS 含首尾，差一天的口径争议最多，写报告时说清楚",
        "related": "WORKDAY|NETWORKDAYS|WORKDAY.INTL|NETWORKDAYS.INTL|TODAY",
        "difficulty": 2,
    },
    {
        "title": "身份证取生日与性别",
        "scene": "从 18 位身份证号里取出出生日期，并按第 17 位判性别。",
        "category": "文本",
        "formula": "生日：=TEXT(MID(A2, 7, 8), \"0000-00-00\")　"
                   "性别：=IF(MOD(MID(A2, 17, 1), 2), \"男\", \"女\")",
        "breakdown": "18 位身份证：第 7~14 位是出生日期，第 17 位奇数为男、偶数为女。\n"
                     "`MID(A2,7,8)` 取出 8 位数字，"
                     "`TEXT(...,\"0000-00-00\")` 把它变成日期样式；\n"
                     "性别那一步用 MOD 判奇偶，**MOD 返回 1 或 0，正好当 IF 的条件**。",
        "pitfalls": "① `TEXT(MID(...), \"0000-00-00\")` 得到的是**文本**，"
                    "要参与年龄计算须改成 `DATE(MID(A2,7,4), MID(A2,11,2), MID(A2,13,2))`\n"
                    "② 15 位老身份证的出生年在第 7~8 位且只有两位，"
                    "用 `MID(A2, 7, 2)` 还得补世纪，先判 LEN(A2)=18 再处理\n"
                    "③ 身份证号是 18 位数字，**放进单元格前把格式设成文本**，"
                    "否则会变成科学计数法或丢末位",
        "related": "MID|TEXT|MOD|IF|LEN|DATE",
        "difficulty": 2,
    },
    {
        "title": "按分隔符拆成多列",
        "scene": "「华东、华南、华北」这种一格多值要拆成三格；"
                 "或者「姓名-手机号-部门」要拆成三列。",
        "category": "文本",
        "formula": '一格多值：=TEXTSPLIT(A2, "、")　'
                   '固定前后段：=TEXTBEFORE(A2, "-")　=TEXTAFTER(A2, "-")',
        "breakdown": "TEXTSPLIT 一次拆成多格并自动溢出；\n"
                     "只有前后两段时，TEXTBEFORE / TEXTAFTER 更直白，"
                     "取最后一段用第 3 参数给 -1。\n"
                     "老版本等价写法（很绕，能用新函数就别用这个）：\n"
                     "=TRIM(MID(SUBSTITUTE($A2,\"、\",REPT(\" \",99)), COLUMN(A1)*99-98, 99))",
        "pitfalls": "① 各段长度不一致时 TEXTSPLIT 会补 #N/A，"
                    "给第 6 参数一个填充值（如 `\"\"`）\n"
                    "② 拆出来永远是**文本**，数字要再套 `--` 或 VALUE\n"
                    "③ 结果会溢出，右侧要留空\n"
                    "④ 分隔符是全角还是半角要先看清楚，"
                    "可以用 `CODE(MID(A2,3,1))` 探一下到底是什么字符",
        "related": "TEXTSPLIT|TEXTBEFORE|TEXTAFTER|SUBSTITUTE|MID|TOCOL",
        "difficulty": 3,
    },
    {
        "title": "文本型数字批量转真数字",
        "scene": "SUM 的结果明显偏小；单元格左对齐、左上角带绿三角。",
        "category": "文本",
        "formula": "辅助列法：=IF(ISNUMBER(A2), A2, --TRIM(CLEAN(A2)))　"
                   "或整体转换：=SUM(--TRIM(CLEAN(A2:A100)))",
        "breakdown": "`--` 是「双负号」，它会对文本做一次隐式数值转换，"
                     "效果等同 VALUE 但更短更快。\n"
                     "先 CLEAN 掉不可打印字符、TRIM 掉空格，"
                     "**从网页或系统导出的文本型数字往往混着这两样**。",
        "pitfalls": "① 有些文本里是 CHAR(160) 非断行空格，"
                    "TRIM 删不掉，要 `SUBSTITUTE(A2, CHAR(160), \"\")`\n"
                    "② 转换后仍不是数字的会得到 #VALUE!，"
                    "所以 IF(ISNUMBER(...)) 兜一层更稳\n"
                    "③ **最省事的办法其实是「数据 → 分列 → 直接完成」**，"
                    "选一次目标列就能整体转类型；再不然用 POWER QUERY 导入时定类型",
        "related": "VALUE|ISNUMBER|TRIM|CLEAN|SUBSTITUTE|SUM",
        "difficulty": 2,
    },
    {
        "title": "图表数据源自动跟随行数",
        "scene": "每月往里加数据，不想每次都改图表的引用范围。",
        "category": "查找与引用",   # 动态数组函数在函数库里就归「查找与引用」
        "formula": "365：=TAKE($B$2:$B$1000, -12)　"
                   "老版本：=OFFSET($B$2, COUNTA($B$2:$B$1000)-12, 0, 12, 1)",
        "breakdown": "365 里 `TAKE(区域, -12)` 直接取最后 12 行，"
                     "**而且它不是易失函数**，大表里比 OFFSET 快得多。\n"
                     "老版本的 OFFSET 写法要算「总行数 - 12」当偏移量。\n"
                     "**更推荐的第三条路**：把源数据按 Ctrl+T 变成「表格」，"
                     "图表引用表格列即可自动扩展，连公式都不用写。",
        "pitfalls": "① OFFSET 是易失函数，几百个会明显拖慢文件\n"
                    "② OFFSET 的偏移量算错不会报错，只会给出一块「合法但错」的区域\n"
                    "③ 数据区尾部有空行时 COUNTA 会数错，"
                    "用 `COUNT($B$2:$B$1000)`（只数数字）更准",
        "related": "TAKE|OFFSET|COUNTA|COUNT|INDEX",
        "difficulty": 3,
    },
    {
        "title": "月供、利息与本金拆分",
        "scene": "算房贷月供，并做一张「每期还多少利息、多少本金」的计划表。",
        "category": "财务",
        "formula": "月供：=-PMT($B$1/12, $B$2*12, $B$3)　"
                   "第 n 期利息：=-IPMT($B$1/12, A6, $B$2*12, $B$3)　"
                   "第 n 期本金：=-PPMT($B$1/12, A6, $B$2*12, $B$3)",
        "breakdown": "B1 年利率、B2 年限、B3 贷款额。\n"
                     "**三个函数的第一参数都是「每期利率」**，"
                     "所以年利率要 /12、年限要 *12（这就是最常出错的地方）。\n"
                     "IPMT / PPMT 的第 2 参数是「第几期」、第 3 个是「总期数」，"
                     "而 PMT 的第 2 个直接是总期数 —— 参数含义不同，别照抄。",
        "pitfalls": "① 忘了把年利率除以 12、年限乘 12，结果会离谱且不报错\n"
                    "② 三个函数都**返回负数**（现金流出），外面加负号是为了好看\n"
                    "③ 校验公式：`IPMT + PPMT` 应等于 `PMT`，对不上就是参数写错了\n"
                    "④ 这是**等额本息**；等额本金要逐期自己算，"
                    "或用「本金/期数 + 剩余本金×月利率」手写一列",
        "related": "PMT|IPMT|PPMT|RATE|NPER|SLN",
        "difficulty": 3,
    },
]

# ======================================================================
# 拼装
# ======================================================================
SEED_FUNCTIONS = _MATH + _STAT + _LOOKUP + _TEXT + _DATE + _MISC + _EXTRA

# 分类的显示顺序以 CATEGORIES 为准；库里若有没登记的分类，补在其后（防御性写法）
_REGISTERED = [item["name"] for item in CATEGORIES]
for _item in SEED_FUNCTIONS:
    if _item["category"] not in _REGISTERED:
        _REGISTERED.append(_item["category"])
        CATEGORIES.append({"name": _item["category"], "desc": "（未登记说明的分类）"})

__all__ = [
    "CATEGORIES",
    "LEARNING_PATHS",
    "SEED_RECIPES",
    "SEED_FUNCTIONS",
]
