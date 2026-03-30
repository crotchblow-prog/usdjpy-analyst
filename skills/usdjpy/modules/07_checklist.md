# Module 07 — Pre-Trade Checklist & Journal

## Purpose
Aggregate signals from all available modules into a single decision grid. This is the final output that tells you whether conditions favor going long, short, or staying flat on USD/JPY.

## Input
Read the latest signal output from each module that has been run. Not all modules run daily — use the most recent available data for each.

Check for signal files or recent report data in:
- `./data/` for raw/processed data files
- `./output/daily/` or `./output/weekly/` for the most recent module outputs

If a module has no data (hasn't been built yet or hasn't been run), mark it as "N/A" in the checklist.

## Checklist Grid

Build this table from available module signals:

```markdown
## Pre-Trade Checklist — {date}

| # | Factor | Signal | Direction | Confidence | Notes |
|---|--------|--------|-----------|------------|-------|
| 1 | Macro Regime (Rate Differential) | {from Module 01} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {spread trend + divergence status} |
| 2 | Central Bank Policy | {from Module 02} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {policy stance summary} |
| 3 | Technical Setup | {from Module 03} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {trend + key levels} |
| 4 | Positioning (COT) | {from Module 04} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {crowding status} |
| 5 | Cross-Asset | {from Module 05} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {correlation regime} |
| 6 | Seasonality | {from Module 06} | {BULLISH/BEARISH/NEUTRAL} | {H/M/L} | {seasonal bias + events} |
```

## Scoring Logic

### Count directional signals (exclude N/A modules):
```
bullish_count = number of BULLISH signals
bearish_count = number of BEARISH signals
neutral_count = number of NEUTRAL signals
total_available = bullish_count + bearish_count + neutral_count
```

### Weight by confidence:
```
weighted_score = sum of:
  +2 for each BULLISH HIGH
  +1 for each BULLISH MEDIUM or LOW
  -2 for each BEARISH HIGH
  -1 for each BEARISH MEDIUM or LOW
   0 for NEUTRAL
```

### Overall Bias
```
if weighted_score >= +4 → STRONG BULLISH
if weighted_score in [+2, +3] → MODERATE BULLISH
if weighted_score in [-1, +1] → NEUTRAL / NO EDGE
if weighted_score in [-3, -2] → MODERATE BEARISH
if weighted_score <= -4 → STRONG BEARISH
```

### Conviction Check
Flag LOW conviction if:
- Fewer than 3 modules have data (insufficient coverage)
- Any HIGH confidence signal conflicts with the overall bias
- A DIVERGENCE alert is active from Module 01

## Risk Alerts

Check for and flag these conditions:
- **BOJ intervention risk**:
  - CRITICAL: USD/JPY above 160 (absolute level), OR above 150 AND +5 yen in past month
  - ELEVATED: USD/JPY above 150 (below critical threshold)
  - NO: USD/JPY at or below 150
- **Event risk**: Major data release or central bank meeting within 48 hours (check Module 02 or note if unavailable)
- **Positioning extreme**: COT percentile above crowding threshold (check Module 04)
- **Correlation breakdown**: Key correlations have broken down (check Module 05)

```markdown
### Risk Alerts
- [ ] BOJ intervention risk: {CRITICAL/ELEVATED/NO} — USD/JPY at {level}, {X} yen move in past month
- [ ] Event risk within 48h: {YES/NO/UNKNOWN} — {event details if known}
- [ ] Positioning extreme: {YES/NO/N/A} — {percentile if available}
- [ ] Correlation breakdown: {YES/NO/N/A} — {details if available}
```

## Output Format

```markdown
## 07 — Pre-Trade Checklist

### Signal Grid
{checklist table from above}

### Overall Assessment
**Bias:** {STRONG BULLISH / MODERATE BULLISH / NEUTRAL / MODERATE BEARISH / STRONG BEARISH}
**Weighted Score:** {score} / {max possible based on available modules}
**Conviction:** {HIGH / MEDIUM / LOW}
**Available Modules:** {X} of 6

### Risk Alerts
{risk alert checklist}

### Recommendation
{2-3 sentences summarizing: the overall direction, what would change the view, 
and what to watch for next. Be specific about levels.}
```

## Journal Entry (/usdjpy-journal)

When the user runs `/usdjpy-journal`, prompt them for:
1. **Action taken**: Long / Short / Flat / Closed position
2. **Entry level** (if applicable): price
3. **Stop loss** (if applicable): price
4. **Target** (if applicable): price
5. **Rationale**: free text from the user

Then generate a journal entry:

```markdown
# Trade Journal — {date}

## Decision
- **Action:** {user input}
- **Entry:** {user input}
- **Stop:** {user input}
- **Target:** {user input}
- **Risk/Reward:** {calculated from entry/stop/target}

## Rationale
{user's free text}

## System Signals at Time of Decision
{paste the checklist grid and overall assessment from the most recent report}

## Review
{leave blank — user fills this in later when they close the trade}
- **Exit date:**
- **Exit price:**
- **P&L:**
- **What worked:**
- **What I missed:**
```

Save to `./output/journal/YYYY-MM-DD.md`
