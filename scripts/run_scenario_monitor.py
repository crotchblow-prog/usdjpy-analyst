#!/usr/bin/env python3
"""
run_scenario_monitor.py — Module 09: Scenario Monitor

Two modes:
  check     — Live check: which playbook scenario is unfolding? (Job 1)
  scorecard — Post-session scorecard: score each scenario. (Job 2)

Usage:
    python3 scripts/run_scenario_monitor.py --mode check
    python3 scripts/run_scenario_monitor.py --mode scorecard
"""

import argparse
import csv
import datetime as dt
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import yaml
import yfinance as yf

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

JST = dt.timezone(dt.timedelta(hours=9))

# ── Config ──────────────────────────────────────────────────────────────────

def load_config():
    with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
        return yaml.safe_load(f)


# ── SMC Report Parser ──────────────────────────────────────────────────────

def find_latest_smc_report():
    """Find the most recent smc_YYYY-MM-DD.md file."""
    daily_dir = os.path.join(PROJECT_ROOT, "output", "daily")
    if not os.path.isdir(daily_dir):
        return None
    candidates = glob.glob(os.path.join(daily_dir, "smc_*.md"))
    # Filter to smc_YYYY-MM-DD.md (not smc_levels_*, smc_fix_*)
    dated = []
    for f in candidates:
        m = re.match(r"smc_(\d{4}-\d{2}-\d{2})\.md$", os.path.basename(f))
        if m:
            dated.append((m.group(1), f))
    if not dated:
        return None
    dated.sort(key=lambda x: x[0], reverse=True)
    return dated[0][1]


def parse_smc_report(filepath):
    """Extract key data from an SMC report markdown file."""
    with open(filepath, "r") as f:
        content = f.read()

    data = {"filepath": filepath, "raw": content}

    # Date from filename
    m = re.search(r"smc_(\d{4}-\d{2}-\d{2})\.md", filepath)
    data["date"] = m.group(1) if m else None

    # Generation time: *Generated: 2026-03-31 08:58 JST*
    m = re.search(r"\*Generated:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*JST\*", content)
    if m:
        data["generation_time"] = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    else:
        data["generation_time"] = None

    # Direction
    m = re.search(r"\*\*Direction:\*\*\s*(\w+)", content)
    data["direction"] = m.group(1) if m else "NEUTRAL"

    # Grade
    m = re.search(r"Grade\s*\*\*(\w\+?)\*\*", content)
    data["grade"] = m.group(1) if m else "?"

    # Setup type
    m = re.search(r"\*\*Setup Type:\*\*\s*(.+?)$", content, re.MULTILINE)
    data["setup_type"] = m.group(1).strip() if m else "Unknown"

    # Entry plan values
    m = re.search(r"\|\s*Entry\s*\|\s*([\d.]+)", content)
    data["entry_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Stop Loss\s*\|\s*([\d.]+)", content)
    data["stop_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Target 1\s*\|\s*([\d.]+)", content)
    data["target1_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Target 2\s*\|\s*([\d.]+)", content)
    data["target2_price"] = float(m.group(1)) if m else None

    # Price at generation — infer from entry zone context or use entry as proxy
    m = re.search(r"\*\*Price at Report:\*\*\s*([\d.]+)", content)
    if m:
        data["price_at_report"] = float(m.group(1))
    else:
        # Try to get from "Price at NNN.NN is in" pattern
        m = re.search(r"Price at\s+([\d.]+)\s+is in", content)
        data["price_at_report"] = float(m.group(1)) if m else None

    # Parse scenarios from playbook section
    data["scenarios"] = _parse_scenarios(content)

    return data


