# -*- coding: utf-8 -*-
"""
CBR key rate vs Russian equities (IMOEX, RTS, top-30 stocks) — full reproducible study.

Tested on: Python 3.10+
Required packages:
  pip install pandas numpy requests lxml matplotlib statsmodels scipy

Optional (if installed):
  pip install openpyxl
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import json
import textwrap
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import matplotlib.pyplot as plt

from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests
from statsmodels.stats.diagnostic import breaks_cusumolsresid


# =========================
# User-configurable constants
# =========================

DATA_DIR = Path("cbr_moex_rate_study")
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "output"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Analysis window (max intersection will be used automatically)
CBR_FROM_DDMMYYYY = "17.09.2013"
CBR_TO_DDMMYYYY = date.today().strftime("%d.%m.%Y")

# Indices and stocks
INDEX_SECIDS = {
    "IMOEX": "IMOEX",
    "RTS": "RTSI",  # MOEX secid for RTS index in ISS is typically "RTSI"
}

# Top-30 large & liquid universe (edit if needed; script will skip missing history)
TOP30_TICKERS: List[str] = [
    "SBER", "SBERP", "GAZP", "LKOH", "ROSN", "NVTK", "SIBN", "GMKN", "PLZL", "ALRS",
    "TATN", "SNGS", "SNGSP", "NLMK", "CHMF", "MAGN", "PHOR", "MTSS", "RTKM", "TRNFP",
    "MOEX", "VTBR", "IRAO", "HYDR", "UPRO", "PIKK", "SMLT", "OZON", "X5", "YDEX",
]

# MOEX boards
SHARES_BOARD = "TQBR"   # main board for shares
INDEX_BOARD = "SNDX"    # stock market indices board (per MOEX ISS examples)

# Candle settings
CANDLE_INTERVAL = 24    # daily
PAGE_LIMIT = 500        # MOEX candles typical limit for a single response page

# Backtest assumptions
COMMISSION_HALF_TURN = 0.0005      # 0.05% each side
SLIPPAGE_HALF_TURN = 0.0002        # 0.02% each side
SHORT_BORROW_ANNUAL = 0.08         # 8% per year
TRADING_DAYS_PER_YEAR = 252

VOL_TARGET_ANNUAL = 0.10           # 10% annual vol target (optional sizing)
MAX_LEVERAGE = 2.0

# Strategy parameters
HOLD_DAYS_LIST = [1, 3, 5, 10]
MIN_BP_MOVE = 50  # trade only if abs(change) >= 50 bps, where 50 bps = 0.50%

# Regime filters
MA_TREND_WINDOW = 200
VOL_WINDOW = 20
VOL_PCTL_FILTER = 0.5  # trade only when volatility above median (example)

# If True, generate synthetic data instead of fetching from cbr.ru / iss.moex.com
# (useful when network is unavailable).
#
# Default is False so that, per the README, running the script produces a
# real-data analysis out of the box. The previous default of True meant that
# anyone who cloned the repo and ran the script got a fully synthetic
# backtest and would not realise the synthetic pipeline was active — the
# output looks structurally identical to a real-data run.
#
# To run offline (no network), either:
#   - flip this flag, or
#   - pass --synthetic on the command line (see the new CLI block in main()).
USE_SYNTHETIC = False


# =========================
# Synthetic data generation (realistic simulation)
# =========================

def _generate_synthetic_keyrate() -> pd.DataFrame:
    """
    Generate a realistic step-function key rate series mimicking CBR decisions
    from 2013-09-17 to 2025-12-31.  Approximate real trajectory:
      2013: 5.50 -> 2014 Dec: 17.00 (crisis hike) -> 2015-2019 gradual cuts to ~6.0
      -> 2020 Covid cut to 4.25 -> 2021-2022 hike cycle to 20.0 (Feb 2022 emergency)
      -> gradual cuts to ~7.5 in 2023 -> re-hike to 21% in 2024 -> holds 2025
    """
    np.random.seed(42)
    decisions = [
        # (date, rate)  — approximate real CBR decisions
        ("2013-09-17", 5.50),
        ("2014-03-03", 7.00),
        ("2014-04-28", 7.50),
        ("2014-07-28", 8.00),
        ("2014-11-05", 9.50),
        ("2014-12-12", 10.50),
        ("2014-12-16", 17.00),
        ("2015-02-02", 15.00),
        ("2015-03-16", 14.00),
        ("2015-05-05", 12.50),
        ("2015-06-16", 11.50),
        ("2015-08-03", 11.00),
        ("2016-06-14", 10.50),
        ("2016-09-19", 10.00),
        ("2017-03-27", 9.75),
        ("2017-05-02", 9.25),
        ("2017-06-19", 9.00),
        ("2017-09-18", 8.50),
        ("2017-10-30", 8.25),
        ("2017-12-18", 7.75),
        ("2018-02-12", 7.50),
        ("2018-03-26", 7.25),
        ("2018-09-17", 7.50),
        ("2018-12-17", 7.75),
        ("2019-06-17", 7.50),
        ("2019-07-29", 7.25),
        ("2019-09-09", 7.00),
        ("2019-10-28", 6.50),
        ("2019-12-16", 6.25),
        ("2020-02-10", 6.00),
        ("2020-04-27", 5.50),
        ("2020-06-22", 4.50),
        ("2020-07-27", 4.25),
        ("2021-03-22", 4.50),
        ("2021-04-26", 5.00),
        ("2021-06-15", 5.50),
        ("2021-07-26", 6.50),
        ("2021-09-13", 6.75),
        ("2021-10-25", 7.50),
        ("2021-12-20", 8.50),
        ("2022-02-14", 9.50),
        ("2022-02-28", 20.00),
        ("2022-04-11", 17.00),
        ("2022-05-04", 14.00),
        ("2022-06-14", 9.50),
        ("2022-07-25", 8.00),
        ("2022-09-19", 7.50),
        ("2023-07-24", 8.50),
        ("2023-09-18", 13.00),
        ("2023-10-30", 15.00),
        ("2023-12-18", 16.00),
        ("2024-02-16", 16.00),
        ("2024-07-26", 18.00),
        ("2024-09-13", 19.00),
        ("2024-10-25", 21.00),
        ("2024-12-20", 21.00),
        ("2025-02-14", 21.00),
        ("2025-06-06", 21.00),
        ("2025-12-31", 21.00),
    ]
    df = pd.DataFrame(decisions, columns=["date", "key_rate"])
    df["date"] = pd.to_datetime(df["date"])
    # Expand to daily frequency (calendar days)
    full_idx = pd.date_range("2013-09-17", "2025-12-31", freq="D")
    daily = df.set_index("date")["key_rate"].reindex(full_idx).ffill()
    out = pd.DataFrame({"date": daily.index, "key_rate": daily.values}).reset_index(drop=True)
    return out


def _generate_synthetic_index(name: str, keyrate_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a synthetic daily index price series correlated with key rate changes.
    IMOEX starts ~1500 in 2013, RTS ~1400; both grow with drift, vol, and
    negative correlation with rate hikes.
    """
    np.random.seed({"IMOEX": 123, "RTS": 456}.get(name, 789))
    kr = keyrate_df.set_index("date")["key_rate"]

    # Business days only
    bdays = pd.bdate_range(kr.index.min(), kr.index.max())
    kr_bd = kr.reindex(bdays).ffill().dropna()
    kr_delta = kr_bd.diff().fillna(0.0)

    n = len(kr_bd)
    # Daily returns: drift + vol + rate-change impact + noise
    drift = 0.0003 if name == "IMOEX" else 0.0001  # ~7.5% or ~2.5% annual
    vol = 0.015 if name == "IMOEX" else 0.018
    rate_impact = -0.008  # negative: hike hurts index
    noise = np.random.normal(0, vol, n)

    returns = drift + rate_impact * kr_delta.values + noise
    start_price = 1500.0 if name == "IMOEX" else 1400.0
    prices = start_price * np.exp(np.cumsum(returns))

    df = pd.DataFrame({"date": kr_bd.index, "close": prices})
    return df.reset_index(drop=True)


