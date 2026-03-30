# Module 08 — Smart Money Concepts (Entry/Exit)

## Purpose
Translate the directional bias from Modules 01-07 into precise entry zones, stop losses, and targets using Smart Money Concepts across 4H, 1H, 15M, and 5M timeframes.

## Status: IMPLEMENTED

**Engine:** `./scripts/smc_engine.py` — core SMC functions (reusable)
**Orchestrator:** `./scripts/run_smc_analysis.py` — multi-TF analysis + report + chart
**Commands:** `/usdjpy-entry` (full), `/usdjpy-levels` (quick zones), `/usdjpy-fix` (Tokyo fix fade)

## Prerequisites
- Module 07 checklist must have been run and a directional bias established
- If Module 07 bias is NEUTRAL with LOW conviction, this module should warn the user that SMC entries without a macro bias are lower probability

## Data Source

### Yahoo Finance (`yfinance`)
```python
import yfinance as yf

ticker = "USDJPY=X"

# 4H candles — up to 60 days
df_4h = yf.download(ticker, period="60d", interval="1h")
# Resample 1h to 4h manually:
# df_4h = df_1h.resample('4h').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})

# 1H candles — up to 730 days
df_1h = yf.download(ticker, period="60d", interval="1h")

# 15M candles — up to 60 days
df_15m = yf.download(ticker, period="60d", interval="15m")

# 5M candles — up to 60 days (but only 7 days of data available)
df_5m = yf.download(ticker, period="7d", interval="5m")
```

### Limitations
- 5M data: only 7 days of history available
- 15M data: up to 60 days
- 1H data: up to 730 days
- Data may have gaps during low-liquidity periods (weekends, holidays)
- Yahoo Finance forex data is indicative, not tick-exact — sufficient for zone identification but not for scalping

### Fallback
If yfinance fails, use FRED DEXJPUS (daily only) and note that intraday SMC analysis is unavailable.

## Core SMC Concepts — Algorithmic Definitions

### 1. Swing Points

A swing high is a candle whose high is higher than the highs of N candles on both sides.
A swing low is a candle whose low is lower than the lows of N candles on both sides.

```python
def find_swing_highs(df, lookback=5):
    """A bar is a swing high if its high is the max of the surrounding 2*lookback+1 bars."""
    swing_highs = []
    for i in range(lookback, len(df) - lookback):
        window = df['High'].iloc[i - lookback : i + lookback + 1]
        if df['High'].iloc[i] == window.max():
            swing_highs.append({
                'index': i,
                'datetime': df.index[i],
                'price': df['High'].iloc[i]
            })
    return swing_highs

# Same logic inverted for swing lows using df['Low'].min()
```

Lookback values by timeframe:
- 4H: lookback = 5 (20 bars = ~3 trading days)
- 1H: lookback = 5 (10 bars = ~half a trading day)
- 15M: lookback = 5 (75 minutes each side)
- 5M: lookback = 5 (25 minutes each side)

### 2. Market Structure

**Higher High (HH):** Current swing high > previous swing high
**Higher Low (HL):** Current swing low > previous swing low
**Lower High (LH):** Current swing high < previous swing high
**Lower Low (LL):** Current swing low < previous swing low

**Bullish structure:** Series of HH + HL
**Bearish structure:** Series of LH + LL

**Break of Structure (BOS):**
- Bullish BOS: Price breaks above the most recent swing high → trend continuation (bullish)
- Bearish BOS: Price breaks below the most recent swing low → trend continuation (bearish)

**Change of Character (ChoCH):**
- Bullish ChoCH: In a bearish structure (LH/LL), price breaks above the most recent lower high → potential reversal to bullish
- Bearish ChoCH: In a bullish structure (HH/HL), price breaks below the most recent higher low → potential reversal to bearish

```python
def classify_structure(swing_highs, swing_lows):
    """
    Compare consecutive swing points to determine market structure.
    Returns: 'BULLISH', 'BEARISH', or 'TRANSITIONAL'
    Also returns the most recent BOS or ChoCH event.
    """
    # Compare last 2 swing highs and last 2 swing lows
    # If latest SH > prev SH AND latest SL > prev SL → BULLISH
    # If latest SH < prev SH AND latest SL < prev SL → BEARISH
    # Mixed → TRANSITIONAL
    pass
```

