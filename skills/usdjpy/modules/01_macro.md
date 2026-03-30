# Module 01 — Macro Regime

## Purpose
Track the US-Japan interest rate differential, JGB yield curve shape, and USD dollar index context to determine whether USD/JPY moves are rate-driven, USD-driven, or JPY-specific. This is the single most important driver of the pair over medium-term horizons.

## Data Sources

### JGB Yields — Primary: MOF Japan (daily)

Fetch daily JGB yields from Japan Ministry of Finance:

| URL | Coverage |
|-----|----------|
| `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv` | Historical (1974–last month) |
| `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv` | Current month |

CSV format: `Date,1Y,2Y,3Y,4Y,5Y,6Y,7Y,8Y,9Y,10Y,15Y,20Y,25Y,30Y,40Y`
- JP 2Y = column index 2
- JP 10Y = column index 10
- JP 30Y = column index 14

Date format: `YYYY/M/D` — convert to `YYYY-MM-DD`.
Skip rows where any required column (2Y, 10Y, 30Y) is `-` or empty.

Fetch both CSVs, combine, deduplicate, sort ascending.
Cache as `./data/raw/MOF_JGB_{YYYY-MM-DD}.json` (contains 2Y, 10Y, 30Y).

**Fallback:** If MOF fetch fails, use FRED `IRLTLT01JPM156N` (monthly, 10Y only). Note the update lag and missing curve data in the report.

### DXY — Yahoo Finance

Fetch US Dollar Index from Yahoo Finance: ticker `DX-Y.NYB`.
Use the same Yahoo Finance v8 chart API as USD/JPY. Fetch 3 months of daily data.
Cache as `./data/raw/YF_DXY_{YYYY-MM-DD}.json`.

### US 10Y — FRED API

Base URL: `https://api.stlouisfed.org/fred/series/observations`

| Series ID | Description | Frequency |
|-----------|-------------|-----------|
| DGS10 | US 10-Year Treasury Constant Maturity Rate | Daily |

API call format:
```
https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={API_KEY}&file_type=json&sort_order=desc&limit=700&observation_start={2_YEARS_AGO}
```

Read `api_key` from `config.yaml` → `fred.api_key`

### USD/JPY — Yahoo Finance
Use `USDJPY=X` via Yahoo Finance v8 chart API (FRED DEXJPUS is stale as of Aug 2025).
Cache as `./data/raw/YF_USDJPY_X_{YYYY-MM-DD}.json`.

### US 2Y — FRED API
Series ID: `DGS2` (already in config.yaml). Fetched alongside US 10Y.

## Calculations

### 1. US-Japan 10Y Spread
```
spread = US_10Y - JP_10Y
```
Compute for each US 10Y date. With MOF daily data, align directly. If using FRED monthly fallback, forward-fill the last known JP 10Y value.

### 2. Spread Change
```
spread_change_1w = spread[today] - spread[today - 7 days]
spread_change_1m = spread[today] - spread[today - 30 days]
spread_change_3m = spread[today] - spread[today - 90 days]
```

### 3. Spread Direction
```
if spread_change_1m > threshold (config: thresholds.spread_widening_alert):
    direction = "WIDENING"
elif spread_change_1m < -threshold:
    direction = "NARROWING"
else:
    direction = "STABLE"
```

### 4. USD/JPY Change
```
usdjpy_change_1w = usdjpy[today] - usdjpy[today - 7 days]
usdjpy_change_1m = usdjpy[today] - usdjpy[today - 30 days]
```

### 5. Divergence Check
The spread and USD/JPY should move in the same direction. When they don't, it's a warning signal.

```
if spread WIDENING and usdjpy RISING → "CONFIRMED" (normal: wider spread = stronger USD)
if spread WIDENING and usdjpy FALLING → "DIVERGENCE" (watch for spread to reverse)
if spread NARROWING and usdjpy FALLING → "CONFIRMED" (normal: narrower spread = weaker USD)
if spread NARROWING and usdjpy RISING → "DIVERGENCE" (watch for USD/JPY to correct down)
if spread STABLE → "NEUTRAL"
```

