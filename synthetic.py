# -*- coding: utf-8 -*-
"""Генерация синтетических данных для тестирования без сети.

Траектория ставки примерно повторяет реальные решения ЦБ 2013-2025.
"""

import numpy as np
import pandas as pd


# примерная реальная траектория ставки ЦБ
_CBR_DECISIONS = [
    ("2013-09-17", 5.50), ("2014-03-03", 7.00), ("2014-04-28", 7.50),
    ("2014-07-28", 8.00), ("2014-11-05", 9.50), ("2014-12-12", 10.50),
    ("2014-12-16", 17.00), ("2015-02-02", 15.00), ("2015-03-16", 14.00),
    ("2015-05-05", 12.50), ("2015-06-16", 11.50), ("2015-08-03", 11.00),
    ("2016-06-14", 10.50), ("2016-09-19", 10.00), ("2017-03-27", 9.75),
    ("2017-05-02", 9.25), ("2017-06-19", 9.00), ("2017-09-18", 8.50),
    ("2017-10-30", 8.25), ("2017-12-18", 7.75), ("2018-02-12", 7.50),
    ("2018-03-26", 7.25), ("2018-09-17", 7.50), ("2018-12-17", 7.75),
    ("2019-06-17", 7.50), ("2019-07-29", 7.25), ("2019-09-09", 7.00),
    ("2019-10-28", 6.50), ("2019-12-16", 6.25), ("2020-02-10", 6.00),
    ("2020-04-27", 5.50), ("2020-06-22", 4.50), ("2020-07-27", 4.25),
    ("2021-03-22", 4.50), ("2021-04-26", 5.00), ("2021-06-15", 5.50),
    ("2021-07-26", 6.50), ("2021-09-13", 6.75), ("2021-10-25", 7.50),
    ("2021-12-20", 8.50), ("2022-02-14", 9.50), ("2022-02-28", 20.00),
    ("2022-04-11", 17.00), ("2022-05-04", 14.00), ("2022-06-14", 9.50),
    ("2022-07-25", 8.00), ("2022-09-19", 7.50), ("2023-07-24", 8.50),
    ("2023-09-18", 13.00), ("2023-10-30", 15.00), ("2023-12-18", 16.00),
    ("2024-02-16", 16.00), ("2024-07-26", 18.00), ("2024-09-13", 19.00),
    ("2024-10-25", 21.00), ("2024-12-20", 21.00), ("2025-02-14", 21.00),
    ("2025-06-06", 21.00), ("2025-12-31", 21.00),
]


def make_keyrate():
    np.random.seed(42)
    df = pd.DataFrame(_CBR_DECISIONS, columns=["date", "key_rate"])
    df["date"] = pd.to_datetime(df["date"])
    idx = pd.date_range("2013-09-17", "2025-12-31", freq="D")
    daily = df.set_index("date")["key_rate"].reindex(idx).ffill()
    return pd.DataFrame({"date": daily.index, "key_rate": daily.values}).reset_index(drop=True)


def make_index(name, kr_df):
    np.random.seed({"IMOEX": 123, "RTS": 456}.get(name, 789))
    kr = kr_df.set_index("date")["key_rate"]
    bdays = pd.bdate_range(kr.index.min(), kr.index.max())
    kr_bd = kr.reindex(bdays).ffill().dropna()
    kr_delta = kr_bd.diff().fillna(0.0)
    n = len(kr_bd)

    drift = 0.0003 if name == "IMOEX" else 0.0001
    vol = 0.015 if name == "IMOEX" else 0.018
    noise = np.random.normal(0, vol, n)
    rets = drift - 0.008 * kr_delta.values + noise
    px = (1500.0 if name == "IMOEX" else 1400.0) * np.exp(np.cumsum(rets))

    return pd.DataFrame({"date": kr_bd.index, "close": px}).reset_index(drop=True)


def make_stock(ticker, kr_df, imoex_ret):
    """Синтетическая акция, скоррелированная с IMOEX и ставкой."""
    _exp = {"GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "PLZL", "ALRS", "SIBN",
            "SNGS", "SNGSP", "TATN", "NLMK", "CHMF", "MAGN", "PHOR"}

    seed = sum(ord(c) for c in ticker) % 10000
    np.random.seed(seed)

    kr = kr_df.set_index("date")["key_rate"]
    bdays = imoex_ret.index
    kr_bd = kr.reindex(bdays).ffill().bfill()
    kr_delta = kr_bd.diff().fillna(0.0)
    n = len(bdays)

    beta = 0.8 + np.random.rand() * 0.5
    alpha = (np.random.rand() - 0.5) * 0.0002
    idio_vol = 0.01 + np.random.rand() * 0.01
    rate_sens = (-0.003 + np.random.rand() * 0.002) if ticker in _exp else (-0.008 - np.random.rand() * 0.004)

    idio = np.random.normal(0, idio_vol, n)
    mkt = imoex_ret.reindex(bdays).fillna(0.0).values
    rets = alpha + beta * mkt + rate_sens * kr_delta.values + idio

    px = (100 + np.random.rand() * 400) * np.exp(np.cumsum(rets))

    return pd.DataFrame({
        "date": bdays,
        "open": px * (1 + np.random.normal(0, 0.002, n)),
        "high": px * (1 + np.abs(np.random.normal(0, 0.005, n))),
        "low": px * (1 - np.abs(np.random.normal(0, 0.005, n))),
        "close": px,
        "volume": (np.random.rand(n) * 1e6 + 1e5).astype(int),
        "value": (np.random.rand(n) * 1e9 + 1e7).astype(int),
    }).reset_index(drop=True)
