"""
可转债筛选系统 - 报告输出模块
生成 Excel 和控制台报告
"""

import os
from datetime import datetime

import pandas as pd

from config import OUTPUT_DIR


def generate_report(df: pd.DataFrame, output_format: str = "excel") -> str:
    """生成筛选报告

    Args:
        df: 包含评分和排除标记的 DataFrame
        output_format: "excel" / "console" / "both"

    Returns:
        输出文件路径（excel 模式）
    """
    print("=" * 50)
    print("Step 4: 报告输出")
    print("=" * 50)

    if output_format in ("console", "both"):
        _print_console_report(df)

    filepath = ""
    if output_format in ("excel", "both"):
        filepath = _write_excel_report(df)

    return filepath


def _print_console_report(df: pd.DataFrame):
    """控制台输出报告"""

    sort_col = "财务总分" if "财务总分" in df.columns else None
    if sort_col:
        df_sorted = df.sort_values(by=sort_col, ascending=False, na_position="last")
    else:
        df_sorted = df

    print("\n" + "=" * 80)
    print("  可转债避雷筛选报告")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 概览表
    has_ytm = "到期收益率" in df.columns and df["到期收益率"].notna().any()
    if has_ytm:
        print(f"\n{'转债名称':<12} {'现价':>8} {'溢价率':>8} {'到期收益率':>8} {'评级':>6} {'排除项':>6} {'评分':>6} {'风险等级':<10}")
        print("-" * 86)
    else:
        print(f"\n{'转债名称':<12} {'现价':>8} {'溢价率':>8} {'评级':>6} {'排除项':>6} {'评分':>6} {'风险等级':<10}")
        print("-" * 70)

    price_col = "现价" if "现价" in df.columns else None
    premium_col = "溢价率" if "溢价率" in df.columns else None
    rating_col = "评级" if "评级" in df.columns else None
    ytm_col = "到期收益率" if has_ytm else None

    for _, row in df_sorted.iterrows():
        name = str(row.get("转债名称", row.get("转债代码", "?")))[:10]
        price = f"{row.get(price_col, 0):.1f}" if price_col and pd.notna(row.get(price_col)) else "?"
        premium = f"{row.get(premium_col, 0):.1f}%" if premium_col and pd.notna(row.get(premium_col)) else "?"
        rating = str(row.get(rating_col, "?"))[:4] if rating_col else "?"
        excluded = int(row.get("排除项计数", 0))
        score = row.get("财务总分", 0)
        level = row.get("风险等级", "?")

        if has_ytm:
            ytm_val = row.get("到期收益率")
            ytm = f"{ytm_val:.1f}%" if pd.notna(ytm_val) else "N/A"
            print(f"{name:<12} {price:>8} {premium:>8} {ytm:>8} {rating:>6} {excluded:>6} {score:>6.1f} {level:<10}")
        else:
            print(f"{name:<12} {price:>8} {premium:>8} {rating:>6} {excluded:>6} {score:>6.1f} {level:<10}")

    # 详情
    print("\n" + "-" * 80)
    print("  [排除项标记 ≥2 的转债详情]")
    print("-" * 80)

    if "排除项计数" in df_sorted.columns:
        excluded_df = df_sorted[df_sorted["排除项计数"] >= 2]
    else:
        excluded_df = pd.DataFrame()

    if excluded_df.empty:
        print("  (无)")
    else:
        for _, row in excluded_df.iterrows():
            _print_bond_detail(row, price_col, premium_col, rating_col)

    print("\n" + "-" * 80)
    print("  [财务评分最低的5只转债详情]")
    print("-" * 80)

    if "财务总分" in df_sorted.columns:
        bottom5 = df_sorted.tail(5)
        for _, row in bottom5.iterrows():
            _print_bond_detail(row, price_col, premium_col, rating_col)
    else:
        print("  (无评分数据)")

    print("\n" + "=" * 80)
    print("  报告结束")
    print("=" * 80)


