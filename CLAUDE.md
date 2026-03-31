# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# USD/JPY Analysis Workstation

## Project Overview
This is a personal USD/JPY trend analysis system. It fetches macro, technical, positioning, and cross-asset data, then synthesizes it into actionable daily and weekly reports.

All analysis runs inside Claude Code — no external scripts or scheduling needed. Just type the command and get the report.

## Setup (first time only)

```bash
bash setup.sh          # creates dirs, checks deps, prompts for FRED key + email
pip install pyyaml     # required for send_report.py
pip install yfinance   # required for /usdjpy-entry (Module 08)
pip install matplotlib pandas numpy scipy
pip install supabase   # required for web dashboard data push
```

Environment variables (add to `~/.zshrc`):
```bash
export USDJPY_EMAIL_PASSWORD="your_namecheap_smtp_password"
export SUPABASE_SERVICE_ROLE_KEY="your_supabase_service_role_key"
```

After setup, update `config.yaml`: set `fred.api_key` (free at fred.stlouisfed.org), `email.to_address`, and `supabase.url`.

## Commands

### /usdjpy-daily
Run a daily analysis covering:
- Economic Calendar: Web search for next-24h HIGH/MED impact events (US + Japan)
- Session Context: Prev day H/L/C, Asian session range, pivot/R1/S1 levels
- Module 01 (Macro Regime): Fetch US/JP rate differential, JGB curve (2s10s, 2s30s), DXY context
- Module 03 (Technicals): Fetch USD/JPY price data, calculate SMA, RSI, MACD, Ichimoku
- Module 05 (Cross-Asset): Fetch correlated assets (S&P 500, Nikkei, Gold, VIX, Oil), compute rolling correlations + energy risk
- Module 07 (Checklist): Aggregate all signals into a go/no-go grid

Output: Save report to `./output/daily/YYYY-MM-DD.md` with inline PNG charts, plus a PDF version (`YYYY-MM-DD.pdf`) with embedded charts.

### /usdjpy-weekly
Run a full weekly analysis covering ALL modules (01-07):
- Everything in /usdjpy-daily, plus:
- Module 02 (Policy & Politics): Run `python3 run_cb_analysis.py` for BOJ/Fed stances, intervention risk + Japanese political developments
- Module 04 (Positioning): Run `python3 run_cot_analysis.py` to fetch CFTC COT JPY futures data + institutional flow context
- Module 06 (Seasonality): Check current seasonal bias, upcoming flow events + Japan trade balance

Output: Save report to `./output/weekly/YYYY-MM-DD.md` with charts.

### /usdjpy-cot
Run Module 04 (Positioning) standalone:
- Fetches latest CFTC Commitments of Traders data for JPY futures (contract 097741)
- Computes net speculative position, week-over-week change, percentile rank
- Flags crowding (>85th or <15th percentile) with contrarian signal
- Cache: `./data/raw/cot_YYYY-MM-DD.json` (7-day validity)

Run: `python3 run_cot_analysis.py`

### /usdjpy-cb
Run Module 02 (Policy & Politics) standalone:
- BOJ: current rate, stance, last/next meeting, key quote
- Fed: current rate, stance, last/next meeting, dot plot summary
- MOF intervention risk: rhetoric level, last intervention, risk assessment
- Japanese political developments (fiscal policy, elections, Diet)
- Policy divergence signal with contrarian interpretation
- Cache: `./data/raw/central_bank_YYYY-MM-DD.json` (valid until next meeting)

Run: `python3 run_cb_analysis.py`

### /usdjpy-check
Quick pre-trade checklist only. Run Module 07 using the most recent data in `./data/`. 
Do NOT fetch new data — just read what's already there and produce the checklist.
If no recent data exists, tell the user to run /usdjpy-daily first.

### /usdjpy-entry
Run Module 08 (Smart Money Concepts) for tactical entry/exit analysis:
- Reads directional bias from the most recent Module 07 checklist
- Fetches intraday data from Yahoo Finance (4H, 1H, 15M, 5M)
- Identifies market structure, order blocks, FVGs, liquidity levels
- Classifies scenario (A: Intervention Bounce, B: Trend Retracement, C: Liquidity Sweep, D: Tokyo Fix Fade)
- Outputs entry zone, stop loss, targets, and confluence score
- If Module 07 bias is NEUTRAL, warn before proceeding

