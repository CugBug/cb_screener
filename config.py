"""
可转债筛选系统 - 可配置参数
修改此文件中的参数即可调整筛选策略
"""

# ═══════════════════════════════════════════════
# 一级粗筛参数
# ═══════════════════════════════════════════════

ROUGH_PRICE_MIN = 80
ROUGH_PRICE_MAX = 120
ROUGH_RATING_MIN = "A"

PREMIUM_WARN_THRESHOLD = 200.0
PREMIUM_WARN_PRICE_MIN = 110.0

# ═══════════════════════════════════════════════
# 排除项参数
# ═══════════════════════════════════════════════

STOCK_PRICE_MIN = 5.0
CONSECUTIVE_LOSS_YEARS = 2
NEAR_EXPIRY_YEARS = 0.5
PREMIUM_HIGH = 20.0
RATING_EXCLUDE_BELOW = "A"

# ═══════════════════════════════════════════════
# 财务评分权重 (8项，总和应为1.0)
# ═══════════════════════════════════════════════

WEIGHT_CASH_TO_CURRENT_LIAB = 0.10
WEIGHT_DEBT_RATIO = 0.15
WEIGHT_RECEIVABLES_TO_REVENUE = 0.10
WEIGHT_CFO_TO_NET_PROFIT = 0.15
WEIGHT_GROSS_MARGIN = 0.10
WEIGHT_CONSECUTIVE_LOSS = 0.15
WEIGHT_AUDIT_OPINION = 0.10
WEIGHT_PLEDGE_RATIO = 0.15

# ═══════════════════════════════════════════════
# 财务指标阈值
# ═══════════════════════════════════════════════

# 货币资金/流动负债
CASH_TO_CURRENT_LIAB_SAFE = 0.80
CASH_TO_CURRENT_LIAB_WARN = 0.50

# 资产负债率
DEBT_RATIO_SAFE = 0.60
DEBT_RATIO_WARN = 0.70

# 应收账款/营收
RECEIVABLES_TO_REVENUE_SAFE = 0.20
RECEIVABLES_TO_REVENUE_WARN = 0.50

# 经营现金流/净利润
CFO_TO_NET_PROFIT_SAFE = 1.0
CFO_TO_NET_PROFIT_WARN = 0.5

# 毛利率
GROSS_MARGIN_SAFE = 0.20
GROSS_MARGIN_WARN = 0.10

# 股权质押
PLEDGE_RATIO_SAFE = 0.30
PLEDGE_RATIO_WARN = 0.50

# ═══════════════════════════════════════════════
# 风险等级
# ═══════════════════════════════════════════════

RISK_LEVELS = [
    (80, 100, "[安全] 安全", "可关注"),
    (60, 80, "[关注] 需关注", "结合溢价率和价格综合评估"),
    (40, 60, "[谨慎] 谨慎", "个别指标出问题，需细看"),
    (0, 40, "[回避] 回避", "建议不碰"),
]

# ═══════════════════════════════════════════════
# 输出配置
# ═══════════════════════════════════════════════

OUTPUT_DIR = "output"