def _print_bond_detail(row, price_col, premium_col, rating_col):
    name = row.get("转债名称", row.get("转债代码", "?"))
    code = row.get("转债代码", "?")

    print(f"\n  === {name}（{code}）详情 ===")

    if "排除_正股价格" in row.index:
        print("  【一键排除】")
        det_1 = row.get("排除_正股价格_详情", "无数据")
        mark_1 = "[X]" if row.get("排除_正股价格") else "[OK]"
        print(f"    ① 正股价格 < 5元          → {det_1}  {mark_1}")

        det_2 = row.get("排除_连续亏损_详情", "无数据")
        mark_2 = "[X]" if row.get("排除_连续亏损") else "[OK]"
        print(f"    ② 连续亏损                  → {det_2}  {mark_2}")

        det_3 = row.get("排除_临近到期高溢价_详情", "无数据")
        mark_3 = "[X]" if row.get("排除_临近到期高溢价") else "[OK]"
        print(f"    ③ 剩余<6月+溢价率>20%    → {det_3}  {mark_3}")

        det_4 = row.get("排除_拒绝下修_详情", "无数据")
        print(f"    ④ 多次拒绝下修              → {det_4}")

        det_5 = row.get("排除_评级不足_详情", "无数据")
        mark_5 = "[X]" if row.get("排除_评级不足") else "[OK]"
        print(f"    ⑤ 信用评级 < A               → {det_5}  {mark_5}")

        excluded_count = int(row.get("排除项计数", 0))
        print(f"    排除结论: 触犯{excluded_count}条")

    if "评分_资产负债率" in row.index:
        print("  【财务指标】")
        _print_indicator("资产负债率", row)
        _print_indicator("毛利率", row)
        _print_indicator("经营现金流/净利润", row)
        _print_indicator("货币资金/流动负债", row)
        _print_indicator("应收账款/营收", row)
        _print_indicator("连续亏损", row)
        _print_indicator("股权质押", row)
        _print_indicator("审计意见", row)

    if "风险等级" in row.index and row.get("风险等级"):
        print(f"  【综合判定】{row.get('风险等级', '?')}  (评分: {row.get('财务总分', 0):.1f})")


def _print_indicator(name, row):
    detail = row.get(f"详情_{name}", "无数据")
    score = row.get(f"评分_{name}", None)

    if score == 2:
        icon = "[OK]"
    elif score == 1:
        icon = "[!]"
    elif score == 0:
        icon = "[X]"
    else:
        icon = "[?]"

    print(f"    {name}: {detail:<20} {icon}")


def _write_excel_report(df: pd.DataFrame) -> str:
    """输出 Excel 报告"""

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now()
    filepath = os.path.join(OUTPUT_DIR, f"筛选报告_{now.strftime('%Y%m%d_%H%M%S')}.xlsx")

    try:
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            _write_overview_sheet(df, writer)
            _write_detail_sheet(df, writer)

        print(f"  [报告] Excel 已保存至: {filepath}")
    except PermissionError:
        # 文件可能被占用，尝试备用文件名
        filepath = os.path.join(OUTPUT_DIR, f"筛选报告_{now.strftime('%Y%m%d_%H%M%S')}_v2.xlsx")
        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            _write_overview_sheet(df, writer)
            _write_detail_sheet(df, writer)
        print(f"  [报告] Excel 已保存至: {filepath}")
    return filepath


def _write_overview_sheet(df, writer):
    overview_cols = _build_overview_columns(df)

    overview_df = df[overview_cols].copy()
    overview_df = overview_df.sort_values(by="财务总分", ascending=False, na_position="last")

    overview_df.to_excel(writer, sheet_name="概览", index=False)

    ws = writer.sheets["概览"]
    for i, col in enumerate(overview_df.columns, 1):
        max_len = max(len(str(col)), overview_df[col].astype(str).str.len().max() or 0)
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = min(max_len + 4, 40)


def _write_detail_sheet(df, writer):
    detail_cols = _build_detail_columns(df)

    detail_df = df[detail_cols].copy()
    detail_df = detail_df.sort_values(by="财务总分", ascending=False, na_position="last")

    detail_df.to_excel(writer, sheet_name="详情", index=False)

    ws = writer.sheets["详情"]
    for i, col in enumerate(detail_df.columns, 1):
        max_len = max(len(str(col)), detail_df[col].astype(str).str.len().max() or 0)
        col_letter = _col_idx_to_letter(i)
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def _build_overview_columns(df):
    cols = []

    for c in ["转债代码", "转债名称"]:
        if c in df.columns:
            cols.append(c)

    price_col = "现价" if "现价" in df.columns else None
    if price_col:
        cols.append("现价")

    for c in ["溢价率", "到期收益率", "评级"]:
        if c in df.columns:
            cols.append(c)

    for c in ["排除项计数", "财务总分", "风险等级", "风险建议"]:
        if c in df.columns:
            cols.append(c)

    return cols


def _build_detail_columns(df):
    cols = _build_overview_columns(df)

    detail_prefixes = ["排除_", "评分_", "详情_"]
    for col in df.columns:
        if any(col.startswith(p) for p in detail_prefixes):
            cols.append(col)

    return cols


def _col_idx_to_letter(i):
    result = ""
    while i > 0:
        i -= 1
        result = chr(65 + i % 26) + result
        i //= 26
    return result


def _find_col(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    for col in candidates:
        for df_col in df.columns:
            if col in df_col:
                return df_col
    return None
