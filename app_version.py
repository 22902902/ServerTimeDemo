"""版本号与更新日志的单一数据源。

以前版本号是 main.py 里一行硬编码字符串（``APP_TITLE = "个人系统 v1.4.0"``），
从建立版本控制起就没再改过 —— 于是不管重打包多少次，界面上的版本号都一模一样，
用户根本没法判断自己手上跑的是不是新版（"我看界面没变，是没有重新打包吗？"
就是这么来的）。

现在统一收口到这里：

- ``APP_TITLE`` 由 main.py 导入，顶栏、窗口标题、所有弹窗都显示同一串，
  改了版本号，界面上立刻看得见
- ``VERSION_HISTORY`` 是更新日志的唯一数据源；
  ``scripts/gen_changelog.py`` 据此生成仓库根目录的 ``CHANGELOG.md``，
  ``scripts/test_release_meta.py`` 盯着两者不许漂移
- 顶栏的「更新日志」按钮也读这里，不用去翻仓库文件

版本号规则：``主版本.次版本.修订号`` —— 加功能进次版本，只修 bug 进修订号。
"""

APP_NAME = "个人系统"
APP_VERSION = "1.5.0"
APP_RELEASE_DATE = "2026-09-21"

# 界面各处显示的应用名（顶栏、窗口标题、弹窗标题）
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"


VERSION_HISTORY = [
    {
        "version": "1.5.0",
        "date": "2026-09-21",
        "title": "系统工具箱：分类可拖拽、标签检索、全局搜索",
        "changes": [
            "新增 **拖拽改分类**：按住工具图标拖到分类胶囊上松手即改归属 —— "
            "只改数据库里的分类字段，**物理文件一动不动**",
            "拖拽反馈：半透明影子卡片跟随鼠标；指针底下的分类变深色高亮"
            "（「松手就落这儿」）；拖拽期间自动把空分类也摆出来当投放目标，"
            "松手后再收起（空分类平时不进分类栏，否则满屏噪音）",
            "新增 **「+ 新建分类」入口**（摆在分类栏末尾，不用再去设置对话框里建）；"
            "右键菜单加「移动到分类 ▸」与「新建分类…」（新建时顺手把工具移进去）",
            "修复 **扫描覆盖手工分类**：只有仍是「未分类」的工具才按所在目录名兜底，"
            "拖拽改过的分类不会被下一次扫描冲掉",
            "新增 **标签**：一个工具可填多个标签，竖线 | / 逗号 , / 顿号 、 / "
            "分号 ；/ 空格 都能当分隔符（全角也认，C/C++、C# 这类含斜杠、井号的标签不误切）；"
            "编辑面板下方实时显示「已识别 N 个」",
            "新增 **标签横条**：顶部自动列出全库最常用标签（跨包统计），点一下即搜",
            "新增 **全局搜索**：搜索框有内容时忽略分类栏与工具包过滤，"
            "状态条注明「（全局）」—— 标签天生是跨分类、跨包的检索词，"
            "被当前分类挡住就等于搜不到",
            "描述输入框改成卡片式（白底 + 1px 极浅描边 + 占位提示），"
            "不再是原来那个灰底凹陷的裸文本框",
            "修复 **拖放高亮完全没反应**：旧实现拿 ttk 的样式名去配 tk.Label，"
            "抛出的 TclError 被静默吞掉，等于零反馈",
            "数据层：``tool_items`` 新增 ``tags`` 列，老库启动时自动迁移，无需重装",
        ],
    },
    {
        "version": "1.4.0",
        "date": "2026-09-20",
        "title": "界面风格定稿 · 账号中心 · 笔记区 Markdown · 工具箱四种排列",
        "changes": [
            "界面风格定稿：Typora 式克制感 + 纯灰阶，自绘分组侧栏（不是 Treeview）、"
            "统一 24px gutter、去掉共享层的硬描边",
            "账号中心：工具栏收进下拉、修好被「饿死」的控件（同容器里 expand 控件"
            "会把后面的固定尺寸控件压成 0 像素并被 Tk 直接不映射）",
            "笔记区：两处预览统一走 ``markdown_view`` 真渲染（此前页面预览贴的是源码）、"
            "编辑区加 Markdown 格式工具栏（样式▾/标题 1-6、加粗、斜体、删除线、代码块、"
            "引用、列表、编号、分隔线、链接、图片）+ 语法速查弹窗，排版对齐 Typora",
            "工具箱：四种排列（图标 / 文件夹 / 卡片 / 列表）、修复 exe 图标提取、"
            "常态胶囊的圆角真正画得出来",
            "日志基建：``log_setup`` 统一配置 root logger 并挂文件 handler"
            "（打包后 ``console=False``，无控制台时日志会全丢）",
            "清理：删除未使用导入（pyflakes 64 → 7）、补全依赖清单、修掉 4 个"
            "「点了就崩」的真 Bug",
        ],
    },
]


def latest() -> dict:
    """最新一版（``VERSION_HISTORY`` 首条）。"""
    return VERSION_HISTORY[0]


def changelog_markdown() -> str:
    """把 ``VERSION_HISTORY`` 渲染成 Markdown。

    生成 ``CHANGELOG.md`` 的脚本与顶栏「更新日志」弹窗都调这里，
    避免出现两份各自维护、慢慢就对不上的日志。
    """
    lines = [f"# 更新日志 · {APP_NAME}", ""]
    lines.append(f"当前版本 **v{APP_VERSION}**（{APP_RELEASE_DATE}）")
    lines.append("")
    for entry in VERSION_HISTORY:
        lines.append(f"## v{entry['version']} — {entry['date']}")
        lines.append("")
        lines.append(f"**{entry['title']}**")
        lines.append("")
        for change in entry["changes"]:
            lines.append(f"- {change}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def changelog_header() -> str:
    """``CHANGELOG.md`` 顶部的「自动生成，别手改」说明。"""

    return (
        "<!-- 本文件由 scripts/gen_changelog.py 从 app_version.py 生成，不要手工编辑。\n"
        "     要改内容请改 app_version.py 的 VERSION_HISTORY，然后重跑：\n"
        "     python scripts/gen_changelog.py\n"
        "     （scripts/test_release_meta.py 会检查两者是否同步） -->\n"
    )
