# Module 09 — Scenario Monitor

## Purpose
Close the feedback loop: check which playbook scenario actually played out after each SMC report.

## Jobs

### Job 1 — Live Check (6h after SMC report)
- Fetch latest 5M price data from Yahoo Finance
- Compare current price action against 3 playbook scenarios
- Determine which scenario is unfolding (or none)
- Email a short status update

### Job 2 — Scorecard (12h after SMC report)
- Fetch the full 12h of 5M price data since SMC generation
- Score each scenario: HIT / PARTIAL / MISS / NO TRADE
- Log results to cumulative scorecard CSV
- Email a summary with running stats

## Data Inputs
- Latest SMC report: `./output/daily/smc_YYYY-MM-DD.md`
- Fresh 5M price data: Yahoo Finance (`USDJPY=X`)
- Module 07 bias from daily report

## SMC Report Parsing

Extract from the most recent `smc_*.md`:
- **Generation time:** from `*Generated: YYYY-MM-DD HH:MM JST*`
- **Direction:** from `**Direction:** LONG/SHORT`
- **Grade:** from `Grade **X**`
- **Setup type:** from `**Setup Type:** ...`
- **Entry price:** from entry plan table `| Entry | NNN.NN |`
- **Stop price:** from `| Stop Loss | NNN.NN |`
- **Target 1 price:** from `| Target 1 | NNN.NN |`
- **Target 2 price:** from `| Target 2 | NNN.NN |` (if present)
- **Three scenarios** from `#### Primary:`, `#### Alternative:`, `#### Tail Risk:`
  - Each scenario: name, probability, key level, trigger, action, invalidation

## Job 1 — Live Check Logic

### Scenario Matching Rules

**Primary (Pullback to OB):**
- ACTIVE if: price touched entry zone AND bounced (5M close above entry after touching zone)
- APPROACHING if: price within 10 pips of entry zone and moving toward it
- INVALIDATED if: price broke below stop level

**Alternative (Liquidity Sweep):**
- ACTIVE if: price broke below sweep level AND showed bullish displacement (5M body > 15 pips opposite direction)
- APPROACHING if: price within 10 pips of sweep level
- INVALIDATED if: price held below sweep level > 30 minutes without displacement

**Tail Risk:**
- ACTIVE if: price dropped > 100 pips in < 30 minutes
- APPROACHING if: price within 20 pips of 160.00 intervention level AND moving toward it
- NOT TRIGGERED otherwise

**None matching:**
- RANGING if: price hasn't moved > 20 pips from generation price
- UNEXPECTED if: price moved > 50 pips in direction none of the scenarios projected

### Output Format

```markdown
## Module 09 — Scenario Monitor (Live Check)
**SMC Report:** YYYY-MM-DD HH:MM JST
**Check Time:** YYYY-MM-DD HH:MM JST (Xh elapsed)
**Price at Report:** NNN.NN
**Current Price:** NNN.NN

### Status: [SCENARIO NAME] [STATUS]
[Description of what happened]

**Entry zone hit:** YES/NO [at HH:MM JST]
**Current P&L:** +/- NN pips from entry
**Target 1:** NNN.NN — NN pips away
**Stop:** NNN.NN — NN pips below/above

### Other Scenarios
- Alternative: [status]
- Tail Risk: [status]
```

## Job 2 — Scorecard Logic

### Scoring Rules

For each scenario:
- **HIT:** Key level reached AND projected direction played out (target hit or > 50% toward target)
- **PARTIAL:** Trigger fired but target not reached (right direction, insufficient magnitude)
- **MISS:** Scenario expected but didn't materialize
- **NO TRADE:** Price never reached any entry zone (flat/ranging)

### Additional Tracking
- Actual high / low / close during 12h window
- Best-matching scenario
- Entry zone hit (yes/no)
- Theoretical P&L (entry to 12h close, if zone was hit)
- MAE (Maximum Adverse Excursion — worst drawdown from entry)
- MFE (Maximum Favorable Excursion — best move toward target)

### Scorecard Storage

Append one row per SMC report to: `./output/scorecard/scenario_log.csv`

Columns:
```
date, generation_time, direction, grade, setup_type,
entry_price, stop_price, target1_price, target2_price,
scenario1_name, scenario1_prob, scenario1_outcome,
scenario2_name, scenario2_prob, scenario2_outcome,
scenario3_name, scenario3_prob, scenario3_outcome,
best_match, entry_zone_hit, actual_high, actual_low, actual_close,
theoretical_pl_pips, mae_pips, mfe_pips
```

### Running Stats (after 10+ rows)
- Primary scenario accuracy: (HIT + PARTIAL) / total
- Alternative scenario accuracy
- Tail risk frequency
- Average theoretical P&L by grade (A+ vs B vs C)
- Setup type performance
- Entry zone hit rate

### Output Format

```markdown
## Module 09 — Scenario Scorecard
**SMC Report:** YYYY-MM-DD HH:MM JST
**Window:** HH:MM — HH:MM JST (12h closed)

### Result: [SCENARIO] — [OUTCOME]

**Actual price action:**
- High: NNN.NN (at HH:MM JST)
- Low: NNN.NN (at HH:MM JST)
- Close: NNN.NN (at HH:MM JST)

**Scenario outcomes:**
| Scenario | Projected | Actual | Score |
|----------|-----------|--------|-------|
| ... | ... | ... | ... |

**Best match:** [scenario] (NN% path similarity)
**Theoretical P&L:** +/- NN pips
**MAE:** -NN pips | **MFE:** +NN pips

### Running Stats (N=NN reports)
| Metric | Value |
|--------|-------|
| Primary accuracy | NN% |
| Entry zone hit rate | NN% |
| Avg theoretical P&L | +NN pips |
```

## Email

- Live check subject: `USD/JPY Monitor — [SCENARIO NAME] [STATUS]`
- Scorecard subject: `USD/JPY Scorecard — [RESULT] [P&L]`
- Both: `.md` attachment only (no PDF)

## Commands

- `/usdjpy-monitor` — Run live check (Job 1)
- `/usdjpy-scorecard` — Run scorecard (Job 2)

## Script

`python3 scripts/run_scenario_monitor.py --mode check|scorecard`
