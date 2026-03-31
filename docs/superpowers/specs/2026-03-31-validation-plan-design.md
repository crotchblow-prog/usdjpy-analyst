# Validation Plan Design — USD/JPY Analyst

**Date:** 2026-03-31
**Status:** Approved
**Goal:** Validate every module's calculated values by cross-referencing against multiple external sources, surfaced on the dashboard.

## Problem

Reports generate daily but there's no automated way to know if the calculated values (RSI, SMA, MACD, correlations, scoring, etc.) are accurate. Manual cross-referencing is time-consuming and inconsistent.

## Approach

**Scheduled Independent Validator (Approach C)** — a separate CI job that runs 30 minutes after each report. It reads our report data from Supabase, independently fetches the same indicators from external sources, compares with configurable tolerances, and pushes validation results to Supabase. A new dashboard page shows pass/fail per indicator per source.

## What Gets Validated

| Module | Indicators | External Sources | Tolerance |
|--------|-----------|-----------------|-----------|
| 01 Macro | US-JP rate spread, DXY level | FRED (direct), Investing.com | ±0.05% |
| 03 Technicals | RSI(14), SMA(50/200), MACD, Ichimoku cloud | TradingView, Yahoo Finance, Investing.com | RSI ±2pts, SMA ±0.05 yen, MACD signal ±0.02 yen |
| 05 Cross-Asset | Nikkei/Gold/VIX/SPX correlations, spot prices | Yahoo Finance (2nd fetch), Investing.com | Spot ±0.1%, Correlation ±0.05 |
| 07 Checklist | Weighted score, directional bias | Internal consistency — inputs match 01/03/05 outputs | Exact match |
| 08 SMC | Swing points, order block levels, FVG zones | TradingView, Yahoo Finance (price verification) | Price levels ±0.10 |

## Architecture

```
CI Schedule (30min after report)
    |
    v
scripts/run_validation.py
    |
    +-- 1. Read report data from Supabase (what we calculated)
    |
    +-- 2. Fetch reference values from external sources
    |   +-- Yahoo Finance (yfinance) -- prices, technicals
    |   +-- Investing.com (web scrape) -- RSI, SMA, DXY
    |   +-- TradingView (web scrape) -- technicals, SMC levels
    |
    +-- 3. Compare with tolerances from config.yaml
    |
    +-- 4. Push results to Supabase `validation` table
    |
    +-- 5. Print summary to stdout (for CI logs)
```

### Supabase Table: `validation`

| Column | Type | Description |
|--------|------|-------------|
| id | uuid (PK) | Auto-generated |
| report_id | uuid (FK, nullable) | Links to reports table |
| date | date | Report date |
| module | text | Module identifier (01, 03, 05, 07, 08) |
| indicator | text | e.g., "rsi_14", "sma_200", "dxy" |
| our_value | numeric | Value from our report |
| source_name | text | e.g., "yahoo", "tradingview", "investing" |
| source_value | numeric | Value from external source |
| tolerance | numeric | Configured tolerance |
| diff | numeric | Absolute difference |
| status | text | PASS / WARN / FAIL / SKIP |
| checked_at | timestamptz | When validation ran |

### Status Logic

- **PASS** — diff within tolerance
- **WARN** — diff is 1-2x tolerance (might be timing)
- **FAIL** — diff exceeds 2x tolerance
- **SKIP** — all sources unavailable for this indicator

## External Source Strategy

### Yahoo Finance (yfinance)
- Already a dependency
- Fetches: spot prices, historical OHLC for SMA/RSI/MACD recalculation
- No Ichimoku built-in — recalculate from raw OHLC

### Investing.com (web scrape via requests + BeautifulSoup)
- Fetches: RSI, SMA, DXY, Nikkei, Gold spot
- Risk: page structure can change
- Mitigation: try/except, mark source as "unavailable" if scrape fails

### TradingView (web scrape or unofficial API)
- Fetches: technicals summary (RSI, MACD, SMA), price levels
- Risk: anti-bot measures, rate limiting
- Mitigation: fail gracefully, skip source

### Fallback Rule
Validation requires at least 1 external source per indicator to produce a result. If all sources fail, status = SKIP (not FAIL). Broken scrapers never flood false alarms.

## Config

```yaml
validation:
  enabled: true
  tolerances:
    rsi: 2.0
    sma: 0.05
    macd: 0.02
    spot_pct: 0.001    # 0.1%
    correlation: 0.05
  sources:
    yahoo: true
    investing: true
    tradingview: true
```

## CI Integration

Two new scheduled runs, 30 minutes after each report:

| Existing Run | Time (JST) | Validation Run | Time (JST) | Cron (UTC) |
|-------------|------------|----------------|------------|------------|
| Morning report | 08:30 | Validate morning | 09:00 | `0 0 * * 1-5` |
| Afternoon SMC | 16:30 | Validate afternoon | 17:00 | `0 8 * * 1-5` |

Workflow step:
```yaml
- name: Run Validation
  if: steps.run-type.outputs.validation == 'true'
  env:
    SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
  run: |
    python scripts/run_validation.py
```

Behavior:
- Reads most recent report from Supabase for today's date
- If no report found, logs warning and exits cleanly
- `continue-on-error: true` — validation never blocks the pipeline
- Results pushed to Supabase and visible in CI summary

## Dashboard Page: `/validation`

### 1. Summary Card (top)
- Large pass rate: "42/45 PASS" with color (green >90%, yellow >75%, red <75%)
- Last validated timestamp
- Date picker to view historical validation

### 2. Module Breakdown (middle)
- One row per module (01, 03, 05, 07, 08)
- Each shows: module name, checks passed/total, status badge (PASS/WARN/FAIL)
- Click to expand and see individual indicators

### 3. Indicator Detail (expanded)
- Table: indicator name, our value, source, source value, diff, tolerance, status
- Example: `RSI(14) | 62.3 | Yahoo | 63.1 | 0.8 | +/-2.0 | PASS`
- FAIL rows highlighted in red, WARN in yellow

### Navigation
Add "Validation" to the sidebar nav, between "Scorecard" and "Journal".

## Out of Scope

- Python unit tests (separate effort)
- Type checking / linting
- Performance benchmarking
- Module 02/04/06 validation (qualitative data, not numeric)
