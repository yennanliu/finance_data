"""
Formatting utilities for financial data display.
"""

from __future__ import annotations


def safe(value, default="N/A"):
    """Return value if valid, else default."""
    if value is None or value == "":
        return default
    return value


def pct(value) -> str:
    """Format value as percentage."""
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def money(value, prefix="$") -> str:
    """Format value as money with magnitude suffix (T/B/M/K)."""
    try:
        v = float(value)
        for mag, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(v) >= mag:
                return f"{prefix}{v / mag:.2f}{suffix}"
        return f"{prefix}{v:.2f}"
    except (TypeError, ValueError):
        return "N/A"


def fmt_price(value) -> str:
    """Format value as price with $ prefix."""
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def df_to_text(df, rows: list[str] | None = None, max_cols: int = 4) -> str:
    """Convert DataFrame to formatted text table."""
    if df is None or df.empty:
        return "  (no data)"
    try:
        cols = list(df.columns[:max_cols])
        col_labels = [str(c)[:10] for c in cols]
        header = f"{'':30}" + "  ".join(f"{lbl:>14}" for lbl in col_labels)
        sep = "-" * len(header)
        lines = [header, sep]
        target = rows if rows else list(df.index)
        for row in target:
            if row in df.index:
                values = [df.loc[row, c] for c in cols]
                fmts = [money(v) for v in values]
                label = str(row)[:28].ljust(30)
                lines.append(label + "  ".join(f"{f:>14}" for f in fmts))
        return "\n".join(lines)
    except Exception as exc:
        return f"  (formatting error: {exc})"


__all__ = ["safe", "pct", "money", "fmt_price", "df_to_text"]
