# -*- coding: utf-8 -*-
"""
接口服务 - interfaces.json 内嵌版本
无需外部文件，PyInstaller打包后仍可正常工作
"""

import json
import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _get_default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "interfaces.json"


def _load_interface_config_from_json(file_path: Path | None) -> dict | None:
    if not file_path:
        return None
    try:
        if not file_path.exists():
            return None
        data = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("login_interface") and data.get("environments"):
            return data
    except Exception:
        return None
    return None

# 内嵌接口配置字典
_INTERFACE_CONFIG = {
    "environments": {
        "test": {
            "label": "测试环境",
            "endpoint": "http://auctioncs.example.com:6070//culture-frontend-trade/webHttpServlet"
        },
        "prod": {
            "label": "正式环境",
            "endpoint": "http://api.example.com:2130//culture-frontend-trade/webHttpServlet"
        }
    },
    "login_interface": {
        "display_name": "账号密码登录",
        "name": "logon",
        "method": "POST",
        "request_mode": "json",
        "description": "登录接口，密码字段 P 需要先做 DES/CBC/PKCS7/Base64 加密。",
        "fields": [
            {"name": "name", "label": "接口名", "description": "固定为登录接口标识。", "widget": "entry", "readonly": True, "default": "logon"},
            {"name": "U", "label": "登录账号", "description": "登录用户 ID，默认带入当前登录账号。", "widget": "entry", "default": "{{account}}"},
            {"name": "P", "label": "密码密文", "description": "按 DES/CBC/PKCS7/Base64 生成的密码密文，默认自动带入。", "widget": "entry", "readonly": True, "default": "{{encrypted_password}}"},
            {"name": "LT", "label": "登录类型", "description": "pc 表示 PC 客户端，web 表示网页客户端。", "widget": "select", "default": "{{lt}}", "options": [{"label": "web", "value": "web"}, {"label": "pc", "value": "pc"}]}
        ],
        "params": {"name": "logon", "U": "{{account}}", "P": "{{encrypted_password}}", "LT": "{{lt}}"}
    },
    "shared_interfaces": [
        {
            "display_name": "仓单出库申请查询",
            "name": "out_bill_apply_query",
            "method": "POST",
            "request_mode": "json",
            "no_login": True,
            "endpoint_suffix": "/bill-frontend/webHttpServlet",
            "date_range": {"start": "SD", "end": "ED", "max_months": 3},
            "description": "仓单出库申请查询接口，不依赖登录态，供货会员与经济会员列表中都显示。请求地址为当前环境 IP:端口 + /bill-frontend/webHttpServlet。开始日期与结束日期区间不能超过 3 个月。",
            "response_description": [
                "仓单出库申请查询返回包说明：",
                "{",
                '  "name": "out_bill_apply_query",',
                '  "RESULT": {',
                '    "RETCODE": "返回码，>=0 成功，其他为失败，错误描述在 MESSAGE 中",',
                '    "ARGS": "返回提示信息中的参数列表，使用 | 分割参数",',
                '    "TC": "总记录数"',
                "  },",
                '  "RESULTLIST": {',
                '    "REC": [{',
                '      "OAI": "出库编号",',
                '      "BII": "仓单号",',
                '      "UI": "用户代码",',
                '      "UNA": "用户名称",',
                '      "OVI": "仓单原始凭证号",',
                '      "BRI": "品种代码",',
                '      "BRN": "品种名称",',
                '      "WHI": "仓库编号",',
                '      "WHN": "仓库名称",',
                '      "CQ": "商品数量",',
                '      "UN": "商品单位",',
                '      "DT": "出库方式，0 自提，1 配送",',
                '      "BS": "出库状态，0 出库申请，1 已设置配送费用，2 已确定配送费用，3 出库完成，4 撤销",',
                '      "DF": "配送费",',
                '      "CT": "创建时间",',
                '      "PT": "处理时间",',
                '      "EC": "配送公司",',
                '      "EN": "配送单号",',
                '      "DP": "收货人姓名",',
                '      "TEL": "收货人手机号",',
                '      "DA": "收货地址"',
                "    }]",
                "  }",
                "}"
            ],
            "fields": [
                {"name": "name", "label": "接口名", "description": "固定为仓单出库申请查询接口标识。", "widget": "entry", "readonly": True, "default": "out_bill_apply_query"},
                {"name": "WMI", "label": "仓库管理员ID", "description": "仓库管理员登录账号。", "widget": "entry", "default": ""},
                {"name": "WMP", "label": "仓库管理员密码", "description": "仓库管理员密码，按接口要求原样提交。", "widget": "entry", "default": ""},
                {"name": "SD", "label": "开始日期", "description": "日期格式为 YYYY-MM-DD，且与结束日期区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                {"name": "ED", "label": "结束日期", "description": "日期格式为 YYYY-MM-DD，不能早于开始日期，且区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                {"name": "UI", "label": "用户代码 UI", "description": "可为空。", "widget": "entry", "default": ""},
                {"name": "BI", "label": "品种ID BI", "description": "可为空。", "widget": "entry", "default": ""}
            ],
            "params": {"name": "out_bill_apply_query", "WMI": "", "WMP": "", "SD": "", "ED": "", "UI": "", "BI": ""}
        }
    ],
    "post_login_interfaces": {
        "supplier": [
            {
                "display_name": "登录接口示例",
                "name": "logon",
                "method": "POST",
                "request_mode": "json",
                "description": "当前仅预置登录接口示例，后续供货会员接口可继续按该格式补充。",
                "response_description": [
                    "登录返回包说明：",
                    "{",
                    '  "name": "logon",',
                    '  "RESULT": {',
                    '    "RETCODE": "返回码，>=0 成功，其他为失败，错误描述在 MESSAGE 中",',
                    '    "ARGS": "返回提示信息中的参数列表，使用 | 分割参数",',
                    '    "SYI": "当前登录系统编号",',
                    '    "JSI": "有权限的系统编号，多个用英文分号分隔，例如 201;301",',
                    '    "FUT": "资金账户类型，0 主账户，1 附属账户",',
                    '    "LT": "上次登录时间",',
                    '    "LI": "上次登录 IP",',
                    '    "CP": "是否需要修改密码，1 是，2 否",',
                    '    "CFP": "是否需要修改资金密码，1 是，2 否",',
                    '    "RST": "实名状态，0 未实名，1 审核中，2 已实名",',
                    '    "I": "用户身份，0 客户，1 会员",',
                    '    "N": "登录用户名称",',
                    '    "NN": "昵称",',
                    '    "ISNN": "是否设置过昵称，1 已设置，2 未设置",',
                    '    "U": "登录用户ID",',
                    '    "UT": "交易员类型，1 超级交易员，2 高级交易员，3 普通交易员",',
                    '    "RK": "随机串",',
                    '    "UPL": "用户头像图片地址",',
                    '    "TR": "服务端登录过程中每个操作的耗时信息"',
                    "  }",
                    "}"
                ],
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为登录接口标识。", "widget": "entry", "readonly": True, "default": "logon"},
                    {"name": "U", "label": "登录账号", "description": "默认带入当前账号，可按需修改。", "widget": "entry", "default": "{{account}}"},
                    {"name": "P", "label": "密码密文", "description": "默认带入当前登录密码加密结果。", "widget": "entry", "readonly": True, "default": "{{encrypted_password}}"},
                    {"name": "LT", "label": "登录类型", "description": "可选 web 或 pc。", "widget": "select", "default": "{{lt}}", "options": [{"label": "web", "value": "web"}, {"label": "pc", "value": "pc"}]}
                ],
                "params": {"name": "logon", "U": "{{account}}", "P": "{{encrypted_password}}", "LT": "{{lt}}"}
            },
            {
                "display_name": "成交查询",
                "name": "broker_trade_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员成交查询。U 取登录成功返回的 U，SI 取登录成功返回的 RETCODE。RECCNT 大于 0 向上查最新成交，小于 0 向下查历史成交。",
                "response_description": [
                    "供货会员下成交查询返回包说明：",
                    "{",
                    '  "name": "broker_trade_query",',
                    '  "RESULT": {',
                    '    "RETCODE": "返回码 >=0 成功，其他为失败，错误描述在 MESSAGE",',
                    '    "ARGS": "返回提示信息中的参数列表，使用 | 分割参数",',
                    '    "TC": "总记录数",',
                    '    "MAXID": "最大号ID",',
                    '    "MINID": "最小号ID"',
                    "  },",
                    '  "RESULTLIST": {',
                    '    "REC": [{',
                    '      "TN": "成交号",',
                    '      "ON": "挂摘单号",',
                    '      "TI": "成交时间",',
                    '      "BS": "买卖方向，1买，2卖",',
                    '      "COI": "商品统一代码",',
                    '      "CON": "商品名称",',
                    '      "TP": "成交价格",',
                    '      "TQ": "成交数量",',
                    '      "TPM": "成交金额",',
                    '      "OP": "存货价",',
                    '      "CPL": "卖出盈亏(利润)",',
                    '      "CAT": "卖出增值税",',
                    '      "TF": "交易手续费",',
                    '      "ACF": "加收手续费",',
                    '      "WF": "仓储费",',
                    '      "IF": "保险费",',
                    '      "TRF": "托管费",',
                    '      "TT": "成交类型，1 正常交易，2 强平交易，3 协议交易，4 委托交易",',
                    '      "PR": "用户代码",',
                    '      "PNM": "用户名称",',
                    '      "PT": "用户类型，0 客户，1 会员",',
                    '      "OT": "操作类型，0 返回所有，1 返回挂单成交，2 返回摘单成交",',
                    '      "PON": "对方委托单号"',
                    "    }]",
                    "  }",
                    "}"
                ],
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为成交查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_trade_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。RECCNT 大于 0 查最新记录时，下一次 LTI 建议填上次返回的 MAXID；RECCNT 小于 0 查历史记录时，下一次 LTI 建议填上次返回的 MINID。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，成交号 > LTI；小于 0 表示查询之前记录，成交号 < LTI。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_trade_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "成交查询(历史)",
                "name": "broker_trade_history_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员成交历史查询。U 取登录成功返回的 U，SI 取登录成功返回的 RETCODE。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为成交历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_trade_history_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_trade_history_query", "U": "{{login_user_u}}", "SDT": "", "EDT": "", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "商品挂单记录查询",
                "name": "broker_order_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员商品挂单记录查询。U 取登录成功返回的 U，SI 取登录成功返回的 RETCODE。RECCNT 大于 0 向上查最新记录，小于 0 向下查之前记录。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为商品挂单记录查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_order_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"}
                ],
                "params": {"name": "broker_order_query", "U": "{{login_user_u}}", "SI": "{{login_retcode}}", "LTI": "0", "RECCNT": "20"}
            },
            {
                "display_name": "商品挂单记录查询(历史)",
                "name": "broker_order_history_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员商品挂单记录历史查询。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为商品挂单记录历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_order_history_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"}
                ],
                "params": {"name": "broker_order_history_query", "U": "{{login_user_u}}", "SI": "{{login_retcode}}", "LTI": "0", "RECCNT": "20", "SDT": "", "EDT": ""}
            },
            {
                "display_name": "持仓汇总查询",
                "name": "broker_hold_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员持仓汇总查询，一次返回全部持仓数据。U 取登录成功返回的 U，SI 取登录成功返回的 RETCODE。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为持仓汇总查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_hold_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_hold_query", "U": "{{login_user_u}}", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "提货申请查询",
                "name": "broker_delivery_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员提货申请查询。RECCNT 大于 0 向上查最新记录，小于 0 向下查之前记录。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为提货申请查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_delivery_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_delivery_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "提货申请查询(历史)",
                "name": "broker_delivery_history_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员提货申请历史查询。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为提货申请历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_delivery_history_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_delivery_history_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SDT": "", "EDT": "", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "过户申请查询",
                "name": "broker_transfer_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员过户申请查询。RECCNT 大于 0 向上查最新记录，小于 0 向下查之前记录。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为过户申请查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_transfer_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_transfer_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "过户申请查询(历史)",
                "name": "broker_transfer_history_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员过户申请历史查询。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为过户申请历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_transfer_history_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_transfer_history_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SDT": "", "EDT": "", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "协议交易查询",
                "name": "broker_block_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员协议交易查询。RECCNT 大于 0 向上查最新记录，小于 0 向下查之前记录。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为协议交易查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_block_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_block_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "协议交易查询(历史)",
                "name": "broker_block_history_query",
                "method": "POST",
                "request_mode": "json",
                "description": "供货会员协议交易历史查询。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为协议交易历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_block_history_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_block_history_query", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SDT": "", "EDT": "", "SI": "{{login_retcode}}"}
            }
        ],
        "broker": [
            {
                "display_name": "登录接口示例",
                "name": "logon",
                "method": "POST",
                "request_mode": "json",
                "description": "当前仅预置登录接口示例，后续经济会员接口可继续按该格式补充。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为登录接口标识。", "widget": "entry", "readonly": True, "default": "logon"},
                    {"name": "U", "label": "登录账号", "description": "默认带入当前账号，可按需修改。", "widget": "entry", "default": "{{account}}"},
                    {"name": "P", "label": "密码密文", "description": "默认带入当前登录密码加密结果。", "widget": "entry", "readonly": True, "default": "{{encrypted_password}}"},
                    {"name": "LT", "label": "登录类型", "description": "可选 web 或 pc。", "widget": "select", "default": "{{lt}}", "options": [{"label": "web", "value": "web"}, {"label": "pc", "value": "pc"}]}
                ],
                "params": {"name": "logon", "U": "{{account}}", "P": "{{encrypted_password}}", "LT": "{{lt}}"}
            },
            {
                "display_name": "出入金流水查询",
                "name": "broker_cash_flow",
                "method": "POST",
                "request_mode": "json",
                "description": "经纪会员出入金流水查询。RECCNT 大于 0 向上查最新记录，小于 0 向下查之前记录。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为出入金流水查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_cash_flow"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_cash_flow", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "出入金流水查询(历史)",
                "name": "broker_cash_history_flow",
                "method": "POST",
                "request_mode": "json",
                "description": "经纪会员出入金流水历史查询。开始时间与结束时间不能为空，且区间不能超过 3 个月。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为出入金流水历史查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_cash_history_flow"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "LTI", "label": "基准号ID", "description": "第一次填写 0。", "widget": "entry", "default": "0"},
                    {"name": "RECCNT", "label": "记录条数", "description": "大于 0 表示查询最新记录，小于 0 表示查询之前记录。", "widget": "entry", "default": "20"},
                    {"name": "SDT", "label": "开始时间", "description": "日期格式为 2020-12-12，且与结束时间区间不能超过 3 个月。", "widget": "date", "default": "{{today}}"},
                    {"name": "EDT", "label": "结束时间", "description": "日期格式为 2020-12-12，且不能早于开始时间。", "widget": "date", "default": "{{yesterday}}"},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_cash_history_flow", "U": "{{login_user_u}}", "LTI": "0", "RECCNT": "20", "SDT": "", "EDT": "", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "客户列表",
                "name": "broker_user_query",
                "method": "POST",
                "request_mode": "json",
                "description": "经纪会员客户列表查询。BT 第一次传 0，后续可使用上次返回的 MAXBT 做增量查询；UD、UMN、MNO 为可选查询条件。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为客户列表查询接口标识。", "widget": "entry", "readonly": True, "default": "broker_user_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "BT", "label": "基准时间 BT", "description": "第一次传 0。后续增量查询时，建议填入上次返回的 MAXBT。", "widget": "entry", "default": "0"},
                    {"name": "UD", "label": "用户代码", "description": "查询条件，可不传。", "widget": "entry", "default": ""},
                    {"name": "UMN", "label": "姓名", "description": "查询条件，可不传。", "widget": "entry", "default": ""},
                    {"name": "MNO", "label": "手机号", "description": "查询条件，可不传。", "widget": "entry", "default": ""},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_user_query", "U": "{{login_user_u}}", "BT": "0", "UD": "", "UMN": "", "MNO": "", "SI": "{{login_retcode}}"}
            },
            {
                "display_name": "客户资金信息列表",
                "name": "broker_user_funds_query",
                "method": "POST",
                "request_mode": "json",
                "description": "经纪会员客户资金信息列表。BR 为用户代码查询条件，可不传。",
                "fields": [
                    {"name": "name", "label": "接口名", "description": "固定为客户资金信息列表接口标识。", "widget": "entry", "readonly": True, "default": "broker_user_funds_query"},
                    {"name": "U", "label": "会员代码 U", "description": "登录成功后返回的 U，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_user_u}}"},
                    {"name": "BR", "label": "用户代码 BR", "description": "查询条件，可不传。", "widget": "entry", "default": ""},
                    {"name": "SI", "label": "会话标识 SI", "description": "登录成功返回的 RETCODE，后续接口统一取这个值。", "widget": "entry", "readonly": True, "default": "{{login_retcode}}"}
                ],
                "params": {"name": "broker_user_funds_query", "U": "{{login_user_u}}", "BR": "", "SI": "{{login_retcode}}"}
            }
        ]
    }
}


