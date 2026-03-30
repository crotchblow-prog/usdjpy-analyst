#!/usr/bin/env python3
"""
run_smc_analysis.py — Module 08 orchestration: multi-timeframe SMC analysis.

Reads Module 07 bias, fetches intraday data, runs structural analysis across
4H/1H/15M/5M, identifies entry zones, classifies scenarios, and generates
the full SMC report + chart.

Usage:
    python3 scripts/run_smc_analysis.py [--mode full|levels|fix]

Modes:
    full   — Full /usdjpy-entry analysis (default)
    levels — Quick /usdjpy-levels (active zones + liquidity only)
    fix    — Quick /usdjpy-fix (Scenario D Tokyo fix fade check)
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import glob

import numpy as np
import pandas as pd
import yaml

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.smc_engine import (
    find_swing_points,
    classify_structure,
    find_order_blocks,
    check_ob_mitigation,
    find_fvg,
    check_fvg_fill,
    premium_discount,
    is_in_ote,
    build_liquidity_map,
    get_tokyo_fix_price,
    classify_scenario,
    compute_confluence_score,
    find_best_entry_zone,
    compute_entry_plan,
    check_15m_confirmation,
    resample_to_4h,
    pips_distance,
    INTERVENTION_LEVELS,
)


# ── Config ────────────────────────────────────────────────────────────────

def load_config():
    config_path = os.path.join(PROJECT_ROOT, "config.yaml")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# ── Data Fetching ─────────────────────────────────────────────────────────

def fetch_intraday_data(ticker="USDJPY=X"):
    """Fetch multi-timeframe data from Yahoo Finance."""
    import yfinance as yf

    print("  Fetching 1H data (60d)...")
    df_1h = yf.download(ticker, period="60d", interval="1h", progress=False)
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = df_1h.columns.get_level_values(0)
    print(f"    -> {len(df_1h)} bars")

    print("  Resampling to 4H...")
    df_4h = resample_to_4h(df_1h)
    print(f"    -> {len(df_4h)} bars")

    print("  Fetching 15M data (60d)...")
    df_15m = yf.download(ticker, period="60d", interval="15m", progress=False)
    if isinstance(df_15m.columns, pd.MultiIndex):
        df_15m.columns = df_15m.columns.get_level_values(0)
    print(f"    -> {len(df_15m)} bars")

    print("  Fetching 5M data (7d)...")
    df_5m = yf.download(ticker, period="7d", interval="5m", progress=False)
    if isinstance(df_5m.columns, pd.MultiIndex):
        df_5m.columns = df_5m.columns.get_level_values(0)
    print(f"    -> {len(df_5m)} bars")

    return df_4h, df_1h, df_15m, df_5m


def fetch_daily_data(ticker="USDJPY=X"):
    """Fetch daily data for liquidity map."""
    import yfinance as yf
    print("  Fetching daily data (60d)...")
    df = yf.download(ticker, period="60d", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    print(f"    -> {len(df)} bars")
    return df


# ── Module 07 Bias Reader ────────────────────────────────────────────────

def read_module07_bias():
    """
    Read the most recent daily or weekly report to extract Module 07 bias.
    Returns dict with direction, confidence, risk_alerts, recommendation.
    """
    output_dirs = [
        os.path.join(PROJECT_ROOT, "output", "daily"),
        os.path.join(PROJECT_ROOT, "output", "weekly"),
    ]

    latest_file = None
    latest_date = None

    for d in output_dirs:
        if not os.path.isdir(d):
            continue
        # Match YYYY-MM-DD.md but not smc_*.md
        for f in glob.glob(os.path.join(d, "*.md")):
            basename = os.path.basename(f)
            if basename.startswith("smc_"):
                continue
            match = re.match(r"(\d{4}-\d{2}-\d{2})\.md$", basename)
            if match:
                file_date = match.group(1)
                if latest_date is None or file_date > latest_date:
                    latest_date = file_date
                    latest_file = f

    if latest_file is None:
        return {
            "direction": "NEUTRAL",
            "confidence": "LOW",
            "risk_alerts": [],
            "recommendation": "No recent report found — run /usdjpy-daily first",
            "source_file": None,
            "report_date": None,
        }

    with open(latest_file, "r") as f:
        content = f.read()

    # Extract bias from Module 07 checklist
    direction = "NEUTRAL"
    confidence = "LOW"
    risk_alerts = []

    # Look for Module 07 overall direction first (most authoritative).
    # Report formats vary: "**Overall: MODERATE BULLISH**" or "**Bias: BULLISH**"
    # or "**Bias:** BULLISH".  Try Module 07 section first, then fall back.
    overall_match = re.search(r"\*\*Overall:\s*(.+?)\*\*", content)
    if not overall_match:
        # Fallback: **Bias: VALUE** (value inside bold) or **Bias:** VALUE
        overall_match = re.search(r"\*\*Bias:\s*(.+?)\*\*", content)
    if not overall_match:
        overall_match = re.search(r"\*\*Bias:\*\*\s*(.+)", content)
    if overall_match:
        bias_text = overall_match.group(1).strip()
        if "BULLISH" in bias_text.upper():
            direction = "LONG"
        elif "BEARISH" in bias_text.upper():
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

    # Look for conviction — handle both "**Conviction: HIGH**" and "**Conviction:** HIGH"
    conv_match = re.search(r"\*\*Conviction:\s*(\w+)", content)
    if not conv_match:
        conv_match = re.search(r"\*\*Conviction:\*\*\s*(\w+)", content)
    if conv_match:
        confidence = conv_match.group(1).upper()

    # Extract risk alerts — try table format first, then checkbox format
    alert_table_pattern = re.compile(
        r"\|\s*(.+?)\s*\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|", re.MULTILINE
    )
    for m in alert_table_pattern.finditer(content):
        alert_name = m.group(1).strip()
        status = m.group(2).strip()
        detail = m.group(3).strip()
        if status in ("ELEVATED", "CRITICAL", "YES", "UNKNOWN"):
            risk_alerts.append(f"{alert_name}: {status} — {detail}")
    # Fallback: checkbox format
    if not risk_alerts:
        alert_pattern = re.compile(r"- \[x\]\s*\*\*(.+?)\*\*", re.MULTILINE)
        for m in alert_pattern.finditer(content):
            risk_alerts.append(m.group(1))

    # Extract recommendation
    rec_match = re.search(r"### Recommendation\n\n(.+?)(?:\n\n---|\Z)", content, re.DOTALL)
    recommendation = rec_match.group(1).strip() if rec_match else ""

    # Check for intervention risk
    intervention_risk = any("intervention" in a.lower() for a in risk_alerts)
    energy_risk = any("energy" in a.lower() for a in risk_alerts)
    event_risk = any("event" in a.lower() for a in risk_alerts)

    return {
        "direction": direction,
        "confidence": confidence,
        "risk_alerts": risk_alerts,
        "recommendation": recommendation,
        "intervention_risk": intervention_risk,
        "energy_risk": energy_risk,
        "event_risk": event_risk,
        "source_file": latest_file,
        "report_date": latest_date,
    }


# ── Timeframe Analysis ────────────────────────────────────────────────────

def analyze_timeframe(df, timeframe, lookback=5):
    """Run full SMC analysis on a single timeframe."""
    if df is None or len(df) < lookback * 3:
        return {
            "timeframe": timeframe,
            "structure": "INSUFFICIENT DATA",
            "events": [],
            "order_blocks": [],
            "fvgs": [],
            "swing_highs": [],
            "swing_lows": [],
        }

    swing_highs, swing_lows = find_swing_points(df, lookback=lookback)
    print(f"    [{timeframe}] Swing points: {len(swing_highs)} highs, {len(swing_lows)} lows")

    structure, events, swing_highs, swing_lows = classify_structure(swing_highs, swing_lows)
    print(f"    [{timeframe}] BOS/ChoCH events: {len(events)}")
    for e in events:
        print(f"      {e['type']} {e['direction']} at {e['price']:.2f} "
              f"(broke {e.get('broken_level', 0):.2f}) idx={e['index']}")

    # Find order blocks from BOS/ChoCH events
    order_blocks = find_order_blocks(df, events, timeframe=timeframe)
    ob_count_before = len(order_blocks)
    check_ob_mitigation(order_blocks, df)
    ob_count_after = sum(1 for ob in order_blocks if not ob["mitigated"])
    print(f"    [{timeframe}] Order blocks: {ob_count_before} found, "
          f"{ob_count_after} unmitigated (filtered {ob_count_before - ob_count_after})")
    for ob in order_blocks:
        status = "MITIGATED" if ob["mitigated"] else "ACTIVE"
        print(f"      {ob['type']} {ob['zone_bottom']:.2f}-{ob['zone_top']:.2f} [{status}]"
              f"{' INTERVENTION' if ob.get('is_intervention') else ''}")

    # Find FVGs
    fvgs = find_fvg(df, timeframe=timeframe)
    fvg_count_before = len(fvgs)
    check_fvg_fill(fvgs, df)
    fvg_count_after = sum(1 for f in fvgs if not f["filled"])
    print(f"    [{timeframe}] FVGs: {fvg_count_before} found, "
          f"{fvg_count_after} unfilled (filtered {fvg_count_before - fvg_count_after})")

    return {
        "timeframe": timeframe,
        "structure": structure,
        "events": events,
        "order_blocks": order_blocks,
        "fvgs": fvgs,
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
    }


# ── Full Analysis ─────────────────────────────────────────────────────────

def run_full_analysis():
    """Run the complete Module 08 SMC analysis."""
    config = load_config()

    print("=" * 60)
    print("Module 08 — Smart Money Concepts (USD/JPY)")
    print("=" * 60)

    # Step 1: Read Module 07 bias
    print("\n[1/5] Reading Module 07 bias...")
    bias_info = read_module07_bias()
    direction = bias_info["direction"]
    confidence = bias_info["confidence"]

    print(f"  Bias: {direction} | Confidence: {confidence}")
    print(f"  Source: {bias_info.get('source_file', 'N/A')}")

    if direction == "NEUTRAL":
        print("  WARNING: Bias is NEUTRAL — running as Range/Counter-trend (reduced probability)")
        # Soft gate: still run, but note it
        # Try to infer direction from technicals context
        direction = _infer_direction_from_context(bias_info)

    # Step 2: Fetch data
    print("\n[2/5] Fetching intraday data...")
    df_4h, df_1h, df_15m, df_5m = fetch_intraday_data()
    df_daily = fetch_daily_data()

    current_price = float(df_1h["Close"].iloc[-1]) if len(df_1h) > 0 else 0
    print(f"  Current price: {current_price:.2f}")

    # Step 3: Multi-timeframe structural analysis
    print("\n[3/5] Running structural analysis...")
    analysis_4h = analyze_timeframe(df_4h, "4H", lookback=5)
    analysis_1h = analyze_timeframe(df_1h, "1H", lookback=5)
    analysis_15m = analyze_timeframe(df_15m, "15M", lookback=5)
    analysis_5m = analyze_timeframe(df_5m, "5M", lookback=5)

    print(f"  4H: {analysis_4h['structure']} ({len(analysis_4h['events'])} events, "
          f"{len(analysis_4h['order_blocks'])} OBs, {len(analysis_4h['fvgs'])} FVGs)")
    print(f"  1H: {analysis_1h['structure']} ({len(analysis_1h['events'])} events, "
          f"{len(analysis_1h['order_blocks'])} OBs, {len(analysis_1h['fvgs'])} FVGs)")
    print(f"  15M: {analysis_15m['structure']}")
    print(f"  5M: {analysis_5m['structure']}")

    # Premium/discount on 4H
    if analysis_4h["swing_highs"] and analysis_4h["swing_lows"]:
        sh_4h = max(s["price"] for s in analysis_4h["swing_highs"][-5:])
        sl_4h = min(s["price"] for s in analysis_4h["swing_lows"][-5:])
    else:
        sh_4h = float(df_4h["High"].max()) if len(df_4h) > 0 else current_price + 1
        sl_4h = float(df_4h["Low"].min()) if len(df_4h) > 0 else current_price - 1

    pd_zone, pd_desc, pd_details = premium_discount(sh_4h, sl_4h, current_price)
    print(f"  Premium/Discount: {pd_zone} ({pd_desc})")
    print(f"  Range: {sl_4h:.2f} — {sh_4h:.2f} (midpoint: {pd_details.get('midpoint', 0):.2f})")

    # Build liquidity map
    all_swing_highs = analysis_4h["swing_highs"] + analysis_1h["swing_highs"]
    all_swing_lows = analysis_4h["swing_lows"] + analysis_1h["swing_lows"]
    liquidity_map = build_liquidity_map(df_daily, all_swing_highs, all_swing_lows, df_5m)

    # Step 4: Identify entry zone
    print("\n[4/5] Identifying entry zones...")

    # Combine OBs from all timeframes — lower TFs provide tighter refinement zones.
    # FVGs only from 4H and 1H (15M/5M FVGs are too noisy for zone selection).
    all_obs = (analysis_4h["order_blocks"] + analysis_1h["order_blocks"]
               + analysis_15m["order_blocks"] + analysis_5m["order_blocks"])
    all_fvgs = analysis_4h["fvgs"] + analysis_1h["fvgs"]

    entry_zone = find_best_entry_zone(all_obs, all_fvgs, direction, "1H", current_price)

    if entry_zone:
        print(f"  Best zone: {entry_zone['zone_type']} at "
              f"{entry_zone['zone_bottom']:.2f}-{entry_zone['zone_top']:.2f} "
              f"({entry_zone['distance_pips']:.0f} pips away)")
        if entry_zone.get("is_intervention"):
            print(f"  ** INTERVENTION OB near {entry_zone.get('source', {}).get('intervention_level', '?')}")
    else:
        print("  No valid entry zone found for current bias direction")
        # Check if price is too far from any zone
        if all_obs or all_fvgs:
            print("  DISTANT — no immediate setup")

    # 15M confirmation
    confirmation = {"confirmed": False, "status": "No entry zone identified"}
    if entry_zone:
        confirmation = check_15m_confirmation(df_15m, entry_zone, direction)
        print(f"  15M: {confirmation['status']}")

    # Classify scenario
    scenario = classify_scenario(
        analysis_4h["structure"], entry_zone, liquidity_map,
        current_price, direction, df_5m
    )
    print(f"  Scenario: {scenario['scenario']} — {scenario['name']}")

    # Step 5: Compute entry plan + confluence
    print("\n[5/5] Computing entry plan...")

    entry_plan = None
    if entry_zone:
        entry_plan = compute_entry_plan(
            direction, entry_zone,
            analysis_4h["swing_highs"], analysis_4h["swing_lows"],
            liquidity_map, pd_details,
        )

    # Check confluence factors
    fvg_overlap = False
    if entry_zone:
        ez_mid = (entry_zone["zone_top"] + entry_zone["zone_bottom"]) / 2
        for fvg in all_fvgs:
            if not fvg["filled"] and fvg["zone_bottom"] <= ez_mid <= fvg["zone_top"]:
                fvg_overlap = True
                break

    ote = is_in_ote(sh_4h, sl_4h, current_price) if entry_zone else False

    # Check if liquidity was swept
    liquidity_swept = False
    if scenario.get("scenario") == "C":
        liquidity_swept = True

    # MTF alignment
    structures = [analysis_4h["structure"], analysis_1h["structure"], analysis_15m["structure"]]
    if direction == "LONG":
        mtf_aligned = all(s == "BULLISH" for s in structures)
    elif direction == "SHORT":
        mtf_aligned = all(s == "BEARISH" for s in structures)
    else:
        mtf_aligned = False

    # Near intervention?
    near_intervention = any(
        abs(current_price - lvl) <= 1.0 for lvl in INTERVENTION_LEVELS
    )

    # Near round number?
    near_round = any(
        abs(current_price - rn) <= 0.20 for rn in range(140, 170)
    )

    # Tokyo fix
    fix_price = get_tokyo_fix_price(df_5m)
    near_fix = fix_price is not None and abs(current_price - fix_price) <= 0.30

    confluence = compute_confluence_score(
        entry_zone=entry_zone,
        fvg_overlap=fvg_overlap,
        in_ote=ote,
        liquidity_swept=liquidity_swept,
        mtf_aligned=mtf_aligned,
        bias_confidence=confidence,
        scenario=scenario,
        near_intervention=near_intervention,
        near_tokyo_fix=near_fix,
        near_round_number=near_round,
        event_within_4h=bias_info.get("event_risk", False),
        spread_widening=False,
    )

    if entry_plan:
        print(f"  Entry: {entry_plan['entry']:.2f} | Stop: {entry_plan['stop']:.2f} | "
              f"T1: {entry_plan['t1_price']:.2f} (R:R 1:{entry_plan['t1_rr']:.1f})")
    else:
        print("  No valid entry plan (R:R < 1:2 or no zones)")

    print(f"  Confluence: {confluence['score']:.1f} — Grade {confluence['grade']}")

    # Collect all results
    results = {
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M JST"),
        "current_price": current_price,
        "bias": bias_info,
        "direction": direction,
        "confidence": confidence,
        "analysis_4h": analysis_4h,
        "analysis_1h": analysis_1h,
        "analysis_15m": analysis_15m,
        "analysis_5m": analysis_5m,
        "pd_zone": pd_zone,
        "pd_desc": pd_desc,
        "pd_details": pd_details,
        "liquidity_map": liquidity_map,
        "entry_zone": entry_zone,
        "confirmation": confirmation,
        "scenario": scenario,
        "entry_plan": entry_plan,
        "confluence": confluence,
        "fix_price": fix_price,
        "df_4h": df_4h,
        "df_1h": df_1h,
        "df_15m": df_15m,
        "df_5m": df_5m,
        "df_daily": df_daily,
    }

    return results


def _infer_direction_from_context(bias_info):
    """When bias is NEUTRAL, try to infer a lean from the recommendation text."""
    import re as _re

    # Intervention risk near top → lean SHORT (most common USD/JPY scenario)
    if bias_info.get("intervention_risk"):
        return "SHORT"

    rec = bias_info.get("recommendation", "").lower()
    # Use word boundaries to avoid false matches like "longs" in "risk for new longs is poor"
    if _re.search(r"\bgo short\b|\bsell\b|\bbearish bias\b|\bfade\b", rec):
        return "SHORT"
    elif _re.search(r"\bgo long\b|\bbuy\b|\bbullish bias\b", rec):
        return "LONG"

    return "LONG"  # default fallback


# ── Report Generation ─────────────────────────────────────────────────────

def generate_report(results, mode="full"):
    """Generate markdown report from analysis results."""
    today = dt.date.today().strftime("%Y-%m-%d")
    lines = []

    if mode == "full":
        lines.append(f"# USD/JPY Smart Money Concepts — {today}")
        lines.append("")
        lines.append("## 08 — Smart Money Concepts")
        lines.append("")
        lines.append(_section_context(results))
        lines.append(_section_4h_structure(results))
        lines.append(_section_scenario(results))
        lines.append(_section_entry_zone(results))
        lines.append(_section_confirmation(results))
        lines.append(_section_entry_plan(results))
        lines.append(_section_active_zones(results))
        lines.append(_section_liquidity_map(results))
        lines.append(_section_session_plan(results))
        lines.append(_section_invalidation(results))
        lines.append("")
        lines.append(f"![SMC Entry Chart](smc_entry_{today}.png)")
        lines.append("")
        lines.append("---")
        lines.append(f"*Generated: {results['timestamp']}*")
        lines.append(f"*Source: Module 07 from {results['bias'].get('report_date', 'N/A')}*")

    elif mode == "levels":
        lines.append(f"# USD/JPY Active Zones & Liquidity — {today}")
        lines.append("")
        lines.append(_section_active_zones(results))
        lines.append(_section_liquidity_map(results))
        lines.append("")
        lines.append("---")
        lines.append(f"*Quick levels check — {results['timestamp']}*")

    elif mode == "fix":
        lines.append(f"# USD/JPY Tokyo Fix Fade Check — {today}")
        lines.append("")
        lines.append(_section_fix_check(results))
        lines.append("")
        lines.append("---")
        lines.append(f"*Fix check — {results['timestamp']}*")

    return "\n".join(lines)


def _section_context(r):
    """Context section: bias, intervention risk, COT, events, alignment."""
    bias = r["bias"]
    direction = r["direction"]
    confidence = r["confidence"]
    neutral_note = ""
    if bias["direction"] == "NEUTRAL":
        neutral_note = "\n> **Note:** Module 07 bias is NEUTRAL — this is a Range/Counter-trend setup with reduced probability.\n"

    alerts = "\n".join(f"- {a}" for a in bias.get("risk_alerts", [])) or "- None"

    return f"""### Context (from Module 07)

