"""
可转债筛选系统 - 排除项检查模块
实现5条硬性排除标准的检查
"""

import pandas as pd
from typing import Optional

from data_fetcher import parse_financial_value
from config import (
    STOCK_PRICE_MIN,
    CONSECUTIVE_LOSS_YEARS,
    NEAR_EXPIRY_YEARS,
    PREMIUM_HIGH,
    RATING_EXCLUDE_BELOW,
)


def check_exclusions(
    candidates: pd.DataFrame,
    financial_data: dict[str, Optional[pd.DataFrame]],
) -> pd.DataFrame:
    """对候选池执行5条排除项检查

    Args:
        candidates: 粗筛后的候选池 DataFrame
        financial_data: {stock_code: financial_abstract_df} 财务摘要数据字典

    Returns:
        带有排除标记的 DataFrame
    """
    print("=" * 50)
    print("Step 2: 排除项检查")
    print("=" * 50)

    df = candidates.copy()

    df["排除_正股价格"] = False
    df["排除_连续亏损"] = False
    df["排除_临近到期高溢价"] = False
    df["排除_拒绝下修"] = False
    df["排除_评级不足"] = False

    df["排除_正股价格_详情"] = ""
    df["排除_连续亏损_详情"] = ""
    df["排除_临近到期高溢价_详情"] = ""
    df["排除_拒绝下修_详情"] = ""
    df["排除_评级不足_详情"] = ""

    stock_price_col = "正股价" if "正股价" in df.columns else None
    premium_col = "溢价率" if "溢价率" in df.columns else None
    expiry_col = "剩余年限" if "剩余年限" in df.columns else None
    rating_col = "评级" if "评级" in df.columns else None
    stock_code_col = "正股代码" if "正股代码" in df.columns else None

    for idx, row in df.iterrows():
        stock_code = str(row.get(stock_code_col, "")).zfill(6) if stock_code_col else ""

        # ① 正股价格 < 5元
        _check_stock_price(row, idx, df, stock_price_col)

        # ② 连续2年亏损
        _check_consecutive_loss(row, idx, df, stock_code, financial_data)

        # ③ 剩余期限 < 6个月 且 溢价率 > 20%
        _check_near_expiry_premium(row, idx, df, expiry_col, premium_col)

        # ④ 多次拒绝下修 (需人工核查)
        df.at[idx, "排除_拒绝下修"] = False
        df.at[idx, "排除_拒绝下修_详情"] = "需人工核查"

        # ⑤ 信用评级 < A
        _check_rating(row, idx, df, rating_col)

    df["排除项计数"] = (
        df["排除_正股价格"].astype(int)
        + df["排除_连续亏损"].astype(int)
        + df["排除_临近到期高溢价"].astype(int)
        + df["排除_评级不足"].astype(int)
    )

    excluded = df[df["排除项计数"] >= 2]
    print(f"  触犯 ≥2 条排除项（建议回避）: {len(excluded)} 只")

    for _, row in excluded.iterrows():
        name = row.get("转债名称", row.get("转债代码", "?"))
        reasons = []
        if row.get("排除_正股价格"):
            reasons.append("正股<5元")
        if row.get("排除_连续亏损"):
            reasons.append("连亏")
        if row.get("排除_临近到期高溢价"):
            reasons.append("到期+高溢价")
        if row.get("排除_评级不足"):
            reasons.append("评级不足")
        print(f"    {name}: {', '.join(reasons)}")

    print(f"  排除项检查完成\n")
    return df


def _check_stock_price(row, idx, df, col):
    if col is None:
        df.at[idx, "排除_正股价格"] = False
        df.at[idx, "排除_正股价格_详情"] = "无数据"
        return

    price = pd.to_numeric(row[col], errors="coerce")
    if pd.notna(price) and price < STOCK_PRICE_MIN:
        df.at[idx, "排除_正股价格"] = True
        df.at[idx, "排除_正股价格_详情"] = f"正股价 {price:.2f} < {STOCK_PRICE_MIN}"
    else:
        df.at[idx, "排除_正股价格"] = False
        df.at[idx, "排除_正股价格_详情"] = f"正股价 {price:.2f}" if pd.notna(price) else "无数据"


