# Validation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent validation pipeline that cross-references our calculated values against Yahoo Finance, Investing.com, and TradingView, pushes results to Supabase, and displays them on a `/validation` dashboard page.

**Architecture:** A standalone `scripts/run_validation.py` runs as a separate CI job 30min after each report. It reads our report's `module_data` from Supabase, independently fetches the same indicators from 2-3 external sources, compares with configurable tolerances, and pushes per-indicator pass/warn/fail results to a `validation` Supabase table. The dashboard gets a new `/validation` page.

**Tech Stack:** Python (yfinance, requests, beautifulsoup4), Supabase (postgres + JS SDK), Next.js 16 (App Router), Tailwind CSS v4

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/run_validation.py` | Create | Main orchestrator: read from Supabase, fetch external, compare, push results |
| `scripts/validation_sources.py` | Create | External source fetchers: Yahoo, Investing.com, TradingView |
| `scripts/push_to_supabase.py` | Modify | Add `push_validation_results()` function |
| `config.yaml` | Modify | Add `validation:` section with tolerances and source toggles |
| `requirements.txt` | Modify | Add `beautifulsoup4>=4.9` |
| `.github/workflows/usdjpy-reports.yml` | Modify | Add validation cron schedules and run step |
| `dashboard/src/app/validation/page.tsx` | Create | Validation dashboard page |
| `dashboard/src/components/Navigation.tsx` | Modify | Add validation nav item |
| `dashboard/src/lib/supabase.ts` | Modify | Add `ValidationResult` type |
| `dashboard/src/lib/i18n.ts` | Modify | Add validation translation keys |

---

### Task 1: Supabase Migration — Create `validation` Table

**Files:**
- None (Supabase MCP tool)

- [ ] **Step 1: Apply migration**

Use the Supabase MCP `apply_migration` tool with project_id `vyymfdlzjbgrgcrlfvff`:

```sql
CREATE TABLE validation (
    id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    report_id uuid REFERENCES reports(id),
    date date NOT NULL,
    module text NOT NULL,
    indicator text NOT NULL,
    our_value numeric,
    source_name text NOT NULL,
    source_value numeric,
    tolerance numeric,
    diff numeric,
    status text NOT NULL CHECK (status IN ('PASS', 'WARN', 'FAIL', 'SKIP')),
    checked_at timestamptz DEFAULT now()
);

CREATE INDEX idx_validation_date ON validation (date);
CREATE INDEX idx_validation_date_module ON validation (date, module);

ALTER TABLE validation ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read" ON validation FOR SELECT USING (true);
```

- [ ] **Step 2: Verify table exists**

Run SQL via Supabase MCP:

```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'validation' ORDER BY ordinal_position;
```

Expected: 12 columns matching the spec (id, report_id, date, module, indicator, our_value, source_name, source_value, tolerance, diff, status, checked_at).

- [ ] **Step 3: Commit** (nothing to commit — migration is remote-only)

---

### Task 2: Config + Dependencies

**Files:**
- Modify: `config.yaml` (add after `supabase:` section, before `schedule:`)
- Modify: `requirements.txt` (add beautifulsoup4)

- [ ] **Step 1: Add validation config to `config.yaml`**

Add this block after the `supabase:` section and before `schedule:`:

```yaml
validation:
  enabled: true
  tolerances:
    rsi: 2.0          # points
    sma: 0.05         # yen
    macd: 0.02        # yen
    spot_pct: 0.001   # 0.1%
    correlation: 0.05  # absolute
    spread_pct: 0.0005 # 0.05%
  sources:
    yahoo: true
    investing: true
    tradingview: true
```

- [ ] **Step 2: Add beautifulsoup4 to `requirements.txt`**

Add this line after `requests>=2.28`:

```
beautifulsoup4>=4.9
```

- [ ] **Step 3: Install locally**

Run: `pip install beautifulsoup4>=4.9`

- [ ] **Step 4: Commit**

```bash
git add config.yaml requirements.txt
git commit -m "feat: add validation config and beautifulsoup4 dependency"
```

---

### Task 3: External Source Fetchers (`validation_sources.py`)

**Files:**
- Create: `scripts/validation_sources.py`

This module provides three fetcher functions. Each returns a dict of `{indicator_name: value}` or an empty dict on failure. All fetchers are wrapped in try/except so a broken source never crashes the validator.

- [ ] **Step 1: Create `scripts/validation_sources.py`**

```python
"""
validation_sources.py — Fetch reference indicator values from external sources.

Each fetch_* function returns a dict of {indicator_name: float_value}.
On failure, returns an empty dict (never raises).
"""

