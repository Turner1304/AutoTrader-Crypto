import json
from datetime import datetime, timezone, date
from pathlib import Path

import pandas as pd
import streamlit as st

from kraken_data import fetch_ohlc, load_csv_ohlc
from strategy import add_indicators, signal_details
from backtester import BacktestConfig, run_backtest

st.set_page_config(page_title="AutoTrader Pro Crypto", page_icon="📈", layout="wide")
st.title("AutoTrader Pro — Crypto")
st.caption("Kraken public market data • Spot only • Paper/research mode • Live trading is disabled")

DEFAULTS = {
    "pairs": ["XBTGBP", "ETHGBP", "SOLGBP"],
    "interval": 15,
    "capital": 200.0,
    "allocation": 25,
    "max_positions": 3,
    "fee": 0.26,
    "spread": 0.10,
    "slippage": 0.05,
    "stop": 1.5,
    "target": 3.0,
    "rsi_period": 14,
    "ema_fast": 9,
    "ema_slow": 21,
    "ema_trend": 200,
    "daily_trade_limit": 5,
    "daily_loss_limit": 5.0,
}
CONFIG_FILE = Path("autotrader_settings.json")

def log_event(message):
    st.session_state.setdefault("audit_log", [])
    st.session_state["audit_log"].insert(0, {
        "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "event": message
    })
    st.session_state["audit_log"] = st.session_state["audit_log"][:200]

def init_state():
    if "config" not in st.session_state:
        st.session_state.config = DEFAULTS.copy()
    if "baseline" not in st.session_state:
        st.session_state.baseline = DEFAULTS.copy()
    if "bot_status" not in st.session_state:
        st.session_state.bot_status = "PAUSED"
    if "emergency_latched" not in st.session_state:
        st.session_state.emergency_latched = False
    if "daily_date" not in st.session_state:
        st.session_state.daily_date = str(date.today())
    if "daily_trades" not in st.session_state:
        st.session_state.daily_trades = 0
    if "daily_pnl" not in st.session_state:
        st.session_state.daily_pnl = 0.0
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    if "auto_daily_reset" not in st.session_state:
        st.session_state.auto_daily_reset = True
    if "auto_strategy_reset" not in st.session_state:
        st.session_state.auto_strategy_reset = True
    if "auto_recovery" not in st.session_state:
        st.session_state.auto_recovery = True

init_state()
cfg = st.session_state.config

# A date rollover resets counters only; it never changes risk or strategy preferences.
today = str(date.today())
if st.session_state.auto_daily_reset and st.session_state.daily_date != today:
    st.session_state.daily_date = today
    st.session_state.daily_trades = 0
    st.session_state.daily_pnl = 0.0
    log_event("Automatic daily reset: counters reset; saved strategy settings retained.")

tabs = st.tabs(["Dashboard", "Market scanner", "Backtesting", "Controls & resets", "Activity log"])

with tabs[0]:
    st.subheader("Bot control centre")
    status = st.session_state.bot_status
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mode", "PAPER ONLY")
    c2.metric("Status", status)
    c3.metric("Trades today", st.session_state.daily_trades)
    c4.metric("Daily P&L", f'£{st.session_state.daily_pnl:.2f}')
    if st.session_state.emergency_latched:
        st.error("EMERGENCY STOP LATCHED — automatic recovery is blocked. Clear the latch manually after checking the system.")
    a, b, c = st.columns(3)
    with a:
        if st.button("▶ Start paper mode", disabled=st.session_state.emergency_latched, use_container_width=True):
            st.session_state.bot_status = "RUNNING (PAPER)"
            log_event("Paper mode started.")
            st.rerun()
    with b:
        if st.button("Ⅱ Pause", use_container_width=True):
            st.session_state.bot_status = "PAUSED"
            log_event("Paper mode paused.")
            st.rerun()
    with c:
        if st.button("■ Emergency stop", type="primary", use_container_width=True):
            st.session_state.bot_status = "EMERGENCY STOP"
            st.session_state.emergency_latched = True
            log_event("EMERGENCY STOP activated. Automatic recovery disabled until manually cleared.")
            st.rerun()
    st.caption("These controls change the dashboard's paper-mode state only. They do not place, cancel or manage Kraken orders.")
    st.divider()
    st.subheader("Current risk settings")
    cols = st.columns(4)
    cols[0].metric("Starting balance", f'£{cfg["capital"]:.2f}')
    cols[1].metric("Allocation / trade", f'{cfg["allocation"]}%')
    cols[2].metric("Stop loss", f'{cfg["stop"]:.2f}%')
    cols[3].metric("Take profit", f'{cfg["target"]:.2f}%')
    st.info("No live trading is connected. This build is for market research, historical testing and paper-mode interface development.")

