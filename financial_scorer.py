"""
可转债筛选系统 - 财务评分模块
基于8项财务指标进行加权评分
"""

import pandas as pd
from typing import Optional

from data_fetcher import parse_financial_value
from config import (
    WEIGHT_CASH_TO_CURRENT_LIAB,
    WEIGHT_DEBT_RATIO,
    WEIGHT_RECEIVABLES_TO_REVENUE,
    WEIGHT_CFO_TO_NET_PROFIT,
    WEIGHT_GROSS_MARGIN,
    WEIGHT_CONSECUTIVE_LOSS,
    WEIGHT_AUDIT_OPINION,
    WEIGHT_PLEDGE_RATIO,
    CASH_TO_CURRENT_LIAB_SAFE,
    CASH_TO_CURRENT_LIAB_WARN,
    DEBT_RATIO_SAFE,
    DEBT_RATIO_WARN,
    RECEIVABLES_TO_REVENUE_SAFE,
    RECEIVABLES_TO_REVENUE_WARN,
    CFO_TO_NET_PROFIT_SAFE,
    CFO_TO_NET_PROFIT_WARN,
    GROSS_MARGIN_SAFE,
    GROSS_MARGIN_WARN,
    CONSECUTIVE_LOSS_YEARS,
    PLEDGE_RATIO_SAFE,
    PLEDGE_RATIO_WARN,
)


INDICATORS = [
    ("货币资金/流动负债", WEIGHT_CASH_TO_CURRENT_LIAB),
    ("资产负债率", WEIGHT_DEBT_RATIO),
    ("应收账款/营收", WEIGHT_RECEIVABLES_TO_REVENUE),
    ("经营现金流/净利润", WEIGHT_CFO_TO_NET_PROFIT),
    ("毛利率", WEIGHT_GROSS_MARGIN),
    ("连续亏损", WEIGHT_CONSECUTIVE_LOSS),
    ("审计意见", WEIGHT_AUDIT_OPINION),
    ("股权质押", WEIGHT_PLEDGE_RATIO),
]


def score_financials(
    candidates: pd.DataFrame,
    financial_data: dict[str, pd.DataFrame | None],
    debt_data: dict[str, pd.DataFrame | None],
    pledge_data: pd.DataFrame | None,
) -> pd.DataFrame:
    """对候选池进行财务指标评分

    Args:
        candidates: 候选池 DataFrame (含排除项标记)
        financial_data: {stock_code: financial_abstract_df}
        debt_data: {stock_code: stock_financial_debt_ths df}
        pledge_data: 全市场质押比例 DataFrame

    Returns:
        包含评分结果的 DataFrame
    """
    print("=" * 50)
    print("Step 3: 财务指标评分")
    print("=" * 50)

    df = candidates.copy()

    for indicator_name, _ in INDICATORS:
        df[f"评分_{indicator_name}"] = None
        df[f"详情_{indicator_name}"] = ""

    stock_code_col = "正股代码" if "正股代码" in df.columns else None

    for idx, row in df.iterrows():
        stock_code = str(row.get(stock_code_col, "")).zfill(6) if stock_code_col else ""

        fin_df = financial_data.get(stock_code)
        bs_df = debt_data.get(stock_code)

        # ① 货币资金/流动负债
        _score_cash_to_current_liab(row, idx, df, bs_df)

        # ② 资产负债率
        _score_debt_ratio(row, idx, df, fin_df)

        # ③ 应收账款/营收
        _score_receivables_to_revenue(row, idx, df, bs_df, fin_df)

        # ④ 经营现金流/净利润
        _score_cfo_to_net_profit(row, idx, df, fin_df)

        # ⑤ 毛利率
        _score_gross_margin(row, idx, df, fin_df)

        # ⑥ 连续亏损
        _score_consecutive_loss(row, idx, df, fin_df)

        # ⑦ 审计意见 (默认标准无保留)
        _score_audit_opinion(row, idx, df)

        # ⑧ 股权质押
        _score_pledge_ratio(row, idx, df, stock_code, pledge_data)

    _calculate_total_score(df)
    _assign_risk_level(df)

    print("  财务评分完成\n")
    return df


def _score_cash_to_current_liab(row, idx, df, bs_df):
    if bs_df is None:
        df.at[idx, "评分_货币资金/流动负债"] = 1
        df.at[idx, "详情_货币资金/流动负债"] = "无资产负债表数据"
        return

    cash = _get_latest_value(bs_df, ["货币资金"])
    current_liab = _get_latest_value(bs_df, ["流动负债合计", "流动负债"])

    if cash is None or current_liab is None or current_liab == 0:
        df.at[idx, "评分_货币资金/流动负债"] = 1
        df.at[idx, "详情_货币资金/流动负债"] = "数据不全"
        return

    ratio = cash / current_liab
    df.at[idx, "详情_货币资金/流动负债"] = f"{ratio:.2%}"

    if ratio >= CASH_TO_CURRENT_LIAB_SAFE:
        df.at[idx, "评分_货币资金/流动负债"] = 2
    elif ratio >= CASH_TO_CURRENT_LIAB_WARN:
        df.at[idx, "评分_货币资金/流动负债"] = 1
    else:
        df.at[idx, "评分_货币资金/流动负债"] = 0


