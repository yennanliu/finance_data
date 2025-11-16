# finance_data

A collection of tools for downloading and managing SEC financial reports.

## Ref

- https://www.annualreports.com/Company/palantir-technologies-inc

## Directory Structure

```
finance_data/
├── 10-k/       # 10-K annual reports
├── 10-q/       # 10-Q quarterly reports
├── 13-f/       # 13-F holdings reports
└── script/     # Download scripts
```

## Scripts

### download_10k.py

Automatically downloads 10-K annual reports from the SEC EDGAR database.

**Installation:**

```bash
pip install requests
```

**Usage:**

```bash
# Download 5 most recent 10-K reports for Apple
python script/download_10k.py AAPL

# Download 10 most recent reports
python script/download_10k.py AAPL -n 10

# Download for multiple companies
python script/download_10k.py AAPL MSFT TSLA

# Specify your email (recommended by SEC)
python script/download_10k.py AAPL -e your.email@example.com
```

**Features:**
- Automatic ticker-to-CIK conversion
- Downloads multiple reports at once
- Rate limiting to respect SEC guidelines
- Files saved as `{TICKER}_{DATE}_10K.html` in the `10-k/` directory

**Arguments:**
- `tickers`: One or more stock ticker symbols (required)
- `-n, --number`: Number of recent reports to download (default: 5)
- `-e, --email`: Your email for SEC User-Agent header (default: user@example.com)

## Notes

- The SEC requires a User-Agent header with contact information
- Rate limiting is built-in (max 10 requests per second)
- Reports are downloaded in HTML format