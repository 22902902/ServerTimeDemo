# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（五）日期与时间
================================================================================
共 16 个条目。字段规范见 ``excel_seed_schema``；文本见 ``excel_seed_text``。

先记住一条，后面全部好懂
--------------------------------------------------------------------------------
**Excel 里没有「日期类型」，日期就是一个数字。**
1900/1/1 记为 1，往后每天 +1；时间是一天的小数部分（中午 12 点是 0.5）。
所以「日期」能参与加减、「格式」只是显示样式、而 ``TEXT`` 一转就变成文本不能再算。

另一条：**日期函数里用 TODAY() / NOW() 的都是易失函数**，
打开文件就重算，做「截止还有几天」这种表时心里要有数。
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    F(
        code="TODAY", name_cn="今天", category="日期与时间",
        tags="必学|易失", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="TODAY()",
        args_desc="无参数（**但必须写空括号**）",
        returns="今天的日期（时间部分是 0，即当天零点的序列值）",
        description="取今天的日期，会随日期自动更新。",
        example_formula="=TODAY()-A2",
        example_result="A2 是签约日 → 返回「到今天过了多少天」。"
                       "想让它在 B 列显示成「已逾期 12 天」，"
                       '就用 `=IF(B2<TODAY(), \"已逾期 \"&(TODAY()-B2)&\" 天\", \"正常\")`',
        pitfalls="① 忘了写括号：`TODAY` 会被当名称报错\n"
                 "② **易失函数**：每次打开 / 重算都会刷新，"
                 "所以「今天过期」的报表明天打开数字会变（通常正是你要的）\n"
                 "③ 它带时间部分为 0，与 `NOW()` 比大小时要注意\n"
                 "④ 它是动态的，**做历史留痕要存成值**（复制 → 粘贴为值），"
                 "否则回看时所有日期都变成「今天」",
        use_cases="算剩余天数 / 逾期天数；做「今天到期」提醒；"
                  "按今天筛当月数据；自动填报表日期",
        related="NOW|DATE|DAYS|DATEDIF|EOMONTH",
    ),
    F(
        code="NOW", name_cn="现在", category="日期与时间",
        tags="必学|易失", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="NOW()",
        args_desc="无参数（必须写空括号）",
        returns="当前的日期 + 时间（序列值，含小数部分）",
        description="取当前日期时间，每次重算都刷新到最新。",
        example_formula='=TEXT(NOW(), "yyyy-mm-dd hh:mm")',
        example_result="显示成「2026-09-23 14:20」。"
                       "直接放 NOW() 会显示成一长串带秒的格式，"
                       "建议配 TEXT 或设单元格格式",
        pitfalls="① 易失：**它连分钟都在变**，做「记录提交时间」时"
                 "必须转成值，否则所有人打开看到的都是自己的当前时间\n"
                 "② 只想取日期部分用 INT(NOW()) 或直接 TODAY()\n"
                 "③ 时间精度受单元格格式影响（显示到分但底数有秒）",
        use_cases="记录「此刻」的时间戳；算已运行时长；"
                  "做实时倒计时（配条件格式）；日志类表格",
        related="TODAY|INT|MOD|HOUR|TEXT",
    ),
    F(
        code="DATE", name_cn="拼出日期", category="日期与时间",
        tags="必学|必考", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="DATE(年, 月, 日)",
        args_desc="年：年份（0~1899 会被自动加上 1900）\n"
                  "月：月份，**可以越界**（13 表示次年 1 月，0 表示上年 12 月）\n"
                  "日：日，**可以越界**（32 表示下月 1 日，0 表示上月最后一天）",
        returns="对应的日期序列值（真日期，可参与计算）",
        description="用三个数字拼出一个真日期，是构日期最正规的写法。",
        example_formula="=DATE(2026, 9, 23)",
        example_result="2026/9/23。"
                       "越界的用法非常有用："
                       "`=DATE(YEAR(A2), MONTH(A2)+1, 1)-1` 得到 A2 所在月的最后一天；"
                       "`=DATE(2026, 0, 1)` 得到 2025/12/1",
        pitfalls="① **年份写 26 会被当 1926**（自动加 1900），"
                       "1900~9999 之外的年份会报错。用两位数年份的老写法在 2026 年已经不安全\n"
                 "② 拼出来的其实是数字，显示成日期要设格式\n"
                 "③ 月 / 日越界是特性也是坑：写 DATE(2026, 13, 5) 不报错但结果是 2027 年，"
                 "调试时要留个心\n"
                 "④ 「年月日」来自文本时先 VALUE 转成数字，日期串用 DATEVALUE 更快",
        use_cases="把「年 / 月 / 日」三列拼成真日期；"
                  "算某月最后一天 / 第一天（配 EOMONTH 更直接）；"
                  "做季度 / 旬的起止日期；构造周期性的日期",
        related="YEAR|MONTH|DAY|EOMONTH|DATEVALUE|TODAY",
    ),
    F(
        code="YEAR", name_cn="取年份", category="日期与时间",
        tags="必学", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="YEAR(序列值)",
        args_desc="序列值：日期或日期的文本（Excel 会尝试自动识别文本日期）",
        returns="四位年份（1900~9999）",
        description="从日期里取年份。",
        example_formula="=YEAR(A2)",
        example_result="2026/9/23 → 2026。"
                       "常用来做「按年汇总」的条件："
                       "`=SUMPRODUCT((YEAR($A$2:$A$100)=2026)*$C$2:$C$100)`",
        pitfalls="① 参数**必须是日期或能识别的日期串**；"
                 "传纯数字（如 20260923）会按日期序列值解释，得到离谱结果\n"
                 "② 它只取年，不保留月日，做分组要配 MONTH\n"
                 "③ 对文本型日期（\"2026/9/23\"）通常能识别，"
                 "但格式怪一点（\"20260923\"）就不行，先 DATEVALUE\n"
                 "④ 想「按年分组」更推荐加辅助列 + 数据透视，"
                 "不要在每个公式里反复算 YEAR",
        use_cases="按年统计 / 分组；算周岁（配 DATEDIF）；"
                  "取合同年度；构造年度区间条件",
        related="MONTH|DAY|DATEDIF|DATE",
    ),
    F(
        code="MONTH", name_cn="取月份", category="日期与时间",
        tags="必学", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="MONTH(序列值)",
        args_desc="序列值：日期或日期的文本",
        returns="1~12 的月份数字",
        description="从日期里取月份数字。",
        example_formula="=MONTH(A2)",
        example_result="2026/9/23 → 9。"
                       "做「按月汇总」的经典条件："
                       "`=SUMPRODUCT((MONTH($A$2:$A$100)=9)*$C$2:$C$100)`",
        pitfalls="① **它只给数字，跨年时会把不同年的同月混在一起**。"
                 "做月度汇总一定要**同时按年筛**，只按 MONTH 是常见事故\n"
                 "② 想要「9月」这种带字的展示，用 TEXT(A2, \"m月\") 或 DATE + 自定义格式\n"
                 "③ 参数是文本日期时同理需要能被识别",
        use_cases="按月汇总（务必配 YEAR）；算月度进度；"
                  "按月份做条件格式；提取报表月份",
        related="YEAR|DAY|EOMONTH|TEXT|DATE",
    ),
    F(
        code="DAY", name_cn="取日", category="日期与时间",
        tags="必学", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="DAY(序列值)",
        args_desc="序列值：日期或日期的文本",
        returns="1~31 的日数字",
        description="从日期里取「日」。",
        example_formula="=DAY(A2)",
        example_result="2026/9/23 → 23。"
                       "常用来判断「是否月末」：`=DAY(A2+1)=1` 为真表示 A2 是当月最后一天",
        pitfalls="① DAY(0) 返回 0（1900 年 1 月 0 日的特例），"
                 "对空单元格或 0 要留个心\n"
                 "② 判断月末更稳的写法是 `=A2=EOMONTH(A2,0)`\n"
                 "③ 它不返回「第几天」，只是日号",
        use_cases="判断月末 / 月初；按日拆分统计；"
                  "做「月初月末」的区间条件；取账单出账日",
        related="YEAR|MONTH|EOMONTH|DATE|WEEKDAY",
    ),
    F(
        code="HOUR", name_cn="取小时", category="日期与时间",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="HOUR(序列值)",
        args_desc="序列值：日期时间值（含小数的部分即时间）或时间文本",
        returns="0~23 的小时数",
        description="从时间值里取小时。",
        example_formula="=HOUR(B2-C2)*60+MINUTE(B2-C2)",
        example_result="把两个时间相减的时长转成总分钟数（如 1 小时 20 分 → 80）。"
                       "算工时 / 响应时长最常用的一招",
        pitfalls="① 时间值跨天时要自己处理：只要时间不要日期得先 MOD(值,1)\n"
                 "② 时间是小数，直接相加超过 24 小时**会进位到日期**，"
                 "显示时会「变回 0 点」，要把单元格格式设成 `[h]:mm` 才看得见总时长\n"
                 "③ 它只截取，不做四舍五入；1:59 的 HOUR 是 1",
        use_cases="算工时（小时 + 分钟）；判断是上午还是下午；"
                  "按时段分组；算响应时长",
        related="MINUTE|SECOND|MOD|TEXT|INT",
    ),
    F(
        code="DATEDIF", name_cn="算时间差（年/月/日）", category="日期与时间",
        tags="必学|隐藏函数|算年龄", min_version="Excel 2003", difficulty=3,
        importance=3,
        syntax="DATEDIF(起始日期, 结束日期, 单位)",
        args_desc='起始日期：**必须早于结束日期**，否则返回 #NUM!\n'
                  '结束日期：截止日期\n'
                  '单位：双引号里的字符串\n'
                  '  "Y"  整年数　"M"  整月数　"D"  天数\n'
                  '  "MD" 忽略年月、只按「日」差（**官方承认有 bug**）\n'
                  '  "YM" 忽略年、只算月差（0~11）\n'
                  '  "YD" 忽略年、只算日差',
        returns="按单位算出的整数差值",
        description="算两个日期之间差几年几个月几天，是算年龄、工龄、账期的标准工具。",
        example_formula='=DATEDIF(A2, TODAY(), "Y")&"岁"&DATEDIF(A2, TODAY(), "YM")&"个月"',
        example_result='"2020/3/5" 到今天 → "6岁6个月"。'
                       "这行是「精确年龄」的经典写法",
        pitfalls="① **这是个隐藏函数：输入时 Excel 不给任何提示**，"
                 "打错字母只会得到 #NUM! 或 #NAME?，让人怀疑人生。"
                 "先记住拼写 DATEDIF，单位全大写加引号\n"
                 "② 起始日期晚于结束日期返回 **#NUM!**，做模板时要套 IF 交换\n"
                 "③ **单位 \"MD\" 有已知 bug**（微软文档承认结果可能为负），"
                 "要「整月之外还剩几天」建议用 \"YM\" 算月、再自己减\n"
                 "④ 单位不加引号会被当名称报错\n"
                 "⑤ 它算的是「整」单位数：1 月 31 日到 2 月 1 日，\"M\" 是 0、\"D\" 是 1",
        use_cases="算年龄 / 工龄 / 账龄；算入职几年几个月；"
                  "算设备使用年限；算距到期还有几个月",
        related="DAYS|YEAR|EOMONTH|TODAY|EDATE",
    ),
    F(
        code="EOMONTH", name_cn="某月最后一天", category="日期与时间",
        tags="必学|财务必用", min_version="Excel 2007", difficulty=2, importance=3,
        syntax="EOMONTH(起始日期, 月数)",
        args_desc="起始日期：从哪天算起\n"
                  "月数：往前 / 往后推几个月；0 = 当月；-1 = 上月；1 = 下月",
        returns="该月最后一天的日期",
        description="取某个月的最后一天，财务对账、月度区间的必备函数。",
        example_formula="=EOMONTH(A2, 0)",
        example_result="A2=2026/9/5 → 2026/9/30。"
                       "上月最后一天写 -1，本月的第一天写 `EOMONTH(A2,-1)+1`",
        pitfalls="① 它返回的单元格**可能显示成数字 46282**，"
                 "因为结果本身是序列值 —— 记得把单元格格式设成日期\n"
                 "② 想「本月第一天」不能直接用它，"
                 "要写 `EOMONTH(A2,-1)+1` 或 `DATE(YEAR(A2),MONTH(A2),1)`\n"
                 "③ 月数为负且跨度很大时会算到很早的日期，别忘了检查\n"
                 "④ 需要 2007 及以上",
        use_cases="月度区间的上界；计算月末结账日；"
                  "生成「本月 1 日至月末」的动态区间；"
                  "算账期（如「次月末付款」）",
        related="EDATE|DATE|DAY|TODAY|WORKDAY",
    ),
    F(
        code="EDATE", name_cn="推几个月后的同一天", category="日期与时间",
        tags="必学|账期必用", min_version="Excel 2007", difficulty=2, importance=3,
        syntax="EDATE(起始日期, 月数)",
        args_desc="起始日期：从哪天算起\n"
                  "月数：往后推几个月（负数往前）",
        returns="相隔指定月数、日号相同的日期",
        description="按「月」推算日期，算账期、还款日、复查日期最合适。",
        example_formula="=EDATE(A2, 3)",
        example_result="2026/9/23 → 2026/12/23。"
                       "做「3 个月后的今天」这类账期直接一行",
        pitfalls="① **月末的日号会自动贴到月末**："
                 "EDATE(2026/1/31, 1) = 2026/2/28（2 月没有 31 号），"
                 "这是有意设计但常被忽略\n"
                 "② 结果是序列值，格式要设成日期\n"
                 "③ 需要 2007 及以上\n"
                 "④ 想「整月对齐到月末」就用 EOMONTH，两者别混",
        use_cases="账期 / 还款日 / 复查日；合同续签提醒；"
                  "把月度数据往前后推；算「N 个月后的今天」",
        related="EOMONTH|DATE|DAYS|DATEDIF",
    ),
    F(
        code="WORKDAY", name_cn="推 N 个工作日", category="日期与时间",
        tags="工作日计算|实用", min_version="Excel 2007", difficulty=2, importance=2,
        syntax="WORKDAY(起始日期, 工作日天数, [假日])",
        args_desc="起始日期：从哪天开始算（**不含这一天**）\n"
                  "工作日天数：往后推几个工作日（负数往前）\n"
                  "假日：可选，一个区域，写上调休 / 法定假日；"
                  "每个假日都会被额外跳过",
        returns="推出来的日期（自动跳过周六周日与指定假日）",
        description="算「N 个工作日之后是哪天」，做交付日期、承诺时限必备。",
        example_formula="=WORKDAY(A2, 5, 假日表!$A$2:$A$30)",
        example_result="从 A2 起第 5 个工作日（跳过周末和假日表里的日期）。"
                       "例：下单日 + 5 个工作日 = 承诺发货日",
        pitfalls="① **它不包含起始日**：WORKDAY(周一, 1) 得到周二，"
                 "「当天算第一天」的场合要写 WORKDAY(A2, N-1) 或从 A2-1 起算\n"
                 "② **它只认周六周日**为周末。"
                 "单休 / 大小周 / 中东的周五周六休息要用 WORKDAY.INTL 并指定周末规则\n"
                 "③ 假日表要自己维护，Excel **不知道中国的法定假日**\n"
                 "④ 需要 2007 及以上",
        use_cases="承诺发货 / 交付日期；工单 SLA 到期日；"
                  "放假通知里的「节后第 N 个工作日」；"
                  "算合同内的响应时限",
        related="NETWORKDAYS|WORKDAY.INTL|EDATE|TODAY",
    ),
    F(
        code="NETWORKDAYS", name_cn="数几个工作日", category="日期与时间",
        tags="工作日计算|实用", min_version="Excel 2007", difficulty=2, importance=3,
        syntax="NETWORKDAYS(起始日期, 结束日期, [假日])",
        args_desc="起始日期：区间开始（**包含这一天**）\n"
                  "结束日期：区间结束（**也包含这一天**）\n"
                  "假日：可选，法定假日 / 调休区域",
        returns="区间内的工作日天数（含首尾，跳过周六周日与指定假日）",
        description="数一段日期里有几个工作日，算请假天数、工期、账期最常用。",
        example_formula="=NETWORKDAYS(A2, B2, 假日表!$A$2:$A$30)",
        example_result="A2 到 B2 之间有几天工作日。"
                       "算「请假扣薪」时把开始和结束都算进去，正好是它的口径",
        pitfalls="① **首尾都算**（闭区间）。很多人以为「不算结束日」而算错一天\n"
                 "② 起始日晚于结束日会返回**负数**，不报错\n"
                 "③ 单休 / 大小周要用 NETWORKDAYS.INTL\n"
                 "④ 它不知道中国法定假日，必须自己给假日表；"
                 "**调休上班的周六要记得从「周末」里排除** —— "
                 "标准函数做不到，得改用 NETWORKDAYS.INTL 自定义周末\n"
                 "⑤ 需要 2007 及以上",
        use_cases="请假天数；项目工期；服务响应天数；"
                  "算「本月还剩多少个工作日」；薪酬按工作日折算",
        related="WORKDAY|NETWORKDAYS.INTL|DAYS|DATEDIF",
    ),
    F(
        code="WEEKDAY", name_cn="星期几", category="日期与时间",
        tags="必学|报表常用", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="WEEKDAY(序列值, [返回类型])",
        args_desc="序列值：日期\n"
                  "返回类型：决定「一周从哪天起、星期几算 1」\n"
                  "  1 或省略 = 周日是 1、周六是 7（**默认**，中文习惯不直观）\n"
                  "  2 = 周一是 1、周日是 7（**最常用**）\n"
                  "  3 = 周一是 0、周日是 6\n"
                  "  11~17 = 周一 / 周二 / … 起算的各种变体",
        returns="1~7 的星期序号",
        description="判断是星期几，做周末判定和排班必备。",
        example_formula='=IF(WEEKDAY(A2, 2)>=6, "周末", "工作日")',
        example_result="周一到周五显示「工作日」，周六周日显示「周末」。"
                       "**注意参数 2** —— 不写它，周一就是 2 而不是 1",
        pitfalls="① **省略第 2 参数时「周日 = 1」**，"
                 "这是最反直觉的地方：很多人的「周一 = 1」期望需要显式写 2\n"
                 "② 它不认中国法定假日，判「是否休息日」只按周末\n"
                 "③ 纯数字参数（非日期）会按日期序列值解释，结果离谱\n"
                 "④ 想要「星期一」这样的文字，用 "
                 '`TEXT(A2, "aaaa")` 或 CHOOSE(WEEKDAY(A2,2), \"一\",\"二\",…)',
        use_cases="标记周末；排班表的星期列；"
                  "取「本周一」「本周日」（配 A2-WEEKDAY(A2,2)+1）；"
                  "排除周末的统计",
        related="WEEKNUM|CHOOSE|TEXT|NETWORKDAYS|TODAY",
    ),
    F(
        code="WEEKNUM", name_cn="第几周", category="日期与时间",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="WEEKNUM(序列值, [返回类型])",
        args_desc="序列值：日期\n"
                  "返回类型：1 或省略 = 周日为一周开始；2 = 周一为一周开始；"
                  "21 = ISO 8601 口径（周一开始，且第一周必须含 4 天以上）",
        returns="该日期是当年的第几周（1~53）",
        description="算日期属于当年的第几周。",
        example_formula="=WEEKNUM(A2, 2)",
        example_result="按「周一开始」算第几周。"
                       "做周报周期、滚动周统计时用",
        pitfalls="① **口径差异非常大**：参数 2 与 ISO 口径（21）"
                 "在年初年末会差一周。跨部门对齐周序号时**必须写清楚用哪个口径**\n"
                 "② 它只给序号，不告诉你是哪一周的哪一天，"
                 "通常还要配 WEEKDAY 才是完整的「第 N 周周三」\n"
                 "③ 想「按周汇总」更稳的做法是加辅助列算「本周一的日期」"
                 "（`=A2-WEEKDAY(A2,2)+1`），按日期分组不会有口径争议",
        use_cases="周报周期编号；按周汇总统计；"
                  "算「今年第几周」；排班周期",
        related="WEEKDAY|ISOWEEKNUM|DATE|TODAY",
    ),
    F(
        code="DATEVALUE", name_cn="文本转日期", category="日期与时间",
        tags="清洗必备", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="DATEVALUE(日期文本)",
        args_desc='日期文本：能识别的日期字符串，如 "2026/9/23"、"2026-09-23"、'
                  '"23-Sep-2026"',
        returns="对应的日期序列值；无法识别时返回 #VALUE!",
        description="把看起来像日期的文本变成真日期。",
        example_formula="=DATEVALUE(A2)",
        example_result='"2026/9/23" → 46282（真日期，可参与计算、可设格式）。'
                       "导入的 CSV 里日期常常是文本，这是清洗第一步",
        pitfalls="① **它认不出的格式会 #VALUE!**："
                 '"20260923"、"2026年9月23日" 通常都能认，'
                 "但自定义怪格式就不一定 —— 认不出时用 DATE+MID 自己拼\n"
                 "② **识别能力受系统区域设置影响**：\"9/23/2026\" 在中文环境可能被当无效值。"
                 "跨环境交付不要依赖它\n"
                 "③ 结果是序列值，记得设格式\n"
                 "④ 它只处理日期；带时间的串用 `--A2` 或 VALUE",
        use_cases="导入 CSV 后把日期列转成真日期；"
                  "从系统导出文本日期做计算；"
                  "统一多种日期写法后排序",
        related="VALUE|DATE|TEXT|YEAR|DAYS",
    ),
    F(
        code="DAYS", name_cn="相隔天数", category="日期与时间",
        tags="必学|方向易错", min_version="Excel 2013", difficulty=2, importance=3,
        syntax="DAYS(结束日期, 起始日期)",
        args_desc="结束日期：**写在第一个**\n"
                  "起始日期：写在第二个\n"
                  "（两个参数都是日期或日期串）",
        returns="两个日期相差的天数；结束日期早于起始日期时返回负数",
        description="算两个日期相隔几天，参数顺序与直觉相反，要特别注意。",
        example_formula="=DAYS(B2, A2)",
        example_result="B2 减 A2 的天数。"
                       "**直接写 `=B2-A2` 效果完全一样且更短** —— "
                       "DAYS 的价值在于参数可以给日期串、可读性更明确",
        pitfalls="① **参数顺序是「结束, 起始」**，"
                 "与 `B2-A2` 的书写顺序正好相反，这是它最大的失手点\n"
                 "② 结果可能为负（没有交换），做「剩余天数」要套 MAX(0, …)\n"
                 "③ 它是自然日天数；**要工作日天数用 NETWORKDAYS**\n"
                 "④ 需要 2013 及以上",
        use_cases="算相隔天数；剩余天数 / 逾期天数；"
                  "账龄天数；两个日期之间的自然日跨度",
        related="DATEDIF|NETWORKDAYS|TODAY|EDATE",
    ),
]
