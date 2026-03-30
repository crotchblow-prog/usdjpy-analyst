#!/usr/bin/env python3
"""
Module 04 — CFTC Commitments of Traders (COT) positioning analysis for JPY futures.

Usage:
    python3 run_cot_analysis.py          # print summary to stdout
    python3 run_cot_analysis.py --json   # output JSON for integration

Data source: CFTC Legacy Futures report (deacmelf.htm)
Contract: Japanese Yen (097741), Chicago Mercantile Exchange
"""

import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, date
from pathlib import Path

# SSL context (macOS compatibility)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

BASE_DIR   = Path(__file__).parent
DATA_RAW   = BASE_DIR / "data" / "raw"
TODAY      = date(2026, 3, 30)
TODAY_STR  = TODAY.strftime("%Y-%m-%d")

DATA_RAW.mkdir(parents=True, exist_ok=True)

# Config thresholds
CROWDING_HIGH = 85  # percentile above which = CROWDED
CROWDING_LOW  = 15  # percentile below which = CROWDED (opposite direction)


# ── Fetch current COT data from CFTC ─────────────────────────────────────────

def fetch_cot_current():
    """Fetch the latest COT report and extract JPY positioning."""
    cache = DATA_RAW / f"cot_{TODAY_STR}.json"
    if cache.exists():
        with open(cache) as f:
            data = json.load(f)
        print(f"  COT: using cached data from {cache.name}")
        return data

    url = "https://www.cftc.gov/dea/futures/deacmelf.htm"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  WARN: CFTC fetch failed: {e}", file=sys.stderr)
        return _try_fallback_cache()

    # Find JAPANESE YEN block
    idx = text.upper().find("JAPANESE YEN")
    if idx < 0:
        print("  WARN: JAPANESE YEN not found in CFTC report", file=sys.stderr)
        return _try_fallback_cache()

    block = text[idx:idx + 2500]
    lines = block.split("\n")

    data = _parse_cot_block(lines)
    if data:
        with open(cache, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  COT: fetched {data['report_date']}, net={data['net_position']:+,d}")

    return data


def _parse_cot_block(lines):
    """Parse the HTM fixed-width COT block for JPY."""
    data = {}

    # Line 0: "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE  Code-097741"
    # Line 1: "Commitments of Traders - Futures Only, March 24, 2026"
    date_match = re.search(r'(\w+ \d+, \d{4})', lines[1] if len(lines) > 1 else "")
    if date_match:
        try:
            data["report_date"] = datetime.strptime(date_match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
        except ValueError:
            data["report_date"] = TODAY_STR

    # Line 10: "All  :   328,210:    98,271    161,077     21,036    167,443 ..."
    # Fields: OI, NC Long, NC Short, Spreading, Comm Long, Comm Short, Total Long, Total Short, NR Long, NR Short
    all_line = None
    changes_line = None
    found_all = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Only match the first "All" line (positions), not the percentage "All" line
        if not found_all and stripped.startswith("All") and ":" in stripped:
            all_line = stripped
            found_all = True
        if "Changes in Commitments" in line:
            # The next line with numbers has the changes (starts with ":")
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = lines[j].strip()
                if re.search(r'[-\d,]+', candidate):
                    changes_line = candidate
                    break

    if not all_line:
        print("  WARN: Could not find 'All' line in COT block", file=sys.stderr)
        return None

    # Parse numbers from All line
    # Format: "All  :   328,210:    98,271    161,077     21,036    167,443    109,542    286,750    291,655:    41,460     36,555"
    numbers = [int(s.replace(",", "")) for s in re.findall(r'[-\d,]+', all_line)]
    # numbers: [OI, NC_long, NC_short, Spreading, Comm_long, Comm_short, Total_long, Total_short, NR_long, NR_short]
    if len(numbers) >= 4:
        data["open_interest"] = numbers[0]
        data["nc_long"]       = numbers[1]
        data["nc_short"]      = numbers[2]
        data["nc_spreading"]  = numbers[3]
        data["net_position"]  = numbers[1] - numbers[2]  # long - short
    else:
        return None

    # Parse changes line
    if changes_line:
        chg_numbers = [int(s.replace(",", "")) for s in re.findall(r'[-\d,]+', changes_line)]
        # Same order: OI_chg, NC_long_chg, NC_short_chg, Spreading_chg, ...
        if len(chg_numbers) >= 4:
            data["oi_change"]        = chg_numbers[0]
            data["nc_long_change"]   = chg_numbers[1]
            data["nc_short_change"]  = chg_numbers[2]
            data["net_change"]       = chg_numbers[1] - chg_numbers[2]

    return data


def _try_fallback_cache():
    """Try to load the most recent cached COT data."""
    import glob
    caches = sorted(Path(DATA_RAW).glob("cot_????-??-??.json"))
    if caches:
        latest = caches[-1]
        age_days = (TODAY - datetime.strptime(latest.stem.replace("cot_", ""), "%Y-%m-%d").date()).days
        if age_days <= 14:  # accept up to 2 weeks old
            print(f"  COT: using fallback cache {latest.name} ({age_days}d old)")
            with open(latest) as f:
                return json.load(f)
    print("  WARN: No COT data available", file=sys.stderr)
    return None


# ── Historical data & percentile ──────────────────────────────────────────────

def load_cot_history():
    """Load all cached COT data files to build a history of net positions."""
    history = []  # [(date_str, net_position), ...]
    for f in sorted(DATA_RAW.glob("cot_????-??-??.json")):
        try:
            with open(f) as fh:
                d = json.load(fh)
            if "net_position" in d:
                dt = d.get("report_date", f.stem.replace("cot_", ""))
                history.append((dt, d["net_position"]))
        except Exception:
            continue
    return history


def compute_percentile(current_net, history):
    """Compute percentile rank of current net position within history."""
    if not history:
        return None
    values = [v for _, v in history]
    values.append(current_net)
    values.sort()
    rank = values.index(current_net)
    return round(100 * rank / (len(values) - 1)) if len(values) > 1 else 50


# ── Signal logic (contrarian) ────────────────────────────────────────────────

def compute_signal(net_position, percentile, net_change):
    """
    Contrarian interpretation:
    - Extreme net short JPY (high percentile of SHORT) = crowded → BEARISH USD/JPY
    - Extreme net long JPY (low percentile) = crowded long → BULLISH USD/JPY
    - Note: net_position = NC_long - NC_short
      Negative net = speculators are net short JPY (= long USD/JPY)
      Positive net = speculators are net long JPY (= short USD/JPY)
    """
    # Determine positioning direction
    if net_position < 0:
        pos_direction = "short"  # net short JPY = effectively long USD/JPY
    else:
        pos_direction = "long"   # net long JPY = effectively short USD/JPY

    # Crowding status
    crowding = "MODERATE"
    if percentile is not None:
        if percentile >= CROWDING_HIGH or percentile <= CROWDING_LOW:
            crowding = "CROWDED"
        elif 25 <= percentile <= 75:
            crowding = "MODERATE"
        else:
            crowding = "LIGHT"

    # Contrarian signal
    bias = "NEUTRAL"
    confidence = "LOW"

    if crowding == "CROWDED":
        if net_position < 0:
            # Speculators massively short JPY → crowded → reversal risk → BEARISH USD/JPY
            bias = "BEARISH"
            confidence = "MEDIUM"
        else:
            # Speculators massively long JPY → crowded → reversal risk → BULLISH USD/JPY
            bias = "BULLISH"
            confidence = "MEDIUM"
        if percentile is not None and (percentile >= 95 or percentile <= 5):
            confidence = "HIGH"
    elif crowding == "LIGHT":
        # Not crowded — slight contrarian lean
        if net_position < 0:
            bias = "BULLISH"   # room for more short JPY = USD/JPY upside
        else:
            bias = "BEARISH"   # room for more long JPY = USD/JPY downside
        confidence = "LOW"

    return {
        "bias": bias,
        "confidence": confidence,
        "crowding": crowding,
        "direction": pos_direction,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run_cot_analysis():
    """Run Module 04 and return a dict with all results."""
    print("▶ Module 04 — Positioning (COT)")

    current = fetch_cot_current()
    if not current:
        return None

    net = current["net_position"]
    net_change = current.get("net_change")

    # Build history and compute percentile
    history = load_cot_history()
    percentile = compute_percentile(net, history)

    # Compute signal
    signal = compute_signal(net, percentile, net_change)

    result = {
        "report_date": current.get("report_date", TODAY_STR),
        "open_interest": current.get("open_interest"),
        "nc_long": current.get("nc_long"),
        "nc_short": current.get("nc_short"),
        "net_position": net,
        "net_change": net_change,
        "percentile": percentile,
        "crowding": signal["crowding"],
        "direction": signal["direction"],
        "bias": signal["bias"],
        "confidence": signal["confidence"],
        "history_points": len(history),
    }

    print(f"  Net: {net:+,d} ({signal['direction']} JPY) | WoW: {net_change:+,d}" if net_change else f"  Net: {net:+,d}")
    print(f"  Percentile: {percentile}th | Crowding: {signal['crowding']}")
    print(f"  Bias: {signal['bias']} / {signal['confidence']} (contrarian)")

    return result


def format_report_section(r):
    """Format Module 04 as a markdown report section."""
    if not r:
        return "## 04 — Positioning (COT)\n\n**Data unavailable** — CFTC report could not be fetched.\n"

    net = r["net_position"]
    direction = r["direction"]
    net_change = r.get("net_change")
    percentile = r.get("percentile")
    crowding = r["crowding"]
    bias = r["bias"]
    confidence = r["confidence"]

    net_fmt = f"{net:+,d}"
    chg_fmt = f"{net_change:+,d}" if net_change is not None else "N/A"
    pct_fmt = f"{percentile}th" if percentile is not None else "N/A"
    hist_note = f" ({r['history_points']} weeks of data)" if r.get("history_points", 0) > 1 else " (first data point — no history yet)"

    # Narrative
    if crowding == "CROWDED":
        if direction == "short":
            narrative = f"Speculators are heavily net short JPY ({net_fmt} contracts) — a crowded trade. Contrarian signal flags reversal risk: a short squeeze would pressure USD/JPY lower."
        else:
            narrative = f"Speculators are heavily net long JPY ({net_fmt} contracts) — a crowded trade. Contrarian signal flags unwind risk: a long liquidation would push USD/JPY higher."
    elif crowding == "LIGHT":
        narrative = f"Positioning is light at the {pct_fmt} percentile{hist_note}. No crowding pressure — positioning is not a primary driver this week."
    else:
        narrative = f"Net speculative position at {net_fmt} contracts ({direction} JPY), {pct_fmt} percentile{hist_note}. Positioning is moderate — no crowding signal."

    section = f"""## 04 — Positioning (COT)

**Bias: {bias}** | Confidence: {confidence} | *(contrarian interpretation)*

| Metric | Value |
|--------|-------|
| Net Speculative Position | {net_fmt} contracts ({direction} JPY) |
| Week-over-Week Change | {chg_fmt} contracts |
| 3-Year Percentile | {pct_fmt}{hist_note} |
| Crowding Status | {crowding} |

{narrative}

*Data: CFTC COT Legacy Futures, report date {r.get('report_date', 'N/A')}*
"""
    return section


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_cot_analysis()

    if "--json" in sys.argv:
        if result:
            print(json.dumps(result, indent=2))
    else:
        print()
        print(format_report_section(result))
