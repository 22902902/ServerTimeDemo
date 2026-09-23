# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（一）逻辑 / 数学与三角函数
================================================================================
共 29 个条目。字段规范见 ``excel_seed_schema``。

为什么把「逻辑」和「数学」放在第一个分片：这两类是**后面所有公式的骨架**。
L1 / L5 两个学习阶段几乎全部落在这里，先认识它们，再去看查找与统计，
公式的可读性会从第一天开始就是对的（IFS 而不是六层嵌套 IF）。
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    # ==================================================================
    # 逻辑
    # ==================================================================
    F(
        code="IF", name_cn="条件判断", category="逻辑",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="IF(逻辑测试, 真值, [假值])",
        args_desc="逻辑测试：能得出 TRUE / FALSE 的表达式，如 B2>=60\n"
                  "真值：成立时返回的内容（可再嵌一层 IF，但别超过 4 层）\n"
                  "假值：不成立时返回的内容；省略时返回 FALSE",
        returns="真值或假值其中之一；分支里带错误值时会把这个错误抛出来",
        description="最基本的判断：满足条件返回一个值，否则返回另一个值。",
        example_formula='=IF(B2>=60, "及格", "不及格")',
        example_result='B2 是 58 得到「不及格」；是 60 得到「及格」',
        pitfalls="① 文本结果必须写半角双引号，`IF(B2>=60, 及格, 不及格)` 会被当名称，"
                 "报 #NAME?\n"
                 "② 嵌套超过 4 层就该换 IFS / SWITCH，靠缩进硬扛的嵌套 IF 没人改得动\n"
                 '③ 省略第三个参数返回 FALSE 而不是空，做报表要显式写 ""，'
                 "否则单元格里冒出 FALSE\n"
                 "④ 拿文本型数字比较会翻车：\"58\">=60 在 Excel 里恒为 TRUE（文本大于数字）",
        use_cases="及格线判定；库存是否补货；按阈值打标签；金额是否超预算；"
                  "把空单元格显示成「未填」",
        related="IFS|SWITCH|AND|OR|IFERROR",
    ),
    F(
        code="IFS", name_cn="多条件判断", category="逻辑",
        tags="必学|替代嵌套IF", min_version="Excel 2019", difficulty=2, importance=3,
        syntax="IFS(条件1, 值1, 条件2, 值2, …, [TRUE, 兜底值])",
        args_desc="条件1：第一个判断（必须按「苛刻 → 宽松」排）\n"
                  "值1：条件1 成立时返回什么\n"
                  "……成对往后排，最多 127 对\n"
                  "TRUE, 兜底值：都不成立时的 else 分支（强烈建议写）",
        returns="第一个成立的条件对应的值；全都不成立且没写兜底则返回 #N/A",
        description="多分支判断，取代一层层嵌套的 IF，可读性高一个量级。",
        example_formula='=IFS(B2>=90, "优秀", B2>=80, "良好", B2>=60, "及格", TRUE, "不及格")',
        example_result="B2=85 → 良好；B2=45 → 不及格；按从上到下的顺序命中第一个成立的",
        pitfalls="① **条件顺序必须从苛刻到宽松**。反过来写成 B2>=60 在前，"
                 "90 分也会被判成「及格」——这是最常见的错\n"
                 "② 最后少了 `TRUE, 兜底` 又都不命中时返回 #N/A，报表上很难看\n"
                 "③ 需要 Excel 2019 / 365；老版本打开会显示成 _xlfn.IFS 并报错",
        use_cases="成绩档位；业绩分级；阶梯提成率；按天数区间给账期；"
                  "替代别人留下的六层嵌套 IF",
        related="IF|SWITCH|IFERROR",
    ),
    F(
        code="SWITCH", name_cn="等值多分支", category="逻辑",
        tags="替代嵌套IF", min_version="Excel 2019", difficulty=2, importance=2,
        syntax="SWITCH(表达式, 值1, 结果1, 值2, 结果2, …, [默认值])",
        args_desc="表达式：要拿去比对的那个值\n"
                  "值1 / 结果1：相等时返回结果1\n"
                  "……成对往后排，最多 126 对\n"
                  "默认值：都不相等时返回（只能放最后、只写一个）",
        returns="命中的结果；都不相等且没给默认值则返回 #N/A",
        description="枚举型多分支判断：一个个比对「等于什么」，比 IFS 更贴合这类需求。",
        example_formula='=SWITCH(C2, "A", "华东", "B", "华南", "C", "华北", "其他")',
        example_result='C2="B" → 华南；C2="Z" → 其他（落到默认值）',
        pitfalls="① 只能做**等值**比较，区间判断（>=80 给「良好」）要用 IFS\n"
                 "② 默认值必须写在最后，写在中间会被当成一个「待比对的值」\n"
                 "③ 大小写不敏感：\"a\" 与 \"A\" 会被判为相等，要区分得配 EXACT",
        use_cases="代码翻译成名称；性别 / 状态码映射；省份简称转大区；"
                  "月份数字转中文月名",
        related="IFS|IF|CHOOSE|EXACT",
    ),
    F(
        code="AND", name_cn="并且", category="逻辑",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="AND(逻辑1, [逻辑2], …)",
        args_desc="逻辑1：能得出 TRUE / FALSE 的表达式\n"
                  "逻辑2…：最多再给 254 个，全部都要成立",
        returns="全部为 TRUE 才返回 TRUE，否则 FALSE",
        description="多个条件同时成立。",
        example_formula='=IF(AND(B2>=60, C2="已交"), "通过", "不通过")',
        example_result="两个条件都满足才给「通过」",
        pitfalls="① 返回的是 TRUE / FALSE，不是 1 / 0，直接参与算术要包 -- 或 N()\n"
                 "② 区域里混了文本、空单元格会当 FALSE，别把整列传给 AND\n"
                 "③ 配合 IF 时把 AND 写在条件位，别写成 `IF(B2>=60, IF(C2=\"已交\",…))`",
        use_cases="多重准入条件；同时满足两个阈值；日期区间落在范围内（>=开始 AND <=结束）",
        related="OR|NOT|IF|IFS",
    ),
    F(
        code="OR", name_cn="或者", category="逻辑",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="OR(逻辑1, [逻辑2], …)",
        args_desc="逻辑1：第一个条件\n逻辑2…：最多再给 254 个，任一成立即可",
        returns="任一为 TRUE 返回 TRUE；全部为 FALSE 才返回 FALSE",
        description="多个条件只要满足一个就算成立。",
        example_formula='=IF(OR(D2="紧急", E2<TODAY()), "优先处理", "排期")',
        example_result="标记为紧急、或已过期，任一成立就「优先处理」",
        pitfalls="① 想表达「A 或 B 之一**且仅一个**」要用 XOR，不是 OR\n"
                 "② OR 写太长会失去可读性，超过 4 个条件建议用 COUNTIF 数满足个数\n"
                 "③ 与 AND 混用时优先级：AND 更高，混用一定要加括号",
        use_cases="多分支筛选；把几个状态码都算作「异常」；任一日期已过就提醒",
        related="AND|NOT|XOR|IF",
    ),
    F(
        code="NOT", name_cn="取反", category="逻辑",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="NOT(逻辑)",
        args_desc="逻辑：要取反的 TRUE / FALSE 表达式",
        returns="TRUE 变 FALSE，FALSE 变 TRUE",
        description="把判断结果反过来。",
        example_formula='=IF(NOT(ISBLANK(F2)), "已填", "待补")',
        example_result="F2 有内容时返回「已填」",
        pitfalls="① 别用来代替写成 `<>` 的比较：`NOT(A2=1)` 不如 `A2<>1` 直观\n"
                 "② 套在 IS 系列外面读起来最顺，套在算术外面容易看错",
        use_cases="排除某一类；把 ISXXX 的结果反过来用；条件取反",
        related="AND|OR|ISBLANK|IF",
    ),
    F(
        code="XOR", name_cn="异或", category="逻辑",
        tags="冷门但有用", min_version="Excel 2013", difficulty=2, importance=1,
        syntax="XOR(逻辑1, [逻辑2], …)",
        args_desc="逻辑1：第一个条件\n逻辑2…：最多再给 253 个",
        returns="为 TRUE 的个数是**奇数**时返回 TRUE，偶数时返回 FALSE",
        description="「有且仅有奇数个成立」的判断，用于互斥场景。",
        example_formula="=XOR(B2, C2)",
        example_result="B2、C2 一真一假时返回 TRUE，两个都真或都假返回 FALSE",
        pitfalls="① 不是「只能有一个成立」——三个条件全真时它返回 TRUE，"
                 "要「恰好一个」得用 `SUM(--B2,--C2)=1`\n"
                 "② 需要 2013 及以上",
        use_cases="二选一的单据校验；同一笔业务两条路径是否只走了一条",
        related="OR|AND|COUNTIF",
    ),
    F(
        code="IFERROR", name_cn="错误兜底", category="逻辑",
        tags="必学|收口", min_version="Excel 2007", difficulty=2, importance=3,
        syntax="IFERROR(值, 出错时返回)",
        args_desc="值：要检查的表达式\n出错时返回：出现任何错误值时返回它（#N/A、#VALUE!、#DIV/0!、#REF! …）",
        returns="表达式正常时返回它自己的结果，否则返回第二个参数",
        description="给公式兜底，把错误值统一换成指定内容。",
        example_formula='=IFERROR(VLOOKUP(A2, 表2!A:D, 4, FALSE), "未找到")',
        example_result="查不到时显示「未找到」，而不是让 #N/A 铺满整张表",
        pitfalls="① **它会吞掉所有错误**，包括你打错函数名导致的 #NAME?。"
                 "调试期先别套，确认公式对了再加\n"
                 "② 分不清错误类型。只想兜「查不到」时用 IFNA，别的错误照旧暴露出来更好\n"
                 "③ 套在内层逻辑上会让「本来该报错」的数据静默通过，报表核对时要留个裸公式版",
        use_cases="查找兜底；除法防 #DIV/0!；对外报表不显示错误值；包装 OFFSET / INDIRECT",
        related="IFNA|ISERROR|IF|VLOOKUP",
    ),
    F(
        code="IFNA", name_cn="只兜查不到", category="逻辑",
        tags="收口", min_version="Excel 2013", difficulty=2, importance=3,
        syntax="IFNA(值, 值为 #N/A 时返回)",
        args_desc="值：要检查的表达式\n值为 #N/A 时返回：仅当结果是 #N/A 才替换",
        returns="结果为 #N/A 时返回第二参数，其他错误值原样抛出",
        description="只兜「找不到」这一种错误，其余错误继续暴露。",
        example_formula='=IFNA(MATCH(A2, 表2!A:A, 0), "无此编号")',
        example_result="MATCH 找不到返回 #N/A → 显示「无此编号」；"
                       "如果 A:A 写成了不存在的表名，仍会照实报错",
        pitfalls="① 需要 2013 及以上，2007 只有 IFERROR\n"
                 "② 别和 IFERROR 叠在同一层，两个都能兜会看不出到底哪出错",
        use_cases="包装 VLOOKUP / MATCH / XLOOKUP；对账时单独标出「缺失的编号」",
        related="IFERROR|ISNA|MATCH|XLOOKUP",
    ),
    F(
        code="LET", name_cn="给中间量起名", category="逻辑",
        tags="365新增|写长公式必学", min_version="Excel 365", difficulty=3, importance=3,
        syntax="LET(名称1, 值1, [名称2, 值2], …, 计算结果)",
        args_desc="名称1：给中间结果起的名字，**不加引号**\n"
                  "值1：它代表的值或表达式\n"
                  "……最多 126 对\n"
                  "计算结果：用这些名字算出的最终结果（必须是最后一个参数）",
        returns="计算结果的值",
        description="把长公式里的中间量命名，重复的部分只算一次，公式也能读懂了。",
        example_formula="=LET(单价, B2, 数量, C2, 折扣, D2, 单价*数量*(1-折扣))",
        example_result="三项中间量起名后一次算出金额；"
                       "原来要写 `B2*C2*(1-D2)`，量一多就没人看得懂",
        pitfalls="① 名称不能长得像单元格地址（A1、R1C1、ABC 这类），会报名称冲突\n"
                 "② 名称只在**这一个公式内部**有效，不是全局命名；要复用请配 LAMBDA\n"
                 "③ 只有 365 / 2021 支持，老版本打开变 _xlfn.LET 报错\n"
                 "④ 名称也可以赋给区域：`LET(数据, A2:A100, …)`，配合动态数组非常好用",
        use_cases="拆解又长又重复的公式；避免同一段 SUBSTITUTE 链写三遍；"
                  "给业务量起名（单价 / 税率 / 天数）提升可读性",
        related="LAMBDA|INDEX|MATCH|SUMPRODUCT",
    ),
    F(
        code="LAMBDA", name_cn="自定义函数", category="逻辑",
        tags="365新增|高级", min_version="Excel 365", difficulty=4, importance=2,
        syntax="LAMBDA([参数1, 参数2, …], 计算式)",
        args_desc="参数：自定义函数要接收的输入，0~253 个\n"
                  "计算式：用这些参数写出的结果（最后一个参数）",
        returns="一个可被调用的匿名函数；直接在单元格里写会返回 #CALC!",
        description="不写 VBA 也能自己造函数，配「公式 → 名称管理器」可以全局复用。",
        example_formula="=LAMBDA(金额, 税率, 金额*(1+税率))(B2, 0.13)",
        example_result="写完立刻用括号传参调用来求含税金额；"
                       "也可以在名称管理器里注册成「含税」，之后像内置函数一样用 =含税(B2, 0.13)",
        pitfalls="① **单独写会返回 #CALC!** —— LAMBDA 必须被调用，或者注册成名称\n"
                 "② 想做递归要在里面用 IF 留终止条件，写错会直接栈溢出崩掉 Excel\n"
                 "③ 只有 365 支持，且**保存为 .xlsm 才能让别处复用名称**\n"
                 "④ 参数名同样不能像单元格地址",
        use_cases="封装公司特有的算法（阶梯提成、账期折算）；给重复公式一个业务名；"
                  "配合 MAP / REDUCE / BYROW 做数组级运算",
        related="LET|MAP|REDUCE|BYROW",
    ),

    # ==================================================================
    # 数学与三角函数
    # ==================================================================
    F(
        code="SUM", name_cn="求和", category="数学与三角函数",
        tags="必学|骨架", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="SUM(数值1, [数值2], …)",
        args_desc="数值1：数字、单元格或区域\n数值2…：最多再给 254 个，可以是多个不连续区域",
        returns="所有数值之和；区域里的文本与逻辑值被忽略",
        description="最常用的求和。",
        example_formula="=SUM(B2:B100)",
        example_result="把 B2 到 B100 的数字加起来；空单元格与文字自动跳过",
        pitfalls="① 区域里**文本型数字不会被求和**，结果偏小还看不出问题，"
                 "用 SUM(--区域) 或先 VALUE 转换\n"
                 "② 整列 SUM(A:A) 在含错误值时会返回错误，定位不到是哪一行\n"
                 "③ 求和结果明显不对时先看有没有隐藏行 —— 只要不筛选，SUM 照样算隐藏行",
        use_cases="金额合计；工时汇总；不连续区域一次求和（用逗号分隔多个区域）",
        related="SUMIF|SUMIFS|SUBTOTAL|SUMPRODUCT",
    ),
    F(
        code="SUMIF", name_cn="单条件求和", category="数学与三角函数",
        tags="必学|报表主力", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="SUMIF(条件区域, 条件, [求和区域])",
        args_desc="条件区域：拿什么去比对\n"
                  "条件：写成 \"华东\"、\">100\"、\">=\"&G2 这类文本；通配符 * ? 可用\n"
                  "求和区域：实际要加总的区域；省略时对条件区域自己求和",
        returns="满足条件的单元格之和",
        description="按一个条件汇总。",
        example_formula='=SUMIF(A2:A100, "华东", C2:C100)',
        example_result="A 列等于「华东」的那些行，把 C 列加起来",
        pitfalls="① **条件区域与求和区域的大小必须一致**，错位不会报错但结果是错的\n"
                 "② 条件里的比较符要**整体加引号**：`\">100\"` 对，`>\"100\"` 错\n"
                 "③ 引用单元格拼条件要写 `\">=\"&G2`，别忘了 & 和引号\n"
                 "④ 求和区域省略时按条件区域算，很容易把行号列算错",
        use_cases="按大区 / 部门 / 产品汇总；按金额门槛统计（>1000 的合计）；"
                  "按关键字模糊汇总（\"*华东*\"）",
        related="SUMIFS|COUNTIF|AVERAGEIF|SUMPRODUCT",
    ),
    F(
        code="SUMIFS", name_cn="多条件求和", category="数学与三角函数",
        tags="必学|报表主力|最常用函数之一", min_version="Excel 2007",
        difficulty=2, importance=3,
        syntax="SUMIFS(求和区域, 条件区域1, 条件1, [条件区域2, 条件2], …)",
        args_desc="求和区域：**写在第一个**（与 SUMIF 顺序相反，最容易记错）\n"
                  "条件区域1：第一个筛选区域\n"
                  "条件1：\"华东\" / \">=2026/1/1\" / \">=\"&G2\n"
                  "……条件成对往后排，最多 127 对，全部是「并且」关系",
        returns="同时满足全部条件的单元格之和",
        description="按多个条件汇总，报表里出现频率最高的函数之一。",
        example_formula='=SUMIFS(D2:D100, A2:A100, "华东", B2:B100, ">=2026/1/1", B2:B100, "<2026/4/1")',
        example_result="A 列是华东、且 B 列日期落在 2026 年第一季度的 D 列金额合计",
        pitfalls="① **参数顺序与 SUMIF 相反**：求和区域在最前面。这是最高频的失手点\n"
                 "② 所有区域必须**行数一致**，否则 #VALUE!\n"
                 "③ 每个条件都要「区域 + 条件」成对写，漏一个就整体错位\n"
                 "④ 同列多条件（区间）就写两遍区域，如日期 >= 且 < 各写一次\n"
                 "⑤ 条件是日期时写 \"2026/1/1\" 这样的文本可能因区域设置不认，"
                 "稳妥写法是 `\">=\"&DATE(2026,1,1)`",
        use_cases="按「大区 + 月份」汇总；按「部门 + 状态」统计；"
                  "区间汇总（金额段、日期段）；多条件对账",
        related="SUMIF|COUNTIFS|AVERAGEIFS|SUMPRODUCT",
    ),
    F(
        code="SUMPRODUCT", name_cn="数组乘积求和", category="数学与三角函数",
        tags="必学|高手利器|替代辅助列", min_version="Excel 2003",
        difficulty=3, importance=3,
        syntax="SUMPRODUCT(数组1, [数组2], …)",
        args_desc="数组1：第一组数（区域或 TRUE/FALSE 数组）\n"
                  "数组2…：最多再给 254 组，**所有数组维度必须完全一致**\n"
                  "各组对应位置相乘，再把乘积全部相加",
        returns="诸元素乘积之和",
        description="不进 Ctrl+Shift+Enter 也能做数组运算的万金油，能替代大量辅助列。",
        example_formula='=SUMPRODUCT((A2:A100="华东")*(C2:C100>1000)*D2:D100)',
        example_result="华东、且金额大于 1000 的行，把 D 列加起来。"
                       "比 SUMIFS 灵活：条件可以任意组合、还能做「或」",
        pitfalls="① **维度必须一致**，A2:A100 配 C2:C90 会报 #VALUE!\n"
                 "② 条件要自己乘 `*` 连接，「或」用 `+`，但「或」的结果可能 >1，"
                 "要包 --(...)>0 或 SUM(--(...))\n"
                 "③ 文本列直接参与乘法会报 #VALUE!，用 -- 转成 1 / 0 或先 N()\n"
                 "④ 整列引用（A:A）会拖慢文件，能写区间就写区间\n"
                 "⑤ 它返回的是「乘积之和」，一个数组时才是单纯的求和",
        use_cases="多条件（含「或」）求和；条件计数；中式排名（不并列）；"
                  "加权平均；带权重的分摊",
        related="SUMIFS|COUNTIFS|AGGREGATE",
    ),
    F(
        code="ROUND", name_cn="四舍五入", category="数学与三角函数",
        tags="必学|金额必用", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="ROUND(数值, 位数)",
        args_desc="数值：要处理的值\n"
                  "位数：正数 = 保留几位小数；0 = 取整；负数 = 对十位 / 百位取整",
        returns="按指定位数四舍五入后的数值",
        description="按位数四舍五入，金额计算里必用。",
        example_formula="=ROUND(B2*C2*0.13, 2)",
        example_result="税额算到 2 位小数。位数写 0 就是取整，写 -2 就是对百位取整（1234 → 1200）",
        pitfalls="① **它改的是数值本身，改格式只是看起来变了**。"
                 "对账差额往往就出在「显示 2 位但底数还是 15 位小数」\n"
                 "② 只改单元格格式为 2 位小数**不代表**参与计算时被四舍五入\n"
                 "③ 银行的「四舍六入五成双」要用 ROUND 之外的规则，"
                 "财务口径有要求时别想当然",
        use_cases="金额与税额保留 2 位；单价折算取整；按百元 / 千元取整上报",
        related="ROUNDUP|ROUNDDOWN|INT|TEXT",
    ),
    F(
        code="ROUNDUP", name_cn="向上舍入", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="ROUNDUP(数值, 位数)",
        args_desc="数值：要处理的值\n位数：保留几位；0 取整；负数对十 / 百位进位",
        returns="**远离零方向**舍入的结果（正数变大，负数变小）",
        description="无条件进位，用于「不足一个也算一个」的场景。",
        example_formula="=ROUNDUP(B2/10, 0)*10",
        example_result="B2=31 → 向上取到 40。算装箱数、按整箱下单时用",
        pitfalls="① 对负数它是「更负」（-2.1 → -3），想单纯「变大」得用 CEILING\n"
                 "② 与 CEILING 的区别：ROUNDUP 按小数位，CEILING 按指定倍数",
        use_cases="装箱 / 打包数量；按整打、整箱下单；不足一天算一天",
        related="ROUND|ROUNDDOWN|CEILING|INT",
    ),
    F(
        code="ROUNDDOWN", name_cn="向下舍入", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="ROUNDDOWN(数值, 位数)",
        args_desc="数值：要处理的值\n位数：保留几位；0 取整；负数对十 / 百位舍掉",
        returns="**朝零方向**舍入的结果（截断，不做四舍五入）",
        description="无条件截断，不做四舍五入。",
        example_formula="=ROUNDDOWN(B2, 0)",
        example_result="B2=9.99 → 9。算「满额才算」的场景用它，不能用 INT 代替",
        pitfalls="① 与 INT 不等价：负数是 -9.99 → -9，而 INT(-9.99) = -10\n"
                 "② 名字像 TRUNC，其实行为一致（TRUNC 更直白，建议负数场景用 TRUNC）",
        use_cases="按天数折算（不满一天不算）；整单发货数量；金额抹零",
        related="ROUND|ROUNDUP|INT|TRUNC",
    ),
    F(
        code="INT", name_cn="向下取整", category="数学与三角函数",
        tags="日期计算常用", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="INT(数值)",
        args_desc="数值：要取整的值",
        returns="**小于等于它的最大整数**",
        description="向下取整；因为日期在 Excel 里就是数字，它也是取日期部分的常用手法。",
        example_formula="=INT(NOW())",
        example_result="NOW() 是 2026/9/23 14:05 → 返回 2026/9/23 00:00，即「今天零点」",
        pitfalls="① 对负数是往更小走：INT(-2.1) = -3，这和 ROUNDDOWN 不同\n"
                 "② 取日期部分推荐 INT，取时间部分推荐 `MOD(值, 1)`",
        use_cases="剥掉时间只留日期；月份 = (月份数-1)/12 的整除；时间转小时数",
        related="MOD|ROUNDDOWN|TRUNC|DATE",
    ),
    F(
        code="MOD", name_cn="求余数", category="数学与三角函数",
        tags="日期计算常用", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="MOD(被除数, 除数)",
        args_desc="被除数：要取余的数\n除数：除以多少",
        returns="余数，**符号与除数一致**",
        description="求余数，在日期时间与循环规律里非常好用。",
        example_formula="=MOD(B2, 1)",
        example_result="B2=2026/9/23 14:05 → 0.5868…，即「当天已过的比例」。"
                       "乘 24 得小时数，乘 1440 得分钟数",
        pitfalls="① 除数为 0 返回 #DIV/0!\n"
                 "② 负数结果与直觉不同：MOD(-1, 3) = 2（不是 -1），"
                 "循环取模时反而正是你要的\n"
                 "③ 浮点误差会让 MOD(0.3, 0.1) 得到 0.0999999…，判断相等要留容差",
        use_cases="取时间部分（MOD(值,1)*24 得小时）；按奇偶 / 周期分组；"
                  "隔行填色规则；工资按周循环排班",
        related="INT|QUOTIENT|WEEKDAY|HOUR",
    ),
    F(
        code="ABS", name_cn="绝对值", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="ABS(数值)",
        args_desc="数值：要去掉正负号的数",
        returns="绝对值",
        description="去掉正负号。",
        example_formula="=ABS(B2-C2)<0.01",
        example_result="判断两个金额是否相等时，用「差值绝对值小于 0.01」避免浮点误差误判",
        pitfalls="① 它只去符号，不改变数值精度\n"
                 "② 想「把正负都算成收入」用它；想保留方向做金额方向判断别用",
        use_cases="金额差异比较；偏差幅度统计；误差容差判断",
        related="SIGN|ROUND",
    ),
    F(
        code="PRODUCT", name_cn="连乘", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="PRODUCT(数值1, [数值2], …)",
        args_desc="数值1：数字或区域\n数值2…：最多再给 254 个",
        returns="所有数值相乘的积",
        description="连乘，用来算复利、连乘系数。",
        example_formula="=PRODUCT(1+B2:B4)-1",
        example_result="B2:B4 是三年增长率（如 5%、3%、2%），返回三年累计增长率。"
                       "返回多重值时新版 Excel 会自动溢出",
        pitfalls="① 区域里有 0 会让结果直接变 0，用前先确认没有空值被当 0 算\n"
                 "② 老版本直接写 PRODUCT(1+B2:B4) 是按普通公式算，"
                 "需要配合数组输入或改用 SUMPRODUCT",
        use_cases="复利 / 累计增长率；连乘系数（体积换算、折扣链）",
        related="SUM|SUMPRODUCT|POWER|EXP",
    ),
    F(
        code="SUBTOTAL", name_cn="可见单元格统计", category="数学与三角函数",
        tags="必学|筛选场景", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="SUBTOTAL(功能号, 引用1, [引用2], …)",
        args_desc="功能号：1~11 = 统计方式（含手动隐藏行）；"
                  "101~111 = 同一种统计但**忽略手动隐藏行**\n"
                  "  1 / 101 平均值　2 / 102 计数　3 / 103 非空计数　4 / 104 最大值\n"
                  "  5 / 105 最小值　9 / 109 求和　……\n"
                  "引用1：要统计的区域",
        returns="按功能号算出的统计值",
        description="只统计「看得见」的行，筛选后合计的正确姿势。",
        example_formula="=SUBTOTAL(9, D2:D100)",
        example_result="对 D 列求和；筛选后只加可见行，这是它和 SUM 的关键区别",
        pitfalls="① **SUBTOTAL 会忽略区域内其他 SUBTOTAL 的结果**，"
                 "所以总计行放 SUBTOTAL 不会重复计算 —— 这是它的设计意图\n"
                 "② 9 和 109 的区别：109 连「手动右键隐藏」的行也不算，"
                 "9 只忽略筛选掉的行。多数人想要 109 的效果\n"
                 "③ 筛选 + 汇总表放在一起时，别用 SUM 又用 SUBTOTAL，口径会不一致\n"
                 "④ 状态栏显示的计数是按 103 口径，别和 102 混用对照",
        use_cases="筛选后的合计；带分类小计的报表；只统计可见数据的平均值",
        related="AGGREGATE|SUM|COUNT|SUMIF",
    ),
    F(
        code="AGGREGATE", name_cn="高级聚合", category="数学与三角函数",
        tags="高级|能忽略错误值", min_version="Excel 2010", difficulty=3, importance=2,
        syntax="AGGREGATE(功能号, 选项, 引用, [k])",
        args_desc="功能号：1~19，除 SUBTOTAL 那 11 种外还多了 LARGE / SMALL / "
                  "PERCENTILE / QUARTILE / MODE 等\n"
                  "选项：5 = 忽略手动隐藏行　6 = 忽略错误值　7 = 两者都忽略\n"
                  "  1 / 2 / 3 = 同上三条，但连嵌套的小计也一并忽略；"
                  "0（或省略）/ 4 = 谁也不忽略\n"
                  "引用：统计区域\n"
                  "k：仅当功能号是 14~19（第 k 大 / 第 k 百分位等）时才需要",
        returns="按功能号算出的统计值",
        description="SUBTOTAL 的加强版：不仅能只算可见行，还能同时忽略错误值。",
        example_formula="=AGGREGATE(9, 6, D2:D100)",
        example_result="D 列求和，并且**跳过所有错误值**。"
                       "数据里混着 #N/A 时，这是唯一能直接求和的写法",
        pitfalls="① 功能号最容易记错：9 才是求和，1 是平均值\n"
                 "② 用 14~19 时 k 必填；用 1~13 时多写 k 会报错\n"
                 "③ 语法是 `AGGREGATE(功能号, 选项, 引用, [k])`，"
                 "只有 14~19 才接受 `(功能号, 选项, 数组, k)` 的数组形式",
        use_cases="含错误值的列求和 / 计数；筛选后取第 k 大；"
                  "只统计可见行的极值（不用辅助列）",
        related="SUBTOTAL|LARGE|SMALL|SUM",
    ),
    F(
        code="CEILING", name_cn="按倍数向上取整", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="CEILING(数值, 基数)",
        args_desc="数值：要取整的值\n基数：向上取到它的整数倍（如 0.5、10、100）",
        returns="不小于数值、且是基数整数倍的最小数",
        description="按指定倍数向上取整。",
        example_formula="=CEILING(B2, 0.5)",
        example_result="B2=2.3 → 2.5；B2=0.1 → 0.5。用于按半小时计费、按百元报价",
        pitfalls="① 老版本 ``CEILING`` 对「数值为正、基数为负」会报 #NUM!，"
                 "要处理负数用 ``CEILING.MATH``\n"
                 "② 与 ROUNDUP 不同：这里是按**倍数**不是按小数位",
        use_cases="按时段计费（半小时 / 15 分钟一跳）；按 100 元为单位报价；"
                  "箱子按 12 的倍数下单",
        related="FLOOR|ROUNDUP|MROUND|INT",
    ),
    F(
        code="FLOOR", name_cn="按倍数向下取整", category="数学与三角函数",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="FLOOR(数值, 基数)",
        args_desc="数值：要取整的值\n基数：向下取到它的整数倍",
        returns="不大于数值、且是基数整数倍的最大数",
        description="按指定倍数向下取整。",
        example_formula="=FLOOR(B2, 10)",
        example_result="B2=37 → 30。用于按整十 / 整箱向下取，或把时间归到 5 分钟格",
        pitfalls="① 与 CEILING 一样，负数 + 负数基数在老版本会 #NUM!，"
                 "需要时用 ``FLOOR.MATH``\n"
                 "② 把时间归整时基数要用 `TIME(0,5,0)`，写成 5 是按「5 天」对齐",
        use_cases="按整箱 / 整十下取；时间归到最近的 5 分钟；分段区间起点",
        related="CEILING|ROUNDDOWN|MROUND|TIME",
    ),
    F(
        code="MROUND", name_cn="按倍数就近取整", category="数学与三角函数",
        tags="", min_version="Excel 2007", difficulty=2, importance=2,
        syntax="MROUND(数值, 倍数)",
        args_desc="数值：要取整的值\n倍数：要取到它的整数倍",
        returns="离数值最近的倍数；正好在中间（如 1.5 对 1）时**远离零**舍入",
        description="就近取到指定倍数，比「先除再乘再四舍五入」干净得多。",
        example_formula="=MROUND(B2, 5)",
        example_result="B2=12 → 10；B2=13 → 15。按 5 的倍数取最接近的值",
        pitfalls="① **两个参数的符号必须一致**，一正一负返回 #NUM!\n"
                 "② 老版本 2003 没有这个函数，2007 起才有\n"
                 "③ 想固定向上用 CEILING、固定向下用 FLOOR",
        use_cases="按 5 元 / 0.5 元就近取价；时间就近归整；刻度对齐",
        related="CEILING|FLOOR|ROUND",
    ),
    F(
        code="RAND", name_cn="随机小数", category="数学与三角函数",
        tags="会重算|注意", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="RAND()",
        args_desc="无参数",
        returns="0 到 1 之间的随机小数（可等于 0，不会等于 1）",
        description="生成 0~1 的随机数。",
        example_formula="=RAND()*100+1",
        example_result="生成 1~101 之间的随机小数。"
                       "取随机整数更推荐 RANDBETWEEN",
        pitfalls="① **任何一次重算都会变**：改别的单元格、保存、重开都会刷新，"
                 "想固定要先复制 → 右键「选择性粘贴 → 值」\n"
                 "② 写 RAND() 的单元格一直在动，会拖慢大表；"
                 "确认后立刻转成数值\n"
                 "③ 它不保证「不重复」，随机抽号要用 RAND 辅助列 + RANK 去重",
        use_cases="随机抽样分组；生成测试数据；随机排序的辅助列",
        related="RANDBETWEEN|RANDARRAY|RANK.EQ",
    ),
    F(
        code="RANDBETWEEN", name_cn="随机整数", category="数学与三角函数",
        tags="会重算|注意", min_version="Excel 2007", difficulty=1, importance=2,
        syntax="RANDBETWEEN(下限, 上限)",
        args_desc="下限：最小整数\n上限：最大整数（两端都含）",
        returns="下限到上限之间的随机整数",
        description="生成区间内的随机整数。",
        example_formula="=RANDBETWEEN(1, 100)",
        example_result="1~100 之间的随机整数（含 1 和 100）",
        pitfalls="① 同样是**易失函数**，每次重算都变，抽签完要立刻转数值\n"
                 "② 可以重复：要「不重复随机数」得用辅助列 RAND + RANK，"
                 "或者 365 的 SORTBY + SEQUENCE\n"
                 "③ 需要 2007 及以上（2003 里要挂「分析工具库」加载项）",
        use_cases="抽签 / 摇号；随机分配责任人；造测试数据",
        related="RAND|RANDARRAY|SEQUENCE|SORTBY",
    ),
]
