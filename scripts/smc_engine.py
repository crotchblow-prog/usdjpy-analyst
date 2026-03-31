#!/usr/bin/env python3
"""
smc_engine.py — Smart Money Concepts analysis engine for USD/JPY.

Core functions for swing detection, market structure, order blocks, FVGs,
premium/discount zones, liquidity mapping, and Tokyo fix extraction.

Includes USD/JPY-specific adaptations:
- Intervention OB tagging near key levels (145, 150, 155, 160, 161.95)
- Tokyo fix price extraction (9:55 JST)
- Round number liquidity levels
- Session boundary detection (Tokyo/London/NY)

Usage:
    from scripts.smc_engine import SMCEngine
    engine = SMCEngine(config)
    results = engine.analyze(df_4h, df_1h, df_15m, df_5m)
"""

import datetime as dt
from typing import Optional

import numpy as np
import pandas as pd


# ── USD/JPY-specific constants ────────────────────────────────────────────

INTERVENTION_LEVELS = [145.0, 150.0, 155.0, 160.0, 161.95]
INTERVENTION_TOLERANCE = 0.50  # within 50 pips of level
ROUND_NUMBERS = [x for x in range(140, 170)]  # 140.00 through 169.00
TOKYO_FIX_HOUR = 9
TOKYO_FIX_MINUTE = 55

# Session boundaries in JST (UTC+9)
SESSIONS = {
    "tokyo": (9, 15),    # 09:00-15:00 JST
    "london": (17, 2),   # 17:00-02:00 JST (next day)
    "new_york": (22, 7), # 22:00-07:00 JST (next day)
}


# ── Swing Points ──────────────────────────────────────────────────────────

