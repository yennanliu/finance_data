"""
Configuration constants for analysis generation.
"""

from datetime import date

TODAY = date.today().isoformat()
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TOKENS = 20000

ANALYSIS_TYPES = {
    "fundamental-analysis": {
        "filename_prefix": "fundamental_analysis",
        "label": "基本面深度分析",
        "ext": ".md",
    },
    "technical-analysis": {
        "filename_prefix": "technical_analysis",
        "label": "技術分析",
        "ext": ".md",
    },
    "stock-eval": {
        "filename_prefix": "stock_eval",
        "label": "綜合股票評估",
        "ext": ".md",
    },
    "economics-analysis": {
        "filename_prefix": "economics_analysis",
        "label": "總體經濟分析",
        "ext": ".md",
    },
    "portfolio-review": {
        "filename_prefix": "portfolio_review",
        "label": "投資組合回顧",
        "ext": ".md",
    },
    "sector-analysis": {
        "filename_prefix": "sector_analysis",
        "label": "產業板塊分析",
        "ext": ".md",
    },
    "earnings-call-analysis": {
        "filename_prefix": "earnings_call_analysis",
        "label": "財報電話會議分析",
        "ext": ".md",
    },
    "insider-trading": {
        "filename_prefix": "insider_trading",
        "label": "內部人交易分析",
        "ext": ".md",
    },
    "institutional-ownership": {
        "filename_prefix": "institutional_ownership",
        "label": "機構持股分析",
        "ext": ".md",
    },
    "report-generator": {
        "filename_prefix": "report",
        "label": "綜合HTML投資報告",
        "ext": ".html",
    },
    "financial-report-analyst": {
        "filename_prefix": "financial_report_analyst",
        "label": "財報深度解析",
        "ext": ".md",
    },
    "stock-valuation": {
        "filename_prefix": "stock_valuation",
        "label": "多方法估值分析",
        "ext": ".md",
    },
}

__all__ = ["TODAY", "DEFAULT_MODEL", "DEFAULT_TOKENS", "ANALYSIS_TYPES"]
