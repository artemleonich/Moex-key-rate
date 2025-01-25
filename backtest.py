# -*- coding: utf-8 -*-
"""Бэктест и метрики стратегий."""

import math
from typing import Optional

import numpy as np
import pandas as pd

from config import (COMMISSION, SLIPPAGE, SHORT_BORROW_PA,
                    TRADING_DAYS, VOL_TARGET, MAX_LEVERAGE)


def log_returns(price_df, col="close"):
    s = price_df.set_index("date")[col].astype(float).sort_index()
    return np.log(s).diff().rename("ret")


def max_drawdown(cum):
    return float((cum / cum.cummax() - 1).min())


def perf_stats(rets):
    r = rets.dropna()
    if r.empty:
        return {k: float("nan") for k in ["cagr", "vol_ann", "sharpe", "max_dd", "win_rate", "n_days"]}

    cum = (1 + r).cumprod()
    n = len(r)
    cagr = cum.iloc[-1] ** (TRADING_DAYS / n) - 1
    vol = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    sr = (r.mean() * TRADING_DAYS) / (vol + 1e-12)
    mdd = max_drawdown(cum)

    return {
        "cagr": float(cagr),
        "vol_ann": float(vol),
        "sharpe": float(sr),
        "max_dd": float(mdd),
        "win_rate": float((r > 0).mean()),
        "n_days": float(n),
    }


def apply_costs(positions, returns):
    pos = positions.reindex(returns.index).fillna(0)
    ret = returns.fillna(0)

    turnover = pos.diff().abs().fillna(pos.abs())
    tc = turnover * (COMMISSION + SLIPPAGE) * 2
    borrow = pos.clip(upper=0).abs() * (SHORT_BORROW_PA / TRADING_DAYS)

    pnl = pos.shift(1).fillna(0) * ret - tc - borrow
    return pnl.rename("strategy_ret")


def vol_size(signal, base_ret, window=20):
    vol = base_ret.rolling(window).std()
    lev = (VOL_TARGET / (vol * math.sqrt(TRADING_DAYS) + 1e-12)).clip(upper=MAX_LEVERAGE)
    return (signal * lev).fillna(0)


def event_signal(kr_daily, min_bp=0):
    """Сигнал по изменению ставки: снижение -> лонг, повышение -> шорт."""
    d = kr_daily.set_index("date")["key_rate"].sort_index()
    delta = d.diff().fillna(0)
    thresh = min_bp / 100.0
    sig = pd.Series(0.0, index=d.index)
    sig[delta <= -thresh] = 1.0
    sig[delta >= thresh] = -1.0
    return sig.rename("event_signal")


def hold_signal(sig, days):
    """Удерживаем позицию N торговых дней после сигнала."""
    idx = sig.index
    pos = pd.Series(0.0, index=idx)
    until = None
    val = 0.0
    for dt in idx:
        s = float(sig.loc[dt])
        if s != 0:
            val = s
            i = idx.get_loc(dt)
            until = idx[min(i + days, len(idx) - 1)]
        if until is not None and dt <= until:
            pos.loc[dt] = val
        else:
            pos.loc[dt] = 0.0
    return pos.rename(f"pos_hold_{days}")
