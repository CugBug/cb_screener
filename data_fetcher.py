
"""
可转债筛选系统 - 数据获取层
封装所有 AkShare API 调用, 提供统一的数据接口

实际 API 列名映射:
  bond_zh_hs_cov_spot: symbol, code, name, trade (现价)
  bond_zh_cov: 债券代码, 债券简称, 正股代码, 正股价, 转股溢价率, 信用评级, 上市时间
  stock_financial_abstract_ths: 报告期, 净利润, 基本每股收益, 每股经营现金流, 销售毛利率, 资产负债率
  stock_financial_debt_ths: 报告期, 货币资金, 应收账款, 流动负债合计, 营业总收入
  stock_gpzy_pledge_ratio_em: 股票代码, 质押比例
"""

import time
from datetime import date, datetime

import akshare as ak
import pandas as pd


# ── AkShare 原始 API ──

def _fetch_spot() -> pd.DataFrame:
    """bond_zh_hs_cov_spot() - 全市场转债实时行情"""
    print("  [数据] 获取全市场转债行情...")
    df = ak.bond_zh_hs_cov_spot()
    print(f"  [数据] 获取到 {len(df)} 只转债行情")
    return df


def _fetch_detail() -> pd.DataFrame:
    """bond_zh_cov() - 全市场转债基本信息"""
    print("  [数据] 获取全市场转债基本信息...")
    df = ak.bond_zh_cov()
    print(f"  [数据] 获取到 {len(df)} 条转债基本信息")
    return df


def _fetch_pledge_raw() -> pd.DataFrame | None:
    """stock_gpzy_pledge_ratio_em() - 全市场股权质押比例"""
    try:
        df = ak.stock_gpzy_pledge_ratio_em()
        print(f"  [数据] 获取到 {len(df)} 条质押数据")
        return df
    except Exception as e:
        print(f"    警告: 获取股权质押数据失败 - {e}")
        return None


# ── 公开接口 ──

def fetch_all_bonds() -> pd.DataFrame:
    """合并转债行情与基本信息, 输出标准化 DataFrame

    Returns columns:
        转债代码, 转债名称, 现价, 溢价率, 评级, 剩余年限,
        正股代码, 正股价, 上市时间
    """
    spot = _fetch_spot()
    detail = _fetch_detail()

    # 标准化 spot 列名: code -> 转债代码, name -> 转债名称, trade -> 现价
    spot = spot.rename(columns={
        "code": "转债代码",
        "name": "转债名称",
        "trade": "现价",
    })

    # 标准化 detail 列名
    detail = detail.rename(columns={
        "债券代码": "转债代码",
        "债券简称": "转债简称",
        "转股溢价率": "溢价率",
        "信用评级": "评级",
        "正股代码": "正股代码",
        "正股价": "正股价",
    })

    # 计算剩余年限 (默认 6 年期转债)
    # 上市时间 + 20天 ≈ 发行日期，部分补偿上市延迟
    if "上市时间" in detail.columns:
        today = date.today()
        detail["剩余年限"] = detail["上市时间"].apply(
            lambda d: max(0.0, round(6.0 - (today - d).days / 365.25 - 0.05, 2))
            if pd.notna(d) else None
        )

    # 合并: spot LEFT JOIN detail ON 转债代码
    keep_cols = [
        "转债代码", "转债简称", "溢价率", "评级", "剩余年限",
        "正股代码", "正股价", "上市时间",
    ]
    keep_cols = [c for c in keep_cols if c in detail.columns]
    detail_sub = detail[keep_cols]

    merged = pd.merge(
        spot[["转债代码", "转债名称", "现价"]],
        detail_sub,
        on="转债代码",
        how="left",
        suffixes=("", "_y"),
    )

    # 清理重复列
    dup_cols = [c for c in merged.columns if c.endswith("_y")]
    if dup_cols:
        merged.drop(columns=dup_cols, inplace=True)

    # 数值化
    for col in ["现价", "溢价率", "正股价", "剩余年限"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # 补充到期收益率 + 剩余年限（Jisilu 精确值覆盖估算值）
    merged = _merge_jisilu_data(merged)

    print(f"  [数据] 合并后共 {len(merged)} 条记录\n")
    return merged


def fetch_financial_abstract(stock_code: str) -> pd.DataFrame | None:
    """stock_financial_abstract_ths(symbol) - 获取正股财务摘要

    Returns columns: 报告期, 净利润, 基本每股收益, 每股经营现金流, 销售毛利率, 资产负债率
    """
    try:
        df = ak.stock_financial_abstract_ths(symbol=stock_code)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"    警告: 获取 {stock_code} 财务摘要失败 - {e}")
        return None


