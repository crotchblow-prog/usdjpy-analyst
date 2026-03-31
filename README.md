# SMC Pulse

**Smart Money Concepts analysis for forex trading.**

Website: [smcpulse.com](https://smcpulse.com) | Built with [Claude Code](https://claude.ai/code)

> Currently USD/JPY only. Multi-pair support planned.

## What It Does

Three questions the system answers each trading day:

1. **Should I be long or short?** — Modules 01-07 aggregate macro, technical, positioning, and cross-asset signals into a weighted directional bias with confidence level.
2. **Where do I enter?** — Module 08 identifies Smart Money Concepts (order blocks, FVGs, liquidity levels) across 4 timeframes and outputs a graded entry plan.
3. **What are the realistic paths?** — The 12h Playbook projects 3 probability-weighted price scenarios over the next 2 trading sessions with a visual path chart.

Reports are delivered via web dashboard at [smcpulse.com](https://smcpulse.com) (bilingual EN/中文, dark/light theme) with email as backup.

## Architecture

![SMC Pulse Architecture](smcpulse_architecture.png)

External data flows through Claude Code analysis modules, gets pushed to GitHub via Actions cron, then to Supabase (data) and Vercel (dashboard) for delivery.

### Modules

| # | Module | Frequency | Data Source | Purpose |
|---|--------|-----------|-------------|---------|
| 01 | Macro Regime | Daily | FRED, MOF Japan | US/JP rate differential, JGB curve, DXY |
| 02 | Policy & Politics | Weekly | Web search | BOJ/Fed stances, intervention risk, political developments |
| 03 | Technicals | Daily | Yahoo Finance | SMA, RSI, MACD, Ichimoku |
| 04 | Positioning | Weekly | CFTC | COT net speculative position, crowding signal |
| 05 | Cross-Asset | Daily | FRED, Yahoo | Correlations (Nikkei, Gold, VIX, Oil), energy risk |
| 06 | Seasonality | Weekly | Reference data | Seasonal bias, flow events, trade balance |
| 07 | Checklist | Daily | Modules 01-06 | Weighted signal aggregation → direction + confidence |
| 08 | SMC Entry | On-demand | Yahoo Finance | Order blocks, FVGs, entry zones, 12h playbook |
| 09 | Scenario Monitor | Auto | Yahoo Finance | Live check + scorecard |

### Terminology

- **Setup** (A/B/C/D) = market condition classification. Setup A: Intervention Bounce, B: Trend Retracement, C: Liquidity Sweep, D: Tokyo Fix Fade.
- **Scenario** (Primary/Alternative/Tail Risk) = forward-looking playbook projections. These are probability-weighted paths, not structural classifications.

These terms are never mixed in output. "Setup" appears in the entry report. "Scenario" appears only in the 12h Playbook.

## Web Dashboard

Live at [smcpulse.com](https://smcpulse.com)

| Page | Purpose |
|------|---------|
| Dashboard | Hero card, MTF alignment, risk alerts, liquidity levels |
| Reports | Daily + weekly modules with charts (date navigation) |
| SMC Analysis | Entry plan, 12h playbook, scenario paths, active zones |
| Scorecard | Module 09 accuracy tracking, P&L by grade, setup performance |
| Journal | Trade log with report context and performance stats |

Features: auto dark/light theme, English + Traditional Chinese (中文), mobile-responsive, real-time data from Supabase.

### Infrastructure

| Service | Role |
|---------|------|
| Supabase | PostgreSQL database + file storage (Tokyo region) |
| Vercel | Next.js hosting + auto-deploy from GitHub |
| GitHub Actions | Cron automation for report generation + data push |

## Commands

| Command | Description |
|---------|-------------|
| `/usdjpy-daily` | Full daily analysis (Modules 01, 03, 05, 07) + PDF |
| `/usdjpy-weekly` | Full weekly analysis (all Modules 01-07) + PDF |
| `/usdjpy-entry` | Module 08 SMC entry zones + 12h playbook + chart + PDF |
| `/usdjpy-levels` | Quick reference: active zones and liquidity levels only |
| `/usdjpy-fix` | Tokyo Fix Fade check (best at 09:50 JST) |
| `/usdjpy-check` | Pre-trade checklist from cached data (no API calls) |
| `/usdjpy-cot` | Standalone CFTC COT positioning analysis |
| `/usdjpy-cb` | Standalone central bank policy analysis |
| `/usdjpy-monitor` | Module 09 live check against active playbook |
| `/usdjpy-scorecard` | Module 09 post-session accuracy scoring |
| `/usdjpy-journal import` | Import trades from Exness CSV export |
| `/usdjpy-journal sync` | Pull trades from MT5 terminal (Windows only) |
| `/usdjpy-journal open` | Manual trade entry with auto-attached signals |
| `/usdjpy-journal close` | Close trade with pips/R:R calculation |
| `/usdjpy-journal review` | Performance summary and bias alignment analysis |

## Automated Schedule

Reports run via GitHub Actions cron. Data is pushed to Supabase after each run.

| Time (JST) | UTC Cron | Days | Reports |
|------------|----------|------|---------|
| 08:30 | `30 23 * * 0-4` | Mon-Fri | Daily + SMC (+ Weekly on Monday) |
| 14:30 | `30 5 * * 1-5` | Mon-Fri | Module 09 live check (morning SMC) |
| 16:30 | `30 7 * * 1-5` | Mon-Fri | SMC afternoon refresh |
| 20:30 | `30 11 * * 1-5` | Mon-Fri | Module 09 scorecard (morning SMC) |
| 22:30 | `30 13 * * 1-5` | Mon-Fri | Module 09 live check (afternoon SMC) |
| 04:30+1 | `30 19 * * 1-5` | Mon-Fri | Module 09 scorecard (afternoon SMC) |

Manual trigger available via `workflow_dispatch` with report type selector (all/daily/weekly/smc/monitor/scorecard).

## Setup

### Prerequisites

- Python 3.11+
- FRED API key (free at [fred.stlouisfed.org](https://fred.stlouisfed.org))

### Installation

```bash
git clone https://github.com/<user>/usdjpy-analyst.git
cd usdjpy-analyst
pip install -r requirements.txt
cp config.yaml.example config.yaml
# Edit config.yaml: set fred.api_key and supabase.url
```

### GitHub Secrets

| Secret | Purpose |
|--------|---------|
| `FRED_API_KEY` | FRED API access for macro data |
| `GMAIL_APP_PASSWORD` | Gmail App Password for SMTP delivery (backup) |
| `GMAIL_ADDRESS` | Sender/recipient email address |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key for data push |

### First Run

```bash
/usdjpy-daily          # generates daily report + PDF
/usdjpy-entry          # generates SMC entry + playbook chart
```

## Project Structure

```
usdjpy-analyst/
├── CLAUDE.md                          # Claude Code instructions
├── TESTING.md                         # 5-layer validation checklist
├── config.yaml.example                # Template (copy to config.yaml)
├── requirements.txt                   # matplotlib, numpy, pandas, scipy, yfinance, reportlab, supabase
├── setup.sh                           # First-time setup script
├── smcpulse_architecture.png          # Architecture diagram
│
├── scripts/
│   ├── run_smc_analysis.py            # Module 08 orchestrator + playbook + charts
│   ├── smc_engine.py                  # SMC core: swing detection, OBs, FVGs, BOS/ChoCH
│   ├── run_scenario_monitor.py        # Module 09: live check + scorecard
│   ├── push_to_supabase.py            # Supabase data push (reports, scenarios, zones)
│   ├── generate_pdf.py                # PDF renderer (daily, weekly, SMC reports)
│   └── journal.py                     # Trade journal: CSV import, MT5 sync, review
│
├── run_daily_analysis.py              # Daily pipeline (Modules 01, 03, 05, 07)
├── run_cb_analysis.py                 # Module 02: Central bank policy
├── run_cot_analysis.py                # Module 04: CFTC COT positioning
├── send_report.py                     # Email delivery via SMTP (backup)
├── run_daily.sh / run_weekly.sh       # Cron wrappers
│
├── skills/usdjpy/
│   ├── SKILL.md                       # Execution flow and caching rules
│   ├── modules/01-09_*.md             # Module specifications
│   └── templates/                     # Report templates (daily, weekly)
│
├── .claude/commands/
│   ├── usdjpy-monitor.md              # /usdjpy-monitor command
│   └── usdjpy-scorecard.md            # /usdjpy-scorecard command
│
├── data/
│   ├── raw/                           # Cached API responses (gitignored)
│   └── trades/                        # Exness CSV exports for journal import
│
├── output/
│   ├── daily/                         # Daily reports, SMC reports, monitor checks, charts, PDFs
│   ├── weekly/                        # Weekly reports, charts, PDFs
│   ├── scorecard/                     # scenario_log.csv + scorecard reports
│   └── journal/                       # trade_log.csv + individual entries
│
├── dashboard/                         # Next.js web dashboard (smcpulse.com)
│   ├── src/app/                       # Pages: /, /daily, /smc, /scorecard, /journal
│   ├── src/components/                # Shared UI components
│   ├── src/lib/                       # Supabase client, i18n, providers
│   ├── e2e/                           # Playwright E2E tests
│   └── playwright.config.ts           # E2E test config
│
└── .github/workflows/
    └── usdjpy-reports.yml             # Automated report generation + Supabase push
```

## Build Phases

| Phase | Modules | What was built |
|-------|---------|----------------|
| 1 | 01 + 07 | Macro regime (FRED/MOF) + checklist scoring |
| 2 | 03 + 05 | Technicals (SMA/RSI/MACD/Ichimoku) + cross-asset correlations |
| 3 | 02 + 04 | Central bank policy (BOJ/Fed) + CFTC COT positioning |
| 4 | 06 | Seasonality, fiscal year flows, trade balance |
| 5 | 08 | SMC engine, entry zones, 12h playbook, PDF reports, trade journal |
| 6 | 09 | Scenario monitor — live check + scorecard |
| 7 | — | Supabase database + Vercel dashboard (smcpulse.com) |

## Testing

The project uses a 5-layer validation framework documented in [TESTING.md](TESTING.md):

1. **Data Integrity** — APIs return fresh data, files save correctly, charts render
2. **Signal Logic** — Calculations match external sources (TradingView, FRED, barchart.com)
3. **Cross-Module Flow** — Data flows between modules, weekly pipeline includes all 7, cache-only mode works
4. **Edge Cases** — Duplicate runs use cache, weekend handling, API failure resilience
5. **Report Quality** — PDF layout, email delivery, chart readability

Layers 1, 3, and 4 are validated. Layer 2 and 5 are manual spot-checks.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Conviction cap at HIGH requires 4+ modules | Prevents false confidence from thin data (daily runs only 3 of 6 modules) |
| 12h playbook, not 24h | Matches the active trading window — projects the next 2 sessions, not all 3 |
| Setup vs Scenario terminology | Avoids confusion between structural classification (Setup A-D) and forward projections (Primary/Alt/Tail) |
| Nearby zones filtered to 100 pips | Full zone appendix includes 4H+1H only; nearby summary filters by distance for actionability |
| Target deduplication within 5 pips | Prevents cluttered target lists when EQH, round number, and swing high cluster near the same price |
| Primary scenario floor at 35% | Ensures the highest-probability path always reads as primary, even when confidence is low |
| CSV journal import over MT5 direct | MT5 Python package is Windows-only; CSV works on Mac immediately |

## Disclaimer

This is a personal learning project. It generates analysis for educational purposes only. Nothing in this system constitutes financial advice. Trading foreign exchange carries significant risk of loss. Past performance of any analysis methodology does not guarantee future results.
