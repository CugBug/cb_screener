"""
可转债筛选系统 - 主入口
命令行半自动筛选管线
"""

import argparse
import os
import sys
import time
import traceback
from datetime import datetime

import pandas as pd

from data_fetcher import (
    fetch_all_bonds,
    fetch_financial_abstract,
    fetch_debt_report,
    fetch_pledge_data,
    fetch_bond_value_analysis,
    fetch_bond_summary_sina,
)
from rough_filter import rough_filter
from exclusion_check import check_exclusions
from financial_scorer import score_financials
from investment_scorer import score_investment
from report_generator import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="可转债避雷筛选系统 - 半自动筛选管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --mode rough              # 仅粗筛
  python main.py --mode full               # 完整流程
  python main.py --mode full --output both # 完整流程 + 控制台输出
  python main.py --mode detail --codes 127061,113632  # 指定转债分析
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["rough", "full", "detail"],
        default="full",
        help="运行模式: rough=仅粗筛, full=完整流程, detail=指定转债分析",
    )
    parser.add_argument(
        "--output",
        choices=["excel", "console", "both"],
        default="excel",
        help="输出格式 (默认: excel)",
    )
    parser.add_argument(
        "--codes",
        type=str,
        default="",
        help="指定转债代码，逗号分隔 (用于 detail 模式)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  可转债避雷筛选系统 v1.0")
    print(f"  模式: {args.mode}  输出: {args.output}")
    print("=" * 60)
    print()

    if args.mode == "detail":
        _run_safely(_run_detail_mode, args, "detail")
    elif args.mode == "rough":
        _run_safely(_run_rough_mode, args, "rough")
    else:
        _run_safely(_run_full_mode, args, "full")


def _run_safely(func, args, mode_name):
    """顶层错误包装器：捕获异常，保存中间结果，打印堆栈"""
    try:
        func(args)
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"  [错误] {mode_name} 模式执行失败")
        print(f"  异常: {type(e).__name__}: {e}")
        print(f"{'='*60}")
        traceback.print_exc()
        sys.exit(1)


def _save_partial_result(df: pd.DataFrame, tag: str = "partial"):
    """保存中间结果到 output/ 目录"""
    try:
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        from config import OUTPUT_DIR
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, f"中间结果_{tag}_{suffix}.xlsx")
        df.to_excel(filepath, index=False, engine="openpyxl")
        print(f"  [保存] 中间结果已保存至: {filepath}")
    except Exception:
        pass


def _run_rough_mode(args):
    print("Step 0: 数据获取")
    print("-" * 50)
    df = fetch_all_bonds()
    candidates = rough_filter(df)

    print(f"粗筛完成，共 {len(candidates)} 只候选转债：")
    _print_candidate_list(candidates)

    generate_report(candidates, output_format=args.output)


def _run_full_mode(args):
    t0 = time.time()

    # Step 0: 数据获取
    print("Step 0: 数据获取")
    print("-" * 50)
    df = fetch_all_bonds()

    # Step 1: 粗筛
    candidates = rough_filter(df)

    if len(candidates) == 0:
        print("无候选转债，流程结束")
        return

    # 获取候选池需要的正股财务数据
    print("Step 1.5: 获取财务数据")
    print("-" * 50)
    stock_codes = _extract_stock_codes(candidates)
    print(f"  需获取 {len(stock_codes)} 只正股的财务数据\n")

    financial_data = {}
    debt_data = {}

    for i, code in enumerate(stock_codes):
        print(f"  [{i+1}/{len(stock_codes)}] 获取 {code} 财务摘要...")
        fin = fetch_financial_abstract(code)
        if fin is not None:
            financial_data[code] = fin

        print(f"  [{i+1}/{len(stock_codes)}] 获取 {code} 资产负债表...")
        bs = fetch_debt_report(code)
        if bs is not None:
            debt_data[code] = bs

    print(f"\n  [数据] 获取质押比例...")
    try:
        pledge_data = fetch_pledge_data()
    except Exception as e:
        print(f"    质押数据获取失败: {e}，继续流程")
        pledge_data = None

    # 获取候选池每只转债的纯债价值
    bond_codes = candidates["转债代码"].dropna().astype(str).tolist()
    print(f"\n  [数据] 获取 {len(bond_codes)} 只转债纯债价值...")
    debt_value_map = {}
    for i, code in enumerate(bond_codes):
        print(f"  [{i+1}/{len(bond_codes)}] 获取 {code} 纯债价值...")
        val = fetch_bond_value_analysis(code)
        if val is not None:
            debt_value_map[code] = val
    candidates["纯债价值"] = candidates["转债代码"].astype(str).map(debt_value_map)
    matched = candidates["纯债价值"].notna().sum()
    print(f"  [数据] 纯债价值匹配: {matched}/{len(candidates)} 只\n")

    # 获取候选池每只转债的精确剩余年限 (新浪)
    print(f"  [数据] 获取 {len(bond_codes)} 只转债剩余年限...")
    remain_map = {}
    for i, code in enumerate(bond_codes):
        print(f"  [{i+1}/{len(bond_codes)}] 获取 {code} 剩余年限...")
        val = fetch_bond_summary_sina(code)
        if val is not None:
            remain_map[code] = val
    mask = candidates["转债代码"].astype(str).map(remain_map).notna()
    overwritten = mask.sum()
    candidates.loc[mask, "剩余年限"] = candidates.loc[mask, "转债代码"].astype(str).map(remain_map)
    print(f"  [数据] 剩余年限匹配: {overwritten}/{len(candidates)} 只\n")

    # Step 2: 排除项检查
    try:
        candidates = check_exclusions(candidates, financial_data)
    except Exception as e:
        print(f"    排除项检查失败: {e}")
        _save_partial_result(candidates, "排除前")
        raise

    # Step 3: 财务评分
    try:
        candidates = score_financials(candidates, financial_data, debt_data, pledge_data)
    except Exception as e:
        print(f"    财务评分失败: {e}")
        _save_partial_result(candidates, "评分前")
        raise

    # Step 3.5: 投资推荐评分
    try:
        candidates = score_investment(candidates)
    except Exception as e:
        print(f"    投资推荐评分失败: {e}")
        raise

    # Step 4: 报告输出
    generate_report(candidates, output_format=args.output)

    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed:.1f} 秒")


