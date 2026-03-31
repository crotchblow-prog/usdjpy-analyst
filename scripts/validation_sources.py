"""
External source fetchers for USD/JPY indicator validation.
Each function returns {indicator_name: value} or {} on failure.
"""

import numpy as np
import pandas as pd


def fetch_yahoo(config):
    """
    Fetch USD/JPY and cross-asset data from Yahoo Finance.
    Calculates: spot, SMA, RSI, MACD, Ichimoku from raw OHLC.
    """
    try:
        import yfinance as yf

        tech = config["technicals"]
        sma_periods = tech["sma_periods"]        # e.g. [50, 200]
        rsi_period = tech["rsi_period"]           # e.g. 14
        macd_fast = tech["macd"]["fast"]          # e.g. 12
        macd_slow = tech["macd"]["slow"]          # e.g. 26
        macd_signal = tech["macd"]["signal"]      # e.g. 9
        tenkan_period = tech["ichimoku"]["tenkan"] # e.g. 9
        kijun_period = tech["ichimoku"]["kijun"]   # e.g. 26

        # --- Fetch USD/JPY 6-month daily OHLC ---
        usdjpy = yf.download("USDJPY=X", period="6mo", interval="1d", auto_adjust=True, progress=False)
        if usdjpy.empty:
            print("[yahoo] Failed: no USDJPY=X data returned")
            return {}

        # Flatten MultiIndex columns if present
        if isinstance(usdjpy.columns, pd.MultiIndex):
            usdjpy.columns = usdjpy.columns.get_level_values(0)

        close = usdjpy["Close"].dropna()
        high = usdjpy["High"].dropna()
        low = usdjpy["Low"].dropna()

        result = {}

        # Spot price (most recent close)
        result["spot_usdjpy"] = float(close.iloc[-1])

        # SMAs
        for period in sma_periods:
            if len(close) >= period:
                result[f"sma_{period}"] = float(close.rolling(period).mean().iloc[-1])

        # RSI (Wilder's smoothing)
        if len(close) > rsi_period:
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(window=rsi_period).mean()
            avg_loss = loss.rolling(window=rsi_period).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi_series = 100 - (100 / (1 + rs))
            result["rsi_14"] = float(rsi_series.iloc[-1])

        # MACD
        if len(close) >= macd_slow:
            ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
            ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
            macd_line_series = ema_fast - ema_slow
            macd_signal_series = macd_line_series.ewm(span=macd_signal, adjust=False).mean()
            result["macd_line"] = float(macd_line_series.iloc[-1])
            result["macd_signal"] = float(macd_signal_series.iloc[-1])

        # Ichimoku: tenkan and kijun
        if len(high) >= kijun_period and len(low) >= kijun_period:
            tenkan_high = high.rolling(tenkan_period).max()
            tenkan_low = low.rolling(tenkan_period).min()
            result["ichimoku_tenkan"] = float(((tenkan_high + tenkan_low) / 2).iloc[-1])

            kijun_high = high.rolling(kijun_period).max()
            kijun_low = low.rolling(kijun_period).min()
            result["ichimoku_kijun"] = float(((kijun_high + kijun_low) / 2).iloc[-1])

        # --- Cross-asset spots ---
        cross_assets = {
            "^GSPC": "spot_sp500",
            "^N225": "spot_nikkei",
            "GC=F": "spot_gold",
            "^VIX": "spot_vix",
            "CL=F": "spot_wti",
            "DX-Y.NYB": "spot_dxy",
        }
        for ticker, key in cross_assets.items():
            try:
                df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    val = df["Close"].dropna().iloc[-1]
                    result[key] = float(val)
            except Exception:
                pass  # skip individual ticker failures silently

        print(f"[yahoo] Fetched {len(result)} indicators")
        return result

    except Exception as e:
        print(f"[yahoo] Failed: {e}")
        return {}


def fetch_investing():
    """
    Scrape technical indicators from investing.com USD/JPY technical page.
    Returns: rsi_14, sma_50, sma_200, macd_line
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        url = "https://www.investing.com/currencies/usd-jpy-technical"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.investing.com/",
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        result = {}

        # Map of label substrings to indicator keys
        label_map = {
            "RSI(14)": "rsi_14",
            "MACD(12,26)": "macd_line",
            "SMA50": "sma_50",
            "SMA200": "sma_200",
        }

        # Try to find tables containing technical indicator data
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label_text = cells[0].get_text(strip=True)
                    for key_substr, indicator in label_map.items():
                        if key_substr in label_text and indicator not in result:
                            try:
                                val_text = cells[1].get_text(strip=True).replace(",", "")
                                result[indicator] = float(val_text)
                            except ValueError:
                                pass

        # Fallback: search for indicator values in divs/spans if table parsing found nothing
        if not result:
            for key_substr, indicator in label_map.items():
                tags = soup.find_all(string=lambda text: text and key_substr in text)
                for tag in tags:
                    parent = tag.parent
                    # Look for a sibling or nearby element with a numeric value
                    sibling = parent.find_next_sibling()
                    if sibling:
                        try:
                            val_text = sibling.get_text(strip=True).replace(",", "")
                            result[indicator] = float(val_text)
                            break
                        except ValueError:
                            pass

        print(f"[investing] Fetched {len(result)} indicators")
        return result

    except Exception as e:
        print(f"[investing] Failed: {e}")
        return {}


def fetch_tradingview():
    """
    Fetch USD/JPY indicators from TradingView scanner API.
    Returns: spot_usdjpy, rsi_14, sma_50, sma_200, macd_line, macd_signal,
             ichimoku_kijun, ichimoku_tenkan
    """
    try:
        import requests

        url = "https://scanner.tradingview.com/forex/scan"
        payload = {
            "symbols": {
                "tickers": ["FX:USDJPY"]
            },
            "columns": [
                "close",
                "RSI",
                "RSI[1]",
                "SMA50",
                "SMA200",
                "MACD.macd",
                "MACD.signal",
                "Ichimoku.BLine",
                "Ichimoku.CLine",
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        # Response shape: {"data": [{"s": "FX:USDJPY", "d": [val0, val1, ...]}], ...}
        rows = data.get("data", [])
        if not rows:
            print("[tradingview] Failed: empty response data")
            return {}

        values = rows[0].get("d", [])
        # Map positional columns to indicator names
        column_map = [
            "spot_usdjpy",   # close
            "rsi_14",        # RSI
            None,            # RSI[1] (previous RSI — not needed, skip)
            "sma_50",        # SMA50
            "sma_200",       # SMA200
            "macd_line",     # MACD.macd
            "macd_signal",   # MACD.signal
            "ichimoku_kijun",  # Ichimoku.BLine (Kijun-sen / Base Line)
            "ichimoku_tenkan", # Ichimoku.CLine (Tenkan-sen / Conversion Line)
        ]

        result = {}
        for i, name in enumerate(column_map):
            if name is None:
                continue
            if i < len(values) and values[i] is not None:
                try:
                    result[name] = float(values[i])
                except (TypeError, ValueError):
                    pass

        print(f"[tradingview] Fetched {len(result)} indicators")
        return result

    except Exception as e:
        print(f"[tradingview] Failed: {e}")
        return {}