def _check_consecutive_loss(row, idx, df, stock_code, financial_data):
    if stock_code not in financial_data or financial_data[stock_code] is None:
        df.at[idx, "排除_连续亏损"] = False
        df.at[idx, "排除_连续亏损_详情"] = "无数据"
        return

    fin_df = financial_data[stock_code].copy()

    net_profit_col = _find_col(fin_df, ["净利润"])
    report_col = _find_col(fin_df, ["报告期"])

    if net_profit_col is None:
        df.at[idx, "排除_连续亏损"] = False
        df.at[idx, "排除_连续亏损_详情"] = "无净利润字段"
        return

    fin_df[net_profit_col] = fin_df[net_profit_col].apply(parse_financial_value)

    if report_col and report_col in fin_df.columns:
        fin_df = fin_df.sort_values(by=report_col, ascending=False)

    recent = fin_df.head(CONSECUTIVE_LOSS_YEARS)
    profits = recent[net_profit_col].dropna().tolist()

    if len(profits) >= CONSECUTIVE_LOSS_YEARS and all(p < 0 for p in profits[:CONSECUTIVE_LOSS_YEARS]):
        df.at[idx, "排除_连续亏损"] = True
        df.at[idx, "排除_连续亏损_详情"] = f"连亏{CONSECUTIVE_LOSS_YEARS}年: {profits[:CONSECUTIVE_LOSS_YEARS]}"
    else:
        df.at[idx, "排除_连续亏损"] = False
        df.at[idx, "排除_连续亏损_详情"] = "净利润正常" if profits else "无数据"


def _check_near_expiry_premium(row, idx, df, expiry_col, premium_col):
    if expiry_col is None:
        df.at[idx, "排除_临近到期高溢价"] = False
        df.at[idx, "排除_临近到期高溢价_详情"] = "无剩余年限数据"
        return

    remaining = pd.to_numeric(row[expiry_col], errors="coerce")
    premium = pd.to_numeric(row[premium_col], errors="coerce") if premium_col else None

    if pd.notna(remaining) and remaining < NEAR_EXPIRY_YEARS:
        if premium is not None and pd.notna(premium) and premium > PREMIUM_HIGH:
            df.at[idx, "排除_临近到期高溢价"] = True
            df.at[idx, "排除_临近到期高溢价_详情"] = f"剩余{remaining:.2f}年, 溢价率{premium:.2f}%"
        else:
            df.at[idx, "排除_临近到期高溢价"] = False
            df.at[idx, "排除_临近到期高溢价_详情"] = f"剩余{remaining:.2f}年, 溢价率不高"
    else:
        df.at[idx, "排除_临近到期高溢价"] = False
        df.at[idx, "排除_临近到期高溢价_详情"] = f"剩余{remaining:.2f}年" if pd.notna(remaining) else "无数据"


def _check_rating(row, idx, df, rating_col):
    if rating_col is None:
        df.at[idx, "排除_评级不足"] = False
        df.at[idx, "排除_评级不足_详情"] = "无评级数据"
        return

    rating = str(row[rating_col]).strip().upper()
    rating_order = ["C", "CC", "CCC", "B", "B+", "BB-", "BB", "BB+", "BBB-", "BBB", "BBB+",
                    "A-", "A", "A+", "AA-", "AA", "AA+", "AAA"]

    min_rating = RATING_EXCLUDE_BELOW.upper()

    if rating in rating_order and min_rating in rating_order:
        if rating_order.index(rating) < rating_order.index(min_rating):
            df.at[idx, "排除_评级不足"] = True
            df.at[idx, "排除_评级不足_详情"] = f"评级 {rating} < {min_rating}"
        else:
            df.at[idx, "排除_评级不足"] = False
            df.at[idx, "排除_评级不足_详情"] = f"评级 {rating}"
    else:
        df.at[idx, "排除_评级不足"] = False
        df.at[idx, "排除_评级不足_详情"] = "未知评级格式"


def _find_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    for col in candidates:
        for df_col in df.columns:
            if col in df_col:
                return df_col
    return None
