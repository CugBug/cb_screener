
"""
可转债筛选系统 - 数据获取层
封装所有 AkShare API 调用, 提供统一的数据接口

实际 API 列名映射:
  bond_zh_hs_cov_spot: symbol, code, name, trade (现价)
  bond_zh_cov: 债券代码, 正股代码, 正股价, 转股溢价率, 信用评级, 上市时间
  stock_financial_abstract_ths: 报告期, 净利润, 基本每股收益, 销售毛利率, 资产负债率
  stock_financial_debt_ths: 报告期, 货币资金, 应收账款, 流动负债合计
  stock_gpzy_pledge_ratio_em: 股票代码, 质押比例
  bond_cb_jsl: 代码, 剩余年限 (Jisilu 精确值)
"""

import time
from datetime import date

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
        纯债价值, 正股代码, 正股价
    """
    spot = _fetch_spot()
    detail = _fetch_detail()

    # 标准化 spot 列名
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

    # 计算剩余年限 (默认 6 年期转债，上市时间 + 20天 ≈ 发行日期)
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

    # 纯债价值在 Step 1.5 通过 bond_zh_cov_value_analysis() 逐只获取
    merged["纯债价值"] = None

    print(f"  [数据] 合并后共 {len(merged)} 条记录\n")
    return merged


def fetch_financial_abstract(stock_code: str) -> pd.DataFrame | None:
    """stock_financial_abstract_ths(symbol) - 获取正股财务摘要"""
    try:
        df = ak.stock_financial_abstract_ths(symbol=stock_code)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"    警告: 获取 {stock_code} 财务摘要失败 - {e}")
        return None


def fetch_debt_report(stock_code: str) -> pd.DataFrame | None:
    """stock_financial_debt_ths(symbol) - 获取资产负债表"""
    try:
        df = ak.stock_financial_debt_ths(symbol=stock_code)
        time.sleep(0.3)
        return df
    except Exception as e:
        print(f"    警告: 获取 {stock_code} 资产负债表失败 - {e}")
        return None


def fetch_pledge_data() -> pd.DataFrame | None:
    """获取并标准化质押比例数据"""
    df = _fetch_pledge_raw()
    if df is None:
        return None

    df = df.rename(columns={
        "股票代码": "股票代码",
        "质押比例": "质押比例",
    })

    if "股票代码" in df.columns:
        df["股票代码"] = df["股票代码"].astype(str).str.strip().str.zfill(6)

    return df


def fetch_bond_value_analysis(bond_code: str) -> float | None:
    """bond_zh_cov_value_analysis(symbol) - 获取单只转债最新纯债价值"""
    try:
        df = ak.bond_zh_cov_value_analysis(symbol=bond_code)
        time.sleep(0.3)
        if df is None or df.empty or "纯债价值" not in df.columns:
            return None
        latest = df.sort_values(by="日期", ascending=False).iloc[0]
        val = latest["纯债价值"]
        return float(val) if pd.notna(val) else None
    except Exception as e:
        print(f"    警告: 获取 {bond_code} 纯债价值失败 - {e}")
        return None


def fetch_bond_summary_sina(bond_code: str) -> float | None:
    """bond_cb_summary_sina(symbol) - 获取单只转债剩余年限 (新浪财经)

    需要带市场前缀: sh=D浠? sz=深市
    Returns: 剩余年限 (float) 或 None
    """
    try:
        if bond_code.startswith("11"):
            symbol = f"sh{bond_code}"
        elif bond_code.startswith("12"):
            symbol = f"sz{bond_code}"
        else:
            return None

        df = ak.bond_cb_summary_sina(symbol=symbol)
        time.sleep(0.3)
        if df is None or df.empty:
            return None

        remain_row = df[df["item"] == "剩余年限（年）"]
        if remain_row.empty:
            return None
        val = remain_row.iloc[0]["value"]
        return float(val) if pd.notna(val) and val != "--" else None
    except Exception as e:
        print(f"    警告: 获取 {bond_code} 剩余年限失败 - {e}")
        return None


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
