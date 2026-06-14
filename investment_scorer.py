"""
可转债筛选系统 - 投资推荐评分模块
基于估值 + 质量双维度，输出推荐分和星级
"""

import pandas as pd

from config import (
    INVEST_WEIGHT_VALUATION,
    INVEST_WEIGHT_QUALITY,
    VALUATION_DEBT_VALUE_RATIO_WEIGHT,
    VALUATION_PREMIUM_WEIGHT,
    DEBT_VALUE_RATIO_SAFE,
    DEBT_VALUE_RATIO_FAIR,
    PREMIUM_VALUATION_LOW,
    PREMIUM_VALUATION_MID,
    PREMIUM_VALUATION_HIGH,
    QUALITY_FINANCIAL_SCORE_WEIGHT,
    QUALITY_RATING_WEIGHT,
    RATING_BONUS,
    EXCLUSION_PENALTY_1,
    MIN_REMAINING_YEARS,
    INVEST_LEVELS,
)


def score_investment(df: pd.DataFrame) -> pd.DataFrame:
    """计算投资推荐分和星级

    Args:
        df: 包含财务评分和排除标记的 DataFrame
            需要列: 现价, 纯债价值, 溢价率, 财务总分, 评级, 排除项计数, 剩余年限

    Returns:
        增加 推荐分, 推荐等级 列的 DataFrame
    """
    print("=" * 50)
    print("Step 3.5: 投资推荐评分")
    print("=" * 50)

    df = df.copy()
    df["估值分"] = 0.0
    df["质量分"] = 0.0
    df["推荐分"] = 0.0
    df["推荐等级"] = ""
    df["推荐原因"] = ""

    for idx, row in df.iterrows():
        excluded = int(row.get("排除项计数", 0))

        # 触犯 ≥2 条排除项 → 直接 ★ 回避
        if excluded >= 2:
            df.at[idx, "推荐分"] = 0.0
            df.at[idx, "推荐等级"] = "★ 回避"
            reasons = []
            if row.get("排除_正股价格"):
                reasons.append("正股<5")
            if row.get("排除_连续亏损"):
                reasons.append("连亏")
            if row.get("排除_临近到期高溢价"):
                reasons.append("到期+高溢价")
            if row.get("排除_评级不足"):
                reasons.append("评级低")
            df.at[idx, "推荐原因"] = f"排除≥2条: {', '.join(reasons)}"
            continue

        valuation, val_detail = _score_valuation(row)
        quality, qual_detail = _score_quality(row, excluded)
        total = valuation * INVEST_WEIGHT_VALUATION + quality * INVEST_WEIGHT_QUALITY

        # 剩余年限闸门: < 4个月上限锁死 ★★
        remaining = row.get("剩余年限")
        capped = pd.notna(remaining) and remaining < MIN_REMAINING_YEARS

        df.at[idx, "估值分"] = round(valuation, 1)
        df.at[idx, "质量分"] = round(quality, 1)
        df.at[idx, "推荐分"] = round(total, 1)

        if capped:
            df.at[idx, "推荐等级"] = "★★ 暂不考虑"
            df.at[idx, "推荐原因"] = f"剩余{remaining:.2f}年<{MIN_REMAINING_YEARS}年(锁死) | {val_detail} | {qual_detail}"
        else:
            df.at[idx, "推荐等级"] = _assign_level(total)
            excl_note = f" 排除-{EXCLUSION_PENALTY_1}" if excluded == 1 else ""
            df.at[idx, "推荐原因"] = f"估值({val_detail}) 质量({qual_detail}{excl_note})"

    _print_summary(df)
    return df