def _generate_synthetic_stock(ticker: str, keyrate_df: pd.DataFrame,
                               imoex_ret: pd.Series) -> pd.DataFrame:
    """
    Generate synthetic stock prices:
      - correlated with IMOEX (beta ~0.8-1.2)
      - exporters have less sensitivity to rate, domestic have more
    """
    exporters = {"GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "PLZL", "ALRS", "SIBN", "SNGS",
                 "SNGSP", "TATN", "NLMK", "CHMF", "MAGN", "PHOR"}
    domestic = {"SBER", "SBERP", "VTBR", "MTSS", "PIKK", "SMLT", "MOEX", "RTKM",
                "HYDR", "IRAO", "UPRO", "OZON", "X5", "YDEX", "TRNFP"}

    seed = sum(ord(c) for c in ticker) % 10000
    np.random.seed(seed)

    kr = keyrate_df.set_index("date")["key_rate"]
    bdays = imoex_ret.index
    kr_bd = kr.reindex(bdays).ffill().bfill()
    kr_delta = kr_bd.diff().fillna(0.0)

    n = len(bdays)
    beta = 0.8 + np.random.rand() * 0.5  # 0.8 to 1.3
    alpha = (np.random.rand() - 0.5) * 0.0002  # small alpha
    idio_vol = 0.01 + np.random.rand() * 0.01

    if ticker in exporters:
        rate_sens = -0.003 + np.random.rand() * 0.002  # less sensitive
    else:
        rate_sens = -0.008 - np.random.rand() * 0.004  # more sensitive

    idio = np.random.normal(0, idio_vol, n)
    imoex_vals = imoex_ret.reindex(bdays).fillna(0.0).values

    returns = alpha + beta * imoex_vals + rate_sens * kr_delta.values + idio
    start_price = 100 + np.random.rand() * 400
    prices = start_price * np.exp(np.cumsum(returns))

    df = pd.DataFrame({
        "date": bdays,
        "open": prices * (1 + np.random.normal(0, 0.002, n)),
        "high": prices * (1 + np.abs(np.random.normal(0, 0.005, n))),
        "low": prices * (1 - np.abs(np.random.normal(0, 0.005, n))),
        "close": prices,
        "volume": (np.random.rand(n) * 1e6 + 1e5).astype(int),
        "value": (np.random.rand(n) * 1e9 + 1e7).astype(int),
    })
    return df.reset_index(drop=True)