**Direction:** {direction}
**Confidence:** {confidence}
**Report Date:** {bias.get('report_date', 'N/A')}
{neutral_note}
**Risk Alerts:**
{alerts}

**Recommendation:** {bias.get('recommendation', 'N/A')[:200]}

---
"""


def _section_4h_structure(r):
    """4H structure section."""
    a4h = r["analysis_4h"]
    structure = a4h["structure"]
    events = a4h["events"]
    pd_zone = r["pd_zone"]
    pd_desc = r["pd_desc"]
    details = r["pd_details"]

    last_event = "None"
    if events:
        e = events[-1]
        last_event = f"{e['type']} ({e['direction']}) at {e['price']:.2f} on {e['datetime']}"

    return f"""### 4H Structure

**Market Structure:** {structure}
**Last BOS/ChoCH:** {last_event}
**Premium/Discount:** Price at {r['current_price']:.2f} is in **{pd_zone}** ({pd_desc})
**Range:** {details.get('swing_low', 0):.2f} — {details.get('swing_high', 0):.2f} (midpoint: {details.get('midpoint', 0):.2f})
**OTE Zone:** {details.get('ote_bottom', 0):.2f} — {details.get('ote_top', 0):.2f} (61.8%-79%)

**MTF Alignment:**
| Timeframe | Structure |
|-----------|-----------|
| 4H | {a4h['structure']} |
| 1H | {r['analysis_1h']['structure']} |
| 15M | {r['analysis_15m']['structure']} |
| 5M | {r['analysis_5m']['structure']} |

