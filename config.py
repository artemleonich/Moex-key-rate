from pathlib import Path
from datetime import date

DATA_DIR = Path("cbr_moex_rate_study")
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "output"

RAW_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

CBR_FROM = "17.09.2013"
CBR_TO = date.today().strftime("%d.%m.%Y")

INDEX_SECIDS = {
    "IMOEX": "IMOEX",
    "RTS": "RTSI",
}

TOP30 = [
    "SBER", "SBERP", "GAZP", "LKOH", "ROSN", "NVTK", "SIBN", "GMKN", "PLZL", "ALRS",
    "TATN", "SNGS", "SNGSP", "NLMK", "CHMF", "MAGN", "PHOR", "MTSS", "RTKM", "TRNFP",
    "MOEX", "VTBR", "IRAO", "HYDR", "UPRO", "PIKK", "SMLT", "OZON", "X5", "YDEX",
]

SHARES_BOARD = "TQBR"
INDEX_BOARD = "SNDX"
CANDLE_INTERVAL = 24
PAGE_LIMIT = 500

# торговые расходы
COMMISSION = 0.0005  # 5 бп на сторону
SLIPPAGE = 0.0002
SHORT_BORROW_PA = 0.08
TRADING_DAYS = 252

VOL_TARGET = 0.10
MAX_LEVERAGE = 2.0

HOLD_DAYS = [1, 3, 5, 10]
MIN_BP = 50  # мин. изменение ставки для сигнала (бп)

MA_WINDOW = 200
VOL_WINDOW = 20
VOL_PCTL = 0.5

USE_SYNTHETIC = True
