# -*- coding: utf-8 -*-
"""
================================================================================
Excel 学习中心 · 内置函数库（六）财务 / 数据库 / 工程 / 兼容性
================================================================================
共 22 个条目。字段规范见 ``excel_seed_schema``。

选材理由（不是「官方分类都得凑齐」，而是「这几类真的会被用到」）
--------------------------------------------------------------------------------
* **财务**：贷款月供、利息本金拆分、投资回报 —— 这是最实用的一类，
  也是「会用 Excel」和「会算账」之间的差别。12 个函数值得花一个下午。
* **数据库**：``D`` 系列在 90 年代很风光，现在基本被 SUMIFS / FILTER 取代。
  保留 4 个是为了看懂老文件；新表不要再用它。
* **工程**：单位换算 ``CONVERT`` 偶尔能救命；进制转换再顺带一个。
* **兼容性**：老写法为什么在新版被「改名」，值得知道一次，以后看到不慌。

财务函数有一条铁律，先记住再往下看
--------------------------------------------------------------------------------
**利率和期数的时间单位必须一致。**
年利率 4.9% 算月供 → 利率写 ``4.9%/12``、期数写 ``=年限*12``。
十个算错的人里有九个是忘了这一步。
"""

from __future__ import annotations

from excel_seed_schema import F

