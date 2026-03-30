# USD/JPY Weekly Report Template

> **This is the exact format to follow when generating weekly reports.**
> Weekly reports include ALL modules (01-07). Same structure as daily but with 
> additional sections for Modules 02, 04, and 06.
> Save output to `./output/weekly/YYYY-MM-DD.md`

---

```markdown
# USD/JPY Weekly Analysis — Week of {YYYY-MM-DD}

> **{BULLISH / BEARISH / NEUTRAL}** | Conviction: **{HIGH / MEDIUM / LOW}** | Score: **{+X}/{max}** | Full coverage: **6/6 modules**

---

## At a Glance

| | Value | 1W | 1M | 3M | Signal |
|---|---|---|---|---|---|
| USD/JPY | {XXX.XX} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| US 10Y | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| JP 10Y | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | — |
| Spread | {X.XX%} | {+X.XX} | {+X.XX} | {+X.XX} | {WIDENING/NARROWING/STABLE} |
| RSI (14) | {XX.X} | — | — | — | {OB/OS/NEUTRAL} |
| COT Net | {+/-X,XXX} | {+/-X,XXX} | — | — | {CROWDED/MODERATE/LIGHT} |

> {2 sentences: what changed this week vs last week. What's the dominant theme.}

---

## Risk Alerts

| Alert | Status | Detail |
|---|---|---|
| BOJ Intervention | {CRITICAL / ELEVATED / LOW} | USD/JPY at {XXX.XX}, {+X.XX} yen in 30d |
| Event Risk (next week) | {YES / NO} | {Event name, date} |
| COT Crowding | {YES / NO} | {Percentile}th percentile (3yr) |
| Correlation Breakdown | {YES / NO} | {Which asset(s) or "All normal"} |
| Seasonal Flow | {YES / NO} | {What flow and expected direction} |

---

## 01 — Macro Regime

{Same format as daily report template — see daily_report.md}

---

## 02 — Central Bank Policy

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L}

### BOJ
| Field | Status |
|-------|--------|
| Policy Rate | {X.XX%} |
| Stance | {Hiking / Holding / Cutting} |
| Last Meeting | {date} — {outcome summary} |
| Next Meeting | {date} |
| Key Quote | {<15 words max from latest statement} |

### Fed
| Field | Status |
|-------|--------|
| Fed Funds Rate | {X.XX% - X.XX%} |
| Stance | {Hiking / Holding / Cutting} |
| Last Meeting | {date} — {outcome summary} |
| Next Meeting | {date} |
| Key Quote | {<15 words max from latest statement} |

### Intervention Risk
**MOF Rhetoric Level:** {SILENT / VERBAL WARNING / STRONG WARNING / RATE CHECK}
**Last Intervention:** {date and approximate level}

{1-2 sentences: what the policy divergence means for USD/JPY direction.}

---

## 03 — Technicals

{Same format as daily report template — see daily_report.md}

---

## 04 — Positioning (COT)

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L} | *(contrarian interpretation)*

| Metric | Value |
|--------|-------|
| Net Speculative Position | {+/-X,XXX} contracts ({long/short} JPY) |
| Week-over-Week Change | {+/-X,XXX} contracts |
| 3-Year Percentile | {XX}th |
| Crowding Status | {CROWDED / MODERATE / LIGHT} |

{1 sentence: what the positioning tells us. Emphasize that this is a contrarian signal.}

---

## 05 — Cross-Asset Correlations

{Same format as daily report template — see daily_report.md}

---

## 06 — Seasonality & Flows

**Bias: {BULLISH / BEARISH / NEUTRAL}** | Confidence: {H/M/L}

| Factor | Status |
|--------|--------|
| Current Month | {Month} — Historical bias: {direction} ({strength}) |
| Fiscal Year Position | {days until/since Japan FY end (Mar 31)} |
| Repatriation Flow | {Active / Not active} |

### Upcoming Events (next 2 weeks)
| Date | Event | Expected Impact |
|------|-------|-----------------|
| {date} | {event} | {direction + magnitude} |
| {date} | {event} | {direction + magnitude} |

{1 sentence: how seasonality aligns or conflicts with the other modules.}

---

## 07 — Checklist

| # | Factor | Direction | Confidence | Note |
|---|--------|-----------|------------|------|
| 1 | Macro Regime | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 2 | Central Bank | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 3 | Technicals | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 4 | Positioning | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 5 | Cross-Asset | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |
| 6 | Seasonality | {BULL/BEAR/NEUT} | {H/M/L} | {short note} |

**Overall: {STRONG BULLISH / MODERATE BULLISH / NEUTRAL / MODERATE BEARISH / STRONG BEARISH}**
**Score: {+X} / {max}** | **Conviction: {HIGH / MEDIUM / LOW}** | **Modules: 6/6**

---

## Week Ahead

{3-4 sentences. Cover: (1) the directional view, (2) key levels and what happens if they break, (3) the main event risk next week, (4) what to watch for that would change the view. Be direct and specific.}

---

## vs Last Week

| Metric | Last Week | This Week | Change |
|--------|-----------|-----------|--------|
| Bias | {direction} | {direction} | {Unchanged / Shifted} |
| Score | {+X} | {+X} | {+/-X} |
| USD/JPY | {XXX.XX} | {XXX.XX} | {+X.XX} |
| Spread | {X.XX%} | {X.XX%} | {+X.XX} |

{1 sentence: did conviction increase, decrease, or hold. Why.}

---

*Data: FRED, MOF Japan, Yahoo Finance, CFTC | TZ: JST | Next: /usdjpy-daily Monday*
```

---

## Additional Rules for Weekly Reports

1. **"vs Last Week" section is mandatory.** Read the previous weekly report from `./output/weekly/` and compare. If no previous report exists, write "First weekly report — no comparison available."

2. **All 6 modules must have a section.** Unlike daily reports where N/A modules are checklist-only, weekly reports give every module its own section.

3. **Week Ahead replaces Bottom Line.** Weekly reports are forward-looking. The "Week Ahead" section should name specific dates and events.

4. **COT data is the new addition.** Make sure the positioning data is clearly labeled as contrarian — readers often misread "net short JPY" as bearish JPY when it's actually a crowded short that favors JPY strength.

5. **Charts:** Generate the same 3 charts as daily (macro, technicals, correlations). No additional charts needed for the weekly-only modules.