def find_swing_points(df: pd.DataFrame, lookback: int = 5):
    """
    Find swing highs and swing lows.
    A swing high has the highest high in a window of 2*lookback+1 bars.
    A swing low has the lowest low in the same window.
    """
    swing_highs = []
    swing_lows = []
    highs = df["High"].values
    lows = df["Low"].values

    for i in range(lookback, len(df) - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows[i - lookback : i + lookback + 1]

        # Accept swing if it's the max/min in window.
        # When ties exist, accept only the first occurrence (leftmost) to avoid
        # duplicate swings in compressed price ranges.
        if highs[i] == window_h.max():
            first_max_offset = int(np.argmax(window_h))
            if first_max_offset == lookback:  # i is the first occurrence
                swing_highs.append({
                    "index": i,
                    "datetime": df.index[i],
                    "price": float(highs[i]),
                })

        if lows[i] == window_l.min():
            first_min_offset = int(np.argmin(window_l))
            if first_min_offset == lookback:  # i is the first occurrence
                swing_lows.append({
                    "index": i,
                    "datetime": df.index[i],
                    "price": float(lows[i]),
                })

    return swing_highs, swing_lows


# ── Market Structure ──────────────────────────────────────────────────────

def classify_structure(swing_highs: list, swing_lows: list):
    """
    Classify market structure as BULLISH, BEARISH, or TRANSITIONAL.
    Returns structure type plus BOS/ChoCH events.
    """
    events = []

    # Label each swing high as HH or LH
    for i in range(1, len(swing_highs)):
        prev = swing_highs[i - 1]
        curr = swing_highs[i]
        label = "HH" if curr["price"] > prev["price"] else "LH"
        swing_highs[i]["label"] = label

    # Label each swing low as HL or LL
    for i in range(1, len(swing_lows)):
        prev = swing_lows[i - 1]
        curr = swing_lows[i]
        label = "HL" if curr["price"] > prev["price"] else "LL"
        swing_lows[i]["label"] = label

    if len(swing_highs) > 0 and "label" not in swing_highs[0]:
        swing_highs[0]["label"] = "SH"
    if len(swing_lows) > 0 and "label" not in swing_lows[0]:
        swing_lows[0]["label"] = "SL"

    # Merge and sort all swings by index for event detection
    all_swings = []
    for sh in swing_highs:
        all_swings.append({**sh, "swing_type": "high"})
    for sl in swing_lows:
        all_swings.append({**sl, "swing_type": "low"})
    all_swings.sort(key=lambda x: x["index"])

    # Detect BOS and ChoCH events
    # Track the current structure state
    recent_highs = [s for s in swing_highs if "label" in s and s["label"] in ("HH", "LH")]
    recent_lows = [s for s in swing_lows if "label" in s and s["label"] in ("HL", "LL")]

    # Determine structure from the last few swings
    last_high_labels = [s["label"] for s in swing_highs[-3:] if "label" in s]
    last_low_labels = [s["label"] for s in swing_lows[-3:] if "label" in s]

    bullish_highs = last_high_labels.count("HH")
    bearish_highs = last_high_labels.count("LH")
    bullish_lows = last_low_labels.count("HL")
    bearish_lows = last_low_labels.count("LL")

    if bullish_highs >= bearish_highs and bullish_lows >= bearish_lows:
        structure = "BULLISH"
    elif bearish_highs >= bullish_highs and bearish_lows >= bullish_lows:
        structure = "BEARISH"
    else:
        structure = "TRANSITIONAL"

    # Detect BOS/ChoCH from swing sequences
    _detect_bos_choch(swing_highs, swing_lows, all_swings, events)

    return structure, events, swing_highs, swing_lows


def _detect_bos_choch(swing_highs, swing_lows, all_swings, events):
    """Detect Break of Structure and Change of Character events.

    Scans ALL consecutive swing pairs chronologically to build a complete
    event history, not just the most recent pair.
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return

    # Track running structure state as we scan forward
    structure_state = "UNKNOWN"  # BULLISH, BEARISH, or UNKNOWN

    # Scan swing highs: each consecutive pair can produce a BOS or ChoCH
    for i in range(1, len(swing_highs)):
        prev = swing_highs[i - 1]
        curr = swing_highs[i]
        label = curr.get("label")
        if label is None:
            continue

        if label == "HH":
            if structure_state == "BEARISH":
                # HH after bearish structure = ChoCH (reversal)
                events.append({
                    "type": "ChoCH",
                    "direction": "bullish",
                    "price": curr["price"],
                    "datetime": curr["datetime"],
                    "index": curr["index"],
                    "broken_level": prev["price"],
                })
            else:
                # HH continuing bullish = BOS
                events.append({
                    "type": "BOS",
                    "direction": "bullish",
                    "price": curr["price"],
                    "datetime": curr["datetime"],
                    "index": curr["index"],
                    "broken_level": prev["price"],
                })
            structure_state = "BULLISH"
        elif label == "LH":
            structure_state = "BEARISH"

    # Scan swing lows similarly
    structure_state = "UNKNOWN"
    for i in range(1, len(swing_lows)):
        prev = swing_lows[i - 1]
        curr = swing_lows[i]
        label = curr.get("label")
        if label is None:
            continue

        if label == "LL":
            if structure_state == "BULLISH":
                # LL after bullish structure = ChoCH (reversal)
                events.append({
                    "type": "ChoCH",
                    "direction": "bearish",
                    "price": curr["price"],
                    "datetime": curr["datetime"],
                    "index": curr["index"],
                    "broken_level": prev["price"],
                })
            else:
                # LL continuing bearish = BOS
                events.append({
                    "type": "BOS",
                    "direction": "bearish",
                    "price": curr["price"],
                    "datetime": curr["datetime"],
                    "index": curr["index"],
                    "broken_level": prev["price"],
                })
            structure_state = "BEARISH"
        elif label == "HL":
            structure_state = "BULLISH"

    # Sort events chronologically by index
    events.sort(key=lambda e: e["index"])


# ── Order Blocks ──────────────────────────────────────────────────────────

def find_order_blocks(df: pd.DataFrame, bos_events: list, timeframe: str = ""):
    """
    For each BOS/ChoCH event, find the last opposing candle before the move.
    Tags intervention OBs when near key USD/JPY levels.
    Stores the BOS index so mitigation only considers candles after the BOS.
    """
    order_blocks = []
    for event in bos_events:
        direction = event["direction"]
        bos_index = event["index"]

        for i in range(bos_index - 1, max(bos_index - 20, 0), -1):
            candle = df.iloc[i]
            c_open = float(candle["Open"])
            c_close = float(candle["Close"])
            c_high = float(candle["High"])
            c_low = float(candle["Low"])

            is_bearish_candle = c_close < c_open
            is_bullish_candle = c_close > c_open

            if direction == "bullish" and is_bearish_candle:
                ob = _make_order_block(
                    "bullish_ob", df, i, c_open, c_close, c_high, c_low, timeframe, event
                )
                ob["bos_index"] = bos_index
                order_blocks.append(ob)
                break
            elif direction == "bearish" and is_bullish_candle:
                ob = _make_order_block(
                    "bearish_ob", df, i, c_open, c_close, c_high, c_low, timeframe, event
                )
                ob["bos_index"] = bos_index
                order_blocks.append(ob)
                break

    return order_blocks


def _make_order_block(ob_type, df, i, c_open, c_close, c_high, c_low, timeframe, event):
    """Create an order block dict with intervention tagging."""
    zone_top = max(c_open, c_close)
    zone_bottom = min(c_open, c_close)
    midpoint = (zone_top + zone_bottom) / 2

    # Check if near intervention level
    is_intervention = False
    nearest_intervention = None
    for level in INTERVENTION_LEVELS:
        if abs(midpoint - level) <= INTERVENTION_TOLERANCE:
            is_intervention = True
            nearest_intervention = level
            break

    # Enforce minimum zone width: 3 pips for 5M/15M, 5 pips for 1H/4H
    min_width_pips = 5 if timeframe in ("4H", "4h", "1H", "1h") else 3
    min_width = min_width_pips * 0.01  # JPY pair: 1 pip = 0.01
    zone_width = zone_top - zone_bottom
    if zone_width < min_width:
        expand = (min_width - zone_width) / 2
        zone_top += expand
        zone_bottom -= expand

    return {
        "type": ob_type,
        "datetime": df.index[i],
        "index": i,
        "zone_top": zone_top,
        "zone_bottom": zone_bottom,
        "full_range_top": c_high,
        "full_range_bottom": c_low,
        "timeframe": timeframe,
        "event_type": event["type"],
        "mitigated": False,
        "is_intervention": is_intervention,
        "intervention_level": nearest_intervention,
    }


def check_ob_mitigation(order_blocks: list, df: pd.DataFrame):
    """Mark order blocks as mitigated if price has *closed* through them.

    A wick through the zone is not mitigation — smart money defends zones
    with wicks. Only a candle close beyond the zone body confirms that
    institutional interest has been fully absorbed.

    Mitigation is checked only for candles AFTER the BOS/ChoCH event that
    created the OB — price action between the OB candle and the BOS is part
    of the impulse, not a retest.
    """
    for ob in order_blocks:
        if ob["mitigated"]:
            continue
        # Use BOS index as the start point for mitigation checks
        bos_idx = ob.get("bos_index")
        if bos_idx is not None and bos_idx < len(df):
            bos_time = df.index[bos_idx]
            mask = df.index > bos_time
        else:
            mask = df.index > ob["datetime"]
        if not mask.any():
            continue
        subsequent = df.loc[mask]
        if ob["type"] == "bullish_ob":
            # Mitigated only if a candle CLOSED below the zone bottom
            if subsequent["Close"].min() < ob["zone_bottom"]:
                ob["mitigated"] = True
        else:
            # Mitigated only if a candle CLOSED above the zone top
            if subsequent["Close"].max() > ob["zone_top"]:
                ob["mitigated"] = True


# ── Fair Value Gaps ───────────────────────────────────────────────────────

def find_fvg(df: pd.DataFrame, timeframe: str = ""):
    """Detect 3-candle fair value gaps (imbalances)."""
    fvgs = []
    highs = df["High"].values
    lows = df["Low"].values

    for i in range(2, len(df)):
        c1_high = float(highs[i - 2])
        c1_low = float(lows[i - 2])
        c3_high = float(highs[i])
        c3_low = float(lows[i])

        # Bullish FVG: gap up
        if c3_low > c1_high:
            fvgs.append({
                "type": "bullish_fvg",
                "datetime": df.index[i - 1],
                "index": i - 1,
                "zone_top": c3_low,
                "zone_bottom": c1_high,
                "timeframe": timeframe,
                "filled": False,
            })

        # Bearish FVG: gap down
        if c3_high < c1_low:
            fvgs.append({
                "type": "bearish_fvg",
                "datetime": df.index[i - 1],
                "index": i - 1,
                "zone_top": c1_low,
                "zone_bottom": c3_high,
                "timeframe": timeframe,
                "filled": False,
            })

    return fvgs


def check_fvg_fill(fvgs: list, df: pd.DataFrame):
    """Mark FVGs as filled if price has *closed* through the midpoint.

    A wick into the gap or a touch of the edge is not a fill — price
    must close past the 50% mark of the imbalance for the gap to be
    considered absorbed.  Partially filled FVGs remain valid entry zones.
    """
    for fvg in fvgs:
        if fvg["filled"]:
            continue
        fvg_time = fvg["datetime"]
        mask = df.index > fvg_time
        if not mask.any():
            continue
        subsequent = df.loc[mask]
        midpoint = (fvg["zone_top"] + fvg["zone_bottom"]) / 2
        if fvg["type"] == "bullish_fvg":
            # Filled only if a candle closed below the gap midpoint
            if subsequent["Close"].min() <= midpoint:
                fvg["filled"] = True
        else:
            # Filled only if a candle closed above the gap midpoint
            if subsequent["Close"].max() >= midpoint:
                fvg["filled"] = True


# ── Premium / Discount ────────────────────────────────────────────────────

def premium_discount(swing_high: float, swing_low: float, current_price: float):
    """
    Classify current price within the swing range.
    Returns (zone_name, description, details_dict).
    """
    if swing_high == swing_low:
        return "EQUILIBRIUM", "no range", {}

    midpoint = (swing_high + swing_low) / 2
    range_size = swing_high - swing_low
    pct = (current_price - swing_low) / range_size * 100

    # Fib levels for OTE
    fib_618 = swing_low + range_size * 0.618
    fib_786 = swing_low + range_size * 0.786
    ote_zone = (fib_618, fib_786)

    details = {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "midpoint": midpoint,
        "range_pips": range_size * 100,  # JPY pair: 1 pip = 0.01
        "fib_382": swing_low + range_size * 0.382,
        "fib_500": midpoint,
        "fib_618": fib_618,
        "fib_786": fib_786,
        "ote_top": fib_786,
        "ote_bottom": fib_618,
        "pct_in_range": pct,
    }

    if pct >= 78.6:
        return "DEEP PREMIUM", "strong short zone", details
    elif pct >= 50:
        return "PREMIUM", "short zone", details
    elif pct >= 21.4:
        return "DISCOUNT", "long zone", details
    else:
        return "DEEP DISCOUNT", "strong long zone", details


def is_in_ote(swing_high: float, swing_low: float, price: float) -> bool:
    """Check if price is in the Optimal Trade Entry zone (61.8-79%)."""
    range_size = swing_high - swing_low
    if range_size == 0:
        return False
    fib_618 = swing_low + range_size * 0.618
    fib_786 = swing_low + range_size * 0.786
    return fib_618 <= price <= fib_786


# ── Liquidity Map ─────────────────────────────────────────────────────────

def find_equal_levels(swing_points: list, tolerance_pips: float = 10):
    """Find clusters of swing points at similar levels (EQH/EQL)."""
    tolerance = tolerance_pips * 0.01  # JPY pair
    clusters = []
    used = set()

    for i, sp1 in enumerate(swing_points):
        if i in used:
            continue
        cluster_points = [sp1]
        for j, sp2 in enumerate(swing_points[i + 1 :], start=i + 1):
            if j in used:
                continue
            if abs(sp1["price"] - sp2["price"]) <= tolerance:
                cluster_points.append(sp2)
                used.add(j)
        if len(cluster_points) >= 2:
            used.add(i)
            avg_price = np.mean([p["price"] for p in cluster_points])
            clusters.append({
                "level": float(avg_price),
                "touches": len(cluster_points),
                "points": cluster_points,
            })

    return clusters


def build_liquidity_map(
    df_daily: pd.DataFrame,
    swing_highs: list,
    swing_lows: list,
    df_5m: Optional[pd.DataFrame] = None,
):
    """
    Build comprehensive liquidity map with USD/JPY-specific levels.
    Returns sorted list of levels with type and significance.
    """
    levels = []

    # Equal Highs / Equal Lows
    eqh_clusters = find_equal_levels(swing_highs)
    for c in eqh_clusters:
        levels.append({
            "price": c["level"],
            "type": "EQH",
            "significance": f"Buy stops — {c['touches']} touches",
            "liquidity": "buy_stops",
        })

    eql_clusters = find_equal_levels(swing_lows)
    for c in eql_clusters:
        levels.append({
            "price": c["level"],
            "type": "EQL",
            "significance": f"Sell stops — {c['touches']} touches",
            "liquidity": "sell_stops",
        })

    # Previous day high/low
    if len(df_daily) >= 2:
        prev_day = df_daily.iloc[-2]
        levels.append({
            "price": float(prev_day["High"]),
            "type": "PDH",
            "significance": "Previous day high",
            "liquidity": "buy_stops",
        })
        levels.append({
            "price": float(prev_day["Low"]),
            "type": "PDL",
            "significance": "Previous day low",
            "liquidity": "sell_stops",
        })

    # Previous week high/low (last 5 trading days)
    if len(df_daily) >= 6:
        pw_slice = df_daily.iloc[-6:-1]
        levels.append({
            "price": float(pw_slice["High"].max()),
            "type": "PWH",
            "significance": "Previous week high",
            "liquidity": "buy_stops",
        })
        levels.append({
            "price": float(pw_slice["Low"].min()),
            "type": "PWL",
            "significance": "Previous week low",
            "liquidity": "sell_stops",
        })

    # Intervention levels
    if len(df_daily) > 0:
        current_price = float(df_daily["Close"].iloc[-1])
        for lvl in INTERVENTION_LEVELS:
            if abs(current_price - lvl) <= 3.0:  # within 300 pips
                levels.append({
                    "price": lvl,
                    "type": "INTERVENTION",
                    "significance": f"BOJ intervention level ({lvl:.2f})",
                    "liquidity": "intervention_defense",
                })

    # Round numbers near current price
    if len(df_daily) > 0:
        current_price = float(df_daily["Close"].iloc[-1])
        for rn in ROUND_NUMBERS:
            if abs(current_price - rn) <= 2.0:
                levels.append({
                    "price": float(rn),
                    "type": "ROUND",
                    "significance": f"Round number {rn:.0f}.00",
                    "liquidity": "psychological",
                })

    # Tokyo fix level
    if df_5m is not None:
        fix_price = get_tokyo_fix_price(df_5m)
        if fix_price is not None:
            levels.append({
                "price": fix_price,
                "type": "TOKYO_FIX",
                "significance": "Today's Tokyo fix (9:55 JST)",
                "liquidity": "fix_flow",
            })

    # Sort by price descending
    levels.sort(key=lambda x: x["price"], reverse=True)
    return levels


# ── Tokyo Fix ─────────────────────────────────────────────────────────────

def get_tokyo_fix_price(df_5m: pd.DataFrame) -> Optional[float]:
    """Extract the 9:55 JST fixing price from 5M data."""
    if df_5m is None or len(df_5m) == 0:
        return None

    idx = df_5m.index
    # Ensure timezone-aware in JST
    if idx.tz is None:
        try:
            idx = idx.tz_localize("UTC").tz_convert("Asia/Tokyo")
        except Exception:
            idx = idx.tz_localize("Asia/Tokyo")
    elif str(idx.tz) != "Asia/Tokyo":
        idx = idx.tz_convert("Asia/Tokyo")

    # Find bars at 9:55 JST
    fix_bars = df_5m.loc[
        (idx.hour == TOKYO_FIX_HOUR) & (idx.minute == TOKYO_FIX_MINUTE)
    ]

    if len(fix_bars) == 0:
        # Try 9:50 as fallback (if 5M candle covers 9:50-9:55)
        fix_bars = df_5m.loc[
            (idx.hour == TOKYO_FIX_HOUR) & (idx.minute == 50)
        ]

    if len(fix_bars) > 0:
        return float(fix_bars["Close"].iloc[-1])
    return None


def get_session_boundaries(df: pd.DataFrame, session: str = "tokyo"):
    """Get session open/close times from the dataframe."""
    if session not in SESSIONS:
        return []

    start_hour, end_hour = SESSIONS[session]
    idx = df.index
    if idx.tz is None:
        try:
            idx = idx.tz_localize("UTC").tz_convert("Asia/Tokyo")
        except Exception:
            idx = idx.tz_localize("Asia/Tokyo")
    elif str(idx.tz) != "Asia/Tokyo":
        idx = idx.tz_convert("Asia/Tokyo")

    boundaries = []
    dates = set(idx.date)
    for d in sorted(dates):
        open_time = None
        close_time = None
        for ts in idx:
            if ts.date() == d and ts.hour == start_hour and ts.minute == 0:
                open_time = ts
            if ts.date() == d and ts.hour == end_hour and ts.minute == 0:
                close_time = ts
        if open_time is not None:
            boundaries.append({"date": d, "open": open_time, "close": close_time})

    return boundaries


# ── Scenario Classification ───────────────────────────────────────────────

def classify_scenario(
    structure_4h: str,
    entry_zone: Optional[dict],
    liquidity_map: list,
    current_price: float,
    bias: str,
    df_5m: Optional[pd.DataFrame] = None,
):
    """
    Classify the setup into one of four USD/JPY-specific scenarios:
    A: Intervention Bounce — price near intervention level + bearish structure
    B: Trend Retracement — price pulling back to OB/FVG in trending structure
    C: Liquidity Sweep — price sweeps EQH/EQL then reverses
    D: Tokyo Fix Fade — fade the pre-fix flow after 9:55 JST
    """
    # Check for Scenario A: Intervention Bounce
    intervention_levels = [l for l in liquidity_map if l["type"] == "INTERVENTION"]
    near_intervention = any(
        abs(current_price - l["price"]) <= 1.0 for l in intervention_levels
    )

    if near_intervention and structure_4h in ("BEARISH", "TRANSITIONAL"):
        return {
            "scenario": "A",
            "name": "Intervention Bounce",
            "description": (
                "Price near BOJ intervention level with bearish/transitional structure. "
                "Watch for MOF verbal escalation or actual intervention."
            ),
            "bias_alignment": bias == "SHORT",
        }

    # Check for Scenario D: Tokyo Fix Fade
    if df_5m is not None:
        fix_price = get_tokyo_fix_price(df_5m)
        if fix_price is not None:
            # Check if we're in the post-fix window (roughly)
            now_jst = _get_now_jst()
            if now_jst is not None and 10 <= now_jst.hour <= 12:
                fix_move = current_price - fix_price
                if abs(fix_move) >= 0.15:  # 15+ pip move into the fix
                    return {
                        "scenario": "D",
                        "name": "Tokyo Fix Fade",
                        "description": (
                            f"Post-fix fade opportunity. Fix at {fix_price:.2f}, "
                            f"current {current_price:.2f} ({fix_move:+.2f}). "
                            "Fix flows often reverse in the 10:00-12:00 window."
                        ),
                        "bias_alignment": True,
                        "fix_price": fix_price,
                        "fix_move": fix_move,
                    }

    # Check for Scenario C: Liquidity Sweep
    eqh_levels = [l for l in liquidity_map if l["type"] == "EQH"]
    eql_levels = [l for l in liquidity_map if l["type"] == "EQL"]

    for eqh in eqh_levels:
        if current_price > eqh["price"] and (current_price - eqh["price"]) <= 0.30:
            return {
                "scenario": "C",
                "name": "Liquidity Sweep",
                "description": (
                    f"Price swept above EQH at {eqh['price']:.2f} — buy stops taken. "
                    "Watch for reversal to trap longs."
                ),
                "bias_alignment": bias == "SHORT",
                "swept_level": eqh["price"],
            }
    for eql in eql_levels:
        if current_price < eql["price"] and (eql["price"] - current_price) <= 0.30:
            return {
                "scenario": "C",
                "name": "Liquidity Sweep",
                "description": (
                    f"Price swept below EQL at {eql['price']:.2f} — sell stops taken. "
                    "Watch for reversal to trap shorts."
                ),
                "bias_alignment": bias == "LONG",
                "swept_level": eql["price"],
            }

    # Default: Scenario B: Trend Retracement
    if entry_zone is not None:
        return {
            "scenario": "B",
            "name": "Trend Retracement",
            "description": (
                f"Price retracing to {entry_zone.get('zone_type', 'zone')} "
                f"at {entry_zone.get('zone_bottom', 0):.2f}-{entry_zone.get('zone_top', 0):.2f} "
                "in trending structure."
            ),
            "bias_alignment": True,
        }

    return {
        "scenario": "B",
        "name": "Trend Retracement",
        "description": "Standard retracement setup — waiting for price to reach zone.",
        "bias_alignment": True,
    }


# ── Confluence Scoring ────────────────────────────────────────────────────

def compute_confluence_score(
    entry_zone: Optional[dict],
    fvg_overlap: bool,
    in_ote: bool,
    liquidity_swept: bool,
    mtf_aligned: bool,
    bias_confidence: str,
    scenario: dict,
    near_intervention: bool = False,
    near_tokyo_fix: bool = False,
    near_round_number: bool = False,
    event_within_4h: bool = False,
    spread_widening: bool = False,
):
    """
    Score entry confluence (0-6 base + USD/JPY bonuses/penalties).

    Base scoring:
      +1 Order block at entry zone
      +1 FVG overlaps with order block
      +1 Entry in OTE zone (61.8-79%)
      +1 Liquidity swept before reversal
      +1 Multi-timeframe alignment (4H+1H+15M agree)
      +1 Module 07 bias is HIGH confidence

    USD/JPY bonuses:
      +1 Near intervention level (Scenario A)
      +1 Tokyo fix confluence (Scenario D)
      +0.5 Round number alignment

    Penalties:
      -1 Event risk within 4 hours
      -0.5 Spread widening (low liquidity)
    """
    score = 0.0
    details = []

    # Base scoring
    if entry_zone is not None:
        score += 1
        details.append("+1 Order block at entry zone")

    if fvg_overlap:
        score += 1
        details.append("+1 FVG overlaps with OB")

    if in_ote:
        score += 1
        details.append("+1 Entry in OTE zone (61.8-79%)")

    if liquidity_swept:
        score += 1
        details.append("+1 Liquidity swept before reversal")

    if mtf_aligned:
        score += 1
        details.append("+1 Multi-timeframe alignment")

    if bias_confidence == "HIGH":
        score += 1
        details.append("+1 High-confidence bias")
    elif bias_confidence == "MEDIUM":
        score += 0.5
        details.append("+0.5 Medium-confidence bias")

    # USD/JPY bonuses
    if near_intervention and scenario.get("scenario") == "A":
        score += 1
        details.append("+1 Intervention level confluence")

    if near_tokyo_fix and scenario.get("scenario") == "D":
        score += 1
        details.append("+1 Tokyo fix confluence")

    if near_round_number:
        score += 0.5
        details.append("+0.5 Round number alignment")

    # Penalties
    if event_within_4h:
        score -= 1
        details.append("-1 Event risk within 4 hours")

    if spread_widening:
        score -= 0.5
        details.append("-0.5 Spread widening / low liquidity")

    # Clamp
    score = max(0, score)

    # Grade
    if score >= 5:
        grade = "A+"
    elif score >= 3:
        grade = "B"
    elif score >= 1:
        grade = "C"
    else:
        grade = "NO SETUP"

    return {
        "score": score,
        "max_score": 8.5,  # theoretical max with all bonuses
        "grade": grade,
        "details": details,
    }


# ── Entry Zone Identification ─────────────────────────────────────────────

def find_best_entry_zone(
    order_blocks: list,
    fvgs: list,
    bias: str,
    zone_name: str,
    current_price: float,
):
    """
    Find the best entry zone from available OBs and FVGs.
    For LONG: look for bullish OBs/FVGs below current price in discount.
    For SHORT: look for bearish OBs/FVGs above current price in premium.
    """
    candidates = []

    # Filter order blocks by direction and mitigation
    for ob in order_blocks:
        if ob["mitigated"]:
            continue
        if bias == "LONG" and ob["type"] == "bullish_ob" and ob["zone_top"] < current_price:
            dist = current_price - ob["zone_top"]
            candidates.append({
                "zone_type": "Order Block",
                "zone_top": ob["zone_top"],
                "zone_bottom": ob["zone_bottom"],
                "full_range_top": ob["full_range_top"],
                "full_range_bottom": ob["full_range_bottom"],
                "timeframe": ob.get("timeframe", ""),
                "distance_pips": dist * 100,
                "is_intervention": ob.get("is_intervention", False),
                "source": ob,
                "priority": 1,  # OBs have highest priority
            })
        elif bias == "SHORT" and ob["type"] == "bearish_ob" and ob["zone_bottom"] > current_price:
            dist = ob["zone_bottom"] - current_price
            candidates.append({
                "zone_type": "Order Block",
                "zone_top": ob["zone_top"],
                "zone_bottom": ob["zone_bottom"],
                "full_range_top": ob["full_range_top"],
                "full_range_bottom": ob["full_range_bottom"],
                "timeframe": ob.get("timeframe", ""),
                "distance_pips": dist * 100,
                "is_intervention": ob.get("is_intervention", False),
                "source": ob,
                "priority": 1,
            })

    # Filter FVGs
    for fvg in fvgs:
        if fvg["filled"]:
            continue
        if bias == "LONG" and fvg["type"] == "bullish_fvg" and fvg["zone_top"] < current_price:
            dist = current_price - fvg["zone_top"]
            candidates.append({
                "zone_type": "Fair Value Gap",
                "zone_top": fvg["zone_top"],
                "zone_bottom": fvg["zone_bottom"],
                "full_range_top": fvg["zone_top"],
                "full_range_bottom": fvg["zone_bottom"],
                "timeframe": fvg.get("timeframe", ""),
                "distance_pips": dist * 100,
                "is_intervention": False,
                "source": fvg,
                "priority": 2,
            })
        elif bias == "SHORT" and fvg["type"] == "bearish_fvg" and fvg["zone_bottom"] > current_price:
            dist = fvg["zone_bottom"] - current_price
            candidates.append({
                "zone_type": "Fair Value Gap",
                "zone_top": fvg["zone_top"],
                "zone_bottom": fvg["zone_bottom"],
                "full_range_top": fvg["zone_top"],
                "full_range_bottom": fvg["zone_bottom"],
                "timeframe": fvg.get("timeframe", ""),
                "distance_pips": dist * 100,
                "is_intervention": False,
                "source": fvg,
                "priority": 2,
            })

    if not candidates:
        # Also check zones where price is currently inside
        for ob in order_blocks:
            if ob["mitigated"]:
                continue
            if bias == "LONG" and ob["type"] == "bullish_ob":
                if ob["zone_bottom"] <= current_price <= ob["zone_top"]:
                    candidates.append({
                        "zone_type": "Order Block (price inside)",
                        "zone_top": ob["zone_top"],
                        "zone_bottom": ob["zone_bottom"],
                        "full_range_top": ob["full_range_top"],
                        "full_range_bottom": ob["full_range_bottom"],
                        "timeframe": ob.get("timeframe", ""),
                        "distance_pips": 0,
                        "is_intervention": ob.get("is_intervention", False),
                        "source": ob,
                        "priority": 0,
                    })
            elif bias == "SHORT" and ob["type"] == "bearish_ob":
                if ob["zone_bottom"] <= current_price <= ob["zone_top"]:
                    candidates.append({
                        "zone_type": "Order Block (price inside)",
                        "zone_top": ob["zone_top"],
                        "zone_bottom": ob["zone_bottom"],
                        "full_range_top": ob["full_range_top"],
                        "full_range_bottom": ob["full_range_bottom"],
                        "timeframe": ob.get("timeframe", ""),
                        "distance_pips": 0,
                        "is_intervention": ob.get("is_intervention", False),
                        "source": ob,
                        "priority": 0,
                    })

    if not candidates:
        return None

    # Sort: price-inside first (priority 0), then OBs (1) before FVGs (2), then nearest
    candidates.sort(key=lambda c: (c["priority"], c["distance_pips"]))
    return candidates[0]


# ── Risk Management ───────────────────────────────────────────────────────

def compute_entry_plan(
    bias: str,
    entry_zone: dict,
    swing_highs_4h: list,
    swing_lows_4h: list,
    liquidity_map: list,
    pd_details: dict,
    buffer_pips: float = 10,
):
    """
    Compute entry, stop loss, and targets.
    Returns entry plan dict or None if R:R < 1:2.
    """
    buffer = buffer_pips * 0.01  # JPY pair

    if bias == "LONG":
        entry = entry_zone["zone_top"]  # enter at top of zone on retest
        stop = entry_zone["full_range_bottom"] - buffer
        risk = entry - stop

        # Find targets from liquidity map and swing points
        targets = []
        for level in liquidity_map:
            if level["price"] > entry:
                targets.append(level)
        # Add swing highs above entry
        for sh in swing_highs_4h:
            if sh["price"] > entry:
                targets.append({
                    "price": sh["price"],
                    "type": "4H Swing High",
                    "significance": f"4H swing high at {sh['price']:.2f}",
                })
        targets.sort(key=lambda t: t["price"])

    elif bias == "SHORT":
        entry = entry_zone["zone_bottom"]  # enter at bottom of zone on retest
        stop = entry_zone["full_range_top"] + buffer
        risk = stop - entry

        targets = []
        for level in liquidity_map:
            if level["price"] < entry:
                targets.append(level)
        for sl in swing_lows_4h:
            if sl["price"] < entry:
                targets.append({
                    "price": sl["price"],
                    "type": "4H Swing Low",
                    "significance": f"4H swing low at {sl['price']:.2f}",
                })
        targets.sort(key=lambda t: t["price"], reverse=True)
    else:
        return None

    if risk <= 0:
        return None

    # Select T1: first target that meets minimum R:R of 2.0
    # Select T2: next target beyond T1, must be >5 pips away from T1
    min_rr = 2.0
    dedup_pips = 0.05  # 5 pips for JPY pair
    t1 = None
    t2 = None
    for t in targets:
        reward = abs(t["price"] - entry)
        rr = reward / risk if risk > 0 else 0
        if rr >= min_rr:
            if t1 is None:
                t1 = t
            elif t2 is None:
                # Skip if within 5 pips of T1 — merge labels instead
                if abs(t["price"] - t1["price"]) <= dedup_pips:
                    t1_type_str = t1.get("type", "")
                    t_type_str = t.get("type", "")
                    if t_type_str and t_type_str not in t1_type_str:
                        t1["type"] = f"{t1_type_str} / {t_type_str}"
                    continue
                t2 = t
                break

    if t1 is None:
        # Fallback: use swing high/low as target
        if bias == "LONG" and pd_details.get("swing_high"):
            t1 = {"price": pd_details["swing_high"], "type": "Swing High", "significance": "Range high"}
        elif bias == "SHORT" and pd_details.get("swing_low"):
            t1 = {"price": pd_details["swing_low"], "type": "Swing Low", "significance": "Range low"}

    if t1 is None:
        return None

    t1_reward = abs(t1["price"] - entry)
    rr1 = t1_reward / risk if risk > 0 else 0
    t2_reward = abs(t2["price"] - entry) if t2 else None
    rr2 = t2_reward / risk if t2_reward and risk > 0 else None

    # Final R:R check (fallback targets may not meet minimum)
    if rr1 < min_rr:
        return None

    return {
        "entry": entry,
        "stop": stop,
        "risk_pips": risk * 100,
        "t1_price": t1["price"],
        "t1_type": t1.get("type", ""),
        "t1_rr": rr1,
        "t2_price": t2["price"] if t2 else None,
        "t2_type": t2.get("type", "") if t2 else None,
        "t2_rr": rr2,
        "direction": bias,
    }


# ── Confirmation Checks ──────────────────────────────────────────────────

def check_15m_confirmation(df_15m: pd.DataFrame, entry_zone: dict, bias: str):
    """
    Check if 15M timeframe shows confirmation at the entry zone.
    Looks for ChoCH, engulfing, or rejection wicks.
    """
    if df_15m is None or len(df_15m) < 10:
        return {"confirmed": False, "status": "Insufficient 15M data"}

    zone_top = entry_zone["zone_top"]
    zone_bottom = entry_zone["zone_bottom"]

    # Check if price has reached the zone
    recent = df_15m.tail(20)
    in_zone = recent[
        (recent["Low"] <= zone_top) & (recent["High"] >= zone_bottom)
    ]

    if len(in_zone) == 0:
        dist = abs(float(df_15m["Close"].iloc[-1]) - (zone_top + zone_bottom) / 2)
        return {
            "confirmed": False,
            "status": f"Not yet at zone ({dist * 100:.0f} pips away)",
        }

    # Check for structure shift (ChoCH) at zone
    sh_15m, sl_15m = find_swing_points(recent, lookback=3)
    if len(sh_15m) >= 2 and len(sl_15m) >= 2:
        structure, events, _, _ = classify_structure(sh_15m, sl_15m)
        choch_events = [e for e in events if e["type"] == "ChoCH"]

        if bias == "LONG" and any(e["direction"] == "bullish" for e in choch_events):
            return {"confirmed": True, "status": "15M bullish ChoCH confirmed"}
        if bias == "SHORT" and any(e["direction"] == "bearish" for e in choch_events):
            return {"confirmed": True, "status": "15M bearish ChoCH confirmed"}

    # Check for engulfing at zone
    for i in range(len(in_zone) - 1, max(len(in_zone) - 5, 0), -1):
        if i < 1:
            break
        curr = in_zone.iloc[i] if i < len(in_zone) else None
        prev_idx = in_zone.index[i - 1] if i >= 1 else None
        if curr is None or prev_idx is None:
            continue
        prev = in_zone.loc[prev_idx]

        if bias == "LONG":
            # Bullish engulfing
            if (curr["Close"] > curr["Open"] and prev["Close"] < prev["Open"]
                    and curr["Close"] > prev["Open"] and curr["Open"] < prev["Close"]):
                return {"confirmed": True, "status": "15M bullish engulfing at zone"}
        elif bias == "SHORT":
            # Bearish engulfing
            if (curr["Close"] < curr["Open"] and prev["Close"] > prev["Open"]
                    and curr["Close"] < prev["Open"] and curr["Open"] > prev["Close"]):
                return {"confirmed": True, "status": "15M bearish engulfing at zone"}

    # Check for rejection wick
    last_bar = in_zone.iloc[-1]
    body_size = abs(float(last_bar["Close"]) - float(last_bar["Open"]))
    if bias == "LONG":
        lower_wick = float(min(last_bar["Open"], last_bar["Close"])) - float(last_bar["Low"])
        if lower_wick > body_size * 2:
            return {"confirmed": True, "status": "15M rejection wick (long lower shadow)"}
    elif bias == "SHORT":
        upper_wick = float(last_bar["High"]) - float(max(last_bar["Open"], last_bar["Close"]))
        if upper_wick > body_size * 2:
            return {"confirmed": True, "status": "15M rejection wick (long upper shadow)"}

    return {"confirmed": False, "status": "Awaiting confirmation at zone"}


# ── Helpers ───────────────────────────────────────────────────────────────

def _get_now_jst():
    """Get current time in JST."""
    try:
        import pytz
        return dt.datetime.now(pytz.timezone("Asia/Tokyo"))
    except ImportError:
        # Fallback: assume system is JST (Okinawa)
        return dt.datetime.now()


def resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1H data to 4H candles."""
    if df_1h is None or len(df_1h) == 0:
        return pd.DataFrame()
    return df_1h.resample("4h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()


def pips_distance(price1: float, price2: float) -> float:
    """Calculate distance in pips for JPY pair."""
    return abs(price1 - price2) * 100