# =========================
# Utility: HTTP client
# =========================

@dataclass
class HTTPConfig:
    timeout: int = 45
    retries: int = 5
    backoff: float = 1.6
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


HTTP = HTTPConfig()


def http_get(url: str, params: Optional[dict] = None) -> requests.Response:
    headers = {"User-Agent": HTTP.user_agent}
    last_exc: Optional[Exception] = None
    for attempt in range(1, HTTP.retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=HTTP.timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            sleep_s = (HTTP.backoff ** (attempt - 1)) + np.random.rand() * 0.2
            time.sleep(sleep_s)
    raise RuntimeError(f"GET failed after {HTTP.retries} attempts: {url}") from last_exc


# =========================
# CBR: key rate (official table)
# =========================

def fetch_cbr_key_rate(from_ddmmyyyy: str, to_ddmmyyyy: str) -> pd.DataFrame:
    """
    Downloads key rate history table from cbr.ru/hd_base/KeyRate/ and parses it.

    Returns DataFrame with columns: date (datetime64), key_rate (float, in %).
    """
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    params = {
        "UniDbQuery.Posted": "True",
        "UniDbQuery.From": from_ddmmyyyy,
        "UniDbQuery.To": to_ddmmyyyy,
    }
    html = http_get(url, params=params).text
    tables = pd.read_html(html)
    if not tables:
        raise RuntimeError("CBR KeyRate table not found in HTML.")
    df = tables[0].copy()

    # Expected columns in RU: ["Дата", "Ставка"]
    # Be robust to variations.
    col_date = df.columns[0]
    col_rate = df.columns[1]

    df.rename(columns={col_date: "date", col_rate: "key_rate"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["key_rate"] = (
        df["key_rate"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    df = df.dropna(subset=["date", "key_rate"]).sort_values("date").reset_index(drop=True)
    return df


def make_keyrate_frequencies(df_daily: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Produces daily / monthly / quarterly features:
      - level (end-of-period)
      - average
      - delta (end-of-period change)
    """
    d = df_daily.copy()
    d = d.set_index("date").sort_index()
    d = d[~d.index.duplicated(keep="last")]

    out: Dict[str, pd.DataFrame] = {}

    # Daily
    out["daily"] = d.rename(columns={"key_rate": "key_rate_daily"})

    # Monthly
    m = pd.DataFrame(index=d.resample("ME").last().index)
    m["key_rate_eom"] = d["key_rate"].resample("ME").last()
    m["key_rate_avg"] = d["key_rate"].resample("ME").mean()
    m["key_rate_delta_eom"] = m["key_rate_eom"].diff()
    out["monthly"] = m

    # Quarterly
    q = pd.DataFrame(index=d.resample("QE").last().index)
    q["key_rate_eoq"] = d["key_rate"].resample("QE").last()
    q["key_rate_avg"] = d["key_rate"].resample("QE").mean()
    q["key_rate_delta_eoq"] = q["key_rate_eoq"].diff()
    out["quarterly"] = q

    return out


# =========================
# MOEX ISS: data fetching
# =========================

def moex_iss_fetch_json(base_url: str, params: Optional[dict] = None) -> dict:
    resp = http_get(base_url, params=params)
    return resp.json()


def fetch_moex_candles(
    engine: str,
    market: str,
    board: str,
    secid: str,
    from_ymd: str,
    to_ymd: str,
    interval: int = 24,
    page_limit: int = 500,
) -> pd.DataFrame:
    """
    Fetches candles via:
      https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{secid}/candles.json

    Uses pagination start=0,500,1000...
    """
    base_url = (
        f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{board}"
        f"/securities/{secid}/candles.json"
    )

    all_rows: List[List] = []
    cols: Optional[List[str]] = None

    start = 0
    while True:
        params = {
            "from": from_ymd,
            "till": to_ymd,
            "interval": interval,
            "start": start,
            "iss.meta": "off",
            "iss.only": "candles",
        }
        js = moex_iss_fetch_json(base_url, params=params)
        block = js.get("candles", {})
        if not block:
            break
        if cols is None:
            cols = block.get("columns", [])
        data = block.get("data", [])
        if not data:
            break
        all_rows.extend(data)

        if len(data) < page_limit:
            break
        start += page_limit

    if not all_rows or not cols:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "value", "volume"])

    df = pd.DataFrame(all_rows, columns=cols)

    # MOEX candles usually: open, close, high, low, value, volume, begin, end
    if "begin" in df.columns:
        df["date"] = pd.to_datetime(df["begin"].str.slice(0, 10))
    elif "end" in df.columns:
        df["date"] = pd.to_datetime(df["end"].str.slice(0, 10))
    else:
        raise RuntimeError(f"Unexpected candle columns for {secid}: {df.columns.tolist()}")

    keep_cols = []
    for c in ["open", "high", "low", "close", "value", "volume", "date"]:
        if c in df.columns:
            keep_cols.append(c)
    df = df[keep_cols].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df


def fetch_moex_index_history_close(
    secid: str,
    from_ymd: str,
    to_ymd: str,
) -> pd.DataFrame:
    """
    Fetches index history via MOEX ISS 'history' endpoint (close prices).
    Uses:
      https://iss.moex.com/iss/history/engines/stock/markets/index/boards/SNDX/securities/{secid}.json
    with pagination start/limit.

    Returns: date, close
    """
    base_url = (
        f"https://iss.moex.com/iss/history/engines/stock/markets/index/boards/{INDEX_BOARD}"
        f"/securities/{secid}.json"
    )

    all_rows: List[List] = []
    cols: Optional[List[str]] = None

    start = 0
    limit = 1000  # history endpoint often allows larger than 100; safe default
    while True:
        params = {
            "from": from_ymd,
            "till": to_ymd,
            "start": start,
            "limit": limit,
            "iss.meta": "off",
            "iss.only": "history",
            "history.columns": "TRADEDATE,CLOSE",
        }
        js = moex_iss_fetch_json(base_url, params=params)
        block = js.get("history", {})
        if not block:
            break
        if cols is None:
            cols = block.get("columns", [])
        data = block.get("data", [])
        if not data:
            break
        all_rows.extend(data)

        if len(data) < limit:
            break
        start += limit

    if not all_rows or not cols:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.DataFrame(all_rows, columns=cols)
    df.rename(columns={"TRADEDATE": "date", "CLOSE": "close"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return df


def compute_log_returns(price_df: pd.DataFrame, price_col: str = "close") -> pd.Series:
    s = price_df.set_index("date")[price_col].astype(float).sort_index()
    r = np.log(s).diff()
    return r.rename("ret")


# =========================
# Metrics & backtest
# =========================

def max_drawdown(cum_curve: pd.Series) -> float:
    peak = cum_curve.cummax()
    dd = (cum_curve / peak) - 1.0
    return float(dd.min())


def perf_stats(returns: pd.Series) -> Dict[str, float]:
    r = returns.dropna().copy()
    if r.empty:
        return {k: float("nan") for k in [
            "cagr", "vol_ann", "sharpe", "max_dd", "win_rate", "n_days"
        ]}
    cum = (1.0 + r).cumprod()
    n = len(r)
    cagr = cum.iloc[-1] ** (TRADING_DAYS_PER_YEAR / n) - 1.0
    vol_ann = r.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = (r.mean() * TRADING_DAYS_PER_YEAR) / (r.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR) + 1e-12)
    mdd = max_drawdown(cum)
    win = (r > 0).mean()
    return {
        "cagr": float(cagr),
        "vol_ann": float(vol_ann),
        "sharpe": float(sharpe),
        "max_dd": float(mdd),
        "win_rate": float(win),
        "n_days": float(n),
    }


def apply_costs(positions: pd.Series, returns: pd.Series) -> pd.Series:
    """
    positions: -1..+1, indexed by date (daily)
    returns: close-to-close returns, indexed by date
    Costs:
      - commission and slippage on position changes (turnover)
      - borrow cost for shorts
    """
    pos = positions.reindex(returns.index).fillna(0.0)
    ret = returns.copy().fillna(0.0)

    # Turnover: abs(delta pos) is fraction of notional re-traded.
    turnover = pos.diff().abs().fillna(pos.abs())
    cost_per_turn = (COMMISSION_HALF_TURN + SLIPPAGE_HALF_TURN) * 2.0
    trading_cost = turnover * cost_per_turn

    # Borrow for shorts: daily cost on abs(short exposure)
    borrow_daily = SHORT_BORROW_ANNUAL / TRADING_DAYS_PER_YEAR
    borrow_cost = (pos.clip(upper=0).abs()) * borrow_daily

    pnl = pos.shift(1).fillna(0.0) * ret - trading_cost - borrow_cost
    return pnl.rename("strategy_ret")


def vol_target_position(signal: pd.Series, base_returns: pd.Series, vol_window: int = 20) -> pd.Series:
    """
    Vol-target sizing:
      leverage_t = min(MAX_LEVERAGE, VOL_TARGET_ANNUAL / (vol_est * sqrt(252)))
    """
    vol = base_returns.rolling(vol_window).std()
    lev = (VOL_TARGET_ANNUAL / (vol * math.sqrt(TRADING_DAYS_PER_YEAR) + 1e-12)).clip(upper=MAX_LEVERAGE)
    pos = (signal * lev).fillna(0.0)
    return pos


def build_event_signal(keyrate_daily: pd.DataFrame, min_bp: int = 0) -> pd.Series:
    """
    Signal on key rate changes:
      cut => +1, hike => -1, no change => 0
    min_bp: minimum absolute change to trade (in basis points).
    """
    d = keyrate_daily.set_index("date")["key_rate"].sort_index()
    delta = d.diff().fillna(0.0)
    # Convert to bps threshold: 1% = 100 bps. Here rate is in %.
    thresh = min_bp / 100.0
    sig = pd.Series(0.0, index=d.index)
    sig[delta <= -thresh] = 1.0
    sig[delta >= thresh] = -1.0
    return sig.rename("event_signal")


def hold_signal(signal: pd.Series, hold_days: int) -> pd.Series:
    """
    Converts sparse event signal into holding positions for N trading days.
    If new signal arrives, overrides.
    """
    idx = signal.index
    pos = pd.Series(0.0, index=idx)
    active_until: Optional[pd.Timestamp] = None
    active_val = 0.0

    for dt in idx:
        s = float(signal.loc[dt])
        if s != 0.0:
            active_val = s
            # set expiry in trading-day sense
            # approximate by counting forward in index positions
            i = idx.get_loc(dt)
            j = min(i + hold_days, len(idx) - 1)
            active_until = idx[j]
        if active_until is not None and dt <= active_until:
            pos.loc[dt] = active_val
        else:
            pos.loc[dt] = 0.0
    return pos.rename(f"pos_hold_{hold_days}")


# =========================
# Main analysis
# =========================

def plot_series(df: pd.DataFrame, title: str, path: Path) -> None:
    plt.figure(figsize=(12, 5))
    for col in df.columns:
        plt.plot(df.index, df[col], label=col)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> None:
    # -------------------------
    # Data loading (live or synthetic)
    # -------------------------
    idx_prices: Dict[str, pd.DataFrame] = {}
    idx_returns: Dict[str, pd.Series] = {}
    stock_close: Dict[str, pd.DataFrame] = {}
    stock_ret: Dict[str, pd.Series] = {}

    if USE_SYNTHETIC:
        print("=== Using SYNTHETIC data (network unavailable) ===")
        keyrate = _generate_synthetic_keyrate()
        keyrate.to_csv(RAW_DIR / "cbr_key_rate_daily.csv", index=False)
        print(f"Synthetic key rate: {len(keyrate)} rows, "
              f"{keyrate['date'].min().date()} .. {keyrate['date'].max().date()}")

        keyrate_freq = make_keyrate_frequencies(keyrate)
        keyrate_freq["monthly"].to_csv(RAW_DIR / "cbr_key_rate_monthly.csv")
        keyrate_freq["quarterly"].to_csv(RAW_DIR / "cbr_key_rate_quarterly.csv")

        for name in INDEX_SECIDS:
            df = _generate_synthetic_index(name, keyrate)
            df.to_csv(RAW_DIR / f"moex_index_{name}_close.csv", index=False)
            idx_prices[name] = df
            idx_returns[name] = compute_log_returns(df).rename(name)
            print(f"Synthetic index {name}: {len(df)} rows")

        # Generate stocks (need IMOEX returns first)
        imoex_log_ret = idx_returns["IMOEX"]
        for ticker in TOP30_TICKERS:
            df = _generate_synthetic_stock(ticker, keyrate, imoex_log_ret)
            df.to_csv(RAW_DIR / f"moex_{ticker}_candles_daily.csv", index=False)
            stock_close[ticker] = df[["date", "close"]].copy()
            stock_ret[ticker] = compute_log_returns(df).rename(ticker)
            print(f"Synthetic {ticker}: {len(df)} rows")

    else:
        print("=== Downloading CBR key rate ===")
        keyrate = fetch_cbr_key_rate(CBR_FROM_DDMMYYYY, CBR_TO_DDMMYYYY)
        keyrate.to_csv(RAW_DIR / "cbr_key_rate_daily.csv", index=False)

        keyrate_freq = make_keyrate_frequencies(keyrate)
        keyrate_freq["monthly"].to_csv(RAW_DIR / "cbr_key_rate_monthly.csv")
        keyrate_freq["quarterly"].to_csv(RAW_DIR / "cbr_key_rate_quarterly.csv")

        # Define analysis window by key rate range
        from_ymd = keyrate["date"].min().strftime("%Y-%m-%d")
        to_ymd = min(keyrate["date"].max(), pd.Timestamp.today()).strftime("%Y-%m-%d")

        print(f"Key rate window: {from_ymd} .. {to_ymd}")

        print("\n=== Downloading indices ===")

        for name, secid in INDEX_SECIDS.items():
            try:
                df = fetch_moex_index_history_close(secid=secid, from_ymd=from_ymd, to_ymd=to_ymd)
                if df.empty:
                    print(f"[WARN] No index history for {name} ({secid}).")
                    continue
                df.to_csv(RAW_DIR / f"moex_index_{secid}_close.csv", index=False)
                idx_prices[name] = df
                idx_returns[name] = compute_log_returns(df).rename(name)
                print(f"Index {name}: {len(df)} rows")
            except Exception as e:
                print(f"[ERROR] Index {name} failed: {e}")

        if "IMOEX" not in idx_returns:
            raise RuntimeError("IMOEX index returns are required for downstream analysis.")

        print("\n=== Downloading top-30 stock candles (daily) ===")

        for ticker in TOP30_TICKERS:
            try:
                df = fetch_moex_candles(
                    engine="stock",
                    market="shares",
                    board=SHARES_BOARD,
                    secid=ticker,
                    from_ymd=from_ymd,
                    to_ymd=to_ymd,
                    interval=CANDLE_INTERVAL,
                    page_limit=PAGE_LIMIT,
                )
                if df.empty:
                    print(f"[WARN] No candles for {ticker}. Skipping.")
                    continue
                df.to_csv(RAW_DIR / f"moex_{ticker}_candles_daily.csv", index=False)
                stock_close[ticker] = df[["date", "close"]].copy()
                stock_ret[ticker] = compute_log_returns(df).rename(ticker)
                print(f"{ticker}: {len(df)} rows")
            except Exception as e:
                print(f"[ERROR] {ticker} failed: {e}")

    # Build aligned panel for core analysis (IMOEX + key rate)
    imoex_r = idx_returns["IMOEX"].copy()
    rate_daily = keyrate.set_index("date")["key_rate"].rename("key_rate").sort_index()
    panel = pd.concat([imoex_r, rate_daily], axis=1).dropna()
    panel["key_rate_delta"] = panel["key_rate"].diff().fillna(0.0)

    panel.to_csv(OUT_DIR / "panel_imoex_keyrate_daily.csv")

    # -------------------------
    # Descriptive statistics
    # -------------------------
    print("\n=== Descriptive stats ===")
    desc = panel[["IMOEX", "key_rate", "key_rate_delta"]].describe()
    desc.to_csv(OUT_DIR / "desc_imoex_keyrate.csv")
    print(desc)

    # Plot key rate & cumulative returns
    cum = pd.DataFrame(index=panel.index)
    cum["IMOEX_cum"] = (1.0 + panel["IMOEX"].fillna(0.0)).cumprod()
    kr = pd.DataFrame(index=panel.index)
    kr["key_rate"] = panel["key_rate"]

    plot_series(kr, "CBR key rate (%), daily", OUT_DIR / "key_rate_daily.png")
    plot_series(cum, "IMOEX cumulative (log-return based)", OUT_DIR / "imoex_cum.png")

    # -------------------------
    # Lag correlations
    # -------------------------
    print("\n=== Lag correlation (IMOEX returns vs delta key rate) ===")
    max_lag = 30
    x = panel["key_rate_delta"]
    y = panel["IMOEX"]
    lag_corr = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            c = y.shift(-lag).corr(x)
        else:
            c = y.corr(x.shift(lag))
        lag_corr.append((lag, c))
    lag_corr_df = pd.DataFrame(lag_corr, columns=["lag_days", "corr"])
    lag_corr_df.to_csv(OUT_DIR / "lag_correlation_imoex_vs_keyrate_delta.csv", index=False)

    plt.figure(figsize=(12, 4))
    plt.plot(lag_corr_df["lag_days"], lag_corr_df["corr"])
    plt.title("Lag correlation: IMOEX returns vs delta KeyRate")
    plt.axhline(0, linewidth=1)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "lag_correlation.png", dpi=160)
    plt.close()

    # -------------------------
    # ARIMAX / SARIMAX
    # -------------------------
    print("\n=== ARIMAX (SARIMAX) ===")
    endog = panel["IMOEX"].astype(float)
    exog = panel[["key_rate", "key_rate_delta"]].astype(float)

    # Simple specification; you can grid-search orders if needed
    model = SARIMAX(endog=endog, exog=exog, order=(1, 0, 1), trend="c", enforce_stationarity=False)
    res = model.fit(disp=False)
    summary_text = str(res.summary())
    with open(OUT_DIR / "sarimax_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary_text)
    print(summary_text)

    # CUSUM stability test on residuals (structural instability)
    print("\n=== Structural stability (CUSUM) ===")
    r = res.resid.dropna()
    # breaks_cusumolsresid expects residuals and df (k parameters)
    cusum = breaks_cusumolsresid(r, ddof=int(res.df_model) if hasattr(res, "df_model") else 1)
    # Output: (stat, pvalue, crit_values)
    cusum_text = f"CUSUM stat: {cusum[0]}\nCUSUM p-value: {cusum[1]}\n"
    with open(OUT_DIR / "cusum_test.txt", "w", encoding="utf-8") as f:
        f.write(cusum_text)
    print(cusum_text)

    # -------------------------
    # VAR + Granger
    # -------------------------
    print("\n=== VAR + Granger ===")
    var_df = panel[["IMOEX", "key_rate_delta"]].dropna().copy()
    var_model = VAR(var_df)
    var_res = var_model.fit(maxlags=10, ic="aic")
    var_summary_text = str(var_res.summary())
    with open(OUT_DIR / "var_summary.txt", "w", encoding="utf-8") as f:
        f.write(var_summary_text)
    print(var_summary_text[:2000])

    # Granger tests
    # H0: x does NOT Granger-cause y
    gc_results = grangercausalitytests(var_df[["IMOEX", "key_rate_delta"]].dropna(), maxlag=10, verbose=False)
    # Save p-values per lag
    rows = []
    for lag, out in gc_results.items():
        pval = out[0]["ssr_ftest"][1]
        rows.append((lag, pval))
    gc_df = pd.DataFrame(rows, columns=["lag", "pvalue_ssr_ftest"])
    gc_df.to_csv(OUT_DIR / "granger_pvalues_keyrate_to_imoex.csv", index=False)
    print("\nGranger causality p-values (key_rate_delta -> IMOEX):")
    print(gc_df.to_string(index=False))

    # -------------------------
    # Backtests
    # -------------------------
    print("\n=== Backtest strategies ===")
    # Convert log returns to simple returns for PnL approx
    imoex_simple = np.expm1(panel["IMOEX"]).rename("IMOEX_simple")

    event_sig = build_event_signal(keyrate, min_bp=MIN_BP_MOVE)
    event_sig = event_sig.reindex(panel.index).fillna(0.0)

    # Regime filters
    price_imoex = idx_prices["IMOEX"].set_index("date")["close"].reindex(panel.index).ffill()
    ma200 = price_imoex.rolling(MA_TREND_WINDOW).mean()
    vol20 = imoex_simple.rolling(VOL_WINDOW).std()
    vol_median = vol20.expanding().median()

    # Strategy outputs
    strat_table = []

    for hold_days in HOLD_DAYS_LIST:
        # Strategy A: event-direction (no filter)
        pos_a = hold_signal(event_sig, hold_days=hold_days)
        pos_a = vol_target_position(pos_a, imoex_simple)  # vol target sizing
        ret_a = apply_costs(pos_a, imoex_simple)
        stats_a = perf_stats(ret_a)
        stats_a.update({"strategy": f"A_event_hold{hold_days}", "hold_days": hold_days})
        strat_table.append(stats_a)

        # Strategy B: event-direction + regime filter (trend & vol)
        filter_mask = (price_imoex > ma200) & (vol20 > vol_median)
        pos_b = hold_signal(event_sig, hold_days=hold_days) * filter_mask.astype(float)
        pos_b = vol_target_position(pos_b, imoex_simple)
        ret_b = apply_costs(pos_b, imoex_simple)
        stats_b = perf_stats(ret_b)
        stats_b.update({"strategy": f"B_event_regime_hold{hold_days}", "hold_days": hold_days})
        strat_table.append(stats_b)

    # Strategy C: cross-sectional (exporters vs domestic) on event days
    exporters = ["GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "PLZL", "ALRS", "SIBN", "SNGS"]
    domestic = ["SBER", "VTBR", "MTSS", "PIKK", "SMLT", "MOEX", "RTKM"]

    # Build equal-weight baskets if data exists
    def basket_returns(tickers: List[str]) -> pd.Series:
        rets = [stock_ret[t] for t in tickers if t in stock_ret]
        if not rets:
            return pd.Series(dtype=float)
        df = pd.concat(rets, axis=1).dropna(how="all")
        # Convert log returns to simple and equal-weight
        simple = np.expm1(df).mean(axis=1)
        return simple.rename("basket_ret")

    exp_ret = basket_returns(exporters)
    dom_ret = basket_returns(domestic)

    if not exp_ret.empty and not dom_ret.empty:
        # Align with panel
        cs = pd.concat([exp_ret.rename("exp"), dom_ret.rename("dom")], axis=1).reindex(panel.index).dropna()
        spread = (cs["exp"] - cs["dom"]).rename("spread")

        # Positions on spread: hike => long spread, cut => short spread
        sig_c = (-event_sig).reindex(spread.index).fillna(0.0)  # hike => -1 in event_sig => +1 in sig_c
        for hold_days in HOLD_DAYS_LIST:
            pos_c = hold_signal(sig_c, hold_days=hold_days)
            # No vol targeting by default for spread (but could be enabled)
            ret_c = apply_costs(pos_c, spread)
            stats_c = perf_stats(ret_c)
            stats_c.update({"strategy": f"C_cs_spread_hold{hold_days}", "hold_days": hold_days})
            strat_table.append(stats_c)

            # Save curves
            curve = (1.0 + ret_c.fillna(0.0)).cumprod()
            plt.figure(figsize=(12, 4))
            plt.plot(curve.index, curve.values)
            plt.title(f"Strategy C (spread) cumulative, hold={hold_days}")
            plt.tight_layout()
            plt.savefig(OUT_DIR / f"curve_C_spread_hold{hold_days}.png", dpi=160)
            plt.close()

    # Save strategy comparison
    strat_df = pd.DataFrame(strat_table).sort_values(["sharpe", "cagr"], ascending=False)
    strat_df.to_csv(OUT_DIR / "strategy_comparison.csv", index=False)
    print("\n=== Strategy comparison ===")
    print(strat_df.to_string(index=False))

    # Plot top 5 curves
    top_names = strat_df.head(5)["strategy"].tolist()
    curves = {}

    for name in top_names:
        if name.startswith("A_") or name.startswith("B_"):
            hold = int(name.split("hold")[-1])
            if name.startswith("A_"):
                pos = vol_target_position(hold_signal(event_sig, hold_days=hold), imoex_simple)
            else:
                filter_mask = (price_imoex > ma200) & (vol20 > vol_median)
                pos = vol_target_position(hold_signal(event_sig, hold_days=hold) * filter_mask.astype(float), imoex_simple)
            ret = apply_costs(pos, imoex_simple)
            curves[name] = (1.0 + ret.fillna(0.0)).cumprod()

    if curves:
        plt.figure(figsize=(12, 5))
        for name, curve in curves.items():
            plt.plot(curve.index, curve.values, label=name)
        plt.title("Top strategies cumulative curves (net of costs)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(OUT_DIR / "top_strategies_curves.png", dpi=160)
        plt.close()

    print(f"\n=== Done ===")
    print(f"Outputs saved to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    # Parse a tiny CLI so users can flip USE_SYNTHETIC without editing
    # source. The default (no flag) uses real CBR + MOEX ISS data per
    # the README. --synthetic enables offline mode.
    parser = argparse.ArgumentParser(
        description="CBR key rate vs Russian equities — strategy study."
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate synthetic data instead of fetching from cbr.ru / iss.moex.com "
             "(useful when network is unavailable).",
    )
    args = parser.parse_args()

    if args.synthetic:
        # Override the module-level default for this run only.
        USE_SYNTHETIC = True

    main()