---
"""


def _section_scenario(r):
    """Scenario identification."""
    s = r["scenario"]
    return f"""### Scenario Identification

**Scenario {s['scenario']}:** {s['name']}
**Rationale:** {s['description']}
**Bias Alignment:** {'Yes' if s.get('bias_alignment') else 'No — reduced probability'}

---
"""


def _section_entry_zone(r):
    """Entry zone details."""
    ez = r["entry_zone"]
    if ez is None:
        return """### Entry Zone (1H)

**No valid entry zone identified** for current bias direction.
Price may be distant from all zones — wait for retracement or new structure.

---
"""

    intervention_tag = ""
    if ez.get("is_intervention"):
        intervention_tag = " | **INTERVENTION OB**"

    return f"""### Entry Zone (1H)

**Zone Type:** {ez['zone_type']}{intervention_tag}
**Zone Range:** {ez['zone_bottom']:.2f} — {ez['zone_top']:.2f}
**Full Range:** {ez['full_range_bottom']:.2f} — {ez['full_range_top']:.2f}
**Timeframe:** {ez.get('timeframe', 'N/A')}
**Distance from Current Price:** {ez['distance_pips']:.0f} pips
**Status:** {'Unmitigated' if not ez.get('source', {}).get('mitigated') else 'Partially mitigated'}

