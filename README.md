<h1 align="center">Moex-key-rate</h1>

<p align="center">
  <a href=".github/assets/light/stack.svg#gh-light-mode-only"><img src=".github/assets/light/stack.svg" height="28" alt="Python · Time Series · Research" /></a><a href=".github/assets/stack.svg#gh-dark-mode-only"><img src=".github/assets/stack.svg" height="28" alt="Python · Time Series · Research" /></a>
</p>

Исследование связи ключевой ставки Банка России с российскими акциями: данные, статистические модели и событийные бэктесты в одном Python-скрипте.

[Запуск](#запуск) · [Настройки](#настройки) · [English](#english)

## Возможности

- Загрузка истории ключевой ставки с сайта Банка России и дневных данных IMOEX, RTS и заданного списка из 30 акций через MOEX ISS.
- Дневные, месячные и квартальные признаки ставки; лаговые корреляции в окне ±30 дней.
- SARIMAX, VAR, тесты Грейнджера и CUSUM.
- Три семейства стратегий: реакция на изменение ставки, реакция с фильтром тренда и волатильности, спред экспортёров и внутренних компаний.
- Периоды удержания 1, 3, 5 и 10 дней; комиссии, проскальзывание и стоимость заимствования для коротких позиций.
- Отдельный синтетический режим для запуска без сети.
- Выгрузка таблиц CSV, описаний моделей TXT и графиков PNG.

Проект предназначен для исследования. В синтетическом режиме чувствительность цен к ставке задаётся генератором; результаты такого запуска описывают симуляцию.

## Запуск

Нужен **Python 3.10+**.

```bash
git clone https://github.com/artemleonich/Moex-key-rate.git
cd Moex-key-rate
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install lxml

# Данные Банка России и MOEX ISS — режим по умолчанию
python cbr_moex_study.py

# Синтетические данные, без сетевой загрузки
python cbr_moex_study.py --synthetic
```

В Windows используйте `.venv\Scripts\activate` для активации окружения. `lxml` нужен для разбора HTML-таблиц Банка России через `pandas.read_html`; он пока не включён в `requirements.txt`.

Скрипт создаёт `cbr_moex_rate_study/raw/` для исходных данных и `cbr_moex_rate_study/output/` для результатов. Повторный запуск обновляет файлы с теми же именами. Фиксируйте выбранный режим и настройки вместе с результатами.

## Как устроено исследование

1. Собирает данные и выравнивает доходности IMOEX с дневной ставкой по доступным датам.
2. Считает описательную статистику и лаговые корреляции.
3. Оценивает SARIMAX и проверяет стабильность остатков через CUSUM.
4. Строит VAR и тесты Грейнджера.
5. Сравнивает стратегии после учёта заданных издержек.

| Семейство | Логика эксперимента |
| --- | --- |
| A · Event | Long при снижении ставки, short при повышении |
| B · Event + regime | Та же событийная логика с фильтром MA и волатильности |
| C · Cross-sectional spread | Спред равновзвешенных корзин экспортёров и внутренних компаний |

Отсутствующая история отдельных акций пропускается. Семейство C рассчитывается при наличии данных для обеих корзин.

## Настройки

Параметры находятся в начале [cbr_moex_study.py](cbr_moex_study.py).

| Параметр | Значение по умолчанию | Назначение |
| --- | --- | --- |
| `USE_SYNTHETIC` | `False` | Реальные источники; `--synthetic` включает симуляцию |
| `CBR_FROM_DDMMYYYY` | `17.09.2013` | Начало окна; конец задаётся текущей датой |
| `HOLD_DAYS_LIST` | `[1, 3, 5, 10]` | Периоды удержания |
| `MIN_BP_MOVE` | `50` | Минимальное изменение ставки, базисные пункты |
| `MA_TREND_WINDOW` | `200` | Окно трендового фильтра |
| `VOL_TARGET_ANNUAL` | `0.10` | Целевая волатильность для A и B |
| `MAX_LEVERAGE` | `2.0` | Ограничение размера позиции |
| `COMMISSION_HALF_TURN` | `0.0005` | Комиссия за сторону, 0,05% |
| `SLIPPAGE_HALF_TURN` | `0.0002` | Проскальзывание за сторону, 0,02% |
| `SHORT_BORROW_ANNUAL` | `0.08` | Годовая стоимость заимствования, 8% |

Издержки и правила — допущения эксперимента. При интерпретации статистики нужно учитывать период, доступность данных и выбор спецификаций моделей.

## Результаты и структура

```text
cbr_moex_study.py                  # сбор, анализ и бэктесты
requirements.txt                  # основные зависимости
cbr_moex_rate_study/
├── raw/                          # исходные данные, исключены из Git
└── output/
    ├── panel_imoex_keyrate_daily.csv
    ├── lag_correlation_imoex_vs_keyrate_delta.csv
    ├── granger_pvalues_keyrate_to_imoex.csv
    ├── strategy_comparison.csv
    ├── sarimax_summary.txt
    ├── var_summary.txt
    ├── cusum_test.txt
    └── *.png                     # ставка, доходности и кривые стратегий
LICENSE
```

Стек: **pandas / numpy** для расчётов, **requests / lxml** для загрузки и разбора данных, **statsmodels** для моделей, **matplotlib** для графиков.

## English

A research pipeline for the CBR key rate and Russian equities, including IMOEX / RTS data, a configurable 30-stock universe, lag correlations, SARIMAX, VAR, Granger tests, CUSUM and three event-based strategy families.

Install `requirements.txt` plus `lxml`, then run `python cbr_moex_study.py` for real CBR / MOEX ISS data or add `--synthetic` for offline simulation. The current default is `USE_SYNTHETIC = False`.

Outputs are written to `cbr_moex_rate_study/output/`. Keep the data mode and assumptions with each run; synthetic price responses to rate changes are built into the generator.

## Лицензия / License

[MIT](LICENSE).

