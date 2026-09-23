# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（三）查找与引用 / 动态数组
================================================================================
共 37 个条目。字段规范见 ``excel_seed_schema``。

这是全库**最重要**的一片。原因很直接：
Excel 的日常难度绝大部分集中在「跨表把数据对起来」，而这一片就是那把钥匙。

学习顺序（也是本工具 L3 → L6 的路线）
--------------------------------------------------------------------------------
1. ``VLOOKUP``   ── 入门：会写、知道第 4 个参数必须给 FALSE
2. ``INDEX`` + ``MATCH`` ── 进阶：能往左查、列插入不会错位
3. ``XLOOKUP``   ── 现代写法：一个函数替代上面两个，还能兜底、还能反向搜
4. ``FILTER`` / ``UNIQUE`` / ``SORT`` ── 动态数组：从「查一个值」到「查一组行」

动态数组的函数按官方分类仍属「查找与引用」（与速查书章节一致），
但都打了 ``动态数组`` 标签，学习路径 L6 靠标签聚合，不靠分类。
"""

from __future__ import annotations

from excel_seed_schema import F

DYNAMIC = "动态数组|365新增"

SEED = [
    # ==================================================================
    # 查找与引用 · 经典
    # ==================================================================
    F(
        code="VLOOKUP", name_cn="垂直查找", category="查找与引用",
        tags="必学|分水岭|最出名函数", min_version="Excel 2003",
        difficulty=2, importance=3,
        syntax="VLOOKUP(查找值, 表格区域, 列序数, [匹配方式])",
        args_desc="查找值：要查什么（编号、姓名）\n"
                  "表格区域：去哪张表里查。**首列必须就是查找列**\n"
                  "列序数：要返回的值在区域里是第几列（从区域第一列算起，不是从 A 列）\n"
                  "匹配方式：FALSE 或 0 = 精确匹配；TRUE 或 1 = 近似匹配；**省略 = TRUE**",
        returns="区域内同一行、指定列的内容；找不到（精确模式）返回 #N/A",
        description="在区域首列里找值，返回同一行指定列的内容，Excel 最出名的查找函数。",
        example_formula='=IFNA(VLOOKUP(A2, 价格表!$A$2:$D$500, 3, FALSE), "无此编号")',
        example_result="拿 A2 的编号去「价格表」的首列找，找到后返回该行第 3 列（比如单价）；"
                       "找不到就显示「无此编号」",
        pitfalls="① **第 4 个参数省略会变成近似匹配**，这是头号坑："
                 "表没排序时结果会莫名其妙地错，而且**不报错**\n"
                 "② 只能**向右查**：查找列不能在返回列的右边。要往左查必须换 INDEX+MATCH 或 XLOOKUP\n"
                 "③ 列序数写死是硬编码：中间插入一列，所有 VLOOKUP 全错位，且不报错\n"
                 "④ 首列重复值时只返回**第一条**命中的，后面的永远取不到\n"
                 "⑤ 整列引用（价格表!A:D）会拖慢大表，且新增列会改变列序数\n"
                 "⑥ 查找值与查找列的数据类型要一致：数字 1001 查文本 \"1001\" 查不到",
        use_cases="按编号查名称 / 单价；两张表按主键对齐；对账单匹配；"
                  "从明细表取某个字段到汇总表",
        related="INDEX|MATCH|XLOOKUP|IFNA|HLOOKUP",
    ),
    F(
        code="HLOOKUP", name_cn="水平查找", category="查找与引用",
        tags="冷门但书上有", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="HLOOKUP(查找值, 表格区域, 行序数, [匹配方式])",
        args_desc="查找值：要查什么\n"
                  "表格区域：首**行**必须就是查找行\n"
                  "行序数：返回值在区域里的第几行\n"
                  "匹配方式：FALSE / 0 精确；TRUE / 1 近似；省略 = TRUE",
        returns="区域内同一列、指定行的内容；精确模式下找不到返回 #N/A",
        description="VLOOKUP 的横向版本，适用于表头在第一行的横排表。",
        example_formula="=HLOOKUP(B1, 指标表!$B$1:$M$5, 3, FALSE)",
        example_result="用横向表头（B1 里的月份）在第 1 行里找，返回第 3 行的值",
        pitfalls="① 同样是省略第 4 参数会变近似匹配\n"
                 "② 实际工作里横排表少，遇到横排表更常见的做法是**先转置**（粘贴 → 转置）再 VLOOKUP\n"
                 "③ 与 VLOOKUP 相比更难维护：插入行就会错位",
        use_cases="查横排的指标表 / 月度对照表；查只有一行数据的参数表",
        related="VLOOKUP|XLOOKUP|TRANSPOSE|INDEX",
    ),
    F(
        code="XLOOKUP", name_cn="现代查找", category="查找与引用",
        tags="必学|365新增|替代VLOOKUP", min_version="Excel 365",
        difficulty=2, importance=3,
        syntax="XLOOKUP(查找值, 查找数组, 返回数组, [未找到], [匹配模式], [搜索模式])",
        args_desc="查找值：要查什么\n"
                  "查找数组：去哪一列（或一行）里找，**只有一列，且不用管它在左边还是右边**\n"
                  "返回数组：要拿回来的那列，长度必须与查找数组一致\n"
                  "未找到：查不到时返回什么；省略则返回 #N/A（**这一项让 IFNA 可以省掉**）\n"
                  "匹配模式：0 精确（默认）／-1 精确或下一个更小／1 精确或下一个更大／2 通配符\n"
                  "搜索模式：1 从前到后（默认）／-1 从后到前（取最后一条）／2、-2 二分查找",
        returns="返回数组里对应位置的内容；可一次返回多列（返回数组给多列即溢出）",
        description="一个函数替掉 VLOOKUP + IFNA + INDEX/MATCH，且能往左查、能反向搜、能一次带出多列。",
        example_formula='=XLOOKUP(A2, 价格表!$A$2:$A$500, 价格表!$C$2:$C$500, "无此编号")',
        example_result="拿 A2 在价格表 A 列里找，返回同行 C 列的值；"
                       "找不到直接显示「无此编号」，不需要外面再套 IFNA",
        pitfalls="① **查找数组与返回数组必须行数一致**，写错不会报错但会给出错位的值\n"
                 "② 只有 365 / 2021 支持。发给用 2016 的同事，对方打开会看到 _xlfn.XLOOKUP 报错 —— "
                 "**给别人传文件前要确认对方版本**\n"
                 "③ 默认精确匹配，所以从 VLOOKUP 迁移过来时反而要小心："
                 "原本依赖「近似匹配」的区间判断，要显式给匹配模式 -1\n"
                 "④ 返回数组给多列会**溢出**：目标位置右侧如果有数据会被 #SPILL! 挡住\n"
                 "⑤ 首列重复值默认返回第一条，想取最后一条用搜索模式 -1",
        use_cases="替代所有 VLOOKUP 场景；反向查找（返回值在查找列左侧）；"
                  "取最后一条记录；一次带出多列；区间匹配（0-60 不合格）",
        related="VLOOKUP|INDEX|MATCH|XMATCH|FILTER",
    ),
    F(
        code="LOOKUP", name_cn="向量查找 / 区间匹配", category="查找与引用",
        tags="区间匹配常用", min_version="Excel 2003", difficulty=3, importance=2,
        syntax="LOOKUP(查找值, 查找向量, [结果向量])　或　LOOKUP(查找值, 数组)",
        args_desc="查找值：要比对的值\n"
                  "查找向量：**必须按升序排好**的一列\n"
                  "结果向量：长度与查找向量一致，返回对应位置的值",
        returns="小于等于查找值的**最后一个**匹配项对应的结果",
        description="经典的区间查表函数：给的数落在哪个档位里，就返回那个档位的标签。",
        example_formula='=LOOKUP(B2, {0,60,80,90}, {"不及格","及格","良好","优秀"})',
        example_result="B2=85 → 良好。它找到「<=85 的最后一个」是 80，返回对应标签。"
                       "分数段查表写一行就够，不需要嵌套 IF",
        pitfalls="① **查找向量必须升序**，乱序会给错答案且不报错\n"
                 "② 找不到「<= 查找值」的项时返回 #N/A（比如 B2 是负数而首项是 0）\n"
                 "③ 用常量数组 `{0,60,80,90}` 时分隔符是**逗号**（列）或分号（行），"
                 "受区域设置影响，稳妥做法是写到单元格里再引用区域\n"
                 "④ 它比 XLOOKUP 的区间模式难读，新文件建议优先 XLOOKUP",
        use_cases="分数段 / 金额段打标签；阶梯提成率；按区间给折扣；"
                  "把「距离」映射成「运费档位」",
        related="XLOOKUP|VLOOKUP|MATCH|IFS",
    ),
    F(
        code="INDEX", name_cn="按行列号取值", category="查找与引用",
        tags="必学|分水岭|万能", min_version="Excel 2003", difficulty=3, importance=3,
        syntax="INDEX(数组, 行号, [列号])　或　INDEX(引用, 行号, [列号], [区域号])",
        args_desc="数组：要取值的区域\n"
                  "行号：区域内第几行（0 表示整列）\n"
                  "列号：区域内第几列（0 表示整行）；区域只有一列时可省略\n"
                  "区域号：多个不连续区域组成的引用里取第几块（少用）",
        returns="区域内指定行列交叉处的值",
        description="按「第几行第几列」取值。单独用很少见，和 MATCH 搭配才是主力。",
        example_formula="=INDEX($C$2:$C$100, MATCH(A2, $A$2:$A$100, 0))",
        example_result="用 MATCH 找到行号，再用 INDEX 取该行 C 列的值。"
                       "效果同 VLOOKUP，但**能往左查、插入列不会错位**",
        pitfalls="① 行号 / 列号是**相对于给定区域**算的，不是工作表行号。"
                 "这既是它灵活的原因，也是算错位置的头号原因\n"
                 "② 行号给 0 会返回整列（365 里会溢出成一组值）\n"
                 "③ 单独 INDEX 返回的是「值」；要返回引用（配合 SUM、COUNTIF 等）"
                 "需要 INDEX 的引用形式，行为不同\n"
                 "④ 与 MATCH 的 `$` 锁定要一次性锁对，否则下拉即错位",
        use_cases="INDEX+MATCH 查找（替代 VLOOKUP）；配合 MATCH 做动态取列；"
                  "取第 N 行记录；配合 ROW() 做动态区域起点",
        related="MATCH|VLOOKUP|XLOOKUP|OFFSET|ROW",
    ),
    F(
        code="MATCH", name_cn="找位置", category="查找与引用",
        tags="必学|分水岭", min_version="Excel 2003", difficulty=3, importance=3,
        syntax="MATCH(查找值, 查找区域, [匹配方式])",
        args_desc="查找值：要找什么\n"
                  "查找区域：**只能是一行或一列**\n"
                  "匹配方式：0 = 精确匹配（最常用）；1 或省略 = 升序近似；"
                  "-1 = 降序近似；配合通配符时用 0",
        returns="找到的值在区域里的**位置序号**（第几个），不是值本身",
        description="找出某个值在一行 / 一列里排第几，是 INDEX 的最佳搭档。",
        example_formula='=MATCH(A2, 价格表!$A$2:$A$500, 0)',
        example_result="A2 在价格表 A 列里排第几个（比如第 7 个）。"
                       "注意返回的是位置，不是值",
        pitfalls="① **第 3 参数省略会变成升序近似匹配**，和 VLOOKUP 一样是高频坑。"
                 "日常一律显式写 0\n"
                 "② 位置是**相对于区域**的：区域从第 2 行开始时，返回 1 表示工作表第 2 行\n"
                 "③ 找不到返回 #N/A，外面套 IFNA\n"
                 "④ 查找区域不能是二维，给 A:C 会返回 #N/A 或错误位置\n"
                 "⑤ 大小写不敏感，\"abc\" 能匹配 \"ABC\"（要区分用 EXACT 或 XMATCH 的匹配模式）",
        use_cases="定位行号 / 列号；配 INDEX 做查找；判断某值是否存在；"
                  "动态取列（表头名 → 列号）；计算「第几个出现」",
        related="INDEX|XMATCH|VLOOKUP|IFNA|ROW",
    ),
    F(
        code="XMATCH", name_cn="现代找位置", category="查找与引用",
        tags="365新增", min_version="Excel 365", difficulty=2, importance=2,
        syntax="XMATCH(查找值, 查找数组, [匹配模式], [搜索模式])",
        args_desc="查找值：要找什么\n"
                  "查找数组：一行或一列\n"
                  "匹配模式：0 精确（默认）／-1 精确或更小／1 精确或更大／2 通配符\n"
                  "搜索模式：1 从前到后（默认）／-1 从后到前／2、-2 二分查找",
        returns="位置序号（整数），从 1 开始；找不到返回 #N/A",
        description="MATCH 的升级版：默认就是精确匹配，还能反向搜、能区分大小写。",
        example_formula='=XMATCH(A2, 价格表!$A$2:$A$500)',
        example_result="返回位置序号。相比 MATCH 的好处：**不用记得写 0**，"
                       "默认就是精确匹配",
        pitfalls="① 需要 365 / 2021\n"
                 "② 返回的仍是位置而非值；要值还得配 INDEX\n"
                 "③ 反向搜索用搜索模式 -1（找「最后一次出现」很方便）",
        use_cases="找最后一次出现的位置；区分大小写查找；替代 MATCH 减少参数记错",
        related="MATCH|INDEX|XLOOKUP",
    ),
    F(
        code="OFFSET", name_cn="偏移取值", category="查找与引用",
        tags="动态区域|慎用", min_version="Excel 2003", difficulty=3, importance=2,
        syntax="OFFSET(基点, 行偏移, 列偏移, [高度], [宽度])",
        args_desc="基点：从哪个单元格出发\n"
                  "行偏移：往下（正）或往上（负）走几行\n"
                  "列偏移：往右（正）或往左（负）走几列\n"
                  "高度 / 宽度：返回一个多大的区域；省略则返回 1 个单元格",
        returns="一个新的区域引用",
        description="从一个起点出发，按偏移量划出一块区域。做「自动跟随数据长度」的动态区域最经典。",
        example_formula="=SUM(OFFSET($B$2, 0, 0, COUNTA($B$2:$B$1000), 1))",
        example_result="从 B2 开始，高度取「B 列实际有多少个非空」—— "
                       "**新增数据时合计自动跟着变**，不用改引用范围",
        pitfalls="① 它是**易失函数**：任何一次重算都会重算它，大表里几百个 OFFSET 会让文件明显变卡\n"
                 "② 偏移量算错不会报错，只会给出一块「合法但错」的区域，且很难排查\n"
                 "③ 引用被移动 / 删除时容易变成 #REF!\n"
                 "④ 现代替代：用**表格（Ctrl+T）** + 结构化引用，或 365 的动态数组（FILTER / TAKE），"
                 "它们都能自动跟随长度而且不是易失函数\n"
                 "⑤ 高度 / 宽度给 0 或负数会报 #REF!",
        use_cases="图表数据源自动跟随行数；动态的最后一个 N 行（近 7 天数据）；"
                  "配合 SUM / AVERAGE 做滚动统计",
        related="INDIRECT|INDEX|COUNTA|TAKE",
    ),
    F(
        code="INDIRECT", name_cn="把文本变成引用", category="查找与引用",
        tags="慎用|易失", min_version="Excel 2003", difficulty=3, importance=2,
        syntax='INDIRECT(文本, [引用样式])',
        args_desc="文本：一段描述单元格地址的字符串，如 \"A1\"、\"Sheet2!B5\"、\"数据!A1:D9\"\n"
                  "引用样式：TRUE / 省略 = A1 样式；FALSE = R1C1 样式",
        returns="该字符串所指位置的值或区域",
        description="把「拼出来的地址文本」当成真引用用，是跨表动态引用的老办法。",
        example_formula='=SUM(INDIRECT("\'" & B1 & "\'!D:D"))',
        example_result="B1 里写着月份（如「9月」），公式就去「9月」这张表里对 D 列求和。"
                       "**换月份只要改 B1**，不用改公式",
        pitfalls="① **它不是易失函数，但引用的表名一旦改动会立刻 #REF!**，"
                 "而且 Excel 的「查找替换」改表名时不会追踪到它 —— 这是它最大的坑\n"
                 "② 表名含空格、数字开头或特殊字符时，必须用单引号包起来："
                 "`\"'2026 数据'!A1\"`；拼错就是 #REF!，且不提示哪里错\n"
                 "③ 引用已关闭的工作簿时必须写全路径，否则 #REF!\n"
                 "④ 因为引用关系是运行期才算出，**Excel 看不到依赖**，"
                 "改动上游时不会提示、删除行也不会自动调整\n"
                 "⑤ 现代替代：365 的 VSTACK / HSTACK 或用「表格 + 结构化引用」，"
                 "或者干脆用 POWER QUERY 汇总多表",
        use_cases="跨多张同结构工作表汇总（1月/2月/3月）；"
                  "把「表名」放在单元格里做下拉切换；动态指定要引用哪一块",
        related="OFFSET|INDEX|SUMIF|XLOOKUP",
    ),
    F(
        code="CHOOSE", name_cn="按序号挑一个", category="查找与引用",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="CHOOSE(索引号, 值1, [值2], …)",
        args_desc="索引号：1 对应值1，2 对应值2，……（必须是 1~254 的整数）\n"
                  "值1…：可以是值、单元格、区域，最多 254 个",
        returns="第「索引号」个参数的内容",
        description="按下标从一堆候选里挑一个，也能用来拼动态区域。",
        example_formula='=CHOOSE(MONTH(TODAY()), "Q1","Q1","Q1","Q2","Q2","Q2","Q3","Q3","Q3","Q4","Q4","Q4")',
        example_result="今天是 9 月 → 返回「Q3」。月数直接映射到季度，比写嵌套 IF 干净",
        pitfalls="① 索引号超出范围返回 #VALUE!\n"
                 "② 索引号是小数会**向下取整**，不报错（CHOOSE(1.9, …) 取第 1 个）\n"
                 "③ 参数最多 254 个，要挑的东西多了该换查表（LOOKUP / INDEX）\n"
                 "④ 它能返回区域，这时要配合 SUM 等函数使用",
        use_cases="月份→季度；按序号选不同区域或图表源；按序号选文案",
        related="SWITCH|IFS|LOOKUP|INDEX",
    ),
    F(
        code="ROW", name_cn="取行号", category="查找与引用",
        tags="辅助必用", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="ROW([引用])",
        args_desc="引用：单元格或区域；省略则返回公式自己所在的行号",
        returns="行号（整数）；给区域时在 365 会溢出成一组行号",
        description="取行号，也是生成连续序号（1、2、3…）最省事的写法。",
        example_formula="=ROW()-1",
        example_result="公式写在数据区的第 2 行 → 返回 1；往下拉依次 2、3…。"
                       "比手敲 + 填充更不易错",
        pitfalls="① **ROW() 省略参数返回的是公式自己所在行**，"
                 "一旦在上面插行，所有序号会自动跟着变（有时正是你想要的）\n"
                 "② 想要「插行后也保持 1..N 连续」就用它；"
                 "想「固定绑定某条记录」就得改成手写序号或加辅助列\n"
                 "③ ROW(A1) 与 ROW() 不一样：前者恒为 1，可作为步长起点控制",
        use_cases="生成连续序号；按行号做隔行处理；给 LARGE / SMALL 当 k；"
                  "构造递增的偏移量",
        related="ROWS|COLUMN|SEQUENCE|LARGE",
    ),
    F(
        code="ROWS", name_cn="数几行", category="查找与引用",
        tags="动态区域常用", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="ROWS(数组)",
        args_desc="数组：任意区域或数组",
        returns="区域包含的行数",
        description="数一个区域有几行，做动态计算时常用。",
        example_formula="=ROWS($A$2:$A$500)",
        example_result="返回 499。配 OFFSET / INDEX 划动态区域时，常拿它当「高度」",
        pitfalls="① 它数的是**区域的行数**，不是「有数据的行数」。"
                 "要数实际数据用 COUNTA\n"
                 "② 别和 ROW() 混：ROW() 给行号，ROWS() 给个数",
        use_cases="动态区域的尺寸；配合 OFFSET / INDEX 做「最后一个 N 行」；"
                  "数组公式里判断长度",
        related="ROW|COLUMN|COLUMNS|COUNTA",
    ),
    F(
        code="COLUMN", name_cn="取列号", category="查找与引用",
        tags="辅助必用", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="COLUMN([引用])",
        args_desc="引用：单元格或区域；省略则返回公式自己所在的列号（A = 1）",
        returns="列号（A 列是 1，B 列是 2，……）",
        description="取列号。",
        example_formula="=VLOOKUP($A2, 价格表!$A:$D, COLUMN()-1, FALSE)",
        example_result="在 B 列写公式时 COLUMN()-1 = 1，在 C 列写就是 2，"
                       "**往右拉时列序数自动递增**，不用手改",
        pitfalls="① 需要把第一个参数锁列（$A2），否则往右拉时查找值也跑了\n"
                 "② 列号是数字，字母 A、AA 的换算要配 ADDRESS 或自己算",
        use_cases="让 VLOOKUP 的列序数随拖动自动变；生成列标签；配合 MOD 做隔列处理",
        related="COLUMNS|ROW|ADDRESS|VLOOKUP",
    ),
    F(
        code="COLUMNS", name_cn="数几列", category="查找与引用",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="COLUMNS(数组)",
        args_desc="数组：任意区域或数组",
        returns="区域包含的列数",
        description="数一个区域有几列。",
        example_formula="=COLUMNS($B$2:$D$2)",
        example_result="返回 3。做「动态填充宽度」或校验区域大小时用",
        pitfalls="① 数的是区域列数，不是「有数据的列数」\n"
                 "② 与 COLUMN() 不是一回事",
        use_cases="校验区域尺寸；配合 OFFSET 定宽度；动态区域的尺寸计算",
        related="COLUMN|ROWS|OFFSET",
    ),
    F(
        code="HYPERLINK", name_cn="超链接", category="查找与引用",
        tags="报表交互", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="HYPERLINK(链接位置, [显示文字])",
        args_desc="链接位置：网址、文件路径、`#表名!单元格` 这样的内部跳转，"
                  "也可以是拼出来的字符串\n"
                  "显示文字：单元格里显示的名字；省略就显示链接本身",
        returns="可点击的链接（单击跳转）",
        description="在单元格里造一个可点击的链接，还能动态拼接。",
        example_formula='=HYPERLINK("#明细!A1", "跳到明细")',
        example_result="显示「跳到明细」，点一下跳到「明细」表的 A1。"
                       "做多表导航页最实用",
        pitfalls="① `#` 开头是**工作簿内跳转**，少了 # 会被当成文件名去找，提示找不到文件\n"
                 "② 打开非 http 链接时 Excel 可能弹安全警告，"
                 "公司环境里常被策略拦掉\n"
                 "③ 显示文字非空时会**覆盖单元格格式**，颜色 / 下划线由系统定，改不回来\n"
                 "④ 拼动态网址别忘了 ENCODEURL 处理中文与空格",
        use_cases="报表导航页；按编号跳到对应文件；动态生成搜索链接；"
                  "把责任单号做成可点击",
        related="CONCAT|TEXTJOIN|ENCODEURL|INDIRECT",
    ),
    F(
        code="TRANSPOSE", name_cn="转置", category="查找与引用",
        tags="动态数组", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="TRANSPOSE(数组)",
        args_desc="数组：要转置的区域",
        returns="行列互换后的数组（365 里会自动溢出；老版本需按区域数组公式输入）",
        description="把行变列、列变行。",
        example_formula="=TRANSPOSE(A1:D1)",
        example_result="横向的 4 个值变成竖排的 4 行。365 直接回车即可",
        pitfalls="① 365 里它是动态数组：结果区域要留空，否则 #SPILL!\n"
                 "② 老版本要**先选中目标区域**再按 Ctrl+Shift+Enter，否则只出第一个值\n"
                 "③ 转置**不保留格式**，只是值的重排；要保留格式请用「选择性粘贴 → 转置」\n"
                 "④ 一旦源数据行数变化，转置结果会自动跟着溢出变化（365）",
        use_cases="横表转竖表以便做数据透视 / VLOOKUP；把一行指标变成一列；"
                  "配 VSTACK 拼装报表",
        related="VSTACK|HSTACK|INDEX|TOCOL",
    ),

    # ==================================================================
    # 动态数组（365）
    # ==================================================================
    F(
        code="FILTER", name_cn="按条件筛出一组", category="查找与引用",
        tags=DYNAMIC + "|分水岭|强烈推荐", min_version="Excel 365",
        difficulty=3, importance=3,
        syntax="FILTER(数组, 条件, [无匹配时返回])",
        args_desc="数组：要筛选的区域（可多列）\n"
                  "条件：与数组**行数一致**的 TRUE/FALSE 数组，如 `$A$2:$A$100=\"华东\"`；"
                  "多个条件用 `*`（并且）、`+`（或者）连接\n"
                  "无匹配时返回：全都不满足时返回什么；省略则报 #CALC!",
        returns="满足条件的那些行（整行带出）；结果会自动「溢出」到下方单元格",
        description="按条件把符合条件的**整行**筛出来，替代筛选 + 复制粘贴这一整套手工动作。",
        example_formula='=FILTER(A2:D100, ($B$2:$B$100="华东")*($D$2:$D$100>1000), "没有符合条件的记录")',
        example_result="把「华东且金额大于 1000」的所有行整行带出到下方。"
                       "源表新增数据，结果自动跟着变",
        pitfalls="① **一定要写第三参数**，否则无匹配时整个格子显示 #CALC!，很难看\n"
                 "② 溢出区域右侧 / 下方**必须为空**，被占住会报 #SPILL!。"
                 "这是动态数组最常见的问题：目标区域里还留着旧的静态数据\n"
                 "③ 条件数组行数必须与数组一致，否则 #VALUE!\n"
                 "④ 「或者」用 `+` 时如果多个条件同时成立，求和会 >1，"
                 "要写成 `((A=1)+(B=2))>0` 才是纯粹的布尔筛选\n"
                 "⑤ 文本比较要套 TRIM / UPPER 处理脏数据，否则「华东 」匹配不上\n"
                 "⑥ 它只**引用**源数据，不会随源数据一起被修改；"
                 "要落到别处请复制 → 选择性粘贴 → 值\n"
                 "⑦ 只有 365 / 2021 支持",
        use_cases="按条件导出明细（替代筛选+复制）；做动态看板；"
                  "只显示未完成的清单；按大区拆分多张报表的中间层；配 SORT 做动态排行榜",
        related="UNIQUE|SORT|XLOOKUP|SUMIFS|IFERROR",
    ),
    F(
        code="UNIQUE", name_cn="去重", category="查找与引用",
        tags=DYNAMIC + "|强烈推荐", min_version="Excel 365",
        difficulty=2, importance=3,
        syntax="UNIQUE(数组, [按列], [仅出现一次])",
        args_desc="数组：要去重的区域（给多列就是「整行组合」去重）\n"
                  "按列：FALSE / 省略 = 按行比对；TRUE = 按列比对\n"
                  "仅出现一次：FALSE / 省略 = 每个不同的值各留一条；"
                  "TRUE = **只留只出现过一次的**（去掉重复出现的）",
        returns="去重后的值列表，自动溢出",
        description="一键提取不重复清单，替代「高级筛选 → 选择不重复的记录」那套老流程。",
        example_formula='=SORT(UNIQUE(A2:A1000))',
        example_result="把 A 列的去重清单按字母 / 数字顺序排出（外层 SORT 保证稳定顺序）。"
                       "**源表加数据，清单自动变长**",
        pitfalls="① 「A」和「a」、以及「华东」和「华东 」（多一个空格）会被当成不同的值，"
                 "去重前先 TRIM\n"
                 "② 第三个参数给 TRUE 是「只留唯一的」，和直觉相反，读题要慢\n"
                 "③ 同样会 #SPILL!，结果要与目标区域留白\n"
                 "④ 只有 365 / 2021 支持。给老版本的人看，只能先复制成值再发\n"
                 "⑤ 数字与文本型的 \"1\" 会算两条，清洗前先统一类型",
        use_cases="提取客户 / 产品 / 大区清单（做下拉菜单数据源）；"
                  "去重后计数；找「只出现过一次」的记录；配 SORT 生成稳定清单",
        related="SORT|FILTER|COUNTIF|SORTBY",
    ),
    F(
        code="SORT", name_cn="排序（动态）", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=3,
        syntax="SORT(数组, [排序索引], [排序顺序], [按列])",
        args_desc="数组：要排序的区域\n"
                  "排序索引：按**第几列 / 第几行**排（在数组内的序号）；省略为 1\n"
                  "排序顺序：1 = 升序（默认）；-1 = 降序\n"
                  "按列：FALSE / 省略 = 按行排序；TRUE = 按列排序",
        returns="排好序的数组，自动溢出",
        description="用公式排序，源数据不动，结果自动更新。",
        example_formula='=SORT(A2:D100, 4, -1)',
        example_result="按区域内第 4 列（D 列）降序排列整张表。"
                       "源表数据改了、加行删行，排序结果自动跟上",
        pitfalls="① **排序索引是「区域内的第几列」**，不是工作表的列号。"
                 "区域从 B 列开始时，想按 D 列排要写 3\n"
                 "② 排序是中文按拼音、数字按大小、文本按字典序混着的，"
                 "自定义顺序（如「高/中/低」）它做不到\n"
                 "③ 与筛选 / 数据透视的排序不同，它不改变源数据\n"
                 "④ 需要 365 / 2021",
        use_cases="动态排行榜；报表里的数据永远按金额降序；"
                  "与 FILTER 串联做「筛选后再排序」；给图表一个永远有序的数据源",
        related="SORTBY|UNIQUE|FILTER|LARGE",
    ),
    F(
        code="SORTBY", name_cn="按别的列排序", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=2,
        syntax="SORTBY(数组, 排序依据数组1, [排序顺序1], [排序依据数组2, 排序顺序2], …)",
        args_desc="数组：要排序的区域\n"
                  "排序依据数组1：按哪一列排（**给实际区域，不用给序号**）\n"
                  "排序顺序1：1 升序（默认）/ -1 降序\n"
                  "后续可再加排序依据，做多级排序",
        returns="排好序的数组，自动溢出",
        description="按「区域外的某一列」来排序，可以排多个层级。",
        example_formula='=SORTBY(A2:B100, D2:D100, -1, B2:B100, 1)',
        example_result="把 A:B 按 D 列降序排，D 相同时按 B 列升序 —— **多级排序一次写完**",
        pitfalls="① **排序依据数组不必是数组内的列**，这是它比 SORT 强的地方\n"
                 "② 所有数组行数必须一致\n"
                 "③ 做「随机排序」的经典写法：`=SORTBY(A2:A100, RANDARRAY(99))`\n"
                 "④ 需要 365 / 2021",
        use_cases="多级排序（先按大区再按金额）；用辅助列排序；随机打乱顺序",
        related="SORT|RANDARRAY|FILTER|UNIQUE",
    ),
    F(
        code="SEQUENCE", name_cn="生成序列", category="查找与引用",
        tags=DYNAMIC + "|造数据", min_version="Excel 365", difficulty=2, importance=3,
        syntax="SEQUENCE(行数, [列数], [起始值], [步长])",
        args_desc="行数：造几行\n列数：造几列，省略为 1\n"
                  "起始值：从几开始，省略为 1\n步长：每次加多少，省略为 1",
        returns="一个数字序列数组，自动溢出",
        description="一句话造出 1..N 的序列，是动态数组里最常用的「零件」。",
        example_formula="=SEQUENCE(12, 1, 1, 1)",
        example_result="竖排的 1 到 12。常用来做月份编号、序号列、"
                       "或给 RANDARRAY / INDEX 当索引",
        pitfalls="① 行 / 列数太大（比如几百万）会让 Excel 直接卡死甚至无响应，**先小量试**\n"
                 "② 它与 ROW(1:10) 效果类似，但 SEQUENCE 更直观且不依赖行号\n"
                 "③ 结果会溢出，目标区域要空着\n"
                 "④ 需要 365 / 2021",
        use_cases="生成连续序号 / 月份 / 星期；造测试数据；"
                  "给 MAP / INDEX 提供索引数组；做日历的行列骨架",
        related="RANDARRAY|ROW|MAKEARRAY|INDEX",
    ),
    F(
        code="RANDARRAY", name_cn="随机数组", category="查找与引用",
        tags=DYNAMIC + "|会重算", min_version="Excel 365", difficulty=2, importance=2,
        syntax="RANDARRAY([行数], [列数], [最小值], [最大值], [是否整数])",
        args_desc="行数 / 列数：造多大的数组，省略都是 1\n"
                  "最小值 / 最大值：取值范围，省略为 0~1\n"
                  "是否整数：TRUE = 返回整数；FALSE / 省略 = 小数",
        returns="随机数数组，自动溢出",
        description="一次造一整片随机数，配合 SORTBY 可以做「随机抽样 / 随机排序」。",
        example_formula="=SORTBY(A2:A100, RANDARRAY(ROWS(A2:A100)))",
        example_result="把 A 列随机打乱顺序。"
                       "抽奖、随机分组、随机抽查名单都用这一行",
        pitfalls="① **易失函数**：任何改动都会重新随机，**抽完立刻复制 → 粘贴为值**\n"
                 "② 行数要与被排序的区域一致，写法上用 ROWS(区域) 最稳\n"
                 "③ 会产生重复值（随机整数尤其），要「不重复抽样」得再加去重逻辑\n"
                 "④ 需要 365 / 2021",
        use_cases="随机抽签 / 抽样；随机分组；打乱名单顺序；造测试数据",
        related="SORTBY|RAND|SEQUENCE|RANDBETWEEN",
    ),
    F(
        code="TAKE", name_cn="取前 / 后 N 行", category="查找与引用",
        tags=DYNAMIC + "|实用", min_version="Excel 365", difficulty=2, importance=3,
        syntax="TAKE(数组, 行数, [列数])",
        args_desc="数组：源区域\n"
                  "行数：正数 = 取前几行；负数 = 取**后**几行\n"
                  "列数：同理（正 = 左几列，负 = 右几列）；省略则取全部列",
        returns="截取出来的子数组，自动溢出",
        description="从一大片数据里取前几行或后几行，代替 OFFSET 划动态区域的写法。",
        example_formula="=TAKE(A2:B1000, -7)",
        example_result="取最后 7 行 —— 「最近 7 天数据」一行公式搞定。"
                       "而且**不是易失函数**，比 OFFSET 快得多",
        pitfalls="① 行数超过实际行数会取到空行（显示 0），不报错\n"
                 "② 取「最后 N 行」注意源区域里有没有空行尾部，"
                 "空行会被算进「行数」里\n"
                 "③ 需要 365 / 2021",
        use_cases="最近 N 天 / 最近 N 条；只看前 10 名；"
                  "配合 SORT 做「排序后取前 10」；截掉表头行",
        related="DROP|FILTER|SORT|OFFSET",
    ),
    F(
        code="DROP", name_cn="丢掉前 / 后 N 行", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=2,
        syntax="DROP(数组, 行数, [列数])",
        args_desc="数组：源区域\n"
                  "行数：正数 = 从**开头**丢掉几行；负数 = 从**末尾**丢掉几行\n"
                  "列数：同理；省略则不动列",
        returns="剩下的子数组，自动溢出",
        description="TAKE 的反面：从头上或尾巴上砍掉几行，最常用是砍掉表头。",
        example_formula="=DROP(A1:B100, 1)",
        example_result="砍掉第 1 行（表头），只剩数据体。"
                       "做「标题占多行」的报表数据源特别好用",
        pitfalls="① 与 TAKE 的正负号含义一致：正 = 从开头，负 = 从末尾\n"
                 "② 丢掉的行数超过总数会返回 #CALC!\n"
                 "③ 需要 365 / 2021",
        use_cases="去掉表头只留数据；去掉合计行；去掉最后的总结行",
        related="TAKE|FILTER|CHOOSEROWS",
    ),
    F(
        code="CHOOSEROWS", name_cn="挑指定行", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=2,
        syntax="CHOOSEROWS(数组, 行号1, [行号2], …)",
        args_desc="数组：源区域\n"
                  "行号：要保留的第几行（相对区域的序号）；负数 = 从末尾数",
        returns="由指定行拼成的新数组，自动溢出",
        description="按行号把指定几行挑出来，顺序可以自定义、也能重复。",
        example_formula="=CHOOSEROWS(A2:D100, 1, 5, 9)",
        example_result="只取区域内的第 1、5、9 行，拼成一个 3 行的小表。"
                       "配合 LARGE/MATCH 可以取「销售额前 3 名所在的行」",
        pitfalls="① 行号是**区域内**的序号，不是工作表行号\n"
                 "② 行号可以重复（同一行取两次），也可以乱序（顺便实现重排）\n"
                 "③ 需要 365 / 2021",
        use_cases="取指定的几行（如第 1 名、第 2 名、第 3 名）；"
                  "重排行的顺序；与 MATCH 配合按条件取行",
        related="CHOOSECOLS|TAKE|DROP|INDEX",
    ),
    F(
        code="CHOOSECOLS", name_cn="挑指定列", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=3,
        syntax="CHOOSECOLS(数组, 列号1, [列号2], …)",
        args_desc="数组：源区域\n"
                  "列号：要保留的第几列（相对区域的序号）；负数 = 从右边数",
        returns="由指定列拼成的新数组，自动溢出",
        description="从一堆列里只挑出要的那几列，还能顺手调整顺序。",
        example_formula="=CHOOSECOLS(A2:F100, 1, 4, 6)",
        example_result="只保留第 1、4、6 列，组成一个精简表。"
                       "**做「从宽表里抽 3 列给别人」这件事，一行搞定**",
        pitfalls="① 列号是**区域内**的序号。区域从 B 列开始时，"
                 "想取 D 列要写 3，不是 4 —— 这是最高频的错\n"
                 "② 列号可重复、可乱序，所以它也能当「列重排」用\n"
                 "③ 导出给别人前记得复制 → 粘贴为值（对方可能没有 365）\n"
                 "④ 需要 365 / 2021",
        use_cases="从宽表抽指定列；调整列顺序以便导出；"
                  "配 FILTER 做「筛选 + 选列」的报表；隐藏中间的计算列",
        related="CHOOSEROWS|FILTER|HSTACK|VSTACK",
    ),
    F(
        code="VSTACK", name_cn="纵向拼接", category="查找与引用",
        tags=DYNAMIC + "|汇总利器", min_version="Excel 365", difficulty=2, importance=3,
        syntax="VSTACK(数组1, [数组2], …)",
        args_desc="数组1：第一块数据（要带表头）\n"
                  "数组2…：往下接的每一块，顺序就是拼接顺序",
        returns="纵向堆在一起的新数组，自动溢出",
        description="把多张结构相同的表纵向拼成一张，多表汇总的现代写法。",
        example_formula='=VSTACK(表1!A1:D1, FILTER(表1!A2:D100, 表1!A2:A100<>""), '
                        'FILTER(表2!A2:D100, 表2!A2:A100<>""))',
        example_result="把表1、表2 的数据带表头拼成一张长表。"
                       "配合 UNIQUE / SUMIFS / 数据透视就能做跨表汇总",
        pitfalls="① **列数不一致会补齐 #N/A**，看起来像数据缺失，其实是因为某块少了一列\n"
                 "② 各块列的顺序必须一致：Excel 只按位置拼，不认表头名。"
                 "列顺序不同的两块拼在一起会静默错位，**这是最危险的地方**\n"
                 "③ 用 CHOOSECOLS 把每块的列顺序统一后再拼，是稳妥做法\n"
                 "④ 拼 12 个月的表比 INDIRECT 循环更可读、也不会因为改表名而崩\n"
                 "⑤ 需要 365 / 2021",
        use_cases="多张同结构表汇总（12 个月 / 多个分公司）；"
                  "加一行「合计」；把小表拼成大表再做透视",
        related="HSTACK|FILTER|CHOOSECOLS|UNIQUE",
    ),
    F(
        code="HSTACK", name_cn="横向拼接", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=2,
        syntax="HSTACK(数组1, [数组2], …)",
        args_desc="数组1：最左边那块\n数组2…：往右接的每一块",
        returns="横向并排组成的新数组，自动溢出",
        description="把几块数据横向并排，或给一块数据补上计算列。",
        example_formula="=HSTACK(A2:A100, B2:B100*C2:C100)",
        example_result="A 列原文 + 一列「金额（单价×数量）」并排输出，"
                       "**不用先在表里插一列再写公式**",
        pitfalls="① 各块**行数不一致时短的那块尾部补 #N/A**\n"
                 "② 各列宽窄不影响结果，但类型会各自保留（文本 + 数字可混排）\n"
                 "③ 需要 365 / 2021",
        use_cases="给筛选结果补一列计算值；把两个来源的列并排；"
                  "做报表的「指标 + 同比」并排展示",
        related="VSTACK|CHOOSECOLS|FILTER",
    ),
    F(
        code="TOCOL", name_cn="拉成一列", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=2,
        syntax="TOCOL(数组, [忽略哪些], [按行还是按列扫])",
        args_desc="数组：源区域\n"
                  "忽略哪些：0 = 全都要（默认）；1 = 忽略空白；2 = 忽略错误；3 = 两者都忽略\n"
                  "扫描方式：FALSE / 省略 = 一行行扫（先横后竖）；TRUE = 一列列扫",
        returns="把整片数据拉直成一列，自动溢出",
        description="把二维区域拉成一维长列，做去重 / 计数 / 透视前常要的一步。",
        example_formula="=UNIQUE(TOCOL(B2:H100, 1))",
        example_result="把 B2:H100 这一整片（多行多列）拉成一列、去掉空白、再去重，"
                       "得到全表出现过的所有「问题类型」。"
                       "**这是「多列里找唯一值」最省事的写法**",
        pitfalls="① 忽略选项的含义要记牢：**1 是忽略空白、2 是忽略错误**，容易记反\n"
                 "② 扫描顺序影响结果顺序，想让它可复现就套一层 SORT\n"
                 "③ 大片区域拉直后行数会很多，注意别溢出到已有数据上\n"
                 "④ 需要 365 / 2021",
        use_cases="多列去重（把宽度不一的分类列拉直）；"
                  "交叉表转长表以便透视；统计「一共出现过哪些值」",
        related="TOROW|UNIQUE|WRAPROWS|VSTACK",
    ),
    F(
        code="TOROW", name_cn="拉成一行", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=2, importance=1,
        syntax="TOROW(数组, [忽略哪些], [按行还是按列扫])",
        args_desc="参数含义与 TOCOL 完全一致：\n"
                  "忽略哪些：0 全要 / 1 忽略空白 / 2 忽略错误 / 3 两者\n"
                  "扫描方式：省略按行扫；TRUE 按列扫",
        returns="把整片数据拉直成一行，自动溢出",
        description="TOCOL 的横向版本，把区域拉成一行。",
        example_formula="=TOROW(B2:D5, 1)",
        example_result="把 B2:D5 拉成一行、跳过空白。"
                       "做横向的清单展示或喂给需要一维输入的函数",
        pitfalls="① 与 TOCOL 只差输出方向，参数含义一样\n"
                 "② 拉成一行后横向占用很多列，注意别撞到已有数据\n"
                 "③ 需要 365 / 2021",
        use_cases="把多行数据摊成一行展示；为一维输入的函数准备数据",
        related="TOCOL|UNIQUE|HSTACK",
    ),
    F(
        code="EXPAND", name_cn="补齐到指定尺寸", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=3, importance=1,
        syntax="EXPAND(数组, 行数, [列数], [填充值])",
        args_desc="数组：源数据\n"
                  "行数 / 列数：要撑到多大（必须不小于原尺寸）\n"
                  "填充值：多出来的位置填什么；省略则填 #N/A",
        returns="补齐后的数组，自动溢出",
        description="把一块数组撑到指定大小，缺的位置用指定值填上。",
        example_formula='=EXPAND(B2:D5, 8, 3, "")',
        example_result="把 4 行的数据撑到 8 行，多出的行留空。"
                       "让几块要 VSTACK 的数据行数一致时很有用",
        pitfalls="① **默认填充值是 #N/A**，不写第 4 参数会满屏 #N/A，很吓人\n"
                 "② 目标尺寸比原数据小会报 #VALUE!，它只能放大不能缩小\n"
                 "③ 需要 365 / 2021",
        use_cases="把几块尺寸不一的数组补齐后再 VSTACK / HSTACK；"
                  "给图表准备固定行数的数据区",
        related="VSTACK|HSTACK|TAKE|WRAPROWS",
    ),
    F(
        code="WRAPROWS", name_cn="折成多行", category="查找与引用",
        tags=DYNAMIC, min_version="Excel 365", difficulty=3, importance=2,
        syntax="WRAPROWS(向量, 每行几个, [填充值])",
        args_desc="向量：一维的数据（一行或一列）\n"
                  "每行几个：折成每行放几个元素\n"
                  "填充值：最后一行不够时补什么；省略补 #N/A",
        returns="折好的二维数组，自动溢出",
        description="把一长条数据按固定个数折成多行 —— 一维转二维的常用件。",
        example_formula="=WRAPROWS(SEQUENCE(20), 5)",
        example_result="1..20 折成 4 行 5 列的矩阵。"
                       "做「把清单排成 N 列的卡片墙」或「批量生成排班表」就靠它",
        pitfalls="① **默认补 #N/A**，最后一行不满时会出现 #N/A，"
                 "一般要显式写第 3 参数给 \"\"\n"
                 "② 源数据必须是**一维**的；二维要先用 TOCOL 拉直\n"
                 "③ 需要 365 / 2021",
        use_cases="把长清单排成多列（打印卡片 / 标签）；"
                  "把一列数据变成周排班矩阵；生成固定宽度的报表块",
        related="WRAPCOLS|TOCOL|SEQUENCE|EXPAND",
    ),
    F(
        code="MAP", name_cn="逐元素变换", category="查找与引用",
        tags=DYNAMIC + "|高级|函数式", min_version="Excel 365", difficulty=4,
        importance=2,
        syntax="MAP(数组1, [数组2], …, LAMBDA(参数…, 计算式))",
        args_desc="数组1…：要逐个遍历的一到多个数组（**长度必须一致**）\n"
                  "LAMBDA：接收同样多个参数，返回这一对元素的处理结果",
        returns="与输入同尺寸的数组，自动溢出",
        description="把「对每个元素做同一件事」写成一行公式，替代下拉填充 + 辅助列。",
        example_formula='=MAP(A2:A100, LAMBDA(编号, IF(ISNUMBER(XMATCH(编号, 黑名单!A:A)), "拦截", "放行")))',
        example_result="对 A2:A100 每一个编号判断是否在黑名单里，"
                       "**一次算出整列结果**，不用先写一个再往下拉",
        pitfalls="① LAMBDA 的参数个数必须与数组个数一致，否则 #VALUE!\n"
                 "② 所有数组长度必须相同\n"
                 "③ 里面**不能**引用会变动的区域做「跨行聚合」，"
                 "MAP 是逐元素、不共享中间状态；要累积用 REDUCE / SCAN\n"
                 "④ 公式对非 365 用户不可见（显示 _xlfn.MAP），交付前要转成值\n"
                 "⑤ 调试困难：出错时只告诉你「LAMBDA 有问题」，"
                 "建议先在单个单元格上把内层逻辑试通",
        use_cases="整列批量替换 / 清洗；批量查黑名单；"
                  "把繁琐的下拉填充公式收成一个动态结果",
        related="REDUCE|SCAN|BYROW|LAMBDA|LET",
    ),
    F(
        code="REDUCE", name_cn="累积归约", category="查找与引用",
        tags=DYNAMIC + "|高级|函数式", min_version="Excel 365", difficulty=4,
        importance=2,
        syntax="REDUCE([初始值], 数组, LAMBDA(累积值, 当前值, 计算式))",
        args_desc="初始值：累积器的起点（**建议一定要给**，否则用数组首项当起点）\n"
                  "数组：要遍历的数据\n"
                  "LAMBDA：接收「到目前为止的累积值」与「当前元素」，返回新的累积值",
        returns="**单个**最终结果（不是数组）",
        description="把一串数据「一路卷起来」算成一个结果，比如拼接字符串、累乘、复杂校验。",
        example_formula='=REDUCE("", A2:A10, LAMBDA(累积, 当前, 累积 & 当前 & "、"))',
        example_result="把 A2:A10 用「、」连成一个长串（相当于 TEXTJOIN，"
                       "但能塞进更复杂的逻辑）。**返回一个值，不溢出**",
        pitfalls="① 它**返回一个值**，和 MAP / SCAN 的数组返回完全不同，别混\n"
                 "② 初始值省略时用数组第一个元素当起点，"
                 "想「累计拼接」却忘了给 \"\" 会丢掉第一个元素\n"
                 "③ 大数据量很慢：它本质是逐元素循环，几万行会明显卡\n"
                 "④ 想「每步都留一个中间结果」要用 SCAN，不是 REDUCE\n"
                 "⑤ 只有 365 / 2021",
        use_cases="字符串累积拼接；带条件的连续累加（如「连续达标天数」）；"
                  "多重校验收敛成一个结论；自定义的复杂聚合",
        related="SCAN|MAP|BYROW|LAMBDA|TEXTJOIN",
    ),
    F(
        code="SCAN", name_cn="累积并保留每步", category="查找与引用",
        tags=DYNAMIC + "|高级|函数式", min_version="Excel 365", difficulty=4,
        importance=2,
        syntax="SCAN([初始值], 数组, LAMBDA(累积值, 当前值, 计算式))",
        args_desc="初始值：累积器的起点\n"
                  "数组：要遍历的数据\n"
                  "LAMBDA：返回新的累积值；**每一步的结果都会被留下**",
        returns="与输入同长度的数组，每一步的累积结果，自动溢出",
        description="像 REDUCE 一样累积，但把每一步的结果都留下来 —— 做累计求和 / 累计计数。",
        example_formula="=SCAN(0, C2:C100, LAMBDA(累积, 当前, 累积 + 当前))",
        example_result="C 列的**累计求和**：第 5 行显示前 5 行之和。"
                       "做「累计达成率」「滚动总额」一行搞定，不用辅助列",
        pitfalls="① 与 REDUCE 的区别只有一点：SCAN 返回**每一步的数组**，"
                 "REDUCE 只返回最后那一个值\n"
                 "② 「按分组重新开始累计」它做不到，"
                 "需要复杂的 LAMBDA 或回到辅助列写法\n"
                 "③ 结果会溢出，目标区域要空着\n"
                 "④ 只有 365 / 2021",
        use_cases="累计求和（正态分布曲线 / 达成率曲线）；"
                  "累计计数；跑动余额；配 IF 做「连续达标天数」",
        related="REDUCE|MAP|BYROW|LAMBDA|SUM",
    ),
    F(
        code="BYROW", name_cn="按行汇总", category="查找与引用",
        tags=DYNAMIC + "|高级|函数式", min_version="Excel 365", difficulty=4,
        importance=2,
        syntax="BYROW(数组, LAMBDA(行, 计算式))",
        args_desc="数组：要按行处理的区域\n"
                  "LAMBDA：接收「一整行」作为参数，返回这一行的汇总值",
        returns="每行一个结果的**竖排**数组（行数与原表相同）",
        description="对每一行做同样的汇总，比如「每行算一次最大值 / 是否全部达标」。",
        example_formula='=BYROW(B2:E100, LAMBDA(行, IF(COUNTIF(行, "不达标")>0, "有问题", "OK")))',
        example_result="B:E 每一行里只要有「不达标」就标记「有问题」。"
                       "**一整列结论一次算出**，比写 99 个公式干净",
        pitfalls="① LAMBDA 收到的是**整行**（一个数组），所以里面能用 SUM / COUNTIF 这类聚合函数\n"
                 "② 返回的是竖排数组，与行数一致 —— 想横向摊开要再套 TRANSPOSE\n"
                 "③ 逐行循环，**大数据量会慢**；几万行建议还是用辅助列 + SUMIFS\n"
                 "④ 只有 365 / 2021",
        use_cases="每行做一次判定 / 汇总；一行里有任一异常就整体标红；"
                  "按行算指标而不加辅助列",
        related="BYCOL|MAP|REDUCE|SCAN|SUMPRODUCT",
    ),
    F(
        code="BYCOL", name_cn="按列汇总", category="查找与引用",
        tags="动态数组|365新增|高级|函数式", min_version="Excel 365",
        difficulty=4, importance=2,
        syntax="BYCOL(数组, LAMBDA(列, 计算式))",
        args_desc="数组：要按列处理的区域\n"
                  "LAMBDA：接收「一整列」作为参数，返回这一列的汇总值（如 SUM / COUNTA）",
        returns="每列一个结果的**横排**数组（列数与原表相同）",
        description="对每一列做同样的汇总，与 BYROW 互为横竖版本。",
        example_formula="=BYCOL(B2:E100, LAMBDA(列, SUM(列)))",
        example_result="一次算出 B、C、D、E 四列的合计，横向摊开。"
                       "**以前要写 4 个 SUM，现在一行**",
        pitfalls="① 返回的是**横排**数组（与列数一致），与 BYROW 的竖排相反\n"
                 "② 同样逐列循环，列数 × 行数很大时慢\n"
                 "③ 只有 365 / 2021",
        use_cases="一次算出多列合计 / 多列去重计数；做多指标汇总行；"
                  "对每列做同一套清洗",
        related="BYROW|MAP|SUMPRODUCT|SEQUENCE",
    ),
]