with tabs[1]:
    st.subheader("Kraken market scanner")
    pairs = st.multiselect("Markets", ["XBTGBP", "ETHGBP", "SOLGBP", "XRPGBP", "XBTUSD", "ETHUSD", "SOLUSD"],
                           cfg["pairs"], key="scan_pairs")
    interval = st.selectbox("Candle interval", [5, 15, 30, 60], index=[5,15,30,60].index(cfg["interval"]), key="scan_interval")
    if st.button("Scan markets", type="primary"):
        rows, detail = [], {}
        bar = st.progress(0)
        for n, pair in enumerate(pairs):
            try:
                df = add_indicators(fetch_ohlc(pair, interval))
                sig = signal_details(df.iloc[-1])
                rows.append({"Pair": pair, "Last price": df.iloc[-1].close,
                             "Signal": "LONG SETUP (research only)" if sig["entry"] else "WAIT",
                             "Score": f'{sig["score"]}/6', "RSI": round(df.iloc[-1].rsi, 1)})
                detail[pair] = (df, sig)
            except Exception as e:
                rows.append({"Pair": pair, "Signal": "DATA ERROR", "Error": str(e)})
            bar.progress((n + 1) / max(len(pairs), 1))
        st.session_state["scan_rows"], st.session_state["scan_detail"] = rows, detail
    if "scan_rows" in st.session_state:
        st.dataframe(pd.DataFrame(st.session_state["scan_rows"]), use_container_width=True, hide_index=True)
        for pair, (df, sig) in st.session_state.get("scan_detail", {}).items():
            with st.expander(pair + " signal explanation"):
                for label, passed in sig["checks"].items():
                    st.write(("PASS — " if passed else "NO — ") + label)
                st.line_chart(df.set_index("time")[["close", "ema9", "ema21", "ema200"]].tail(150))

with tabs[2]:
    st.subheader("Cost-aware historical backtest")
    st.warning("Historical simulation only. It does not predict future returns or place orders.")
    st.caption("Kraken public OHLC endpoint supplies at most 720 recent candles per request. Upload a longer OHLC CSV for broader testing.")
    c1, c2 = st.columns(2)
    with c1:
        markets = st.multiselect("Pairs", ["XBTGBP", "ETHGBP", "SOLGBP", "XRPGBP"], cfg["pairs"], key="bt_pairs")
        minutes = st.selectbox("Interval", [5, 15, 30, 60, 240], index=[5,15,30,60,240].index(cfg["interval"]) if cfg["interval"] in [5,15,30,60,240] else 1)
        capital = st.number_input("Starting balance (£)", 25.0, 100000.0, float(cfg["capital"]), 25.0)
        alloc = st.slider("Maximum allocation per position (%)", 5, 100, int(cfg["allocation"]))
        maxpos = st.slider("Maximum simultaneous positions", 1, 5, int(cfg["max_positions"]))
    with c2:
        fee = st.number_input("Fee per side (%)", 0.0, 2.0, float(cfg["fee"]), 0.01)
        spread = st.number_input("Full spread assumption (%)", 0.0, 2.0, float(cfg["spread"]), 0.01)
        slip = st.number_input("Slippage per side (%)", 0.0, 2.0, float(cfg["slippage"]), 0.01)
        stop = st.number_input("Stop loss (%)", 0.2, 20.0, float(cfg["stop"]), 0.1)
        target = st.number_input("Take profit (%)", 0.2, 50.0, float(cfg["target"]), 0.1)
    upload = st.file_uploader("Optional OHLC CSV: time, open, high, low, close, volume", type="csv")
    if st.button("Run backtest", type="primary"):
        data = {}
        if upload:
            try:
                data["CSV upload"] = load_csv_ohlc(upload)
            except Exception as e:
                st.error(str(e))
        else:
            for pair in markets:
                try:
                    data[pair] = fetch_ohlc(pair, minutes)
                except Exception as e:
                    st.warning(f"{pair}: {e}")
        if data:
            st.session_state["bt"] = run_backtest(data, BacktestConfig(capital, alloc, fee, spread, slip, stop, target, maxpos))
    if "bt" in st.session_state:
        result = st.session_state["bt"]
        m = result["metrics"]
        st.caption(f'Candles tested: {result["candles"]:,}')
        cols = st.columns(3)
        for col, (label, val) in zip(cols, [
            ("Net P&L", f'£{m["net_pnl"]:.2f}'), ("Return", f'{m["return_pct"]:.2f}%'),
            ("Win rate", f'{m["win_rate"]:.1f}%'), ("Trades", str(m["trades"])),
            ("Max drawdown", f'{m["max_drawdown_pct"]:.2f}%'), ("Fees", f'£{m["fees"]:.2f}')]):
            col.metric(label, val)
        st.write(f'Average win: £{m["avg_win"]:.2f} | Average loss: £{m["avg_loss"]:.2f} | Profit factor: {m["profit_factor"]}')
        if not result["equity"].empty:
            st.line_chart(result["equity"].set_index("time")[["equity"]])
        if result["trades"].empty:
            st.info("No trades met the strategy rules in this sample.")
        else:
            st.dataframe(result["trades"], use_container_width=True, hide_index=True)
            st.download_button("Download trade log CSV", result["trades"].to_csv(index=False), "autotrader_backtest_trades.csv", "text/csv")
        summary = {"metrics": m, "candles": result["candles"], "created_utc": datetime.now(timezone.utc).isoformat()}
        st.download_button("Download summary JSON", json.dumps(summary, default=str, indent=2), "autotrader_backtest_summary.json", "application/json")