import datetime as dt
import re
import traceback

import numpy as np
import pandas as pd
import requests
import yfinance as yf


# ── Yahoo Finance ─────────────────────────────────────────────────────────

def fetch_yahoo(config):
    """Fetch USDJPY price + recalculate technicals from Yahoo Finance OHLC."""
    try:
        ticker = yf.Ticker("USDJPY=X")
        df = ticker.history(period="6mo", interval="1d")
        if df.empty:
            print("    [yahoo] No data returned")
            return {}

        results = {}
        close = df["Close"]
        latest = float(close.iloc[-1])
        results["spot_usdjpy"] = latest

        # SMA
        tech = config.get("technicals", {})
        for period in tech.get("sma_periods", [50, 200]):
            if len(close) >= period:
                results[f"sma_{period}"] = float(close.rolling(period).mean().iloc[-1])

        # RSI
        rsi_period = tech.get("rsi_period", 14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        results["rsi_14"] = float(rsi.iloc[-1])

        # MACD
        macd_cfg = tech.get("macd", {"fast": 12, "slow": 26, "signal": 9})
        ema_fast = close.ewm(span=macd_cfg["fast"], adjust=False).mean()
        ema_slow = close.ewm(span=macd_cfg["slow"], adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=macd_cfg["signal"], adjust=False).mean()
        results["macd_line"] = float(macd_line.iloc[-1])
        results["macd_signal"] = float(signal_line.iloc[-1])

        # Ichimoku
        ichimoku = tech.get("ichimoku", {"tenkan": 9, "kijun": 26, "senkou_b": 52})
        high = df["High"]
        low = df["Low"]

        tenkan = (high.rolling(ichimoku["tenkan"]).max() + low.rolling(ichimoku["tenkan"]).min()) / 2
        kijun = (high.rolling(ichimoku["kijun"]).max() + low.rolling(ichimoku["kijun"]).min()) / 2
        results["ichimoku_tenkan"] = float(tenkan.iloc[-1])
        results["ichimoku_kijun"] = float(kijun.iloc[-1])

        # Cross-asset spot prices
        cross_assets = {
            "spot_sp500": "^GSPC",
            "spot_nikkei": "^N225",
            "spot_gold": "GC=F",
            "spot_vix": "^VIX",
            "spot_wti": "CL=F",
            "spot_dxy": "DX-Y.NYB",
        }
        for key, sym in cross_assets.items():
            try:
                t = yf.Ticker(sym)
                h = t.history(period="5d", interval="1d")
                if not h.empty:
                    results[key] = float(h["Close"].iloc[-1])
            except Exception:
                pass

        print(f"    [yahoo] Fetched {len(results)} indicators")
        return results

    except Exception as e:
        print(f"    [yahoo] Failed: {e}")
        traceback.print_exc()
        return {}


# ── Investing.com ─────────────────────────────────────────────────────────

def fetch_investing():
    """Scrape USDJPY technicals from Investing.com."""
    try:
        from bs4 import BeautifulSoup

        url = "https://www.investing.com/currencies/usd-jpy-technical"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"    [investing] HTTP {resp.status_code}")
            return {}

        soup = BeautifulSoup(resp.text, "html.parser")
        results = {}

        # Parse technical indicators table
        # Investing.com shows RSI(14), SMA(50), SMA(200), MACD in a summary table
        for row in soup.select("table.technicalIndicatorsTbl tr"):
            cells = row.select("td")
            if len(cells) >= 2:
                name = cells[0].get_text(strip=True).lower()
                try:
                    value = float(cells[1].get_text(strip=True).replace(",", ""))
                except (ValueError, IndexError):
                    continue

                if "rsi(14)" in name:
                    results["rsi_14"] = value
                elif "sma(50)" in name:
                    results["sma_50"] = value
                elif "sma(200)" in name:
                    results["sma_200"] = value
                elif "macd(12,26)" in name:
                    results["macd_line"] = value

        print(f"    [investing] Fetched {len(results)} indicators")
        return results

    except Exception as e:
        print(f"    [investing] Failed: {e}")
        traceback.print_exc()
        return {}


# ── TradingView ───────────────────────────────────────────────────────────

