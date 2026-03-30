# Module 03 — Technical Analysis

## Purpose
Apply technical indicators to USD/JPY price data for trend identification and timing signals.

## Data Sources

### Primary: Yahoo Finance OHLCV
- Ticker: `USDJPY=X`
- Fetch via Yahoo Finance v8 chart API (daily bars, 2-year history)
- Provides real Open/High/Low/Close data
- Cache as `./data/raw/YF_USDJPY_X_{YYYY-MM-DD}.json`
- OHLCV is required for accurate Ichimoku (real H/L), candlestick charting, and key level identification

### Fallback: Yahoo Finance close-only
- If OHLCV extraction fails, use close prices only
- Ichimoku H/L will be approximated from close — note this in the report

## Indicators to Calculate

### Moving Averages
- 50-day SMA and 200-day SMA
- Golden cross (50 > 200) = bullish, Death cross (50 < 200) = bearish
- Price position relative to both SMAs

### RSI (14-period)
- Above 70 = overbought (potential reversal down)
- Below 30 = oversold (potential reversal up)
- Look for RSI divergence vs price (price makes new high but RSI doesn't)

### MACD (12, 26, 9)
- MACD line cross above signal = bullish
- MACD line cross below signal = bearish
- Histogram direction for momentum

### Ichimoku Cloud
- Tenkan-sen (9) vs Kijun-sen (26) cross
- Price vs Cloud (Senkou Span A & B) — uses real daily highs/lows
- Chikou Span position
- Cloud color (A > B = bullish, B > A = bearish)
- Particularly relevant because Japanese institutional traders use Ichimoku heavily

### Key Levels
- Support: 30-bar low using real daily lows
- Resistance: 30-bar high using real daily highs
- Round number levels (150, 155, 160) carry psychological significance

## Signal Logic
```
BULLISH: Price above cloud AND above 200 SMA AND MACD bullish AND RSI not overbought
BEARISH: Price below cloud AND below 200 SMA AND MACD bearish AND RSI not oversold
NEUTRAL: Mixed signals or price inside the cloud
```

Confidence:
- HIGH: All 4 indicators agree
- MEDIUM: 3 of 4 agree
- LOW: 2 of 4 agree or price inside cloud

## Output Format
```markdown
## 03 — Technical Analysis

| Indicator | Value | Signal |
|-----------|-------|--------|
| Price | XXX.XX | — |
| 50 SMA | XXX.XX | {Above/Below price} |
| 200 SMA | XXX.XX | {Above/Below price} |
| SMA Cross | {Golden/Death/None} | {Bullish/Bearish/Neutral} |
| RSI (14) | XX.X | {Overbought/Oversold/Neutral} |
| MACD | {Above/Below signal} | {Bullish/Bearish} |
| Ichimoku | {Above/Below/Inside cloud} | {Bullish/Bearish/Neutral} |

**Key Levels:** Support {XXX.XX}, Resistance {XXX.XX}
**Technical Bias:** {BULLISH / BEARISH / NEUTRAL} (Confidence: {H/M/L})

*Data source: Yahoo Finance (OHLCV)*
```

## Chart
- Price line chart with 50/200 SMA overlay
- Ichimoku cloud shading (Senkou A/B band)
- Tenkan and Kijun horizontal reference lines
- RSI subplot below
- Save as `./output/{daily|weekly}/technicals_YYYY-MM-DD.png`