---
"""


def _section_confirmation(r):
    """15M confirmation status."""
    c = r["confirmation"]
    return f"""### Confirmation Status (15M)

**Status:** {'CONFIRMED' if c['confirmed'] else 'PENDING'}
**Detail:** {c['status']}

---
"""


def _section_entry_plan(r):
    """Entry plan table."""
    ep = r["entry_plan"]
    cf = r["confluence"]

    if ep is None:
        return f"""### Entry Plan

**No valid entry** — either no zone found, or risk:reward below 1:2 minimum.

**Confluence Score:** {cf['score']:.1f} — Grade **{cf['grade']}**
**Scoring Details:**
{chr(10).join('- ' + d for d in cf['details'])}

---
"""

    t2_line = ""
    if ep.get("t2_price") is not None:
        t2_line = f"| Target 2 | {ep['t2_price']:.2f} ({ep.get('t2_type', '')}) | R:R = 1:{ep['t2_rr']:.1f} |"

    return f"""### Entry Plan

| Field | Value | Notes |
|-------|-------|-------|
| Direction | {ep['direction']} | |
| Entry | {ep['entry']:.2f} | Zone {'top' if ep['direction'] == 'LONG' else 'bottom'} |
| Stop Loss | {ep['stop']:.2f} | {ep['risk_pips']:.0f} pips risk |
| Target 1 | {ep['t1_price']:.2f} ({ep.get('t1_type', '')}) | R:R = 1:{ep['t1_rr']:.1f} |
{t2_line}

