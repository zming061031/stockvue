# StockVue - Automated Daily Stock Analysis

ICT/SMC-based stock screening with automated daily reports.

## Features
- **Markets**: HK (yfinance), US (yfinance), A-Share (akshare + Sina fallback)
- **ICT/SMC Framework**: BOS, CHoCH, MSS, FVG, Order Blocks, Liquidity Sweeps
- **Fibonacci Zones**: DISCOUNT (<0.786), PREMIUM (>0.618), NEUTRAL
- **Confluence Scoring**: Multiple confirmations combined into 0-100 score
- **Win Rate Display**: Threshold 70% (configurable)

## Setup GitHub Actions (Manual)

1. **Create a new GitHub repo** named `stockvue`
2. **Push this code**:
   ```bash
   git init
   git add .
   git commit -m "Initial StockVue code"
   git remote add origin https://github.com/YOUR_GITHUB/stockvue.git
   git push -u origin master
   ```
3. **Enable GitHub Pages**: Repo Settings → Pages → Source: "Deploy from a branch" → branch: `gh-pages`
4. **Trigger workflow**: Go to Actions tab → "Daily Stock Report" → Run workflow
5. **Set schedule** (optional): Edit `.github/workflows/daily-report.yml` → change `cron: '40 * * * *'` to desired schedule

## Local Setup

```bash
pip install akshare yfinance requests pyyaml tenacity rich
python daily_runner.py
```

## Configuration

Edit `config.yaml` to adjust:
- `display_win_rate_min`: Minimum win rate to display (default: 70)
- `technical_filters`: RSI range, volume ratio range, MA requirements
- `screening`: Min change %, max results per market
- `risk_management`: Max trades, stop loss %, take profit ratios

## Output Files
- `dashboard.html` - HTML dashboard
- `reports/latest_report.txt` - Markdown report
- `stockvue.log` - Log file