### 6. JGB Yield Curve
```
jgb_2s10s = JP_10Y - JP_2Y
jgb_2s30s = JP_30Y - JP_2Y
jgb_2s10s_change_1w = jgb_2s10s[today] - jgb_2s10s[today - 7 days]
jgb_2s30s_change_1w = jgb_2s30s[today] - jgb_2s30s[today - 7 days]
```

Signal:
```
if jgb_2s10s_change_1w > 0 OR jgb_2s30s_change_1w > 0:
    curve_signal = "Steepening" → fiscal dominance fears → JPY NEGATIVE
elif jgb_2s10s_change_1w < 0 OR jgb_2s30s_change_1w < 0:
    curve_signal = "Flattening" → BOJ credibility intact → JPY NEUTRAL/POSITIVE
else:
    curve_signal = "Stable"

# Alert flag:
if jgb_2s30s_change_1w > 0.10:  # 10bps steepening in one week
    flag = "⚠ JGB 2s30s steepened >10bps this week — watch for fiscal dominance concerns"
```

### 7. DXY Context
```
dxy_current = DXY[today]
dxy_change_1w = DXY[today] - DXY[today - 7 days]
dxy_change_1m = DXY[today] - DXY[today - 30 days]
```

Compare DXY direction vs USD/JPY direction (using 1W change):
```
dxy_rising = dxy_change_1w > 0.3   # ~0.3 pts threshold for "rising"
dxy_falling = dxy_change_1w < -0.3
dxy_flat = not dxy_rising and not dxy_falling

usdjpy_rising = usdjpy_change_1w > 0.3
usdjpy_falling = usdjpy_change_1w < -0.3

if dxy_rising and usdjpy_rising:
    driver = "USD-driven" (broad dollar strength)
elif dxy_flat and usdjpy_rising:
    driver = "JPY-specific weakness"
elif dxy_falling and usdjpy_rising:
    driver = "DIVERGENCE" (JPY very weak — watch for reversal)
elif dxy_falling and usdjpy_falling:
    driver = "USD-driven" (broad dollar weakness)
elif dxy_rising and usdjpy_falling:
    driver = "JPY-specific strength"
else:
    driver = "Mixed"
```

## Signal Output

### Bias
```
if spread WIDENING + CONFIRMED → BULLISH USD/JPY
if spread NARROWING + CONFIRMED → BEARISH USD/JPY
if DIVERGENCE → CAUTION (note direction of divergence)
if STABLE → NEUTRAL
```

### Confidence
```
HIGH: spread change > 2x threshold AND confirmed
MEDIUM: spread change > threshold AND confirmed, OR spread change > 2x threshold with divergence
LOW: spread change near threshold, OR divergence present
```

## Report Output Format

```markdown
## 01 — Macro Regime

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
**Macro Bias:** {BULLISH / BEARISH / NEUTRAL} (Confidence: {HIGH / MEDIUM / LOW})

{1-2 sentence narrative explaining the current rate differential regime}
{1 sentence on JGB curve shape — steepening/flattening and implications}
{1 sentence identifying whether the current move is USD-driven or JPY-specific}
```

## Charts

### Chart 1: Spread vs USD/JPY
Generate a dual-axis matplotlib chart:
- Left axis: US-JP 10Y spread (line, blue)
- Right axis: USD/JPY spot rate (line, red)
- X axis: dates (3 months for daily, 12 months for weekly)
- Title: "US-Japan 10Y Spread vs USD/JPY"
- Highlight divergence periods with light yellow background shading if detected
- Save as `./output/{daily|weekly}/macro_spread_YYYY-MM-DD.png`

### Chart 2: JGB Curve + DXY (weekly report only)
Generate a two-panel chart:
- Top panel: JGB 2s10s and 2s30s spread over 6 months
- Bottom panel: DXY level over 3 months with USD/JPY overlay (dual axis)
- Save as `./output/weekly/macro_curve_dxy_YYYY-MM-DD.png`
