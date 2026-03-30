# Module 04 — Positioning (CFTC Commitment of Traders)

## Purpose
Track speculative positioning in JPY futures to identify crowding and potential reversal risk.

## Status: IMPLEMENTED (Phase 3)

## Data Sources
- CFTC Legacy Futures report: https://www.cftc.gov/dea/futures/deacmelf.htm
- Japanese Yen futures (CME) — contract code 097741
- Fixed-width HTML format, parsed by `run_cot_analysis.py`
- Cache: `./data/raw/cot_YYYY-MM-DD.json` (7-day validity)
- History built from accumulated cache files for percentile ranking

## Key Metrics
- **Net speculative positioning**: Non-commercial long minus short contracts
- **Week-over-week change**: Direction of positioning shift
- **Percentile rank**: Where current positioning sits vs 3-year history
- **Extreme reading**: Above 85th or below 15th percentile = crowded

## Signal Logic
```
if net_position extremely_short AND percentile > 85 → BEARISH JPY positioning is CROWDED
  → Contrarian signal: watch for JPY short squeeze = USD/JPY bearish reversal risk
  → Signal: BEARISH USD/JPY (contrarian)

if net_position extremely_long AND percentile > 85 → BULLISH JPY positioning is CROWDED
  → Contrarian signal: watch for JPY long unwind = USD/JPY bullish
  → Signal: BULLISH USD/JPY (contrarian)

if positioning moderate (25th-75th percentile) → NEUTRAL
```

Note: COT signals are contrarian — extreme positioning suggests the move is crowded and vulnerable to reversal.

## Institutional Flow Context (Weekly report only)

After the COT quantitative analysis, add a qualitative section using web search to check for recent reports about:
- **GPIF** (Government Pension Investment Fund) rebalancing announcements or portfolio shifts
- **Japanese life insurer** hedging ratio changes (e.g., Nippon Life, Dai-ichi Life quarterly announcements)
- **Toshin** (investment trust) flow data — retail Japanese investor foreign asset purchases
- **Carry trade** unwind commentary from major banks (Goldman, JPMorgan, Nomura, etc.)

This is a qualitative check — not a computed signal. If web search returns nothing notable, write "No notable institutional flow news this week."

**Do NOT run this section in the daily report.** Weekly only.

## Output Format
```markdown
## 04 — Positioning (COT)

**Net Speculative Position:** {X,XXX} contracts ({long/short} JPY)
**Week-over-Week Change:** {+/-X,XXX} contracts
**3-Year Percentile:** {XX}th percentile
**Crowding Status:** {CROWDED / MODERATE / LIGHT}

**Positioning Bias:** {BULLISH / BEARISH / NEUTRAL} (contrarian interpretation)
**Confidence:** {H/M/L}

### Institutional Flow Context (weekly only)
**Flow Notes:** {1-2 sentences summarizing any notable institutional flow developments, or "No notable institutional flow news this week."}
```
