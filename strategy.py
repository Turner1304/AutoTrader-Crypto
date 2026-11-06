import numpy as np

def add_indicators(df):
    x = df.copy()
    c = x["close"]
    x["ema9"] = c.ewm(span=9, adjust=False).mean()
    x["ema21"] = c.ewm(span=21, adjust=False).mean()
    x["ema200"] = c.ewm(span=200, adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    # Correct edge cases: no losses means RSI 100; no movement means RSI 50.
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
    x["rsi"] = rsi
    fast = c.ewm(span=12, adjust=False).mean()
    slow = c.ewm(span=26, adjust=False).mean()
    x["macd"] = fast - slow
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    typical = (x["high"] + x["low"] + c) / 3
    volume = x["volume"].rolling(24).sum()
    x["vwap24"] = (typical * x["volume"]).rolling(24).sum() / volume.replace(0, np.nan)
    x["vol_avg20"] = x["volume"].rolling(20).mean()
    return x

def signal_details(row):
    checks = {
        "Price above EMA 200": row.close > row.ema200,
        "EMA 9 above EMA 21": row.ema9 > row.ema21,
        "MACD above signal": row.macd > row.macd_signal,
        "RSI between 50 and 70": 50 <= row.rsi <= 70,
        "Price above rolling VWAP": row.close > row.vwap24,
        "Volume above 20-candle average": row.volume > row.vol_avg20,
    }
    return {"checks": checks, "score": int(sum(checks.values())),
            "entry": bool(all(checks.values()))}