def _score_debt_ratio(row, idx, df, fin_df):
    if fin_df is None:
        df.at[idx, "评分_资产负债率"] = 1
        df.at[idx, "详情_资产负债率"] = "无财务数据"
        return

    val = _get_latest_value(fin_df, ["资产负债率"])
    if val is None:
        df.at[idx, "评分_资产负债率"] = 1
        df.at[idx, "详情_资产负债率"] = "无数据"
        return

    ratio = val / 100 if val > 1 else val
    df.at[idx, "详情_资产负债率"] = f"{ratio:.2%}"

    if ratio <= DEBT_RATIO_SAFE:
        df.at[idx, "评分_资产负债率"] = 2
    elif ratio <= DEBT_RATIO_WARN:
        df.at[idx, "评分_资产负债率"] = 1
    else:
        df.at[idx, "评分_资产负债率"] = 0


def _score_receivables_to_revenue(row, idx, df, bs_df, fin_df):
    if bs_df is None:
        df.at[idx, "评分_应收账款/营收"] = 1
        df.at[idx, "详情_应收账款/营收"] = "无资产负债表数据"
        return

    receivables = _get_latest_value(bs_df, ["应收账款", "应收票据及应收账款"])

    revenue = None
    if fin_df is not None:
        revenue = _get_latest_value(fin_df, ["营业总收入"])
    if revenue is None:
        revenue = _get_latest_value(bs_df, ["营业总收入", "营业收入"])

    if receivables is None or revenue is None or revenue == 0:
        df.at[idx, "评分_应收账款/营收"] = 1
        df.at[idx, "详情_应收账款/营收"] = "数据不全"
        return

    ratio = receivables / revenue
    df.at[idx, "详情_应收账款/营收"] = f"{ratio:.2%}"

    if ratio <= RECEIVABLES_TO_REVENUE_SAFE:
        df.at[idx, "评分_应收账款/营收"] = 2
    elif ratio <= RECEIVABLES_TO_REVENUE_WARN:
        df.at[idx, "评分_应收账款/营收"] = 1
    else:
        df.at[idx, "评分_应收账款/营收"] = 0


def _score_cfo_to_net_profit(row, idx, df, fin_df):
    if fin_df is None:
        df.at[idx, "评分_经营现金流/净利润"] = 1
        df.at[idx, "详情_经营现金流/净利润"] = "无财务数据"
        return

    cfo_per_share = _get_latest_value(fin_df, ["每股经营现金流"])
    eps = _get_latest_value(fin_df, ["基本每股收益", "每股收益"])

    if cfo_per_share is None or eps is None or eps == 0:
        df.at[idx, "评分_经营现金流/净利润"] = 1
        df.at[idx, "详情_经营现金流/净利润"] = "数据不全"
        return

    ratio = cfo_per_share / eps
    df.at[idx, "详情_经营现金流/净利润"] = f"{ratio:.2f}"

    if ratio >= CFO_TO_NET_PROFIT_SAFE:
        df.at[idx, "评分_经营现金流/净利润"] = 2
    elif ratio >= CFO_TO_NET_PROFIT_WARN:
        df.at[idx, "评分_经营现金流/净利润"] = 1
    else:
        df.at[idx, "评分_经营现金流/净利润"] = 0


def _score_gross_margin(row, idx, df, fin_df):
    if fin_df is None:
        df.at[idx, "评分_毛利率"] = 1
        df.at[idx, "详情_毛利率"] = "无财务数据"
        return

    val = _get_latest_value(fin_df, ["销售毛利率", "毛利率"])
    if val is None:
        df.at[idx, "评分_毛利率"] = 1
        df.at[idx, "详情_毛利率"] = "无数据"
        return

    ratio = val / 100 if val > 1 else val
    df.at[idx, "详情_毛利率"] = f"{ratio:.2%}"

    if ratio >= GROSS_MARGIN_SAFE:
        df.at[idx, "评分_毛利率"] = 2
    elif ratio >= GROSS_MARGIN_WARN:
        df.at[idx, "评分_毛利率"] = 1
    else:
        df.at[idx, "评分_毛利率"] = 0