### 3. Order Blocks (OB)

**Bullish Order Block:**
The last bearish (red) candle before an impulsive bullish move that causes a bullish BOS.
- Zone: from the candle's body low (open) to its body high (close), or full range (low to high) for a wider zone
- This represents where institutional buying occurred

**Bearish Order Block:**
The last bullish (green) candle before an impulsive bearish move that causes a bearish BOS.
- Zone: from the candle's body low to body high
- This represents where institutional selling occurred

```python
def find_order_blocks(df, bos_events):
    """
    For each BOS event, look backward to find the last opposing candle.
    
    Bullish BOS → scan backward for last bearish candle (close < open)
    Bearish BOS → scan backward for last bullish candle (close > open)
    
    The order block zone is defined by that candle's open and close (body).
    """
    order_blocks = []
    for bos in bos_events:
        direction = bos['direction']  # 'bullish' or 'bearish'
        bos_index = bos['index']
        
        # Scan backward
        for i in range(bos_index - 1, max(bos_index - 20, 0), -1):
            candle = df.iloc[i]
            if direction == 'bullish' and candle['Close'] < candle['Open']:
                # Found bearish candle before bullish BOS
                order_blocks.append({
                    'type': 'bullish_ob',
                    'datetime': df.index[i],
                    'zone_top': max(candle['Open'], candle['Close']),
                    'zone_bottom': min(candle['Open'], candle['Close']),
                    'full_range_top': candle['High'],
                    'full_range_bottom': candle['Low'],
                    'timeframe': bos['timeframe'],
                    'mitigated': False  # set True once price returns and trades through
                })
                break
            elif direction == 'bearish' and candle['Close'] > candle['Open']:
                order_blocks.append({
                    'type': 'bearish_ob',
                    'datetime': df.index[i],
                    'zone_top': max(candle['Open'], candle['Close']),
                    'zone_bottom': min(candle['Open'], candle['Close']),
                    'full_range_top': candle['High'],
                    'full_range_bottom': candle['Low'],
                    'timeframe': bos['timeframe'],
                    'mitigated': False
                })
                break
    return order_blocks
```

**Mitigation:** An order block is "mitigated" (used up) once price returns to it and trades through the zone. Mitigated OBs should not be used again.

### 4. Fair Value Gaps (FVG)

**Bullish FVG:** Three consecutive candles where:
- Candle 3's low > Candle 1's high
- The gap between Candle 1 high and Candle 3 low is the imbalance zone
- Price tends to return to fill this gap

**Bearish FVG:** Three consecutive candles where:
- Candle 3's high < Candle 1's low
- The gap between Candle 1 low and Candle 3 high is the imbalance zone

```python
def find_fvg(df):
    """Scan for 3-candle fair value gaps."""
    fvgs = []
    for i in range(2, len(df)):
        c1_high = df['High'].iloc[i - 2]
        c1_low = df['Low'].iloc[i - 2]
        c3_high = df['High'].iloc[i]
        c3_low = df['Low'].iloc[i]
        
        # Bullish FVG
        if c3_low > c1_high:
            fvgs.append({
                'type': 'bullish_fvg',
                'datetime': df.index[i - 1],  # middle candle
                'zone_top': c3_low,
                'zone_bottom': c1_high,
                'filled': False
            })
        
        # Bearish FVG
        if c3_high < c1_low:
            fvgs.append({
                'type': 'bearish_fvg',
                'datetime': df.index[i - 1],
                'zone_top': c1_low,
                'zone_bottom': c3_high,
                'filled': False
            })
    return fvgs
```

**Fill status:** An FVG is "filled" when price returns and trades into the gap. Partially filled FVGs are still valid.

### 5. Premium/Discount Zones

Divide the current relevant price range (most recent significant swing high to swing low) into two halves:

```python
def premium_discount(swing_high, swing_low, current_price):
    """
    Above 50% of range = premium zone (look for shorts)
    Below 50% of range = discount zone (look for longs)
    """
    midpoint = (swing_high + swing_low) / 2
    
    # Finer granularity
    premium_start = midpoint  # 50%
    deep_premium = swing_high - (swing_high - swing_low) * 0.236  # ~76.4% (OTE zone)
    discount_end = midpoint
    deep_discount = swing_low + (swing_high - swing_low) * 0.236  # ~23.6%
    optimal_trade_entry = (swing_high - swing_low) * 0.618 + swing_low  # 61.8% fib
    
    if current_price > deep_premium:
        return "DEEP PREMIUM", "strong short zone"
    elif current_price > premium_start:
        return "PREMIUM", "short zone"
    elif current_price > discount_end:
        return "DISCOUNT", "long zone"
    else:
        return "DEEP DISCOUNT", "strong long zone"
```

The **Optimal Trade Entry (OTE)** zone is between the 62% and 79% Fibonacci retracement — this is where SMC traders look for the highest probability entries.

### 6. Liquidity Levels

**Equal Highs (EQH):** Two or more swing highs at approximately the same level (within 5-10 pips). These represent buy-stop liquidity pools that smart money targets before reversing.

**Equal Lows (EQL):** Same concept on the downside — sell-stop liquidity pools.

**Previous Session Levels:**
- Previous day high/low (PDH/PDL)
- Previous week high/low (PWH/PWL)
- Previous month high/low (PMH/PML)
- Asian session high/low (for Tokyo session context)

```python
def find_equal_levels(swing_points, tolerance_pips=10):
    """Find clusters of swing points at similar levels."""
    tolerance = tolerance_pips * 0.01  # convert pips to price for JPY pairs
    clusters = []
    
    for i, sp1 in enumerate(swing_points):
        for sp2 in swing_points[i+1:]:
            if abs(sp1['price'] - sp2['price']) <= tolerance:
                clusters.append({
                    'level': (sp1['price'] + sp2['price']) / 2,
                    'type': 'EQH' if sp1 in swing_highs else 'EQL',
                    'touches': 2,
                    'liquidity_type': 'buy_stops' if 'EQH' else 'sell_stops'
                })
    return clusters
```

## Multi-Timeframe Execution Flow

This is the core decision tree. Read top-down:

```
STEP 1: Read Module 07 bias
├── BULLISH → look for LONG entries only
├── BEARISH → look for SHORT entries only
└── NEUTRAL → skip Module 08 (no edge)

STEP 2: 4H Structure Analysis
├── Identify current market structure (HH/HL or LH/LL)
├── Determine premium/discount zone
├── Find unmitigated order blocks and unfilled FVGs
└── OUTPUT: "4H is {bullish/bearish}, price is in {premium/discount}"

STEP 3: 1H Zone Identification
├── Within the 4H bias direction, find the nearest:
│   ├── Unmitigated order block (highest priority)
│   ├── Unfilled fair value gap
│   └── Key liquidity level (EQH/EQL)
├── The zone must be in the correct premium/discount area
│   ├── For longs: zone must be in discount (below 50%)
│   └── For shorts: zone must be in premium (above 50%)
└── OUTPUT: "1H entry zone at {price range}"

STEP 4: 15M Confirmation
├── Wait for price to reach the 1H zone
├── Look for:
│   ├── ChoCH on 15M (structure shift confirming reversal at the zone)
│   ├── Bullish/bearish engulfing pattern at the zone
│   └── Rejection wick showing zone is holding
└── OUTPUT: "15M confirms / does not confirm entry"

STEP 5: 5M Entry Trigger
├── After 15M confirms, find exact entry on 5M:
│   ├── 5M order block formed after the 15M ChoCH
│   ├── 5M FVG within the zone
│   └── Entry at the OTE (61.8-79% fib) of the 5M impulse
├── Stop loss: below/above the 1H order block or zone boundary
├── Target: next 4H swing high/low or liquidity level
└── OUTPUT: exact entry price, stop, target, risk:reward
```