SEED = [
    # ==================================================================
    # 财务
    # ==================================================================
    F(
        code="PMT", name_cn="等额月供", category="财务",
        tags="必学|财务核心|买房买车", min_version="Excel 2003", difficulty=3,
        importance=3,
        syntax="PMT(利率, 期数, 现值, [终值], [类型])",
        args_desc="利率：**每期**利率。年利率要除以 12（按月）或 4（按季）\n"
                  "期数：总期数。5 年按月 = 60\n"
                  "现值：借款本金（现值），写成正数\n"
                  "终值：最后一期还清后还要剩多少（贷款通常为 0），省略即 0\n"
                  "类型：0 或省略 = 期末付款；1 = 期初付款（先付 / 租金常见）",
        returns="每期应付款额，**结果是负数**（表示现金流出）",
        description="算等额本息每期要还多少，房贷车贷的核心公式。",
        example_formula="=-PMT(B2/12, C2*12, D2)",
        example_result="B2 年利率 4.9%、C2 年限 20 年、D2 贷款 100 万 → "
                       "月供约 6544 元。前面加负号是为了显示成正数，"
                       "**不是公式写错**",
        pitfalls="① **利率与期数的单位必须一致**：年利率配年数会得到离谱的结果，"
                 "且不报错。按月就一起除 / 乘 12\n"
                 "② **返回负数**是因为它遵循「现金流出为负」的财务惯例，"
                 "嫌难看就在前面加 `-`，别在参数里乱改符号\n"
                 "③ 结果是等额本息（每期总还款相同）；**等额本金要另算**，"
                 "用 PPMT 逐期相加或自己做表\n"
                 "④ 「期初付款」的租金 / 保险费记得把第 5 参数写 1，"
                 "默认 0 会差一期的利息\n"
                 "⑤ 它不是「还款总额」；总额 = 月供 × 期数",
        use_cases="房贷 / 车贷月供；租金测算；分期付款每期金额；"
                  "养老金定投每期存多少；设备融资租赁",
        related="PPMT|IPMT|RATE|NPER|PV",
    ),
    F(
        code="IPMT", name_cn="某期利息", category="财务",
        tags="财务核心|做还款计划表", min_version="Excel 2003", difficulty=3,
        importance=3,
        syntax="IPMT(利率, 期数, 总期数, 现值, [终值], [类型])",
        args_desc="利率：每期利率（年利率 / 12）\n"
                  "期数：要看第几期（1 到总期数）\n"
                  "总期数：一共几期\n"
                  "现值：本金\n终值 / 类型：同 PMT",
        returns="第「期数」期还款额中的**利息部分**，负数",
        description="拆出某个月的还款里有多少是利息。",
        example_formula="=-IPMT($B$2/12, ROW()-1, $C$2*12, $D$2)",
        example_result="配 ROW() 往下拉，得到每一期的利息。"
                       "**第 1 期利息最高、越往后越低**，本金部分正好相反",
        pitfalls="① 第 2 个参数是**第几期**而不是总额，"
                 "与 PMT 的参数顺序不同（PMT 第 2 是总期数），极易写混\n"
                 "② 期数超出总期数返回 #NUM!\n"
                 "③ 同样返回负数\n"
                 "④ 想看「某一年的利息合计」用 CUMIPMT，"
                 "但要先把现金流按年聚合，或直接用 SUM(IPMT(...)) 数组\n"
                 "⑤ 与 PMT 一样，利率与期数单位要一致",
        use_cases="做贷款还款计划表（本金 / 利息 / 余额三列）；"
                  "算利息抵税金额；算提前还款省了多少利息；"
                  "经营租赁的利息费用分摊",
        related="PPMT|PMT|RATE|NPER",
    ),
    F(
        code="PPMT", name_cn="某期本金", category="财务",
        tags="财务核心|做还款计划表", min_version="Excel 2003", difficulty=3,
        importance=3,
        syntax="PPMT(利率, 期数, 总期数, 现值, [终值], [类型])",
        args_desc="参数含义与 IPMT 完全一致：\n"
                  "第 2 个是「第几期」，第 3 个是「总期数」",
        returns="第「期数」期还款额中的**本金部分**，负数",
        description="拆出某个月的还款里有多少在还本金。",
        example_formula="=-PPMT($B$2/12, ROW()-1, $C$2*12, $D$2)",
        example_result="第 1 期本金只有几百、利息占大头；"
                       "到最后一期本金几乎等于整月月供 —— 这就是等额本息的特点",
        pitfalls="① 与 IPMT 一起用时，**两者之和应等于 PMT 的结果**"
                 "（符号一致的前提下），这是校验公式写对了没有的好办法\n"
                 "② 第 2 / 3 个参数依旧是「第几期 / 总期数」\n"
                 "③ 返回负数\n"
                 "④ 「剩余本金」要自己累减：`本金 - SUM($PPMT...)`，"
                 "没有内置的直接函数",
        use_cases="还款计划表的本金列；算剩余本金用于提前还款；"
                  "算每期折旧对应的本金摊销；核对月供是否正确",
        related="IPMT|PMT|NPER|PV",
    ),
    F(
        code="FV", name_cn="终值", category="财务",
        tags="财务|定投必用", min_version="Excel 2003", difficulty=3, importance=3,
        syntax="FV(利率, 期数, 每期付款, [现值], [类型])",
        args_desc="利率：每期利率\n"
                  "期数：总期数\n"
                  "每期付款：每期投入 / 收到的金额（**自己在掏钱就写负数**）\n"
                  "现值：一开始就有的一笔钱，省略为 0\n"
                  "类型：0 期末 / 1 期初",
        returns="到最后一期时的总价值，负数表示净流出",
        description="算「一直存下去最后能有多少钱」，定投 / 储蓄计划的核心。",
        example_formula="=-FV(B2/12, C2*12, D2)",
        example_result="年化 5%、每月存 3000、存 10 年 → 约 46.6 万。"
                       "**每期付款写负数**（自己掏钱），或者外面加负号让结果好看",
        pitfalls="① 现金流方向符号必须自洽："
                 "「我付出去」与「未来拿到」符号相反，弄反了结果会差一倍\n"
                 "② 利率与期数单位一致（年化 / 月付 → /12 与 *12）\n"
                 "③ 「期初投入」比「期末投入」多赚一期利息，"
                 "长期看差别不小，别漏第 5 参数\n"
                 "④ 它假设**利率恒定**；浮动利率要自己做表",
        use_cases="每月定投到期金额；教育金 / 养老金规划；"
                  "定期存款到期本息；算保险产品的现金价值",
        related="PV|PMT|RATE|NPER",
    ),
    F(
        code="PV", name_cn="现值", category="财务",
        tags="财务", min_version="Excel 2003", difficulty=3, importance=3,
        syntax="PV(利率, 期数, 每期付款, [终值], [类型])",
        args_desc="利率：每期折现率\n"
                  "期数：总期数\n"
                  "每期付款：每期收 / 付的金额\n"
                  "终值：期末想要的余额，省略为 0",
        returns="这笔未来现金流折算到今天的价值",
        description="算未来的一串钱相当于今天多少钱，是「值不值」的判断依据。",
        example_formula="=-PV(B2/12, C2*12, D2)",
        example_result="月租 5000、租 3 年、折现率 6% 年化 → "
                       "相当于今天一次性付约 16.4 万。"
                       "**「一次付清 vs 分期」用这个比**",
        pitfalls="① 与 FV 互为逆运算，参数顺序一致但含义相反，别混\n"
                 "② 折现率选多少是业务判断，不是数学问题；"
                 "用年化 / 12 还是年化，说清楚口径\n"
                 "③ 返回负数（现金流出方向）\n"
                 "④ 它假设每期金额相同；金额不等要逐期 PV 后求和，或直接用 NPV",
        use_cases="一次付清 vs 分期的对比；租赁 vs 购买的比较；"
                  "算养老金缺口；项目现金流的估值",
        related="FV|NPV|PMT|RATE",
    ),
    F(
        code="RATE", name_cn="反求利率", category="财务",
        tags="财务|迭代解", min_version="Excel 2003", difficulty=4, importance=2,
        syntax="RATE(期数, 每期付款, 现值, [终值], [类型], [猜测值])",
        args_desc="期数：总期数\n"
                  "每期付款：每期金额（**符号要与现值相反**）\n"
                  "现值：本金 / 当前投入\n"
                  "终值：期末余额\n"
                  "类型：0 / 1\n"
                  "猜测值：迭代起点，省略为 10%；**不收敛时改这个值试试**",
        returns="每期利率；无解或迭代不收敛时返回 #NUM!",
        description="已知付款额反推利率，用来算「这到底相当于年化多少」。",
        example_formula="=RATE(C2*12, -D2, E2)*12",
        example_result="知道贷了多少、每月还多少、还多久 → 反推出真实年化。"
                       "**算「某平台宣称的低利率到底是多少」最有用**",
        pitfalls="① 它是**迭代求解**，参数符号不自洽时直接 #NUM!，"
                 "这是最常见的情况：三个现金流的符号必须有一正一负\n"
                 "② 得到的是**每期**利率，要乘 12 才是年化 —— 别忘了\n"
                 "③ 不收敛时调第 6 参数（猜测值），比如给 0.01 / 0.1\n"
                 "④ 结果对「期初 / 期末」很敏感，第 5 参数要写对",
        use_cases="反推真实年化利率；算分期手续费折算的年化；"
                  "算理财实际收益率；比较两个方案的融资成本",
        related="NPER|PMT|IRR|XIRR",
    ),
    F(
        code="NPER", name_cn="反求期数", category="财务",
        tags="财务", min_version="Excel 2003", difficulty=3, importance=2,
        syntax="NPER(利率, 每期付款, 现值, [终值], [类型])",
        args_desc="利率：每期利率\n"
                  "每期付款：每期金额\n"
                  "现值：本金\n终值 / 类型：同上",
        returns="需要的期数（可能是小数）；参数不合理时返回 #NUM!",
        description="算「这样还下去要还多少期」。",
        example_formula="=NPER(B2/12, -C2, D2)",
        example_result="贷款 100 万、月供 6000、年化 4.9% → 约 228 个月（19 年）。"
                       "**每月多还一点，能少还多少期**，用它算最直观",
        pitfalls="① 得到的是**期数**，按月算的结果单位是月，除以 12 才是年\n"
                 "② 结果是小数是正常的（最后一期不满），"
                 "实际还款要向上取整：`ROUNDUP(NPER(...), 0)`\n"
                 "③ 每期付款太小（还不上利息）会返回 #NUM! 或负数\n"
                 "④ 符号要自洽",
        use_cases="算还清要多久；算「每月多还 500 少还几年」；"
                  "算攒够目标金额需要几期；债务清偿规划",
        related="PMT|RATE|FV|NPER",
    ),
    F(
        code="NPV", name_cn="净现值", category="财务",
        tags="财务|投资决策", min_version="Excel 2003", difficulty=4, importance=3,
        syntax="NPV(利率, 值1, [值2], …)",
        args_desc="利率：每期折现率（**每期**，不是年化）\n"
                  "值1…：按**时间顺序**排列的各期净现金流，最多 254 个",
        returns="未来各期现金流的现值之和（**不含第 0 期**）",
        description="把未来各期现金流折现求和，判断项目值不值得做。",
        example_formula="=A2 + NPV(B2, C3:C10)",
        example_result="**注意这个写法**：A2 是第 0 期（现在投出去的钱），"
                       "必须**加在 NPV 外面**。"
                       "结果 > 0 说明项目收益率高于 B2 的折现率",
        pitfalls="① **这是最经典的 Excel 财务坑：NPV 会把第一个值也折现一期**，"
                 "它假设所有参数都是「期末」现金流。"
                 "所以「初始投资」必须写在 NPV 外面单独加，"
                 "写成 `NPV(率, 初始投资, 各期收益)` 是**错的**\n"
                 "② 值必须按时间顺序给，中间不出现的期要写 0 占位\n"
                 "③ 现金流有正有负；全正或全负算 NPV 没意义\n"
                 "④ 利率是「每期」的：按年现金流就给年化，"
                 "按月现金流要把年化 / 12\n"
                 "⑤ 各期金额不等也能算，这是它比 PV 强的地方",
        use_cases="项目投资决策（NPV > 0 才做）；"
                  "设备买还是租；比较两个方案哪个更值；"
                  "算分期收入的现值",
        related="IRR|XIRR|PV|XNPV",
    ),
    F(
        code="IRR", name_cn="内部收益率", category="财务",
        tags="财务|投资决策", min_version="Excel 2003", difficulty=4, importance=3,
        syntax="IRR(值, [猜测值])",
        args_desc="值：按时间顺序的现金流（**必须至少一正一负**），"
                  "且**第一笔通常是初始投资**\n"
                  "猜测值：迭代起点，省略为 10%",
        returns="让 NPV 等于 0 的折现率；无解时返回 #NUM! 或错误值",
        description="算这笔投资相当于年化多少收益率，与「资金成本」比较决定做不做。",
        example_formula="=IRR(A2:A10)",
        example_result="8 年现金流的 IRR 是 12% → 高于公司要求的 10%，项目可做。"
                       "**IRR 与 NPV 通常一起看**："
                       "NPV 说「赚多少钱」，IRR 说「收益率多少」",
        pitfalls="① **必须有一正一负**，否则直接 #NUM!\n"
                 "② 第一笔通常是最初投入（负数），**顺序不能乱**，"
                 "顺序变了结果就变\n"
                 "③ **可能有多解**：现金流符号反复变动（- + - +）时会算出多个 IRR，"
                 "这时要改看 NPV 或 MIRR\n"
                 "④ 它假设所有收益能按 IRR 再投资，"
                 "高 IRR 项目这个假设偏乐观\n"
                 "⑤ 结果不收敛时改第 2 参数（猜测值）\n"
                 "⑥ 它默认**等间隔**（年 / 月）；"
                 "日期不规则的现金流用 XIRR",
        use_cases="项目收益率测算；设备投资回报；"
                  "算「这笔钱投进去几年回本」；比较多个项目的吸引力",
        related="XIRR|NPV|RATE|MIRR",
    ),
    F(
        code="XIRR", name_cn="不定期内部收益率", category="财务",
        tags="财务|实用", min_version="Excel 2007", difficulty=4, importance=2,
        syntax="XIRR(值, 日期, [猜测值])",
        args_desc="值：各次现金流金额\n"
                  "日期：**与值一一对应**的实际日期（真日期，不是文本）\n"
                  "猜测值：迭代起点",
        returns="年化内部收益率（按实际天数 365 天折算）",
        description="算日期不规则的现金流的年化收益率，金额和时间都真实的那种。",
        example_formula="=XIRR(B2:B20, C2:C20)",
        example_result="按实际的收款日期与金额算出年化收益。"
                       "**买基金、分批买入、不定期回款**这些场景只能用 XIRR",
        pitfalls="① 「值」与「日期」必须**一一对应、个数相同、且按日期升序**\n"
                 "② 日期必须是**真日期**（序列值），文本日期先 DATEVALUE\n"
                 "③ 至少一正一负，否则 #NUM!\n"
                 "④ 它给的是**年化**结果（与 IRR 的期收益率不同），"
                 "所以 XIRR 的结果通常看起来更大\n"
                 "⑤ 需要 2007 及以上",
        use_cases="基金定投实际年化；分批买入股票的真实收益；"
                  "不定期回款的项目收益；算「这笔钱实际赚了多少个点」",
        related="IRR|XNPV|NPV|RATE",
    ),
    F(
        code="SLN", name_cn="直线折旧", category="财务",
        tags="财务|会计", min_version="Excel 2003", difficulty=2, importance=2,
        syntax="SLN(原值, 残值, 年限)",
        args_desc="原值：资产入账价值\n"
                  "残值：用完后预计能卖多少\n"
                  "年限：折旧年限（单位与你要的期间一致，按年就是年数）",
        returns="**每期**折旧额（每期都相同）",
        description="直线法折旧，每期摊一样的金额。",
        example_formula="=SLN(B2, C2, D2)",
        example_result="10 万的设备、残值 1 万、用 5 年 → 每年折旧 1.8 万。"
                       "做固定资产台账时最常用的一种",
        pitfalls="① 它是**按年**口径（给了年限就按年），"
                 "想按月要写 `SLN(原值, 残值, 年限*12)`\n"
                 "② 残值不能大于原值\n"
                 "③ 它**不限制累计折旧不超过「原值-残值」**："
                 "脱离年限去用会算出不合理的值，做台账要自己控期数\n"
                 "④ 中国会计上更多用「年限平均法 + 残值率」，"
                 "公式一样但要先把残值率换成金额",
        use_cases="固定资产折旧台账；按月摊设备成本；"
                  "算某个部门分摊的设备费用",
        related="DDB|DB|SYD",
    ),
    F(
        code="DDB", name_cn="双倍余额递减折旧", category="财务",
        tags="财务|会计|加速折旧", min_version="Excel 2003", difficulty=4,
        importance=2,
        syntax="DDB(原值, 残值, 年限, 期数, [系数])",
        args_desc="原值：入账价值\n"
                  "残值：预计净残值\n"
                  "年限：折旧总年限\n"
                  "期数：要看第几期的折旧额\n"
                  "系数：递减倍率，省略为 2（即双倍余额递减）",
        returns="第「期数」期的折旧额（前期大、后期小）",
        description="加速折旧法：前期多摊、后期少摊，适合技术迭代快的设备。",
        example_formula="=DDB($B$2, $C$2, $D$2, ROW()-1)",
        example_result="配 ROW() 往下拉得到每期折旧额。"
                       "**注意最后一期：它不会自动把账面价值卡到残值**，"
                       "实务上最后两年要改成直线法",
        pitfalls="① **它不管「账面价值会不会低于残值」**，"
                 "直接拉到底可能出现折旧后净值低于残值的情况。"
                 "会计准则要求最后两年改用直线法，这一步要手工处理\n"
                 "② 「期数」是第几期而不是总期数（和 PMT 系列一样要看清楚）\n"
                 "③ 系数 2 是双倍余额递减；1.5 是 150% 递减\n"
                 "④ 老写法 ``DDB`` 与新版一致；"
                 "另外还有 DB（固定余额递减，算法不同，别混）",
        use_cases="设备加速折旧；技术类资产（电子设备）的折旧测算；"
                  "税务上的加速折旧政策测算",
        related="SLN|DB|SYD|PPMT",
    ),

    # ==================================================================
    # 数据库
    # ==================================================================
    F(
        code="DSUM", name_cn="条件求和（条件区域版）", category="数据库",
        tags="老写法|现代用SUMIFS", min_version="Excel 2003", difficulty=3,
        importance=1,
        syntax="DSUM(数据库, 字段, 条件)",
        args_desc="数据库：包含表头的整个数据区域\n"
                  "字段：要对哪一列求和。可写列标题文字（加引号）或列序号\n"
                  "条件：一块**至少两行**的区域 —— 第一行是列标题，"
                  "下面几行是条件（同一行内是「并且」，不同行之间是「或者」）",
        returns="满足条件的记录中，指定字段的合计",
        description="用「条件区域」做条件汇总的老函数，90 年代的主力。",
        example_formula='=DSUM(A1:D100, "金额", F1:G3)',
        example_result="按 F1:G3 那块条件区域（F 列是「大区」，G 列是「月份」）"
                       "汇总 A1:D100 里「金额」列",
        pitfalls="① **条件区域必须包含列标题行**，而且标题文字要和数据区完全一致，"
                 "差一个空格就查不到（返回 0，不报错）\n"
                 "② 它的「或者」是靠**多行**表达的，这一套逻辑现在看很别扭\n"
                 "③ 现代替代：``SUMIFS`` / ``FILTER`` 更直观、也不用维护条件区域。"
                 "**新表不要再用 D 系列**，认识它就够了\n"
                 "④ 条件区域里用公式条件时写法特殊（如 `=\"<>\"`），很容易踩坑",
        use_cases="维护老报表时看懂它；需要「多行或条件」的复杂筛选"
                  "（这点上它比 SUMIFS 灵活）",
        related="DAVERAGE|DCOUNT|DGET|SUMIFS",
    ),
    F(
        code="DCOUNT", name_cn="条件计数（条件区域版）", category="数据库",
        tags="老写法|现代用COUNTIFS", min_version="Excel 2003", difficulty=3,
        importance=1,
        syntax="DCOUNT(数据库, 字段, 条件)",
        args_desc="数据库：带表头的完整区域\n"
                  "字段：要计数的列；**只有该列是数字的行才被计入**\n"
                  "条件：条件区域（第一行表头 + 若干行条件）",
        returns="满足条件的记录数（只数指定字段为数字的那些行）",
        description="用条件区域计数的老函数。",
        example_formula='=DCOUNT(A1:D100, "金额", F1:G3)',
        example_result="满足条件的记录数。"
                       "因为只数「金额」列有数字的行，所以空白金额的行不计入",
        pitfalls="① 和 DSUM 一样，**条件区域的表头必须与数据区一字不差**\n"
                 "② 想「数所有行不论字段有没有值」要改用 ``DCOUNTA``\n"
                 "③ 现代替代 ``COUNTIFS``；老文件里看到它不必慌，"
                 "只是把条件区域换成成对的「区域, 条件」即可",
        use_cases="读懂老报表；需要「多行或条件」的计数",
        related="DSUM|DAVERAGE|DGET|COUNTIFS",
    ),
    F(
        code="DGET", name_cn="条件取值（唯一）", category="数据库",
        tags="老写法|能查文本", min_version="Excel 2003", difficulty=3, importance=1,
        syntax="DGET(数据库, 字段, 条件)",
        args_desc="数据库：带表头的完整区域\n"
                  "字段：要取哪一列的值\n"
                  "条件：条件区域",
        returns="**唯一**满足条件的记录在该字段的值\n"
                "没有记录 → #VALUE!；**多于一条记录 → #NUM!**",
        description="按条件取唯一一条记录的值。",
        example_formula='=DGET(A1:D100, "负责人", F1:G3)',
        example_result="条件唯一命中时取值；"
                       "命中 0 条报 #VALUE!、命中 2 条以上报 #NUM!",
        pitfalls="① **条件必须唯一命中**，这既是它的严格之处，"
                 "也是它很少被用的原因（多一条记录就报错）\n"
                 "② 它**不区分匹配方式**，也没有近似匹配选项\n"
                 "③ 现代替代就是 XLOOKUP / FILTER，既能查文本也能兜底，"
                 "**新表别再用 DGET**",
        use_cases="读懂老报表；想要「必须唯一」的强校验场景",
        related="DSUM|DCOUNT|XLOOKUP|VLOOKUP",
    ),
    F(
        code="DAVERAGE", name_cn="条件平均（条件区域版）", category="数据库",
        tags="老写法|现代用AVERAGEIFS", min_version="Excel 2003", difficulty=3,
        importance=1,
        syntax="DAVERAGE(数据库, 字段, 条件)",
        args_desc="数据库：带表头的完整区域\n"
                  "字段：要求平均值的列\n"
                  "条件：条件区域（表头 + 条件行）",
        returns="满足条件的记录在该字段的平均值；无满足项返回 #DIV/0!",
        description="用条件区域求平均的老函数。",
        example_formula='=DAVERAGE(A1:D100, "评分", F1:G3)',
        example_result="满足条件的记录的平均评分",
        pitfalls="① 表头必须一致，否则无条件匹配、返回整列平均 —— "
                 "**这种「静默算错」比报错更危险**\n"
                 "② 空值行不计入平均（与 AVERAGEIFS 口径一致）\n"
                 "③ 现代替代 ``AVERAGEIFS``，参数顺序是「平均区域」在前",
        use_cases="读懂老报表；多行「或条件」下的平均值",
        related="DSUM|DCOUNT|DGET|AVERAGEIFS",
    ),

    # ==================================================================
    # 工程
    # ==================================================================
    F(
        code="CONVERT", name_cn="单位换算", category="工程",
        tags="冷门但能用", min_version="Excel 2007", difficulty=3, importance=1,
        syntax='CONVERT(数值, 原单位, 目标单位)',
        args_desc='数值：要换算的值\n'
                  '原单位 / 目标单位：**加双引号**的单位代码\n'
                  '  重量 g / kg / lbm（磅）/ ozm（盎司）\n'
                  '  距离 m / km / mi（英里）/ ft / in / yd\n'
                  '  温度 C / F / K\n'
                  '  信息 bit / byte\n'
                  '  时间 day / hr / mn / sec',
        returns="换算后的数值；单位代码不认识时返回 #N/A",
        description="内置的单位换算，覆盖重量 / 距离 / 温度 / 速度 / 能量等。",
        example_formula="=CONVERT(A2, \"lbm\", \"kg\")",
        example_result="100 磅 → 45.36 公斤。"
                       "温度：`=CONVERT(100, \"C\", \"F\")` → 212",
        pitfalls="① **单位代码不是缩写随你写**：分钟的代码是 `mn` 不是 `m`，"
                 "写错会返回 #N/A\n"
                 "② 大小写敏感：`m`（米）与 `M`（可能被当别的）不同\n"
                 "③ **温度换算是非线性**的（带偏移），所以不能像重量那样"
                 "「换算两次回来结果一样」地推导中间单位\n"
                 "④ 中文单位（「元」「箱」）它当然不认，业务单位还得自己定汇率",
        use_cases="外贸单位换算（磅 / 公斤、英寸 / 毫米）；"
                  "温度换算；数据容量换算；时间单位换算",
        related="DEC2BIN|BIN2DEC",
    ),
    F(
        code="DEC2BIN", name_cn="十进制转二进制", category="工程",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="DEC2BIN(十进制数, [位数])",
        args_desc="十进制数：要转换的整数（**范围 -512 ~ 511**）\n"
                  "位数：补足到几位；省略则用最少位数",
        returns="二进制字符串",
        description="十进制整数转二进制字符串，做位运算 / 权限码时用得上。",
        example_formula="=DEC2BIN(10, 8)",
        example_result='"00001010"。第 2 参数给 8 是为了补齐 8 位，'
                       "做「权限位 / 状态位」的可读展示",
        pitfalls="① **范围只有 -512~511**，再大就 #NUM!。"
                 "大数字转二进制要自己写公式或换 Python\n"
                 "② 负数的结果是用两位补码表示的 10 位串，"
                 "不熟悉补码的人会看懵\n"
                 "③ 结果是**文本**，前面补的 0 要保留就必须是文本",
        use_cases="展示权限位 / 状态位；教学；"
                  "跟机器设备打交道时的寄存器值换算",
        related="BIN2DEC|CONVERT|BITAND",
    ),
    F(
        code="BIN2DEC", name_cn="二进制转十进制", category="工程",
        tags="", min_version="Excel 2003", difficulty=2, importance=1,
        syntax="BIN2DEC(二进制串)",
        args_desc="二进制串：最多 10 个字符的 0/1 字符串（可加引号）",
        returns="十进制整数",
        description="二进制字符串转十进制整数。",
        example_formula='=BIN2DEC("00001010")',
        example_result="10。"
                       "与 DEC2BIN 配合可以做位运算的读写",
        pitfalls="① **超过 10 位会 #NUM!**\n"
                 "② 含 0/1 以外的字符会 #NUM!\n"
                 "③ 首位为 1 的 10 位串会被当负数（补码），"
                 "想当无符号数得自己换算法",
        use_cases="解析设备 / 接口返回的状态位；与 DEC2BIN 互算",
        related="DEC2BIN|CONVERT",
    ),

    # ==================================================================
    # 兼容性
    # ==================================================================
    F(
        code="RANK", name_cn="排名（旧写法）", category="兼容性",
        tags="老写法|看老文件用", min_version="Excel 2003", difficulty=2,
        importance=2,
        syntax="RANK(数值, 引用, [排序方式])",
        args_desc="与 ``RANK.EQ`` 完全一致：\n"
                  "数值 / 引用 / 排序方式（0 或省略降序，1 升序）",
        returns="名次（并列时同名次、后续跳号）",
        description="RANK.EQ 的旧名字，行为一模一样。",
        example_formula="=RANK(B2, $B$2:$B$100, 0)",
        example_result="与 `=RANK.EQ(B2, $B$2:$B$100, 0)` 结果完全相同",
        pitfalls="① **它只是为了兼容老文件而保留**，"
                 "新公式应该写 ``RANK.EQ``（微软已把 RANK 归入兼容性分类）\n"
                 "② 行为与 RANK.EQ 一致，不用担心结果不同\n"
                 "③ 并列跳号的问题一样存在，中式排名要自己写 SUMPRODUCT",
        use_cases="读懂老报表；维护历史公式；"
                  "新写公式时知道该换成 RANK.EQ",
        related="RANK.EQ|RANK.AVG|SUMPRODUCT",
    ),
    F(
        code="STDEV", name_cn="标准差（旧写法）", category="兼容性",
        tags="老写法|看老文件用", min_version="Excel 2003", difficulty=3,
        importance=1,
        syntax="STDEV(数值1, [数值2], …)",
        args_desc="与 ``STDEV.S`` 完全一致（样本标准差，分母 n-1）",
        returns="样本标准差",
        description="STDEV.S 的旧名字。",
        example_formula="=STDEV(B2:B100)",
        example_result="与 `=STDEV.S(B2:B100)` 结果完全相同。"
                       "**注意它与 ``STDEVP``（总体）的区分**："
                       "旧版有两个名字，新版对应 STDEV.S 与 STDEV.P",
        pitfalls="① 旧版命名没有 `.S` / `.P` 后缀，"
                 "**STDEV 是样本、STDEVP 是总体**，多一个 P 就是总体，容易看漏\n"
                 "② 新版一律用带后缀的写法，语义一目了然\n"
                 "③ 只有一个数据点时 STDEV 会 #DIV/0!",
        use_cases="读懂老报表；把老公式迁移成 STDEV.S / STDEV.P",
        related="STDEV.S|VAR.S|AVERAGE|CORREL",
    ),
    F(
        code="PERCENTILE", name_cn="百分位（旧写法）", category="兼容性",
        tags="老写法|看老文件用", min_version="Excel 2003", difficulty=3,
        importance=1,
        syntax="PERCENTILE(数组, k)",
        args_desc="与 ``PERCENTILE.INC`` 完全一致（含端点口径）",
        returns="第 k 百分位的值",
        description="PERCENTILE.INC 的旧名字。",
        example_formula="=PERCENTILE(B2:B100, 0.9)",
        example_result="与 `=PERCENTILE.INC(B2:B100, 0.9)` 结果完全相同",
        pitfalls="① **新旧版本的差异在于「含端点 / 不含端点」**："
                 "旧 PERCENTILE ≈ 新的 .INC；.EXC 是不含端点的新口径，"
                 "两者在 k 靠近 0 或 1 时结果不同\n"
                 "② 报口径时一定要写清楚用哪个，"
                 "薪酬 / 服务水平的百分位是**有行业约定的**\n"
                 "③ k 必须在 0~1 之间",
        use_cases="读懂老报表；把老公式迁移成 PERCENTILE.INC / .EXC",
        related="PERCENTILE.INC|QUARTILE.INC|MEDIAN|LARGE",
    ),
]
