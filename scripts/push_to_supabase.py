#!/usr/bin/env python3
"""
push_to_supabase.py — Push report data to Supabase for the web dashboard.

Usage:
    python3 scripts/push_to_supabase.py <report.md>                    # auto-detect type
    python3 scripts/push_to_supabase.py <report.md> --type smc         # explicit type
    python3 scripts/push_to_supabase.py --scorecard <scorecard_data>   # push scorecard JSON
    python3 scripts/push_to_supabase.py --journal <trade_dict>         # push journal entry

Can also be imported and called from other scripts:
    from scripts.push_to_supabase import push_report, push_scorecard, push_journal_entry
"""

import argparse
import datetime as dt
import json
import os
import re
import sys

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

JST = dt.timezone(dt.timedelta(hours=9))


# ── Config ────────────────────────────────────────────────────────────────

def load_config():
    with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
        return yaml.safe_load(f)


def get_supabase_client():
    """Create a Supabase client using service_role key (bypasses RLS)."""
    from supabase import create_client

    config = load_config()
    sb_config = config.get("supabase", {})
    url = sb_config.get("url")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", sb_config.get("service_role_key", ""))

    if not url or not key:
        raise RuntimeError(
            "Supabase not configured. Set supabase.url in config.yaml "
            "and SUPABASE_SERVICE_ROLE_KEY env var."
        )

    return create_client(url, key)


# ── Report Type Detection ─────────────────────────────────────────────────

def detect_report_type(filepath):
    """Detect report type from filename."""
    basename = os.path.basename(filepath)
    if basename.startswith("smc_") and not basename.startswith("smc_levels_") and not basename.startswith("smc_fix_"):
        return "smc"
    # Check parent directory
    parent = os.path.basename(os.path.dirname(filepath))
    if parent == "weekly":
        return "weekly"
    return "daily"


def extract_date_from_filename(filepath):
    """Extract YYYY-MM-DD from filename."""
    basename = os.path.basename(filepath)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", basename)
    return m.group(1) if m else None


# ── SMC Report Parser ─────────────────────────────────────────────────────

def parse_smc_report(filepath):
    """Parse an SMC report into structured data for Supabase.

    Reuses the same regex patterns as run_scenario_monitor.py.
    """
    with open(filepath, "r") as f:
        content = f.read()

    data = {}
    report_date = extract_date_from_filename(filepath)
    data["date"] = report_date
    data["report_type"] = "smc"

    # Generation time
    m = re.search(r"\*Generated:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*JST\*", content)
    if not m:
        m = re.search(r"Generated at (\d{2}:\d{2}) JST", content)
        if m and report_date:
            data["generation_time"] = f"{report_date}T{m.group(1)}:00+09:00"
        else:
            data["generation_time"] = None
    else:
        data["generation_time"] = dt.datetime.strptime(
            m.group(1), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=JST).isoformat()

    # Direction
    m = re.search(r"\*\*Direction:\*\*\s*(\w+)", content)
    data["direction"] = m.group(1) if m else "NEUTRAL"

    # Confidence
    m = re.search(r"\*\*Confidence:\*\*\s*(\w+)", content)
    data["confidence"] = m.group(1).upper() if m else "LOW"

    # Grade
    m = re.search(r"Grade\s*\*\*(\w\+?)\*\*", content)
    data["grade"] = m.group(1) if m else None

    # Setup type
    m = re.search(r"\*\*Setup Type:\*\*\s*(.+?)$", content, re.MULTILINE)
    data["setup_type"] = m.group(1).strip() if m else None

    # Entry plan values
    m = re.search(r"\|\s*Entry\s*\|\s*([\d.]+)", content)
    data["entry_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Stop Loss\s*\|\s*([\d.]+)", content)
    data["stop_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Target 1\s*\|\s*([\d.]+)", content)
    data["target1_price"] = float(m.group(1)) if m else None

    m = re.search(r"\|\s*Target 2\s*\|\s*([\d.]+)", content)
    data["target2_price"] = float(m.group(1)) if m else None

    # Confluence score
    m = re.search(r"\*\*Confluence Score:\*\*\s*([\d.]+)", content)
    data["confluence_score"] = float(m.group(1)) if m else None

    # Confirmation status
    m = re.search(r"\*\*Status:\*\*\s*(CONFIRMED|PENDING|NOT_AT_ZONE)", content)
    data["confirmation_status"] = m.group(1) if m else None

    # Current price (price at report)
    m = re.search(r"\*\*Price at Report:\*\*\s*([\d.]+)", content)
    if not m:
        m = re.search(r"Price at\s+([\d.]+)\s+is in", content)
    data["current_price"] = float(m.group(1)) if m else None

    # Market structure per timeframe
    for tf, col in [("4h", "4H"), ("1h", "1H"), ("15m", "15M"), ("5m", "5M")]:
        m = re.search(rf"\|\s*{col}\s*\|\s*(\w+)\s*\|", content)
        data[f"market_structure_{tf}"] = m.group(1) if m else None

    # Premium/Discount
    m = re.search(r"\*\*(DEEP_PREMIUM|PREMIUM|OTE|DISCOUNT|DEEP_DISCOUNT|DEEP PREMIUM|DEEP DISCOUNT)\*\*", content)
    if m:
        data["premium_discount"] = m.group(1).replace(" ", "_")
    else:
        data["premium_discount"] = None

    # Recommendation (from Module 07 context)
    m = re.search(r"\*\*Recommendation:\*\*\s*(.+?)(?:\n---|\n\n)", content, re.DOTALL)
    rec = m.group(1).strip() if m else None
    # Filter out empty/separator-only results
    if rec and rec.replace("-", "").strip() == "":
        rec = None
    data["recommendation"] = rec

    # Risk alerts — find the "**Risk Alerts:**" block and grab bullet lines
    risk_alerts = []
    alerts_match = re.search(r"\*\*Risk Alerts:\*\*\s*\n((?:- .+\n?)+)", content)
    if alerts_match:
        for line in alerts_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                # Clean up leading "| " artifacts from table-style alerts
                alert_text = line[2:].strip()
                if alert_text.startswith("| "):
                    alert_text = alert_text[2:].strip()
                risk_alerts.append(alert_text)
    data["risk_alerts"] = risk_alerts

    # Warnings (contradictions)
    warnings = []
    for m in re.finditer(r"⚠\s*(.+?)$", content, re.MULTILINE):
        warnings.append(m.group(1).strip())
    data["warnings"] = warnings

    data["md_content"] = content

    # Parse scenarios
    data["scenarios"] = _parse_scenarios(content)

    # Parse zones
    data["zones"] = _parse_zones(content, data.get("current_price"))

    # Parse liquidity levels
    data["liquidity_levels"] = _parse_liquidity_levels(content)

    return data