class InterfaceService:
    """接口服务类 - 优先读取 JSON，失败时回退到内嵌默认配置"""

    def __init__(self, file_path=None):
        """
        初始化接口服务
        1. 优先读取显式传入或默认位置的 interfaces.json
        2. 如果文件不存在或格式无效，则回退到内嵌默认配置
        """
        candidate_path = Path(file_path) if file_path else _get_default_config_path()
        self.config_path = candidate_path
        self.config = _load_interface_config_from_json(candidate_path) or deepcopy(_INTERFACE_CONFIG)

    def get_default_environment_key(self) -> str:
        environments = self.config.get("environments", {})
        if "test" in environments:
            return "test"
        return next(iter(environments.keys()), "")

    def get_environments(self) -> dict:
        return deepcopy(self.config.get("environments", {}))

    def get_environment(self, environment_key: str) -> dict:
        environments = self.config.get("environments", {})
        if environment_key in environments:
            return deepcopy(environments[environment_key])
        default_key = self.get_default_environment_key()
        return deepcopy(environments.get(default_key, {}))

    def get_endpoint(self, environment_key: str = None) -> str:
        if environment_key:
            return self.get_environment(environment_key).get("endpoint", "")
        default_key = self.get_default_environment_key()
        return self.get_environment(default_key).get("endpoint", "")

    def get_login_interface(self) -> dict:
        return deepcopy(self.config["login_interface"])

    def get_member_interfaces(self, member_type: str) -> list[dict]:
        interfaces = self.config.get("post_login_interfaces", {}).get(member_type, [])
        shared_interfaces = self.config.get("shared_interfaces", [])
        return deepcopy(list(interfaces) + list(shared_interfaces))

    def resolve_interface_endpoint(self, interface: dict, environment_key: str = None) -> str:
        explicit_endpoint = str(interface.get("endpoint", "")).strip()
        if explicit_endpoint:
            return explicit_endpoint

        base_endpoint = self.get_endpoint(environment_key)
        endpoint_suffix = str(interface.get("endpoint_suffix", "")).strip()
        if not endpoint_suffix:
            return base_endpoint

        if not endpoint_suffix.startswith("/"):
            endpoint_suffix = f"/{endpoint_suffix}"

        parsed = urlsplit(base_endpoint)
        if not parsed.scheme or not parsed.netloc:
            return base_endpoint
        return urlunsplit((parsed.scheme, parsed.netloc, endpoint_suffix, "", ""))

    def apply_context(self, data, context: dict):
        if isinstance(data, dict):
            return {key: self.apply_context(value, context) for key, value in data.items()}
        if isinstance(data, list):
            return [self.apply_context(item, context) for item in data]
        if isinstance(data, str):
            return PLACEHOLDER_RE.sub(lambda match: str(context.get(match.group(1), match.group(0))), data)
        return data