def fetch_tradingview():
    """Fetch USDJPY technicals from TradingView's unofficial widget API."""
    try:
        # TradingView provides a public technical analysis API
        url = "https://scanner.tradingview.com/forex/scan"
        payload = {
            "symbols": {"tickers": ["FX:USDJPY"]},
            "columns": [
                "close", "RSI", "RSI[1]",
                "SMA50", "SMA200",
                "MACD.macd", "MACD.signal",
                "Ichimoku.BLine", "Ichimoku.CLine",
            ],
        }
        headers = {"Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"    [tradingview] HTTP {resp.status_code}")
            return {}

        data = resp.json()
        if not data.get("data"):
            print("    [tradingview] No data in response")
            return {}

        values = data["data"][0].get("d", [])
        columns = ["close", "rsi_14", "rsi_14_prev",
                    "sma_50", "sma_200",
                    "macd_line", "macd_signal",
                    "ichimoku_kijun", "ichimoku_tenkan"]

        results = {}
        for col, val in zip(columns, values):
            if val is not None and col != "rsi_14_prev":
                if col == "close":
                    results["spot_usdjpy"] = float(val)
                else:
                    results[col] = float(val)

        print(f"    [tradingview] Fetched {len(results)} indicators")
        return results

    except Exception as e:
        print(f"    [tradingview] Failed: {e}")
        traceback.print_exc()
        return {}
```

- [ ] **Step 2: Verify imports work**

Run: `cd /Users/chiaoe/projects/claude_code/usdjpy-analyst && python -c "from scripts.validation_sources import fetch_yahoo, fetch_investing, fetch_tradingview; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/validation_sources.py
git commit -m "feat: add external source fetchers for validation (yahoo, investing, tradingview)"
```

---

### Task 4: Supabase Push Function

**Files:**
- Modify: `scripts/push_to_supabase.py` (add `push_validation_results()` after `push_scorecard()`)

- [ ] **Step 1: Add `push_validation_results()` to `push_to_supabase.py`**

Add this function after the `push_scorecard()` function (around line 1003):

```python
def push_validation_results(results, report_date):
    """Push validation results to Supabase.

    results: list of dicts with keys matching the validation table columns.
    report_date: YYYY-MM-DD string.
    """
    if not results:
        print("  No validation results to push.")
        return

    print(f"  Pushing {len(results)} validation results to Supabase...")
    client = get_supabase_client()

    # Find report_id for linking (optional)
    report_id = None
    report_res = client.table("reports").select("id").eq(
        "date", report_date
    ).eq("report_type", "daily").execute()
    if report_res.data:
        report_id = report_res.data[0]["id"]

    # Delete existing validation for this date (re-run safe)
    client.table("validation").delete().eq("date", report_date).execute()

    # Build rows
    rows = []
    for r in results:
        rows.append({
            "report_id": report_id,
            "date": report_date,
            "module": r["module"],
            "indicator": r["indicator"],
            "our_value": r["our_value"],
            "source_name": r["source_name"],
            "source_value": r["source_value"],
            "tolerance": r["tolerance"],
            "diff": r["diff"],
            "status": r["status"],
        })

    # Insert in batches of 50
    for i in range(0, len(rows), 50):
        batch = rows[i:i + 50]
        client.table("validation").insert(batch).execute()

    print(f"    Validation results pushed ({len(rows)} rows)")
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import scripts.push_to_supabase; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/push_to_supabase.py
git commit -m "feat: add push_validation_results() to Supabase push module"
```

---

### Task 5: Main Validation Script (`run_validation.py`)

**Files:**
- Create: `scripts/run_validation.py`

- [ ] **Step 1: Create `scripts/run_validation.py`**

```python
"""
run_validation.py — Cross-reference report calculations against external sources.

Reads the latest report's module_data from Supabase, fetches the same indicators
from Yahoo Finance / Investing.com / TradingView, compares with configurable
tolerances, and pushes per-indicator PASS/WARN/FAIL results back to Supabase.

Usage:
    python scripts/run_validation.py [--date YYYY-MM-DD]
"""

import argparse
import datetime as dt
import json
import os
import sys

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

JST = dt.timezone(dt.timedelta(hours=9))


def load_config():
    config_path = os.path.join(PROJECT_ROOT, "config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_report_from_supabase(report_date):
    """Fetch the daily report's module_data from Supabase."""
    from scripts.push_to_supabase import get_supabase_client

    client = get_supabase_client()

    # Try daily first, fall back to weekly
    for rtype in ("daily", "weekly"):
        result = client.table("reports").select("id, module_data").eq(
            "date", report_date
        ).eq("report_type", rtype).execute()
        if result.data and result.data[0].get("module_data"):
            md = result.data[0]["module_data"]
            if isinstance(md, str):
                md = json.loads(md)
            return md

    return None


def get_smc_report_from_supabase(report_date):
    """Fetch SMC report data (zones, levels) from Supabase."""
    from scripts.push_to_supabase import get_supabase_client

    client = get_supabase_client()
    result = client.table("reports").select("id, entry_price, stop_price, target1_price").eq(
        "date", report_date
    ).eq("report_type", "smc").execute()
    if result.data:
        return result.data[0]
    return None


def extract_our_values(module_data):
    """Extract numeric indicator values from our report's module_data."""
    values = {}

    # Module 01 — Macro
    m01 = module_data.get("module_01", {})
    if m01.get("us_10y") is not None:
        values[("01", "us_10y")] = float(m01["us_10y"])
    if m01.get("jp_10y") is not None:
        values[("01", "jp_10y")] = float(m01["jp_10y"])
    if m01.get("spread") is not None:
        values[("01", "rate_spread")] = float(m01["spread"])
    if m01.get("dxy") is not None:
        values[("01", "spot_dxy")] = float(m01["dxy"])

    # Module 03 — Technicals
    m03 = module_data.get("module_03", {})
    if m03.get("price") is not None:
        values[("03", "spot_usdjpy")] = float(m03["price"])
    if m03.get("rsi") is not None:
        values[("03", "rsi_14")] = float(m03["rsi"])
    if m03.get("sma_50") is not None:
        values[("03", "sma_50")] = float(m03["sma_50"])
    if m03.get("sma_200") is not None:
        values[("03", "sma_200")] = float(m03["sma_200"])
    if m03.get("macd_line") is not None:
        values[("03", "macd_line")] = float(m03["macd_line"])
    if m03.get("macd_signal") is not None:
        values[("03", "macd_signal")] = float(m03["macd_signal"])

    # Module 05 — Cross-Asset
    m05 = module_data.get("module_05", {})
    correlations = m05.get("correlations", {})
    for asset, corr_val in correlations.items():
        if corr_val is not None:
            values[("05", f"corr_{asset.lower()}")] = float(corr_val)

    return values


def get_tolerance(indicator, tolerances):
    """Look up the tolerance for a given indicator name."""
    if "rsi" in indicator:
        return tolerances.get("rsi", 2.0)
    if "sma" in indicator:
        return tolerances.get("sma", 0.05)
    if "macd" in indicator:
        return tolerances.get("macd", 0.02)
    if "corr" in indicator:
        return tolerances.get("correlation", 0.05)
    if "spread" in indicator:
        return tolerances.get("spread_pct", 0.0005)
    if "spot" in indicator or "dxy" in indicator:
        return tolerances.get("spot_pct", 0.001)
    return 1.0  # generous default


def compute_diff(our_val, source_val, indicator):
    """Compute the difference. Percentage for spot prices, absolute for others."""
    if "spot" in indicator or "dxy" in indicator or "spread" in indicator:
        # Percentage difference
        if our_val == 0:
            return abs(source_val)
        return abs(source_val - our_val) / abs(our_val)
    else:
        # Absolute difference
        return abs(source_val - our_val)


def classify_status(diff, tolerance):
    """PASS if within tolerance, WARN if 1-2x, FAIL if >2x."""
    if diff <= tolerance:
        return "PASS"
    elif diff <= tolerance * 2:
        return "WARN"
    else:
        return "FAIL"


def run_validation(report_date, config):
    """Main validation logic."""
    val_config = config.get("validation", {})
    if not val_config.get("enabled", True):
        print("Validation disabled in config.")
        return []

    tolerances = val_config.get("tolerances", {})
    sources_enabled = val_config.get("sources", {})

    # 1. Read our report data from Supabase
    print(f"Validating report for {report_date}...")
    module_data = get_report_from_supabase(report_date)
    if not module_data:
        print(f"  No report found in Supabase for {report_date}. Exiting.")
        return []

    our_values = extract_our_values(module_data)
    print(f"  Extracted {len(our_values)} indicators from our report")

    if not our_values:
        print("  No numeric indicators found. Exiting.")
        return []

    # 2. Fetch external reference values
    from scripts.validation_sources import fetch_yahoo, fetch_investing, fetch_tradingview

    external = {}
    if sources_enabled.get("yahoo", True):
        external["yahoo"] = fetch_yahoo(config)
    if sources_enabled.get("investing", True):
        external["investing"] = fetch_investing()
    if sources_enabled.get("tradingview", True):
        external["tradingview"] = fetch_tradingview()

    # 3. Compare
    results = []
    for (module, indicator), our_val in our_values.items():
        matched_any = False
        for source_name, source_data in external.items():
            if indicator in source_data:
                matched_any = True
                source_val = source_data[indicator]
                tol = get_tolerance(indicator, tolerances)
                diff = compute_diff(our_val, source_val, indicator)
                status = classify_status(diff, tol)

                results.append({
                    "module": module,
                    "indicator": indicator,
                    "our_value": round(our_val, 6),
                    "source_name": source_name,
                    "source_value": round(source_val, 6),
                    "tolerance": tol,
                    "diff": round(diff, 6),
                    "status": status,
                })

        # If no source had this indicator, mark SKIP
        if not matched_any:
            results.append({
                "module": module,
                "indicator": indicator,
                "our_value": round(our_val, 6),
                "source_name": "none",
                "source_value": None,
                "tolerance": get_tolerance(indicator, tolerances),
                "diff": None,
                "status": "SKIP",
            })

    return results


def print_summary(results):
    """Print a human-readable summary to stdout."""
    if not results:
        print("\nNo validation results.")
        return

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    warn_count = sum(1 for r in results if r["status"] == "WARN")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    total = len(results)

    print(f"\n{'='*60}")
    print(f"  Validation Summary: {pass_count}/{total} PASS")
    print(f"  PASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  SKIP={skip_count}")
    print(f"{'='*60}")

    # Print failures and warnings
    for r in results:
        if r["status"] in ("FAIL", "WARN"):
            print(f"  [{r['status']}] Module {r['module']} | {r['indicator']}: "
                  f"ours={r['our_value']} vs {r['source_name']}={r['source_value']} "
                  f"(diff={r['diff']}, tol={r['tolerance']})")


def main():
    parser = argparse.ArgumentParser(description="Cross-reference validation")
    parser.add_argument("--date", help="Report date (YYYY-MM-DD). Default: today JST.")
    parser.add_argument("--no-push", action="store_true", help="Skip Supabase push")
    args = parser.parse_args()

    if args.date:
        report_date = args.date
    else:
        report_date = dt.datetime.now(JST).strftime("%Y-%m-%d")

    config = load_config()
    results = run_validation(report_date, config)
    print_summary(results)

    # 4. Push to Supabase
    if results and not args.no_push:
        try:
            from scripts.push_to_supabase import push_validation_results
            push_validation_results(results, report_date)
        except Exception as e:
            print(f"  Supabase push failed (non-blocking): {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script parses**

Run: `python -c "import ast; ast.parse(open('scripts/run_validation.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add scripts/run_validation.py
git commit -m "feat: add run_validation.py — cross-reference validation orchestrator"
```

---

### Task 6: CI Integration

**Files:**
- Modify: `.github/workflows/usdjpy-reports.yml`

- [ ] **Step 1: Add validation cron schedules**

In the `schedule:` section (lines 4-16), add two new cron entries:

```yaml
    # 09:00 JST = 00:00 UTC — Validation (30min after morning report)
    - cron: '0 0 * * 1-5'
    # 17:00 JST = 08:00 UTC — Validation (30min after afternoon SMC)
    - cron: '0 8 * * 1-5'
```

- [ ] **Step 2: Add `validation` to workflow_dispatch options**

In the `report_type` choices (lines 23-30), add `validation`:

```yaml
        options:
          - all
          - daily
          - weekly
          - smc
          - monitor
          - scorecard
          - validation
```

- [ ] **Step 3: Add validation flag to defaults and manual trigger**

In the defaults section (line 74), add:

```bash
echo "validation=false" >> $GITHUB_OUTPUT
```

In the manual trigger block (lines 77-95), add:

```bash
if [ "$TYPE" = "all" ] || [ "$TYPE" = "validation" ]; then
  echo "validation=true" >> $GITHUB_OUTPUT
fi
```

- [ ] **Step 4: Add validation to scheduled trigger UTC hour checks**

In the scheduled trigger section (lines 98-128), add two new `elif` branches:

```bash
elif [ "$HOUR_UTC" -eq 0 ]; then
  # 00:00 UTC = 09:00 JST — Validation (morning)
  echo "type=validation-am" >> $GITHUB_OUTPUT
  echo "validation=true" >> $GITHUB_OUTPUT
elif [ "$HOUR_UTC" -eq 8 ] && [ "$(echo $HOUR_UTC)" -eq 8 ]; then
  # 08:00 UTC = 17:00 JST — Validation (afternoon)
  echo "type=validation-pm" >> $GITHUB_OUTPUT
  echo "validation=true" >> $GITHUB_OUTPUT
```

Note: The 08:00 UTC slot conflicts with the existing 07:30 UTC afternoon SMC check (which uses `HOUR_UTC == 7`). Since we use `HOUR_UTC -eq 8` specifically, this is safe — cron fires at :00, not :30.

- [ ] **Step 5: Add Run Validation step**

Add this step after the "Run Scorecard" step and before "Commit scorecard data":

```yaml
      - name: Run Validation
        if: steps.run-type.outputs.validation == 'true'
        id: validation
        continue-on-error: true
        env:
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: |
          python scripts/run_validation.py
          echo "status=success" >> $GITHUB_OUTPUT
```

- [ ] **Step 6: Add validation to summary table**

In the Summary step, add:

```bash
echo "| Validation | ${{ steps.validation.outcome || 'skipped' }} |" >> $GITHUB_STEP_SUMMARY
```

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/usdjpy-reports.yml
git commit -m "feat: add validation CI job — runs 30min after morning/afternoon reports"
```

---

### Task 7: Dashboard — TypeScript Types + Supabase

**Files:**
- Modify: `dashboard/src/lib/supabase.ts` (add `ValidationResult` interface)

- [ ] **Step 1: Add `ValidationResult` type**

Add this interface after the `JournalEntry` interface (around line 117):

```typescript
export interface ValidationResult {
  id: string;
  report_id: string | null;
  date: string;
  module: string;
  indicator: string;
  our_value: number | null;
  source_name: string;
  source_value: number | null;
  tolerance: number | null;
  diff: number | null;
  status: "PASS" | "WARN" | "FAIL" | "SKIP";
  checked_at: string;
}
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/lib/supabase.ts
git commit -m "feat: add ValidationResult type to Supabase client"
```

---

### Task 8: Dashboard — i18n Translation Keys

**Files:**
- Modify: `dashboard/src/lib/i18n.ts`

- [ ] **Step 1: Add English validation translations**

Add after the `journal.*` keys (around line 157), before the `common.*` keys:

```typescript
    // Validation
    "validation.title": "Validation",
    "validation.summary": "Validation Summary",
    "validation.passRate": "Pass Rate",
    "validation.lastChecked": "Last Checked",
    "validation.module": "Module",
    "validation.indicator": "Indicator",
    "validation.ourValue": "Our Value",
    "validation.source": "Source",
    "validation.sourceValue": "Source Value",
    "validation.diff": "Diff",
    "validation.tolerance": "Tolerance",
    "validation.status": "Status",
    "validation.noData": "No validation data yet. Validation runs automatically 30min after each report.",
    "validation.pass": "PASS",
    "validation.warn": "WARN",
    "validation.fail": "FAIL",
    "validation.skip": "SKIP",
    "validation.module01": "Macro Regime",
    "validation.module03": "Technicals",
    "validation.module05": "Cross-Asset",
    "validation.module07": "Checklist",
    "validation.module08": "SMC",
```

- [ ] **Step 2: Add Chinese validation translations**

Add in the `zh` section at the equivalent position:

```typescript
    "validation.title": "驗證",
    "validation.summary": "驗證摘要",
    "validation.passRate": "通過率",
    "validation.lastChecked": "最後檢查",
    "validation.module": "模組",
    "validation.indicator": "指標",
    "validation.ourValue": "我們的值",
    "validation.source": "來源",
    "validation.sourceValue": "來源值",
    "validation.diff": "差異",
    "validation.tolerance": "容差",
    "validation.status": "狀態",
    "validation.noData": "尚無驗證資料。驗證在每份報告後30分鐘自動執行。",
    "validation.pass": "通過",
    "validation.warn": "警告",
    "validation.fail": "失敗",
    "validation.skip": "跳過",
    "validation.module01": "宏觀環境",
    "validation.module03": "技術分析",
    "validation.module05": "跨資產",
    "validation.module07": "檢查清單",
    "validation.module08": "SMC",
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/lib/i18n.ts
git commit -m "feat: add validation i18n keys (EN + ZH)"
```

---

### Task 9: Dashboard — Navigation

**Files:**
- Modify: `dashboard/src/components/Navigation.tsx` (add validation nav item)

- [ ] **Step 1: Add validation nav item**

In the `navItems` array, add this entry between scorecard and journal (between lines 12 and 13):

```typescript
  { href: "/validation", labelKey: "nav.validation", icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" },
```

- [ ] **Step 2: Add nav translation keys**

In `dashboard/src/lib/i18n.ts`, add to both EN and ZH nav sections:

EN (after `"nav.scorecard"`):
```typescript
    "nav.validation": "Validation",
```

ZH (after `"nav.scorecard"`):
```typescript
    "nav.validation": "驗證",
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/Navigation.tsx dashboard/src/lib/i18n.ts
git commit -m "feat: add Validation to dashboard navigation"
```

---

### Task 10: Dashboard — Validation Page

**Files:**
- Create: `dashboard/src/app/validation/page.tsx`

**Important:** Before writing any Next.js code, read `node_modules/next/dist/docs/` in the dashboard directory to check for API changes in Next.js 16. The dashboard's `AGENTS.md` warns that this version has breaking changes.

- [ ] **Step 1: Create `dashboard/src/app/validation/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { supabase, type ValidationResult } from "@/lib/supabase";
import { useLocale } from "@/lib/providers";
import type { TranslationKey } from "@/lib/i18n";

interface ModuleSummary {
  module: string;
  total: number;
  pass: number;
  warn: number;
  fail: number;
  skip: number;
  items: ValidationResult[];
}

const MODULE_NAMES: Record<string, TranslationKey> = {
  "01": "validation.module01",
  "03": "validation.module03",
  "05": "validation.module05",
  "07": "validation.module07",
  "08": "validation.module08",
};

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    PASS: "bg-bull/20 text-bull",
    WARN: "bg-yellow-500/20 text-yellow-400",
    FAIL: "bg-bear/20 text-bear",
    SKIP: "bg-text-muted/20 text-text-muted",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-medium ${colors[status] || ""}`}>
      {status}
    </span>
  );
}

function PassRateCard({ results, lastChecked, t }: {
  results: ValidationResult[];
  lastChecked: string | null;
  t: (key: TranslationKey) => string;
}) {
  const total = results.filter((r) => r.status !== "SKIP").length;
  const passed = results.filter((r) => r.status === "PASS").length;
  const rate = total > 0 ? (passed / total) * 100 : 0;
  const color = rate >= 90 ? "text-bull" : rate >= 75 ? "text-yellow-400" : "text-bear";

  return (
    <div className="bg-bg-card border border-border rounded-xl p-6">
      <div className="text-sm text-text-secondary mb-1">{t("validation.passRate")}</div>
      <div className={`text-4xl font-bold font-mono ${color}`}>
        {passed}/{total}
      </div>
      <div className={`text-lg font-mono ${color}`}>{rate.toFixed(0)}%</div>
      {lastChecked && (
        <div className="text-xs text-text-muted mt-2">
          {t("validation.lastChecked")}: {new Date(lastChecked).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo" })}
        </div>
      )}
    </div>
  );
}

function ModuleRow({ summary, t }: { summary: ModuleSummary; t: (key: TranslationKey) => string }) {
  const [expanded, setExpanded] = useState(false);
  const worstStatus = summary.fail > 0 ? "FAIL" : summary.warn > 0 ? "WARN" : "PASS";
  const labelKey = MODULE_NAMES[summary.module] || ("validation.module" + summary.module as TranslationKey);

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-card-hover transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm text-text-muted">M{summary.module}</span>
          <span className="font-medium">{t(labelKey)}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-text-secondary font-mono">
            {summary.pass}/{summary.total - summary.skip}
          </span>
          <StatusBadge status={worstStatus} />
          <svg
            className={`w-4 h-4 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-muted text-xs">
                <th className="text-left px-4 py-2">{t("validation.indicator")}</th>
                <th className="text-right px-4 py-2">{t("validation.ourValue")}</th>
                <th className="text-left px-4 py-2">{t("validation.source")}</th>
                <th className="text-right px-4 py-2">{t("validation.sourceValue")}</th>
                <th className="text-right px-4 py-2">{t("validation.diff")}</th>
                <th className="text-right px-4 py-2">{t("validation.tolerance")}</th>
                <th className="text-center px-4 py-2">{t("validation.status")}</th>
              </tr>
            </thead>
            <tbody>
              {summary.items.map((item) => (
                <tr
                  key={item.id}
                  className={`border-t border-border/50 ${
                    item.status === "FAIL" ? "bg-bear/5" : item.status === "WARN" ? "bg-yellow-500/5" : ""
                  }`}
                >
                  <td className="px-4 py-2 font-mono">{item.indicator}</td>
                  <td className="px-4 py-2 text-right font-mono">{item.our_value?.toFixed(4) ?? "—"}</td>
                  <td className="px-4 py-2 text-text-secondary">{item.source_name}</td>
                  <td className="px-4 py-2 text-right font-mono">{item.source_value?.toFixed(4) ?? "—"}</td>
                  <td className="px-4 py-2 text-right font-mono">{item.diff?.toFixed(4) ?? "—"}</td>
                  <td className="px-4 py-2 text-right font-mono text-text-muted">{item.tolerance ?? "—"}</td>
                  <td className="px-4 py-2 text-center"><StatusBadge status={item.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function ValidationPage() {
  const { t } = useLocale();
  const [results, setResults] = useState<ValidationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [availableDates, setAvailableDates] = useState<string[]>([]);

  // Fetch available dates
  useEffect(() => {
    async function fetchDates() {
      const res = await supabase
        .from("validation")
        .select("date")
        .order("date", { ascending: false })
        .limit(30);
      if (res.data) {
        const unique = [...new Set(res.data.map((r) => r.date))];
        setAvailableDates(unique);
        if (unique.length > 0 && !selectedDate) {
          setSelectedDate(unique[0]);
        }
      }
    }
    fetchDates();
  }, []);

  // Fetch results for selected date
  useEffect(() => {
    if (!selectedDate) return;
    async function fetchResults() {
      setLoading(true);
      const res = await supabase
        .from("validation")
        .select("*")
        .eq("date", selectedDate)
        .order("module", { ascending: true })
        .order("indicator", { ascending: true });
      setResults(res.data || []);
      setLoading(false);
    }
    fetchResults();
  }, [selectedDate]);

  // Group by module
  const modules: ModuleSummary[] = [];
  const grouped = new Map<string, ValidationResult[]>();
  for (const r of results) {
    if (!grouped.has(r.module)) grouped.set(r.module, []);
    grouped.get(r.module)!.push(r);
  }
  for (const [mod, items] of grouped) {
    modules.push({
      module: mod,
      total: items.length,
      pass: items.filter((i) => i.status === "PASS").length,
      warn: items.filter((i) => i.status === "WARN").length,
      fail: items.filter((i) => i.status === "FAIL").length,
      skip: items.filter((i) => i.status === "SKIP").length,
      items,
    });
  }

  const lastChecked = results.length > 0 ? results[0].checked_at : null;

  if (loading) {
    return <div className="p-6 text-text-secondary">{t("common.loading")}</div>;
  }

  if (results.length === 0) {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">{t("validation.title")}</h1>
        <p className="text-text-secondary">{t("validation.noData")}</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t("validation.title")}</h1>
        <select
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="bg-bg-card border border-border rounded-lg px-3 py-1.5 text-sm"
        >
          {availableDates.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      <PassRateCard results={results} lastChecked={lastChecked} t={t} />

      <div className="space-y-3">
        {modules.map((m) => (
          <ModuleRow key={m.module} summary={m} t={t} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run from the dashboard directory:

```bash
cd /Users/chiaoe/projects/claude_code/usdjpy-analyst/dashboard && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/app/validation/page.tsx
git commit -m "feat: add /validation dashboard page with module breakdown and indicator detail"
```

---

### Task 11: End-to-End Test — Local Dry Run

**Files:**
- None (verification only)

- [ ] **Step 1: Run validation locally with `--no-push`**

```bash
cd /Users/chiaoe/projects/claude_code/usdjpy-analyst
python scripts/run_validation.py --date 2026-03-31 --no-push
```

Expected: Script prints indicator count, fetches from external sources, shows PASS/WARN/FAIL summary. No Supabase push.

- [ ] **Step 2: Run validation with Supabase push**

```bash
python scripts/run_validation.py --date 2026-03-31
```

Expected: Results pushed to Supabase. Check with SQL:

```sql
SELECT module, indicator, status, source_name, diff
FROM validation WHERE date = '2026-03-31'
ORDER BY module, indicator;
```

- [ ] **Step 3: Verify dashboard page**

Open `https://smcpulse.com/validation` (or local dev server) and confirm:
- Summary card shows pass rate
- Module rows expand to show indicator details
- Date picker works

- [ ] **Step 4: Final commit — push all changes**

```bash
git push
```

---

## Dependency Graph

```
Task 1 (DB migration)
Task 2 (config + deps)     ← no dependencies
Task 3 (source fetchers)   ← depends on Task 2 (beautifulsoup4)
Task 4 (Supabase push fn)  ← depends on Task 1 (table exists)
Task 5 (main script)       ← depends on Tasks 3, 4
Task 6 (CI integration)    ← depends on Task 5
Task 7 (TS types)          ← depends on Task 1
Task 8 (i18n keys)         ← no dependencies
Task 9 (navigation)        ← depends on Task 8
Task 10 (dashboard page)   ← depends on Tasks 7, 8, 9
Task 11 (E2E test)         ← depends on all above
```

Parallelizable groups:
- **Group A** (backend): Tasks 1, 2, then 3+4 in parallel, then 5, then 6
- **Group B** (frontend): Tasks 7+8 in parallel, then 9, then 10
- **Final**: Task 11 after both groups complete
