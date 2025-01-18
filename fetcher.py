# -*- coding: utf-8 -*-
"""Загрузка данных с cbr.ru и MOEX ISS."""

import time
from typing import Optional, List

import numpy as np
import pandas as pd
import requests

from config import INDEX_BOARD


_TIMEOUT = 45
_RETRIES = 5
_BACKOFF = 1.6
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _get(url, params=None):
    """GET с ретраями и экспоненциальным бэкофф."""
    last_err = None
    for i in range(_RETRIES):
        try:
            r = requests.get(url, params=params,
                             headers={"User-Agent": _UA}, timeout=_TIMEOUT)
            r.raise_for_status()
            return r
        except Exception as e:
            last_err = e
            time.sleep(_BACKOFF ** i + np.random.rand() * 0.2)
    raise RuntimeError(f"Не удалось загрузить {url}") from last_err


def fetch_cbr_keyrate(from_date, to_date):
    """Парсит таблицу ключевой ставки с cbr.ru."""
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    params = {
        "UniDbQuery.Posted": "True",
        "UniDbQuery.From": from_date,
        "UniDbQuery.To": to_date,
    }
    html = _get(url, params).text
    tables = pd.read_html(html)
    if not tables:
        raise RuntimeError("Таблица ключевой ставки не найдена")

    df = tables[0].copy()
    df.columns = ["date", "key_rate"]
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["key_rate"] = (
        df["key_rate"].astype(str)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )
    return df.dropna(subset=["date", "key_rate"]).sort_values("date").reset_index(drop=True)


def keyrate_frequencies(df_daily):
    """Пересчёт ставки в дневную/месячную/квартальную частоту."""
    d = df_daily.set_index("date").sort_index()
    d = d[~d.index.duplicated(keep="last")]

    out = {}
    out["daily"] = d.rename(columns={"key_rate": "key_rate_daily"})

    m = pd.DataFrame(index=d.resample("ME").last().index)
    m["key_rate_eom"] = d["key_rate"].resample("ME").last()
    m["key_rate_avg"] = d["key_rate"].resample("ME").mean()
    m["key_rate_delta_eom"] = m["key_rate_eom"].diff()
    out["monthly"] = m

    q = pd.DataFrame(index=d.resample("QE").last().index)
    q["key_rate_eoq"] = d["key_rate"].resample("QE").last()
    q["key_rate_avg"] = d["key_rate"].resample("QE").mean()
    q["key_rate_delta_eoq"] = q["key_rate_eoq"].diff()
    out["quarterly"] = q

    return out


def fetch_moex_candles(engine, market, board, secid,
                       from_ymd, to_ymd, interval=24, page_limit=500):
    """Свечи через MOEX ISS candles endpoint."""
    base = (
        f"https://iss.moex.com/iss/engines/{engine}/markets/{market}"
        f"/boards/{board}/securities/{secid}/candles.json"
    )
    rows = []
    cols = None
    start = 0

    while True:
        p = {
            "from": from_ymd, "till": to_ymd,
            "interval": interval, "start": start,
            "iss.meta": "off", "iss.only": "candles",
        }
        js = _get(base, p).json()
        block = js.get("candles", {})
        if not block:
            break
        if cols is None:
            cols = block.get("columns", [])
        data = block.get("data", [])
        if not data:
            break
        rows.extend(data)
        if len(data) < page_limit:
            break
        start += page_limit

    if not rows or not cols:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "value", "volume"])

    df = pd.DataFrame(rows, columns=cols)
    if "begin" in df.columns:
        df["date"] = pd.to_datetime(df["begin"].str.slice(0, 10))
    elif "end" in df.columns:
        df["date"] = pd.to_datetime(df["end"].str.slice(0, 10))
    else:
        raise RuntimeError(f"Непонятные колонки свечей для {secid}: {df.columns.tolist()}")

    keep = [c for c in ["open", "high", "low", "close", "value", "volume", "date"] if c in df.columns]
    return df[keep].dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def fetch_moex_index(secid, from_ymd, to_ymd):
    """История закрытия индекса через MOEX ISS history."""
    base = (
        f"https://iss.moex.com/iss/history/engines/stock/markets/index"
        f"/boards/{INDEX_BOARD}/securities/{secid}.json"
    )
    rows = []
    cols = None
    start = 0
    lim = 1000

    while True:
        p = {
            "from": from_ymd, "till": to_ymd,
            "start": start, "limit": lim,
            "iss.meta": "off", "iss.only": "history",
            "history.columns": "TRADEDATE,CLOSE",
        }
        js = _get(base, p).json()
        block = js.get("history", {})
        if not block:
            break
        if cols is None:
            cols = block.get("columns", [])
        data = block.get("data", [])
        if not data:
            break
        rows.extend(data)
        if len(data) < lim:
            break
        start += lim

    if not rows or not cols:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.DataFrame(rows, columns=cols)
    df.rename(columns={"TRADEDATE": "date", "CLOSE": "close"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
