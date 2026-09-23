# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（七）补齐片
================================================================================
共 46 个条目，字段规范见 ``excel_seed_schema``。

这一片的来历
--------------------------------------------------------------------------------
前面六个分片写完，全库已经有 154 个函数。但把每条的 ``related``（相关函数）
拉出来一对，发现指向了 46 个「提到但没详解」的名字 ——
比如 HOUR 旁边挂着 MINUTE / SECOND，TRIM 旁边挂着 CLEAN / LENB。

留着这个缺口有两个坏处：
1. 界面上「相关函数」点不动，学习链条断在半路；
2. 时间一长，这些名字到底是我们库里的还是拼错的，没人分得清。

所以补上。补完后的硬约束是：**``related`` 里出现的每一个函数名，库里都必须有。**
这条约束写进了 ``scripts/test_excel.py``，往后再手抖打错名字会直接测试失败。

这一片的条目写得比前面短：它们多数是被「顺带提到」的配角，
重点是「什么时候会用到它」以及「最容易记错的那一处」。
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    # ==================================================================
    # 数学与三角函数 · 补齐
    # ==================================================================
    F(
        code="TRUNC", name_cn="截断取整", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="TRUNC(数值, [位数])",
        args_desc="数值：要截断的值\n位数：保留几位小数；省略为 0；负数对十 / 百位截断",
        returns="直接砍掉多余小数位的结果（**不做四舍五入**）",
        description="按位数截断，不做舍入。",
        example_formula="=TRUNC(-9.99)",
        example_result="→ -9。"
                       "注意 INT(-9.99) 是 **-10**："
                       "INT 是「向下」、TRUNC 是「朝零」，负数场景完全不同",
        pitfalls="① **负数上与 INT 不一致**，这是选它还是选 INT 的唯一判据\n"
                 "② 与 ROUNDDOWN 行为一致，但名字更直白，负数场景建议用它",
        use_cases="取整不算进（不满一个不算）；负数金额抹零；"
                  "与 INT 按需互换",
        related="INT|ROUNDDOWN|ROUND|MOD",
    ),
    F(
        code="SIGN", name_cn="取符号", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="SIGN(数值)",
        args_desc="数值：任意数字",
        returns="正数返回 1，0 返回 0，负数返回 -1",
        description="判断一个数是正、零还是负。",
        example_formula="=B2-C2*SIGN(B2-C2)",
        example_result="把差值换成绝对值。"
                       "更常见的用法是配条件格式或做涨跌方向判断",
        pitfalls="① 它只给三种结果，**不给你差多少**，"
                 "所以基本总要再配 ABS 或乘法才有用\n"
                 "② 文本参数返回 #VALUE!",
        use_cases="涨跌方向标记；分正负段做不同处理；"
                  "与 ABS 搭配把值「正负化」",
        related="ABS|IF|MOD",
    ),
    F(
        code="QUOTIENT", name_cn="整除取商", category="数学与三角函数",
        tags="", min_version="Excel 2007", difficulty=2, importance=2,
        syntax="QUOTIENT(被除数, 除数)",
        args_desc="被除数：要除的数\n除数：除以多少",
        returns="商的整数部分（**朝零截断**）",
        description="整除取商，忽略余数。",
        example_formula="=QUOTIENT(B2, 12)",
        example_result="37 → 3。"
                       "「37 件按每箱 12 件能装几整箱」直接就是它；"
                       "余数是 MOD(B2, 12) 的活儿",
        pitfalls="① 除数为 0 返回 #DIV/0!\n"
                 "② 负数是朝零截断（-37/12 → -3），与 INT 的向下不同\n"
                 "③ 它**不告诉你余数**，要余数用 MOD，两个一起才是完整的「带余除法」",
        use_cases="按整箱 / 整打折算数量；分页页码；"
                  "把总数拆成「多少个完整的组 + 余数」",
        related="MOD|INT|TRUNC",
    ),
    F(
        code="POWER", name_cn="乘方", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="POWER(底数, 指数)",
        args_desc="底数：要求的数\n指数：几次方（可小数 = 开方；可负数 = 取倒数）",
        returns="底数的指数次幂",
        description="算乘方。",
        example_formula="=POWER(B2, 1/12)",
        example_result="把「12 个月的累计增长率 B2」折算成月均增长率。"
                       "**开方就是指数给分数**，比 1/2 次方写成 SQRT 更统一",
        pitfalls="① 负数开分数次方会 #NUM!（数学上不是实数）\n"
                 "② 底数 0、指数负数会 #DIV/0!\n"
                 "③ 写 `B2^2` 比 POWER 更短，熟练后用 `^` 就行",
        use_cases="复利 / 复合增长率反算月均；平方 / 立方；开方；"
                  "幂函数拟合",
        related="EXP|SQRT|PRODUCT|LOG",
    ),
    F(
        code="EXP", name_cn="自然指数", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="EXP(数值)",
        args_desc="数值：e 的几次方",
        returns="e 的该次幂（e ≈ 2.718281828）",
        description="算 e 的次幂，是 LN 的反函数。",
        example_formula="=EXP(B2)-1",
        example_result="B2 是连续复利增长率时，转成普通增长率。"
                       "做金融建模时会用到",
        pitfalls="① 数值太大（>709）会溢出成 #NUM!\n"
                 "② 与 POWER 的关系：`EXP(x)` = `POWER(e, x)`，日常算复利用 POWER 更直观\n"
                 "③ 它是 LN 的反函数，反算时要成对使用",
        use_cases="连续复利折算；对数回归还原；"
                  "与 LN 配对做变换",
        related="LN|POWER|LOG",
    ),

    # ==================================================================
    # 统计 · 补齐
    # ==================================================================
    F(
        code="RANK.AVG", name_cn="排名（并列取平均）", category="统计",
        tags="", min_version="Excel 2010", difficulty=2, importance=1,
        syntax="RANK.AVG(数值, 引用, [排序方式])",
        args_desc="参数与 RANK.EQ 一致（0 或省略降序，1 升序）",
        returns="名次；**并列时取这些名次的平均值**",
        description="排名时并列取平均的版本。",
        example_formula="=RANK.AVG(B2, $B$2:$B$100, 0)",
        example_result="两个并列第 2 会各得 **2.5**，"
                       "而 RANK.EQ 给两个都是 2、后面直接跳 4",
        pitfalls="① 结果是小数（2.5），做「第几名」展示时要自己取整或说明口径\n"
                 "② 与 RANK.EQ 的选择是业务口径问题，"
                 "**体育比赛 / 考试成绩通常用 RANK.EQ**，"
                 "统计学术场景才会用 AVG\n"
                 "③ 需要 2010 及以上",
        use_cases="需要「并列平分名次」的统计场景；"
                  "与 RANK.EQ 对照检查排名逻辑",
        related="RANK.EQ|RANK|SUMPRODUCT|LARGE",
    ),
    F(
        code="VAR.S", name_cn="样本方差", category="统计",
        tags="", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="VAR.S(数值1, [数值2], …)",
        args_desc="数值1：数字或区域（样本）\n数值2…：最多再给 254 个",
        returns="样本方差（分母 n-1）",
        description="衡量离散程度的方差（样本口径）。",
        example_formula="=VAR.S(B2:B100)",
        example_result="标准差的平方。"
                       "**它的单位是「原单位的平方」**，所以展示时通常用 STDEV.S 更直观",
        pitfalls="① 样本用 ``.S``（n-1）、总体用 ``.P``（n），写错口径会被一眼看出\n"
                 "② 单位不直观（元的平方），做汇报请用 STDEV.S\n"
                 "③ 只有一个数据点时 .S 会 #DIV/0!\n"
                 "④ 老写法 ``VAR`` 与 .S 等价",
        use_cases="方差分析；风险评估；"
                  "需要「离散程度的平方」做中间计算时",
        related="STDEV.S|STDEV.P|AVERAGE|CORREL",
    ),
    F(
        code="STDEV.P", name_cn="总体标准差", category="统计",
        tags="", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="STDEV.P(数值1, [数值2], …)",
        args_desc="数值1：数字或区域（**全部**数据）\n数值2…：最多再给 254 个",
        returns="总体标准差（分母 n）",
        description="总体口径的标准差。",
        example_formula="=STDEV.P(B2:B100)",
        example_result="与 STDEV.S 相比结果**略小**（分母更大）。"
                       "B 列是全公司所有人的数据时用 .P，"
                       "是从中抽样的一部分时用 .S",
        pitfalls="① **口径选择要看数据是不是「总体」**："
                 "手上就是全部数据 → .P；只是抽样 → .S。"
                 "报数据时必须写清口径\n"
                 "② 老写法 ``STDEVP``（多一个 P）与它等价，两个 P 别数漏\n"
                 "③ 只有一个数据点时 .P 返回 0（不像 .S 报错）",
        use_cases="全量数据的波动分析；质量控制的整体标准差；"
                  "与 STDEV.S 对照说明口径",
        related="STDEV.S|VAR.S|AVERAGE|CORREL",
    ),
    F(
        code="QUARTILE.INC", name_cn="四分位", category="统计",
        tags="", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="QUARTILE.INC(数组, 四分位值)",
        args_desc="数组：数据区域\n"
                  "四分位值：0 最小值／1 第 25%／2 中位数／3 第 75%／4 最大值",
        returns="对应四分位的数值（含端点口径）",
        description="取四分位，做「中间 50% 落在什么区间」的判断。",
        example_formula="=QUARTILE.INC(B2:B100, 3) - QUARTILE.INC(B2:B100, 1)",
        example_result="第 75% 与第 25% 之差，即**四分位距（IQR）**。"
                       "常用它当「正常范围」，超出的当异常值",
        pitfalls="① 四分位值必须给 0~4 的整数；给小数会截断、给 5 会 #NUM!\n"
                 "② ``.INC`` 含端点、``.EXC`` 不含，**两者结果不同**，报口径要说清\n"
                 "③ 老写法 ``QUARTILE`` 与 .INC 等价\n"
                 "④ 箱线图的口径正是它，做图前先确认用哪个",
        use_cases="算 IQR 找异常值；数据分布描述；箱线图；"
                  "薪酬区间分析",
        related="PERCENTILE.INC|MEDIAN|STDEV.S|TRIMMEAN",
    ),
    F(
        code="MODE.MULT", name_cn="全部众数", category="统计",
        tags="", min_version="Excel 2010", difficulty=3, importance=1,
        syntax="MODE.MULT(数值1, [数值2], …)",
        args_desc="数据区域（可给多个）",
        returns="**所有**出现次数最多的值，竖排溢出；无重复值返回 #N/A",
        description="并列众数全部返回（MODE.SNGL 只给第一个）。",
        example_formula="=MODE.MULT(B2:B100)",
        example_result="如果 3 和 7 并列最多，就竖排返回 3、7 两个值；"
                       "MODE.SNGL 只会给 3",
        pitfalls="① 结果**溢出到下方**，下方要留空，否则 #SPILL!\n"
                 "② 无重复值返回 #N/A\n"
                 "③ 它是数组函数，老版本要按 Ctrl+Shift+Enter 选中区域后输入\n"
                 "④ 需要 2010 及以上",
        use_cases="并列众数分析；找出「最常出现的几种」；"
                  "数据热点分析",
        related="MODE.SNGL|COUNTIF|UNIQUE|FREQUENCY",
    ),
    F(
        code="TRIMMEAN", name_cn="截尾平均", category="统计",
        tags="抗极端值", min_version="Excel 2007", difficulty=3, importance=1,
        syntax="TRIMMEAN(数组, 要削去的比例)",
        args_desc="数组：数据区域\n"
                  "要削去的比例：**两端合计**削掉的比例，如 0.2 = 上下各 10%",
        returns="削掉两端极值后的平均值",
        description="去掉最高和最低的一部分再求平均，比 AVERAGE 抗极端值。",
        example_formula="=TRIMMEAN(B2:B100, 0.2)",
        example_result="两端各去掉 10% 后的平均，"
                       "**评分 / 打分场景里最常用**（去掉最高分和最低分）",
        pitfalls="① 参数是**两端合计**的比例（0.2 表示上下各 10%），"
                 "这是最容易理解错的地方\n"
                 "② 削去的个数会**向下取整到偶数**，"
                 "所以「10 个数据削 1 个」这种需求它做不到\n"
                 "③ 它就是「去掉最高最低分」的正式版，比自己做排序再平均稳",
        use_cases="比赛打分去极值；绩效考核去极值；"
                  "服务评分的稳健均值",
        related="AVERAGE|MEDIAN|QUARTILE.INC|LARGE",
    ),
    F(
        code="SLOPE", name_cn="回归斜率", category="统计",
        tags="", min_version="Excel 2003", difficulty=3, importance=1,
        syntax="SLOPE(因变量区域, 自变量区域)",
        args_desc="因变量：Y 值区域（**写在第一个**）\n"
                  "自变量：X 值区域（个数必须相同）",
        returns="线性回归直线的斜率",
        description="算两组数据线性关系的斜率（X 每变 1，Y 变多少）。",
        example_formula="=SLOPE(B2:B100, A2:A100)",
        example_result="投入每增加 1 单位，销量增加多少。"
                       "配 INTERCEPT 能拼出完整的回归方程",
        pitfalls="① **参数顺序是「Y, X」**，与 y=ax+b 的书写顺序不同，极易反\n"
                 "② 两组数据个数必须相同\n"
                 "③ 它只给斜率，不给截距（要 INTERCEPT）也不给拟合优度（要 RSQ）\n"
                 "④ 有多个自变量时它不够用，要用 LINEST",
        use_cases="算单位边际效应；趋势线的斜率；"
                  "简单线性关系的量化",
        related="CORREL|FORECAST.LINEAR|STDEV.S|AVERAGE",
    ),
    F(
        code="FORECAST.LINEAR", name_cn="线性预测", category="统计",
        tags="", min_version="Excel 2016", difficulty=3, importance=2,
        syntax="FORECAST.LINEAR(要预测的 X, 已知 Y 区域, 已知 X 区域)",
        args_desc="要预测的 X：给一个新的自变量\n"
                  "已知 Y 区域：历史结果\n已知 X 区域：历史自变量",
        returns="按线性回归预测出的 Y 值",
        description="基于历史数据做线性外推预测。",
        example_formula="=FORECAST.LINEAR(13, $B$2:$B$13, $A$2:$A$13)",
        example_result="已知 1~12 月的数值，预测第 13 个月。"
                       "**注意参数顺序是「新 X, Y 区域, X 区域」**",
        pitfalls="① **参数顺序很反直觉**：第一个是新 X，然后才是 Y、X。"
                 "写反了不报错但结果无意义\n"
                 "② 它只做**线性**外推：趋势是曲线（指数增长）时结果会越来越偏\n"
                 "③ 外推越远越不可靠，别拿 12 个月数据预测 3 年后\n"
                 "④ 老写法 ``FORECAST`` 与它等价",
        use_cases="按趋势预测下期销量；"
                  "算目标值对应的投入；简单的时间序列外推",
        related="SLOPE|CORREL|TREND|AVERAGE",
    ),

    # ==================================================================
    # 文本 · 补齐
    # ==================================================================
    F(
        code="CLEAN", name_cn="删不可打印字符", category="文本",
        tags="清洗必备", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="CLEAN(文本)",
        args_desc="文本：要清理的字符串",
        returns="删掉所有 ASCII 0~31 的不可打印字符后的文本",
        description="删掉换行、制表符这类看不见却会让匹配失败的控制字符。",
        example_formula="=TRIM(CLEAN(A2))",
        example_result="先删控制字符再删空格，"
                       "**这是「查找匹配不上」的标准修复组合**",
        pitfalls="① **它对 CHAR(160) 非断行空格无效** —— "
                 "从网页复制来的数据里全是这种空格，还得另配 "
                 "`SUBSTITUTE(A2, CHAR(160), \"\")`\n"
                 "② 它不删普通空格（那是 TRIM 的活儿），两个要一起用\n"
                 "③ 中文全角空格它也删不掉",
        use_cases="导入数据后的第一道清洗；查找匹配失败时的排查；"
                  "删掉从系统导出时带的行尾控制符",
        related="TRIM|SUBSTITUTE|CHAR|LEN",
    ),
    F(
        code="LENB", name_cn="按字节计长度", category="文本",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="LENB(文本)",
        args_desc="文本：要测量的字符串",
        returns="字节数；**中文一个字算 2 个字节**（DBCS 口径）",
        description="按字节算长度，中文算 2。",
        example_formula="=LENB(A2)-LEN(A2)",
        example_result="这个差值正好等于**中文字的个数**。"
                       "想「统计中文字数」就靠这一行",
        pitfalls="① 它是 DBCS 口径，只在中文 / 日文 / 韩文环境里符合直觉；"
                 "**换到纯英文系统行为会不同**\n"
                 "② 报文长度校验（如短信 70 字 / 银行定长字段）才需要它，"
                 "日常算长度用 LEN 就够",
        use_cases="校验定长报文；统计中文字数；"
                  "短信 / 字段长度限制判断",
        related="LEN|MID|LEFT|UNICHAR",
    ),
    F(
        code="NUMBERVALUE", name_cn="按指定分隔符转数字", category="文本",
        tags="清洗|跨区域", min_version="Excel 2013", difficulty=3, importance=1,
        syntax="NUMBERVALUE(文本, [小数点分隔符], [分组分隔符])",
        args_desc="文本：要转换的内容\n"
                  "小数点分隔符：本机不认的小数点样式，如 \",\"（欧式）\n"
                  "分组分隔符：千分位样式，如 \".\"（欧式）",
        returns="转换后的数值；不认的格式返回 #VALUE!",
        description="处理「欧式数字格式」的转换：1.234,56 这种。",
        example_formula='=NUMBERVALUE("1.234,56", ",", ".")',
        example_result="→ 1234.56。"
                       "**VALUE 处理不了这个**：它按本机区域设置解析，"
                       "会把 1.234 当成 1.234 小数",
        pitfalls="① 只有在导入外部数据、对方用欧式格式时才需要它；"
                 "同机同区域的数据用 VALUE 或 `--` 更快\n"
                 "② 第 2 / 3 参数要成对理解：一个说小数点什么，一个说千分位是什么\n"
                 "③ 需要 2013 及以上",
        use_cases="导入欧洲 / 南美的报表数据；"
                  "处理千分位与小数点互换的脏数据",
        related="VALUE|TEXT|SUBSTITUTE|ISNUMBER",
    ),
    F(
        code="UNICHAR", name_cn="按 Unicode 取字符", category="文本",
        tags="", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="UNICHAR(数字)",
        args_desc="数字：Unicode 码位（1~1114111）",
        returns="该码位对应的字符（**汉字也能生成**）",
        description="CHAR 的 Unicode 版，能取中文与各种符号。",
        example_formula="=UNICHAR(10004)",
        example_result="→ ✓（对勾）。"
                       "常用：10004 ✓、10005 ✗、9733 ★、9829 ♥、9749 ☕",
        pitfalls="① 码位是**十进制**，网上的码表常给十六进制（U+2714），"
                 "要自己换算：HEX2DEC(\"2714\")\n"
                 "② 超出 1~1114111 会 #VALUE!\n"
                 "③ 换个字体可能显示成方框 —— 用的是系统字体里有没有这个字形",
        use_cases="在单元格里放对勾 / 星标 / 特殊符号；"
                  "做简易评分展示；生成特殊分隔符",
        related="UNICODE|CHAR|CODE|REPT",
    ),
    F(
        code="CODE", name_cn="取字符代码", category="文本",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="CODE(文本)",
        args_desc="文本：取**第一个字符**的代码",
        returns="该字符在系统代码页里的编号",
        description="取字符的代码，用来识别看不见的字符。",
        example_formula="=CODE(MID(A2, 3, 1))",
        example_result="能告诉你字符串第 3 个位置到底是个什么字符。"
                       "**排查「两个看着一样的文本为什么不相等」时很有用**",
        pitfalls="① **只看第一个字符**，要看别的位得配 MID\n"
                 "② 它给的是本机代码页口径，"
                 "中文汉字会得到 19000+ 之类的值（不是 Unicode 码位），要 Unicode 用 UNICODE\n"
                 "③ 常见对照：32 空格、160 非断行空格、9 制表符、10 换行",
        use_cases="定位看不见的字符；对比两段「看起来一样」的文本；"
                  "解析导入数据的分隔符到底是什么",
        related="UNICODE|CHAR|LEN|CLEAN",
    ),

    # ==================================================================
    # 信息 · 补齐
    # ==================================================================
    F(
        code="N", name_cn="转成数字", category="信息",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="N(值)",
        args_desc="值：任意内容",
        returns="数字原样返回；日期返回序列值；TRUE 返回 1；"
                "**文本返回 0**；错误值原样返回错误",
        description="把各种类型统一压成数字，文本一律变 0。",
        example_formula="=SUM(N(B2:B100))",
        example_result="把区域里 TRUE/FALSE 当 1/0 求和。"
                       "更常用的是 `--` 双负号，效果一样但更短",
        pitfalls="① **文本一律返回 0**，不是提取数字 —— "
                 "想把 \"123\" 转成 123 要用 VALUE 或 `--`\n"
                 "② 它不报错，所以「静默变 0」比报错更危险\n"
                 "③ 单独用时基本不如 `--` 直观",
        use_cases="把 TRUE/FALSE 数组转成 1/0；"
                  "读懂老公式里的 N()；判断类型",
        related="VALUE|ISNUMBER|TYPE|SUMPRODUCT",
    ),
    F(
        code="NA", name_cn="制造 #N/A", category="信息",
        tags="画图技巧", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="NA()",
        args_desc="无参数（必须写空括号）",
        returns="#N/A 错误值",
        description="主动生成一个 #N/A —— 它的价值在**图表里**。",
        example_formula='=IF(B2="", NA(), B2)',
        example_result="B2 为空时返回 #N/A。"
                       "**折线图会跳过 #N/A 点**，"
                       "而空单元格默认会被画成 0（线掉到底），这就是它的用途",
        pitfalls="① 它就是要报错，别拿它当「空值」用\n"
                 "② **图表会跳过 #N/A，但会绘制 0** —— "
                 "这是它和 `\"\"` 的唯一关键区别，也是它存在的理由\n"
                 "③ 用 IFERROR 套住它会让这个技巧失效，别多此一举\n"
                 "④ 它会让 SUM / AVERAGE 等函数报错，只适合纯展示列",
        use_cases="折线图断点（未发生的月份不画线）；"
                  "标记「不适用」且希望图表跳过；占位待填",
        related="ISNA|IFNA|IFERROR|ISBLANK",
    ),
    F(
        code="ISERR", name_cn="是否错误（不含 #N/A）", category="信息",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="ISERR(值)",
        args_desc="值：单元格引用或表达式",
        returns="是错误值**但排除 #N/A** 时 TRUE",
        description="判断是否出错，但不把「找不到」算进去。",
        example_formula='=IF(ISERR(A2), "公式有错", "正常")',
        example_result="#VALUE!、#REF! 等返回 TRUE；"
                       "**#N/A 返回 FALSE**（因为那不算「错误」，只是没找到）",
        pitfalls="① **它的存在就是为了把 #N/A 排除在外** —— "
                 "和 ISERROR 的区别只有这一点，但正是这一点常常有用\n"
                 "② 日常兜底用 IFERROR 更省事；"
                 "只有「想单独盯住真错误」时才需要它\n"
                 "③ 返回值要参与算术时记得转 1/0",
        use_cases="区分「查不到」与「公式坏了」；"
                  "数据质量检查时只盯真错误；与 ISNA 配对覆盖全部错误",
        related="ISERROR|ISNA|IFERROR|IFNA",
    ),
    F(
        code="TYPE", name_cn="判断数据类型", category="信息",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="TYPE(值)",
        args_desc="值：任意内容",
        returns="1 数字／2 文本／4 逻辑值／16 错误值／64 数组",
        description="返回数据类型的编号，用来做大分支判断。",
        example_formula='=CHOOSE(TYPE(A2), "数字", "文本", , "逻辑值", , , "错误值")',
        example_result="按类型给不同处理。"
                       "编号是二进制位（1/2/4/16/64），所以 CHOOSE 里要留空位",
        pitfalls="① **编号不连续**（1、2、4、16、64），"
                 "不要按 1/2/3/4 猜，这是最容易记错的地方\n"
                 "② 它是位标志：日期算数字（1）、公式算结果类型\n"
                 "③ 日常判断用 ISNUMBER / ISTEXT 更可读，TYPE 更像「底层工具」",
        use_cases="数据清洗时按类型走不同分支；"
                  "调试时确认某个值的真实类型；解析混合类型的列",
        related="ISNUMBER|ISTEXT|N|ISERROR",
    ),

    # ==================================================================
    # 日期与时间 · 补齐
    # ==================================================================
    F(
        code="MINUTE", name_cn="取分钟", category="日期与时间",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="MINUTE(序列值)",
        args_desc="序列值：日期时间值或时间文本",
        returns="0~59 的分钟数",
        description="从时间值里取分钟。",
        example_formula="=HOUR(B2)*60+MINUTE(B2)",
        example_result="把「2 小时 15 分」转成 135 分钟。"
                       "算工时 / 计费时长就这么写",
        pitfalls="① 只取当前这一小时的分钟部分，"
                 "**不是「总分钟数」** —— 总分钟要像上面那样自己算\n"
                 "② 跨天的时间要先 MOD(值, 1) 剥掉日期\n"
                 "③ 秒会被截断，不外显",
        use_cases="算总分钟数；按时段分组；"
                  "配 HOUR 做时长换算",
        related="HOUR|SECOND|TIME|MOD",
    ),
    F(
        code="SECOND", name_cn="取秒", category="日期与时间",
        tags="", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="SECOND(序列值)",
        args_desc="序列值：日期时间值或时间文本",
        returns="0~59 的秒数",
        description="从时间值里取秒。",
        example_formula="=TEXT(NOW(), \"hh:mm:ss\")",
        example_result="想展示到秒其实用 TEXT 更好读；"
                       "要**算**秒数才用 SECOND",
        pitfalls="① 因为 Excel 时间精度与显示格式的关系，"
                 "秒常常被四舍五入掉，取值前确认单元格里真的有秒\n"
                 "② 单独用它很少见，一般是凑完整的时分秒",
        use_cases="精确到秒的时间计算；"
                  "日志时间解析；配 HOUR/MINUTE 转总秒数",
        related="MINUTE|HOUR|TIME|TEXT",
    ),
    F(
        code="TIME", name_cn="拼出时间", category="日期与时间",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="TIME(时, 分, 秒)",
        args_desc="时 / 分 / 秒：数字，**可以越界**（分给 90 = 1 小时 30 分；"
                  "时给 25 = 次日 1 点）",
        returns="0~1 之间的小数值（时间的序列值）",
        description="用三个数字拼出一个时间值。",
        example_formula="=TIME(8, 30, 0)",
        example_result="8:30。"
                       "越界很好用：`A2 + TIME(2, 0, 0)` 就是「加两小时」",
        pitfalls="① 结果是**小数**（8:30 是 0.354...），"
                 "单元格要设成时间格式才看得懂\n"
                 "② 它没有日期部分，**结果不会超过 24 小时** —— "
                 "超过了会自动回绕（25:00 显示成 1:00）。"
                 "要算「总时长」必须把格式设成 `[h]:mm`\n"
                 "③ 时间相加超过一天要配合日期一起算",
        use_cases="时间加减（加 2 小时）；构造标准上班时间；"
                  "把时分秒三列拼成真时间",
        related="HOUR|MINUTE|SECOND|DATE|TEXT",
    ),
    F(
        code="WORKDAY.INTL", name_cn="自定义周末的工作日", category="日期与时间",
        tags="工作日计算|单休必用", min_version="Excel 2010", difficulty=3,
        importance=2,
        syntax="WORKDAY.INTL(起始日期, 工作日天数, [周末规则], [假日])",
        args_desc="起始日期 / 工作日天数 同 WORKDAY\n"
                  "周末规则：7 位 0/1 字符串，**从周一开始**；1 表示那天休息\n"
                  '  "0000011" = 周六周日休（默认）\n'
                  '  "0000001" = 只周日休（单休）\n'
                  '  "0000110" = 周五周六休\n'
                  "  也可用 1~17 的编号（1 = 周六周日，2 = 周日周一，…，11 = 仅周日）\n"
                  "假日：额外跳过的日期区域",
        returns="推出来的日期",
        description="能自定义「哪天算周末」的工作日推算，单休 / 大小周 / 中东作息都能算。",
        example_formula='=WORKDAY.INTL(A2, 5, "0000001")',
        example_result="从 A2 起第 5 个工作日，**只把周日当休息日**（单休）。"
                       "双休改成 \"0000011\" 即可",
        pitfalls="① **周末规则的 7 位串是从「周一」开始的**，"
                 "不是周日，顺序写反了结果全错\n"
                 "② 字符串里 1 = 休息、0 = 上班，与直觉「1=上班」相反\n"
                 "③ **中国的调休（周末上班）它做不到**："
                 "规则的粒度只到「星期几」，认不了「某个具体的周六要上班」。"
                 "要精确到调休只能手工维护工作日历\n"
                 "④ 需要 2010 及以上",
        use_cases="单休 / 大小周公司的交付日期；"
                  "跨时区团队（周五周六休）的排期；"
                  "只休周日的排班",
        related="WORKDAY|NETWORKDAYS.INTL|NETWORKDAYS|EDATE",
    ),
    F(
        code="NETWORKDAYS.INTL", name_cn="自定义周末的工作日数", category="日期与时间",
        tags="工作日计算|单休必用", min_version="Excel 2010", difficulty=3,
        importance=2,
        syntax="NETWORKDAYS.INTL(起始日期, 结束日期, [周末规则], [假日])",
        args_desc="起始日期 / 结束日期：**首尾都算**\n"
                  "周末规则：同 WORKDAY.INTL，7 位 0/1 串从周一开始（1 = 休息）\n"
                  "假日：额外排除的日期区域",
        returns="区间内的工作日天数",
        description="按自定义周末规则数工作日，单休公司算请假天数必用。",
        example_formula='=NETWORKDAYS.INTL(A2, B2, "0000001", 假日表!$A$2:$A$30)',
        example_result="A2 到 B2 之间（含首尾）、只休周日的工作日天数",
        pitfalls="① 与 WORKDAY.INTL 一样，**周末串从周一开始、1 代表休息**\n"
                 "② 首尾都算（闭区间），差一天的口径争议最多\n"
                 "③ 同样处理不了「调休上班」\n"
                 "④ 需要 2010 及以上",
        use_cases="单休公司的请假 / 计薪天数；"
                  "跨地区团队的工期统计；与 NETWORKDAYS 对照口径",
        related="NETWORKDAYS|WORKDAY.INTL|DAYS|DATEDIF",
    ),
    F(
        code="ISOWEEKNUM", name_cn="ISO 周序号", category="日期与时间",
        tags="", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="ISOWEEKNUM(序列值)",
        args_desc="序列值：日期",
        returns="按 ISO 8601 口径的周序号（周一开始，第一周必须含 4 天以上）",
        description="按国际标准口径算第几周，跨国协作 / 财务年度周用它对齐。",
        example_formula="=ISOWEEKNUM(A2)",
        example_result="与 WEEKNUM(A2, 2) 在**年初年末会差一周**，"
                       "其余时候基本一致",
        pitfalls="① **它的口径是 ISO 8601，与 WEEKNUM 的默认口径不同**，"
                 "和国外同事对周序号时优先用它\n"
                 "② 它仍不告诉你「本周是哪几天」，"
                 "要算周一起止还是用 `A2-WEEKDAY(A2,2)+1`\n"
                 "③ 需要 2013 及以上",
        use_cases="与国际团队对周序号；ISO 口径的周报编号；"
                  "财务年度周口径",
        related="WEEKNUM|WEEKDAY|DATE|TODAY",
    ),

    # ==================================================================
    # 查找与引用 · 补齐
    # ==================================================================
    F(
        code="ADDRESS", name_cn="生成地址文本", category="查找与引用",
        tags="配合INDIRECT", min_version="Excel 2003", difficulty=3, importance=1,
        syntax="ADDRESS(行号, 列号, [引用类型], [样式], [工作表名])",
        args_desc="行号 / 列号：数字\n"
                  "引用类型：1 绝对（$A$1，默认）／2 绝对行（A$1）／"
                  "3 绝对列（$A1）／4 相对（A1）\n"
                  "样式：TRUE / 省略 = A1 样式；FALSE = R1C1 样式\n"
                  "工作表名：填上则地址变成 `'表名'!$A$1` 形式",
        returns="**文本形式**的单元格地址（不是引用）",
        description="拼出「第几行第几列」的地址文本，主要用来喂给 INDIRECT。",
        example_formula='=INDIRECT(ADDRESS(ROW(), COLUMN()-1))',
        example_result="返回左边一格的值。"
                       "真实场景更多是拼跨表地址："
                       '`=INDIRECT(ADDRESS(2, 3, 4, TRUE, B1))`',
        pitfalls="① **返回的是文本**，它自己不能取值，必须套 INDIRECT 或 HYPERLINK\n"
                 "② 引用类型的 4 个数字极易记混，"
                 "记法：**1 全绝对、2 行绝对、3 列绝对、4 全相对**\n"
                 "③ 套 INDIRECT 后公式就不可追踪了，"
                 "能不用这套就用别的方式（见 INDIRECT 条目）",
        use_cases="动态拼跨表引用；生成跳转链接；"
                  "教学演示「地址是怎么构成的」",
        related="INDIRECT|ROW|COLUMN|HYPERLINK",
    ),
    F(
        code="FORMULATEXT", name_cn="显示公式本身", category="查找与引用",
        tags="审表利器", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="FORMULATEXT(引用)",
        args_desc="引用：单元格引用（**必须是引用**）",
        returns="该单元格里的公式文本；没有公式则返回 #N/A",
        description="把别的单元格里的公式当文本显示出来，做「公式清单」很方便。",
        example_formula="=FORMULATEXT(B2)",
        example_result='显示 "=SUM(B3:B10)" 这样的文本。'
                       "配 ISFORMULA 就能做一张「哪里是公式、哪里是手填」的检查表",
        pitfalls="① 必须传**引用**，传值会 #VALUE!\n"
                 "② 目标格没有公式时返回 **#N/A**，套 IFERROR 更稳\n"
                 "③ 它是文本，不能直接算；"
                 "要「执行」一段文本公式得靠 EVALUATE（旧宏函数）或 INDIRECT\n"
                 "④ 需要 2013 及以上",
        use_cases="接手别人的表时导出公式清单；"
                  "做公式审查表；配 ISFORMULA 检查模板完整性",
        related="ISFORMULA|INDIRECT|TYPE|ADDRESS",
    ),
    F(
        code="WRAPCOLS", name_cn="折成多列", category="查找与引用",
        tags="动态数组", min_version="Excel 365", difficulty=3, importance=1,
        syntax="WRAPCOLS(向量, 每列几个, [填充值])",
        args_desc="向量：一维数据\n"
                  "每列几个：每列放几个元素\n"
                  "填充值：最后一列不满时补什么；省略补 #N/A",
        returns="折好的二维数组（**按列填**），自动溢出",
        description="把一长条数据按固定个数折成多列（按列方向填充）。",
        example_formula='=WRAPCOLS(SEQUENCE(10), 3, "")',
        example_result="1..10 折成 4 列，最后一列留空。"
                       "与 WRAPROWS 的区别：**WRAPCOLS 是竖着填满一列再换下一列**",
        pitfalls="① **默认补 #N/A**，一般要给第 3 参数\n"
                 "② 它是**按列**填的，视觉上「先往下、再往右」；"
                 "要「先往右、再往下」用 WRAPROWS，两者结果**不同**，容易选错\n"
                 "③ 需要 365 / 2021",
        use_cases="把长清单排成多列（卡片 / 标签版式）；"
                  "生成按列读的排班表",
        related="WRAPROWS|TOCOL|TOROW|SEQUENCE",
    ),
    F(
        code="MAKEARRAY", name_cn="按行列函数造数组", category="查找与引用",
        tags="动态数组|365新增|高级", min_version="Excel 365", difficulty=4,
        importance=1,
        syntax="MAKEARRAY(行数, 列数, LAMBDA(行, 列, 计算式))",
        args_desc="行数 / 列数：要造多大\n"
                  "LAMBDA：接收当前的行号与列号，返回该位置的值",
        returns="造好的二维数组，自动溢出",
        description="用「行号 + 列号」的函数式写法生成整片数值。",
        example_formula="=MAKEARRAY(9, 9, LAMBDA(r, c, r*c))",
        example_result="生成 9×9 的乘法表。"
                       "做矩阵、坐标网格、带行列规律的测试数据很顺手",
        pitfalls="① **两个参数都是「相对序号」**（从 1 开始），"
                 "不是工作表行号\n"
                 "② 行 × 列乘积别太大，几十万格会让 Excel 卡死\n"
                 "③ 结果会溢出，目标区域要留空\n"
                 "④ 需要 365 / 2021",
        use_cases="生成乘法表 / 距离矩阵；"
                  "按行列规律造测试数据；生成网格坐标",
        related="SEQUENCE|MAP|LAMBDA|RANDARRAY",
    ),

    # ==================================================================
    # 财务 · 补齐
    # ==================================================================
    F(
        code="SYD", name_cn="年数总和折旧", category="财务",
        tags="加速折旧", min_version="Excel 2003", difficulty=4, importance=1,
        syntax="SYD(原值, 残值, 年限, 期数)",
        args_desc="原值 / 残值 / 年限：同 SLN\n期数：要看第几期的折旧额",
        returns="第「期数」期的折旧额（前期大、逐年递减）",
        description="年数总和法折旧，另一种加速折旧法。",
        example_formula="=SYD($B$2, $C$2, $D$2, ROW()-1)",
        example_result="5 年期的折旧比例依次是 5/15、4/15、3/15、2/15、1/15。"
                       "**递减比双倍余额递减更温和**",
        pitfalls="① 与 DDB 的区别：DDB 按余额比例递减，SYD 按年数比例递减，"
                 "同一个资产两者每期金额不同\n"
                 "② 它**会把累计折旧正好卡到（原值−残值）**，"
                 "这点比 DDB 友好，不用手工在最后两年改直线法\n"
                 "③ 期数是「第几期」不是总期数",
        use_cases="加速折旧测算；税务筹划比较三种折旧法；"
                  "与 SLN / DDB 对照做折旧方案对比表",
        related="SLN|DDB|DB|PPMT",
    ),
    F(
        code="DB", name_cn="固定余额递减折旧", category="财务",
        tags="加速折旧", min_version="Excel 2003", difficulty=4, importance=1,
        syntax="DB(原值, 残值, 年限, 期数, [月份数])",
        args_desc="原值 / 残值 / 年限：同上\n"
                  "期数：第几期\n"
                  "月份数：**第一年使用几个月**（默认 12）；"
                  "用于「年中购入」的情况",
        returns="第「期数」期的折旧额",
        description="固定余额递减法（用固定比率而非固定倍数）。",
        example_formula="=DB($B$2, $C$2, $D$2, ROW()-1, 7)",
        example_result="资产在年中（第 7 个月）启用时的折旧序列。"
                       "**它有 DDB 没有的「月份数」参数**，"
                       "这是它相对于 DDB 的主要优势",
        pitfalls="① **它与 DDB 不是一回事**：DDB 用倍率（默认 2 倍）、"
                 "DB 用由原值 / 残值 / 年限反算出的固定比率，两者结果不同，别混\n"
                 "② 月份数参数会影响到最后**多出一期**（因为第一年不满），"
                 "总期数可能是「年限 + 1」\n"
                 "③ 中文字面上「双倍余额」指的是 DDB，"
                 "写方案时务必核对用的是哪个",
        use_cases="年中购入资产的折旧表；"
                  "按税法规定的年限与残值率测算；与 DDB 对照",
        related="DDB|SLN|SYD|PPMT",
    ),
    F(
        code="MIRR", name_cn="修正内部收益率", category="财务",
        tags="财务|解决IRR多解", min_version="Excel 2003", difficulty=4,
        importance=2,
        syntax="MIRR(值, 融资利率, 再投资利率)",
        args_desc="值：按时间顺序的现金流（**至少要一正一负**）\n"
                  "融资利率：负现金流（投入）的借款成本\n"
                  "再投资利率：正现金流（收益）再拿去投资的收益率",
        returns="修正后的内部收益率",
        description="解决 IRR「多解」和「再投资假设不合理」两个毛病的版本。",
        example_formula="=MIRR(A2:A10, 5%, 8%)",
        example_result="把「投入按 5% 借、收益按 8% 再投」这两个真实假设写进去，"
                       "算出的收益率比 IRR 更贴近实际",
        pitfalls="① **两个利率是业务假设，不是从数据里算出来的** —— "
                 "写报告必须说明取值依据，否则会被质疑\n"
                 "② 现金流仍要至少一正一负\n"
                 "③ 它只有一个解，这正是它相对 IRR 的价值；"
                 "现金流符号反复变动时优先用它",
        use_cases="现金流符号反复变动的项目（IRR 多解时）；"
                  "需要体现真实再投资假设的测算；融资成本与投资收益不同的场景",
        related="IRR|XIRR|NPV|RATE",
    ),
    F(
        code="XNPV", name_cn="不定期净现值", category="财务",
        tags="财务", min_version="Excel 2007", difficulty=4, importance=1,
        syntax="XNPV(利率, 值, 日期)",
        args_desc="利率：年化折现率（**这里是年化的，与 NPV 不同**）\n"
                  "值：各次现金流\n"
                  "日期：与值一一对应的实际日期",
        returns="按实际天数折现的净现值（**含第一笔现金流**）",
        description="日期不规则时的净现值。",
        example_formula="=XNPV(B2, C2:C20, D2:D20)",
        example_result="按真实日期折现求和。"
                       "**它包含第一笔，而 NPV 把所有现金流都当「期末」**，"
                       "所以两者写法不同",
        pitfalls="① **与 NPV 的口径差异是本条最重要的知识点**："
                 "XNPV 含第一笔现金流（通常是你现在投出去的钱），"
                 "NPV 则假设所有参数都在期末。"
                 "所以 NPV 要把初始投资写在函数外面、XNPV 不用\n"
                 "② 日期必须是真日期且与值一一对应\n"
                 "③ 利率是**年化**的（NPV 用的是期利率），写的时候要看清楚\n"
                 "④ 需要 2007 及以上",
        use_cases="日期不规则的项目估值；"
                  "与 XIRR 配套使用（一个给金额、一个给收益率）；"
                  "真实回款节奏下的投资判断",
        related="XIRR|NPV|IRR|PV",
    ),

    # ==================================================================
    # 工程 · 补齐
    # ==================================================================
    F(
        code="BITAND", name_cn="按位与", category="工程",
        tags="", min_version="Excel 2013", difficulty=4, importance=1,
        syntax="BITAND(数值1, 数值2)",
        args_desc="数值1 / 数值2：两个非负整数（**必须 < 2^48**）",
        returns="两个数按二进制逐位做「与」的结果",
        description="按位与，用来从状态值里「抠出」某几位。",
        example_formula="=BITAND(A2, 4)>0",
        example_result="判断状态值 A2 的第 3 位是否被置上。"
                       "**权限位 / 状态位解析的标准写法**",
        pitfalls="① **只接受非负整数**，负数或小数会 #NUM!\n"
                 "② 上限 2^48-1，超了报错\n"
                 "③ 想「设置」或「清除」某位要用 BITOR / BITXOR 配套，"
                 "单独一个 BITAND 只能读不能写",
        use_cases="解析权限位 / 状态标志位；"
                  "与设备协议对接时读寄存器；做位运算教学",
        related="BITOR|BITXOR|DEC2BIN|BIN2DEC",
    ),
    F(
        code="BITOR", name_cn="按位或", category="工程",
        tags="", min_version="Excel 2013", difficulty=4, importance=1,
        syntax="BITOR(数值1, 数值2)",
        args_desc="数值1 / 数值2：两个非负整数（必须 < 2^48）",
        returns="逐位做「或」的结果：任一位是 1 结果该位就是 1",
        description="按位或，用来把某个状态位「打开」。",
        example_formula="=BITOR(A2, 4)",
        example_result="把状态值 A2 的第 3 位设成 1。"
                       "与 BITAND 配合就是完整的「读位 + 置位」",
        pitfalls="① 只接受非负整数\n"
                 "② 它**只会置位不会清位** —— 想关掉某位要先 `BITAND(值, BITNOT(掩码))`，"
                 "而 Excel 没有 BITNOT，得用 `BITAND(值, 2^48-1-掩码)` 绕\n"
                 "③ 需要 2013 及以上",
        use_cases="给状态值置位（开权限 / 标记已完成某阶段）；"
                  "与 BITAND 配套做位运算读写",
        related="BITAND|BITXOR|DEC2BIN|BIN2DEC",
    ),
    F(
        code="BITXOR", name_cn="按位异或", category="工程",
        tags="", min_version="Excel 2013", difficulty=4, importance=1,
        syntax="BITXOR(数值1, 数值2)",
        args_desc="数值1 / 数值2：两个非负整数（必须 < 2^48）",
        returns="逐位做「异或」的结果：两位不同该位为 1，相同为 0",
        description="按位异或：同一位两次异或就恢复原值，所以它也能「切换」某位。",
        example_formula="=BITXOR(A2, 4)",
        example_result="第 3 位从 1 变 0、从 0 变 1 —— "
                       "**一个函数同时具备置位与清位的能力**，做开关标记很方便",
        pitfalls="① 只接受非负整数\n"
                 "② 业务含义不直观，做权限位时优先用 BITAND / BITOR 更好读\n"
                 "③ 需要 2013 及以上",
        use_cases="状态位取反 / 切换；校验位计算；"
                  "加密与编码的小工具",
        related="BITAND|BITOR|DEC2BIN|BIN2DEC",
    ),
    F(
        code="LOG", name_cn="对数", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="LOG(数值, [底数])",
        args_desc="数值：要取对数的正数\n"
                  "底数：以多少为底；省略为 10",
        returns="对数值；数值 ≤ 0 时返回 #NUM!",
        description="算任意底数的对数。",
        example_formula="=LOG(1000, 10)",
        example_result="→ 3。"
                       "指数增长的数据取对数后变成直线，"
                       "这是「对数坐标 / 对数变换」的原理",
        pitfalls="① 数值不能 ≤ 0（返回 #NUM!）\n"
                 "② 底数不能为 1 或 ≤ 0\n"
                 "③ **底数是第二个参数**，很容易和 LOG10 混："
                 "LOG(x) 已经默认底 10，不必再写 LOG10\n"
                 "④ 以 e 为底用 LN 更直接",
        use_cases="跨量级数据的压缩展示；算翻倍次数（LOG(目标/现在, 2)）；"
                  "对数回归前的变换",
        related="LN|EXP|POWER",
    ),
    F(
        code="LN", name_cn="自然对数", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="LN(数值)",
        args_desc="数值：要取对数的正数（不能 ≤ 0）",
        returns="以 e 为底的对数值",
        description="以 e 为底的对数，EXP 的反函数。",
        example_formula="=LN(B2/C2)/LN(2)",
        example_result="算「B2 是 C2 的多少倍再折成几次翻倍」。"
                       "金融里做连续复利折算也用它",
        pitfalls="① 数值 ≤ 0 返回 #NUM!\n"
                 "② 想「几次翻倍」用 `LN(新/旧)/LN(2)` —— "
                 "分母这个 LN(2) 极易漏\n"
                 "③ 与 LOG 的区别只是底数，**别把两者当成一个函数的两种写法**",
        use_cases="算翻倍次数 / 增长率；连续复利折算；"
                  "与 EXP 配对做变换与还原",
        related="LOG|EXP|POWER",
    ),
    F(
        code="SQRT", name_cn="平方根", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="SQRT(数值)",
        args_desc="数值：非负数",
        returns="平方根；负数值返回 #NUM!",
        description="开平方。",
        example_formula="=SQRT(SUM((B2:B100-AVERAGE(B2:B100))^2)/COUNT(B2:B100))",
        example_result="手写标准差。"
                       "日常直接用 STDEV.P 就行，这里是演示公式的构成",
        pitfalls="① 负数返回 #NUM!（数学上不是实数）\n"
                 "② 开三次方要用 POWER(x, 1/3) 或 `x^(1/3)`，SQRT 只管平方根\n"
                 "③ 计算两点距离：`SQRT((x1-x2)^2+(y1-y2)^2)`",
        use_cases="算欧氏距离；几何计算；"
                  "与 ^2 配对做偏差幅度",
        related="POWER|ABS|STDEV.P",
    ),
    F(
        code="UNICODE", name_cn="取 Unicode 码位", category="文本",
        tags="", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="UNICODE(文本)",
        args_desc="文本：取**第一个字符**的 Unicode 码位（十进制）",
        returns="该字符的 Unicode 码位（十进制整数）",
        description="取字符的 Unicode 码位，UNICHAR 的反函数。",
        example_formula="=UNICODE(A2)",
        example_result='A2="✓" → 10004。'
                       "用它排查「看着一样却不相等」的两个字符到底差在哪",
        pitfalls="① 它给的是**十进制**，网上的码表常是十六进制（U+2714），"
                 "对照时要换算：DEC2HEX(10004) = 2714\n"
                 "② 只看第一个字符，看别的位要配 MID\n"
                 "③ 需要 2013 及以上",
        use_cases="排查不可见 / 相似字符；解析特殊符号；"
                  "与 UNICHAR 配对做字符处理",
        related="UNICHAR|CODE|MID|LEN",
    ),
    F(
        code="FREQUENCY", name_cn="频数分布", category="统计",
        tags="数组函数|做直方图", min_version="Excel 2003", difficulty=4,
        importance=2,
        syntax="FREQUENCY(数据数组, 分组数组)",
        args_desc="数据数组：要统计的原始数据\n"
                  "分组数组：**各分段的「上界」**，必须按升序写；"
                  "返回的数组比它多一个元素（最后是超出最大上界的个数）",
        returns="各分段的个数（数组），比分组数组多一个值",
        description="统计「各分数段有多少人」，做频数分布与直方图的老牌函数。",
        example_formula="=FREQUENCY(B2:B100, {60,70,80,90})",
        example_result="返回 5 个数：<60、60~69、70~79、80~89、≥90 各有多少个。"
                       "**返回 5 个而分组只给了 4 个**，这是它的设计",
        pitfalls="① **返回的数组比「分组数组」多一个元素**，"
                 "目标区域要预留 n+1 行，否则最后一个分段被漏掉\n"
                 "② 分组数组必须**升序**，乱序会给错结果\n"
                 "③ 它是数组函数：老版本要**先选中 n+1 个单元格**再按 Ctrl+Shift+Enter；"
                 "365 里直接回车即可\n"
                 "④ **零值会被算进第一个分段**（因为是「<=60」口径），"
                 "数据里的 0 记得先排除\n"
                 "⑤ 现代替代：365 里可以用 `COUNTIFS` 逐段算，或 `MAP` 一次算完，可读性更好",
        use_cases="成绩 / 薪资 / 年龄的分布统计；"
                  "直方图的数据源；区间计数的批量版",
        related="COUNTIFS|PERCENTILE.INC|MAP|MODE.MULT",
    ),
    F(
        code="TREND", name_cn="线性趋势值", category="统计",
        tags="数组函数|预测", min_version="Excel 2003", difficulty=4, importance=2,
        syntax="TREND(已知 Y, [已知 X], [新 X], [常量])",
        args_desc="已知 Y：历史结果（可多列）\n"
                  "已知 X：历史自变量；省略则用 1,2,3…\n"
                  "新 X：要预测的自变量；省略则对历史 X 拟合\n"
                  "常量：TRUE / 省略 = 正常求截距；FALSE = 强制截距为 0",
        returns="预测出的 Y 值数组（可一次给多个新 X）",
        description="一次预测多个点的线性趋势值，比 FORECAST.LINEAR 更适合批量外推。",
        example_formula="=TREND($B$2:$B$13, $A$2:$A$13, A14:A16)",
        example_result="按 1~12 月的趋势，一次算出第 13、14、15 月的预测值。"
                       "**FORECAST.LINEAR 一次只能给一个新 X**，这是它的优势",
        pitfalls="① 它是**数组函数**，老版本要用 Ctrl+Shift+Enter 或选中结果区域\n"
                 "② 与 FORECAST.LINEAR 的参数顺序**不同**"
                 "（TREND 是「Y, X, 新X」，FORECAST 是「新X, Y, X」），极易写混\n"
                 "③ 只做线性拟合；指数趋势要先取对数再拟合\n"
                 "④ 多个因变量（多列 Y）时它可以一次做多元回归的预测部分",
        use_cases="批量趋势预测（未来 3 期一起给）；"
                  "给图表补预测段；简单的时间序列外推",
        related="FORECAST.LINEAR|SLOPE|CORREL|SEQUENCE",
    ),
    F(
        code="ENCODEURL", name_cn="URL 编码", category="Web",
        tags="拼链接用", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="ENCODEURL(文本)",
        args_desc="文本：要编码的内容（中文、空格、特殊符号会被转成 %XX）",
        returns="URL 安全的编码结果",
        description="把中文与特殊字符转成 URL 能用的编码，拼搜索链接用。",
        example_formula='=HYPERLINK("https://example.com/search?q=" & ENCODEURL(A2), "去搜索")',
        example_result="A2 是「华东 上海」时，链接里会正确变成 "
                       "%E5%8D%8E%E4%B8%9C%20%E4%B8%8A%E6%B5%B7，"
                       "**不编码的话中文链接点开会失败**",
        pitfalls="① **它只处理「值」的部分**，不能把整条 URL 丢进去 —— "
                 "`https://` 里的 `://` 也会被编码，结果反而打不开\n"
                 "② 它只做百分号编码，不做 Unicode 规范化\n"
                 "③ 需要 2013 及以上\n"
                 "④ 现代更常见的做法是用 POWER QUERY 抓数据，"
                 "而不是在单元格里拼 URL",
        use_cases="按单元格里的关键字生成搜索链接；"
                  "拼带中文参数的内部系统链接；做跳转导航页",
        related="HYPERLINK|TEXTJOIN|CONCAT|SUBSTITUTE",
    ),
]
