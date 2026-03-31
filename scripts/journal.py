#!/usr/bin/env python3
"""
USD/JPY Trade Journal — Exness MT5 trade data integration.

Commands:
  import  — Import trades from Exness CSV in ./data/trades/
  sync    — Pull trades from MT5 terminal (Windows only)
  open    — Manual journal entry for a planned/active trade
  close   — Close an open journal entry
  review  — Performance summary from trade_log.csv
"""

import argparse
import csv
import datetime as dt
import glob
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRADE_LOG_PATH = os.path.join(PROJECT_ROOT, "output", "journal", "trade_log.csv")
TRADES_DIR = os.path.join(PROJECT_ROOT, "data", "trades")
JOURNAL_DIR = os.path.join(PROJECT_ROOT, "output", "journal")
DAILY_DIR = os.path.join(PROJECT_ROOT, "output", "daily")
WEEKLY_DIR = os.path.join(PROJECT_ROOT, "output", "weekly")

TRADE_LOG_FIELDS = [
    "ticket", "date_open", "date_close", "direction", "symbol", "lots",
    "entry", "exit", "stop", "target", "pips", "profit", "commission", "swap",
    "rr_planned", "rr_actual", "duration_hours",
    "module07_bias", "module07_score", "module08_scenario", "module08_confluence",
    "grade", "notes",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def ensure_dirs():
    os.makedirs(TRADES_DIR, exist_ok=True)
    os.makedirs(JOURNAL_DIR, exist_ok=True)


def load_existing_tickets():
    """Return set of ticket numbers already in trade_log.csv."""
    tickets = set()
    if not os.path.exists(TRADE_LOG_PATH):
        return tickets
    with open(TRADE_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tickets.add(row.get("ticket", ""))
    return tickets


def append_to_trade_log(trades):
    """Append trade dicts to trade_log.csv, creating header if needed."""
    file_exists = os.path.exists(TRADE_LOG_PATH)
    with open(TRADE_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        for t in trades:
            row = {k: t.get(k, "") for k in TRADE_LOG_FIELDS}
            writer.writerow(row)


def find_report_for_date(date_str):
    """Find Module 07 daily/weekly report for a given date. Returns (bias, score) or (None, None)."""
    # Try daily first, then weekly
    for directory in [DAILY_DIR, WEEKLY_DIR]:
        path = os.path.join(directory, f"{date_str}.md")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    text = f.read(2000)  # Only need the header
                # Parse bias line: > **MODERATE BULLISH** | Conviction: **LOW** | Score: **+2/+6**
                m = re.search(
                    r">\s*\*\*(.+?)\*\*\s*\|\s*Conviction:\s*\*\*(.+?)\*\*\s*\|\s*Score:\s*\*\*(.+?)\*\*",
                    text)
                if m:
                    bias = m.group(1).strip()
                    score = m.group(3).strip()
                    return bias, score
            except Exception:
                pass
    return None, None


def find_smc_for_date(date_str):
    """Find Module 08 SMC report for a given date. Returns (scenario, confluence) or (None, None)."""
    path = os.path.join(DAILY_DIR, f"smc_{date_str}.md")
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r") as f:
            text = f.read(5000)
        # Setup type
        m_scenario = re.search(r"\*\*Setup Type:\*\*\s*(.+?)$", text, re.MULTILINE)
        scenario = m_scenario.group(1).strip() if m_scenario else None
        # Confluence score
        m_conf = re.search(r"\*\*Confluence Score:\*\*\s*([\d.]+)", text)
        confluence = m_conf.group(1).strip() if m_conf else None
        return scenario, confluence
    except Exception:
        return None, None


def calc_pips(direction, entry, exit_price):
    """Calculate pips for USDJPY (1 pip = 0.01)."""
    if direction.lower() in ("buy", "long"):
        return round((exit_price - entry) * 100, 1)
    else:
        return round((entry - exit_price) * 100, 1)


def calc_duration_hours(open_time, close_time):
    """Calculate trade duration in hours."""
    if not close_time:
        return 0
    delta = close_time - open_time
    return round(delta.total_seconds() / 3600, 1)


# ── CSV Import ───────────────────────────────────────────────────────────────

def parse_exness_csv(filepath):
    """Parse an Exness MT5 CSV export file. Returns list of trade dicts.

    Exness CSV formats vary slightly. We handle:
    - Standard deal history export (comma or semicolon separated)
    - Column names may include: Ticket/Deal/Order, Open Time, Close Time,
      Type, Volume/Lots, Symbol, Open Price, Close Price, S/L, T/P,
      Commission, Swap, Profit
    """
    trades = []

    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()

    # Detect delimiter
    first_line = content.split("\n")[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","

    reader = csv.DictReader(content.splitlines(), delimiter=delimiter)

    # Normalize column names: strip whitespace, lowercase
    if reader.fieldnames:
        reader.fieldnames = [fn.strip().lower() for fn in reader.fieldnames]

    # Map various Exness column names to our internal names
    COL_MAP = {
        "ticket": ["ticket", "deal", "order", "position", "order no", "deal no"],
        "open_time": ["open time", "time", "open date", "date open"],
        "close_time": ["close time", "close date", "date close"],
        "type": ["type", "direction", "side"],
        "volume": ["volume", "lots", "lot", "size"],
        "symbol": ["symbol", "instrument", "pair"],
        "open_price": ["open price", "price open", "entry price", "open"],
        "close_price": ["close price", "price close", "exit price", "close", "price"],
        "sl": ["s/l", "sl", "stop loss", "stop"],
        "tp": ["t/p", "tp", "take profit", "target"],
        "commission": ["commission", "comm"],
        "swap": ["swap", "rollover"],
        "profit": ["profit", "p/l", "pnl", "net profit"],
    }

    def find_col(row, key):
        """Find a value in row using multiple possible column names."""
        for col_name in COL_MAP.get(key, []):
            if col_name in row:
                val = row[col_name]
                if val is not None:
                    return val.strip() if isinstance(val, str) else val
        return ""

    for row in reader:
        # Normalize row keys
        row = {k.strip().lower(): v for k, v in row.items() if k}

        symbol = find_col(row, "symbol")
        if not symbol:
            continue

        # Filter for USDJPY only
        sym_upper = symbol.upper().replace(" ", "")
        if "USDJPY" not in sym_upper and sym_upper not in ("JPY", "USD/JPY"):
            continue

        trade_type = find_col(row, "type").lower()
        # Skip non-trade entries (balance, deposit, etc.)
        if trade_type not in ("buy", "sell", "long", "short"):
            continue

        ticket = find_col(row, "ticket")
        open_time_str = find_col(row, "open_time")
        close_time_str = find_col(row, "close_time")
        volume = find_col(row, "volume")
        open_price = find_col(row, "open_price")
        close_price = find_col(row, "close_price")
        sl = find_col(row, "sl")
        tp = find_col(row, "tp")
        commission = find_col(row, "commission")
        swap = find_col(row, "swap")
        profit = find_col(row, "profit")

        # Parse times
        open_time = _parse_datetime(open_time_str)
        close_time = _parse_datetime(close_time_str)

        # Parse numeric fields
        open_price = _to_float(open_price)
        close_price = _to_float(close_price)
        sl = _to_float(sl)
        tp = _to_float(tp)
        volume = _to_float(volume)
        commission = _to_float(commission)
        swap = _to_float(swap)
        profit = _to_float(profit)

        if open_price is None:
            continue

        direction = "LONG" if trade_type in ("buy", "long") else "SHORT"
        is_open = close_time is None or close_price is None

        # Calculate pips
        pips = None
        if not is_open and close_price is not None:
            pips = calc_pips(direction, open_price, close_price)

        # Calculate R:R
        rr_planned = None
        if sl and tp and open_price and sl != open_price:
            risk = abs(open_price - sl)
            reward = abs(tp - open_price)
            rr_planned = round(reward / risk, 1) if risk > 0 else None

        rr_actual = None
        if not is_open and sl and close_price and open_price and sl != open_price:
            risk = abs(open_price - sl)
            actual_reward = abs(close_price - open_price)
            rr_actual = round(actual_reward / risk, 1) if risk > 0 else None

        duration = calc_duration_hours(open_time, close_time) if open_time else 0

        # Date for report matching
        date_str = open_time.strftime("%Y-%m-%d") if open_time else ""

        trades.append({
            "ticket": str(ticket),
            "date_open": open_time.strftime("%Y-%m-%d %H:%M") if open_time else "",
            "date_close": close_time.strftime("%Y-%m-%d %H:%M") if close_time else "",
            "direction": direction,
            "symbol": "USDJPY",
            "lots": str(volume) if volume else "",
            "entry": f"{open_price:.3f}" if open_price else "",
            "exit": f"{close_price:.3f}" if close_price and not is_open else "",
            "stop": f"{sl:.3f}" if sl else "",
            "target": f"{tp:.3f}" if tp else "",
            "pips": str(pips) if pips is not None else "",
            "profit": str(profit) if profit is not None else "",
            "commission": str(commission) if commission is not None else "",
            "swap": str(swap) if swap is not None else "",
            "rr_planned": str(rr_planned) if rr_planned else "",
            "rr_actual": str(rr_actual) if rr_actual else "",
            "duration_hours": str(duration) if duration else "",
            "_date_str": date_str,
            "_is_open": is_open,
        })

    return trades


def _parse_datetime(s):
    """Parse various datetime formats from Exness CSV."""
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",
        "%Y.%m.%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ]:
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_float(s):
    """Safely convert string to float, handling empty/non-numeric."""
    if s is None or s == "":
        return None
    try:
        # Handle comma as decimal separator (European format)
        return float(str(s).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return None


def import_trades():
    """Import trades from all CSV files in ./data/trades/."""
    ensure_dirs()

    csv_files = sorted(glob.glob(os.path.join(TRADES_DIR, "*.csv")))
    if not csv_files:
        print("No CSV files found in ./data/trades/")
        print()
        print("Export your trade history from Exness Personal Area:")
        print("  1. Log into Exness PA → Trading tab → History of orders")
        print("  2. Select your MT5 account and date range")
        print("  3. Click 'Download CSV'")
        print(f"  4. Save the file to {TRADES_DIR}/")
        print("  5. Run: python3 scripts/journal.py import")
        return

    existing = load_existing_tickets()
    all_trades = []

    for csv_file in csv_files:
        print(f"Parsing: {os.path.basename(csv_file)}")
        try:
            trades = parse_exness_csv(csv_file)
            print(f"  Found {len(trades)} USDJPY trades")
        except Exception as e:
            print(f"  Error parsing: {e}")
            continue

        for t in trades:
            if t["ticket"] in existing:
                print(f"  Skipping duplicate ticket: {t['ticket']}")
                continue

            # Auto-match with Module 07/08 reports
            date_str = t.pop("_date_str", "")
            is_open = t.pop("_is_open", False)

            m07_bias, m07_score = find_report_for_date(date_str)
            m08_scenario, m08_confluence = find_smc_for_date(date_str)

            t["module07_bias"] = m07_bias or ""
            t["module07_score"] = m07_score or ""
            t["module08_scenario"] = m08_scenario or ""
            t["module08_confluence"] = m08_confluence or ""
            t["grade"] = ""
            t["notes"] = "OPEN" if is_open else ""

            all_trades.append(t)
            existing.add(t["ticket"])

            status = "OPEN" if is_open else "CLOSED"
            bias_match = ""
            if m07_bias:
                trade_dir = t["direction"]
                if ("BULLISH" in m07_bias and trade_dir == "LONG") or \
                   ("BEARISH" in m07_bias and trade_dir == "SHORT"):
                    bias_match = " ✓ WITH bias"
                elif "NEUTRAL" in m07_bias:
                    bias_match = " ~ NEUTRAL bias"
                else:
                    bias_match = " ✗ AGAINST bias"

            pips_str = f" ({t['pips']}pips)" if t["pips"] else ""
            print(f"  + {t['ticket']}: {t['direction']} {t['entry']} → "
                  f"{t['exit'] or '???'} [{status}]{pips_str}{bias_match}")

            # Write individual markdown entry
            _write_journal_entry(t, date_str, is_open, m07_bias, m07_score,
                                 m08_scenario, m08_confluence)

    if all_trades:
        append_to_trade_log(all_trades)
        print(f"\n  Imported {len(all_trades)} new trades → {TRADE_LOG_PATH}")
        # Push to Supabase
        try:
            from scripts.push_to_supabase import push_journal_entry
            for t in all_trades:
                push_journal_entry(t)
        except Exception as e:
            print(f"  Supabase push failed (non-blocking): {e}")
    else:
        print("\n  No new trades to import (all duplicates or no USDJPY trades)")


def _write_journal_entry(trade, date_str, is_open, m07_bias, m07_score,
                         m08_scenario, m08_confluence):
    """Write an individual journal entry as markdown."""
    suffix = "open" if is_open else "closed"
    ticket = trade["ticket"]
    filename = f"{date_str}_{ticket}_{suffix}.md"
    filepath = os.path.join(JOURNAL_DIR, filename)

    lines = [
        f"# Trade Journal — {date_str}",
        "",
        f"**Ticket:** {ticket}",
        f"**Direction:** {trade['direction']}",
        f"**Symbol:** USDJPY",
        f"**Lots:** {trade['lots']}",
        f"**Status:** {'OPEN' if is_open else 'CLOSED'}",
        "",
        "## Entry/Exit",
        "",
        f"| | Price |",
        f"|---|---|",
        f"| Entry | {trade['entry']} |",
        f"| Exit | {trade['exit'] or 'OPEN'} |",
        f"| Stop | {trade['stop']} |",
        f"| Target | {trade['target']} |",
        "",
    ]

    if not is_open:
        lines.extend([
            "## Result",
            "",
            f"| | Value |",
            f"|---|---|",
            f"| Pips | {trade['pips']} |",
            f"| Profit | {trade['profit']} |",
            f"| Commission | {trade['commission']} |",
            f"| Swap | {trade['swap']} |",
            f"| R:R Planned | {trade['rr_planned']} |",
            f"| R:R Actual | {trade['rr_actual']} |",
            f"| Duration | {trade['duration_hours']}h |",
            "",
        ])

    lines.extend([
        "## System Signals at Entry",
        "",
        f"**Module 07 Bias:** {m07_bias or 'N/A'}",
        f"**Module 07 Score:** {m07_score or 'N/A'}",
    ])

    if m07_bias:
        trade_dir = trade["direction"]
        if ("BULLISH" in m07_bias and trade_dir == "LONG") or \
           ("BEARISH" in m07_bias and trade_dir == "SHORT"):
            lines.append("**Alignment:** ✓ Trade WITH system bias")
        elif "NEUTRAL" in m07_bias:
            lines.append("**Alignment:** ~ Neutral bias (no edge)")
        else:
            lines.append("**Alignment:** ✗ Trade AGAINST system bias")

    lines.extend([
        f"**Module 08 Setup:** {m08_scenario or 'N/A'}",
        f"**Module 08 Confluence:** {m08_confluence or 'N/A'}",
        "",
        "## Notes",
        "",
        "*Add your trade notes here*",
        "",
        "## Self-Assessment",
        "",
        "**Grade:** *(A/B/C/D — fill in after review)*",
        "**What went well:**",
        "**What to improve:**",
        "",
    ])

    with open(filepath, "w") as f:
        f.write("\n".join(lines))


# ── MT5 Sync ────────────────────────────────────────────────────────────────

def sync_trades():
    """Pull trades directly from MT5 terminal (Windows only)."""
    import platform
    if platform.system() != "Windows":
        print("MT5 direct connection requires Windows.")
        print("On Mac/Linux, use CSV import instead:")
        print("  python3 scripts/journal.py import")
        print()
        print("Export from Exness Personal Area:")
        print("  1. Log into Exness PA → Trading tab → History of orders")
        print("  2. Select your MT5 account and date range")
        print("  3. Click 'Download CSV'")
        print(f"  4. Save the file to {TRADES_DIR}/")
        return

    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MetaTrader5 package not installed.")
        print("  pip install MetaTrader5")
        return

    if not mt5.initialize():
        print("MT5 terminal not running — use CSV import instead.")
        print("  python3 scripts/journal.py import")
        mt5.shutdown()
        return

    print("Connected to MT5")
    account = mt5.account_info()
    if account:
        print(f"  Account: {account.login} ({account.server})")
        print(f"  Balance: {account.balance} {account.currency}")

    # Get trade history (last 90 days)
    date_from = dt.datetime.now() - dt.timedelta(days=90)
    date_to = dt.datetime.now()

    deals = mt5.history_deals_get(date_from, date_to)
    positions = mt5.positions_get(symbol="USDJPY")

    mt5.shutdown()

    if deals is None:
        deals = []
    if positions is None:
        positions = []

    existing = load_existing_tickets()
    all_trades = []

    # Process closed deals
    for deal in deals:
        if "USDJPY" not in deal.symbol:
            continue
        if deal.type not in (0, 1):  # 0=buy, 1=sell
            continue

        ticket = str(deal.ticket)
        if ticket in existing:
            continue

        direction = "LONG" if deal.type == 0 else "SHORT"
        open_time = dt.datetime.fromtimestamp(deal.time)
        date_str = open_time.strftime("%Y-%m-%d")

        m07_bias, m07_score = find_report_for_date(date_str)
        m08_scenario, m08_confluence = find_smc_for_date(date_str)

        trade = {
            "ticket": ticket,
            "date_open": open_time.strftime("%Y-%m-%d %H:%M"),
            "date_close": open_time.strftime("%Y-%m-%d %H:%M"),
            "direction": direction,
            "symbol": "USDJPY",
            "lots": str(deal.volume),
            "entry": f"{deal.price:.3f}",
            "exit": f"{deal.price:.3f}",
            "stop": "",
            "target": "",
            "pips": "",
            "profit": str(deal.profit),
            "commission": str(deal.commission),
            "swap": str(deal.swap),
            "rr_planned": "",
            "rr_actual": "",
            "duration_hours": "",
            "module07_bias": m07_bias or "",
            "module07_score": m07_score or "",
            "module08_scenario": m08_scenario or "",
            "module08_confluence": m08_confluence or "",
            "grade": "",
            "notes": "",
        }
        all_trades.append(trade)
        existing.add(ticket)

    # Process open positions
    for pos in positions:
        ticket = str(pos.ticket)
        if ticket in existing:
            continue

        direction = "LONG" if pos.type == 0 else "SHORT"
        open_time = dt.datetime.fromtimestamp(pos.time)
        date_str = open_time.strftime("%Y-%m-%d")

        m07_bias, m07_score = find_report_for_date(date_str)
        m08_scenario, m08_confluence = find_smc_for_date(date_str)

        trade = {
            "ticket": ticket,
            "date_open": open_time.strftime("%Y-%m-%d %H:%M"),
            "date_close": "",
            "direction": direction,
            "symbol": "USDJPY",
            "lots": str(pos.volume),
            "entry": f"{pos.price_open:.3f}",
            "exit": "",
            "stop": f"{pos.sl:.3f}" if pos.sl else "",
            "target": f"{pos.tp:.3f}" if pos.tp else "",
            "pips": "",
            "profit": str(pos.profit),
            "commission": str(pos.commission),
            "swap": str(pos.swap),
            "rr_planned": "",
            "rr_actual": "",
            "duration_hours": "",
            "module07_bias": m07_bias or "",
            "module07_score": m07_score or "",
            "module08_scenario": m08_scenario or "",
            "module08_confluence": m08_confluence or "",
            "grade": "",
            "notes": "OPEN",
        }
        all_trades.append(trade)
        existing.add(ticket)

    if all_trades:
        append_to_trade_log(all_trades)
        print(f"Imported {len(all_trades)} trades from MT5")
    else:
        print("No new USDJPY trades found in MT5")


# ── Manual Open ──────────────────────────────────────────────────────────────

def manual_open(direction, entry, stop, target, lots="0.01", rationale=""):
    """Create a manual journal entry for a planned/active trade."""
    ensure_dirs()

    today = dt.date.today().strftime("%Y-%m-%d")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = float(entry)
    stop = float(stop)
    target = float(target)
    lots = float(lots)

    direction = direction.upper()
    if direction not in ("LONG", "SHORT"):
        print(f"Invalid direction: {direction}. Use LONG or SHORT.")
        return

    # Calculate planned R:R
    risk = abs(entry - stop)
    reward = abs(target - entry)
    rr_planned = round(reward / risk, 1) if risk > 0 else 0

    # Generate ticket (manual entries use M + timestamp)
    ticket = f"M{dt.datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Auto-match reports
    m07_bias, m07_score = find_report_for_date(today)
    m08_scenario, m08_confluence = find_smc_for_date(today)

    trade = {
        "ticket": ticket,
        "date_open": now,
        "date_close": "",
        "direction": direction,
        "symbol": "USDJPY",
        "lots": str(lots),
        "entry": f"{entry:.3f}",
        "exit": "",
        "stop": f"{stop:.3f}",
        "target": f"{target:.3f}",
        "pips": "",
        "profit": "",
        "commission": "",
        "swap": "",
        "rr_planned": str(rr_planned),
        "rr_actual": "",
        "duration_hours": "",
        "module07_bias": m07_bias or "",
        "module07_score": m07_score or "",
        "module08_scenario": m08_scenario or "",
        "module08_confluence": m08_confluence or "",
        "grade": "",
        "notes": rationale or "OPEN",
    }

    append_to_trade_log([trade])
    _write_journal_entry(trade, today, True, m07_bias, m07_score,
                         m08_scenario, m08_confluence)

    # Push to Supabase
    try:
        from scripts.push_to_supabase import push_journal_entry
        push_journal_entry(trade)
    except Exception as e:
        print(f"  Supabase push failed (non-blocking): {e}")

    print(f"Journal entry created: {ticket}")
    print(f"  {direction} USDJPY @ {entry:.3f}")
    print(f"  Stop: {stop:.3f} | Target: {target:.3f} | R:R 1:{rr_planned}")
    if m07_bias:
        print(f"  Module 07: {m07_bias} ({m07_score})")
    if m08_scenario:
        print(f"  Module 08: {m08_scenario} (confluence {m08_confluence})")
    print(f"  Saved: {TRADE_LOG_PATH}")


# ── Manual Close ─────────────────────────────────────────────────────────────

def manual_close(ticket, exit_price, grade="", reason=""):
    """Close an open journal entry by ticket number."""
    if not os.path.exists(TRADE_LOG_PATH):
        print("No trade log found. Import or create trades first.")
        return

    exit_price = float(exit_price)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Read all trades
    with open(TRADE_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    found = False
    for row in rows:
        if row["ticket"] == ticket:
            if row["date_close"] and row["notes"] != "OPEN":
                print(f"Ticket {ticket} is already closed.")
                return

            row["date_close"] = now
            row["exit"] = f"{exit_price:.3f}"

            # Calc pips
            entry = float(row["entry"])
            pips = calc_pips(row["direction"], entry, exit_price)
            row["pips"] = str(pips)

            # Calc actual R:R
            if row["stop"]:
                stop = float(row["stop"])
                risk = abs(entry - stop)
                actual_reward = abs(exit_price - entry)
                row["rr_actual"] = str(round(actual_reward / risk, 1)) if risk > 0 else ""

            # Calc duration
            open_time = _parse_datetime(row["date_open"])
            close_time = _parse_datetime(now)
            if open_time and close_time:
                row["duration_hours"] = str(calc_duration_hours(open_time, close_time))

            if grade:
                row["grade"] = grade.upper()
            if reason:
                row["notes"] = reason
            elif row["notes"] == "OPEN":
                row["notes"] = ""

            found = True
            profit_str = f"+{pips}" if pips > 0 else str(pips)
            print(f"Closed ticket {ticket}: {row['direction']} USDJPY")
            print(f"  Entry: {row['entry']} → Exit: {exit_price:.3f} ({profit_str} pips)")
            if grade:
                print(f"  Grade: {grade.upper()}")
            break

    if not found:
        print(f"Ticket {ticket} not found in trade log.")
        return

    # Rewrite the file
    with open(TRADE_LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_LOG_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in TRADE_LOG_FIELDS})

    print(f"  Updated: {TRADE_LOG_PATH}")


# ── Review ───────────────────────────────────────────────────────────────────

def review_performance():
    """Generate performance summary from trade_log.csv."""
    if not os.path.exists(TRADE_LOG_PATH):
        print("No trade log found. Import or create trades first.")
        return

    with open(TRADE_LOG_PATH, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Separate closed and open trades
    closed = [r for r in rows if r.get("date_close") and r.get("notes") != "OPEN"
              and r.get("pips")]
    open_trades = [r for r in rows if not r.get("date_close") or r.get("notes") == "OPEN"]

    print("=" * 60)
    print("USD/JPY Trade Journal — Performance Review")
    print("=" * 60)
    print()

    if not closed and not open_trades:
        print("No trades in the journal yet.")
        return

    # Open positions
    if open_trades:
        print(f"Open Positions: {len(open_trades)}")
        for t in open_trades:
            print(f"  {t['ticket']}: {t['direction']} @ {t['entry']} "
                  f"(SL: {t['stop'] or 'N/A'}, TP: {t['target'] or 'N/A'})")
        print()

    if not closed:
        print("No closed trades to analyze yet.")
        return

    # Core stats
    total = len(closed)
    pips_list = [float(t["pips"]) for t in closed if t["pips"]]
    profit_list = [float(t["profit"]) for t in closed if t["profit"]]
    wins = [p for p in pips_list if p > 0]
    losses = [p for p in pips_list if p <= 0]
    win_rate = len(wins) / total * 100 if total > 0 else 0

    print(f"Total Closed Trades: {total}")
    print(f"Win Rate: {win_rate:.1f}% ({len(wins)}W / {len(losses)}L)")
    print()

    if pips_list:
        print(f"Total Pips: {sum(pips_list):+.1f}")
        print(f"Average Pips: {sum(pips_list)/len(pips_list):+.1f}")
        print(f"Best Trade: {max(pips_list):+.1f} pips")
        print(f"Worst Trade: {min(pips_list):+.1f} pips")
        print()

    if profit_list:
        print(f"Total P&L: {sum(profit_list):+.2f}")
        print(f"Average P&L: {sum(profit_list)/len(profit_list):+.2f}")
        print()

    # Average R:R
    rr_actual = [float(t["rr_actual"]) for t in closed
                 if t.get("rr_actual") and t["rr_actual"]]
    if rr_actual:
        print(f"Average Actual R:R: 1:{sum(rr_actual)/len(rr_actual):.1f}")
        print()

    # Duration
    durations = [float(t["duration_hours"]) for t in closed
                 if t.get("duration_hours") and t["duration_hours"]]
    if durations:
        print(f"Average Duration: {sum(durations)/len(durations):.1f}h")
        print()

    # Performance by Module 07 bias alignment
    with_bias = []
    against_bias = []
    neutral_bias = []
    for t in closed:
        bias = t.get("module07_bias", "")
        direction = t.get("direction", "")
        pips = float(t["pips"]) if t["pips"] else 0
        if ("BULLISH" in bias and direction == "LONG") or \
           ("BEARISH" in bias and direction == "SHORT"):
            with_bias.append(pips)
        elif "NEUTRAL" in bias:
            neutral_bias.append(pips)
        elif bias:
            against_bias.append(pips)

    if with_bias or against_bias:
        print("─" * 40)
        print("Performance by Bias Alignment:")
        if with_bias:
            wr = len([p for p in with_bias if p > 0]) / len(with_bias) * 100
            print(f"  WITH bias:    {len(with_bias)} trades, "
                  f"{wr:.0f}% WR, avg {sum(with_bias)/len(with_bias):+.1f} pips")
        if against_bias:
            wr = len([p for p in against_bias if p > 0]) / len(against_bias) * 100
            print(f"  AGAINST bias: {len(against_bias)} trades, "
                  f"{wr:.0f}% WR, avg {sum(against_bias)/len(against_bias):+.1f} pips")
        if neutral_bias:
            wr = len([p for p in neutral_bias if p > 0]) / len(neutral_bias) * 100
            print(f"  NEUTRAL bias: {len(neutral_bias)} trades, "
                  f"{wr:.0f}% WR, avg {sum(neutral_bias)/len(neutral_bias):+.1f} pips")
        print()

    # Performance by Module 08 setup type
    by_scenario = {}
    for t in closed:
        scenario = t.get("module08_scenario", "") or "No SMC data"
        pips = float(t["pips"]) if t["pips"] else 0
        by_scenario.setdefault(scenario, []).append(pips)

    if len(by_scenario) > 1 or (len(by_scenario) == 1 and "No SMC data" not in by_scenario):
        print("─" * 40)
        print("Performance by Setup Type:")
        for scenario, pips_list in sorted(by_scenario.items()):
            count = len(pips_list)
            wr = len([p for p in pips_list if p > 0]) / count * 100
            avg = sum(pips_list) / count
            print(f"  {scenario}: {count} trades, {wr:.0f}% WR, avg {avg:+.1f} pips")
        print()

    # Performance by day of week
    by_dow = {}
    DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for t in closed:
        open_dt = _parse_datetime(t.get("date_open", ""))
        if open_dt:
            dow = DOW_NAMES[open_dt.weekday()]
            pips = float(t["pips"]) if t["pips"] else 0
            by_dow.setdefault(dow, []).append(pips)

    if by_dow:
        print("─" * 40)
        print("Performance by Day:")
        for dow in DOW_NAMES:
            if dow in by_dow:
                pips_list = by_dow[dow]
                avg = sum(pips_list) / len(pips_list)
                print(f"  {dow}: {len(pips_list)} trades, avg {avg:+.1f} pips")
        print()

    # Current streak
    if pips_list:
        sorted_trades = sorted(closed, key=lambda t: t.get("date_close", ""))
        streak = 0
        streak_type = None
        for t in reversed(sorted_trades):
            p = float(t["pips"]) if t["pips"] else 0
            current = "W" if p > 0 else "L"
            if streak_type is None:
                streak_type = current
            if current == streak_type:
                streak += 1
            else:
                break
        if streak_type:
            print(f"Current Streak: {streak}{streak_type}")

    # Self-assessment grades
    graded = [t for t in closed if t.get("grade")]
    if graded:
        print()
        print("─" * 40)
        print("Self-Assessment Grades:")
        grade_counts = {}
        for t in graded:
            g = t["grade"]
            grade_counts[g] = grade_counts.get(g, 0) + 1
        for g in sorted(grade_counts.keys()):
            print(f"  {g}: {grade_counts[g]}")

    print()
    print("=" * 60)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="USD/JPY Trade Journal")
    sub = parser.add_subparsers(dest="command")

    # import
    sub.add_parser("import", help="Import trades from Exness CSV")

    # sync
    sub.add_parser("sync", help="Sync trades from MT5 terminal")

    # open
    p_open = sub.add_parser("open", help="Manual journal entry")
    p_open.add_argument("direction", help="LONG or SHORT")
    p_open.add_argument("entry", type=float, help="Entry price")
    p_open.add_argument("stop", type=float, help="Stop loss price")
    p_open.add_argument("target", type=float, help="Target price")
    p_open.add_argument("--lots", default="0.01", help="Position size (default: 0.01)")
    p_open.add_argument("--note", default="", help="Trade rationale")

    # close
    p_close = sub.add_parser("close", help="Close an open journal entry")
    p_close.add_argument("ticket", help="Ticket number to close")
    p_close.add_argument("exit_price", type=float, help="Exit price")
    p_close.add_argument("--grade", default="", help="Self-assessment grade (A/B/C/D)")
    p_close.add_argument("--reason", default="", help="Close reason")

    # review
    sub.add_parser("review", help="Performance summary")

    args = parser.parse_args()

    if args.command == "import":
        import_trades()
    elif args.command == "sync":
        sync_trades()
    elif args.command == "open":
        manual_open(args.direction, args.entry, args.stop, args.target,
                    lots=args.lots, rationale=args.note)
    elif args.command == "close":
        manual_close(args.ticket, args.exit_price, grade=args.grade, reason=args.reason)
    elif args.command == "review":
        review_performance()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