def _get_section(content, header):
    """Extract text under a markdown header until the next header or end."""
    pattern = re.compile(
        rf"(?:^|\n)#+\s*.*{re.escape(header)}.*\n(.*?)(?=\n#+\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(content)
    return m.group(1) if m else ""


def _parse_scenarios(content):
    """Parse the 3 playbook scenarios from the report."""
    scenarios = []
    pattern = re.compile(
        r"####\s+(Primary|Alternative|Tail Risk):\s*(.+?)\((\d+)%\)\s*\n(.*?)(?=####|\Z)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        scenario_type_raw = m.group(1).strip()
        type_map = {"Primary": "primary", "Alternative": "alternative", "Tail Risk": "tail_risk"}
        scenario_type = type_map.get(scenario_type_raw, scenario_type_raw.lower().replace(" ", "_"))
        name = m.group(2).strip()
        prob = int(m.group(3))
        body = m.group(4).strip()

        kl = re.search(r"\*\*Key Level:\*\*\s*([\d.]+)", body)
        key_level = float(kl.group(1)) if kl else None

        tr = re.search(r"\*\*Trigger:\*\*\s*(.+?)$", body, re.MULTILINE)
        trigger = tr.group(1).strip() if tr else ""

        inv = re.search(r"\*\*Invalidation:\*\*\s*(.+?)$", body, re.MULTILINE)
        invalidation = inv.group(1).strip() if inv else ""

        act = re.search(r"\*\*Action:\*\*\s*(.+?)$", body, re.MULTILINE)
        action = act.group(1).strip() if act else ""

        # Parse session descriptions
        sessions = re.findall(r"- \*\*(\w+):\*\*\s*(.+?)$", body, re.MULTILINE)
        session1_name = sessions[0][0] if len(sessions) > 0 else None
        session1_desc = sessions[0][1] if len(sessions) > 0 else None
        session2_name = sessions[1][0] if len(sessions) > 1 else None
        session2_desc = sessions[1][1] if len(sessions) > 1 else None

        scenarios.append({
            "scenario_type": scenario_type,
            "name": name,
            "probability": prob,
            "key_level": key_level,
            "trigger_description": trigger,
            "action": action,
            "invalidation": invalidation,
            "session1_name": session1_name,
            "session1_description": session1_desc,
            "session2_name": session2_name,
            "session2_description": session2_desc,
        })

    return scenarios


def _parse_zones(content, current_price=None):
    """Parse active zones from the markdown table."""
    zones = []
    # Match: | 4H | Bullish Ob | 153.08-153.18 | Long | Unmitigated |
    pattern = re.compile(
        r"\|\s*(\d+[HM])\s*\|\s*(.+?)\s*\|\s*([\d.]+)-([\d.]+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|"
    )
    for m in pattern.finditer(content):
        zone_type = m.group(2).strip()
        zone_low = float(m.group(3))
        zone_high = float(m.group(4))
        is_intervention = "(INTERVENTION)" in zone_type
        zone_type_clean = zone_type.replace(" (INTERVENTION)", "").strip()

        distance_pips = None
        is_nearby = False
        if current_price is not None:
            mid = (zone_high + zone_low) / 2
            distance_pips = int(abs(current_price - mid) * 100)
            is_nearby = distance_pips <= 100

        zones.append({
            "timeframe": m.group(1),
            "zone_type": zone_type_clean,
            "zone_high": zone_high,
            "zone_low": zone_low,
            "direction": m.group(5),
            "status": m.group(6),
            "is_intervention": is_intervention,
            "distance_pips": distance_pips,
            "is_nearby": is_nearby,
        })

    return zones


def _parse_liquidity_levels(content):
    """Parse key liquidity levels from the markdown table."""
    levels = []
    # Find the liquidity levels section
    start = content.find("Key Liquidity Levels")
    if start == -1:
        return levels
    section = content[start:]
    # Stop at next major section
    end = section.find("\n---", 10)
    if end > 0:
        section = section[:end]

    # Match: | 161.95 | INTERVENTION | BOJ intervention level (161.95) |
    pattern = re.compile(
        r"\|\s*([\d.]+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|"
    )
    for m in pattern.finditer(section):
        try:
            price = float(m.group(1))
        except ValueError:
            continue
        levels.append({
            "price": price,
            "level_type": m.group(2).strip(),
            "significance": m.group(3).strip(),
        })

    return levels


# ── Daily/Weekly Report Parser ─────────────────────────────────────────────

def parse_daily_weekly_report(filepath, report_type):
    """Parse a daily or weekly report into structured data."""
    with open(filepath, "r") as f:
        content = f.read()

    data = {}
    report_date = extract_date_from_filename(filepath)
    data["date"] = report_date
    data["report_type"] = report_type

    # Generation time — try to find timestamp in report
    m = re.search(r"\*Generated:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*JST\*", content)
    if m:
        data["generation_time"] = dt.datetime.strptime(
            m.group(1), "%Y-%m-%d %H:%M"
        ).replace(tzinfo=JST).isoformat()
    else:
        data["generation_time"] = None

    # Direction from Module 07
    overall_match = re.search(r"\*\*Overall:\s*(.+?)\*\*", content)
    if not overall_match:
        overall_match = re.search(r"\*\*Bias:\s*(.+?)\*\*", content)
    if not overall_match:
        overall_match = re.search(r"\*\*Bias:\*\*\s*(.+)", content)

    direction = "NEUTRAL"
    if overall_match:
        bias_text = overall_match.group(1).strip().upper()
        if "BULLISH" in bias_text:
            direction = "LONG"
        elif "BEARISH" in bias_text:
            direction = "SHORT"
    data["direction"] = direction

    # Confidence
    conv_match = re.search(r"\*\*Conviction:\s*(\w+)", content)
    if not conv_match:
        conv_match = re.search(r"\*\*Conviction:\*\*\s*(\w+)", content)
    data["confidence"] = conv_match.group(1).upper() if conv_match else "LOW"

    # Recommendation
    rec_match = re.search(r"### Recommendation\n\n(.+?)(?:\n\n---|\Z)", content, re.DOTALL)
    data["recommendation"] = rec_match.group(1).strip() if rec_match else None

    # Risk alerts — parse from table rows: | Alert | **STATUS** | Detail |
    risk_alerts = []
    alert_pattern = re.compile(
        r"^\|\s*(.+?)\s*\|\s*\*\*(\w+)\*\*\s*\|\s*(.+?)\s*\|$", re.MULTILINE
    )
    for m in alert_pattern.finditer(content):
        alert_name = m.group(1).strip().lstrip("| ").strip()
        status = m.group(2).strip()
        detail = m.group(3).strip()
        if status in ("ELEVATED", "CRITICAL", "YES", "UNKNOWN"):
            risk_alerts.append(f"{alert_name}: {status} — {detail}")
    data["risk_alerts"] = risk_alerts
    data["warnings"] = []
    data["md_content"] = content

    # Parse module_data
    data["module_data"] = _parse_module_data(content)

    # Fields not applicable to daily/weekly
    data["grade"] = None
    data["setup_type"] = None
    data["entry_price"] = None
    data["stop_price"] = None
    data["target1_price"] = None
    data["target2_price"] = None
    data["confluence_score"] = None
    data["confirmation_status"] = None
    data["current_price"] = None
    data["market_structure_4h"] = None
    data["market_structure_1h"] = None
    data["market_structure_15m"] = None
    data["market_structure_5m"] = None
    data["premium_discount"] = None

    return data


# ── Module Data Parser ────────────────────────────────────────────────────

def _parse_module_data(content):
    """Parse module-level structured data from a daily/weekly report."""
    module_data = {}

    # ── Module 01 — Macro Regime ──
    m01_section = re.search(
        r"## 01 — Macro Regime\s*\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m01_section:
        sec = m01_section.group(1)
        m01 = {}

        # Signal and confidence from header line
        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m01["signal"] = sig.group(1) if sig else None
        m01["confidence"] = sig.group(2) if sig else None

        # Metrics from table rows: | US 10Y | 4.44% | +0.10 | +0.47 | +0.30 |
        # (some columns may have — instead of numbers)
        for label, key in [("US 10Y", "us_10y"), ("JP 10Y", "jp_10y"), ("Spread", "spread")]:
            row = re.search(
                rf"\|\s*{label}\s*\|\s*([\d.]+)%?\s*\|\s*([+-]?[\d.]+)\s*\|\s*([+-]?[\d.]+)",
                sec,
            )
            if row:
                m01[key] = float(row.group(1))
                if key == "spread":
                    m01["spread_1w_chg"] = float(row.group(2))
                    m01["spread_1m_chg"] = float(row.group(3))

        # Spread direction and divergence
        sd = re.search(r"\*\*Spread Direction:\*\*\s*(\w+)", sec)
        m01["spread_trend"] = sd.group(1) if sd else None

        dv = re.search(r"\*\*Divergence Check:\*\*\s*(\w+)", sec)
        m01["divergence"] = dv.group(1) if dv else None

        module_data["module_01"] = m01

    # ── Module 03 — Technicals ──
    m03_section = re.search(
        r"## 03 — Technicals\s*\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m03_section:
        sec = m03_section.group(1)
        m03 = {}

        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m03["signal"] = sig.group(1) if sig else None
        m03["confidence"] = sig.group(2) if sig else None

        # Table rows — two formats:
        # Daily: | Price | 159.70 | — |  and  | 50 SMA | 156.58 | Above price |
        # Weekly: | Price vs SMA50 | Above (156.58) | Bullish |
        for label, key in [
            ("Price", "price"), ("50 SMA", "sma50"), ("200 SMA", "sma200"),
            ("RSI \\(14\\)", "rsi"),
        ]:
            row = re.search(rf"\|\s*{label}\s*\|\s*([\d.]+)", sec)
            if row:
                m03[key] = float(row.group(1))

        # Weekly format: extract price from Key Levels line or module 01 USD/JPY row
        if "price" not in m03:
            kl = re.search(r"\*\*Key Levels:\*\*.*?(\d{2,3}\.\d+)", sec)
            if kl:
                m03["price"] = float(kl.group(1))
            elif "module_01" in module_data:
                # Fall back to Module 01's USD/JPY value
                usd_row = re.search(r"\|\s*USD/JPY\s*\|\s*([\d.]+)", content)
                if usd_row:
                    m03["price"] = float(usd_row.group(1))

        # Weekly format: extract SMA values from parentheses
        if "sma50" not in m03:
            row = re.search(r"Price vs SMA50\s*\|.*?\(([\d.]+)\)", sec)
            if row:
                m03["sma50"] = float(row.group(1))
        if "sma200" not in m03:
            row = re.search(r"Price vs SMA200\s*\|.*?\(([\d.]+)\)", sec)
            if row:
                m03["sma200"] = float(row.group(1))

        # SMA Cross — daily: | SMA Cross | GOLDEN |  weekly: | SMA50 vs SMA200 | Golden Cross |
        sc = re.search(r"\|\s*SMA Cross\s*\|\s*(\w+)", sec)
        if not sc:
            sc = re.search(r"\|\s*SMA50 vs SMA200\s*\|\s*(\w+)", sec)
        m03["sma_cross"] = sc.group(1).upper() if sc else None

        # MACD — daily: | MACD | 0.8834 / 0.8555 | BULLISH |
        # Extract numeric values (line / signal) and direction
        macd_nums = re.search(r"\|\s*MACD\s*\|\s*([\d.-]+)\s*/\s*([\d.-]+)", sec)
        if macd_nums:
            m03["macd_line"] = float(macd_nums.group(1))
            m03["macd_signal_value"] = float(macd_nums.group(2))
        mc = re.search(r"\|\s*MACD\s*\|.*?\|\s*(\w+)\s*\|", sec)
        m03["macd_signal"] = mc.group(1).upper() if mc else None

        # Ichimoku — daily: | Ichimoku Cloud | ABOVE |  weekly: same
        ic = re.search(r"\|\s*Ichimoku Cloud\s*\|\s*(\w+)", sec)
        m03["ichimoku"] = ic.group(1).upper() if ic else None

        # Ichimoku numeric — from line: **Ichimoku:** Tenkan 158.98 | Kijun 157.43
        ichi_vals = re.search(r"Tenkan\s+([\d.]+)\s*\|\s*Kijun\s+([\d.]+)", sec)
        if ichi_vals:
            m03["ichimoku_tenkan"] = float(ichi_vals.group(1))
            m03["ichimoku_kijun"] = float(ichi_vals.group(2))

        module_data["module_03"] = m03

    # ── Module 05 — Cross-Asset Correlations ──
    m05_section = re.search(
        r"## 05 — Cross-Asset Correlations\s*\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m05_section:
        sec = m05_section.group(1)
        m05 = {}

        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m05["signal"] = sig.group(1) if sig else None
        m05["confidence"] = sig.group(2) if sig else None

        regime = re.search(r"(?:Risk\s+)?Regime:?\*?\*?\s*(\w+)", sec)
        m05["regime"] = regime.group(1) if regime else None

        # Correlation table rows: | Asset | 0.284 | Expected | Status |
        correlations = {}
        asset_map = {
            "S&P 500": "sp500", "Nikkei 225": "nikkei",
            "Gold": "gold", "VIX": "vix", "WTI Oil": "oil",
        }
        breakdowns = []
        for asset_label, asset_key in asset_map.items():
            row = re.search(
                rf"\|\s*{re.escape(asset_label)}\s*\|\s*([+-]?[\d.]+)\s*\|\s*\w+\s*\|\s*(.+?)\s*\|",
                sec,
            )
            if row:
                correlations[asset_key] = float(row.group(1))
                status_raw = row.group(2).strip().replace("*", "").upper()
                if "BREAKDOWN" in status_raw:
                    breakdowns.append(asset_key)

        m05["correlations"] = correlations
        m05["breakdowns"] = breakdowns

        module_data["module_05"] = m05

    # ── Module 02 — Policy & Politics (weekly only) ──
    m02_section = re.search(
        r"## 02 — Policy & Politics\s*\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m02_section:
        sec = m02_section.group(1)
        m02 = {}

        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m02["signal"] = sig.group(1) if sig else None
        m02["confidence"] = sig.group(2) if sig else None

        # BOJ fields
        boj_fields = {
            "Policy Rate": "boj_rate",
            "Stance": "boj_stance",
            "Last Meeting": "boj_last_meeting",
            "Next Meeting": "boj_next_meeting",
            "Key Quote": "boj_key_quote",
        }
        # Find BOJ section, then parse its table
        boj_sec = re.search(r"### BOJ\s*\n(.*?)(?=\n### |\Z)", sec, re.DOTALL)
        if boj_sec:
            for label, key in boj_fields.items():
                row = re.search(
                    rf"\|\s*{re.escape(label)}\s*\|\s*(.+?)\s*\|",
                    boj_sec.group(1),
                )
                if row:
                    m02[key] = row.group(1).strip()

        # Fed fields
        fed_fields = {
            "Fed Funds Rate": "fed_rate",
            "Stance": "fed_stance",
            "Last Meeting": "fed_last_meeting",
            "Next Meeting": "fed_next_meeting",
            "Key Quote": "fed_key_quote",
        }
        fed_sec = re.search(r"### Fed\s*\n(.*?)(?=\n### |\Z)", sec, re.DOTALL)
        if fed_sec:
            for label, key in fed_fields.items():
                row = re.search(
                    rf"\|\s*{re.escape(label)}\s*\|\s*(.+?)\s*\|",
                    fed_sec.group(1),
                )
                if row:
                    m02[key] = row.group(1).strip()

        # Intervention Risk
        ir = re.search(r"\*\*MOF Rhetoric Level:\*\*\s*(.+)", sec)
        m02["intervention_risk"] = ir.group(1).strip() if ir else None

        li = re.search(r"\*\*Last Intervention:\*\*\s*(.+)", sec)
        m02["last_intervention"] = li.group(1).strip() if li else None

        # Japanese Political Developments
        pr = re.search(r"\*\*Political Risk:\*\*\s*(\w+)", sec)
        m02["political_risk"] = pr.group(1).strip() if pr else None

        pd = re.search(r"\*\*Key Development:\*\*\s*(.+)", sec)
        m02["political_development"] = pd.group(1).strip() if pd else None

        module_data["module_02"] = m02

    # ── Module 04 — Positioning / COT (weekly only) ──
    m04_section = re.search(
        r"## 04 — Positioning.*?\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m04_section:
        sec = m04_section.group(1)
        m04 = {}

        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m04["signal"] = sig.group(1) if sig else None
        m04["confidence"] = sig.group(2) if sig else None

        # Net Speculative Position: extract number from e.g. "-62,806 contracts"
        np_row = re.search(
            r"\|\s*Net Speculative Position\s*\|\s*([+-]?[\d,]+)\s*contracts",
            sec,
        )
        if np_row:
            m04["net_position"] = int(np_row.group(1).replace(",", ""))

        # Week-over-Week Change
        wow_row = re.search(
            r"\|\s*Week-over-Week Change\s*\|\s*([+-]?[\d,]+)\s*contracts",
            sec,
        )
        if wow_row:
            m04["wow_change"] = int(wow_row.group(1).replace(",", ""))

        # 3-Year Percentile: extract number from e.g. "0th" or "85th"
        pct_row = re.search(
            r"\|\s*3-Year Percentile\s*\|\s*(\d+)(?:st|nd|rd|th)",
            sec,
        )
        if pct_row:
            m04["percentile"] = int(pct_row.group(1))

        # Crowding Status
        crowd_row = re.search(
            r"\|\s*Crowding Status\s*\|\s*(.+?)\s*\|",
            sec,
        )
        if crowd_row:
            crowd_val = crowd_row.group(1).strip()
            m04["crowded"] = "CROWDED" in crowd_val.upper()
        else:
            m04["crowded"] = False

        # Crowded direction based on net position
        if m04.get("net_position") is not None:
            m04["crowded_direction"] = "SHORT_JPY" if m04["net_position"] < 0 else "LONG_JPY"

        module_data["module_04"] = m04

    # ── Module 06 — Seasonality & Flows (weekly only) ──
    m06_section = re.search(
        r"## 06 — Seasonality.*?\n(.*?)(?=\n## \d|\Z)", content, re.DOTALL
    )
    if m06_section:
        sec = m06_section.group(1)
        m06 = {}

        sig = re.search(r"\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)", sec)
        m06["signal"] = sig.group(1) if sig else None
        m06["confidence"] = sig.group(2) if sig else None

        # Factor table: | Current Month | March — Historical bias: ... |
        factor_map = {
            "Current Month": "seasonal_bias",
            "Fiscal Year Position": "fy_position",
            "Repatriation Flow": "repatriation",
        }
        for label, key in factor_map.items():
            row = re.search(
                rf"\|\s*{re.escape(label)}\s*\|\s*(.+?)\s*\|",
                sec,
            )
            if row:
                val = row.group(1).strip()
                # Strip bold markers
                val = re.sub(r"\*\*", "", val)
                m06[key] = val

        # Upcoming Events table: | Date | Event | Expected Impact |
        upcoming_events = []
        events_sec = re.search(
            r"### Upcoming Events.*?\n(.*?)(?=\n### |\n## |\Z)", sec, re.DOTALL
        )
        if events_sec:
            event_pattern = re.compile(
                r"\|\s*([A-Z][a-z]{2}\s+\d{1,2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|"
            )
            for em in event_pattern.finditer(events_sec.group(1)):
                upcoming_events.append({
                    "date": em.group(1).strip(),
                    "event": em.group(2).strip(),
                    "impact": em.group(3).strip(),
                })
        m06["upcoming_events"] = upcoming_events

        # Trade Balance
        tb = re.search(r"\*\*Trade Balance:\*\*\s*(.+)", sec)
        m06["trade_balance"] = tb.group(1).strip() if tb else None

        module_data["module_06"] = m06

    # ── Module 07 — Checklist ──
    m07_section = re.search(
        r"## 07 — Checklist\s*\n(.*?)(?=\n## |\n---\s*\n\s*## |\Z)", content, re.DOTALL
    )
    if m07_section:
        sec = m07_section.group(1)
        m07 = {}

        # Overall direction
        overall = re.search(r"\*\*Overall:\s*(.+?)\*\*", sec)
        if overall:
            bias_text = overall.group(1).strip().upper()
            if "BULLISH" in bias_text:
                m07["direction"] = "LONG"
            elif "BEARISH" in bias_text:
                m07["direction"] = "SHORT"
            else:
                m07["direction"] = "NEUTRAL"
        else:
            m07["direction"] = "NEUTRAL"

        # Conviction
        conv = re.search(r"\*\*Conviction:\s*(\w+)\*\*", sec)
        m07["confidence"] = conv.group(1) if conv else "LOW"

        # Score: +2 / +6
        score = re.search(r"\*\*Score:\s*([+-]?\d+)\s*/\s*([+-]?\d+)\*\*", sec)
        if score:
            m07["score"] = int(score.group(1))
            m07["max_score"] = int(score.group(2))

        # Modules: 3/6
        mods = re.search(r"\*\*Modules:\s*(\d+)/(\d+)\*\*", sec)
        if mods:
            m07["modules_active"] = int(mods.group(1))
            m07["modules_total"] = int(mods.group(2))

        # Conviction capped warning
        m07["conviction_capped"] = "conviction capped" in sec.lower()

        # Parse signal rows: | 1 | Macro Regime | BULL | MEDIUM | note |
        signals = []
        signal_pattern = re.compile(
            r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|"
        )
        for sm in signal_pattern.finditer(sec):
            mod_num = sm.group(1).strip()
            name = sm.group(2).strip()
            direction = sm.group(3).strip()
            confidence = sm.group(4).strip()
            note = sm.group(5).strip()
            # Skip table header rows and separator rows
            if name == "Factor" or name.startswith("-"):
                continue
            signals.append({
                "module": mod_num.zfill(2),
                "name": name,
                "direction": direction,
                "confidence": confidence,
                "note": note,
            })
        m07["signals"] = signals

        module_data["module_07"] = m07

    return module_data


# ── Push Functions ─────────────────────────────────────────────────────────

def push_report(filepath, report_type=None):
    """Parse and push a report to Supabase. Returns the report_id."""
    if report_type is None:
        report_type = detect_report_type(filepath)

    print(f"  Pushing {report_type} report to Supabase...")

    if report_type == "smc":
        data = parse_smc_report(filepath)
    else:
        data = parse_daily_weekly_report(filepath, report_type)

    client = get_supabase_client()

    # Build the report row
    report_row = {
        "date": data["date"],
        "report_type": data["report_type"],
        "generation_time": data.get("generation_time"),
        "direction": data.get("direction"),
        "confidence": data.get("confidence"),
        "grade": data.get("grade"),
        "setup_type": data.get("setup_type"),
        "entry_price": data.get("entry_price"),
        "stop_price": data.get("stop_price"),
        "target1_price": data.get("target1_price"),
        "target2_price": data.get("target2_price"),
        "confluence_score": data.get("confluence_score"),
        "confirmation_status": data.get("confirmation_status"),
        "current_price": data.get("current_price"),
        "market_structure_4h": data.get("market_structure_4h"),
        "market_structure_1h": data.get("market_structure_1h"),
        "market_structure_15m": data.get("market_structure_15m"),
        "market_structure_5m": data.get("market_structure_5m"),
        "premium_discount": data.get("premium_discount"),
        "recommendation": data.get("recommendation"),
        "risk_alerts": json.dumps(data.get("risk_alerts", [])),
        "warnings": json.dumps(data.get("warnings", [])),
        "md_content": data.get("md_content"),
    }

    # Add module_data for daily/weekly reports
    if report_type in ("daily", "weekly") and data.get("module_data"):
        report_row["module_data"] = json.dumps(data["module_data"])

    # Upsert report (date + report_type is unique)
    result = client.table("reports").upsert(
        report_row,
        on_conflict="date,report_type",
    ).execute()

    report_id = result.data[0]["id"]
    print(f"    Report upserted: {report_id}")

    # For SMC reports, also push scenarios, zones, liquidity levels
    if report_type == "smc":
        # Delete existing child rows (cascade would handle this on report delete,
        # but upsert doesn't delete — so we clean up manually)
        client.table("scenarios").delete().eq("report_id", report_id).execute()
        client.table("zones").delete().eq("report_id", report_id).execute()
        client.table("liquidity_levels").delete().eq("report_id", report_id).execute()

        # Push scenarios
        scenarios = data.get("scenarios", [])
        if scenarios:
            for sc in scenarios:
                sc["report_id"] = report_id
            client.table("scenarios").insert(scenarios).execute()
            print(f"    Pushed {len(scenarios)} scenarios")

        # Push zones
        zones = data.get("zones", [])
        if zones:
            for z in zones:
                z["report_id"] = report_id
            client.table("zones").insert(zones).execute()
            print(f"    Pushed {len(zones)} zones")

        # Push liquidity levels
        levels = data.get("liquidity_levels", [])
        if levels:
            for lv in levels:
                lv["report_id"] = report_id
            client.table("liquidity_levels").insert(levels).execute()
            print(f"    Pushed {len(levels)} liquidity levels")

        # Upload playbook chart PNG to storage
        chart_url = _upload_playbook_chart(client, filepath, data["date"])
        if chart_url:
            client.table("reports").update(
                {"playbook_chart_url": chart_url}
            ).eq("id", report_id).execute()
            print(f"    Playbook chart uploaded: {chart_url}")

    # For daily/weekly reports, upload chart PNGs to storage
    if report_type in ("daily", "weekly"):
        chart_urls = _upload_daily_charts(client, filepath, data["date"])
        if chart_urls:
            client.table("reports").update(chart_urls).eq("id", report_id).execute()
            print(f"    Daily chart URLs stored: {list(chart_urls.keys())}")

    return report_id


def _upload_playbook_chart(client, report_filepath, report_date):
    """Upload the playbook chart PNG to Supabase storage. Returns public URL or None."""
    report_dir = os.path.dirname(report_filepath)
    chart_filename = f"smc_playbook_{report_date}.png"
    chart_path = os.path.join(report_dir, chart_filename)

    if not os.path.exists(chart_path):
        print(f"    Playbook chart not found: {chart_path}")
        return None

    storage_path = f"playbook/{chart_filename}"

    with open(chart_path, "rb") as f:
        chart_bytes = f.read()

    # Upload (upsert to overwrite on re-run)
    client.storage.from_("charts").upload(
        storage_path,
        chart_bytes,
        file_options={"content-type": "image/png", "upsert": "true"},
    )

    # Get public URL
    url = client.storage.from_("charts").get_public_url(storage_path)
    return url


def _upload_daily_charts(client, report_filepath, report_date):
    """Upload daily chart PNGs to Supabase storage. Returns dict of public URLs."""
    report_dir = os.path.dirname(report_filepath)
    chart_map = {
        "macro_chart_url": f"macro_spread_{report_date}.png",
        "technicals_chart_url": f"technicals_{report_date}.png",
        "correlations_chart_url": f"correlations_{report_date}.png",
    }

    urls = {}
    for url_key, filename in chart_map.items():
        chart_path = os.path.join(report_dir, filename)
        if not os.path.exists(chart_path):
            print(f"    Chart not found, skipping: {filename}")
            continue

        storage_path = f"daily/{filename}"

        with open(chart_path, "rb") as f:
            chart_bytes = f.read()

        client.storage.from_("charts").upload(
            storage_path,
            chart_bytes,
            file_options={"content-type": "image/png", "upsert": "true"},
        )

        urls[url_key] = client.storage.from_("charts").get_public_url(storage_path)
        print(f"    Uploaded {filename}")

    return urls


def push_scorecard(scorecard_data, smc_report_date=None):
    """Push scorecard results to Supabase.

    scorecard_data: dict with keys matching the scorecard table columns.
    smc_report_date: YYYY-MM-DD of the SMC report being scored.
    """
    print("  Pushing scorecard to Supabase...")
    client = get_supabase_client()

    # Find the report_id for the SMC report
    report_id = None
    if smc_report_date:
        result = client.table("reports").select("id").eq(
            "date", smc_report_date
        ).eq("report_type", "smc").execute()
        if result.data:
            report_id = result.data[0]["id"]

    if not report_id:
        print("    Warning: No matching SMC report found in Supabase — pushing scorecard without report link")

    row = {
        "report_id": report_id,
        "date": smc_report_date,
        "window_start": scorecard_data.get("window_start"),
        "window_end": scorecard_data.get("window_end"),
        "actual_high": scorecard_data.get("actual_high"),
        "actual_low": scorecard_data.get("actual_low"),
        "actual_close": scorecard_data.get("actual_close"),
        "primary_outcome": scorecard_data.get("primary_outcome"),
        "alternative_outcome": scorecard_data.get("alternative_outcome"),
        "tail_risk_outcome": scorecard_data.get("tail_risk_outcome"),
        "best_match": scorecard_data.get("best_match"),
        "entry_zone_hit": scorecard_data.get("entry_zone_hit"),
        "theoretical_pl_pips": scorecard_data.get("theoretical_pl_pips"),
        "mae_pips": scorecard_data.get("mae_pips"),
        "mfe_pips": scorecard_data.get("mfe_pips"),
    }

    # Delete existing scorecard for this date+window (re-run safe, preserves 2nd session)
    window_start = scorecard_data.get("window_start")
    if smc_report_date and window_start:
        client.table("scorecard").delete().eq("date", smc_report_date).eq("window_start", window_start).execute()
    elif smc_report_date:
        client.table("scorecard").delete().eq("date", smc_report_date).execute()
    elif report_id:
        client.table("scorecard").delete().eq("report_id", report_id).execute()

    result = client.table("scorecard").insert(row).execute()
    print(f"    Scorecard pushed (report_id={report_id}, date={smc_report_date})")
    return result.data[0]["id"] if result.data else None


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


def push_journal_entry(trade_dict):
    """Push a single journal entry to Supabase.

    trade_dict: dict with keys from TRADE_LOG_FIELDS in journal.py.
    """
    print("  Pushing journal entry to Supabase...")
    client = get_supabase_client()

    # Try to find a matching SMC report for the trade date
    report_id = None
    date_open = trade_dict.get("date_open", "")
    if date_open:
        trade_date = date_open[:10]  # YYYY-MM-DD
        result = client.table("reports").select("id").eq(
            "date", trade_date
        ).eq("report_type", "smc").execute()
        if result.data:
            report_id = result.data[0]["id"]

    # Map journal CSV fields to Supabase columns
    def _to_float_or_none(val):
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _to_ts_or_none(val):
        if not val or val == "":
            return None
        # Add JST timezone if not present
        if "+" not in val and "Z" not in val:
            return val + "+09:00"
        return val

    direction = trade_dict.get("direction", "").upper()
    if direction in ("BUY",):
        direction = "LONG"
    elif direction in ("SELL",):
        direction = "SHORT"

    bias_val = trade_dict.get("module07_bias", "")
    bias_aligned = None
    if bias_val:
        if direction == "LONG" and "BULLISH" in bias_val.upper():
            bias_aligned = True
        elif direction == "SHORT" and "BEARISH" in bias_val.upper():
            bias_aligned = True
        elif bias_val.upper() not in ("", "NEUTRAL"):
            bias_aligned = False

    row = {
        "report_id": report_id,
        "ticket": str(trade_dict.get("ticket", "")),
        "date_open": _to_ts_or_none(trade_dict.get("date_open")),
        "date_close": _to_ts_or_none(trade_dict.get("date_close")),
        "direction": direction if direction in ("LONG", "SHORT") else None,
        "entry_price": _to_float_or_none(trade_dict.get("entry")),
        "exit_price": _to_float_or_none(trade_dict.get("exit")),
        "stop_price": _to_float_or_none(trade_dict.get("stop")),
        "target_price": _to_float_or_none(trade_dict.get("target")),
        "lots": _to_float_or_none(trade_dict.get("lots")),
        "pips": _to_float_or_none(trade_dict.get("pips")),
        "pnl": _to_float_or_none(trade_dict.get("profit")),
        "grade": trade_dict.get("grade") or None,
        "setup_type": trade_dict.get("module08_scenario") or None,
        "bias_aligned": bias_aligned,
        "notes": trade_dict.get("notes") or None,
    }

    # Check for duplicate ticket
    ticket = row["ticket"]
    if ticket:
        existing = client.table("journal_entries").select("id").eq("ticket", ticket).execute()
        if existing.data:
            print(f"    Ticket {ticket} already exists — skipping")
            return existing.data[0]["id"]

    result = client.table("journal_entries").insert(row).execute()
    entry_id = result.data[0]["id"] if result.data else None
    print(f"    Journal entry pushed: {entry_id}")
    return entry_id


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Push report data to Supabase")
    parser.add_argument("filepath", nargs="?", help="Path to report .md file")
    parser.add_argument("--type", choices=["daily", "weekly", "smc"],
                        help="Report type (auto-detected if omitted)")
    args = parser.parse_args()

    if not args.filepath:
        parser.print_help()
        sys.exit(1)

    push_report(args.filepath, report_type=args.type)
    print("Done.")


if __name__ == "__main__":
    main()
