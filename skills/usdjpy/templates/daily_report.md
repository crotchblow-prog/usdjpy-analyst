# USD/JPY Daily Report Template

> **This is the exact format to follow when generating daily reports.**
> Daily reports include Modules 01, 03, 05, and 07. Modules 02, 04, and 06
> use the most recent weekly data if available (shown in checklist only).
> Save output to `./output/daily/YYYY-MM-DD.md`

---

```markdown
# USD/JPY Daily Analysis — {YYYY-MM-DD}

> **{BULLISH / BEARISH / NEUTRAL}** | Conviction: **{HIGH / MEDIUM / LOW}** | Score: **{+X}/{max}** | Modules: **{X}/6**

---

## At a Glance

| | Value | 1W | 1M | 3M | Signal |
|---|---|---|---|---|---|
| USD/JPY | {XXX.XX} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| US 10Y | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| JP 10Y | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| Spread | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | {WIDENING/NARROWING/STABLE} |
| RSI (14) | {XX.X} | — | — | — | {OB/OS/NEUTRAL} |

> {2 sentences: what's the setup today and what changed since yesterday.}

---

## Risk Alerts

| Alert | Status | Detail |
|---|---|---|
| BOJ Intervention | {CRITICAL / ELEVATED / LOW} | USD/JPY at {XXX.XX}, {+X.XX} yen in 30d |
| Event Risk (48h) | {YES / NO} | {Event name, date} |
| COT Crowding | {YES / NO / N/A} | {Percentile or "Weekly data pending"} |
| Correlation Breakdown | {YES / NO} | {Which asset(s) or "All normal"} |

---

## Economic Calendar (next 24h)

| Time (JST) | Event | Expected | Previous | Impact |
|---|---|---|---|---|
| {HH:MM} | {event name} | {consensus} | {prior} | {HIGH/MED} |
| {HH:MM} | {event name} | {consensus} | {prior} | {HIGH/MED} |

> Use web search to find today's and tomorrow's key economic releases for US and Japan.
> Only include HIGH and MEDIUM impact events.
> If no events, write: "No high-impact releases in next 24h."
>
> Priority events to always include if scheduled:
> - US: NFP, CPI, PPI, Retail Sales, FOMC minutes, Fed speeches
> - Japan: Tokyo CPI, National CPI, Tankan, GDP, Trade Balance, BOJ speeches
> - Other: China PMI (affects risk sentiment), ECB decisions

---

## Today's Session Context

**Prev Day:** H {XXX.XX} | L {XXX.XX} | C {XXX.XX}
**Asian Session:** H {XXX.XX} | L {XXX.XX}
**Pivot:** {XXX.XX} | R1: {XXX.XX} | S1: {XXX.XX}
**Session Note:** {1 sentence — what happened overnight and what's the setup}

> Fetch intraday data from Yahoo Finance (`USDJPY=X`, interval=1h or 15m, period=2d).
> Calculate pivot levels:
>   PP = (prev_day_H + prev_day_L + prev_day_C) / 3
>   R1 = 2 * PP - prev_day_L
>   S1 = 2 * PP - prev_day_H
> Asian session = 00:00–09:00 JST today (if data available).

---

## 01 — Macro Regime

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L}

| Metric | Current | 1W Chg | 1M Chg | 3M Chg |
|--------|---------|--------|--------|--------|
| US 10Y | X.XX% | +X.XX | +X.XX | +X.XX |
| JP 10Y | X.XX% | +X.XX | +X.XX | +X.XX |
| Spread | X.XX% | +X.XX | +X.XX | +X.XX |
| USD/JPY | XXX.XX | +X.XX | +X.XX | +X.XX |
| JGB 2s10s | X.XX% | +X.XX | {Steepening/Flattening} |
| JGB 2s30s | X.XX% | +X.XX | {Steepening/Flattening} |
| DXY | XXX.XX | +X.XX | +X.XX | {USD-driven / JPY-specific / DIVERGENCE} |

**Spread Direction:** {WIDENING / NARROWING / STABLE}
**Divergence Check:** {CONFIRMED / DIVERGENCE / NEUTRAL}

{1-2 sentence narrative explaining the current rate differential regime}
{1 sentence on JGB curve shape — steepening/flattening and implications}
{1 sentence identifying whether the current move is USD-driven or JPY-specific}

![Macro Spread Chart](macro_spread_YYYY-MM-DD.png)

---

## 03 — Technicals

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L}

| Indicator | Value | Signal |
|-----------|-------|--------|
| Price vs SMA50 | {Above/Below} ({XXX.XX}) | {Bullish/Bearish} |
| Price vs SMA200 | {Above/Below} ({XXX.XX}) | {Bullish/Bearish} |
| SMA50 vs SMA200 | {Golden Cross / Death Cross / None} | {Bullish/Bearish/Neutral} |
| RSI (14) | {XX.X} | {Overbought/Oversold/Neutral} |
| MACD | {+/-X.XX} | {Bullish/Bearish} ({crossover?}) |
| Ichimoku Cloud | {Above/Below/Inside} | {Bullish/Bearish/Neutral} |

**Key Levels:** Support {XXX.XX} / Resistance {XXX.XX}

{1 sentence: technical setup and what to watch.}

![Technicals Chart](technicals_YYYY-MM-DD.png)

---

## 05 — Cross-Asset Correlations

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L}

| Asset | 30d Correlation | Expected | Status |
|-------|----------------|----------|--------|
| S&P 500 | +0.XX | Positive | {Normal/Breakdown} |
| Nikkei 225 | +0.XX | Positive | {Normal/Breakdown} |
| Gold | -0.XX | Negative | {Normal/Breakdown} |
| VIX | -0.XX | Negative | {Normal/Breakdown} |
| WTI Oil | +0.XX | Positive | {Normal/Breakdown} |

**Energy Risk:** {CRITICAL / HIGH / NEUTRAL / TAILWIND} — WTI at $XX.XX ({+/-X.X%} 1M)

**Risk Regime:** {RISK-ON / RISK-OFF / DECORRELATED / TRANSITIONAL}
**Breakdown Alerts:** {any flipped correlations or "None"}

{1 sentence including energy risk context.}

![Correlations Chart](correlations_YYYY-MM-DD.png)

---

## 07 — Checklist

| # | Factor | Direction | Confidence | Note |
|---|--------|-----------|------------|------|
| 1 | Macro Regime | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 2 | Central Bank | {BULL/BEAR/NEUT} | {H/M/L} | {short note or "Weekly data"} |
| 3 | Technicals | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 4 | Positioning | {BULL/BEAR/NEUT} | {H/M/L} | {short note or "Weekly data"} |
| 5 | Cross-Asset | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 6 | Seasonality | {BULL/BEAR/NEUT} | {H/M/L} | {short note or "Weekly data"} |

**Overall: {STRONG BULLISH / MODERATE BULLISH / NEUTRAL / MODERATE BEARISH / STRONG BEARISH}**
**Score: {+X} / {max}** | **Conviction: {HIGH / MEDIUM / LOW}** | **Modules: {X}/6**

---

## Bottom Line

{2-3 sentences: the directional view, key levels, what would change the view. Be direct and specific.}

---

*Data: FRED, MOF Japan, Yahoo Finance, CFTC | TZ: JST | Next: /usdjpy-daily tomorrow*
```

---

## Template Rules

1. **Economic Calendar and Session Context appear before Module 01.** These set the stage for the day's analysis. They go after Risk Alerts, before 01 — Macro Regime.

2. **Economic Calendar uses web search.** Search for today's and tomorrow's economic calendar. Only include HIGH and MED impact events for US and Japan.

3. **Session Context requires intraday data.** Use Yahoo Finance (`USDJPY=X`, interval=15m or 1h, period=2d) to get previous day H/L/C and today's Asian session range.

4. **Keep daily report to ~4 pages max in PDF.** The Calendar and Session Context sections replace wasted space; they do not add pages.

5. **Weekly-only modules (02, 04, 06)** appear in the checklist with their most recent data but do not get their own section in the daily report.

6. **Charts:** Generate 3 PNG charts (macro spread, technicals, correlations). Reference them inline with relative paths.