def fetch_debt_report(stock_code: str) -> pd.DataFrame | None:
    """stock_financial_debt_ths(symbol) - 获取资产负债表 (东方财富)

    Returns columns: 报告期, 货币资金, 应收账款, 流动负债合计, 营业总收入
    """
    try:
        df = ak.stock_financial_debt_ths(symbol=stock_code)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"    警告: 获取 {stock_code} 资产负债表失败 - {e}")
        return None


def fetch_pledge_data() -> pd.DataFrame | None:
    """获取并标准化质押比例数据

    Returns columns: 股票代码, 质押比例
    """
    df = _fetch_pledge_raw()
    if df is None:
        return None

    df = df.rename(columns={
        "股票代码": "股票代码",
        "质押比例": "质押比例",
    })

    # 标准化股票代码
    if "股票代码" in df.columns:
        df["股票代码"] = df["股票代码"].astype(str).str.strip().str.zfill(6)

    return df


def fetch_jisilu_data() -> pd.DataFrame | None:
    """bond_cb_jsl() - 集思录转债数据（含到期税前收益）

    默认返回 30 条，需要 cookie 才能获取全量。
    Returns columns: 代码, 到期税前收益, 剩余年限, 债券评级, ...
    """
    try:
        df = ak.bond_cb_jsl()
        print(f"  [数据] 集思录获取到 {len(df)} 条记录")
        return df
    except Exception as e:
        print(f"    警告: 获取集思录数据失败 - {e}")
        return None


def _merge_jisilu_data(merged: pd.DataFrame) -> pd.DataFrame:
    """将集思录的到期税前收益和剩余年限合并到主数据中

    Jisilu 的剩余年限是精确值，优先覆盖估算值。
    到期收益率同样来自 Jisilu。
    """
    merged["到期收益率"] = None

    jsl = fetch_jisilu_data()
    if jsl is None or jsl.empty:
        return merged

    if "代码" not in jsl.columns:
        return merged

    code_col = jsl["代码"].astype(str).str.strip()
    merged_code = merged["转债代码"].astype(str).str.strip()

    # 到期收益率
    if "到期税前收益" in jsl.columns:
        ytm_map = dict(zip(code_col, pd.to_numeric(jsl["到期税前收益"], errors="coerce")))
        merged["到期收益率"] = merged_code.map(ytm_map)
        matched_ytm = merged["到期收益率"].notna().sum()
        print(f"  [数据] 到期收益率匹配: {matched_ytm}/{len(merged)} 只")

    # 剩余年限 — Jisilu 精确值覆盖估算值
    if "剩余年限" in jsl.columns:
        remain_map = dict(zip(code_col, pd.to_numeric(jsl["剩余年限"], errors="coerce")))
        jsl_remain = merged_code.map(remain_map)
        overwritten = (jsl_remain.notna() & merged["剩余年限"].notna()).sum()
        filled = (jsl_remain.notna() & merged["剩余年限"].isna()).sum()
        merged["剩余年限"] = jsl_remain.combine_first(merged["剩余年限"])
        print(f"  [数据] 剩余年限(Jisilu): 覆盖 {overwritten} 只, 补充 {filled} 只")

    return merged


def parse_financial_value(val) -> float | None:
    """安全解析财务数据值: 处理 '598.46万', '-1.05亿', '16.56%' 等格式

    不使用 eval()，逐字符解析，防止代码注入。
    """
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").strip()
    if s in ("False", ""):
        return None
    multiplier = 1.0
    if s.endswith("亿"):
        multiplier = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        multiplier = 1e4
        s = s[:-1]
    s = s.replace("%", "")
    try:
        return float(s) * multiplier
    except ValueError:
        return None
