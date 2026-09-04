"""
Configuration constants for analysis generation.
"""

from datetime import date

TODAY = date.today().isoformat()
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_TOKENS = 32000

# One entry per analysis type — the single place a new type is declared.
# ``prompt_file`` names the template under analysis/prompts/ (the name rarely
# matches the type verbatim), so adding a type never means editing a second
# map that can silently fall out of sync with this one.
ANALYSIS_TYPES = {
    "fundamental-analysis": {
        "filename_prefix": "fundamental_analysis",
        "label": "基本面深度分析",
        "ext": ".md",
        "prompt_file": "fundamental",
    },
    "technical-analysis": {
        "filename_prefix": "technical_analysis",
        "label": "技術分析",
        "ext": ".md",
        "prompt_file": "technical",
    },
    "stock-eval": {
        "filename_prefix": "stock_eval",
        "label": "綜合股票評估",
        "ext": ".md",
        "prompt_file": "stock_eval",
    },
    "economics-analysis": {
        "filename_prefix": "economics_analysis",
        "label": "總體經濟分析",
        "ext": ".md",
        "prompt_file": "economics",
    },
    "portfolio-review": {
        "filename_prefix": "portfolio_review",
        "label": "投資組合回顧",
        "ext": ".md",
        "prompt_file": "portfolio",
    },
    "sector-analysis": {
        "filename_prefix": "sector_analysis",
        "label": "產業板塊分析",
        "ext": ".md",
        "prompt_file": "sector",
    },
    "earnings-call-analysis": {
        "filename_prefix": "earnings_call_analysis",
        "label": "財報電話會議分析",
        "ext": ".md",
        "prompt_file": "earnings_call",
    },
    "insider-trading": {
        "filename_prefix": "insider_trading",
        "label": "內部人交易分析",
        "ext": ".md",
        "prompt_file": "insider_trading",
    },
    "institutional-ownership": {
        "filename_prefix": "institutional_ownership",
        "label": "機構持股分析",
        "ext": ".md",
        "prompt_file": "institutional",
    },
    "report-generator": {
        "filename_prefix": "report",
        "label": "綜合HTML投資報告",
        "ext": ".html",
        "prompt_file": "report_generator",
    },
    "financial-report-analyst": {
        "filename_prefix": "financial_report_analyst",
        "label": "財報深度解析",
        "ext": ".md",
        "prompt_file": "financial_report_analyst",
    },
    "stock-valuation": {
        "filename_prefix": "stock_valuation",
        "label": "多方法估值分析",
        "ext": ".md",
        "prompt_file": "stock_valuation",
    },
}

__all__ = ["TODAY", "DEFAULT_MODEL", "DEFAULT_TOKENS", "ANALYSIS_TYPES"]
