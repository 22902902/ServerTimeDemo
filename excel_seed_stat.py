# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（二）统计 / 信息
================================================================================
共 28 个条目。字段规范见 ``excel_seed_schema``。

统计这一组的学习重点是**「三兄弟」的对应关系**：
``SUM`` / ``SUMIF`` / ``SUMIFS``、``COUNT`` / ``COUNTIF`` / ``COUNTIFS``、
``AVERAGE`` / ``AVERAGEIF`` / ``AVERAGEIFS``。
把这三条线的参数顺序背下来（谁在前、谁成对出现），报表类需求就通关八成。
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    # ==================================================================
    # 统计
    # ==================================================================
    F(
        code="AVERAGE", name_cn="平均值", category="统计",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="AVERAGE(数值1, [数值2], …)",
        args_desc="数值1：数字、单元格或区域\n数值2…：最多再给 254 个",
        returns="算术平均值；区域里的文本、逻辑值与**空单元格都跳过**",
        description="算平均值，只会拿真正有数字的格子做分母。",
        example_formula="=AVERAGE(B2:B100)",
        example_result="B 列有 10 个数字、90 个空格时，是「除以 10」而不是除以 100",
        pitfalls="① 空单元格不计入分母，但**数值 0 会计入**。"
                 "「没填」和「填了 0」在这里结果不同，做人均 / 占比时最容易翻车\n"
                 "② 想「按总行数当分母」要用 SUM/COUNT 自己写，别用 AVERAGE\n"
                 "③ 区域内出现任何错误值，整个结果就是错误值",
        use_cases="平均单价；人均产出；平均响应时长；平均分",
        related="AVERAGEIF|AVERAGEIFS|MEDIAN|SUM|COUNT",
    ),
    F(
        code="AVERAGEIF", name_cn="单条件平均", category="统计",
        tags="", min_version="Excel 2007", difficulty=2, importance=2,
        syntax="AVERAGEIF(条件区域, 条件, [平均区域])",
        args_desc="条件区域：拿什么去比对\n"
                  "条件：\"华东\"、\">60\"、\">=\"&G2；通配符 * ? 可用\n"
                  "平均区域：实际要求平均的区域；省略时对条件区域自己求平均",
        returns="满足条件的那些格子的平均值",
        description="按一个条件求平均。",
        example_formula='=AVERAGEIF(A2:A100, "华东", D2:D100)',
        example_result="A 列是「华东」的行，对 D 列求平均",
        pitfalls="① 满足条件的行里**如果平均区域是空的，这一行不计入分母**；"
                 "业务上常期望「按行数平均」，两者会因为空值差出很多\n"
                 "② 条件区域与平均区域行数必须一致\n"
                 "③ 没有任何行满足条件时返回 #DIV/0!，外面套 IFERROR",
        use_cases="按大区的人均销售额；按班次的平均处理时长；按等级的平均分",
        related="AVERAGE|AVERAGEIFS|SUMIF|COUNTIF",
    ),
    F(
        code="AVERAGEIFS", name_cn="多条件平均", category="统计",
        tags="", min_version="Excel 2007", difficulty=2, importance=2,
        syntax="AVERAGEIFS(平均区域, 条件区域1, 条件1, [条件区域2, 条件2], …)",
        args_desc="平均区域：**写在第一个**（与 AVERAGEIF 顺序相反）\n"
                  "条件区域1 / 条件1：第一组筛选\n"
                  "……成对往后排，条件之间是「并且」",
        returns="同时满足全部条件的格子的平均值",
        description="按多个条件求平均。",
        example_formula='=AVERAGEIFS(D2:D100, A2:A100, "华东", B2:B100, "已完结")',
        example_result="华东且已完结的订单，平均金额",
        pitfalls="① 参数顺序和 AVERAGEIF 相反：平均区域在前\n"
                 "② 所有区域行数必须一致，否则 #VALUE!\n"
                 "③ 同样会「跳过空值」导致分母变小",
        use_cases="按「大区 + 状态」求均值；按「部门 + 月份」求人均；"
                  "剔除异常后的平均值（用条件把异常段排除）",
        related="AVERAGEIF|SUMIFS|COUNTIFS|AVERAGE",
    ),
    F(
        code="COUNT", name_cn="数数字个数", category="统计",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="COUNT(值1, [值2], …)",
        args_desc="值1：数字、单元格或区域\n值2…：最多再给 254 个",
        returns="区域中**数字**的个数（文本、逻辑值、空单元格都不算）",
        description="只数数字有多少个。",
        example_formula="=COUNT(B2:B100)",
        example_result="B 列里真正是数字的格子数。用来快速识别「文本型数字」的一大片问题",
        pitfalls="① 文本型数字（左上角带绿三角的）**不算**，"
                 "所以 COUNT 结果常比 COUNTA 小 —— 这个差值正是脏数据的信号\n"
                 "② 它不是 COUNTA：COUNTA 连文字和空格串也算\n"
                 "③ 用 COUNT 检查「是否填全」是错的，用 COUNTA 或 COUNTBLANK",
        use_cases="检查一列是否都是数字；统计有效样本量；配合 COUNTA 找文本型数字",
        related="COUNTA|COUNTBLANK|COUNTIF|SUM",
    ),
    F(
        code="COUNTA", name_cn="数非空个数", category="统计",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="COUNTA(值1, [值2], …)",
        args_desc="值1：数字、单元格或区域\n值2…：最多再给 254 个",
        returns="区域中**非空**单元格的个数（文字、数字、错误值都算）",
        description="数有多少个格子「填了东西」。",
        example_formula="=COUNTA(A2:A100)",
        example_result="A 列有内容的格子数。做「已填 / 总数」进度最常用",
        pitfalls="① **公式返回的空串 \"\" 也算非空**，"
                 "所以 COUNTA 常把 `=IF(...,\"\")` 留下的假空格数进去，"
                 "要排除得用 COUNTIF(区域,\"?*\") 之类\n"
                 "② 单元格里有一个空格也算非空，导入数据前先 TRIM",
        use_cases="统计已填条数；算填报完成率；检查空行位置；"
                  "与 COUNT 对比找文本型数字",
        related="COUNT|COUNTBLANK|COUNTIF|TRIM",
    ),
    F(
        code="COUNTBLANK", name_cn="数空单元格", category="统计",
        tags="", min_version="Excel 2007", difficulty=1, importance=2,
        syntax="COUNTBLANK(区域)",
        args_desc="区域：要统计的区域（只能给一个区域）",
        returns="区域内**空单元格**的个数",
        description="数有多少个格子是空的。",
        example_formula="=COUNTBLANK(A2:A100)",
        example_result="A 列空格子数。"
                       "注意：公式算出的空串 \"\" 也会被算成「空」",
        pitfalls="① 公式返回 `\"\"` 也算空 —— 这一点与 COUNTA 的判定相反，"
                 "所以 `COUNTA + COUNTBLANK` 通常正好等于总行数，"
                 "而这不代表数据干净\n"
                 "② 只能给一个区域参数，多给会报错\n"
                 "③ 含空格、全角空格的格子**不算**空",
        use_cases="找漏填的行；统计未填数量；配合 COUNTA 交叉验证数据完整性",
        related="COUNTA|COUNT|COUNTIF|TRIM",
    ),
    F(
        code="COUNTIF", name_cn="单条件计数", category="统计",
        tags="必学|报表主力", min_version="Excel 2003", difficulty=2, importance=3,
        syntax='COUNTIF(区域, 条件)',
        args_desc="区域：要统计的单元格区域\n"
                  "条件：\"华东\"、\">60\"、\"<>完成\"、\">=\"&G2；"
                  "通配符 * (任意多字) 与 ? (单字) 可用",
        returns="满足条件的单元格个数",
        description="按一个条件数个数。",
        example_formula='=COUNTIF(A2:A100, "华东")',
        example_result="A 列等于「华东」的行数。"
                       '模糊计数写 "华东*"；统计非空文本写 "?*"',
        pitfalls="① **它会按数值去比对长数字串**：身份证 / 订单号这类超过 15 位的，"
                 "COUNTIF 把 \"123456789012345678\" 当数字比较，会误判相等。"
                 "要么加通配符 `\"*\"&A2&\"*\"`，要么改用 SUMPRODUCT\n"
                 "② 条件里的比较符要整体加引号：`\">60\"`\n"
                 "③ 引用单元格拼接必须写 `\">=\"&G2`\n"
                 "④ 大小写不敏感，\"abc\" 与 \"ABC\" 会被算作同一条\n"
                 "⑤ 条件里要写真通配符 `*` 本身，得写 `~*` 转义",
        use_cases="统计各分组条数；统计达标人数；统计含关键字的记录；"
                  "统计未完成 / 已完成；重复值检测",
        related="COUNTIFS|SUMIF|COUNTA|SUMPRODUCT",
    ),
    F(
        code="COUNTIFS", name_cn="多条件计数", category="统计",
        tags="必学|报表主力", min_version="Excel 2007", difficulty=2, importance=3,
        syntax="COUNTIFS(区域1, 条件1, [区域2, 条件2], …)",
        args_desc="区域1：第一个筛选区域\n"
                  "条件1：\"华东\" / \">=1000\" / \"<>取消\"\n"
                  "……「区域, 条件」成对往后排，最多 127 对，全部是「并且」",
        returns="同时满足全部条件的单元格个数（数的是行数，不是格子总数）",
        description="按多个条件数个数。",
        example_formula='=COUNTIFS(A2:A100, "华东", B2:B100, ">=2026/1/1", C2:C100, "<>已取消")',
        example_result="华东、且日期在 2026 年之后、且状态不是「已取消」的行数",
        pitfalls="① **参数是「区域, 条件」成对出现**，没有「求和区域」那一项，"
                 "所以它比 SUMIFS 简单，但别把两者记混\n"
                 "② 所有区域行数必须一致，否则 #VALUE!\n"
                 "③ 和 COUNTIF 一样有长数字串误判问题\n"
                 "④ 同列做区间（日期段）就把同一列写两遍，两次条件各写一个边界",
        use_cases="按「大区 + 月份」计数；统计逾期且未处理的条数；"
                  "区间计数（金额在 1000~5000 之间的笔数）",
        related="COUNTIF|SUMIFS|AVERAGEIFS|SUMPRODUCT",
    ),
    F(
        code="MAX", name_cn="最大值", category="统计",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="MAX(数值1, [数值2], …)",
        args_desc="数值1：数字或区域\n数值2…：最多再给 254 个",
        returns="最大值；区域内没有数字时返回 0",
        description="取最大值。",
        example_formula="=MAX(B2:B100)",
        example_result="B 列最大的数字。配合 MATCH 能反查「谁最大」",
        pitfalls="① 区域全是文本 / 空时返回 **0** 而不是空，"
                 "做「最高分」时会出现诡异的 0 分\n"
                 "② 逻辑值 TRUE 会被当 1 算进去\n"
                 "③ 想带条件取最大用 MAXIFS，别用 MAX 硬套数组\n"
                 "④ 日期也是数字，MAX 取日期序列值后记得把单元格格式设回日期",
        use_cases="最高销售额；最新日期；最大库存；配合 MATCH 找对应人",
        related="MIN|MAXIFS|LARGE|MATCH",
    ),
    F(
        code="MIN", name_cn="最小值", category="统计",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="MIN(数值1, [数值2], …)",
        args_desc="数值1：数字或区域\n数值2…：最多再给 254 个",
        returns="最小值；区域内没有数字时返回 0",
        description="取最小值。",
        example_formula="=MIN(B2:B100)",
        example_result="B 列最小的数字；配 MATCH 可反查是谁",
        pitfalls="① 和 MAX 一样，没有数字时返回 0，很容易被当成「最小值就是 0」\n"
                 "② 日期最小值即最早日期，格式要设回日期才看得懂\n"
                 "③ 想看「第 2 小」用 SMALL，不要靠排序",
        use_cases="最早日期；最低价；最小库存；起算日",
        related="MAX|MINIFS|SMALL|MATCH",
    ),
    F(
        code="MAXIFS", name_cn="多条件最大值", category="统计",
        tags="", min_version="Excel 2019", difficulty=2, importance=2,
        syntax="MAXIFS(最大所在区域, 条件区域1, 条件1, [条件区域2, 条件2], …)",
        args_desc="最大所在区域：从哪片区域里挑最大值\n"
                  "条件区域1 / 条件1：筛选条件，成对往后排",
        returns="满足全部条件下的最大值；无满足项时返回 0",
        description="带条件的最大值。",
        example_formula='=MAXIFS(D2:D100, A2:A100, "华东", B2:B100, "2026/3/31")',
        example_result="华东、且日期为 2026/3/31 的记录中最大的 D 值（比如当日最高价）",
        pitfalls="① 需要 Excel 2019 / 365；老版本要用 `MAX(IF(...))` 数组公式或 AGGREGATE\n"
                 "② 无满足项返回 0，外面套 IF 判空更稳\n"
                 "③ 参数顺序：**取值区域在最前**，与 MAXIFS 的直觉一致，"
                 "但和 MAX 完全不同",
        use_cases="按大区找最高单；某一天的峰值；某人的最晚打卡时间",
        related="MINIFS|MAX|LARGE|SUMPRODUCT",
    ),
    F(
        code="MINIFS", name_cn="多条件最小值", category="统计",
        tags="", min_version="Excel 2019", difficulty=2, importance=2,
        syntax="MINIFS(最小所在区域, 条件区域1, 条件1, [条件区域2, 条件2], …)",
        args_desc="最小所在区域：从哪片区域里挑最小值\n"
                  "条件区域1 / 条件1：筛选条件，成对往后排",
        returns="满足全部条件下的最小值；无满足项时返回 0",
        description="带条件的最小值。",
        example_formula='=MINIFS(D2:D100, A2:A100, "华东", C2:C100, "已付款")',
        example_result="华东且已付款的记录里最小的 D 值",
        pitfalls="① 需要 2019 / 365\n"
                 "② 「最早时间」也常用它：条件是姓名，取值区域是打卡时间\n"
                 "③ 无满足项返回 0 而不是空；区分「真的是 0」和「没找到」要另加 COUNTIFS 判断",
        use_cases="按人找最早打卡；某类订单的最低成交价；逾期最早的那天",
        related="MAXIFS|MIN|SMALL|COUNTIFS",
    ),
    F(
        code="MEDIAN", name_cn="中位数", category="统计",
        tags="抗极端值", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="MEDIAN(数值1, [数值2], …)",
        args_desc="数值1：数字或区域\n数值2…：最多再给 254 个",
        returns="中位数：个数为奇数取中间那个，偶数取中间两个的平均",
        description="取中位数，少数极端值不会把它带偏。",
        example_formula="=MEDIAN(B2:B100)",
        example_result="100 人里有 2 人月薪 100 万时，MEDIAN 仍接近真实「中间水平」，"
                       "而 AVERAGE 会被拉高",
        pitfalls="① 它忽略文本与空单元格，与 AVERAGE 口径一致\n"
                 "② 中位数是位置统计量，**不能**参与「总和 = 中位数 × 个数」这类运算\n"
                 "③ 想看分布的第 25% / 75% 分位要用 PERCENTILE.INC",
        use_cases="薪酬 / 房价等含极端值的数据看「中位水平」；"
                  "响应时长的典型值；去掉极值后的代表值",
        related="AVERAGE|MODE.SNGL|PERCENTILE.INC|TRIMMEAN",
    ),
    F(
        code="MODE.SNGL", name_cn="众数", category="统计",
        tags="", min_version="Excel 2010", difficulty=2, importance=1,
        syntax="MODE.SNGL(数值1, [数值2], …)",
        args_desc="数值1：数字或区域（也可用老写法 MODE）",
        returns="出现次数最多的那个数值；**没有重复值时返回 #N/A**",
        description="取出现次数最多的数。",
        example_formula="=MODE.SNGL(B2:B100)",
        example_result="B 列里出现最频繁的数字，比如「最常见的问题分类编号」",
        pitfalls="① 没有重复值时返回 #N/A —— 这是正常现象不是公式写错\n"
                 "② 有多个并列众数时只返回**最先出现**的那个，"
                 "想看全部众数得用 MODE.MULT\n"
                 "③ 它是按**数值**判断重复，不是按文本；文本型数据先转成数字或改用 COUNTIF 计数",
        use_cases="最常见的问题类型；出现频率最高的金额；工单热点分析",
        related="COUNTIF|MEDIAN|MODE.MULT|AVERAGE",
    ),
    F(
        code="LARGE", name_cn="第 N 大", category="统计",
        tags="排行常用", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="LARGE(数组, k)",
        args_desc="数组：要挑选的数字区域\nk：第几名（1 = 最大，2 = 第二大）",
        returns="区域中第 k 大的数值；k 超出个数返回 #NUM!",
        description="按名次取第 k 大的值。",
        example_formula="=LARGE($B$2:$B$100, ROW()-1)",
        example_result="往下拉时依次得到第 1 大、第 2 大……（ROW()-1 当 k）。"
                       "配 INDEX + MATCH 可拿到对应的人",
        pitfalls="① k 传 0 或超过数据个数返回 #NUM!\n"
                 "② **并列会各占一个名次**：两个同样的最大值，LARGE(…,1) 与 LARGE(…,2) 结果相同，"
                 "但对应的人只有一个，所以要配 MATCH 时注意重复\n"
                 "③ 想「去重后取第 k 大」得先 UNIQUE",
        use_cases="取前 10 名；取第二名 / 次高值；配合 INDEX+MATCH 做排行榜；"
                  "取某类记录里的最大几笔",
        related="SMALL|MAX|INDEX|MATCH|RANK.EQ",
    ),
    F(
        code="SMALL", name_cn="第 N 小", category="统计",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="SMALL(数组, k)",
        args_desc="数组：要挑选的数字区域\nk：第几名（1 = 最小）",
        returns="区域中第 k 小的数值；k 超出个数返回 #NUM!",
        description="按名次取第 k 小的值。",
        example_formula='=IFERROR(SMALL(IF($A$2:$A$100="华东", $B$2:$B$100), 2), "")',
        example_result="华东纪录里第二小的值。"
                       "老版本要按 Ctrl+Shift+Enter 输入；365 直接回车即可",
        pitfalls="① 公式里出现 IF 返回 FALSE 时会被当 0 参与排序，"
                 "要写成 `IF(条件, 值)` 并在外层套 IFERROR 或筛掉 0\n"
                 "② 效率一般，大数据量建议改用 SMALL(FILTER(...), k)（365）\n"
                 "③ k 超出会 #NUM!，套 IFERROR 更稳",
        use_cases="取最便宜的 3 个报价；取最早 3 笔；配合条件取「次早」",
        related="LARGE|MIN|FILTER|IFERROR",
    ),
    F(
        code="RANK.EQ", name_cn="排名", category="统计",
        tags="必学|排行", min_version="Excel 2010", difficulty=2, importance=3,
        syntax="RANK.EQ(数值, 引用, [排序方式])",
        args_desc="数值：要排名的那个值\n"
                  "引用：在哪个区域里排（**一定要加 $ 锁住**）\n"
                  "排序方式：0 或省略 = 降序（大值排第 1）；1 = 升序",
        returns="该数值在区域中的名次（整数，从 1 开始）",
        description="算名次。并列时给同一个名次，后续名次会跳号。",
        example_formula="=RANK.EQ(B2, $B$2:$B$100, 0)",
        example_result="B2 在整列里的降序名次。"
                       "两个并列第 2 之后直接跳到第 4（这叫美式排名）",
        pitfalls="① 引用区域**没按 $ 锁定**，往下拉时区域会跟着移，名次全乱 —— 最高频错误\n"
                 "② 并列跳号（2、2、4）。要中式排名（2、2、3）用 "
                 "`SUMPRODUCT(($B$2:$B$100>B2)/COUNTIF($B$2:$B$100,$B$2:$B$100))+1`\n"
                 "③ 老写法 ``RANK`` 在新版仍可用，但微软建议用 RANK.EQ",
        use_cases="销售排行；成绩排名；分组内排名（配 COUNTIFS 算组内名次）",
        related="SUMPRODUCT|COUNTIF|LARGE|RANK.AVG",
    ),
    F(
        code="PERCENTILE.INC", name_cn="百分位", category="统计",
        tags="含边界", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="PERCENTILE.INC(数组, k)",
        args_desc="数组：数据区域\nk：要取的分位（0~1 之间，含 0 和 1）；0.9 = 第 90 百分位",
        returns="位于该百分位的数值（含端点的插值口径）",
        description="取某个百分位的值，用来划阈值、看分布。",
        example_formula="=PERCENTILE.INC(B2:B100, 0.9)",
        example_result="B 列的 90 分位值：约九成数据都不超过它。"
                       "常用来定「异常阈值」",
        pitfalls="① k 必须落在 0~1，写成 90 会返回 #NUM!\n"
                 "② ``.INC`` 含端点、``.EXC`` 不含端点，两者在 k 靠近 0 或 1 时结果不同，"
                 "**报口径时要写清楚用的是哪个**\n"
                 "③ 它给的是「位置的插值」，不等于「第 90% 个数据」\n"
                 "④ 老写法 PERCENTILE 与 .INC 等价",
        use_cases="定异常阈值（超过 90 分位算异常）；服务水平（P95 响应时长）；"
                  "薪酬分位对标",
        related="QUARTILE.INC|MEDIAN|MAX|LARGE",
    ),
    F(
        code="STDEV.S", name_cn="样本标准差", category="统计",
        tags="", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="STDEV.S(数值1, [数值2], …)",
        args_desc="数值1：数字或区域（样本数据）\n数值2…：最多再给 254 个",
        returns="样本标准差（分母是 n-1），衡量数据离散程度",
        description="衡量数据波动有多大。",
        example_formula="=STDEV.S(B2:B100)",
        example_result="B 列的标准差。数值越大说明数据越分散、越不稳定",
        pitfalls="① **样本用 .S（n-1）、总体用 .P（n）**。"
                 "同一组数据两者结果不同，写错会被懂行的人一眼看出来\n"
                 "② 数据只有 1 个时 .S 会 #DIV/0!（n-1 = 0）\n"
                 "③ 它的单位与原数据相同，跨量级比较（元 vs 万元）要看变异系数："
                 "STDEV.S/AVERAGE\n"
                 "④ 老写法 ``STDEV`` 与 .S 等价",
        use_cases="质量波动分析；评分稳定性；响应时长波动；风险度量",
        related="VAR.S|AVERAGE|STDEV.P|CORREL",
    ),
    F(
        code="CORREL", name_cn="相关系数", category="统计",
        tags="", min_version="Excel 2003", difficulty=3, importance=2,
        syntax="CORREL(数组1, 数组2)",
        args_desc="数组1：第一组数据\n数组2：第二组数据（**个数必须与数组1 相同**）",
        returns="-1 到 1 之间的相关系数；无相关约为 0",
        description="看两组数据是否同涨同跌。",
        example_formula="=CORREL(B2:B100, C2:C100)",
        example_result="0.85 → 强正相关（B 涨 C 也涨）；"
                       "-0.6 → 中等负相关；接近 0 → 基本无关",
        pitfalls="① **相关不等于因果**。这是分析师最需要克制的一处\n"
                 "② 只捕捉**线性**关系：完美的 U 形关系也会算出接近 0\n"
                 "③ 两组数据个数必须相同，空单元格成对忽略，但错位不会报错只会算错\n"
                 "④ 异常值会把系数拉得很夸张，看之前先画散点",
        use_cases="广告投入与销量关系；温度与能耗；价格与转化率；"
                  "两指标是否同向变化",
        related="STDEV.S|AVERAGE|SLOPE|FORECAST.LINEAR",
    ),

    # ==================================================================
    # 信息
    # ==================================================================
    F(
        code="ISBLANK", name_cn="是否真空", category="信息",
        tags="必学|判空", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="ISBLANK(值)",
        args_desc="值：单元格引用或表达式（通常给单元格引用）",
        returns="单元格**真正为空**时返回 TRUE，否则 FALSE",
        description="判断单元格是不是真正的空。",
        example_formula='=IF(ISBLANK(A2), "未填", A2)',
        example_result="A2 真空时显示「未填」，否则显示 A2 内容",
        pitfalls="① **公式返回的空串 \"\" 不算空！** 这是最经典的坑："
                 "`=IF(B2=\"\",\"\",B2)` 算出的格子 ISBLANK 会返回 FALSE。"
                 "想同时认这两种空，用 `=A2=\"\"` 或 LEN(A2)=0\n"
                 "② 单元格里有一个空格不算空\n"
                 "③ 别拿它判断数值是否为 0，那是两回事",
        use_cases="区分「没填」与「填了 0」；填报完整性检查；条件格式标出空格",
        related="ISNUMBER|ISTEXT|COUNTA|LEN",
    ),
    F(
        code="ISNUMBER", name_cn="是否为数字", category="信息",
        tags="必学|脏数据检测", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="ISNUMBER(值)",
        args_desc="值：单元格引用或表达式",
        returns="结果为数字（含日期）时 TRUE，否则 FALSE",
        description="判断是不是真数字。",
        example_formula='=IF(ISNUMBER(A2), "数字", "文本")',
        example_result="能一眼揪出「文本型数字」—— 那些看起来是数字、"
                       "实际是文本的单元格（左上角带绿三角）",
        pitfalls="① **日期也是数字**，ISNUMBER(日期单元格) 返回 TRUE，"
                 "想单独判日期要配 CELL(\"format\", A2)\n"
                 "② 逻辑值 TRUE/FALSE 在区域引用里 ISNUMBER 返回 FALSE（不是数字）\n"
                 "③ 它是对「运算结果」判断：`ISNUMBER(\"123\")` 是 FALSE，"
                 "因为那是文本",
        use_cases="找出文本型数字并批量转换；判断查找结果是否有效；"
                  "数据清洗前的体检",
        related="ISTEXT|ISBLANK|VALUE|N",
    ),
    F(
        code="ISTEXT", name_cn="是否为文本", category="信息",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="ISTEXT(值)",
        args_desc="值：单元格引用或表达式",
        returns="结果为文本时 TRUE，否则 FALSE",
        description="判断是不是文本。",
        example_formula='=SUMPRODUCT(--ISTEXT(A2:A100))',
        example_result="数出 A 列里有多少个文本格子。"
                       "（SUMPRODUCT 能把 TRUE/FALSE 数组转成 1/0 求和）",
        pitfalls="① 公式算出的 `\"\"` 也算文本，所以「空」的公式格会被判成 ISTEXT = TRUE\n"
                 "② 数字存成文本也返回 TRUE，这才是它最常见的用途\n"
                 "③ 别把它的数组结果直接塞进 SUM，要配 -- 或 SUMPRODUCT",
        use_cases="检测混入文本的数字列；统计异常格式条数；清洗前体检",
        related="ISNUMBER|ISBLANK|VALUE|SUMPRODUCT",
    ),
    F(
        code="ISERROR", name_cn="是否出错", category="信息",
        tags="必学|收口", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="ISERROR(值)",
        args_desc="值：单元格引用或表达式",
        returns="结果为**任何一种错误值**时 TRUE，否则 FALSE",
        description="判断公式是否出错（任何错误都算）。",
        example_formula='=IF(ISERROR(VLOOKUP(A2,表2!A:D,4,FALSE)), "查不到", VLOOKUP(A2,表2!A:D,4,FALSE))',
        example_result="出错时给「查不到」。"
                       "不过在 2007 之后，这种写法应该用 IFERROR 一步到位",
        pitfalls="① 写法啰嗦：把同一个查找写了两遍。"
                 "**2007 起优先用 IFERROR**，只有需要区分错误类型时才回到 ISERROR\n"
                 "② 它把 #N/A 与 #VALUE! 等一视同仁，"
                 "想单独认「找不到」用 ISNA\n"
                 "③ 它返回 TRUE/FALSE，参与算术要转 1/0",
        use_cases="旧文件兼容；区分「哪一类错误」；条件格式标红错误值；"
                  "数组公式里筛掉错误项",
        related="ISNA|ISERR|IFERROR|IFNA",
    ),
    F(
        code="ISNA", name_cn="是否是查不到", category="信息",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="ISNA(值)",
        args_desc="值：单元格引用或表达式",
        returns="结果**恰好是 #N/A** 时 TRUE，其他错误返回 FALSE",
        description="只判断「找不到」这一种错误。",
        example_formula='=IF(ISNA(A2), "无记录", "有记录")',
        example_result="只看 #N/A。这样 #REF!、#VALUE! 之类的真错误不会被悄悄吞掉",
        pitfalls="① 想「兜底」用它写会比较长，日常用 IFNA 更直接\n"
                 "② 它对其他错误返回 FALSE，所以如果只是拿它当 IFERROR 用，"
                 "真错误会漏到下游 —— 这是特性不是 bug，但要心里有数",
        use_cases="对账时单独列出「未匹配」的编号；区分「没找到」与「公式坏了」",
        related="ISERROR|IFNA|NA|IFERROR",
    ),
    F(
        code="ISEVEN", name_cn="是否偶数", category="信息",
        tags="", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="ISEVEN(数值)",
        args_desc="数值：要判断的数（**小数会先被截断取整**）",
        returns="是偶数 TRUE，奇数 FALSE",
        description="判断奇偶。",
        example_formula="=ISEVEN(ROW())",
        example_result="偶数行返回 TRUE，用来做隔行填色的条件格式",
        pitfalls="① 小数会被**截断**：ISEVEN(2.9) 判的是 2，返回 TRUE\n"
                 "② 负数按整数规则：ISEVEN(-3) = FALSE\n"
                 "③ 单独看它没意义，都是配条件格式或 SUMPRODUCT 用",
        use_cases="隔行填色；按奇偶分组抽样；按行号做斑马纹",
        related="ISODD|MOD|ROW",
    ),
    F(
        code="ISODD", name_cn="是否奇数", category="信息",
        tags="", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="ISODD(数值)",
        args_desc="数值：要判断的数（小数先截断）",
        returns="是奇数 TRUE，偶数 FALSE",
        description="判断奇偶（奇数）。",
        example_formula="=IF(ISODD(ROW()), ROW(), \"\")",
        example_result="只在奇数行显示行号，配合图表或核对用",
        pitfalls="① 同样先截断小数\n"
                 "② 与 ISEVEN 是互补的，选一个读起来顺的就行",
        use_cases="奇偶分组；隔行处理；编号规则校验",
        related="ISEVEN|MOD|ROW",
    ),
    F(
        code="ISFORMULA", name_cn="是否是公式", category="信息",
        tags="审表利器", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="ISFORMULA(引用)",
        args_desc="引用：单元格引用（**必须是引用，不能是值**）",
        returns="该单元格里是公式时 TRUE，是常量时 FALSE",
        description="判断某个格子里写的是公式还是手敲的常数。",
        example_formula="=ISFORMULA(A2)",
        example_result="A2 里是公式返回 TRUE。"
                       "一整列 ISFORMULA 扫下来，谁被手改成死值一眼就看出来",
        pitfalls="① 必须传**引用**：`ISFORMULA(2)` 会报错，要写 `ISFORMULA(A2)`\n"
                 "② 数组里逐个判断需要数组输入（365 直接回车即可溢出）\n"
                 "③ 需要 2013 及以上",
        use_cases="接手别人的表时审计；检查有没有人把公式改成常数；"
                  "做报表模板完整性校验",
        related="FORMULATEXT|TYPE|ISNUMBER",
    ),
]
