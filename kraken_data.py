import requests
import pandas as pd

def fetch_ohlc(pair: str, interval: int = 15) -> pd.DataFrame:
    r = requests.get("https://api.kraken.com/0/public/OHLC",
                     params={"pair": pair, "interval": interval}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("error"):
        raise ValueError("; ".join(payload["error"]))
    result = payload["result"]
    key = next(k for k in result if k != "last")
    df = pd.DataFrame(result[key], columns=[
        "time", "open", "high", "low", "close", "exchange_vwap", "volume", "count"])
    for c in ["open", "high", "low", "close", "exchange_vwap", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="s", utc=True)
    df = df.dropna(subset=["time", "open", "high", "low", "close", "volume"])
    return df.iloc[:-1].reset_index(drop=True) if len(df) > 1 else df

def load_csv_ohlc(file):
    df = pd.read_csv(file)
    df.columns = [str(c).strip().lower() for c in df.columns]
    required = ["time", "open", "high", "low", "close", "volume"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    for c in required[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=required).sort_values("time").drop_duplicates("time").reset_index(drop=True)