def _score_consecutive_loss(row, idx, df, fin_df):
    if fin_df is None:
        df.at[idx, "评分_连续亏损"] = 1
        df.at[idx, "详情_连续亏损"] = "无财务数据"
        return

    net_profit_col = _find_col(fin_df, ["净利润"])
    report_col = _find_col(fin_df, ["报告期"])

    if net_profit_col is None:
        df.at[idx, "评分_连续亏损"] = 1
        df.at[idx, "详情_连续亏损"] = "无净利润字段"
        return

    fin_copy = fin_df.copy()
    fin_copy[net_profit_col] = fin_copy[net_profit_col].apply(parse_financial_value)

    if report_col and report_col in fin_copy.columns:
        fin_copy = fin_copy.sort_values(by=report_col, ascending=False)

    recent = fin_copy.head(CONSECUTIVE_LOSS_YEARS)
    profits = recent[net_profit_col].dropna().tolist()

    loss_count = sum(1 for p in profits if p < 0)
    df.at[idx, "详情_连续亏损"] = f"近{len(profits)}期亏损{loss_count}期"

    if loss_count == 0:
        df.at[idx, "评分_连续亏损"] = 2
    elif loss_count < CONSECUTIVE_LOSS_YEARS:
        df.at[idx, "评分_连续亏损"] = 1
    else:
        df.at[idx, "评分_连续亏损"] = 0


def _score_audit_opinion(row, idx, df):
    df.at[idx, "评分_审计意见"] = 2
    df.at[idx, "详情_审计意见"] = "默认标准无保留（需人工核查）"


def _score_pledge_ratio(row, idx, df, stock_code, pledge_data):
    if pledge_data is None or stock_code is None:
        df.at[idx, "评分_股权质押"] = 1
        df.at[idx, "详情_股权质押"] = "无质押数据"
        return

    code_col = _find_col(pledge_data, ["股票代码", "代码"])
    ratio_col = _find_col(pledge_data, ["质押比例", "无限售股质押比例"])

    if code_col is None or ratio_col is None:
        df.at[idx, "评分_股权质押"] = 1
        df.at[idx, "详情_股权质押"] = "无质押数据列"
        return

    match = pledge_data[pledge_data[code_col].astype(str).str.strip() == stock_code]
    if match.empty:
        df.at[idx, "评分_股权质押"] = 1
        df.at[idx, "详情_股权质押"] = "未匹配到质押数据"
        return

    ratio = pd.to_numeric(match.iloc[0][ratio_col], errors="coerce") / 100
    df.at[idx, "详情_股权质押"] = f"{ratio:.2%}"

    if ratio <= PLEDGE_RATIO_SAFE:
        df.at[idx, "评分_股权质押"] = 2
    elif ratio <= PLEDGE_RATIO_WARN:
        df.at[idx, "评分_股权质押"] = 1
    else:
        df.at[idx, "评分_股权质押"] = 0


def _calculate_total_score(df):
    total_weight = sum(w for _, w in INDICATORS)
    df["财务总分"] = 0.0

    for indicator_name, weight in INDICATORS:
        col = f"评分_{indicator_name}"
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(1)
        df["财务总分"] += df[col] * weight

    df["财务总分"] = (df["财务总分"] / (2 * total_weight)) * 100
    df["财务总分"] = df["财务总分"].round(1)


def _assign_risk_level(df):
    from config import RISK_LEVELS

    df["风险等级"] = ""
    df["风险建议"] = ""

    for idx, row in df.iterrows():
        excluded = row.get("排除项计数", 0)
        if excluded >= 2:
            df.at[idx, "风险等级"] = "[排除]"
            df.at[idx, "风险建议"] = "触犯>=2条排除项，直接跳过"
            continue

        score = row.get("财务总分", 0)

        level_found = False
        for low, high, level, advice in RISK_LEVELS:
            if low <= score < high:
                df.at[idx, "风险等级"] = level
                df.at[idx, "风险建议"] = advice
                level_found = True
                break

        if not level_found:
            if score >= 100:
                df.at[idx, "风险等级"] = "[安全]"
                df.at[idx, "风险建议"] = "可关注"
            else:
                df.at[idx, "风险等级"] = "[回避]"
                df.at[idx, "风险建议"] = "建议不碰"


def _get_latest_value(df, candidates):
    """获取 DataFrame 中最新一期的数值

    处理百分比字符串 (如 '16.56%')、中文数字 (如 '598.46万')
    """
    col = _find_col(df, candidates)
    if col is None:
        return None

    report_col = _find_col(df, ["报告期"])
    if report_col and report_col in df.columns:
        sorted_df = df.sort_values(by=report_col, ascending=False)
    else:
        sorted_df = df

    val = sorted_df.iloc[0][col]
    if pd.isna(val):
        return None

    return parse_financial_value(val)


def _find_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    for col in candidates:
        for df_col in df.columns:
            if col in df_col:
                return df_col
    return None
