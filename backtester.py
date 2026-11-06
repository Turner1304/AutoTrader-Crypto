from dataclasses import dataclass
import pandas as pd
from strategy import add_indicators, signal_details

@dataclass
class BacktestConfig:
    starting_cash: float = 200.0
    allocation_pct: float = 25.0
    fee_pct: float = 0.26
    spread_pct: float = 0.10
    slippage_pct: float = 0.05
    stop_pct: float = 1.5
    target_pct: float = 3.0
    max_positions: int = 3

def buy_fill(p, c):
    return p * (1 + (c.spread_pct / 2 + c.slippage_pct) / 100)

def sell_fill(p, c):
    return p * (1 - (c.spread_pct / 2 + c.slippage_pct) / 100)

def run_backtest(data_by_pair, cfg):
    cash, positions, trades, events = cfg.starting_cash, {}, [], []
    data = {}
    for pair, raw in data_by_pair.items():
        if raw is None or len(raw) < 220:
            events.append(f"{pair}: skipped; requires 220 candles, got {0 if raw is None else len(raw)}")
        else:
            data[pair] = add_indicators(raw).reset_index(drop=True)
    if not data:
        return {"trades": pd.DataFrame(), "equity": pd.DataFrame(), "metrics": metrics(pd.DataFrame(), pd.DataFrame(), cfg.starting_cash), "events": events, "candles": 0}

    times = sorted(set(t for df in data.values() for t in df.time))
    lookup = {p: {t: i for i, t in enumerate(df.time)} for p, df in data.items()}
    curve = []
    for t in times:
        # Manage exits first. If stop and target both touch in one candle, assume stop first.
        for pair in list(positions):
            i = lookup[pair].get(t)
            if i is None: continue
            bar, pos = data[pair].iloc[i], positions[pair]
            raw_exit, reason = None, None
            if bar.open <= pos["stop"]:
                raw_exit, reason = float(bar.open), "Stop loss (gap)"
            elif bar.open >= pos["target"]:
                raw_exit, reason = float(bar.open), "Take profit (gap)"
            elif bar.low <= pos["stop"]:
                raw_exit, reason = pos["stop"], "Stop loss"
            elif bar.high >= pos["target"]:
                raw_exit, reason = pos["target"], "Take profit"
            if raw_exit is not None:
                px = sell_fill(raw_exit, cfg)
                proceeds = pos["qty"] * px
                fee_out = proceeds * cfg.fee_pct / 100
                cash += proceeds - fee_out
                net = proceeds - fee_out - pos["cost"]
                trades.append({**pos["record"], "exit_time": t, "exit_price": px,
                               "exit_fee": fee_out, "fees": pos["fee_in"] + fee_out,
                               "net_pnl": net, "return_pct": 100 * net / pos["cost"],
                               "bars_held": i - pos["index"], "exit_reason": reason})
                del positions[pair]

        # Signal on prior completed candle; fill at this candle's open.
        for pair, df in data.items():
            i = lookup[pair].get(t)
            if i is None or i < 220 or pair in positions or len(positions) >= cfg.max_positions:
                continue
            row = df.iloc[i-1]
            cols = ["ema200", "ema9", "ema21", "macd", "macd_signal", "rsi", "vwap24", "vol_avg20"]
            if row[cols].isna().any() or not signal_details(row)["entry"]: continue
            px = buy_fill(float(df.iloc[i].open), cfg)
            budget = min(cash, cfg.starting_cash * cfg.allocation_pct / 100)
            notional = budget / (1 + cfg.fee_pct / 100)
            fee_in = notional * cfg.fee_pct / 100
            if notional <= 0 or px <= 0: continue
            qty = notional / px
            cash -= notional + fee_in
            positions[pair] = {"qty": qty, "cost": notional + fee_in, "fee_in": fee_in,
                "stop": px * (1-cfg.stop_pct/100), "target": px * (1+cfg.target_pct/100), "index": i,
                "record": {"pair": pair, "signal_time": row.time, "entry_time": t,
                    "entry_price": px, "quantity": qty, "entry_notional": notional,
                    "entry_fee": fee_in, "stop_price": px*(1-cfg.stop_pct/100),
                    "take_profit_price": px*(1+cfg.target_pct/100),
                    "signal_score": signal_details(row)["score"]}}
        value = cash
        for pair, pos in positions.items():
            i = lookup[pair].get(t)
            if i is not None: value += pos["qty"] * float(data[pair].iloc[i].close)
        curve.append({"time": t, "equity": value, "cash": cash, "open_positions": len(positions)})

    # Close any remaining positions at final available close, explicitly labelled.
    for pair, pos in list(positions.items()):
        last = data[pair].iloc[-1]
        px = sell_fill(float(last.close), cfg)
        proceeds = pos["qty"] * px
        fee_out = proceeds * cfg.fee_pct / 100
        cash += proceeds - fee_out
        net = proceeds - fee_out - pos["cost"]
        trades.append({**pos["record"], "exit_time": last.time, "exit_price": px,
            "exit_fee": fee_out, "fees": pos["fee_in"] + fee_out, "net_pnl": net,
            "return_pct": 100*net/pos["cost"], "bars_held": len(data[pair])-1-pos["index"],
            "exit_reason": "End of data"})
    eq = pd.DataFrame(curve)
    if not eq.empty:
        eq["peak"] = eq.equity.cummax()
        eq["drawdown_pct"] = (eq.equity/eq.peak-1)*100
    td = pd.DataFrame(trades)
    return {"trades": td, "equity": eq, "metrics": metrics(td, eq, cfg.starting_cash),
            "events": events, "candles": sum(len(x) for x in data.values())}

def metrics(td, eq, start):
    if td.empty:
        return {"starting_cash": start, "ending_equity": start, "net_pnl": 0, "return_pct": 0,
                "trades": 0, "win_rate": 0, "avg_win": 0, "avg_loss": 0,
                "profit_factor": None, "max_drawdown_pct": 0, "fees": 0}
    pnl = td.net_pnl
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_loss = abs(losses.sum())
    end = start + pnl.sum()
    return {"starting_cash": start, "ending_equity": end, "net_pnl": pnl.sum(),
        "return_pct": (end/start-1)*100, "trades": len(td), "win_rate": (pnl>0).mean()*100,
        "avg_win": wins.mean() if len(wins) else 0, "avg_loss": losses.mean() if len(losses) else 0,
        "profit_factor": wins.sum()/gross_loss if gross_loss else None,
        "max_drawdown_pct": abs(eq.drawdown_pct.min()) if not eq.empty else 0,
        "fees": td.fees.sum()}