## Risk Management Rules

```
Minimum risk:reward = 1:2 (do not output entries below this)
Preferred risk:reward = 1:3 or better

Stop loss placement:
- LONG: below the 1H order block low (or 1H FVG bottom) minus 5-10 pip buffer
- SHORT: above the 1H order block high (or 1H FVG top) plus 5-10 pip buffer

Target placement (in priority order):
1. Next unmitigated order block on the opposing side
2. Next liquidity level (EQH/EQL/session high/low)
3. Next swing high/low on the 4H
4. Premium/discount zone boundary (50% of range)

Position sizing note:
This module outputs levels only. Position sizing is the user's responsibility.
```

## Confluence Scoring

Not all setups are equal. Score each potential entry:

```
+1  Order block present at entry zone
+1  Fair value gap overlaps with order block
+1  Entry is in OTE zone (61.8-79% fib)
+1  Liquidity was swept before reversal (stop hunt)
+1  Multi-timeframe alignment (4H + 1H + 15M all agree)
+1  Module 07 bias is HIGH confidence

Score interpretation:
5-6 = A+ setup (highest probability)
3-4 = B setup (tradeable)
1-2 = C setup (weak, consider skipping)
0   = No valid setup
```

## Output Format

```markdown
## 08 — Smart Money Concepts

### Directional Bias (from Module 07)
**Direction:** {LONG / SHORT}
**Confidence:** {H/M/L}

### 4H Structure
**Market Structure:** {Bullish (HH/HL) / Bearish (LH/LL) / Transitional}
**Last BOS/ChoCH:** {type} at {price} on {date}
**Premium/Discount:** Price at {XXX.XX} is in {PREMIUM / DISCOUNT} (range: {low} - {high})

### Entry Zone (1H)
**Zone Type:** {Order Block / FVG / Liquidity Level}
**Zone Range:** {XXX.XX} — {XXX.XX}
**Zone Status:** {Unmitigated / Partially mitigated}
**Distance from Current Price:** {XX} pips

### Confirmation Status (15M)
**15M Structure at Zone:** {ChoCH confirmed / Awaiting confirmation / Not yet at zone}

### Entry Details (5M)
| Field | Value |
|-------|-------|
| Entry | {XXX.XX} |
| Stop Loss | {XXX.XX} |
| Target 1 | {XXX.XX} (R:R = 1:{X.X}) |
| Target 2 | {XXX.XX} (R:R = 1:{X.X}) |
| Risk (pips) | {XX} |
| Confluence Score | {X}/6 — {A+ / B / C} |

### Active Zones Summary
List all unmitigated order blocks and unfilled FVGs across timeframes:

| Timeframe | Type | Zone | Direction | Status |
|-----------|------|------|-----------|--------|
| 4H | Bullish OB | {range} | Long | Unmitigated |
| 1H | Bearish FVG | {range} | Short | Unfilled |
| ... | ... | ... | ... | ... |

### Key Liquidity Levels
| Level | Type | Significance |
|-------|------|-------------|
| {XXX.XX} | EQH | Buy stops (liquidity target) |
| {XXX.XX} | PDH | Previous day high |
| {XXX.XX} | PWL | Previous week low |
| ... | ... | ... |
```

## Chart (when implemented)
- 4H candlestick with order blocks shaded (blue for bullish, red for bearish)
- FVGs highlighted (lighter shade)
- Swing structure drawn (HH/HL/LH/LL labels)
- Premium/discount zone shading
- Entry/stop/target horizontal lines
- Save as `./output/daily/smc_entry_YYYY-MM-DD.png`

## Command

### /usdjpy-entry
Run Module 08 SMC analysis:
1. Read latest Module 07 bias from most recent daily/weekly report
2. Fetch intraday data from Yahoo Finance
3. Run structural analysis on all 4 timeframes
4. Output entry zones and trade parameters
5. Save to `./output/daily/smc_YYYY-MM-DD.md`

If Module 07 bias is NEUTRAL, warn the user and ask whether to proceed anyway.