**Confluence Score:** {cf['score']:.1f} — Grade **{cf['grade']}**

**Scoring Details:**
{chr(10).join('- ' + d for d in cf['details'])}

---
"""


def _section_active_zones(r):
    """Active zones summary across all timeframes."""
    rows = []
    for analysis in [r["analysis_4h"], r["analysis_1h"], r["analysis_15m"], r["analysis_5m"]]:
        tf = analysis["timeframe"]
        for ob in analysis["order_blocks"]:
            if ob["mitigated"]:
                continue
            ob_dir = "Long" if ob["type"] == "bullish_ob" else "Short"
            intervention = " (INTERVENTION)" if ob.get("is_intervention") else ""
            rows.append(
                f"| {tf} | {ob['type'].replace('_', ' ').title()}{intervention} | "
                f"{ob['zone_bottom']:.2f}-{ob['zone_top']:.2f} | {ob_dir} | Unmitigated |"
            )
        for fvg in analysis["fvgs"]:
            if fvg["filled"]:
                continue
            fvg_dir = "Long" if fvg["type"] == "bullish_fvg" else "Short"
            rows.append(
                f"| {tf} | {fvg['type'].replace('_', ' ').title()} | "
                f"{fvg['zone_bottom']:.2f}-{fvg['zone_top']:.2f} | {fvg_dir} | Unfilled |"
            )

    if not rows:
        rows.append("| — | No active zones | — | — | — |")

    table = "\n".join(rows)

    return f"""### Active Zones Summary

