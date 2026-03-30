# Module 02 — Policy & Politics

## Purpose
Track BOJ and Fed policy stances, upcoming meeting dates, MOF intervention risk signals, and Japanese political developments that affect fiscal/monetary policy expectations.

## Status: IMPLEMENTED (Phase 3)

## Data Sources
- BOJ policy decisions: web search for latest meeting outcome
- Fed FOMC statements: web search for latest decision
- MOF intervention risk: computed from Module 01 USD/JPY price data + web search for rhetoric
- Japanese political developments: web search (weekly only)
- Cache: `./data/raw/central_bank_YYYY-MM-DD.json` (valid until next meeting date)
- Run: `python3 run_cb_analysis.py`

## Key Signals
- Policy rate trajectory (hiking / holding / cutting) for both BOJ and Fed
- Hawkish/dovish language shift detection
- Next meeting date countdown
- MOF verbal intervention tracker (keywords: "excessive", "one-sided", "appropriate action")
- Intervention probability estimate based on USD/JPY level + rate of change

## Japanese Political Developments (Weekly report only)

Use web search to check for:
- PM fiscal policy announcements or speeches (economic stimulus, fiscal packages)
- Cabinet changes affecting economic policy (Finance Minister, BOJ governor relations)
- Any Diet (parliament) votes on fiscal packages or supplementary budgets
- Election risk or polling changes that could shift economic policy direction

### Signal Logic
```
political_risk = LOW   # default

if expansionary_fiscal_announcement OR large_supplementary_budget:
    political_risk = HIGH → JPY-negative bias modifier
    reason = "Expansionary fiscal policy increases JGB supply / fiscal dominance fears"

if cabinet_reshuffle_affecting_economic_policy:
    political_risk = MEDIUM
    reason = "Policy continuity uncertain"

if election_risk_elevated OR snap_election_called:
    political_risk = HIGH
    reason = "Election uncertainty — policy direction at risk"

if no_notable_developments:
    political_risk = LOW
    reason = "No notable developments"
```

**Important:** Political risk is an additional bias modifier, not an override. It should be noted in the Module 02 narrative but does not replace the rate-based signal. When political_risk is HIGH, add a JPY-negative bias note to the module narrative.

**Do NOT run the political scan in the daily report.** This section is weekly only.

## Output Format
```markdown
## 02 — Policy & Politics

**BOJ Stance:** {Hiking / Holding / Cutting} — Rate: {X.XX%}, Next meeting: {date}
**Fed Stance:** {Hiking / Holding / Cutting} — Rate: {X.XX%}, Next meeting: {date}
**Policy Divergence:** {Widening / Narrowing / Stable}
**Intervention Risk:** {LOW / MEDIUM / HIGH} — {reasoning}

### Japanese Political Developments (weekly only)
**Political Risk:** {LOW / MEDIUM / HIGH}
**Key Development:** {1 sentence summary or "No notable developments"}

**Bias:** {BULLISH / BEARISH / NEUTRAL}
```