Run: `python3 scripts/run_smc_analysis.py --mode full`
Output: Save to `./output/daily/smc_YYYY-MM-DD.md` + chart + PDF

Requires: `pip install yfinance` (install on first run if not present)

### /usdjpy-levels
Quick reference: Active zones and liquidity levels only (no chart or PDF).
Run: `python3 scripts/run_smc_analysis.py --mode levels`
Output: `./output/daily/smc_levels_YYYY-MM-DD.md`

### /usdjpy-fix
Quick Scenario D check — Tokyo Fix Fade. Best run at 09:50-10:00 JST.
Run: `python3 scripts/run_smc_analysis.py --mode fix`
Output: `./output/daily/smc_fix_YYYY-MM-DD.md`

### /usdjpy-monitor
Run Module 09 live check — which playbook scenario is currently unfolding?
Reads the most recent SMC report, fetches 5M data since generation, and compares against the 3 scenarios.
Run: `python3 scripts/run_scenario_monitor.py --mode check`
Output: `./output/daily/monitor_YYYY-MM-DD.md`

### /usdjpy-scorecard
Run Module 09 scorecard — score each scenario after the 12h playbook window closes.
Logs results to `./output/scorecard/scenario_log.csv` and prints running stats after 10+ entries.
Run: `python3 scripts/run_scenario_monitor.py --mode scorecard`
Output: `./output/scorecard/scorecard_YYYY-MM-DD.md`

### /usdjpy-journal import
Import trades from Exness CSV export files in `./data/trades/`.
- Parses Exness MT5 CSV format (auto-detects delimiter and column names)
- Filters for USDJPY trades only
- Auto-matches with Module 07 bias and Module 08 SMC data from the trade date
- Skips duplicate ticket numbers
- Appends to `./output/journal/trade_log.csv`
- Creates individual markdown entries in `./output/journal/`

Run: `python3 scripts/journal.py import`

CSV Drop Workflow: Export from Exness PA → Trading tab → History of orders → Download CSV → save to `./data/trades/`

### /usdjpy-journal sync
Pull trades directly from MT5 terminal (Windows only — requires `pip install MetaTrader5`).
On Mac, falls back to CSV import with instructions.

Run: `python3 scripts/journal.py sync`

### /usdjpy-journal open
Manual journal entry for a planned or active trade.
Auto-attaches current Module 07 + Module 08 signals.

Run: `python3 scripts/journal.py open LONG 159.36 159.22 160.00 --lots 0.01 --note "OB entry"`

### /usdjpy-journal close
Close an open journal entry. Calculates pips, actual R:R, duration.

Run: `python3 scripts/journal.py close <ticket> <exit_price> --grade B --reason "Hit T1"`

### /usdjpy-journal review
Performance summary: win rate, avg P&L, avg R:R, performance by setup type,
bias alignment, day of week, current streak, self-assessment grades.

Run: `python3 scripts/journal.py review`

## Architecture

### Module pipeline

```
config.yaml  →  skill files  →  API fetch  →  ./data/raw/  →  calculations  →  ./output/
```

Each slash command maps to a set of modules defined in `./skills/usdjpy/modules/`. The modules are processed in order; Module 07 always runs last and aggregates the others into the checklist grid. Module 08 is standalone, triggered only by `/usdjpy-entry`.

### Skill file structure

```
./skills/usdjpy/
  SKILL.md                  # execution flow, data caching rules, report format
  templates/
    daily_report.md         # daily report template (calendar, session, 01/03/05/07)
    weekly_report.md        # weekly report template (all modules + extras)
  modules/
    01_macro.md             # rate differential + JGB curve + DXY (daily)
    02_central_bank.md      # policy & politics: BOJ/Fed + political risk (weekly)
    03_technicals.md        # SMA/RSI/MACD/Ichimoku (daily)
    04_positioning.md       # CFTC COT + institutional flow context (weekly)
    05_cross_asset.md       # correlations + energy risk signal (daily)
    06_seasonality.md       # seasonal bias + flow events + trade balance (weekly)
    07_checklist.md         # signal aggregation + weighted scoring (daily)
    08_smc_entry.md         # SMC entry zones via yfinance intraday (on-demand)
```