| Timeframe | Type | Zone | Direction | Status |
|-----------|------|------|-----------|--------|
{table}

---
"""


def _section_liquidity_map(r):
    """Key liquidity levels."""
    levels = r["liquidity_map"]
    rows = []
    seen = set()
    for l in levels[:15]:  # top 15 levels
        key = f"{l['price']:.2f}-{l['type']}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(f"| {l['price']:.2f} | {l['type']} | {l['significance']} |")

    if not rows:
        rows.append("| — | — | No levels identified |")

    table = "\n".join(rows)

    return f"""### Key Liquidity Levels

| Level | Type | Significance |
|-------|------|-------------|
{table}

---
"""


def _section_session_plan(r):
    """Session plan based on scenario and time."""
    scenario = r["scenario"]["scenario"]
    fix_price = r.get("fix_price")
    direction = r["direction"]

    fix_note = f"Tokyo fix: {fix_price:.2f}" if fix_price else "Tokyo fix: N/A"

    if scenario == "D":
        session_focus = "TOKYO (post-fix fade active)"
    elif scenario == "A":
        session_focus = "ANY SESSION (intervention can happen anytime)"
    else:
        session_focus = "LONDON/NY (highest liquidity for trend continuation)"

    return f"""### Session Plan

**Primary Session:** {session_focus}
**{fix_note}**

**Tokyo (09:00-15:00 JST):** {'Scenario D fade opportunity post-fix' if scenario == 'D' else 'Monitor for range definition and fix flows'}
**London (17:00-02:00 JST):** {'Key session for trend moves — watch for BOS on 15M' if direction != 'NEUTRAL' else 'Watch for breakout direction'}
**New York (22:00-07:00 JST):** {'Continuation or reversal — watch US data releases' if direction != 'NEUTRAL' else 'Reduced activity — manage existing positions'}

---
"""


def _section_invalidation(r):
    """Invalidation criteria."""
    entry_plan = r["entry_plan"]
    direction = r["direction"]
    scenario = r["scenario"]

    invalidation_rules = []
    if entry_plan:
        invalidation_rules.append(
            f"Price breaks {'below' if direction == 'LONG' else 'above'} "
            f"{entry_plan['stop']:.2f} (stop level)"
        )
    if scenario["scenario"] == "A":
        invalidation_rules.append("MOF/BOJ backs down from intervention rhetoric")
    if scenario["scenario"] == "D":
        invalidation_rules.append("Fix move continues beyond typical reversal window (past 12:00 JST)")

    invalidation_rules.append(
        f"4H structure flips to {'BEARISH' if direction == 'LONG' else 'BULLISH'} "
        f"(new {'LL' if direction == 'LONG' else 'HH'})"
    )
    invalidation_rules.append("Major unexpected news event changes macro backdrop")

    items = "\n".join(f"- {rule}" for rule in invalidation_rules)

    return f"""### Invalidation Criteria

{items}

---
"""


def _section_fix_check(r):
    """Tokyo fix fade check (Scenario D)."""
    fix_price = r.get("fix_price")
    current = r["current_price"]
    scenario = r["scenario"]

    if fix_price is None:
        return """**Tokyo fix price not available** — 5M data may not cover today's fix window.