with tabs[3]:
    st.subheader("Customise strategy and risk controls")
    st.caption("Changes below are dashboard configuration only. Save a baseline before experimenting.")
    with st.form("settings_form"):
        left, right = st.columns(2)
        with left:
            new_pairs = st.multiselect("Default markets", ["XBTGBP", "ETHGBP", "SOLGBP", "XRPGBP"], cfg["pairs"])
            new_interval = st.selectbox("Default candle interval (minutes)", [5, 15, 30, 60], index=[5,15,30,60].index(cfg["interval"]))
            new_capital = st.number_input("Paper starting balance (£)", 25.0, 100000.0, float(cfg["capital"]), 25.0)
            new_alloc = st.slider("Maximum allocation per position (%)", 5, 100, int(cfg["allocation"]))
            new_maxpos = st.slider("Maximum simultaneous positions", 1, 5, int(cfg["max_positions"]))
            new_daily_trades = st.number_input("Daily trade limit", 1, 100, int(cfg["daily_trade_limit"]))
            new_daily_loss = st.number_input("Daily loss limit (£)", 1.0, 10000.0, float(cfg["daily_loss_limit"]), 1.0)
        with right:
            new_fee = st.number_input("Fee per side (%)", 0.0, 2.0, float(cfg["fee"]), 0.01)
            new_spread = st.number_input("Full spread assumption (%)", 0.0, 2.0, float(cfg["spread"]), 0.01)
            new_slippage = st.number_input("Slippage per side (%)", 0.0, 2.0, float(cfg["slippage"]), 0.01)
            new_stop = st.number_input("Stop loss (%)", 0.2, 20.0, float(cfg["stop"]), 0.1)
            new_target = st.number_input("Take profit (%)", 0.2, 50.0, float(cfg["target"]), 0.1)
            new_rsi = st.number_input("RSI period", 2, 50, int(cfg["rsi_period"]))
            new_fast = st.number_input("Fast EMA", 2, 100, int(cfg["ema_fast"]))
            new_slow = st.number_input("Slow EMA", 3, 200, int(cfg["ema_slow"]))
            new_trend = st.number_input("Trend EMA", 20, 400, int(cfg["ema_trend"]))
        submitted = st.form_submit_button("Save settings", type="primary")
    if submitted:
        if new_fast >= new_slow or new_slow >= new_trend:
            st.error("EMA periods must be ordered: Fast EMA < Slow EMA < Trend EMA. Settings were not saved.")
        elif not new_pairs:
            st.error("Select at least one default market.")
        else:
            updated = {
                "pairs": new_pairs, "interval": new_interval, "capital": new_capital,
                "allocation": new_alloc, "max_positions": new_maxpos,
                "daily_trade_limit": new_daily_trades, "daily_loss_limit": new_daily_loss,
                "fee": new_fee, "spread": new_spread, "slippage": new_slippage,
                "stop": new_stop, "target": new_target, "rsi_period": new_rsi,
                "ema_fast": new_fast, "ema_slow": new_slow, "ema_trend": new_trend
            }
            st.session_state.config = updated
            log_event("User saved custom settings.")
            st.success("Settings updated for this app session.")

    st.divider()
    st.subheader("Automatic reset behaviour")
    st.session_state.auto_daily_reset = st.toggle("Daily reset", value=st.session_state.auto_daily_reset,
        help="At a new calendar day, resets daily counters only. It does not reset your strategy or risk settings.")
    st.session_state.auto_strategy_reset = st.toggle("Restore baseline after optimisation", value=st.session_state.auto_strategy_reset,
        help="When strategy optimisation is added, experimental parameters will return to the saved baseline.")
    st.session_state.auto_recovery = st.toggle("Automatic recovery after a software error", value=st.session_state.auto_recovery,
        help="Design setting only in this prototype. A future connected service must reconcile exchange state before restarting.")
    r1, r2, r3 = st.columns(3)
    with r1:
        if st.button("Save current settings as baseline", use_container_width=True):
            st.session_state.baseline = st.session_state.config.copy()
            log_event("Current settings saved as the reset baseline.")
            st.success("Baseline saved.")
    with r2:
        if st.button("Restore baseline now", use_container_width=True):
            st.session_state.config = st.session_state.baseline.copy()
            log_event("Settings manually restored to saved baseline.")
            st.success("Baseline restored.")
            st.rerun()
    with r3:
        if st.button("Reset all settings to factory defaults", use_container_width=True):
            st.session_state.config = DEFAULTS.copy()
            st.session_state.baseline = DEFAULTS.copy()
            log_event("All settings and baseline reset to factory defaults.")
            st.success("Factory defaults restored.")
            st.rerun()
    st.divider()
    st.subheader("Emergency stop latch")
    if st.session_state.emergency_latched:
        st.warning("Clear only after reviewing the activity log and confirming no real exchange orders are running.")
        if st.button("Manually clear emergency stop"):
            st.session_state.emergency_latched = False
            st.session_state.bot_status = "PAUSED"
            log_event("Emergency stop manually cleared. Bot remains paused.")
            st.rerun()
    else:
        st.caption("Emergency stop is not latched.")

    st.subheader("Settings persistence")
    st.caption("Download a settings backup so you can keep a copy. This prototype stores settings in the current app session; durable cloud storage is not yet configured.")
    st.download_button("Download settings backup", json.dumps({"config": st.session_state.config, "baseline": st.session_state.baseline}, indent=2),
                       "autotrader_settings_backup.json", "application/json")

with tabs[4]:
    st.subheader("Audit trail")
    st.caption("Records setting changes, resets and paper-mode control actions during this app session.")
    if st.button("Clear activity log"):
        st.session_state.audit_log = []
        log_event("Activity log cleared by user.")
        st.rerun()
    if st.session_state.audit_log:
        st.dataframe(pd.DataFrame(st.session_state.audit_log), use_container_width=True, hide_index=True)
    else:
        st.info("No activity recorded yet.")

with st.expander("Important operating notes"):
    st.markdown("""
- This build has **no Kraken private API keys and no live order execution**.
- Start/pause/emergency-stop buttons control the prototype's paper-mode status only.
- Daily reset clears daily counters only; it does not erase trade history or change saved risk preferences.
- Automatic recovery is a configuration placeholder here, not a running service. A production bot must verify exchange balances and open orders before any restart.
- Emergency stop is latched and blocks the paper-mode Start button until manually cleared.
- Signals are evaluated on completed candles; simulated entries occur at the next candle open.
- Fees, spread and slippage are included in the backtest assumptions. OHLC bars cannot establish exact intrabar order; conservative stop-first handling is used when both stop and target are touched.
- Kraken public OHLC is limited to 720 recent candles. CSV upload supports longer historical tests.
""")
