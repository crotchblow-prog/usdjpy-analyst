# Module 06 — Seasonality & Flow Patterns

## Purpose
Identify seasonal tendencies and predictable institutional flow patterns that affect USD/JPY.

## Status: IMPLEMENTED

## Key Seasonal Patterns

### Japanese Fiscal Year (April 1 – March 31)

| Period | Typical Flow | Effect on USD/JPY | Strength |
|--------|-------------|-------------------|----------|
| Jan | New year positioning, fresh allocations | Neutral to slightly bullish | Weak |
| Feb-Mar | Repatriation ahead of fiscal year-end | JPY strength (USD/JPY bearish) | Strong |
| Apr | New fiscal year, fresh overseas investment | JPY weakness (USD/JPY bullish) | Moderate |
| May | Golden Week reduced liquidity | Volatile, no clear direction | Weak |
| Jun | Mid-year adjustments | Neutral | Weak |
| Jul-Aug | Summer bonus season, Obon holidays | Reduced liquidity, mild JPY strength | Weak |
| Sep | Half-year rebalancing | JPY strength | Moderate |
| Oct-Nov | Fresh overseas investment cycle | JPY weakness (USD/JPY bullish) | Moderate |
| Dec | Year-end position squaring | Volatile, often JPY strength | Moderate |

### Institutional Flow Calendar
- **Life insurers**: Adjust FX hedging ratios at fiscal year boundaries (Apr, Oct)
- **Pension funds (GPIF)**: Quarterly rebalancing can create large one-way flows
- **Toshin (investment trusts)**: Retail Japanese investors buy foreign assets → JPY selling
- **Tokyo Fix (9:55 AM JST)**: Daily flow event, can create short-term volatility

### US Calendar Effects
- **NFP Friday**: First Friday of each month — high volatility
- **FOMC meetings**: ~8 per year — directional catalyst
- **US fiscal year-end (Sep 30)**: Minor effect

## Signal Logic
```
Check current month against seasonal table above.
if current_month in strong_pattern_months (Feb, Mar, Apr, Sep):
    seasonal_bias = table direction
    confidence = MEDIUM
elif current_month in moderate_pattern_months:
    seasonal_bias = table direction
    confidence = LOW
else:
    seasonal_bias = NEUTRAL
    confidence = LOW
```

Flag upcoming events within 2 weeks:
- BOJ meeting dates
- FOMC meeting dates
- Japan fiscal year boundaries
- Golden Week / Obon

## Trade Balance (Weekly report only)

Use web search to find the latest Japan trade balance and current account data (released monthly by MOF, usually around the 20th of each month for prior month data).

### Signal Logic
```
if trade_deficit_widening AND energy_driven:
    trade_signal = "JPY negative" (structural outflow)
elif current_account_surplus_growing:
    trade_signal = "Structural JPY support" (long-term positive)
elif trade_balance_stable:
    trade_signal = "No change"
```

No signal change from month to month unless there is a significant shift (>20% change in deficit/surplus or reversal of direction).

**Do NOT run this section in the daily report.** Weekly only.

## Output Format
```markdown
## 06 — Seasonality & Flows

**Current Month:** {month} — Historical bias: {direction} ({strength})
**Seasonal Bias:** {BULLISH / BEARISH / NEUTRAL}
**Confidence:** {H/M/L}

### Upcoming Events (next 2 weeks)
- {date}: {event description}
- {date}: {event description}

### Flow Notes
{Any relevant institutional flow context for the current period}

### Trade Balance (weekly only)
**Trade Balance:** {surplus / deficit} — ¥X.XX trillion ({month})
**Current Account:** {surplus / deficit} — ¥X.XX trillion ({month})
**Trend:** {Improving / Deteriorating / Stable}
```
