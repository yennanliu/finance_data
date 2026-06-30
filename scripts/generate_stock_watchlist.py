"""
Generate a daily watchlist of 30 under-the-radar US stocks with strong fundamental
growth potential. Avoids hyped/top-market-cap names and focuses on value + growth.

Output: ws/yyyy_mm_<seq>_open.txt
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analysis.llm import run_openai

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a seasoned fundamental equity analyst specializing in identifying \
under-the-radar US stocks with strong long-term growth potential. \
You focus on companies that are NOT in the S&P 500 top-50 by market cap, \
NOT commonly featured in mainstream financial media hot lists, \
and NOT meme/momentum stocks. Your mandate is patient, value-oriented, \
long-term fundamental investing."""

USER_PROMPT = """\
Today is {today}.

Generate a ranked watchlist of exactly 30 US-listed stocks that meet ALL criteria:
1. NOT a mega-cap (avoid AAPL, MSFT, NVDA, AMZN, GOOG, META, TSLA, BRK, JPM, V, etc.)
2. NOT currently a market media darling or trending/viral stock
3. Strong fundamental growth drivers: revenue growth, EPS trajectory, expanding margins, or compelling P/E relative to growth (PEG < 1.5 preferred)
4. Solid balance sheet: manageable debt, positive free cash flow or clear path to it
5. Identifiable competitive moat or structural tailwind (sector, regulation, demographics, technology shift)
6. Market cap ideally $500M–$50B (small/mid cap sweet spot)

For each stock output EXACTLY this format (no markdown tables, plain text):

---
Rank: <N>
Ticker: <TICKER>
Company: <Full Company Name>
Sector: <Sector>
Market Cap: ~$<X>B
Key Metrics (estimated):
  - Revenue Growth (YoY): <X>%
  - EPS Growth (forward): <X>%
  - P/E (fwd): <X>x  |  PEG: <X>
  - Debt/Equity: <X>
  - FCF Yield: <X>%
Investment Thesis:
  <2-4 sentences explaining the core growth driver, moat, and why this is overlooked>
Key Risk:
  <1-2 sentences on the primary downside risk>
---

After the 30 stocks, add a section:

== SELECTION METHODOLOGY ==
<Brief paragraph on the screening logic used: what criteria filtered out hot stocks, \
how you weighted growth vs. value, and what macro/sector themes informed the picks>
"""


# ── Output path ───────────────────────────────────────────────────────────────

def _output_path() -> Path:
    """Return ws/yyyy_mm_<next_seq>_open.txt, creating the dir if needed."""
    ws = Path(__file__).parent.parent / "ws"
    ws.mkdir(exist_ok=True)

    now = datetime.utcnow()
    prefix = now.strftime("%Y_%m")

    # Find the next available sequence number for today's date
    existing = sorted(ws.glob(f"{prefix}_*_open.txt"))
    seq = len(existing) + 1

    return ws / f"{prefix}_{seq:03d}_open.txt"


# ── OpenAI call ───────────────────────────────────────────────────────────────

def generate_watchlist(model: str = "gpt-4o", max_tokens: int = 8000) -> str:
    # Preserve the original clean-exit UX on a missing key (vs. a raised LLMError).
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("ERROR: OPENAI_API_KEY environment variable is not set.")

    today = datetime.utcnow().strftime("%Y-%m-%d")
    print(f"Calling {model} to generate watchlist for {today}…")

    # Reuse the shared OpenAI runner: watchlist uses temp=0.4, 3 rate-limit
    # retries, no per-model token cap, and no refusal escalation.
    return run_openai(
        "", USER_PROMPT.format(today=today), SYSTEM_PROMPT,
        model=model, max_tokens=max_tokens, temperature=0.4,
        max_retries=3, refusal_retry=False, cap_tokens=False,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate fundamental stock watchlist")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--max-tokens", type=int, default=8000)
    args = parser.parse_args()

    content = generate_watchlist(model=args.model, max_tokens=args.max_tokens)

    out = _output_path()
    header = (
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Model: {args.model}\n"
        f"Purpose: Fundamental long-term US stock watchlist (under-the-radar)\n"
        + "=" * 70 + "\n\n"
    )
    out.write_text(header + content, encoding="utf-8")
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