Run this command between 09:50-10:00 JST for best results."""

    fix_move = current - fix_price
    direction_text = "bought" if fix_move > 0 else "sold"

    lines = [
        f"**Fix Price (9:55 JST):** {fix_price:.2f}",
        f"**Current Price:** {current:.2f}",
        f"**Fix Move:** {fix_move:+.2f} ({abs(fix_move) * 100:.0f} pips — {direction_text} into fix)",
        "",
    ]

    if scenario["scenario"] == "D":
        lines.append(f"**Scenario D ACTIVE — {scenario['name']}**")
        lines.append(f"{scenario['description']}")
        if abs(fix_move) >= 0.15:
            fade_dir = "SHORT" if fix_move > 0 else "LONG"
            lines.append(f"\nFade direction: **{fade_dir}** (fade the pre-fix flow)")
        else:
            lines.append("\nFix move too small (<15 pips) — no clear fade opportunity.")
    else:
        lines.append(f"**Scenario: {scenario['scenario']} — {scenario['name']}** (not a fix fade)")
        if abs(fix_move) < 0.15:
            lines.append("Fix move too small for Scenario D.")
        else:
            lines.append("Current scenario does not match fix fade criteria.")

    return "\n".join(lines)


# ── Chart Generation ──────────────────────────────────────────────────────

def generate_chart(results):
    """Generate the SMC entry chart — clean, professional, full-width."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle

    config = load_config()
    dpi = config.get("output", {}).get("chart_dpi", 150)

    # Clean white style — no default matplotlib chrome
    plt.rcParams.update({
        "figure.facecolor": "#F8F9FA",
        "axes.facecolor": "#FFFFFF",
        "axes.edgecolor": "#DFE6E9",
        "axes.grid": True,
        "grid.color": "#DFE6E9",
        "grid.linewidth": 0.5,
        "grid.alpha": 0.7,
        "xtick.color": "#636E72",
        "ytick.color": "#636E72",
        "text.color": "#2D3436",
        "font.family": "Helvetica",
    })

    fig, ax = plt.subplots(figsize=(7.5, 4.5))

    df = results["df_1h"]
    if df is None or len(df) == 0:
        return None

    # Plot ~5 days centered on entry zone
    n_bars = 120
    ez = results.get("entry_zone")
    if ez and ez.get("source", {}).get("datetime") is not None:
        center_dt = ez["source"]["datetime"]
        try:
            center_idx = df.index.get_indexer([center_dt], method="nearest")[0]
            start = max(0, center_idx - n_bars * 2 // 3)
            end = min(len(df), start + n_bars)
            plot_df = df.iloc[start:end].copy()
        except Exception:
            plot_df = df.tail(n_bars).copy()
    else:
        plot_df = df.tail(n_bars).copy()

    dates = plot_df.index
    closes = plot_df["Close"].values
    opens = plot_df["Open"].values
    highs = plot_df["High"].values
    lows = plot_df["Low"].values

    # Candle width: compute from date spacing for readable bars
    if len(dates) >= 2:
        avg_gap = (mdates.date2num(dates[-1]) - mdates.date2num(dates[0])) / len(dates)
        bar_w = avg_gap * 0.6
    else:
        bar_w = 0.03

    # Draw candlesticks — larger, cleaner
    for i in range(len(plot_df)):
        bull = closes[i] >= opens[i]
        fc = "#27AE60" if bull else "#E74C3C"
        ec = "#1E8449" if bull else "#C0392B"
        # Wick
        ax.plot([dates[i], dates[i]], [lows[i], highs[i]], color=ec, linewidth=0.8, zorder=2)
        # Body
        body_bottom = min(opens[i], closes[i])
        body_top = max(opens[i], closes[i])
        body_h = max(body_top - body_bottom, 0.005)
        rect = Rectangle(
            (mdates.date2num(dates[i]) - bar_w / 2, body_bottom),
            bar_w, body_h,
            facecolor=fc, edgecolor=ec, linewidth=0.5, zorder=3
        )
        ax.add_patch(rect)

    # Shade order blocks (unmitigated only)
    analysis_1h = results["analysis_1h"]
    for ob in analysis_1h["order_blocks"]:
        if ob["mitigated"]:
            continue
        if ob.get("is_intervention"):
            fc, ec = "#F39C12", "#F39C12"
            alpha = 0.18
        elif ob["type"] == "bullish_ob":
            fc, ec = "#27AE60", "#27AE60"
            alpha = 0.12
        else:
            fc, ec = "#E74C3C", "#E74C3C"
            alpha = 0.12
        ax.axhspan(ob["zone_bottom"], ob["zone_top"],
                    facecolor=fc, alpha=alpha, edgecolor=ec, linewidth=0.8, zorder=1)
        ax.text(plot_df.index[-1], ob["zone_top"], f"  OB {ob['timeframe']}", fontsize=6,
                color=ec, va="bottom", ha="left", zorder=4)

    # Shade FVGs (very subtle)
    for fvg in analysis_1h["fvgs"]:
        if fvg["filled"] or fvg["datetime"] < plot_df.index[0]:
            continue
        fc = "#AED6F1" if fvg["type"] == "bullish_fvg" else "#F5B7B1"
        ax.axhspan(fvg["zone_bottom"], fvg["zone_top"],
                    facecolor=fc, alpha=0.08, linewidth=0, zorder=0)

    # Premium/Discount shading
    pd_details = results.get("pd_details", {})
    midpoint = pd_details.get("midpoint")
    sh = pd_details.get("swing_high")
    sl = pd_details.get("swing_low")
    if midpoint and sh and sl:
        ax.axhspan(midpoint, sh, facecolor="#FADBD8", alpha=0.06)
        ax.axhspan(sl, midpoint, facecolor="#D5F5E3", alpha=0.06)
        ax.axhline(midpoint, color="#95A5A6", linestyle="--", linewidth=0.5, alpha=0.5)

    # Swing structure labels
    for sh_pt in analysis_1h["swing_highs"][-10:]:
        if sh_pt["datetime"] >= plot_df.index[0]:
            ax.annotate(sh_pt.get("label", "SH"), (sh_pt["datetime"], sh_pt["price"]),
                        textcoords="offset points", xytext=(0, 8),
                        fontsize=6, color="#2980B9", ha="center", fontweight="bold")
    for sl_pt in analysis_1h["swing_lows"][-10:]:
        if sl_pt["datetime"] >= plot_df.index[0]:
            ax.annotate(sl_pt.get("label", "SL"), (sl_pt["datetime"], sl_pt["price"]),
                        textcoords="offset points", xytext=(0, -12),
                        fontsize=6, color="#C0392B", ha="center", fontweight="bold")

    # Entry/Stop/Target lines — labeled on right y-axis, with anti-overlap
    ep = results.get("entry_plan")
    if ep:
        right_x = plot_df.index[-1]
        # Collect all label positions, then nudge overlapping ones apart
        labels = [
            (ep["entry"], f"  Entry {ep['entry']:.2f}  ", "#27AE60", "--", 1.8),
            (ep["stop"], f"  Stop {ep['stop']:.2f}  ", "#E74C3C", "--", 1.8),
            (ep["t1_price"], f"  T1 {ep['t1_price']:.2f}  ", "#2980B9", "--", 1.2),
        ]
        if ep.get("t2_price"):
            labels.append(
                (ep["t2_price"], f"  T2 {ep['t2_price']:.2f}  ", "#2980B9", ":", 1.0))

        # Sort by price and nudge labels that are within 0.12 (12 pips) of each other
        labels.sort(key=lambda x: x[0])
        label_y = [l[0] for l in labels]
        min_gap = 0.12  # minimum visual gap between label centers
        for i in range(1, len(label_y)):
            if label_y[i] - label_y[i - 1] < min_gap:
                mid = (label_y[i] + label_y[i - 1]) / 2
                label_y[i - 1] = mid - min_gap / 2
                label_y[i] = mid + min_gap / 2

        for i, (price, text, color, ls, lw) in enumerate(labels):
            ax.axhline(price, color=color, linestyle=ls, linewidth=lw, zorder=5)
            ax.text(right_x, label_y[i], text,
                    fontsize=7, color=color, va="center", ha="left", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, lw=0.5))

    # Tokyo fix markers
    fix_price = results.get("fix_price")
    if fix_price:
        fix_bars = []
        idx = plot_df.index
        try:
            idx_jst = idx.tz_localize("UTC").tz_convert("Asia/Tokyo") if idx.tz is None else \
                       idx.tz_convert("Asia/Tokyo") if str(idx.tz) != "Asia/Tokyo" else idx
        except Exception:
            idx_jst = idx
        for i, ts in enumerate(idx_jst):
            if ts.hour == 9 and 50 <= ts.minute <= 59:
                fix_bars.append(i)
        for fb in fix_bars[-3:]:
            ax.plot(plot_df.index[fb], fix_price, marker="D", color="#F39C12",
                    markersize=7, zorder=6)

    # Intervention levels
    for lvl in INTERVENTION_LEVELS:
        if sl and sh and sl - 2 <= lvl <= sh + 2:
            ax.axhline(lvl, color="#F39C12", linestyle=":", linewidth=0.8, alpha=0.5)
            ax.text(plot_df.index[0], lvl, f"  INTV {lvl:.0f}", fontsize=6,
                    color="#F39C12", va="bottom")

    # Y-axis: current price ± 100 pips
    current_price = results.get("current_price", closes[-1] if len(closes) else 159)
    ax.set_ylim(current_price - 1.00, current_price + 1.00)

    # Clean formatting
    ax.set_title(
        f"USD/JPY 1H  |  {results['analysis_1h']['structure']}  |  "
        f"Scenario {results['scenario']['scenario']}: {results['scenario']['name']}",
        fontsize=10, fontweight="bold", color="#2D3436", pad=10
    )
    ax.set_ylabel("")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.tick_params(axis="x", rotation=30, labelsize=7)
    ax.tick_params(axis="y", labelsize=8)
    # Horizontal grid only
    ax.yaxis.grid(True, color="#DFE6E9", linewidth=0.5, alpha=0.7)
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.subplots_adjust(left=0.06, right=0.88, top=0.93, bottom=0.12)

    # Save
    today = dt.date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join(PROJECT_ROOT, "output", "daily")
    os.makedirs(output_dir, exist_ok=True)
    chart_path = os.path.join(output_dir, f"smc_entry_{today}.png")
    fig.savefig(chart_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Chart saved: {chart_path}")
    return chart_path


# ── Save Report ───────────────────────────────────────────────────────────

def save_report(report_md, mode="full"):
    """Save the markdown report to output/daily/."""
    today = dt.date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join(PROJECT_ROOT, "output", "daily")
    os.makedirs(output_dir, exist_ok=True)

    if mode == "full":
        filename = f"smc_{today}.md"
    elif mode == "levels":
        filename = f"smc_levels_{today}.md"
    elif mode == "fix":
        filename = f"smc_fix_{today}.md"
    else:
        filename = f"smc_{today}.md"

    path = os.path.join(output_dir, filename)
    with open(path, "w") as f:
        f.write(report_md)
    print(f"  Report saved: {path}")
    return path


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Module 08 — SMC Analysis")
    parser.add_argument("--mode", choices=["full", "levels", "fix"], default="full",
                        help="Analysis mode: full, levels, or fix")
    args = parser.parse_args()

    results = run_full_analysis()

    # Generate report
    print("\nGenerating report...")
    report_md = generate_report(results, mode=args.mode)
    report_path = save_report(report_md, mode=args.mode)

    # Generate chart (full mode only, or if useful)
    if args.mode == "full":
        print("\nGenerating chart...")
        chart_path = generate_chart(results)

        # Generate PDF
        if report_path:
            print("\nGenerating PDF...")
            pdf_script = os.path.join(PROJECT_ROOT, "scripts", "generate_pdf.py")
            if os.path.exists(pdf_script):
                os.system(f"python3 {pdf_script} {report_path} --type smc")
            else:
                print("  PDF script not found — skipping PDF generation")

    print("\nDone!")
    return results


if __name__ == "__main__":
    main()
