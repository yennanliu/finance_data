"""Chart-rendering layer: interactive Plotly candlestick + PNG (kaleido,
with an mplfinance fallback). Heavy deps are imported lazily inside fns.
"""

from __future__ import annotations

from ..config import TODAY


def generate_plotly_candlestick_chart(hist, ticker: str, output_dir: str = None) -> dict:
    """Generate both PNG and interactive Plotly candlestick chart with MA(30,60,200).

    Args:
        hist: OHLCV DataFrame from yfinance (must have OHLCV columns)
        ticker: Stock ticker symbol
        output_dir: Directory to save PNG chart (optional)

    Returns:
        Dict with keys:
          - 'plotly_html': HTML embed code (or empty string)
          - 'png_filename': PNG filename relative to output_dir (or None)
    """
    if hist is None or hist.empty or len(hist) < 60:
        return {"plotly_html": "", "png_filename": None}

    result = {"plotly_html": "", "png_filename": None}

    try:
        import plotly.graph_objects as go
        import pandas as pd
        from pathlib import Path

        # Use last 200 trading days for good chart visibility. The Plotly
        # candlestick uses only OHLC + computed MAs, so Volume is not required
        # (some indices/funds/forex tickers lack it).
        df = hist[["Open", "High", "Low", "Close"]].tail(200).copy()

        # Calculate MAs
        df["MA30"] = df["Close"].rolling(window=30).mean()
        df["MA60"] = df["Close"].rolling(window=60).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()

        # Create candlestick figure
        fig = go.Figure()

        # Add candlestick chart
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name="價格",
                hovertemplate=(
                    "<b>%{x|%Y-%m-%d}</b><br>"
                    "開: $%{open:.2f}<br>"
                    "高: $%{high:.2f}<br>"
                    "低: $%{low:.2f}<br>"
                    "收: $%{close:.2f}<extra></extra>"
                ),
            )
        )

        # Add MA lines with custom colors
        ma_config = [
            ("MA30", "#2196F3", "dash"),
            ("MA60", "#9C27B0", "dash"),
            ("MA200", "#FF6F00", "solid"),
        ]

        for ma_col, color, dash in ma_config:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df[ma_col],
                    mode="lines",
                    name=ma_col,
                    line=dict(color=color, width=2, dash=dash),
                    hovertemplate=f"{ma_col}: $%{{y:.2f}}<extra></extra>",
                )
            )

        # Update layout
        fig.update_layout(
            title=f"{ticker}  |  MA(30/60/200)  |  最近200交易日",
            yaxis_title="股價 (USD)",
            xaxis_title="日期",
            hovermode="x unified",
            template="plotly_dark",
            height=500,
            xaxis_rangeslider_visible=False,
            font=dict(size=11),
        )

        # Generate Plotly HTML
        try:
            result["plotly_html"] = fig.to_html(include_plotlyjs="cdn", div_id="candlestick-chart")
        except Exception as e:
            print(f"  ⚠ Plotly HTML generation failed: {e}")

        # Generate PNG if output_dir provided
        if output_dir:
            try:
                from pathlib import Path
                output_path = Path(output_dir) / f"technical_chart_{TODAY}.png"
                fig.write_image(str(output_path), width=1200, height=600)
                result["png_filename"] = output_path.name
                print(f"  ✓ PNG chart saved: {output_path.name}")
            except Exception as e:
                print(f"  ⚠ PNG generation failed (kaleido may not be installed): {e}")
                # Fallback to mplfinance if kaleido not available
                try:
                    result["png_filename"] = _generate_mplfinance_chart(df, ticker, output_path)
                except Exception as e2:
                    print(f"  ⚠ Fallback PNG generation also failed: {e2}")

        return result

    except ImportError:
        print(f"  ⚠ plotly not installed, skipping interactive chart generation")
        return {"plotly_html": "", "png_filename": None}
    except Exception as e:
        print(f"  ⚠ Chart generation failed: {e}")
        return {"plotly_html": "", "png_filename": None}


def _generate_mplfinance_chart(df, ticker: str, output_path) -> str:
    """Fallback PNG generation using mplfinance (for when kaleido unavailable)."""
    import mplfinance as mpf
    import matplotlib
    matplotlib.use("Agg")

    # Select OHLCV columns, only including Volume if it exists
    cols_to_select = ["Open", "High", "Low", "Close"]
    if "Volume" in df.columns:
        cols_to_select.append("Volume")

    chart_df = df[cols_to_select].copy()

    # Include volume only if available
    include_volume = "Volume" in chart_df.columns

    style = mpf.make_mpf_style(base_mpf_style="charles")
    fig, axes = mpf.plot(
        chart_df,
        type="candle",
        mav=(30, 60, 200),
        volume=include_volume,
        style=style,
        title=f"{ticker}  |  MA(30/60/200)  |  最近200交易日",
        figsize=(12, 7),
        returnfig=True,
    )

    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)

    return output_path.name


def generate_candlestick_chart(hist, ticker: str, output_path: str) -> str:
    """Generate a candlestick chart with MA(30,60,200) overlays and save as PNG.

    Args:
        hist: OHLCV DataFrame from yfinance (must have OHLCV columns)
        ticker: Stock ticker symbol
        output_path: File path where PNG will be saved

    Returns:
        output_path if successful, empty string on failure
    """
    if hist is None or hist.empty or len(hist) < 60:
        return ""

    try:
        import mplfinance as mpf
        import matplotlib
        import matplotlib.patches as mpatches
        matplotlib.use("Agg")  # headless backend, no display

        # Use last 200 trading days for good chart visibility. Include Volume
        # only if the ticker actually has it (indices/funds/forex may not).
        cols = ["Open", "High", "Low", "Close"]
        if "Volume" in hist.columns:
            cols.append("Volume")
        df = hist[cols].tail(200).copy()

        # Define MA periods and colors
        ma_config = [(30, "#2196F3"), (60, "#9C27B0"), (200, "#212121")]

        # Build MA list based on available data
        mavs = []
        ma_colors = []
        legend_labels = []
        for period, color in ma_config:
            if len(df) >= period:
                mavs.append(period)
                ma_colors.append(color)
                legend_labels.append(f"MA{period}")

        if not mavs:
            return ""

        # Create custom style
        style = mpf.make_mpf_style(
            base_mpf_style="charles",
            rc={
                "axes.labelsize": 9,
                "xtick.labelsize": 8,
                "ytick.labelsize": 8,
                "legend.fontsize": 10,
            },
        )

        # Generate the chart with returnfig to add custom legend
        fig, axes = mpf.plot(
            df,
            type="candle",
            mav=tuple(mavs),
            volume="Volume" in df.columns,
            style=style,
            mavcolors=ma_colors,
            title=f"{ticker}  |  MA{mavs}  |  最近200交易日",
            figsize=(12, 7),
            returnfig=True,
        )

        # Add custom legend with MA labels
        legend_patches = [
            mpatches.Patch(facecolor=color, label=label)
            for label, color in zip(legend_labels, ma_colors)
        ]
        axes[0].legend(
            handles=legend_patches,
            loc="upper left",
            frameon=True,
            fancybox=True,
            shadow=True,
            fontsize=10,
        )

        # Save the figure
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt
        plt.close(fig)

        return output_path
    except ImportError:
        print(f"  ⚠ mplfinance not installed, skipping chart generation")
        return ""
    except Exception as e:
        print(f"  ⚠ Chart generation failed: {e}")
        return ""