def _score_valuation(row) -> tuple[float, str]:
    """估值分 = 纯债价值比 × 0.6 + 溢价率 × 0.4，满分 100

    Returns: (score, detail_string)
    """
    max_val = 100.0

    # 纯债价值比
    price = row.get("现价")
    debt_value = row.get("纯债价值")

    if pd.notna(price) and pd.notna(debt_value) and debt_value > 0:
        ratio = price / debt_value
        if ratio < DEBT_VALUE_RATIO_SAFE:
            debt_score = 1.0
            debt_desc = f"纯债折价{ratio:.2f}"
        elif ratio < DEBT_VALUE_RATIO_FAIR:
            debt_score = 0.67
            debt_desc = f"纯债合理{ratio:.2f}"
        else:
            debt_score = 0.33 if ratio <= 1.0 else 0.0
            debt_desc = f"纯债偏高{ratio:.2f}" if ratio <= 1.0 else f"纯债溢价{ratio:.2f}"
    else:
        debt_score = 0.33
        debt_desc = "无纯债"

    # 溢价率
    premium = row.get("溢价率")
    if pd.notna(premium):
        if premium < PREMIUM_VALUATION_LOW:
            premium_score = 1.0
            prem_desc = f"溢价低{premium:.0f}%"
        elif premium < PREMIUM_VALUATION_MID:
            premium_score = 0.6
            prem_desc = f"溢价中{premium:.0f}%"
        elif premium < PREMIUM_VALUATION_HIGH:
            premium_score = 0.25
            prem_desc = f"溢价高{premium:.0f}%"
        else:
            premium_score = 0.0
            prem_desc = f"溢价极高{premium:.0f}%"
    else:
        premium_score = 0.25
        prem_desc = "无溢价率"

    score = max_val * (debt_score * VALUATION_DEBT_VALUE_RATIO_WEIGHT + premium_score * VALUATION_PREMIUM_WEIGHT)
    detail = f"{debt_desc}+{prem_desc}={score:.0f}"
    return score, detail


def _score_quality(row, excluded: int) -> tuple[float, str]:
    """质量分 = 财务总分 × 0.7 + 评级 × 0.3 − 排除扣分，满分 100

    Returns: (score, detail_string)
    """
    max_val = 100.0

    # 财务总分
    fin_score = row.get("财务总分", 50)
    fin_normalized = fin_score / 100.0 if pd.notna(fin_score) else 0.5
    fin_contrib = max_val * fin_normalized * QUALITY_FINANCIAL_SCORE_WEIGHT

    # 评级
    rating = str(row.get("评级", "")).strip().upper()
    rating_bonus_raw = RATING_BONUS.get(rating, 0)
    rating_contrib = max_val * (rating_bonus_raw / 30.0) * QUALITY_RATING_WEIGHT

    quality = fin_contrib + rating_contrib

    detail = f"财务{fin_score:.0f}+评级{rating}({rating_bonus_raw})={quality:.0f}"

    # 排除项扣分
    if excluded == 1:
        quality -= EXCLUSION_PENALTY_1

    return max(0.0, quality), detail


def _assign_level(score: float) -> str:
    for low, high, stars, label in INVEST_LEVELS:
        if low <= score < high:
            return f"{stars} {label}"
    if score >= 100:
        return "★★★★★ 强烈推荐"
    return "★ 回避"


def _print_summary(df: pd.DataFrame):
    """打印各星级分布"""
    if "推荐等级" not in df.columns:
        return
    counts = df["推荐等级"].value_counts()
    for _, _, stars, label in INVEST_LEVELS:
        full_text = f"{stars} {label}"
        cnt = counts.get(full_text, 0)
        if cnt > 0:
            print(f"    {full_text}: {cnt} 只")

    # 前5推荐 (排除 ★ 回避 和 ★★ 暂不考虑)
    top5 = df[df["推荐分"] >= 40].sort_values(by="推荐分", ascending=False).head(5)
    if not top5.empty:
        print("  [TOP5]")
        for _, row in top5.iterrows():
            name = row.get("转债名称", row.get("转债代码", "?"))
            score = row.get("推荐分", 0)
            level = row.get("推荐等级", "?")
            print(f"    {str(name)[:10]:<12} 推荐分={score:.1f}  {level}")

    print("  投资推荐评分完成\n")
