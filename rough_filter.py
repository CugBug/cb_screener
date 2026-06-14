"""
可转债筛选系统 - 一级粗筛模块
基于价格区间、评级、溢价率进行快速初筛
"""

import pandas as pd

from config import (
    ROUGH_PRICE_MIN,
    ROUGH_PRICE_MAX,
    ROUGH_RATING_MIN,
    PREMIUM_WARN_THRESHOLD,
    PREMIUM_WARN_PRICE_MIN,
)


def rough_filter(df: pd.DataFrame) -> pd.DataFrame:
    """一级粗筛：价格 + 评级 + 溢价率

    Args:
        df: 全市场转债 DataFrame

    Returns:
        候选池 DataFrame
    """
    print("=" * 50)
    print("Step 1: 一级粗筛")
    print("=" * 50)
    total = len(df)
    print(f"  输入: {total} 只转债")

    df = df.copy()

    if "现价" not in df.columns:
        print("  [错误] 未找到价格列(现价)，跳过筛选")
        return df
    price_col = "现价"

    df[price_col] = pd.to_numeric(df[price_col], errors="coerce")

    # 1. 价格区间筛选
    mask_price = (df[price_col] > ROUGH_PRICE_MIN) & (df[price_col] < ROUGH_PRICE_MAX)
    after_price = mask_price.sum()
    print(f"  价格区间 ({ROUGH_PRICE_MIN}-{ROUGH_PRICE_MAX}): 淘汰 {total - after_price} 只，剩余 {after_price} 只")

    # 2. 评级筛选
    rating_col = "评级" if "评级" in df.columns else None
    if rating_col is not None:
        mask_rating = df[rating_col].apply(lambda r: _rating_ok(r))
        after_rating = (mask_price & mask_rating).sum()
        print(f"  评级筛选 (>= {ROUGH_RATING_MIN}): 淘汰 {after_price - after_rating} 只，剩余 {after_rating} 只")
    else:
        mask_rating = pd.Series(True, index=df.index)
        print("  [警告] 未找到评级列，跳过评级筛选")

    # 3. 溢价率标注（仅标注，不排除）
    premium_col = "溢价率" if "溢价率" in df.columns else None
    if premium_col is not None:
        df[premium_col] = pd.to_numeric(df[premium_col], errors="coerce")
        mask_premium_warn = (
            (df[premium_col] > PREMIUM_WARN_THRESHOLD)
            & (df[price_col] > PREMIUM_WARN_PRICE_MIN)
        )
        df["溢价率预警"] = mask_premium_warn
        warn_count = mask_premium_warn.sum()
        print(f"  溢价率预警 (> {PREMIUM_WARN_THRESHOLD}% 且价格 > {PREMIUM_WARN_PRICE_MIN}): {warn_count} 只")
    else:
        df["溢价率预警"] = False
        print("  [警告] 未找到溢价率列")

    candidates = df[mask_price & mask_rating].copy()
    print(f"  >>> 粗筛结果: {total} → {len(candidates)} 只候选\n")

    return candidates


def _find_column(df: pd.DataFrame, candidates: list) -> str | None:
    """查找存在的列名"""
    for col in candidates:
        if col in df.columns:
            return col
    # 模糊匹配
    for col in candidates:
        for df_col in df.columns:
            if col in df_col:
                return df_col
    return None


def _rating_ok(rating: str) -> bool:
    """判断评级是否通过"""
    if pd.isna(rating):
        return False

    rating = str(rating).strip().upper()

    rating_order = ["C", "CC", "CCC", "B", "B+", "BB-", "BB", "BB+", "BBB-", "BBB", "BBB+",
                    "A-", "A", "A+", "AA-", "AA", "AA+", "AAA"]

    if rating not in rating_order:
        return True

    min_rating = ROUGH_RATING_MIN.upper()
    if min_rating not in rating_order:
        return True

    return rating_order.index(rating) >= rating_order.index(min_rating)
