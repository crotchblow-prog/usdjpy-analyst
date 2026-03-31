#!/usr/bin/env python3
"""
run_validation.py — Cross-reference validation orchestrator.

Reads report data from Supabase, fetches external reference values, compares
with tolerances, and optionally pushes results back to Supabase.

Usage:
    python3 scripts/run_validation.py [--date YYYY-MM-DD] [--no-push]
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


# ── Config ────────────────────────────────────────────────────────────────

def load_config():
    with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
        return yaml.safe_load(f)


# ── Supabase query ────────────────────────────────────────────────────────

def fetch_module_data(date_str):
    """Read module_data from Supabase reports table for the given date.

    Tries 'daily' first, then falls back to 'weekly'.
    Returns (module_data dict, report_type str) or (None, None).
    """
    from scripts.push_to_supabase import get_supabase_client

    client = get_supabase_client()

    for report_type in ("daily", "weekly"):
        result = client.table("reports").select("id, module_data").eq(
            "date", date_str
        ).eq("report_type", report_type).execute()

        if result.data:
            row = result.data[0]
            raw = row.get("module_data")
            if raw is None:
                continue
            if isinstance(raw, str):
                raw = json.loads(raw)
            if isinstance(raw, dict):
                print(f"[supabase] Found {report_type} report for {date_str}")
                return raw, report_type

    print(f"[supabase] No report found for {date_str}")
    return None, None


# ── Value extraction ──────────────────────────────────────────────────────

def extract_our_values(module_data):
    """Extract numeric indicator values from module_data.

    Returns dict: {indicator_name: (value, module_label)}
    """
    values = {}

    # Module 01: macro
    m01 = module_data.get("module_01", {})
    if m01:
        if "us_10y" in m01:
            values["us_10y"] = (float(m01["us_10y"]), "module_01")
        if "jp_10y" in m01:
            values["jp_10y"] = (float(m01["jp_10y"]), "module_01")
        # Spread — may be nested under 'spread' key or at top level
        spread = m01.get("spread", m01.get("rate_spread"))
        if spread is not None:
            values["rate_spread"] = (float(spread), "module_01")
        # DXY spot — may be nested under 'dxy' dict or at top level
        dxy_block = m01.get("dxy", {})
        if isinstance(dxy_block, dict):
            spot_dxy = dxy_block.get("spot_dxy", dxy_block.get("spot"))
        else:
            spot_dxy = dxy_block
        if spot_dxy is None:
            spot_dxy = m01.get("spot_dxy")
        if spot_dxy is not None:
            values["spot_dxy"] = (float(spot_dxy), "module_01")

    # Module 03: technicals
    m03 = module_data.get("module_03", {})
    if m03:
        # USD/JPY spot
        price_block = m03.get("price", {})
        if isinstance(price_block, dict):
            spot = price_block.get("spot_usdjpy", price_block.get("spot", price_block.get("close")))
        else:
            spot = price_block
        if spot is None:
            spot = m03.get("spot_usdjpy")
        if spot is not None:
            values["spot_usdjpy"] = (float(spot), "module_03")

        # RSI
        rsi_block = m03.get("rsi", {})
        if isinstance(rsi_block, dict):
            rsi = rsi_block.get("rsi_14", rsi_block.get("value"))
        else:
            rsi = rsi_block
        if rsi is None:
            rsi = m03.get("rsi_14")
        if rsi is not None:
            values["rsi_14"] = (float(rsi), "module_03")

        # SMAs
        for period in (50, 200):
            key = f"sma_{period}"
            val = m03.get(key)
            if val is None:
                sma_block = m03.get("sma", {})
                if isinstance(sma_block, dict):
                    val = sma_block.get(str(period), sma_block.get(period))
            if val is not None:
                values[key] = (float(val), "module_03")

        # MACD
        macd_block = m03.get("macd", {})
        if isinstance(macd_block, dict):
            ml = macd_block.get("macd_line", macd_block.get("line", macd_block.get("macd")))
            ms = macd_block.get("macd_signal", macd_block.get("signal"))
        else:
            ml = None
            ms = None
        if ml is None:
            ml = m03.get("macd_line")
        if ms is None:
            ms = m03.get("macd_signal")
        try:
            if ml is not None:
                values["macd_line"] = (float(ml), "module_03")
        except (ValueError, TypeError):
            pass
        try:
            if ms is not None:
                values["macd_signal"] = (float(ms), "module_03")
        except (ValueError, TypeError):
            pass

    # Module 05: cross-asset correlations
    m05 = module_data.get("module_05", {})
    if m05:
        corr_block = m05.get("correlations", {})
        if isinstance(corr_block, dict):
            for asset_name, corr_val in corr_block.items():
                if corr_val is not None:
                    try:
                        key = f"corr_{asset_name.lower()}"
                        values[key] = (float(corr_val), "module_05")
                    except (ValueError, TypeError):
                        pass

    return values


# ── Comparison logic ──────────────────────────────────────────────────────

# Indicators that use percentage diff (|source - ours| / |ours|)
PCT_DIFF_INDICATORS = {"spot_usdjpy", "spot_dxy", "us_10y", "jp_10y", "rate_spread"}

# Map indicator keys to tolerance keys in config
TOLERANCE_KEYS = {
    "rsi_14":     "rsi",
    "sma_50":     "sma",
    "sma_200":    "sma",
    "macd_line":  "macd",
    "macd_signal": "macd",
    "spot_usdjpy": "spot_pct",
    "spot_dxy":   "spot_pct",
    "us_10y":     "spread_pct",
    "jp_10y":     "spread_pct",
    "rate_spread": "spread_pct",
}
# Correlation indicators match prefix "corr_*" -> "correlation"


def get_tolerance_key(indicator):
    """Return the tolerance config key for an indicator."""
    if indicator in TOLERANCE_KEYS:
        return TOLERANCE_KEYS[indicator]
    if indicator.startswith("corr_"):
        return "correlation"
    if indicator.startswith("sma_"):
        return "sma"
    return None


def compute_diff(indicator, our_val, src_val):
    """Return (diff_value, is_pct_diff) for two numeric values."""
    if indicator in PCT_DIFF_INDICATORS and our_val != 0:
        diff = abs(src_val - our_val) / abs(our_val)
        return diff, True
    # Absolute diff for RSI, SMA, MACD, correlations, etc.
    diff = abs(src_val - our_val)
    return diff, False


def classify_status(diff, tolerance):
    """Return PASS / WARN / FAIL given a diff and tolerance."""
    if diff <= tolerance:
        return "PASS"
    if diff <= 2 * tolerance:
        return "WARN"
    return "FAIL"


# ── Main logic ────────────────────────────────────────────────────────────

def run_validation(date_str, no_push=False):
    config = load_config()
    tolerances = config.get("validation", {}).get("tolerances", {})
    sources_cfg = config.get("validation", {}).get("sources", {})

    # 1. Read our values from Supabase
    module_data, report_type = fetch_module_data(date_str)
    if module_data is None:
        print(f"ERROR: No module_data found for {date_str}. Run /usdjpy-daily first.")
        return

    our_values = extract_our_values(module_data)
    if not our_values:
        print("ERROR: module_data present but no numeric indicators could be extracted.")
        return

    print(f"\nExtracted {len(our_values)} indicators from {report_type} report:")
    for k, (v, mod) in sorted(our_values.items()):
        print(f"  {k:30s} = {v:.4f}  ({mod})")

    # 2. Fetch external reference values
    print("\nFetching external reference values...")
    external = {}  # {source_name: {indicator: value}}

    if sources_cfg.get("yahoo", True):
        from scripts.validation_sources import fetch_yahoo
        external["yahoo"] = fetch_yahoo(config)

    if sources_cfg.get("investing", True):
        from scripts.validation_sources import fetch_investing
        external["investing"] = fetch_investing()

    if sources_cfg.get("tradingview", True):
        from scripts.validation_sources import fetch_tradingview
        external["tradingview"] = fetch_tradingview()

    # 3. Compare each indicator against each source
    results = []  # list of comparison dicts for push / display

    for indicator, (our_val, module_label) in sorted(our_values.items()):
        tol_key = get_tolerance_key(indicator)
        tolerance = tolerances.get(tol_key) if tol_key else None

        # Collect which sources have this indicator
        source_hits = {
            src: vals[indicator]
            for src, vals in external.items()
            if indicator in vals
        }

        if not source_hits:
            results.append({
                "module": module_label,
                "indicator": indicator,
                "our_value": our_val,
                "source_name": "none",
                "source_value": None,
                "tolerance": tolerance,
                "diff": None,
                "status": "SKIP",
            })
            continue

        for src_name, src_val in source_hits.items():
            if tolerance is None:
                status = "SKIP"
                diff = None
            else:
                diff, _ = compute_diff(indicator, our_val, src_val)
                status = classify_status(diff, tolerance)

            results.append({
                "module": module_label,
                "indicator": indicator,
                "our_value": our_val,
                "source_name": src_name,
                "source_value": src_val,
                "tolerance": tolerance,
                "diff": diff,
                "status": status,
            })

    # 4. Print summary
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for r in results:
        counts[r["status"]] += 1

    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY — {date_str}")
    print(f"{'='*60}")
    print(f"  PASS  : {counts['PASS']}")
    print(f"  WARN  : {counts['WARN']}")
    print(f"  FAIL  : {counts['FAIL']}")
    print(f"  SKIP  : {counts['SKIP']}")
    print(f"{'='*60}")

    # Details for WARN + FAIL
    issues = [r for r in results if r["status"] in ("WARN", "FAIL")]
    if issues:
        print(f"\nIssues ({len(issues)}):")
        for r in issues:
            diff_str = f"{r['diff']:.6f}" if r["diff"] is not None else "N/A"
            print(
                f"  [{r['status']:4s}] {r['indicator']:30s} "
                f"ours={r['our_value']:.4f}  "
                f"{r['source_name']}={r['source_value']:.4f}  "
                f"diff={diff_str}  tol={r['tolerance']}"
            )
    else:
        print("\nAll checked indicators within tolerance.")

    # 5. Push to Supabase
    if not no_push:
        try:
            from scripts.push_to_supabase import push_validation_results
            push_validation_results(results, date_str)
        except Exception as e:
            print(f"[push] Supabase push failed (non-blocking): {e}")
    else:
        print("\n[push] Skipped (--no-push flag).")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Cross-reference USD/JPY report data against external sources."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Report date in YYYY-MM-DD format (default: today JST)",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip pushing results to Supabase",
    )
    args = parser.parse_args()

    if args.date:
        date_str = args.date
    else:
        date_str = dt.datetime.now(JST).strftime("%Y-%m-%d")

    print(f"Running validation for date: {date_str}")
    run_validation(date_str, no_push=args.no_push)


if __name__ == "__main__":
    main()