def _run_detail_mode(args):
    if not args.codes:
        print("错误: detail 模式需要指定 --codes 参数")
        sys.exit(1)

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    print(f"分析指定转债: {', '.join(codes)}")

    # 获取全市场数据，仅保留指定的转债
    df = fetch_all_bonds()

    code_col = "转债代码"
    if code_col not in df.columns:
        print(f"错误: 未找到 '转债代码' 列，可用列: {list(df.columns)[:10]}")
        sys.exit(1)

    df[code_col] = df[code_col].astype(str)
    candidates = df[df[code_col].isin(codes)].copy()

    if candidates.empty:
        print(f"未找到指定转债: {codes}")
        sys.exit(1)

    print(f"找到 {len(candidates)} 只转债\n")

    stock_codes = _extract_stock_codes(candidates)

    financial_data = {}
    debt_data = {}

    for i, code in enumerate(stock_codes):
        print(f"  [{i+1}/{len(stock_codes)}] 获取 {code} 财务摘要...")
        fin = fetch_financial_abstract(code)
        if fin is not None:
            financial_data[code] = fin

        print(f"  [{i+1}/{len(stock_codes)}] 获取 {code} 资产负债表...")
        bs = fetch_debt_report(code)
        if bs is not None:
            debt_data[code] = bs

    print(f"\n  [数据] 获取质押比例...")
    try:
        pledge_data = fetch_pledge_data()
    except Exception as e:
        print(f"    质押数据获取失败: {e}，继续流程")
        pledge_data = None

    # 纯债价值
    bond_codes = candidates["转债代码"].dropna().astype(str).tolist()
    print(f"\n  [数据] 获取 {len(bond_codes)} 只转债纯债价值...")
    debt_value_map = {}
    for i, code in enumerate(bond_codes):
        print(f"  [{i+1}/{len(bond_codes)}] 获取 {code} 纯债价值...")
        val = fetch_bond_value_analysis(code)
        if val is not None:
            debt_value_map[code] = val
    candidates["纯债价值"] = candidates["转债代码"].astype(str).map(debt_value_map)

    # 精确剩余年限 (新浪)
    print(f"  [数据] 获取 {len(bond_codes)} 只转债剩余年限...")
    remain_map = {}
    for i, code in enumerate(bond_codes):
        print(f"  [{i+1}/{len(bond_codes)}] 获取 {code} 剩余年限...")
        val = fetch_bond_summary_sina(code)
        if val is not None:
            remain_map[code] = val
    mask = candidates["转债代码"].astype(str).map(remain_map).notna()
    candidates.loc[mask, "剩余年限"] = candidates.loc[mask, "转债代码"].astype(str).map(remain_map)

    try:
        candidates = check_exclusions(candidates, financial_data)
    except Exception as e:
        print(f"    排除项检查失败: {e}")
        _save_partial_result(candidates, "排除前")
        raise

    try:
        candidates = score_financials(candidates, financial_data, debt_data, pledge_data)
    except Exception as e:
        print(f"    财务评分失败: {e}")
        _save_partial_result(candidates, "评分前")
        raise

    try:
        candidates = score_investment(candidates)
    except Exception as e:
        print(f"    投资推荐评分失败: {e}")
        raise

    generate_report(candidates, output_format="both")


def _extract_stock_codes(df: pd.DataFrame) -> list[str]:
    """从转债数据中提取正股代码列表（去重、格式化）"""
    stock_code_col = None
    for col in ["正股代码"]:
        if col in df.columns:
            stock_code_col = col
            break

    if stock_code_col is None:
        for col in df.columns:
            if "正股代码" in str(col):
                stock_code_col = col
                break

    if stock_code_col is None:
        print("  [错误] 未找到正股代码列")
        return []

    codes = df[stock_code_col].dropna().astype(str).unique().tolist()

    normalized = []
    for c in codes:
        c = c.strip()
        if "." in c:
            c = c.split(".")[0]
        c = c.zfill(6)
        normalized.append(c)

    return list(set(normalized))


def _print_candidate_list(df: pd.DataFrame):
    price_col = "现价" if "现价" in df.columns else None
    premium_col = "溢价率" if "溢价率" in df.columns else None
    rating_col = "评级" if "评级" in df.columns else None

    for _, row in df.iterrows():
        name = row.get("转债名称", row.get("转债代码", "?"))
        price = f"{row.get(price_col, 0):.1f}" if price_col and pd.notna(row.get(price_col)) else "?"
        premium = f"{row.get(premium_col, 0):.1f}%" if premium_col and pd.notna(row.get(premium_col)) else "?"
        rating = str(row.get(rating_col, "?"))[:6] if rating_col else "?"
        print(f"    {str(name):<12} 价格={price:<8} 溢价率={premium:<8} 评级={rating}")


if __name__ == "__main__":
    main()
