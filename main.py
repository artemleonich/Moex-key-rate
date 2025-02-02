# -*- coding: utf-8 -*-
"""
Исследование влияния ключевой ставки ЦБ на российские акции.
IMOEX, RTS, топ-30 бумаг — SARIMAX, VAR, Грейнджер, бэктесты.
"""

import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import grangercausalitytests
from statsmodels.stats.diagnostic import breaks_cusumolsresid

from config import *
from fetcher import fetch_cbr_keyrate, keyrate_frequencies, fetch_moex_candles, fetch_moex_index
from synthetic import make_keyrate, make_index, make_stock
from backtest import log_returns, event_signal, hold_signal, vol_size, apply_costs, perf_stats


def _plot(df, title, path):
    plt.figure(figsize=(12, 5))
    for c in df.columns:
        plt.plot(df.index, df[c], label=c)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def run():
    idx_prices = {}
    idx_ret = {}
    stk_close = {}
    stk_ret = {}

    if USE_SYNTHETIC:
        print("Используем синтетические данные")
        keyrate = make_keyrate()
        keyrate.to_csv(RAW_DIR / "cbr_key_rate_daily.csv", index=False)
        print(f"Ставка: {len(keyrate)} строк, {keyrate['date'].min().date()} — {keyrate['date'].max().date()}")

        kr_freq = keyrate_frequencies(keyrate)
        kr_freq["monthly"].to_csv(RAW_DIR / "cbr_key_rate_monthly.csv")
        kr_freq["quarterly"].to_csv(RAW_DIR / "cbr_key_rate_quarterly.csv")

        for name in INDEX_SECIDS:
            df = make_index(name, keyrate)
            df.to_csv(RAW_DIR / f"moex_index_{name}_close.csv", index=False)
            idx_prices[name] = df
            idx_ret[name] = log_returns(df).rename(name)
            print(f"  {name}: {len(df)} строк")

        imoex_lr = idx_ret["IMOEX"]
        for t in TOP30:
            df = make_stock(t, keyrate, imoex_lr)
            df.to_csv(RAW_DIR / f"moex_{t}_candles_daily.csv", index=False)
            stk_close[t] = df[["date", "close"]].copy()
            stk_ret[t] = log_returns(df).rename(t)
            print(f"  {t}: {len(df)} строк")
    else:
        print("Загрузка данных ЦБ...")
        keyrate = fetch_cbr_keyrate(CBR_FROM, CBR_TO)
        keyrate.to_csv(RAW_DIR / "cbr_key_rate_daily.csv", index=False)

        kr_freq = keyrate_frequencies(keyrate)
        kr_freq["monthly"].to_csv(RAW_DIR / "cbr_key_rate_monthly.csv")
        kr_freq["quarterly"].to_csv(RAW_DIR / "cbr_key_rate_quarterly.csv")

        from_ymd = keyrate["date"].min().strftime("%Y-%m-%d")
        to_ymd = min(keyrate["date"].max(), pd.Timestamp.today()).strftime("%Y-%m-%d")
        print(f"Период: {from_ymd} — {to_ymd}")

        print("Загрузка индексов...")
        for name, secid in INDEX_SECIDS.items():
            try:
                df = fetch_moex_index(secid, from_ymd, to_ymd)
                if df.empty:
                    print(f"  [!] Нет данных по {name}")
                    continue
                df.to_csv(RAW_DIR / f"moex_index_{secid}_close.csv", index=False)
                idx_prices[name] = df
                idx_ret[name] = log_returns(df).rename(name)
                print(f"  {name}: {len(df)} строк")
            except Exception as e:
                print(f"  [ошибка] {name}: {e}")

        if "IMOEX" not in idx_ret:
            raise RuntimeError("IMOEX обязателен для анализа")

        print("Загрузка акций...")
        for t in TOP30:
            try:
                df = fetch_moex_candles("stock", "shares", SHARES_BOARD, t,
                                        from_ymd, to_ymd, CANDLE_INTERVAL, PAGE_LIMIT)
                if df.empty:
                    print(f"  [!] Нет свечей для {t}")
                    continue
                df.to_csv(RAW_DIR / f"moex_{t}_candles_daily.csv", index=False)
                stk_close[t] = df[["date", "close"]].copy()
                stk_ret[t] = log_returns(df).rename(t)
                print(f"  {t}: {len(df)} строк")
            except Exception as e:
                print(f"  [ошибка] {t}: {e}")

    # собираем панель IMOEX + ставка
    imoex_r = idx_ret["IMOEX"].copy()
    rate_d = keyrate.set_index("date")["key_rate"].rename("key_rate").sort_index()
    panel = pd.concat([imoex_r, rate_d], axis=1).dropna()
    panel["key_rate_delta"] = panel["key_rate"].diff().fillna(0)
    panel.to_csv(OUT_DIR / "panel_imoex_keyrate_daily.csv")

    # описательная статистика
    print("\n--- Описательная статистика ---")
    desc = panel[["IMOEX", "key_rate", "key_rate_delta"]].describe()
    desc.to_csv(OUT_DIR / "desc_imoex_keyrate.csv")
    print(desc)

    # графики
    cum = pd.DataFrame({"IMOEX_cum": (1 + panel["IMOEX"].fillna(0)).cumprod()}, index=panel.index)
    _plot(pd.DataFrame({"key_rate": panel["key_rate"]}), "Ключевая ставка ЦБ, %", OUT_DIR / "key_rate_daily.png")
    _plot(cum, "IMOEX кумулятивно", OUT_DIR / "imoex_cum.png")

    # лаг-корреляция
    print("\n--- Лаг-корреляция (IMOEX vs Δ ставки) ---")
    max_lag = 30
    x, y = panel["key_rate_delta"], panel["IMOEX"]
    lc = [(lag, y.corr(x.shift(lag)) if lag >= 0 else y.shift(-lag).corr(x))
          for lag in range(-max_lag, max_lag + 1)]
    lc_df = pd.DataFrame(lc, columns=["lag_days", "corr"])
    lc_df.to_csv(OUT_DIR / "lag_correlation_imoex_vs_keyrate_delta.csv", index=False)

    plt.figure(figsize=(12, 4))
    plt.plot(lc_df["lag_days"], lc_df["corr"])
    plt.title("Лаг-корреляция: доходность IMOEX vs Δ ставки")
    plt.axhline(0, lw=0.8)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "lag_correlation.png", dpi=160)
    plt.close()

    # SARIMAX
    print("\n--- ARIMAX ---")
    endog = panel["IMOEX"].astype(float)
    exog = panel[["key_rate", "key_rate_delta"]].astype(float)
    mdl = SARIMAX(endog, exog=exog, order=(1, 0, 1), trend="c", enforce_stationarity=False)
    fit = mdl.fit(disp=False)
    with open(OUT_DIR / "sarimax_summary.txt", "w") as f:
        f.write(str(fit.summary()))
    print(fit.summary())

    # CUSUM
    print("\n--- CUSUM тест ---")
    resid = fit.resid.dropna()
    cusum = breaks_cusumolsresid(resid, ddof=int(fit.df_model) if hasattr(fit, "df_model") else 1)
    cusum_txt = f"CUSUM stat: {cusum[0]}\np-value: {cusum[1]}\n"
    with open(OUT_DIR / "cusum_test.txt", "w") as f:
        f.write(cusum_txt)
    print(cusum_txt)

    # VAR + Granger
    print("\n--- VAR + Грейнджер ---")
    var_df = panel[["IMOEX", "key_rate_delta"]].dropna()
    var_m = VAR(var_df)
    var_fit = var_m.fit(maxlags=10, ic="aic")
    with open(OUT_DIR / "var_summary.txt", "w") as f:
        f.write(str(var_fit.summary()))
    print(str(var_fit.summary())[:2000])

    gc = grangercausalitytests(var_df[["IMOEX", "key_rate_delta"]].dropna(), maxlag=10, verbose=False)
    gc_rows = [(lag, v[0]["ssr_ftest"][1]) for lag, v in gc.items()]
    gc_df = pd.DataFrame(gc_rows, columns=["lag", "pvalue"])
    gc_df.to_csv(OUT_DIR / "granger_pvalues.csv", index=False)
    print("\nГрейнджер p-values (Δставки -> IMOEX):")
    print(gc_df.to_string(index=False))

    # бэктесты
    print("\n--- Бэктест ---")
    imoex_simple = np.expm1(panel["IMOEX"]).rename("IMOEX_simple")
    ev_sig = event_signal(keyrate, min_bp=MIN_BP).reindex(panel.index).fillna(0)

    price_imoex = idx_prices["IMOEX"].set_index("date")["close"].reindex(panel.index).ffill()
    ma = price_imoex.rolling(MA_WINDOW).mean()
    vol20 = imoex_simple.rolling(VOL_WINDOW).std()
    vol_med = vol20.expanding().median()

    results = []

    for hd in HOLD_DAYS:
        # A: только событие
        pos_a = vol_size(hold_signal(ev_sig, hd), imoex_simple)
        ret_a = apply_costs(pos_a, imoex_simple)
        st_a = perf_stats(ret_a)
        st_a.update({"strategy": f"A_event_h{hd}", "hold_days": hd})
        results.append(st_a)

        # B: событие + режимный фильтр
        filt = (price_imoex > ma) & (vol20 > vol_med)
        pos_b = vol_size(hold_signal(ev_sig, hd) * filt.astype(float), imoex_simple)
        ret_b = apply_costs(pos_b, imoex_simple)
        st_b = perf_stats(ret_b)
        st_b.update({"strategy": f"B_regime_h{hd}", "hold_days": hd})
        results.append(st_b)

    # C: cross-section спрэд (экспортёры vs внутренние)
    exp_tickers = ["GAZP", "LKOH", "ROSN", "NVTK", "GMKN", "PLZL", "ALRS", "SIBN", "SNGS"]
    dom_tickers = ["SBER", "VTBR", "MTSS", "PIKK", "SMLT", "MOEX", "RTKM"]

    def _basket(tickers):
        rs = [stk_ret[t] for t in tickers if t in stk_ret]
        if not rs:
            return pd.Series(dtype=float)
        return np.expm1(pd.concat(rs, axis=1).dropna(how="all")).mean(axis=1)

    exp_r = _basket(exp_tickers)
    dom_r = _basket(dom_tickers)

    if not exp_r.empty and not dom_r.empty:
        cs = pd.concat([exp_r.rename("exp"), dom_r.rename("dom")], axis=1).reindex(panel.index).dropna()
        spread = (cs["exp"] - cs["dom"]).rename("spread")
        sig_c = (-ev_sig).reindex(spread.index).fillna(0)

        for hd in HOLD_DAYS:
            pos_c = hold_signal(sig_c, hd)
            ret_c = apply_costs(pos_c, spread)
            st_c = perf_stats(ret_c)
            st_c.update({"strategy": f"C_spread_h{hd}", "hold_days": hd})
            results.append(st_c)

            crv = (1 + ret_c.fillna(0)).cumprod()
            plt.figure(figsize=(12, 4))
            plt.plot(crv.index, crv.values)
            plt.title(f"Стратегия C (спрэд), hold={hd}")
            plt.tight_layout()
            plt.savefig(OUT_DIR / f"curve_C_spread_h{hd}.png", dpi=160)
            plt.close()

    strat_df = pd.DataFrame(results).sort_values(["sharpe", "cagr"], ascending=False)
    strat_df.to_csv(OUT_DIR / "strategy_comparison.csv", index=False)
    print("\n--- Сравнение стратегий ---")
    print(strat_df.to_string(index=False))

    # кривые доходности лучших стратегий
    top5 = strat_df.head(5)["strategy"].tolist()
    curves = {}
    for nm in top5:
        if nm.startswith("A_") or nm.startswith("B_"):
            hd = int(nm.split("h")[-1])
            if nm.startswith("A_"):
                p = vol_size(hold_signal(ev_sig, hd), imoex_simple)
            else:
                filt = (price_imoex > ma) & (vol20 > vol_med)
                p = vol_size(hold_signal(ev_sig, hd) * filt.astype(float), imoex_simple)
            curves[nm] = (1 + apply_costs(p, imoex_simple).fillna(0)).cumprod()

    if curves:
        plt.figure(figsize=(12, 5))
        for nm, crv in curves.items():
            plt.plot(crv.index, crv.values, label=nm)
        plt.title("Кривые лучших стратегий (за вычетом комиссий)")
        plt.legend()
        plt.tight_layout()
        plt.savefig(OUT_DIR / "top_strategies.png", dpi=160)
        plt.close()

    print(f"\nГотово. Результаты: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    run()
