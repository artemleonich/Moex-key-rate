# 📈 Moex-key-rate

**CBR key rate vs Russian equities — full reproducible strategy study & analysis**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## 📋 Overview

This project investigates the relationship between the **Central Bank of Russia (CBR) key interest rate** and **Russian equity markets** — including the IMOEX and RTS indices, as well as a universe of 30 large-cap stocks traded on the Moscow Exchange.

The study is a single self-contained Python script that handles everything end-to-end: data acquisition from official sources (cbr.ru and MOEX ISS), statistical analysis (lag correlations, SARIMAX, VAR, Granger causality, CUSUM structural stability tests), and systematic backtesting of multiple trading strategies with realistic transaction costs.

---

## ✨ Features

- **Automated data collection** from CBR (key rate history) and MOEX ISS (index and stock candles) with retry logic and pagination
- **Synthetic data mode** for running the full pipeline offline when network access is unavailable
- **Multi-frequency key rate analysis** — daily, monthly, and quarterly aggregations with level, average, and delta features
- **Statistical modeling** — SARIMAX, VAR, Granger causality tests, and CUSUM structural break detection
- **Lag correlation analysis** between IMOEX returns and key rate changes (up to ±30 days)
- **Three backtested strategies** with configurable holding periods (1, 3, 5, 10 days):
  - **Strategy A** — Event-driven: go long on rate cuts, short on rate hikes
  - **Strategy B** — Event-driven with regime filters (200-day MA trend + volatility)
  - **Strategy C** — Cross-sectional spread: exporters vs domestic stocks on rate events
- **Realistic cost model** — commissions, slippage, and short borrow costs
- **Volatility-targeted position sizing** with configurable leverage cap
- **Automated chart generation** and CSV/TXT output for all results

---

## 📂 Project Structure

```
Moex-key-rate/
├── cbr_moex_study.py              # Main script (data + analysis + backtest)
├── cbr_moex_rate_study/
│   ├── raw/                       # Downloaded raw data (git-ignored)
│   └── output/                    # Analysis results & charts
│       ├── key_rate_daily.png
│       ├── imoex_cum.png
│       ├── lag_correlation.png
│       ├── top_strategies_curves.png
│       ├── curve_C_spread_hold*.png
│       ├── sarimax_summary.txt
│       ├── var_summary.txt
│       ├── cusum_test.txt
│       ├── granger_pvalues_keyrate_to_imoex.csv
│       ├── strategy_comparison.csv
│       └── ...
└── .gitignore
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+

### Installation

```bash
git clone https://github.com/artemleonich/Moex-key-rate.git
cd Moex-key-rate
pip install pandas numpy requests lxml matplotlib statsmodels scipy
```

Optional (for Excel export):

```bash
pip install openpyxl
```

### Running the Study

```bash
python cbr_moex_study.py
```

By default the script runs in **synthetic data mode** (`USE_SYNTHETIC = True`), which generates realistic simulated data so you can explore the full pipeline without network access. To fetch live data from CBR and MOEX, set `USE_SYNTHETIC = False` in the script.

All outputs (charts, CSVs, model summaries) are saved to `cbr_moex_rate_study/output/`.

---

## ⚙️ Configuration

Key parameters at the top of `cbr_moex_study.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `USE_SYNTHETIC` | `True` | Use generated data instead of live API calls |
| `CBR_FROM_DDMMYYYY` | `17.09.2013` | Analysis start date |
| `HOLD_DAYS_LIST` | `[1, 3, 5, 10]` | Holding periods to backtest |
| `MIN_BP_MOVE` | `50` | Minimum rate change (bps) to trigger a trade |
| `MA_TREND_WINDOW` | `200` | Moving average window for trend filter |
| `VOL_TARGET_ANNUAL` | `0.10` | Annualized volatility target (10%) |
| `MAX_LEVERAGE` | `2.0` | Maximum allowed leverage |
| `COMMISSION_HALF_TURN` | `0.0005` | Commission per side (0.05%) |
| `SLIPPAGE_HALF_TURN` | `0.0002` | Slippage per side (0.02%) |
| `SHORT_BORROW_ANNUAL` | `0.08` | Annual short borrow cost (8%) |

---

## 📊 Analysis Pipeline

1. **Data acquisition** — CBR key rate history + MOEX indices (IMOEX, RTS) + top-30 stock candles
2. **Feature engineering** — multi-frequency key rate features, log returns, aligned daily panel
3. **Descriptive statistics** — summary stats for returns and rate changes
4. **Lag correlation** — cross-correlation between IMOEX returns and rate deltas (±30 day window)
5. **SARIMAX modeling** — IMOEX returns regressed on key rate level and delta
6. **Structural stability** — CUSUM test on model residuals
7. **VAR + Granger causality** — tests whether rate changes Granger-cause equity returns
8. **Strategy backtesting** — event-driven, regime-filtered, and cross-sectional strategies with full cost accounting

---

## 🛠️ Tech Stack

- **pandas** / **numpy** — data manipulation
- **requests** / **lxml** — web scraping & API calls
- **matplotlib** — visualization
- **statsmodels** — SARIMAX, VAR, Granger causality, CUSUM
- **scipy** — statistical functions

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).
