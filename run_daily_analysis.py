#!/usr/bin/env python3
"""
USD/JPY Daily Analysis — 2026-03-29
Modules: 01 (Macro), 03 (Technicals), 05 (Cross-Asset), 07 (Checklist)
"""

import json
import os
import ssl
import sys
import math
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, date
from pathlib import Path

# SSL context that skips cert verification (needed on some macOS setups)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# ── Mode ───────────────────────────────────────────────────────────────────
CHECK_MODE = "--check" in sys.argv  # cache-only: no API calls, fail if no data

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_RAW   = BASE_DIR / "data" / "raw"
OUTPUT_DIR = BASE_DIR / "output" / "daily"
TODAY      = date.today()
TODAY_STR  = TODAY.strftime("%Y-%m-%d")
START_DATE = (TODAY - timedelta(days=730)).strftime("%Y-%m-%d")   # 2yr for SMA200

FRED_KEY  = "f13c6f60354d4c8dca6170754a7535f2"
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# In check mode, don't create dirs or fetch — just validate cache exists
if CHECK_MODE:
    if not DATA_RAW.exists() or not any(DATA_RAW.glob(f"*_{TODAY_STR}.json")):
        print("ERROR: No cached data found for today. Run /usdjpy-daily first.", file=sys.stderr)
        sys.exit(1)
    print("▶ Check mode — using cached data only (no API calls)")
else:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Track data freshness — maps source label to cache file mod time
data_freshness = {}  # {"FRED DGS10": "2026-03-30 09:15", ...}
stale_warnings = []  # warnings if cache is from a prior day

# ── Helpers ──────────────────────────────────────────────────────────────────
def _track_freshness(label, cache_path):
    """Record cache file mod time and warn if stale."""
    if cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        data_freshness[label] = mtime.strftime("%Y-%m-%d %H:%M")
        if mtime.date() < TODAY:
            stale_warnings.append(f"{label}: cached from {mtime.strftime('%Y-%m-%d')}")

def fred_fetch(series_id, limit=700):
    cache = DATA_RAW / f"FRED_{series_id}_{TODAY_STR}.json"
    if cache.exists():
        _track_freshness(f"FRED {series_id}", cache)
        with open(cache) as f:
            return json.load(f)
    if CHECK_MODE:
        print(f"  WARN: No cached FRED {series_id} data for today", file=sys.stderr)
        return None
    url = (f"{FRED_BASE}?series_id={series_id}&api_key={FRED_KEY}"
           f"&file_type=json&sort_order=desc&limit={limit}"
           f"&observation_start={START_DATE}")
    try:
        with urllib.request.urlopen(url, timeout=15, context=SSL_CTX) as r:
            data = json.loads(r.read())
        if "error_code" in data:
            print(f"  WARN: FRED {series_id} error: {data.get('error_message')}", file=sys.stderr)
            return None
        with open(cache, "w") as f:
            json.dump(data, f)
        _track_freshness(f"FRED {series_id}", cache)
        return data
    except Exception as e:
        print(f"  WARN: FRED {series_id} fetch failed: {e}", file=sys.stderr)
        return None

def obs_to_series(data):
    """Return sorted list of (date_str, float) ignoring '.' values."""
    if not data:
        return []
    rows = []
    for o in data.get("observations", []):
        if o["value"] != ".":
            rows.append((o["date"], float(o["value"])))
    return sorted(rows, key=lambda x: x[0])

def latest(series):
    return series[-1] if series else None

def value_at(series, target_date_str):
    """Return last value on or before target_date."""
    result = None
    for d, v in series:
        if d <= target_date_str:
            result = v
    return result

def change(series, days):
    if not series:
        return None
    end_d   = TODAY_STR
    start_d = (TODAY - timedelta(days=days)).strftime("%Y-%m-%d")
    v_end   = value_at(series, end_d)
    v_start = value_at(series, start_d)
    if v_end is None or v_start is None:
        return None
    return round(v_end - v_start, 4)

# ── SMA / RSI / MACD helpers ─────────────────────────────────────────────────
def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n