Each module file specifies: exact API endpoints + parameters, calculation formulas, signal interpretation rules, and the markdown output format for its report section.

### Data cache naming

Raw API responses are saved as: `./data/raw/{SOURCE}_{SERIES}_{YYYY-MM-DD}.json`

Cache validity: FRED = 24h, Yahoo Finance price = 4h, COT = 7 days, central bank statements = until next meeting.

### Trade journal data

```
./data/trades/           ← Drop Exness CSV exports here
./output/journal/
  ├── trade_log.csv      ← Master trade log (append-only)
  ├── YYYY-MM-DD_<ticket>_open.md    ← Individual open entries
  └── YYYY-MM-DD_<ticket>_closed.md  ← Individual closed entries
```

### Automated runners (for cron)

`run_daily.sh` and `run_weekly.sh` call `claude -p .` with a non-interactive prompt, then call `send_report.py` to email the output. Cron schedule (JST = UTC+9):
```
0 10 * * 1-5  ~/usdjpy-analyst/run_daily.sh  >> ~/usdjpy-analyst/logs/cron.log 2>&1
0 10 * * 5    ~/usdjpy-analyst/run_weekly.sh >> ~/usdjpy-analyst/logs/cron.log 2>&1
```

### Email delivery

`send_report.py` reads SMTP config from `config.yaml` (`email.*`) and the password from `$USDJPY_EMAIL_PASSWORD`. It sends the markdown body as plain text + attaches the `.md` file and any same-day PNG charts.

```bash
python3 send_report.py ./output/daily/2026-03-29.md [chart.png ...]
```

### Supabase (web dashboard)

`scripts/push_to_supabase.py` pushes report data to Supabase for the web dashboard. It's integrated into:
- `scripts/run_smc_analysis.py` — pushes SMC report + scenarios + zones + liquidity levels
- `scripts/run_scenario_monitor.py` — pushes scorecard results
- `scripts/journal.py` — pushes journal entries

All pushes are wrapped in try/except so Supabase failures never block report generation.

Tables: `reports`, `scenarios`, `scorecard`, `zones`, `liquidity_levels`, `journal_entries`. Upsert on `(date, report_type)` prevents duplicates.

Standalone usage:
```bash
python3 scripts/push_to_supabase.py output/daily/smc_2026-03-31.md
```

## Execution Rules

1. **Read the skill files first.** Before executing any command, read `./skills/usdjpy/SKILL.md` and the relevant module files. They contain the exact data sources, calculation methods, and output formats.

2. **Use config.yaml for all settings.** API keys, series IDs, thresholds, and preferences live in `./config.yaml`. Never hardcode these values.

3. **Save raw data.** After fetching from any API, save the raw JSON response to `./data/raw/SOURCE_SERIES_YYYY-MM-DD.json`. This builds a local history and avoids redundant fetches.

4. **Check for recent data before fetching.** If data for today already exists in `./data/raw/`, skip the fetch and use cached data. FRED data updates once daily, COT data weekly — no need to hit APIs multiple times per day.

5. **Charts.** Generate matplotlib charts as PNG files. Save them alongside the report in the output folder and reference them in the markdown report with relative paths.

6. **PDF generation.** When generating PDF reports, ALWAYS use `python3 scripts/generate_pdf.py <markdown_file>`. Do NOT write a new PDF generation script. If the script needs modifications, edit the existing file. The script auto-detects daily vs weekly from the file path, or accepts `--type daily|weekly`.

7. **Error handling.** If an API is unreachable or returns an error, note it in the report and continue with available data. Never let one failed module block the entire report.

8. **Timezone.** All timestamps in JST (Asia/Tokyo). The user runs this from Okinawa.
