# Module 05 — Cross-Asset Correlations

## Purpose
Monitor how USD/JPY correlates with other major assets to confirm or challenge the directional view and identify the current risk regime.

## Status: IMPLEMENTED (with Energy Risk Assessment)

## Data Sources (to be built)
- FRED API for: S&P 500 (SP500), VIX (VIXCLS), WTI Oil (DCOILWTICO), Gold (GOLDAMGBD228NLBM)
- Yahoo Finance for: Nikkei 225 (^N225)
- USD/JPY from FRED (DEXJPUS)

## Correlation Pairs to Track

| Asset | Expected Correlation with USD/JPY | Rationale |
|-------|-----------------------------------|-----------|
| S&P 500 | Positive (risk-on) | Risk appetite drives both higher |
| Nikkei 225 | Positive | Weak yen boosts Japanese exporters |
| Gold | Negative | Safe haven competes with USD |
| VIX | Negative | Fear = yen strength |
| WTI Oil | Positive (indirectly) | Oil up → JPY weaker (Japan imports oil) |

## Calculations

### Rolling Correlation
```python
# For each asset pair with USD/JPY:
correlation = usdjpy_returns.rolling(window=30).corr(asset_returns)
```

Use daily percentage returns, not levels, to compute correlations.

Window: 30 trading days (from config.yaml → correlations.window)

### Regime Classification
```
if SPX corr > 0.5 AND VIX corr < -0.3:
    regime = "RISK-ON" → supports USD/JPY upside
elif SPX corr < -0.3 AND VIX corr > 0.3:
    regime = "RISK-OFF" → supports USD/JPY downside
elif abs(SPX corr) < 0.2:
    regime = "DECORRELATED" → USD/JPY driven by idiosyncratic factors (rate diff, BOJ)
else:
    regime = "TRANSITIONAL"
```

### Breakdown Alert
Flag if any expected correlation has flipped sign for >5 consecutive trading days. This suggests a regime change may be underway.

## Signal Logic
```
RISK-ON regime + USD/JPY rising → BULLISH (confirmed)
RISK-OFF regime + USD/JPY falling → BEARISH (confirmed)
Regime contradicts USD/JPY direction → CAUTION
DECORRELATED → defer to other modules (NEUTRAL from this module)

# Energy risk override (applies regardless of correlation regime):
if energy_risk == "CRITICAL":
    bias = "BULLISH"          # BULLISH USD/JPY = BEARISH JPY
    confidence = "HIGH"
    # The correlation regime label (RISK-ON/OFF/TRANSITIONAL etc.) stays unchanged
```

## Energy Risk Assessment

In addition to the WTI correlation calculation, evaluate oil price as a standalone signal for Japan's trade balance:

```python
oil_current = WTI[today]
oil_change_1m_pct = (WTI[today] - WTI[today - 30 days]) / WTI[today - 30 days] * 100
```

Signal logic (from config: `thresholds.energy_risk_threshold` and `thresholds.energy_risk_critical`):
```
if oil_change_1m_pct > energy_risk_critical (default 20):
    energy_risk = "CRITICAL" → JPY strongly negative (trade balance shock)
elif oil_change_1m_pct > energy_risk_threshold (default 10):
    energy_risk = "HIGH" → JPY negative (Japan imports ~90% of oil, trade balance deteriorates)
elif oil_change_1m_pct < -energy_risk_threshold:
    energy_risk = "TAILWIND" → JPY supportive (lower energy import costs)
else:
    energy_risk = "NEUTRAL"
```

## Output Format
```markdown
## 05 — Cross-Asset Correlations

| Asset | 30d Correlation | Expected | Status |
|-------|----------------|----------|--------|
| S&P 500 | +0.XX | Positive | {Normal/Breakdown} |
| Nikkei 225 | +0.XX | Positive | {Normal/Breakdown} |
| Gold | -0.XX | Negative | {Normal/Breakdown} |
| VIX | -0.XX | Negative | {Normal/Breakdown} |
| WTI Oil | +0.XX | Positive | {Normal/Breakdown} |

**Energy Risk:** {CRITICAL / HIGH / NEUTRAL / TAILWIND} — WTI at $XX.XX ({+/-X.X%} 1M)

**Risk Regime:** {RISK-ON / RISK-OFF / DECORRELATED / TRANSITIONAL}
**Breakdown Alerts:** {any flipped correlations}
**Cross-Asset Bias:** {BULLISH / BEARISH / NEUTRAL} (Confidence: {H/M/L})

{1 sentence narrative including energy risk context}
```

## Chart
- Heatmap or bar chart of current 30d correlations
- Save as `./output/{daily|weekly}/correlations_YYYY-MM-DD.png`