def ema(values, n):
    if len(values) == 0:
        return None
    k = 2 / (n + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

def ema_series(values, n):
    if len(values) < n:
        return []
    k = 2 / (n + 1)
    result = [sum(values[:n]) / n]
    for v in values[n:]:
        result.append(v * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 2)

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast_s = ema_series(closes, fast)
    ema_slow_s = ema_series(closes, slow)
    min_len = min(len(ema_fast_s), len(ema_slow_s))
    macd_line = [ema_fast_s[-(min_len - i)] - ema_slow_s[-(min_len - i)] for i in range(min_len)]
    signal_line_s = ema_series(macd_line, signal)
    macd_val   = macd_line[-1]
    signal_val = signal_line_s[-1] if signal_line_s else None
    hist       = round(macd_val - signal_val, 4) if signal_val else None
    return round(macd_val, 4), round(signal_val, 4) if signal_val else None, hist

def calc_ichimoku(highs, lows, closes, tenkan=9, kijun=26, senkou_b=52):
    def mid(h_slice, l_slice):
        return (max(h_slice) + min(l_slice)) / 2
    n = len(closes)
    if n < senkou_b:
        return None
    t = mid(highs[-tenkan:], lows[-tenkan:])
    k = mid(highs[-kijun:],  lows[-kijun:])
    sa = (t + k) / 2
    sb = mid(highs[-senkou_b:], lows[-senkou_b:])
    price = closes[-1]
    cloud_top    = max(sa, sb)
    cloud_bottom = min(sa, sb)
    if price > cloud_top:
        pos = "ABOVE"
    elif price < cloud_bottom:
        pos = "BELOW"
    else:
        pos = "INSIDE"
    cloud_bullish = sa > sb
    return {
        "tenkan": round(t, 4),
        "kijun":  round(k, 4),
        "senkou_a": round(sa, 4),
        "senkou_b": round(sb, 4),
        "cloud_color": "GREEN (bullish)" if cloud_bullish else "RED (bearish)",
        "price_vs_cloud": pos,
    }

def yahoo_fetch(ticker, days=730):
    cache = DATA_RAW / f"YF_{ticker.replace('^','').replace('=','_')}_{TODAY_STR}.json"
    if cache.exists():
        _track_freshness(f"YF {ticker}", cache)
        with open(cache) as f:
            return json.load(f)
    if CHECK_MODE:
        print(f"  WARN: No cached Yahoo {ticker} data for today", file=sys.stderr)
        return None
    end_ts   = int(datetime(TODAY.year, TODAY.month, TODAY.day).timestamp())
    start_ts = int((datetime(TODAY.year, TODAY.month, TODAY.day) - timedelta(days=days)).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
           f"?interval=1d&period1={start_ts}&period2={end_ts}")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
            data = json.loads(r.read())
        with open(cache, "w") as f:
            json.dump(data, f)
        _track_freshness(f"YF {ticker}", cache)
        return data
    except Exception as e:
        print(f"  WARN: Yahoo {ticker} fetch failed: {e}", file=sys.stderr)
        return None

def yf_to_series(data):
    if not data:
        return []
    try:
        result = data["chart"]["result"][0]
        ts     = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        rows   = []
        for t, c in zip(ts, closes):
            if c is not None:
                from datetime import timezone
                d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append((d, c))
        return sorted(rows)
    except Exception:
        return []

def yf_to_ohlcv(data):
    """Return sorted list of (date, high, low, close) from Yahoo Finance response."""
    if not data:
        return []
    try:
        from datetime import timezone
        result = data["chart"]["result"][0]
        ts     = result["timestamp"]
        q      = result["indicators"]["quote"][0]
        highs, lows, closes = q["high"], q["low"], q["close"]
        rows = []
        for t, h, l, c in zip(ts, highs, lows, closes):
            if h is not None and l is not None and c is not None:
                d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append((d, h, l, c))
        return sorted(rows)
    except Exception:
        return []

def mof_jgb_fetch():
    """Fetch daily Japan 10Y JGB yields from MOF. Returns [(date_str, float), ...]."""
    cache = DATA_RAW / f"MOF_JGB10Y_{TODAY_STR}.json"
    if cache.exists():
        _track_freshness("MOF JGB", cache)
        with open(cache) as f:
            return json.load(f)
    if CHECK_MODE:
        print("  WARN: No cached MOF JGB data for today", file=sys.stderr)
        return []

    def parse_csv(text):
        rows = {}
        for line in text.splitlines():
            parts = line.strip().split(",")
            if len(parts) < 11 or not parts[0] or not parts[0][0].isdigit():
                continue
            try:
                raw_date = parts[0].strip()  # e.g. 2026/3/26
                y, m, d = raw_date.split("/")
                date_str = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                val_str  = parts[10].strip()  # 10Y is column index 10
                if val_str and val_str != "-":
                    rows[date_str] = float(val_str)
            except (ValueError, IndexError):
                continue
        return rows

    combined = {}
    urls = [
        "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
        "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
                text = r.read().decode("utf-8", errors="ignore")
            combined.update(parse_csv(text))
        except Exception as e:
            print(f"  WARN: MOF JGB fetch failed for {url}: {e}", file=sys.stderr)

    if not combined:
        return None  # caller will fall back to FRED

    series = sorted(combined.items())
    with open(cache, "w") as f:
        json.dump(series, f)
    _track_freshness("MOF JGB", cache)
    return series

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 01 — Macro Regime
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Module 01 — Macro Regime")

us10y_data  = fred_fetch("DGS10")
usdjpy_yf_raw = yahoo_fetch("USDJPY=X")

us10y_s  = obs_to_series(us10y_data)
usdjpy_s = yf_to_series(usdjpy_yf_raw)

# JP 10Y: try MOF daily first, fall back to FRED monthly
jp10y_mof = mof_jgb_fetch()
if jp10y_mof:
    jp10y_s    = jp10y_mof  # already [(date, float), ...] sorted
    jp10y_src  = "MOF (daily)"
else:
    print("  WARN: MOF JGB fetch failed, falling back to FRED IRLTLT01JPM156N", file=sys.stderr)
    jp10y_data = fred_fetch("IRLTLT01JPM156N")
    jp10y_s    = obs_to_series(jp10y_data)
    jp10y_src  = "FRED (monthly)"

# Latest values
us10y_now  = value_at(us10y_s,  TODAY_STR)
jp10y_now  = value_at(jp10y_s,  TODAY_STR)
usdjpy_now = value_at(usdjpy_s, TODAY_STR)

# Build spread series — align JP and US 10Y on common dates
# With daily MOF data no forward-fill needed; with monthly FRED we still forward-fill
jp_by_date = dict(jp10y_s)
us_by_date = dict(us10y_s)
all_dates  = sorted(set(d for d, _ in us10y_s))
spread_s   = []
last_jp    = None
for d in all_dates:
    if d in jp_by_date:
        last_jp = jp_by_date[d]
    if last_jp is not None and d in us_by_date:
        spread_s.append((d, round(us_by_date[d] - last_jp, 4)))

spread_now = value_at(spread_s, TODAY_STR)

# Changes
us10y_1w  = change(us10y_s,  7)
us10y_1m  = change(us10y_s,  30)
us10y_3m  = change(us10y_s,  90)
jp10y_1w  = change(jp10y_s,  7)
jp10y_1m  = change(jp10y_s,  30)
jp10y_3m  = change(jp10y_s,  90)
spread_1w = change(spread_s, 7)
spread_1m = change(spread_s, 30)
spread_3m = change(spread_s, 90)
usdjpy_1w = change(usdjpy_s, 7)
usdjpy_1m = change(usdjpy_s, 30)
usdjpy_3m = change(usdjpy_s, 90)

THRESH = 0.15
spread_dir = "STABLE"
if spread_1m is not None:
    if spread_1m > THRESH:
        spread_dir = "WIDENING"
    elif spread_1m < -THRESH:
        spread_dir = "NARROWING"

usdjpy_dir = "RISING" if (usdjpy_1m or 0) > 0 else "FALLING"

div_check = "NEUTRAL"
if spread_dir == "WIDENING":
    div_check = "CONFIRMED" if usdjpy_dir == "RISING" else "DIVERGENCE"
elif spread_dir == "NARROWING":
    div_check = "CONFIRMED" if usdjpy_dir == "FALLING" else "DIVERGENCE"

macro_bias = "NEUTRAL"
if spread_dir == "WIDENING"  and div_check == "CONFIRMED": macro_bias = "BULLISH"
if spread_dir == "NARROWING" and div_check == "CONFIRMED": macro_bias = "BEARISH"
if div_check == "DIVERGENCE": macro_bias = "CAUTION"

macro_conf = "LOW"
if spread_1m is not None:
    if abs(spread_1m) > 2 * THRESH and div_check == "CONFIRMED":
        macro_conf = "HIGH"
    elif abs(spread_1m) > THRESH and div_check == "CONFIRMED":
        macro_conf = "MEDIUM"

print(f"  US10Y={us10y_now}%, JP10Y={jp10y_now}%, Spread={spread_now}%, USD/JPY={usdjpy_now}")
print(f"  Spread direction={spread_dir}, Divergence={div_check}, Bias={macro_bias}/{macro_conf}")

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 03 — Technicals
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Module 03 — Technicals")

# Use Yahoo Finance OHLCV for proper high/low (Ichimoku, key levels)
ohlcv = yf_to_ohlcv(usdjpy_yf_raw)
if ohlcv:
    closes = [c for _, h, l, c in ohlcv]
    highs  = [h for _, h, l, c in ohlcv]
    lows   = [l for _, h, l, c in ohlcv]
    ohlcv_src = "Yahoo Finance (OHLCV)"
else:
    closes = [v for _, v in usdjpy_s]
    highs  = closes
    lows   = closes
    ohlcv_src = "Yahoo Finance close-only fallback"

price  = closes[-1] if closes else None

# Guard: skip technicals if no price data available
if not closes:
    print("  WARN: No USD/JPY price data — skipping technicals", file=sys.stderr)
    sma50 = sma200 = rsi = macd_val = macd_signal = macd_hist = None
    ichi = None
    sma_cross = "NONE"
    rsi_sig = macd_sig = ichi_sig = "NEUTRAL"
    support = resistance = None
    tech_bias = "NEUTRAL"
    tech_conf = "LOW"
    tech_sigs = []
    price_vs_sma50 = price_vs_sma200 = "N/A"
    ohlcv_src = "N/A — no data"
else:
    sma50  = sma(closes, 50)
    sma200 = sma(closes, 200)

    sma_cross = "NONE"
    if sma50 and sma200:
        sma_cross = "GOLDEN" if sma50 > sma200 else "DEATH"

    rsi = calc_rsi(closes)
    rsi_sig = "NEUTRAL"
    if rsi:
        if rsi > 70: rsi_sig = "OVERBOUGHT"
        elif rsi < 30: rsi_sig = "OVERSOLD"

    macd_val, macd_signal, macd_hist = calc_macd(closes)
    macd_sig = "NEUTRAL"
    if macd_val is not None and macd_signal is not None:
        macd_sig = "BULLISH" if macd_val > macd_signal else "BEARISH"

    ichi = calc_ichimoku(highs, lows, closes)
    ichi_sig = "NEUTRAL"
    if ichi:
        if ichi["price_vs_cloud"] == "ABOVE": ichi_sig = "BULLISH"
        elif ichi["price_vs_cloud"] == "BELOW": ichi_sig = "BEARISH"

    # Key levels: use real highs/lows over last 30 bars
    recent_highs = highs[-30:] if len(highs) >= 30 else highs
    recent_lows  = lows[-30:]  if len(lows)  >= 30 else lows
    support    = round(min(recent_lows),  2)
    resistance = round(max(recent_highs), 2)

    # Count bullish signals
    tech_sigs = []
    if sma_cross == "GOLDEN": tech_sigs.append("BULLISH")
    elif sma_cross == "DEATH": tech_sigs.append("BEARISH")
    if rsi_sig == "OVERBOUGHT": tech_sigs.append("BEARISH")
    elif rsi_sig == "OVERSOLD": tech_sigs.append("BULLISH")
    if macd_sig != "NEUTRAL": tech_sigs.append(macd_sig)
    if ichi_sig != "NEUTRAL": tech_sigs.append(ichi_sig)

    b_count = tech_sigs.count("BULLISH")
    bear_count = tech_sigs.count("BEARISH")
    tech_bias = "NEUTRAL"
    if b_count > bear_count: tech_bias = "BULLISH"
    elif bear_count > b_count: tech_bias = "BEARISH"
    tech_conf = {4: "HIGH", 3: "HIGH", 2: "MEDIUM"}.get(max(b_count, bear_count), "LOW")

    # Price above/below SMAs
    price_vs_sma50  = "Above" if (sma50  and price > sma50)  else "Below"
    price_vs_sma200 = "Above" if (sma200 and price > sma200) else "Below"

print(f"  Price={price}, SMA50={round(sma50,2) if sma50 else 'N/A'}, SMA200={round(sma200,2) if sma200 else 'N/A'}")
print(f"  RSI={rsi}, MACD={macd_sig}, Ichimoku={ichi_sig}, Bias={tech_bias}/{tech_conf}")

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 05 — Cross-Asset Correlations
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Module 05 — Cross-Asset Correlations")

spx_data  = fred_fetch("SP500")
vix_data  = fred_fetch("VIXCLS")
oil_data  = fred_fetch("DCOILWTICO")

nikkei_raw  = yahoo_fetch("^N225")
gold_yf_raw = yahoo_fetch("GC=F")

nikkei_s = yf_to_series(nikkei_raw)
gold_s   = yf_to_series(gold_yf_raw)   # Gold from Yahoo Finance (GC=F)
spx_s    = obs_to_series(spx_data)
vix_s    = obs_to_series(vix_data)
oil_s    = obs_to_series(oil_data)

def align_returns(base_s, asset_s, window=30):
    """Compute rolling 30d correlation of daily returns."""
    base_d = dict(base_s)
    asset_d = dict(asset_s)
    dates = sorted(set(base_d) & set(asset_d))
    if len(dates) < window + 2:
        return None
    # Use last window+1 dates for returns
    tail_dates = dates[-(window + 1):]
    base_vals  = [base_d[d]  for d in tail_dates]
    asset_vals = [asset_d[d] for d in tail_dates]
    # Daily returns
    br = [(base_vals[i]  - base_vals[i-1])  / base_vals[i-1]  for i in range(1, len(base_vals))]
    ar = [(asset_vals[i] - asset_vals[i-1]) / asset_vals[i-1] for i in range(1, len(asset_vals))]
    n  = len(br)
    if n < 5:
        return None
    mean_b = sum(br) / n
    mean_a = sum(ar) / n
    cov  = sum((b - mean_b) * (a - mean_a) for b, a in zip(br, ar)) / n
    std_b = math.sqrt(sum((b - mean_b)**2 for b in br) / n)
    std_a = math.sqrt(sum((a - mean_a)**2 for a in ar) / n)
    if std_b == 0 or std_a == 0:
        return None
    return round(cov / (std_b * std_a), 3)

corr_spx    = align_returns(usdjpy_s, spx_s)
corr_nikkei = align_returns(usdjpy_s, nikkei_s)
corr_gold   = align_returns(usdjpy_s, gold_s)
corr_vix    = align_returns(usdjpy_s, vix_s)
corr_oil    = align_returns(usdjpy_s, oil_s)

def corr_status(corr, expected_positive):
    if corr is None:
        return "N/A"
    if expected_positive:
        return "Normal" if corr > 0 else "BREAKDOWN"
    else:
        return "Normal" if corr < 0 else "BREAKDOWN"

# Regime
risk_regime = "TRANSITIONAL"
if corr_spx is not None and corr_vix is not None:
    if corr_spx > 0.5 and corr_vix < -0.3:
        risk_regime = "RISK-ON"
    elif corr_spx < -0.3 and corr_vix > 0.3:
        risk_regime = "RISK-OFF"
    elif corr_spx is not None and abs(corr_spx) < 0.2:
        risk_regime = "DECORRELATED"

cross_bias = "NEUTRAL"
cross_conf = "LOW"
if risk_regime == "RISK-ON":
    usd_dir = "RISING" if (usdjpy_1m or 0) > 0 else "FALLING"
    cross_bias = "BULLISH" if usd_dir == "RISING" else "CAUTION"
    cross_conf = "MEDIUM"
elif risk_regime == "RISK-OFF":
    usd_dir = "FALLING" if (usdjpy_1m or 0) < 0 else "RISING"
    cross_bias = "BEARISH" if usd_dir == "FALLING" else "CAUTION"
    cross_conf = "MEDIUM"

breakdown_alerts = []
if corr_status(corr_spx,  True)    == "BREAKDOWN": breakdown_alerts.append("SPX")
if corr_status(corr_nikkei, True)  == "BREAKDOWN": breakdown_alerts.append("Nikkei")
if corr_status(corr_gold,  False)  == "BREAKDOWN": breakdown_alerts.append("Gold")
if corr_status(corr_vix,   False)  == "BREAKDOWN": breakdown_alerts.append("VIX")
if corr_status(corr_oil,   True)   == "BREAKDOWN": breakdown_alerts.append("WTI")

print(f"  Regime={risk_regime}, Cross-Asset Bias={cross_bias}/{cross_conf}")
print(f"  SPX corr={corr_spx}, Nikkei={corr_nikkei}, Gold={corr_gold}, VIX={corr_vix}, Oil={corr_oil}")

# ═══════════════════════════════════════════════════════════════════════════════
# MODULE 07 — Pre-Trade Checklist
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Module 07 — Checklist")

# Intraday-weighted scoring: Technicals drive the signal, macro/cross-asset are context.
# Technicals: ±3 (HIGH=3, MED=2, LOW=1) — primary driver for intraday
# Macro/Cross-Asset: ±1 (HIGH=1, MED/LOW=1/0) — background context
def score_primary(bias, conf):
    """Score for primary signal (technicals) — heavier weight."""
    if bias == "BULLISH":
        return {"HIGH": 3, "MEDIUM": 2}.get(conf, 1)
    if bias == "BEARISH":
        return {"HIGH": -3, "MEDIUM": -2}.get(conf, -1)
    return 0

def score_context(bias, conf):
    """Score for context signals (macro, cross-asset) — lighter weight."""
    if bias == "BULLISH":
        return 1 if conf in ("HIGH", "MEDIUM") else 0
    if bias == "BEARISH":
        return -1 if conf in ("HIGH", "MEDIUM") else 0
    return 0

tech_score = score_primary(tech_bias, tech_conf)
macro_score = score_context(macro_bias, macro_conf)
cross_score = score_context(cross_bias, cross_conf)
weighted = tech_score + macro_score + cross_score

# Daily max is ±5 (tech ±3, macro ±1, cross ±1); weekly adds ±3 more
daily_max = 5
total_framework = 6

if   weighted >= 4:  overall = "STRONG BULLISH"
elif weighted >= 2:  overall = "MODERATE BULLISH"
elif weighted >= -1: overall = "NEUTRAL / NO EDGE"
elif weighted >= -3: overall = "MODERATE BEARISH"
else:                overall = "STRONG BEARISH"

# ── Conviction — based on daily modules only (no coverage cap penalty) ──
modules_available = sum(1 for b in [macro_bias, tech_bias, cross_bias] if b not in ("N/A",))

# Score-based conviction using daily max, not framework max
abs_score = abs(weighted)
if abs_score >= 4:
    conviction = "HIGH"
elif abs_score >= 2:
    conviction = "MEDIUM"
else:
    conviction = "LOW"

# Override: divergence always drops to LOW
if div_check == "DIVERGENCE":
    conviction = "LOW"

# Override: neutral bias is MEDIUM at best
if overall == "NEUTRAL / NO EDGE" and conviction == "HIGH":
    conviction = "MEDIUM"

# ── Module-coverage note (informational, no longer caps conviction) ──
conviction_cap_note = ""
if modules_available < 3:
    conviction_cap_note = (
        f"{modules_available}/{total_framework} modules active — "
        f"run /usdjpy-weekly for full scoring"
    )

# ── Structural conflict safeguard (Rule 4) ──
# If direction conflicts with price's position in the range, downgrade conviction.
structural_conflict_note = ""
if price and support and resistance and resistance > support:
    range_size = resistance - support
    pct_in_range = (price - support) / range_size * 100 if range_size > 0 else 50
    if overall in ("MODERATE BULLISH", "STRONG BULLISH") and pct_in_range >= 78.6:
        structural_conflict_note = (
            f"Price at {price:.2f} is in deep premium ({pct_in_range:.0f}% of range "
            f"{support}-{resistance}) while bias is bullish — structural conflict"
        )
        rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        new_level = {"HIGH": "MEDIUM", "MEDIUM": "LOW"}.get(conviction, conviction)
        if rank.get(new_level, 0) < rank.get(conviction, 0):
            conviction = new_level
    elif overall in ("MODERATE BEARISH", "STRONG BEARISH") and pct_in_range <= 21.4:
        structural_conflict_note = (
            f"Price at {price:.2f} is in deep discount ({pct_in_range:.0f}% of range "
            f"{support}-{resistance}) while bias is bearish — structural conflict"
        )
        rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        new_level = {"HIGH": "MEDIUM", "MEDIUM": "LOW"}.get(conviction, conviction)
        if rank.get(new_level, 0) < rank.get(conviction, 0):
            conviction = new_level

# Risk alerts (thresholds: ELEVATED >150, CRITICAL >160)
intervention_risk = "NO"
if price:
    if price > 160:
        intervention_risk = "CRITICAL"
    elif price > 150:
        if usdjpy_1m and usdjpy_1m > 5:
            intervention_risk = "CRITICAL"
        else:
            intervention_risk = "ELEVATED"

corr_breakdown_alert = "NO" if not breakdown_alerts else f"YES — {', '.join(breakdown_alerts)}"

# ═══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Generating charts...")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.dates import DateFormatter
    import numpy as np

    def parse_dates(series):
        return [datetime.strptime(d, "%Y-%m-%d") for d, _ in series]

    def vals(series):
        return [v for _, v in series]

    plt.style.use("seaborn-v0_8")
    CHART_DPI  = 150
    CHART_SIZE = (12, 6)

    # ── Chart 1: Macro Spread vs USD/JPY ─────────────────────────────────────
    fig, ax1 = plt.subplots(figsize=CHART_SIZE)
    ax2 = ax1.twinx()

    spread_dates = parse_dates(spread_s[-90:]) if len(spread_s) >= 90 else parse_dates(spread_s)
    spread_vals  = vals(spread_s[-90:])        if len(spread_s) >= 90 else vals(spread_s)
    usdjpy_dates = parse_dates(usdjpy_s[-90:]) if len(usdjpy_s) >= 90 else parse_dates(usdjpy_s)
    usdjpy_vals  = vals(usdjpy_s[-90:])        if len(usdjpy_s) >= 90 else vals(usdjpy_s)

    ax1.plot(spread_dates, spread_vals, color="#2196F3", linewidth=2, label="US-JP 10Y Spread")
    ax2.plot(usdjpy_dates, usdjpy_vals, color="#F44336", linewidth=2, label="USD/JPY")
    ax1.set_ylabel("Spread (pp)", color="#2196F3")
    ax2.set_ylabel("USD/JPY", color="#F44336")
    ax1.xaxis.set_major_formatter(DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()

    if div_check == "DIVERGENCE":
        ax1.axvspan(spread_dates[-30], spread_dates[-1], alpha=0.15, color="yellow", label="Divergence")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=10)
    plt.title(f"US-Japan 10Y Spread vs USD/JPY — {TODAY_STR}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    macro_chart = OUTPUT_DIR / f"macro_spread_{TODAY_STR}.png"
    plt.savefig(macro_chart, dpi=CHART_DPI)
    plt.close()
    print(f"  Saved {macro_chart}")

    # ── Chart 2: Technicals ──────────────────────────────────────────────────
    fig, (ax_price, ax_rsi) = plt.subplots(2, 1, figsize=(12, 8),
                                            gridspec_kw={"height_ratios": [3, 1]})
    all_ux_dates = parse_dates(usdjpy_s)
    all_ux_vals  = vals(usdjpy_s)
    tail = -180
    udates = all_ux_dates[tail:]
    uvals  = all_ux_vals[tail:]

    ax_price.plot(udates, uvals, color="#333", linewidth=1.5, label="USD/JPY")
    if sma50 and len(closes) >= 50:
        sma50_series = [sma(closes[:i+1], 50) for i in range(len(closes)) if i >= 49]
        sma50_dates  = all_ux_dates[49:]
        ax_price.plot(sma50_dates[tail+49:] if len(sma50_dates) > -tail else sma50_dates,
                      sma50_series[tail+49:] if len(sma50_series) > -tail else sma50_series,
                      color="#FF9800", linewidth=1.5, label="50 SMA", linestyle="--")
    if sma200 and len(closes) >= 200:
        sma200_series = [sma(closes[:i+1], 200) for i in range(len(closes)) if i >= 199]
        sma200_dates  = all_ux_dates[199:]
        ax_price.plot(sma200_dates, sma200_series, color="#9C27B0", linewidth=1.5,
                      label="200 SMA", linestyle="--")

    # Ichimoku cloud shading (simplified using Tenkan/Kijun/Cloud values)
    if ichi:
        ax_price.axhline(ichi["tenkan"],   color="#00BCD4", linewidth=1,   linestyle=":", alpha=0.8, label=f"Tenkan {ichi['tenkan']:.2f}")
        ax_price.axhline(ichi["kijun"],    color="#E91E63", linewidth=1,   linestyle=":", alpha=0.8, label=f"Kijun {ichi['kijun']:.2f}")
        cloud_c = "#a5d6a7" if ichi["senkou_a"] > ichi["senkou_b"] else "#ef9a9a"
        ax_price.axhspan(min(ichi["senkou_a"], ichi["senkou_b"]),
                         max(ichi["senkou_a"], ichi["senkou_b"]),
                         alpha=0.2, color=cloud_c, label="Ichimoku Cloud")

    if support is not None:
        ax_price.axhline(support,    color="#4CAF50", linewidth=1, linestyle="--", alpha=0.7, label=f"Support {support}")
    if resistance is not None:
        ax_price.axhline(resistance, color="#F44336", linewidth=1, linestyle="--", alpha=0.7, label=f"Resistance {resistance}")
    ax_price.set_ylabel("USD/JPY")
    ax_price.legend(loc="upper left", fontsize=10)
    ax_price.xaxis.set_major_formatter(DateFormatter("%b %d"))
    ax_price.xaxis.set_major_locator(mdates.MonthLocator())

    # RSI subplot
    rsi_values = []
    for i in range(14, len(closes)):
        rsi_values.append(calc_rsi(closes[:i+1]))
    rsi_dates = all_ux_dates[14:]
    ax_rsi.plot(rsi_dates[tail:], rsi_values[tail:], color="#673AB7", linewidth=1.5, label="RSI (14)")
    ax_rsi.legend(loc="upper left", fontsize=10)
    ax_rsi.axhline(70, color="#F44336", linewidth=1, linestyle="--", alpha=0.7)
    ax_rsi.axhline(30, color="#4CAF50", linewidth=1, linestyle="--", alpha=0.7)
    ax_rsi.axhline(50, color="#999",    linewidth=0.8, linestyle=":")
    ax_rsi.set_ylabel("RSI")
    ax_rsi.set_ylim(0, 100)
    ax_rsi.xaxis.set_major_formatter(DateFormatter("%b %d"))
    ax_rsi.xaxis.set_major_locator(mdates.MonthLocator())
    fig.autofmt_xdate()

    plt.suptitle(f"USD/JPY Technical Analysis — {TODAY_STR}", fontsize=14, fontweight="bold")
    plt.tight_layout()
    tech_chart = OUTPUT_DIR / f"technicals_{TODAY_STR}.png"
    plt.savefig(tech_chart, dpi=CHART_DPI)
    plt.close()
    print(f"  Saved {tech_chart}")

    # ── Chart 3: Cross-Asset Correlations ────────────────────────────────────
    assets  = ["S&P 500", "Nikkei 225", "Gold", "VIX", "WTI Oil"]
    corrs   = [corr_spx, corr_nikkei, corr_gold, corr_vix, corr_oil]
    colors  = ["#2196F3" if (c or 0) > 0 else "#F44336" for c in corrs]
    c_vals  = [c if c is not None else 0 for c in corrs]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(assets, c_vals, color=colors, edgecolor="white", height=0.6)
    ax.axvline(0, color="#333", linewidth=1)
    ax.axvline(0.3,  color="#4CAF50", linewidth=0.8, linestyle="--", alpha=0.6, label="+0.3 threshold")
    ax.axvline(-0.3, color="#F44336", linewidth=0.8, linestyle="--", alpha=0.6, label="-0.3 threshold")
    for bar, val in zip(bars, c_vals):
        ax.text(val + (0.02 if val >= 0 else -0.02), bar.get_y() + bar.get_height()/2,
                f"{val:.3f}", va="center", ha="left" if val >= 0 else "right", fontsize=10)
    ax.set_xlabel("30-Day Rolling Correlation with USD/JPY")
    ax.set_title(f"Cross-Asset Correlations — {TODAY_STR}\nRisk Regime: {risk_regime}", fontsize=13, fontweight="bold")
    ax.set_xlim(-1, 1)
    ax.legend(loc="lower right", fontsize=10)
    plt.tight_layout()
    corr_chart = OUTPUT_DIR / f"correlations_{TODAY_STR}.png"
    plt.savefig(corr_chart, dpi=CHART_DPI)
    plt.close()
    print(f"  Saved {corr_chart}")

    charts_generated = True

except Exception as e:
    print(f"  WARN: Chart generation failed: {e}", file=sys.stderr)
    import traceback; traceback.print_exc()
    macro_chart = corr_chart = tech_chart = None
    charts_generated = False

# ═══════════════════════════════════════════════════════════════════════════════
# REPORT ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════
print("▶ Writing report...")

def fmt(v, decimals=2):
    return f"{v:.{decimals}f}" if v is not None else "N/A"

def fmt_chg(v, decimals=2):
    if v is None: return "N/A"
    return f"+{v:.{decimals}f}" if v >= 0 else f"{v:.{decimals}f}"

# ── Load prior report for day-over-day comparison ────────────────────────────
import re, glob as glob_mod

prev_report_files = sorted(glob_mod.glob(str(OUTPUT_DIR / "????-??-??.md")))
prev_report_files = [f for f in prev_report_files if not f.endswith(f"{TODAY_STR}.md")]
prev = {}  # prior day's extracted values
if prev_report_files:
    prev_path = prev_report_files[-1]
    prev["date"] = Path(prev_path).stem
    prev_text = Path(prev_path).read_text()
    # Extract bias from header line: > **MODERATE BULLISH** | Conviction: **HIGH** | Score: **+2/+6**
    m = re.search(r'>\s*\*\*([^*]+)\*\*\s*\|\s*Conviction:\s*\*\*(\w+)\*\*\s*\|\s*Score:\s*\*\*([^*]+)\*\*', prev_text)
    if m:
        prev["bias"]       = m.group(1).strip()
        prev["conviction"] = m.group(2).strip()
        prev["score"]      = m.group(3).strip()
    # Extract USD/JPY value from At a Glance table: | USD/JPY | 159.70 |
    m = re.search(r'\|\s*USD/JPY\s*\|\s*([\d.]+)', prev_text)
    if m:
        prev["usdjpy"] = float(m.group(1))
    # Extract spread value
    m = re.search(r'\|\s*Spread\s*\|\s*([\d.]+)%', prev_text)
    if m:
        prev["spread"] = float(m.group(1))
    # Extract RSI
    m = re.search(r'\|\s*RSI \(14\)\s*\|\s*([\d.]+)', prev_text)
    if m:
        prev["rsi"] = float(m.group(1))
    # Extract US 10Y
    m = re.search(r'\|\s*US 10Y\s*\|\s*([\d.]+)%', prev_text)
    if m:
        prev["us10y"] = float(m.group(1))
    # Extract JP 10Y
    m = re.search(r'\|\s*JP 10Y\s*\|\s*([\d.]+)%', prev_text)
    if m:
        prev["jp10y"] = float(m.group(1))
    # Extract 1W changes for momentum comparison
    m = re.search(r'\|\s*USD/JPY\s*\|\s*[\d.]+\s*\|\s*([+-]?[\d.]+)', prev_text)
    if m:
        prev["usdjpy_1w"] = float(m.group(1))
    m = re.search(r'\|\s*Spread\s*\|\s*[\d.]+%\s*\|\s*([+-]?[\d.]+)', prev_text)
    if m:
        prev["spread_1w"] = float(m.group(1))

    # ── Module-level extractions for dynamic narratives ──
    # Module 01: spread direction, divergence check, macro bias
    m = re.search(r'\*\*Spread Direction:\*\*\s*(\w+)\s*\|\s*\*\*Divergence Check:\*\*\s*(\w+)', prev_text)
    if m:
        prev["spread_dir"] = m.group(1)
        prev["div_check"]  = m.group(2)
    m = re.search(r'## 01.*?\n\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)', prev_text, re.DOTALL)
    if m:
        prev["macro_bias"] = m.group(1)
        prev["macro_conf"] = m.group(2)

    # Module 03: technicals bias, SMA cross, MACD signal, Ichimoku position
    m = re.search(r'## 03.*?\n\*\*Bias:\s*(\w+)\*\*\s*\|\s*Confidence:\s*(\w+)', prev_text, re.DOTALL)
    if m:
        prev["tech_bias"] = m.group(1)
        prev["tech_conf"] = m.group(2)
    m = re.search(r'\|\s*SMA Cross\s*\|\s*(\w+)', prev_text)
    if m:
        prev["sma_cross"] = m.group(1)
    m = re.search(r'\|\s*MACD\s*\|[^|]+\|\s*(\w+)', prev_text)
    if m:
        prev["macd_sig"] = m.group(1)
    m = re.search(r'\|\s*Ichimoku Cloud\s*\|\s*(\w+)', prev_text)
    if m:
        prev["ichi_pos"] = m.group(1)

    # Module 05: regime, correlations
    m = re.search(r'Regime:\s*(\w+)', prev_text)
    if m:
        prev["risk_regime"] = m.group(1)
    m = re.search(r'\|\s*S&P 500\s*\|\s*([+-]?[\d.]+)', prev_text)
    if m:
        prev["corr_spx"] = float(m.group(1))
    m = re.search(r'\|\s*Nikkei 225\s*\|\s*([+-]?[\d.]+)', prev_text)
    if m:
        prev["corr_nikkei"] = float(m.group(1))

    print(f"  Prior report: {prev.get('date')} — {prev.get('bias')} / {prev.get('conviction')}")
else:
    print("  No prior report found for comparison")

# ── Build dynamic At a Glance summary ───────────────────────────────────────
def build_at_a_glance_summary():
    if not prev:
        return "First daily report — establishing baseline levels."

    significant = []  # notable changes
    momentum = []     # momentum shifts

    # USD/JPY change >0.5
    if prev.get("usdjpy") and usdjpy_now:
        px_d = usdjpy_now - prev["usdjpy"]
        if abs(px_d) >= 0.5:
            significant.append(f"USD/JPY {'rose' if px_d > 0 else 'fell'} {abs(px_d):.2f} to {fmt(usdjpy_now)}")
        # Momentum: compare 1W changes
        if prev.get("usdjpy_1w") and usdjpy_1w is not None:
            prev_1w = prev["usdjpy_1w"]
            if abs(usdjpy_1w - prev_1w) >= 0.3:
                if abs(usdjpy_1w) < abs(prev_1w):
                    momentum.append(f"1W USD/JPY momentum slowed from {prev_1w:+.2f} to {usdjpy_1w:+.2f}")
                else:
                    momentum.append(f"1W USD/JPY momentum accelerated from {prev_1w:+.2f} to {usdjpy_1w:+.2f}")

    # Yield changes >0.05
    if prev.get("us10y") and us10y_now:
        us_d = us10y_now - prev["us10y"]
        if abs(us_d) >= 0.05:
            significant.append(f"US 10Y {'up' if us_d > 0 else 'down'} {abs(us_d):.2f}pp to {fmt(us10y_now)}%")
    if prev.get("jp10y") and jp10y_now:
        jp_d = jp10y_now - prev["jp10y"]
        if abs(jp_d) >= 0.05:
            significant.append(f"JP 10Y {'up' if jp_d > 0 else 'down'} {abs(jp_d):.2f}pp to {fmt(jp10y_now)}%")

    # Spread change
    if prev.get("spread") and spread_now:
        sp_d = spread_now - prev["spread"]
        if abs(sp_d) >= 0.05:
            significant.append(f"spread {'widened' if sp_d > 0 else 'narrowed'} {abs(sp_d):.2f}pp")
        if prev.get("spread_1w") and spread_1w is not None:
            prev_sp1w = prev["spread_1w"]
            if abs(spread_1w - prev_sp1w) >= 0.03:
                if abs(spread_1w) < abs(prev_sp1w):
                    momentum.append(f"1W spread change slowed from {prev_sp1w:+.2f} to {spread_1w:+.2f}")
                else:
                    momentum.append(f"1W spread change accelerated from {prev_sp1w:+.2f} to {spread_1w:+.2f}")

    parts = significant + momentum
    if parts:
        return "; ".join(parts) + "."
    else:
        return f"No material changes since yesterday — watching {fmt(resistance)} resistance."

at_a_glance_summary = build_at_a_glance_summary()

# ── Build dynamic Bottom Line ────────────────────────────────────────────────
def build_bottom_line():
    lines = []

    # Lead with bias status
    bias_changed = prev.get("bias", overall) != overall
    if bias_changed:
        lines.append(f"Bias shifted from {prev.get('bias')} to {overall}.")
    elif prev:
        if prev.get("score") and f"{weighted:+d}" != prev["score"].split("/")[0]:
            lines.append(f"Bias holds at {overall} but score moved from {prev.get('score')} to {weighted:+d}/+6.")
        else:
            lines.append(f"Bias steady at {overall}.")
    else:
        lines.append(f"Initial bias: {overall}.")

    # Rate differential context
    rate_ctx = f"Rate differential {spread_dir.lower()} ({div_check})"
    if prev.get("spread") and spread_now:
        sp_d = spread_now - prev["spread"]
        if abs(sp_d) >= 0.01:
            rate_ctx += f", spread {'widened' if sp_d > 0 else 'narrowed'} {abs(sp_d):.2f}pp day-over-day"
    rate_ctx += "."
    lines.append(rate_ctx)

    # Technical context — highlight what changed
    tech_parts = []
    if prev.get("rsi") and rsi:
        rsi_d = rsi - prev["rsi"]
        if abs(rsi_d) >= 1.0:
            tech_parts.append(f"RSI {'rose' if rsi_d > 0 else 'fell'} to {fmt(rsi,1)}")
    if macd_sig != "NEUTRAL":
        tech_parts.append(f"MACD {macd_sig.lower()}")
    if ichi and ichi["price_vs_cloud"] == "ABOVE":
        tech_parts.append("price above Ichimoku cloud")
    if tech_parts:
        lines.append("Technicals: " + ", ".join(tech_parts) + ".")

    # Cross-asset
    cross_line = f"Cross-asset regime {risk_regime}"
    if breakdown_alerts:
        cross_line += f" with {', '.join(breakdown_alerts)} breakdown(s)"
    cross_line += " — "
    if risk_regime in ("RISK-ON",) and (usdjpy_1m or 0) > 0:
        cross_line += "confirms USD/JPY upside."
    elif risk_regime in ("RISK-OFF",) and (usdjpy_1m or 0) < 0:
        cross_line += "confirms USD/JPY downside."
    else:
        cross_line += "defer to rate differential and technicals."
    lines.append(cross_line)

    # Key levels
    lines.append(f"Watch {fmt(resistance)} resistance and {fmt(support)} support.")

    return " ".join(lines)

bottom_line_text = build_bottom_line()

# ── Stale data warning ──────────────────────────────────────────────────────
freshness_line = ""
if stale_warnings:
    freshness_line = "⚠ STALE DATA: " + "; ".join(stale_warnings)
    print(f"  WARNING: {freshness_line}")

# Build data freshness footer
freshness_stamps = " | ".join(f"{k}: {v}" for k, v in sorted(data_freshness.items()))
if not freshness_stamps:
    freshness_stamps = "N/A"

# ── Dynamic module narratives ────────────────────────────────────────────────
def build_macro_narrative():
    base = f"The US-Japan 10-year spread stands at {fmt(spread_now)}pp, {spread_dir.lower()} {fmt_chg(spread_1m)}pp over the past month."
    # Day-over-day color
    dod_parts = []
    if prev.get("spread") and spread_now:
        sp_d = spread_now - prev["spread"]
        if abs(sp_d) >= 0.01:
            dod_parts.append(f"spread {'widened' if sp_d > 0 else 'narrowed'} {abs(sp_d):.2f}pp day-over-day")
    if prev.get("spread_dir") and prev["spread_dir"] != spread_dir:
        dod_parts.append(f"direction shifted from {prev['spread_dir']} to {spread_dir}")
    if prev.get("div_check") and prev["div_check"] != div_check:
        dod_parts.append(f"divergence check moved from {prev['div_check']} to {div_check}")
    if prev.get("us10y") and us10y_now:
        us_d = us10y_now - prev["us10y"]
        if abs(us_d) >= 0.03:
            dod_parts.append(f"US 10Y {'up' if us_d > 0 else 'down'} {abs(us_d):.2f}pp")
    if prev.get("jp10y") and jp10y_now:
        jp_d = jp10y_now - prev["jp10y"]
        if abs(jp_d) >= 0.03:
            dod_parts.append(f"JP 10Y {'up' if jp_d > 0 else 'down'} {abs(jp_d):.2f}pp")

    if dod_parts:
        base += " Since yesterday: " + ", ".join(dod_parts) + "."
    else:
        # Confirm/diverge sentence
        if div_check == "CONFIRMED":
            base += " Spread direction and USD/JPY continue moving in concert."
        elif div_check == "DIVERGENCE":
            base += " Spread and USD/JPY are diverging — caution warranted."
        else:
            base += " Rate differentials remain stable with no dominant macro impulse."
    return base

def build_tech_narrative():
    parts = []
    # Lead with what changed vs yesterday
    if prev.get("macd_sig") and prev["macd_sig"] != macd_sig:
        parts.append(f"MACD flipped from {prev['macd_sig']} to {macd_sig}")
    if prev.get("sma_cross") and prev["sma_cross"] != sma_cross:
        parts.append(f"SMA cross changed from {prev['sma_cross']} to {sma_cross}")
    if prev.get("ichi_pos") and ichi and prev["ichi_pos"] != ichi["price_vs_cloud"]:
        parts.append(f"Ichimoku position shifted from {prev['ichi_pos']} to {ichi['price_vs_cloud']} cloud")
    if prev.get("rsi") and rsi:
        rsi_d = rsi - prev["rsi"]
        if abs(rsi_d) >= 1.0:
            parts.append(f"RSI {'rose' if rsi_d > 0 else 'fell'} {abs(rsi_d):.1f} to {fmt(rsi,1)}")

    if parts:
        return "; ".join(parts) + f". Price at {fmt(price)} with {sma_cross} cross and {ichi['price_vs_cloud'].lower() if ichi else 'N/A'} cloud."
    else:
        # No changes — describe current state with today's values
        return f"Technical setup unchanged: {sma_cross} cross, price {ichi['price_vs_cloud'].lower() if ichi else 'N/A'} cloud at {fmt(price)}, RSI neutral at {fmt(rsi,1)}. Watching {fmt(resistance)} for breakout."

def build_cross_narrative():
    parts = []
    # Regime change
    if prev.get("risk_regime") and prev["risk_regime"] != risk_regime:
        parts.append(f"Regime shifted from {prev['risk_regime']} to {risk_regime}")
    # Notable correlation changes
    if prev.get("corr_spx") and corr_spx is not None:
        d = corr_spx - prev["corr_spx"]
        if abs(d) >= 0.05:
            parts.append(f"S&P 500 correlation {'strengthened' if d > 0 else 'weakened'} to {corr_spx:.3f}")
    if prev.get("corr_nikkei") and corr_nikkei is not None:
        d = corr_nikkei - prev["corr_nikkei"]
        if abs(d) >= 0.05:
            parts.append(f"Nikkei correlation moved to {corr_nikkei:.3f}")

    if parts:
        result = "; ".join(parts) + "."
        if breakdown_alerts:
            result += f" {', '.join(breakdown_alerts)} correlation(s) inverted."
        return result
    else:
        # No changes — describe current regime
        if risk_regime == "RISK-ON":
            return "Correlations consistent with risk-on, supporting USD/JPY upside."
        elif risk_regime == "RISK-OFF":
            return "Correlations consistent with risk-off, favoring JPY strength."
        elif risk_regime == "DECORRELATED":
            return "USD/JPY decorrelated from risk assets — driven by rate differential and BOJ expectations."
        else:
            tail = f"; {', '.join(breakdown_alerts)} correlation(s) inverted" if breakdown_alerts else "; monitor for regime clarity"
            return f"Correlations in transition with no dominant regime{tail}."

macro_narrative = build_macro_narrative()
tech_narrative  = build_tech_narrative()
cross_narrative = build_cross_narrative()

report = f"""# USD/JPY Daily Analysis — {TODAY_STR}

> **{overall.upper()}** | Conviction: **{conviction}** | Score: **{weighted:+d}/+{daily_max}** | Modules: **{modules_available}/6** (daily)

---

## At a Glance

| | Value | 1W | 1M | 3M | Signal |
|---|---|---|---|---|---|
| USD/JPY | {fmt(usdjpy_now)} | {fmt_chg(usdjpy_1w)} | {fmt_chg(usdjpy_1m)} | {fmt_chg(usdjpy_3m)} | — |
| US 10Y | {fmt(us10y_now)}% | {fmt_chg(us10y_1w)} | {fmt_chg(us10y_1m)} | {fmt_chg(us10y_3m)} | — |
| JP 10Y | {fmt(jp10y_now)}% | {fmt_chg(jp10y_1w)} | {fmt_chg(jp10y_1m)} | {fmt_chg(jp10y_3m)} | — |
| Spread | {fmt(spread_now)}% | {fmt_chg(spread_1w)} | {fmt_chg(spread_1m)} | {fmt_chg(spread_3m)} | {spread_dir} |
| RSI (14) | {fmt(rsi, 1)} | — | — | — | {rsi_sig} |

> {at_a_glance_summary} {"Spread " + spread_dir.lower() + " (" + div_check + ") with USD/JPY pressing " + fmt(resistance) + " resistance." if div_check == "CONFIRMED" else "Spread " + spread_dir.lower() + " but USD/JPY diverging — caution warranted." if div_check == "DIVERGENCE" else "Rate differentials stable; technicals and cross-asset regime driving price action."}

---

## Risk Alerts

| Alert | Status | Detail |
|---|---|---|
| BOJ Intervention | **{intervention_risk}** | USD/JPY at {fmt(price)}, {fmt_chg(usdjpy_1m)} yen in 30d |
| Event Risk (48h) | **UNKNOWN** | Run /usdjpy-weekly for calendar |
| COT Crowding | **N/A** | Weekly module only |
| Correlation Breakdown | **{"YES" if breakdown_alerts else "NO"}** | {", ".join(breakdown_alerts) if breakdown_alerts else "All normal"} |

---

## 01 — Macro Regime

**Bias: {macro_bias}** | Confidence: {macro_conf}

| Metric | Current | 1W Chg | 1M Chg | 3M Chg |
|--------|---------|--------|--------|--------|
| US 10Y | {fmt(us10y_now)}% | {fmt_chg(us10y_1w)} | {fmt_chg(us10y_1m)} | {fmt_chg(us10y_3m)} |
| JP 10Y | {fmt(jp10y_now)}% | {fmt_chg(jp10y_1w)} | {fmt_chg(jp10y_1m)} | {fmt_chg(jp10y_3m)} |
| Spread | {fmt(spread_now)}% | {fmt_chg(spread_1w)} | {fmt_chg(spread_1m)} | {fmt_chg(spread_3m)} |
| USD/JPY | {fmt(usdjpy_now)} | {fmt_chg(usdjpy_1w)} | {fmt_chg(usdjpy_1m)} | {fmt_chg(usdjpy_3m)} |

**Spread Direction:** {spread_dir} | **Divergence Check:** {div_check}

{macro_narrative}

*JP 10Y source: {jp10y_src}*
{"" if not charts_generated else chr(10) + "![Macro Spread vs USD/JPY](macro_spread_" + TODAY_STR + ".png)" + chr(10)}
---

## 03 — Technicals

**Bias: {tech_bias}** | Confidence: {tech_conf}

| Indicator | Value | Signal |
|-----------|-------|--------|
| Price | {fmt(price)} | — |
| 50 SMA | {fmt(sma50)} | {price_vs_sma50} price |
| 200 SMA | {fmt(sma200)} | {price_vs_sma200} price |
| SMA Cross | {sma_cross} | {"Bullish" if sma_cross == "GOLDEN" else "Bearish"} |
| RSI (14) | {fmt(rsi, 1)} | {rsi_sig} |
| MACD | {fmt(macd_val, 4)} / {fmt(macd_signal, 4)} | {macd_sig} |
| Ichimoku Cloud | {ichi["price_vs_cloud"] if ichi else "N/A"} | {ichi_sig} |

**Ichimoku:** Tenkan {fmt(ichi["tenkan"]) if ichi else "N/A"} | Kijun {fmt(ichi["kijun"]) if ichi else "N/A"} | Cloud: {ichi["cloud_color"] if ichi else "N/A"}
**Key Levels:** Support {fmt(support)} | Resistance {fmt(resistance)}

{tech_narrative}

*Data source: {ohlcv_src}*
{"" if not charts_generated else chr(10) + "![Technical Analysis](technicals_" + TODAY_STR + ".png)" + chr(10)}
---

## 05 — Cross-Asset Correlations

**Bias: {cross_bias}** | Confidence: {cross_conf} | Regime: {risk_regime}

| Asset | 30d Correlation | Expected | Status |
|-------|----------------|----------|--------|
| S&P 500 | {fmt(corr_spx, 3) if corr_spx else "N/A"} | Positive | {corr_status(corr_spx, True)} |
| Nikkei 225 | {fmt(corr_nikkei, 3) if corr_nikkei else "N/A"} | Positive | {corr_status(corr_nikkei, True)} |
| Gold | {fmt(corr_gold, 3) if corr_gold else "N/A"} | Negative | {corr_status(corr_gold, False)} |
| VIX | {fmt(corr_vix, 3) if corr_vix else "N/A"} | Negative | {corr_status(corr_vix, False)} |
| WTI Oil | {fmt(corr_oil, 3) if corr_oil else "N/A"} | Positive | {corr_status(corr_oil, True)} |

{cross_narrative}
{"" if not charts_generated else chr(10) + "![Cross-Asset Correlations](correlations_" + TODAY_STR + ".png)" + chr(10)}
---

## 07 — Checklist

| # | Factor | Direction | Confidence | Note |
|---|--------|-----------|------------|------|
| 1 | Macro Regime | {macro_bias[:4]} | {macro_conf} | Spread {spread_dir.lower()} {fmt_chg(spread_1m)}pp; {div_check} |
| 2 | Central Bank | N/A | N/A | Weekly module |
| 3 | Technicals | {tech_bias[:4]} | {tech_conf} | {sma_cross} cross; {ichi["price_vs_cloud"] if ichi else "N/A"} cloud; RSI {fmt(rsi,1)} |
| 4 | Positioning | N/A | N/A | Weekly module |
| 5 | Cross-Asset | {("NEUT" if cross_bias == "NEUTRAL" else cross_bias[:4])} | {cross_conf} | {risk_regime}; {"Breakdowns: " + ", ".join(breakdown_alerts) if breakdown_alerts else "No breakdowns"} |
| 6 | Seasonality | N/A | N/A | Weekly module |

**Overall: {overall}**
**Score: {weighted:+d} / +{daily_max}** | **Conviction: {conviction}** | **Modules: {modules_available}/6**
{"" if not conviction_cap_note else chr(10) + "⚠ " + conviction_cap_note + chr(10)}{"" if not structural_conflict_note else chr(10) + "⚠ " + structural_conflict_note + " — conviction downgraded" + chr(10)}
---

## Bottom Line

{bottom_line_text}

---
{"" if not freshness_line else freshness_line + chr(10) + chr(10)}*Data: FRED, MOF Japan, Yahoo Finance | TZ: JST | Next: /usdjpy-daily tomorrow | Full: /usdjpy-weekly Friday*
*Data freshness: {freshness_stamps}*
"""

report_path = OUTPUT_DIR / f"{TODAY_STR}.md"
with open(report_path, "w") as f:
    f.write(report)
print(f"  Report saved: {report_path}")

# ── Generate PDF ─────────────────────────────────────────────────────────────
try:
    from generate_pdf import markdown_to_pdf
    pdf_path = markdown_to_pdf(report_path)
    print(f"  PDF saved:    {pdf_path}")
except Exception as e:
    print(f"  PDF generation failed: {e}")

# ── Print summary for parent process ─────────────────────────────────────────
print("\n" + "="*60)
print(f"USD/JPY DAILY ANALYSIS COMPLETE — {TODAY_STR}")
print("="*60)
print(f"  USD/JPY:        {fmt(price)}")
print(f"  US-JP Spread:   {fmt(spread_now)}pp  ({spread_dir})")
print(f"  Macro Bias:     {macro_bias} / {macro_conf}")
print(f"  Technical Bias: {tech_bias} / {tech_conf}")
print(f"  Cross-Asset:    {cross_bias} / {cross_conf}  ({risk_regime})")
print(f"  OVERALL:        {overall}")
print(f"  Conviction:     {conviction}")
print(f"  Report:         {report_path}")
print("="*60)
