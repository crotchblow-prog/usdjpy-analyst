skill: USD/JPY Analyst

## Purpose
Analyze USD/JPY trends using a 7-module framework covering macro (with JGB curve + DXY), policy & politics, technicals, positioning (with institutional flow), cross-asset correlations (with energy risk), seasonality (with trade balance), and trade decision-making.

## Module Index

| Module | Name | Cadence | Data Source |
|--------|------|---------|-------------|
| 01 | Macro Regime | Daily | FRED API, MOF Japan, Yahoo Finance (DXY) |
| 02 | Policy & Politics | Weekly | BOJ/Fed websites, web search (political) |
| 03 | Technicals | Daily | Yahoo Finance / FRED |
| 04 | Positioning (COT) | Weekly | CFTC website, web search (flow context) |
| 05 | Cross-Asset Correlations | Daily | FRED / Yahoo Finance |
| 06 | Seasonality & Flows | Weekly | Static reference + calendar, web search (trade balance) |
| 07 | Pre-Trade Checklist | Daily | Aggregates Modules 01-06 |
| 08 | Smart Money Concepts | On-demand | Yahoo Finance (intraday) | **IMPLEMENTED** |
| 09 | Scenario Monitor | Post-SMC | Yahoo Finance (5M) + SMC report | **IMPLEMENTED** |

## Execution Flow

### Daily (/usdjpy-daily)
1. Read `config.yaml` for API keys and thresholds
2. Run Module 01 → save data + compute signals
3. Run Module 03 → save data + compute signals
4. Run Module 05 → save data + compute signals
5. Run Module 07 → aggregate all available signals into checklist
6. Generate report markdown + charts → save to `./output/daily/`

### Weekly (/usdjpy-weekly)
1. Read `config.yaml`
2. Run ALL modules (01 through 06) in order
3. Run Module 07 with full signal set
4. Generate comprehensive weekly report → save to `./output/weekly/`

## Data Caching Rules
- Before any API call, check `./data/raw/` for today's data
- FRED data: cache valid for 24 hours
- Price data (Yahoo): cache valid for 4 hours on trading days
- COT data: cache valid for 7 days (released weekly on Friday)
- Central bank statements: cache valid until next meeting date

## Report Format
All reports are markdown with embedded chart references. Structure:

```markdown
# USD/JPY Analysis — {date}

## Executive Summary
{2-3 sentence overall bias with confidence level}

## Module Details
{Each module's output as a subsection}

## Checklist Grid
{Module 07 output — the decision table}

## Charts
{Inline PNG references}
```

## Module File Locations
Each module file at `./skills/usdjpy/modules/XX_name.md` contains:
- **Data sources**: Exact API endpoints and parameters
- **Calculations**: Step-by-step formulas and logic
- **Signal rules**: How to interpret the output
- **Output format**: What to include in the report section
