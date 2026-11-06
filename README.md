# AutoTrader Pro Crypto v2

Phone-friendly Streamlit dashboard for Kraken public market data and cost-aware spot backtesting.

Run command:
`streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0`

Install `requirements.txt`.

Features:
- Kraken public OHLC market scanner.
- EMA 9/21/200, RSI, MACD, rolling VWAP and volume conditions.
- Backtest entries at the next candle open after a completed signal.
- Entry and exit fees, spread and slippage.
- Stop/target gap handling; stop-first if both levels touch in one OHLC bar.
- Capital and concurrent-position limits.
- Equity curve, net P&L, win rate, average win/loss, drawdown, profit factor and trade CSV export.
- Optional OHLC CSV upload with columns `time,open,high,low,close,volume`.

Important: Kraken's public OHLC endpoint returns at most 720 recent candles per request. Backtests are historical simulations, not evidence of future profitability. No private keys or live trading code are included.


## V3 dashboard controls
The dashboard now includes a paper-mode control centre, editable risk/strategy settings,
daily counter reset, saved baseline restore, factory reset, emergency-stop latch and an
in-session audit log. It remains research/paper-only: no private Kraken API keys or live
order execution are included. Settings are session-scoped in this prototype; download
the JSON backup to retain a copy. Automatic recovery is a design toggle only and does
not restart a process in this build.
