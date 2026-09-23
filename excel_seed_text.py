# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（四）文 本
================================================================================
共 22 个条目。字段规范见 ``excel_seed_schema``；日期与时间见 ``excel_seed_date``。

导入的脏数据问题九成都落在这里 —— 空格、文本型数字、分隔符、拆列。

一条最实用的经验：
**看到任何「看起来对但比不出来」的数据，先怀疑它是文本，用 TRIM / VALUE / TEXT 洗一遍。**
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    # ==================================================================
    # 文本
    # ==================================================================
    F(
        code="LEFT", name_cn="取左边", category="文本",
        tags="必学|清洗", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="LEFT(文本, [字符数])",
        args_desc="文本：要处理的字符串或单元格\n字符数：取几个字符；省略为 1",
        returns="从左边开始指定个数的字符",
        description="从字符串开头截取。",
        example_formula="=LEFT(A2, 2)",
        example_result='A2="华东-上海" → "华东"。地区前缀提取的标准写法',
        pitfalls="① 按**字符**数，不是字节数。中文一个字算一个（要按字节用 LEFTB）\n"
                 "② 字符数给负数会 #VALUE!\n"
                 "③ 数字截出来是**文本**，要参与计算得配 VALUE 或 `--`\n"
                 "④ 取出来的内容里可能带尾部空格，再套一层 TRIM 更稳",
        use_cases="取地区 / 编号前缀；取年份前两位；从编码里取分类码",
        related="RIGHT|MID|LEN|TRIM|TEXTBEFORE",
    ),
    F(
        code="RIGHT", name_cn="取右边", category="文本",
        tags="必学|清洗", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="RIGHT(文本, [字符数])",
        args_desc="文本：要处理的字符串\n字符数：取几个字符；省略为 1",
        returns="从右边开始指定个数的字符",
        description="从字符串末尾截取。",
        example_formula="=RIGHT(A2, 4)",
        example_result='A2="订单-20260923" → "0923"。后缀提取的标准写法',
        pitfalls="① 负数字符数会 #VALUE!\n"
                 "② **长度不固定时最危险**：`RIGHT(A2, 6)` 在有些行会切掉不该切的内容，"
                 "稳妥做法是先算长度：`RIGHT(A2, LEN(A2)-FIND(\"-\", A2))`\n"
                 "③ 截出的是文本，数字要转换",
        use_cases="取文件名后缀 / 扩展名；取编号末几位；取手机号后 4 位",
        related="LEFT|MID|LEN|FIND|TEXTAFTER",
    ),
    F(
        code="MID", name_cn="取中间一段", category="文本",
        tags="必学|清洗|身份证必用", min_version="Excel 2003", difficulty=2,
        importance=3,
        syntax="MID(文本, 起始位置, 字符数)",
        args_desc="文本：要处理的字符串\n"
                  "起始位置：从第几个字符开始（**从 1 开始数**，不是 0）\n"
                  "字符数：往后取几个",
        returns="从指定位置开始的指定长度字符",
        description="从任意位置截取一段，是「定长字段」数据的主力工具。",
        example_formula="=MID(A2, 7, 8)",
        example_result="从 18 位身份证号里取第 7~14 位，即出生日期 8 位数字，"
                       "通常再套 TEXT：`=TEXT(MID(A2,7,8),\"0000-00-00\")`",
        pitfalls="① **起始位置从 1 开始**，写成 0 会 #VALUE!（这是从编程语言过来的人第一坑）\n"
                 "② 起始位置超出长度会返回空文本 \"\"，不报错，下游会静默拿到空值\n"
                 "③ 字符数是「长度」不是「结束位置」，两者极易写混\n"
                 "④ 定长字段（如老系统的固定宽度导出）用 MID 最合适；"
                 "分隔符分隔的用 TEXTAFTER / TEXTBEFORE 更省事",
        use_cases="身份证取生日 / 性别；编码取固定段；从日期串里取年月日；"
                  "从拼接字段里拆内容",
        related="LEFT|RIGHT|FIND|LEN|TEXT|TEXTSPLIT",
    ),
    F(
        code="LEN", name_cn="长度", category="文本",
        tags="必学|清洗", min_version="Excel 2003", difficulty=1, importance=3,
        syntax="LEN(文本)",
        args_desc="文本：要测的字符串或单元格",
        returns="字符个数（**空格也算**）",
        description="数字符串有几个字符。",
        example_formula="=LEN(A2)",
        example_result='A2=" 华东 " → 4（前后空格都算）。'
                       "所以 LEN(A2) 和 LEN(TRIM(A2)) 不等时，说明有空格",
        pitfalls="① **它把空格算进去**，这正是它最有用的地方："
                 "用它和清洗后的长度对比，就能发现隐藏空格\n"
                 "② 只数字符不数字节，中文一个字算 1（要字节用 LENB）\n"
                 "③ 看不见的字符（CHAR(160) 非断行空格）LEN 照样算，"
                 "TRIM 却删不掉，要用 SUBSTITUTE(A2, CHAR(160), \"\")",
        use_cases="检查前后空格；校验定长字段（身份证 18 位）；"
                  "配合 LEFT/RIGHT/MID 算截取长度；找出异常长度的记录",
        related="TRIM|LENB|CLEAN|MID|SUBSTITUTE",
    ),
    F(
        code="FIND", name_cn="找位置（区分大小写）", category="文本",
        tags="必学|清洗", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="FIND(要找的文本, 被查找文本, [起始位置])",
        args_desc="要找的文本：想定位的子串\n"
                  "被查找文本：在哪个字符串里找\n"
                  "起始位置：从第几个字符开始找；省略为 1",
        returns="子串首次出现的位置（从 1 开始）；找不到返回 #VALUE!",
        description="找出子串在字符串里的位置，区分大小写。",
        example_formula='=LEFT(A2, FIND("-", A2)-1)',
        example_result='"华东-上海" → 取出「华东」。'
                       "FIND 定位分隔符 + LEFT 截取，是最经典的拆分组合",
        pitfalls="① **区分大小写**：找 \"a\" 找不到 \"ABC\" 里的 A。要不区分改用 SEARCH\n"
                 "② **不支持通配符**，想用 * 定位要换 SEARCH\n"
                 "③ 找不到会报 **#VALUE!** 而不是 0，配合 LEFT 时要套 IFERROR\n"
                 "④ 要用第 2 次出现的位置，得配合起始位置 + SUBSTITUTE 技巧，"
                 "或直接用 TEXTAFTER 的第 3 参数",
        use_cases="按分隔符拆前后段；取 @ 前面的用户名；取扩展名前的文件名；"
                  "判断是否包含（配 ISNUMBER）",
        related="SEARCH|LEFT|RIGHT|MID|TEXTAFTER|TEXTBEFORE",
    ),
    F(
        code="SEARCH", name_cn="找位置（不区分大小写）", category="文本",
        tags="必学|清洗", min_version="Excel 2003", difficulty=2, importance=3,
        syntax="SEARCH(要找的文本, 被查找文本, [起始位置])",
        args_desc="要找的文本：想定位的子串，**可以用通配符** ? 任意单字、* 任意多字\n"
                  "被查找文本：在哪个字符串里找\n"
                  "起始位置：从第几个字符开始；省略为 1",
        returns="首次出现的位置（从 1 开始）；找不到返回 #VALUE!",
        description="找出子串位置，忽略大小写、支持通配符。",
        example_formula='=ISNUMBER(SEARCH("华东", A2))',
        example_result="A2 里只要含「华东」就返回 TRUE，"
                       "**做模糊包含判断的标准写法**",
        pitfalls="① 找不到同样是 #VALUE!，套 ISNUMBER 或 IFERROR 才安全\n"
                 "② 通配符是优点也是风险：要找真的 `*` 或 `?` 得写 `~*` `~?` 转义\n"
                 "③ 它不区分大小写，需要区分时才用 FIND",
        use_cases="模糊包含判断（配 ISNUMBER）；不区分大小写地定位；"
                  "按通配符定位一段内容；条件计数时的辅助判断",
        related="FIND|ISNUMBER|SUBSTITUTE|TEXTBEFORE",
    ),
    F(
        code="SUBSTITUTE", name_cn="替换文本", category="文本",
        tags="必学|清洗|最常用清洗函数", min_version="Excel 2003", difficulty=2,
        importance=3,
        syntax="SUBSTITUTE(文本, 旧文本, 新文本, [替换第几次出现])",
        args_desc="文本：要处理的字符串\n"
                  "旧文本：要被替换掉的内容\n"
                  "新文本：换成什么（给 \"\" 就是删除）\n"
                  "替换第几次出现：只替换第几次；省略则**全部替换**",
        returns="替换后的文本",
        description="按内容替换文本，是清洗数据的第一把刀。",
        example_formula='=SUBSTITUTE(A2, " ", "")',
        example_result="删掉 A2 里**所有**空格（包括中间的空格，TRIM 只压首尾和连续空格）。"
                       "手机号、身份证、银行卡号清洗就靠这一行",
        pitfalls="① 它是**按内容**替换，不认位置。按位置替换用 REPLACE\n"
                 "② 大小写敏感：替换 \"a\" 不会动 \"A\"\n"
                 "③ **它删不掉 CHAR(160) 非断行空格**（网页复制来的数据常有），"
                 "要写 SUBSTITUTE(A2, CHAR(160), \"\")\n"
                 "④ 第 4 参数给数字只替换那一次；给 0 会 #VALUE!\n"
                 "⑤ 不做通配符匹配：想「删掉所有括号里的内容」单一 SUBSTITUTE 做不到，"
                 "要配 TEXTSPLIT 或多次处理",
        use_cases="删空格 / 删换行 CHAR(10) / 删非断行空格；统一分隔符；"
                  "把「未填写」统一成空；去掉单位文字只留数字",
        related="REPLACE|TRIM|CLEAN|TEXTSPLIT|CHAR",
    ),
    F(
        code="REPLACE", name_cn="按位置替换", category="文本",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="REPLACE(原文本, 起始位置, 替换长度, 新文本)",
        args_desc="原文本：要处理的字符串\n"
                  "起始位置：从第几个字符开始被替换掉（从 1 开始）\n"
                  "替换长度：**替换掉几个字符**\n"
                  "新文本：换成什么；给 \"\" 就等于删除这几个字符",
        returns="替换后的文本",
        description="按位置替换（或删除）一段字符。",
        example_formula='=REPLACE(A2, 1, 3, "")',
        example_result="删掉前 3 个字符。"
                       "要隐藏手机号中间四位：`=REPLACE(A2, 4, 4, \"****\")`",
        pitfalls="① **三个数字参数最容易写混**：起始位置、替换长度、新文本长度三者互不相关，"
                 "新文本比被替换的多或少都会让整体长度变化\n"
                 "② 与 SUBSTITUTE 的区别务必分清：**REPLACE 认位置，SUBSTITUTE 认内容**\n"
                 "③ 起始位置超出长度会 #VALUE!",
        use_cases="脱敏（手机号 / 身份证打码）；去掉固定前缀；"
                  "在固定位置插入字符；统一编号格式",
        related="SUBSTITUTE|MID|LEFT|REPT",
    ),
    F(
        code="TRIM", name_cn="去多余空格", category="文本",
        tags="必学|清洗|导入数据必用", min_version="Excel 2003", difficulty=1,
        importance=3,
        syntax="TRIM(文本)",
        args_desc="文本：要清理的字符串",
        returns="删掉**首尾空格**，并把**中间连续的多个空格压成一个**",
        description="清理空格，导入数据后第一件该做的事。",
        example_formula='=TRIM(A2)',
        example_result='" 华 东 " → "华 东"。'
                       "VLOOKUP 明明看着一样却查不到，九成就是空格问题",
        pitfalls="① **它删不掉 CHAR(160) 非断行空格** —— "
                 "从网页 / 某些系统复制的数据里全是这种空格，TRIM 对它无效。"
                 "要配 `SUBSTITUTE(A2, CHAR(160), \" \")` 再 TRIM\n"
                 "② 全角空格（CHAR(12288)）它也删不掉\n"
                 "③ 它**不会**删掉中间单独的空格，"
                 "要全删用 `SUBSTITUTE(A2, \" \", \"\")`\n"
                 "④ 中英文之间不加空格是它做不到的，别指望",
        use_cases="查找匹配失败时的第一招；导入 CSV 后的清洗；"
                  "统一姓名 / 公司名格式；去首尾空格后去重",
        related="SUBSTITUTE|CLEAN|LEN|VALUE",
    ),
    F(
        code="TEXT", name_cn="把数字变指定格式的文本", category="文本",
        tags="必学|日期格式化|易错", min_version="Excel 2003", difficulty=3,
        importance=3,
        syntax="TEXT(值, 格式代码)",
        args_desc="值：数字、日期或公式结果\n"
                  "格式代码：用双引号括起来，如 \"yyyy年m月d日\"、\"0.00\"、\"#,##0\"、"
                  "\"0000-00-00\"、\"[h]:mm\"、\"0%\"",
        returns="格式化后的**文本**",
        description="把数字 / 日期按指定样式转成文本。",
        example_formula='=TEXT(TODAY(), "yyyy年m月d日")',
        example_result='2026/9/23 → "2026年9月23日"。'
                       "注意 m 是月、mm 是补零的月、MM 在某些环境会被当分钟解读",
        pitfalls="① **结果是文本，不能再参与计算**。想「看起来 2 位小数但还能算」"
                 "请用单元格格式或 ROUND，不要用 TEXT\n"
                 "② 格式代码里的字母有讲究：`m` 月 vs `mm` 分钟在同一处会冲突，"
                 "日期里紧跟 h 的 m 会被当分钟，稳妥写法是 \"hh:mm\" 与 \"yyyy-m-d\" 分开\n"
                 "③ **格式代码受系统区域设置影响**：\"dd/mm/yyyy\" 在中文环境里没问题，"
                 "但换台机器可能解析不同，跨机交付要小心\n"
                 "④ 从身份证取生日常见写法 `TEXT(MID(A2,7,8),\"0000-00-00\")` —— "
                 "这里用 0 占位而不是 y，因为取出来的是纯数字串",
        use_cases="把日期拼进文字（「截至 2026年9月23日」）；"
                  "身份证 8 位数字转成日期样式；金额千分位展示；"
                  "把数字补成固定位数（\"0000\"）",
        related="VALUE|DATEVALUE|CONCAT|TEXTJOIN|MID",
    ),
    F(
        code="VALUE", name_cn="文本转数字", category="文本",
        tags="必学|清洗|脏数据必用", min_version="Excel 2003", difficulty=2,
        importance=3,
        syntax="VALUE(文本)",
        args_desc="文本：数字样式的文本串，如 \"1234.5\"、\"¥1,234\"、\"12%\"、\"2026/9/23\"",
        returns="转换后的数值（日期会变成日期序列值）；不认识的内容返回 #VALUE!",
        description="把文本型数字变成真数字，或把日期串变成真日期。",
        example_formula="=VALUE(A2)",
        example_result='"1234.5" → 1234.5（右对齐、可参与计算）。'
                       "或者用更短的 `=--A2`、`=A2*1`",
        pitfalls="① 转不了的会 #VALUE!，套 IFERROR 或用 IF(ISNUMBER(...)) 先判断\n"
                 "② 带货币符号、千分位、百分号的通常能转（\"¥1,234\" → 1234，\"12%\" → 0.12），"
                 "但**取决于区域设置**，跨环境不一定灵\n"
                 "③ 它不认识中文里的「元」「万元」，得先 SUBSTITUTE 掉\n"
                 "④ 大批量转换最快的方式其实是「分列」或 `--` —— "
                 "**`--A2` 比 VALUE(A2) 更短也更快**",
        use_cases="SUM 求和结果偏小时的排查与修复；导入数据的类型矫正；"
                  "日期串转真日期（再用 YEAR/MONTH 取字段）",
        related="TEXT|NUMBERVALUE|ISNUMBER|SUBSTITUTE|TRIM",
    ),
    F(
        code="CONCAT", name_cn="连接文本", category="文本",
        tags="必学", min_version="Excel 2019", difficulty=1, importance=3,
        syntax="CONCAT(文本1, [文本2], …)",
        args_desc="文本1：单元格、区域或字符串\n文本2…：最多再给 252 个，**可以直接给区域**",
        returns="拼接后的文本（没有分隔符）",
        description="把多段文本接起来，能直接吃区域。",
        example_formula="=CONCAT(A2:C2)",
        example_result="把 A2、B2、C2 三个格子接在一起。"
                       "老写法是 `A2&B2&C2`，效果一样、更短",
        pitfalls="① **不给分隔符**，想加分隔符用 TEXTJOIN，或者自己插 `&\"-\"&`\n"
                 "② 它会把区域里的**每个单元格**都接上，包括空单元格（空的不影响结果）；"
                 "别指望它自动跳过\n"
                 "③ 日期会变成日期序列值！`CONCAT(\"截至\", TODAY())` 得到「截至46282」，"
                 "要套 TEXT 才行\n"
                 "④ 只是拼接没有任何分隔符，做 CSV 导出时容易粘成一片\n"
                 "⑤ 老版本只有 CONCATENATE（不能给区域）",
        use_cases="拼完整地址；拼编号；把多列拼成一列（多用于导出）；"
                  "拼进一段提示文案",
        related="TEXTJOIN|TEXT|CHOOSECOLS|TEXTSPLIT",
    ),
    F(
        code="TEXTJOIN", name_cn="带分隔符连接", category="文本",
        tags="必学|实用|替代CONCAT", min_version="Excel 2019", difficulty=2,
        importance=3,
        syntax='TEXTJOIN(分隔符, 是否忽略空, 文本1, [文本2], …, 文本252)',
        args_desc='分隔符：放中间的东西，如 "、"、","、CHAR(10)\n'
                  '是否忽略空：TRUE = 跳过空单元格（**几乎总是想要 TRUE**）；FALSE = 空的也占位\n'
                  "文本1：可以给区域\n文本2…：最多再给 251 个",
        returns="拼接后的文本",
        description="用分隔符把多段文本接起来，最常用是「把一列拼成一个串」。",
        example_formula='=TEXTJOIN("、", TRUE, IF($A$2:$A$100="华东", $B$2:$B$100, ""))',
        example_result="把华东区所有负责人用「、」连成一个串。"
                       "365 里直接回车；老版本要按 Ctrl+Shift+Enter",
        pitfalls="① 第 2 参数给 **FALSE** 会让空单元格也占一个分隔符，"
                 "结果里出现「、、」，所以基本都要给 TRUE\n"
                 "② 与 CONCAT 一样，**日期会变成序列值**，要 TEXT 包一下\n"
                 "③ 拼接后总长度上限 32767 字符，超了返回 #VALUE!\n"
                 "④ 用 IF 造条件筛选时，不满足的位置会得到 FALSE 而不是空，"
                 "要显式写 `\"\"` 并配合 TRUE 忽略空\n"
                 "⑤ 需要 2019 / 365",
        use_cases="把一列姓名拼成「张三、李四、王五」；"
                  "把多行备注合并成一段；按条件拼接一串编号；导出时的逗号分隔串",
        related="CONCAT|TEXT|SUBSTITUTE|FILTER",
    ),
    F(
        code="UPPER", name_cn="转大写", category="文本",
        tags="清洗", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="UPPER(文本)",
        args_desc="文本：要转换的字符串（只影响英文字母）",
        returns="全部大写的文本",
        description="英文字母转大写，用来统一格式好比较。",
        example_formula="=UPPER(TRIM(A2))",
        example_result='" ab-01 " → "AB-01"。'
                       "做查找前的统一化处理，避免因大小写不同匹配失败",
        pitfalls="① 只动英文字母，中文数字不受影响\n"
                 "② 它是「造新文本」，不会修改源单元格\n"
                 "③ 大表里整列套 UPPER 会失去「引用关系」（值变了），"
                 "做查找键建议用辅助列或在内存里比较",
        use_cases="统一编号 / 邮箱 / 币种代码；查找匹配前的标准化；"
                  "把用户输入规范化",
        related="LOWER|PROPER|TRIM|EXACT",
    ),
    F(
        code="LOWER", name_cn="转小写", category="文本",
        tags="清洗", min_version="Excel 2003", difficulty=1, importance=2,
        syntax="LOWER(文本)",
        args_desc="文本：要转换的字符串",
        returns="全部小写的文本",
        description="英文字母转小写。",
        example_formula="=LOWER(A2)",
        example_result='"ABC@X.COM" → "abc@x.com"。邮箱标准化常用',
        pitfalls="① 同样只影响英文字母\n"
                 "② 比较两个文本是否「实质相同」时，"
                 "`EXACT(LOWER(A2), LOWER(B2))` 比直接 `=` 更符合直觉",
        use_cases="邮箱统一小写；统一型号代码；查找前标准化",
        related="UPPER|PROPER|EXACT",
    ),
    F(
        code="PROPER", name_cn="首字母大写", category="文本",
        tags="清洗", min_version="Excel 2003", difficulty=1, importance=1,
        syntax="PROPER(文本)",
        args_desc="文本：要转换的字符串",
        returns="每个单词首字母大写、其余小写",
        description="把英文单词首字母转大写（英文姓名、英文标题常用）。",
        example_formula="=PROPER(A2)",
        example_result='"zhang san" → "Zhang San"',
        pitfalls="① **对中文没有意义**，中文不受影响\n"
                 "② 它按空格 / 非字母字符当单词边界，"
                 "所以 \"O'Brien\" 会变成 \"O'Brien\"、\"mcdonald\" 会变成 \"Mcdonald\"（不是 McDonald）\n"
                 "③ 中文人名转拼音后用它，容易出现「Li Xiao Ming」这类不符合习惯的结果，"
                 "人名建议手工核对",
        use_cases="英文姓名规范；英文标题首字母大写；统一导入的英文公司名",
        related="UPPER|LOWER|TRIM",
    ),
    F(
        code="REPT", name_cn="重复文本", category="文本",
        tags="小技巧", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="REPT(文本, 重复次数)",
        args_desc="文本：要重复的内容\n重复次数：重复几遍（0 返回空文本；上限受 32767 字符总长限制）",
        returns="重复拼接后的文本",
        description="把一段文本重复多遍，做简易条形图或补位。",
        example_formula='=REPT("█", B2/10)',
        example_result="B2=85 时得到 8 个方块，"
                       "**在单元格里直接画出一个横向条**，不用图表",
        pitfalls="① 重复次数为 0 返回空文本（不是错误）\n"
                 "② 次数为负会 #VALUE!\n"
                 "③ 结果总长度不能超过 32767 字符，否则 #VALUE! —— "
                 "做条形图时记得给倍率设上限\n"
                 "④ 只用于展示，不参与计算",
        use_cases="单元格内简易条形图；补位对齐（配 LEN 做定长编号）；"
                  "生成分隔线；把「★」重复成星级",
        related="LEN|TEXT|CONCAT|SUBSTITUTE",
    ),
    F(
        code="CHAR", name_cn="字符代码转换", category="文本",
        tags="清洗必备", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="CHAR(数字)",
        args_desc="数字：1~255 的字符代码（Windows 代码页）",
        returns="该代码对应的字符",
        description="按代码取字符，最常用的是拿它表示「看不见的字符」。",
        example_formula='=SUBSTITUTE(A2, CHAR(160), " ")',
        example_result="把非断行空格换成普通空格。"
                       "**这是网页复制的数据清洗的必备一招**",
        pitfalls="① 代码是 **Windows 代码页**口径：CHAR(10) 换行、CHAR(13) 回车、"
                 "CHAR(160) 非断行空格、CHAR(9) 制表符\n"
                 "② **中文汉字不能用 CHAR 生成**（超出 255 会 #VALUE!），"
                 "要用 UNICHAR\n"
                 "③ CHAR(10) 要在单元格里看见换行效果，得同时勾选「自动换行」",
        use_cases="删掉 / 替换非断行空格；在文本里插入换行；删制表符；"
                  "生成不可见分隔符做临时标记",
        related="CODE|UNICHAR|SUBSTITUTE|CLEAN|TEXTJOIN",
    ),
    F(
        code="EXACT", name_cn="严格比较", category="文本",
        tags="", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="EXACT(文本1, 文本2)",
        args_desc="文本1 / 文本2：要比较的两段文本",
        returns="完全相同（**含大小写、含空格**）时 TRUE，否则 FALSE",
        description="区分大小写地比较两段文本。",
        example_formula='=EXACT(A2, B2)',
        example_result='"abc" 与 "ABC" → FALSE；'
                       "普通的 `A2=B2` 会返回 TRUE。用来做严格核对",
        pitfalls="① **它连空格一起比**：' 华东' 与 '华东' 返回 FALSE，"
                 "要先 TRIM\n"
                 "② 它比的是「文本」，数字与文本型的 \"1\" 比较会返回 FALSE，"
                 "类型不一致时先统一\n"
                 "③ 反过来，`=` 比较不区分大小写，"
                 "做数据核对时**用 EXACT 更保险**（能揪出大小写不一致）",
        use_cases="严格核对两份数据的差异；密码 / 验证码比对；"
                  "检查编号大小写是否被改过；去重前的严格判等",
        related="LOWER|UPPER|TRIM|VALUE",
    ),
    F(
        code="TEXTAFTER", name_cn="取分隔符之后", category="文本",
        tags="365新增|替代FIND组合|强烈推荐", min_version="Excel 365",
        difficulty=2, importance=3,
        syntax="TEXTAFTER(文本, 分隔符, [第几次出现], [匹配模式], [没找到时], [是否区分大小写])",
        args_desc="文本：源字符串\n"
                  "分隔符：拿什么切，如 \"-\"、\"@\"\n"
                  "第几次出现：默认 1；给负数表示**从右往左数**（-1 = 最后一个）\n"
                  "匹配模式：0 区分大小写（默认）／1 不区分\n"
                  "没找到时：找不到返回什么；省略则报 #N/A\n"
                  "是否区分大小写：0/1（与匹配模式作用重叠，新版建议用匹配模式）",
        returns="分隔符之后的那一段文本",
        description="按分隔符取后半段，一行替代 FIND + MID + LEN 那串组合。",
        example_formula='=TEXTAFTER(A2, "@")',
        example_result='"zhang@abc.com" → "abc.com"。'
                       "取最后一次出现之后的内容：`=TEXTAFTER(A2, \"-\", -1)`",
        pitfalls="① 找不到分隔符时返回 **#N/A**，加第 5 参数给个兜底值更稳\n"
                 "② **只有 365 / 2024 支持**。这是它最大的限制 —— "
                 "发给老版本用户会显示 #NAME?\n"
                 "③ 第几次出现给负数才是「从右数」，"
                 "取文件名 / 后缀这类需求几乎都用 -1\n"
                 "④ 分隔符默认**区分大小写**",
        use_cases="取邮箱域名；取文件扩展名；按「-」取后半段；"
                  "从长串里取最后一个字段；替代 FIND+MID 的组合",
        related="TEXTBEFORE|TEXTSPLIT|FIND|MID|RIGHT",
    ),
    F(
        code="TEXTSPLIT", name_cn="按分隔符拆成多列", category="文本",
        tags="365新增|强烈推荐|清洗神器", min_version="Excel 365",
        difficulty=3, importance=3,
        syntax='TEXTSPLIT(文本, 列分隔符, [行分隔符], [忽略空], [匹配模式], [填充值])',
        args_desc='文本：要拆的字符串\n'
                  '列分隔符：按它横向拆，如 ","、"、"\n'
                  '行分隔符：按它纵向拆，如 CHAR(10)（可只给列分隔符、也可都给）\n'
                  "忽略空：TRUE = 跳过连续分隔符造成的空段\n"
                  "匹配模式：0 区分大小写 / 1 不区分\n"
                  "填充值：各段长度不一致时补什么；省略补 #N/A",
        returns="拆好的二维数组，自动溢出",
        description="一个函数完成「按分隔符拆成多列 / 多行」，替代「分列」向导和 FIND 组合。",
        example_formula='=TEXTSPLIT(A2, "、")',
        example_result='"华东、华南、华北" → 横向拆成 3 个格子。'
                       "多行用 CHAR(10) 当行分隔符："
                       '`=TEXTSPLIT(A2, "、", CHAR(10))`',
        pitfalls="① **给出「填充值」很重要**：各段长度不同时它会补 #N/A，"
                 "看起来像数据缺失\n"
                 "② 结果会溢出，**目标区域右侧必须为空**，否则 #SPILL!\n"
                 "③ 只有 365 / 2024 支持\n"
                 "④ 它拆出来的永远是**文本**，数字要再套 -- 或 VALUE\n"
                 "⑤ 分隔符是多个字符时也支持（如 \"||\"），比传统「分列」强\n"
                 "⑥ 想要「一行拆成多行」（如备注里的换行）就把行分隔符用上，"
                 "配合 TOCOL 还能源源不断地拉直",
        use_cases="拆分「、」分隔的标签列；把多行备注拆成多行；"
                  "拆中英文混排的地址；解析逗号分隔的导出字段；"
                  "替代「数据 → 分列」且能自动跟随源数据变化",
        related="TEXTAFTER|TEXTBEFORE|TOCOL|VSTACK|SUBSTITUTE",
    ),
    F(
        code="TEXTBEFORE", name_cn="取分隔符之前", category="文本",
        tags="365新增|替代FIND组合|强烈推荐", min_version="Excel 365",
        difficulty=2, importance=3,
        syntax="TEXTBEFORE(文本, 分隔符, [第几次出现], [匹配模式], [没找到时], [是否区分大小写])",
        args_desc="文本：源字符串\n"
                  "分隔符：拿什么切，如 \"-\"、\"@\"、\"(\"\n"
                  "第几次出现：默认 1；负数表示**从右往左数**（-1 = 最后一个）\n"
                  "匹配模式：0 区分大小写（默认）／1 不区分\n"
                  "没找到时：找不到返回什么；省略则报 #N/A\n"
                  "是否区分大小写：0 / 1（新版建议改用匹配模式）",
        returns="分隔符之前的那一段文本",
        description="按分隔符取前半段，TEXTSPLIT 与 TEXTAFTER 的镜像。",
        example_formula='=TEXTBEFORE(A2, "@")',
        example_result='"zhang@abc.com" → "zhang"。'
                       "从「华东(上海)」取括号前的部分：`=TEXTBEFORE(A2, \"(\")`",
        pitfalls="① 找不到分隔符时返回 **#N/A**，加第 5 参数兜底\n"
                 "② **只有 365 / 2024 支持**，老版本打开是 #NAME?\n"
                 "③ 取「路径里最后一层的目录名」这类需求要把第 3 参数给 -1\n"
                 "④ 默认区分大小写；处理用户输入时通常想让匹配模式 = 1",
        use_cases="取 @ 前的用户名；取「-」前的编号；取括号前的名称；"
                  "取文件路径的最后一级目录；替代 LEFT+FIND 的组合",
        related="TEXTAFTER|TEXTSPLIT|LEFT|FIND|MID",
    ),
]