def _parse_scenarios(content):
    """Parse the 3 playbook scenarios from the report."""
    scenarios = []

    # Match #### Primary: ..., #### Alternative: ..., #### Tail Risk: ...
    pattern = re.compile(
        r"####\s+(Primary|Alternative|Tail Risk):\s*(.+?)\((\d+)%\)\s*\n(.*?)(?=####|\Z)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        scenario_type = m.group(1).strip()
        name = m.group(2).strip()
        prob = int(m.group(3))
        body = m.group(4).strip()

        # Extract key level
        kl = re.search(r"\*\*Key Level:\*\*\s*([\d.]+)", body)
        key_level = float(kl.group(1)) if kl else None

        # Extract trigger
        tr = re.search(r"\*\*Trigger:\*\*\s*(.+?)$", body, re.MULTILINE)
        trigger = tr.group(1).strip() if tr else ""

        # Extract invalidation
        inv = re.search(r"\*\*Invalidation:\*\*\s*(.+?)$", body, re.MULTILINE)
        invalidation = inv.group(1).strip() if inv else ""

        # Extract action
        act = re.search(r"\*\*Action:\*\*\s*(.+?)$", body, re.MULTILINE)
        action = act.group(1).strip() if act else ""

        scenarios.append({
            "type": scenario_type,
            "name": name,
            "probability": prob,
            "key_level": key_level,
            "trigger": trigger,
            "invalidation": invalidation,
            "action": action,
            "body": body,
        })

    return scenarios


# ── Price Data ──────────────────────────────────────────────────────────────

def fetch_price_data(start_time, end_time=None):
    """Fetch 5M USDJPY candles from Yahoo Finance."""
    ticker = yf.Ticker("USDJPY=X")

    if end_time is None:
        end_time = dt.datetime.now(JST)

    # yfinance needs start/end as strings or dates
    start_str = start_time.strftime("%Y-%m-%d")
    end_dt = end_time + dt.timedelta(days=1)
    end_str = end_dt.strftime("%Y-%m-%d")

    df = ticker.history(start=start_str, end=end_str, interval="5m")
    if df.empty:
        return df

    # Filter to the exact time window
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(JST)

    mask = (df.index >= start_time) & (df.index <= end_time)
    return df.loc[mask]


# ── Job 1: Live Check ──────────────────────────────────────────────────────

def run_live_check(smc_data):
    """Check which scenario is currently unfolding."""
    gen_time = smc_data["generation_time"]
    if gen_time is None:
        return _error_report("Could not parse generation time from SMC report.")

    now = dt.datetime.now(JST)
    elapsed = now - gen_time
    elapsed_hours = elapsed.total_seconds() / 3600

    print(f"Fetching 5M data from {gen_time.strftime('%H:%M JST')} to now...")
    df = fetch_price_data(gen_time, now)
    if df.empty:
        return _error_report("No price data available for the monitoring window.")

    current_price = float(df["Close"].iloc[-1])
    price_at_report = smc_data.get("price_at_report") or float(df["Close"].iloc[0])
    entry_price = smc_data.get("entry_price")
    stop_price = smc_data.get("stop_price")
    target1 = smc_data.get("target1_price")
    direction = smc_data.get("direction", "LONG")
    scenarios = smc_data.get("scenarios", [])

    # Check each scenario
    statuses = []
    for sc in scenarios:
        status = _check_scenario_status(sc, df, entry_price, stop_price, price_at_report, direction)
        statuses.append(status)

    # Determine overall status
    active = [s for s in statuses if s["status"] == "ACTIVE"]
    approaching = [s for s in statuses if s["status"] == "APPROACHING"]

    if active:
        main_status = active[0]
    elif approaching:
        main_status = approaching[0]
    else:
        # Check for RANGING or UNEXPECTED
        price_move = abs(current_price - price_at_report) * 100
        if price_move < 20:
            main_status = {
                "scenario_type": "None",
                "scenario_name": "No scenario triggered",
                "status": "RANGING",
                "detail": f"Price moved only {price_move:.0f} pips from report price — no significant action yet.",
            }
        else:
            main_status = {
                "scenario_type": "None",
                "scenario_name": "Unexpected move",
                "status": "UNEXPECTED",
                "detail": f"Price moved {price_move:.0f} pips in a direction not projected by any scenario.",
            }

    # Build entry zone hit info
    entry_hit = _check_entry_zone_hit(df, entry_price, direction)

    # Current P&L if entry was hit
    if entry_hit["hit"] and entry_price:
        if direction == "LONG":
            pl_pips = (current_price - entry_price) * 100
        else:
            pl_pips = (entry_price - current_price) * 100
    else:
        pl_pips = None

    # Format report
    report = _format_live_check(
        smc_data, now, elapsed_hours, current_price, price_at_report,
        main_status, statuses, entry_hit, pl_pips, target1, stop_price, direction,
    )
    return report, main_status


def _check_scenario_status(scenario, df, entry_price, stop_price, price_at_report, direction):
    """Determine the status of a single scenario."""
    sc_type = scenario["type"]
    key_level = scenario["key_level"]
    current_price = float(df["Close"].iloc[-1])

    result = {
        "scenario_type": sc_type,
        "scenario_name": scenario["name"],
        "status": "NOT TRIGGERED",
        "detail": "",
    }

    if sc_type == "Primary":
        if entry_price is not None and stop_price is not None:
            # Check if price touched entry zone
            if direction == "LONG":
                touched = float(df["Low"].min()) <= entry_price
                bounced = touched and current_price > entry_price
                approaching = not touched and abs(current_price - entry_price) * 100 < 10 and current_price > entry_price
                invalidated = float(df["Close"].min()) < stop_price
                failed = touched and current_price < entry_price and not invalidated
            else:
                touched = float(df["High"].max()) >= entry_price
                bounced = touched and current_price < entry_price
                approaching = not touched and abs(current_price - entry_price) * 100 < 10 and current_price < entry_price
                invalidated = float(df["Close"].max()) > stop_price
                failed = touched and current_price > entry_price and not invalidated

            if invalidated:
                result["status"] = "INVALIDATED"
                result["detail"] = f"Price broke through stop level ({stop_price:.2f})"
            elif bounced:
                result["status"] = "ACTIVE"
                # Find when zone was touched
                if direction == "LONG":
                    touch_idx = df["Low"].idxmin()
                else:
                    touch_idx = df["High"].idxmax()
                touch_time = touch_idx.strftime("%H:%M JST")
                result["detail"] = f"Price touched entry zone and bounced. Zone hit at {touch_time}."
            elif failed:
                result["status"] = "ACTIVE"
                pl = (current_price - entry_price) * 100 if direction == "LONG" else (entry_price - current_price) * 100
                result["detail"] = f"Entry zone hit but price didn't hold — currently {pl:+.0f} pips from entry."
            elif approaching:
                result["status"] = "APPROACHING"
                dist = abs(current_price - entry_price) * 100
                result["detail"] = f"Price is {dist:.0f} pips from entry zone and moving toward it."
            else:
                if touched:
                    result["detail"] = f"Entry zone at {entry_price:.2f} was touched but scenario unclear."
                else:
                    result["detail"] = f"Entry zone at {entry_price:.2f} not yet reached."

    elif sc_type == "Alternative":
        if key_level is not None:
            if direction == "LONG":
                broke_level = float(df["Low"].min()) < key_level
                # Check for bullish displacement after sweep
                displacement = False
                if broke_level:
                    sweep_idx = df["Low"].idxmin()
                    after_sweep = df.loc[df.index > sweep_idx]
                    if not after_sweep.empty:
                        bodies = (after_sweep["Close"] - after_sweep["Open"]).abs() * 100
                        displacement = (bodies > 15).any()
                approaching = abs(current_price - key_level) * 100 < 10 and current_price > key_level
                # Check held below for >30 min
                held_below = False
                if broke_level:
                    below = df[df["Close"] < key_level]
                    if len(below) >= 6:  # 6 x 5min = 30 min
                        held_below = True
            else:
                broke_level = float(df["High"].max()) > key_level
                displacement = False
                if broke_level:
                    sweep_idx = df["High"].idxmax()
                    after_sweep = df.loc[df.index > sweep_idx]
                    if not after_sweep.empty:
                        bodies = (after_sweep["Close"] - after_sweep["Open"]).abs() * 100
                        displacement = (bodies > 15).any()
                approaching = abs(current_price - key_level) * 100 < 10 and current_price < key_level
                held_below = False
                if broke_level:
                    above = df[df["Close"] > key_level]
                    if len(above) >= 6:
                        held_below = True

            if broke_level and displacement:
                result["status"] = "ACTIVE"
                result["detail"] = f"Price broke {key_level:.2f} and showed displacement — sweep in progress."
            elif broke_level and held_below and not displacement:
                result["status"] = "INVALIDATED"
                result["detail"] = f"Price broke {key_level:.2f} but held beyond for >30 min without displacement."
            elif approaching:
                result["status"] = "APPROACHING"
                dist = abs(current_price - key_level) * 100
                result["detail"] = f"Price is {dist:.0f} pips from sweep level {key_level:.2f}."
            else:
                result["detail"] = f"Sweep level {key_level:.2f} not reached. Low was {float(df['Low'].min()):.2f}."

    elif sc_type == "Tail Risk":
        # Check for flash move (>100 pips in <30 min)
        closes = df["Close"].values
        for i in range(6, len(closes)):  # 6 candles = 30 min
            window_move = abs(float(closes[i]) - float(closes[i - 6])) * 100
            if window_move > 100:
                result["status"] = "ACTIVE"
                result["detail"] = f"Flash move detected: {window_move:.0f} pips in 30 minutes."
                return result

        # Check approaching intervention level
        intervention_level = 160.00
        if key_level:
            intervention_level = key_level
        dist = abs(current_price - intervention_level) * 100
        if dist < 20:
            # Check if moving toward it
            recent = df["Close"].iloc[-6:] if len(df) >= 6 else df["Close"]
            moving_toward = (float(recent.iloc[-1]) - float(recent.iloc[0])) > 0  # moving up toward 160
            if moving_toward:
                result["status"] = "APPROACHING"
                result["detail"] = f"Price is {dist:.0f} pips from intervention level {intervention_level:.0f} and moving toward it."
            else:
                result["detail"] = f"Price near intervention level but moving away."
        else:
            result["detail"] = "Not triggered."

    return result


def _check_entry_zone_hit(df, entry_price, direction):
    """Check if price reached the entry zone during the window."""
    if entry_price is None:
        return {"hit": False, "time": None}

    if direction == "LONG":
        touched = df[df["Low"] <= entry_price]
    else:
        touched = df[df["High"] >= entry_price]

    if touched.empty:
        return {"hit": False, "time": None}

    hit_time = touched.index[0].strftime("%H:%M JST")
    return {"hit": True, "time": hit_time}


def _format_live_check(smc_data, now, elapsed_hours, current_price, price_at_report,
                        main_status, all_statuses, entry_hit, pl_pips, target1, stop_price, direction):
    """Format the live check report as markdown."""
    gen_time = smc_data["generation_time"]
    lines = []
    lines.append(f"## Module 09 — Scenario Monitor (Live Check)")
    lines.append(f"**SMC Report:** {gen_time.strftime('%Y-%m-%d %H:%M JST')}")
    lines.append(f"**Check Time:** {now.strftime('%Y-%m-%d %H:%M JST')} ({elapsed_hours:.1f}h elapsed)")
    lines.append(f"**Price at Report:** {price_at_report:.2f}")
    lines.append(f"**Current Price:** {current_price:.2f}")
    lines.append("")

    status_label = main_status["status"]
    sc_name = main_status.get("scenario_name", "Unknown")
    sc_type = main_status.get("scenario_type", "")
    if sc_type and sc_type != "None":
        lines.append(f"### Status: {sc_type.upper()} {status_label} — {sc_name}")
    else:
        lines.append(f"### Status: {status_label}")
    lines.append(main_status.get("detail", ""))
    lines.append("")

    # Entry zone info
    hit_str = f"YES at {entry_hit['time']}" if entry_hit["hit"] else "NO"
    lines.append(f"**Entry zone hit:** {hit_str}")

    if pl_pips is not None:
        sign = "+" if pl_pips >= 0 else ""
        lines.append(f"**Current P&L:** {sign}{pl_pips:.0f} pips from entry")

    if target1:
        t1_dist = abs(current_price - target1) * 100
        lines.append(f"**Target 1:** {target1:.2f} — {t1_dist:.0f} pips away")

    if stop_price:
        stop_dist = abs(current_price - stop_price) * 100
        if direction == "LONG":
            stop_rel = "above" if current_price > stop_price else "below"
        else:
            stop_rel = "below" if current_price < stop_price else "above"
        warning = " ⚠" if stop_dist < 5 else ""
        lines.append(f"**Stop:** {stop_price:.2f} — {stop_dist:.0f} pips {stop_rel}{warning}")

    lines.append("")
    lines.append("### Other Scenarios")
    for s in all_statuses:
        if s["scenario_type"] == main_status.get("scenario_type"):
            continue
        lines.append(f"- {s['scenario_type']}: {s['scenario_name']}: {s['status']} — {s['detail']}")

    return "\n".join(lines)


# ── Job 2: Scorecard ──────────────────────────────────────────────────────

def run_scorecard(smc_data):
    """Score each scenario after the 12h window closes."""
    gen_time = smc_data["generation_time"]
    if gen_time is None:
        return _error_report("Could not parse generation time from SMC report.")

    window_end = gen_time + dt.timedelta(hours=12)
    now = dt.datetime.now(JST)

    if now < window_end:
        remaining = (window_end - now).total_seconds() / 3600
        return (
            f"## Module 09 — Scenario Scorecard\n\n"
            f"12h window not yet closed. Closes at {window_end.strftime('%H:%M JST')} "
            f"({remaining:.1f}h remaining).\n\n"
            f"Run `/usdjpy-scorecard` after {window_end.strftime('%H:%M JST')}."
        ), None

    print(f"Fetching 5M data for full 12h window: {gen_time.strftime('%H:%M')} — {window_end.strftime('%H:%M JST')}...")
    df = fetch_price_data(gen_time, window_end)
    if df.empty:
        return _error_report("No price data available for the 12h window.")

    direction = smc_data.get("direction", "LONG")
    entry_price = smc_data.get("entry_price")
    stop_price = smc_data.get("stop_price")
    target1 = smc_data.get("target1_price")
    target2 = smc_data.get("target2_price")
    scenarios = smc_data.get("scenarios", [])

    # Actual price action
    actual_high = float(df["High"].max())
    actual_low = float(df["Low"].min())
    actual_close = float(df["Close"].iloc[-1])
    high_time = df["High"].idxmax().strftime("%H:%M JST")
    low_time = df["Low"].idxmin().strftime("%H:%M JST")
    close_time = df.index[-1].strftime("%H:%M JST")

    # Entry zone hit?
    entry_hit = _check_entry_zone_hit(df, entry_price, direction)

    # Score each scenario
    scored = []
    for sc in scenarios:
        outcome = _score_scenario(sc, df, entry_price, stop_price, target1, direction)
        scored.append(outcome)

    # Determine best match
    priority = {"HIT": 0, "PARTIAL": 1, "MISS": 2, "NO TRADE": 3}
    best = min(scored, key=lambda s: priority.get(s["outcome"], 4)) if scored else None

    # Theoretical P&L (if entry was hit)
    theo_pl = None
    mae = None
    mfe = None
    if entry_hit["hit"] and entry_price:
        if direction == "LONG":
            theo_pl = (actual_close - entry_price) * 100
            mae = (float(df.loc[df.index >= df[df["Low"] <= entry_price].index[0]]["Low"].min()) - entry_price) * 100
            mfe = (float(df.loc[df.index >= df[df["Low"] <= entry_price].index[0]]["High"].max()) - entry_price) * 100
        else:
            theo_pl = (entry_price - actual_close) * 100
            mae = (entry_price - float(df.loc[df.index >= df[df["High"] >= entry_price].index[0]]["High"].max())) * 100
            mfe = (entry_price - float(df.loc[df.index >= df[df["High"] >= entry_price].index[0]]["Low"].min())) * 100

    # Save to CSV
    row = _build_csv_row(smc_data, scored, best, entry_hit,
                          actual_high, actual_low, actual_close,
                          theo_pl, mae, mfe)
    csv_path = _append_to_scorecard(row)

    # Running stats
    stats = _compute_running_stats(csv_path)

    # Format report
    report = _format_scorecard(
        smc_data, gen_time, window_end, actual_high, actual_low, actual_close,
        high_time, low_time, close_time, scored, best, entry_hit,
        theo_pl, mae, mfe, stats,
    )

    # Build structured result for Supabase push
    outcome_by_type = {}
    for sc in scored:
        t = sc["type"].lower().replace(" ", "_")
        outcome_by_type[t] = sc["outcome"]

    scorecard_result = {
        "type": best["type"] if best else None,
        "window_start": gen_time.isoformat() if gen_time else None,
        "window_end": window_end.isoformat() if window_end else None,
        "actual_high": actual_high,
        "actual_low": actual_low,
        "actual_close": actual_close,
        "primary_outcome": outcome_by_type.get("primary"),
        "alternative_outcome": outcome_by_type.get("alternative"),
        "tail_risk_outcome": outcome_by_type.get("tail_risk"),
        "best_match": best["type"] if best else None,
        "entry_zone_hit": entry_hit["hit"],
        "theoretical_pl_pips": theo_pl,
        "mae_pips": mae,
        "mfe_pips": mfe,
    }
    return report, scorecard_result


def _score_scenario(scenario, df, entry_price, stop_price, target1, direction):
    """Score a single scenario: HIT / PARTIAL / MISS / NO TRADE."""
    sc_type = scenario["type"]
    key_level = scenario["key_level"]
    result = {
        "type": sc_type,
        "name": scenario["name"],
        "probability": scenario["probability"],
        "outcome": "MISS",
        "detail": "",
    }

    if sc_type == "Primary":
        if entry_price is None:
            result["outcome"] = "NO TRADE"
            result["detail"] = "No entry price defined"
            return result

        if direction == "LONG":
            zone_touched = float(df["Low"].min()) <= entry_price
            if zone_touched and target1:
                toward_target = float(df["High"].max()) - entry_price
                full_target_dist = target1 - entry_price
                if full_target_dist > 0:
                    progress = toward_target / full_target_dist
                    if progress >= 1.0:
                        result["outcome"] = "HIT"
                        result["detail"] = f"Entry zone hit, target reached ({target1:.2f})"
                    elif progress >= 0.5:
                        result["outcome"] = "PARTIAL"
                        result["detail"] = f"Entry zone hit, {progress:.0%} toward target"
                    else:
                        result["outcome"] = "MISS"
                        result["detail"] = f"Entry zone hit but only {progress:.0%} toward target"
            elif zone_touched:
                result["outcome"] = "PARTIAL"
                result["detail"] = "Entry zone hit but no target defined"
            else:
                result["outcome"] = "MISS"
                result["detail"] = f"Entry zone ({entry_price:.2f}) never reached. Low was {float(df['Low'].min()):.2f}."
        else:
            zone_touched = float(df["High"].max()) >= entry_price
            if zone_touched and target1:
                toward_target = entry_price - float(df["Low"].min())
                full_target_dist = entry_price - target1
                if full_target_dist > 0:
                    progress = toward_target / full_target_dist
                    if progress >= 1.0:
                        result["outcome"] = "HIT"
                        result["detail"] = f"Entry zone hit, target reached ({target1:.2f})"
                    elif progress >= 0.5:
                        result["outcome"] = "PARTIAL"
                        result["detail"] = f"Entry zone hit, {progress:.0%} toward target"
                    else:
                        result["outcome"] = "MISS"
                        result["detail"] = f"Entry zone hit but only {progress:.0%} toward target"
            elif zone_touched:
                result["outcome"] = "PARTIAL"
                result["detail"] = "Entry zone hit but no target defined"
            else:
                result["outcome"] = "MISS"
                result["detail"] = f"Entry zone ({entry_price:.2f}) never reached."

    elif sc_type == "Alternative":
        if key_level is None:
            result["outcome"] = "MISS"
            result["detail"] = "No sweep level defined"
            return result

        if direction == "LONG":
            broke = float(df["Low"].min()) < key_level
        else:
            broke = float(df["High"].max()) > key_level

        if broke:
            # Check if displacement followed
            if direction == "LONG":
                sweep_idx = df["Low"].idxmin()
                after = df.loc[df.index > sweep_idx]
                if not after.empty:
                    recovery = float(after["High"].max()) - key_level
                    if recovery * 100 > 30:
                        result["outcome"] = "HIT"
                        result["detail"] = f"Sweep below {key_level:.2f} + strong recovery ({recovery * 100:.0f} pips)"
                    else:
                        result["outcome"] = "PARTIAL"
                        result["detail"] = f"Sweep below {key_level:.2f} but weak recovery ({recovery * 100:.0f} pips)"
                else:
                    result["outcome"] = "PARTIAL"
                    result["detail"] = f"Sweep below {key_level:.2f} at end of window"
            else:
                sweep_idx = df["High"].idxmax()
                after = df.loc[df.index > sweep_idx]
                if not after.empty:
                    recovery = key_level - float(after["Low"].min())
                    if recovery * 100 > 30:
                        result["outcome"] = "HIT"
                        result["detail"] = f"Sweep above {key_level:.2f} + strong drop ({recovery * 100:.0f} pips)"
                    else:
                        result["outcome"] = "PARTIAL"
                        result["detail"] = f"Sweep above {key_level:.2f} but weak drop ({recovery * 100:.0f} pips)"
                else:
                    result["outcome"] = "PARTIAL"
                    result["detail"] = f"Sweep above {key_level:.2f} at end of window"
        else:
            result["detail"] = f"Sweep level {key_level:.2f} not reached."

    elif sc_type == "Tail Risk":
        # Check for flash move >100 pips in 30 min
        closes = df["Close"].values
        triggered = False
        for i in range(6, len(closes)):
            window_move = abs(float(closes[i]) - float(closes[i - 6])) * 100
            if window_move > 100:
                triggered = True
                break

        if triggered:
            result["outcome"] = "HIT"
            result["detail"] = "Flash move >100 pips detected."
        else:
            max_move = 0
            for i in range(6, len(closes)):
                move = abs(float(closes[i]) - float(closes[i - 6])) * 100
                max_move = max(max_move, move)
            if max_move > 50:
                result["outcome"] = "PARTIAL"
                result["detail"] = f"Significant move ({max_move:.0f} pips in 30 min) but below 100 pip threshold."
            else:
                result["outcome"] = "MISS"
                result["detail"] = "No flash move detected."

    return result


def _build_csv_row(smc_data, scored, best, entry_hit,
                    actual_high, actual_low, actual_close,
                    theo_pl, mae, mfe):
    """Build a dict for CSV logging."""
    row = {
        "date": smc_data["date"],
        "generation_time": smc_data["generation_time"].strftime("%H:%M") if smc_data["generation_time"] else "",
        "direction": smc_data["direction"],
        "grade": smc_data["grade"],
        "setup_type": smc_data["setup_type"],
        "entry_price": smc_data.get("entry_price", ""),
        "stop_price": smc_data.get("stop_price", ""),
        "target1_price": smc_data.get("target1_price", ""),
        "target2_price": smc_data.get("target2_price", ""),
    }

    for i, sc in enumerate(scored[:3], 1):
        row[f"scenario{i}_name"] = sc["name"]
        row[f"scenario{i}_prob"] = sc["probability"]
        row[f"scenario{i}_outcome"] = sc["outcome"]

    # Pad if fewer than 3 scenarios
    for i in range(len(scored) + 1, 4):
        row[f"scenario{i}_name"] = ""
        row[f"scenario{i}_prob"] = ""
        row[f"scenario{i}_outcome"] = ""

    row["best_match"] = best["type"] if best else ""
    row["entry_zone_hit"] = "YES" if entry_hit["hit"] else "NO"
    row["actual_high"] = f"{actual_high:.2f}"
    row["actual_low"] = f"{actual_low:.2f}"
    row["actual_close"] = f"{actual_close:.2f}"
    row["theoretical_pl_pips"] = f"{theo_pl:.1f}" if theo_pl is not None else ""
    row["mae_pips"] = f"{mae:.1f}" if mae is not None else ""
    row["mfe_pips"] = f"{mfe:.1f}" if mfe is not None else ""

    return row


CSV_COLUMNS = [
    "date", "generation_time", "direction", "grade", "setup_type",
    "entry_price", "stop_price", "target1_price", "target2_price",
    "scenario1_name", "scenario1_prob", "scenario1_outcome",
    "scenario2_name", "scenario2_prob", "scenario2_outcome",
    "scenario3_name", "scenario3_prob", "scenario3_outcome",
    "best_match", "entry_zone_hit", "actual_high", "actual_low", "actual_close",
    "theoretical_pl_pips", "mae_pips", "mfe_pips",
]


def _append_to_scorecard(row):
    """Append a row to the scenario_log.csv. Skip if date already logged."""
    scorecard_dir = os.path.join(PROJECT_ROOT, "output", "scorecard")
    os.makedirs(scorecard_dir, exist_ok=True)
    csv_path = os.path.join(scorecard_dir, "scenario_log.csv")

    # Check for duplicate date
    if os.path.exists(csv_path):
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for existing in reader:
                if existing.get("date") == row.get("date"):
                    print(f"  Scorecard already has entry for {row['date']} — skipping append.")
                    return csv_path

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    print(f"  Appended scorecard row for {row['date']}")
    return csv_path


def _compute_running_stats(csv_path):
    """Compute running stats from the scorecard CSV."""
    if not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return None

    if len(df) < 10:
        return {"n": len(df), "enough": False}

    stats = {"n": len(df), "enough": True}

    # Primary accuracy
    s1 = df["scenario1_outcome"]
    stats["primary_accuracy"] = ((s1 == "HIT") | (s1 == "PARTIAL")).sum() / len(s1) * 100

    # Alternative accuracy
    s2 = df["scenario2_outcome"]
    valid_s2 = s2[s2 != ""]
    if len(valid_s2) > 0:
        stats["alt_accuracy"] = ((valid_s2 == "HIT") | (valid_s2 == "PARTIAL")).sum() / len(valid_s2) * 100
    else:
        stats["alt_accuracy"] = 0

    # Tail risk frequency
    s3 = df["scenario3_outcome"]
    valid_s3 = s3[s3 != ""]
    if len(valid_s3) > 0:
        stats["tail_frequency"] = ((valid_s3 == "HIT") | (valid_s3 == "PARTIAL")).sum() / len(valid_s3) * 100
    else:
        stats["tail_frequency"] = 0

    # Entry zone hit rate
    stats["entry_hit_rate"] = (df["entry_zone_hit"] == "YES").sum() / len(df) * 100

    # Avg theoretical P&L
    pl = pd.to_numeric(df["theoretical_pl_pips"], errors="coerce")
    stats["avg_pl"] = pl.mean() if pl.notna().any() else 0

    # P&L by grade
    for grade in ["A+", "B", "C"]:
        grade_rows = df[df["grade"] == grade]
        grade_pl = pd.to_numeric(grade_rows["theoretical_pl_pips"], errors="coerce")
        stats[f"grade_{grade}_pl"] = grade_pl.mean() if grade_pl.notna().any() else 0

    return stats


def _format_scorecard(smc_data, gen_time, window_end, actual_high, actual_low,
                       actual_close, high_time, low_time, close_time,
                       scored, best, entry_hit, theo_pl, mae, mfe, stats):
    """Format the scorecard report as markdown."""
    lines = []
    lines.append("## Module 09 — Scenario Scorecard")
    lines.append(f"**SMC Report:** {gen_time.strftime('%Y-%m-%d %H:%M JST')}")
    lines.append(f"**Window:** {gen_time.strftime('%H:%M')} — {window_end.strftime('%H:%M JST')} (12h closed)")
    lines.append("")

    if best:
        lines.append(f"### Result: {best['type'].upper()} SCENARIO — {best['outcome']}")
    else:
        lines.append("### Result: NO SCENARIOS SCORED")
    lines.append("")

    lines.append("**Actual price action:**")
    lines.append(f"- High: {actual_high:.2f} (at {high_time})")
    lines.append(f"- Low: {actual_low:.2f} (at {low_time})")
    lines.append(f"- Close: {actual_close:.2f} (at {close_time})")
    lines.append("")

    lines.append("**Scenario outcomes:**")
    lines.append("| Scenario | Projected | Actual | Score |")
    lines.append("|----------|-----------|--------|-------|")
    for sc in scored:
        lines.append(f"| {sc['type']}: {sc['name'][:30]} | {sc['probability']}% | {sc['detail'][:50]} | {sc['outcome']} |")
    lines.append("")

    if best:
        lines.append(f"**Best match:** {best['type']} — {best['name']}")

    if theo_pl is not None:
        sign = "+" if theo_pl >= 0 else ""
        lines.append(f"**Theoretical P&L:** {sign}{theo_pl:.0f} pips")

    if mae is not None and mfe is not None:
        lines.append(f"**MAE:** {mae:.0f} pips | **MFE:** +{mfe:.0f} pips")

    # Running stats
    if stats and stats.get("enough"):
        lines.append("")
        lines.append(f"### Running Stats (N={stats['n']} reports)")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Primary accuracy | {stats['primary_accuracy']:.0f}% (HIT + PARTIAL) |")
        lines.append(f"| Alternative accuracy | {stats['alt_accuracy']:.0f}% |")
        lines.append(f"| Tail risk frequency | {stats['tail_frequency']:.0f}% |")
        lines.append(f"| Entry zone hit rate | {stats['entry_hit_rate']:.0f}% |")
        lines.append(f"| Avg theoretical P&L | {stats['avg_pl']:+.0f} pips |")
        for grade in ["A+", "B", "C"]:
            key = f"grade_{grade}_pl"
            if key in stats:
                lines.append(f"| Grade {grade} avg P&L | {stats[key]:+.0f} pips |")
    elif stats:
        lines.append("")
        lines.append(f"*{stats['n']}/10 reports logged — running stats available after 10.*")

    return "\n".join(lines)


# ── Email ──────────────────────────────────────────────────────────────────

def send_monitor_email(report_path, mode, status_info=None):
    """Send the monitor/scorecard report via email."""
    # Import send_report
    sys.path.insert(0, PROJECT_ROOT)
    from send_report import load_config, send_report as _send_email_raw

    config = load_config()
    email_config = config.get("email", {})
    if not email_config.get("enabled", False):
        print("Email disabled in config.yaml.")
        return False

    password = os.environ.get("USDJPY_EMAIL_PASSWORD")
    if not password:
        print("USDJPY_EMAIL_PASSWORD not set — skipping email.")
        return False

    from_addr = email_config["from_address"]
    to_addr = email_config["to_address"]
    smtp_host = email_config["smtp_host"]
    smtp_port = email_config["smtp_port"]

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    report_text = open(report_path, "r").read()

    if mode == "check" and status_info:
        sc_name = status_info.get("scenario_name", "Unknown")
        sc_status = status_info.get("status", "UNKNOWN")
        subject = f"USD/JPY Monitor — {sc_name} {sc_status}"
    elif mode == "scorecard" and status_info:
        outcome = status_info.get("outcome", "")
        sc_type = status_info.get("type", "").upper()
        subject = f"USD/JPY Scorecard — {sc_type} {outcome}"
    else:
        subject = f"USD/JPY Monitor — {mode}"

    msg = MIMEMultipart("mixed")
    msg["From"] = f"USD/JPY Analyst <{from_addr}>"
    msg["To"] = to_addr
    msg["Subject"] = subject

    # Body summary (first 2 lines)
    summary_lines = [l for l in report_text.split("\n") if l.strip() and not l.startswith("#")][:3]
    msg.attach(MIMEText("\n".join(summary_lines), "plain", "utf-8"))

    # Attach .md
    md_att = MIMEText(report_text, "plain", "utf-8")
    md_att.add_header("Content-Disposition", "attachment", filename=os.path.basename(report_path))
    msg.attach(md_att)

    try:
        if smtp_port == 587:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(from_addr, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(from_addr, password)
                server.send_message(msg)
        print(f"  Email sent to {to_addr}: {subject}")
        return True
    except Exception as e:
        print(f"  Email failed: {e}")
        return False


# ── Save & Main ──────────────────────────────────────────────────────────

def save_report(report_md, mode):
    """Save the monitor/scorecard report."""
    today = dt.date.today().strftime("%Y-%m-%d")

    if mode == "check":
        out_dir = os.path.join(PROJECT_ROOT, "output", "daily")
        filename = f"monitor_{today}.md"
    else:
        out_dir = os.path.join(PROJECT_ROOT, "output", "scorecard")
        filename = f"scorecard_{today}.md"

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w") as f:
        f.write(report_md)
    print(f"  Saved: {path}")
    return path


def _error_report(msg):
    return f"## Module 09 — Scenario Monitor\n\n**Error:** {msg}", None


def main():
    parser = argparse.ArgumentParser(description="Module 09: Scenario Monitor")
    parser.add_argument("--mode", choices=["check", "scorecard"], default="check",
                        help="check = live status, scorecard = post-session scoring")
    parser.add_argument("--no-email", action="store_true", help="Skip email delivery")
    args = parser.parse_args()

    print(f"=== Module 09 — Scenario Monitor ({args.mode}) ===")

    # Find latest SMC report
    smc_path = find_latest_smc_report()
    if not smc_path:
        print("ERROR: No SMC report found in ./output/daily/smc_*.md")
        print("Run /usdjpy-entry first to generate an SMC report.")
        sys.exit(1)
    print(f"Reading: {smc_path}")

    smc_data = parse_smc_report(smc_path)
    print(f"  Date: {smc_data['date']}")
    print(f"  Direction: {smc_data['direction']}")
    print(f"  Grade: {smc_data['grade']}")
    print(f"  Scenarios: {len(smc_data['scenarios'])}")

    if args.mode == "check":
        report, status_info = run_live_check(smc_data)
    else:
        report, status_info = run_scorecard(smc_data)

    # Save report
    report_path = save_report(report, args.mode)

    # Print to stdout
    print("\n" + report)

    # Push scorecard to Supabase
    if args.mode == "scorecard" and status_info is not None:
        try:
            from scripts.push_to_supabase import push_scorecard
            push_scorecard(status_info, smc_report_date=smc_data["date"])
        except Exception as e:
            print(f"  Supabase push failed (non-blocking): {e}")

    # Email
    if not args.no_email:
        send_monitor_email(report_path, args.mode, status_info)

    print("\nDone.")


if __name__ == "__main__":
    main()
