import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text
import argparse
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TICKERS
from src.db import get_engine
from src.pipeline_logger import log_run


def fetch_stock(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Sciaga ceny akcji przez yfinance."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)

        if df.empty:
            print(f"  Brak danych dla {ticker}")
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0].lower().replace(" ", "_") for col in df.columns]
        else:
            df.columns = [col.lower().replace(" ", "_") for col in df.columns]

        df = df.reset_index()
        df = df.rename(columns={
            "Date":      "date",
            "Open":      "open",
            "High":      "high",
            "Low":       "low",
            "Close":     "close",
            "Volume":    "volume",
            "Adj Close": "adj_close",
            "date":      "date",
        })

        df["date"]     = pd.to_datetime(df["date"]).dt.date
        df["ticker"]   = ticker
        df["currency"] = "PLN" if ticker.endswith(".WA") else "USD"

        cols     = ["date", "ticker", "open", "high", "low", "close", "volume", "adj_close", "currency"]
        existing = [c for c in cols if c in df.columns]
        return df[existing]

    except Exception as e:
        print(f"  Blad dla {ticker}: {e}")
        return pd.DataFrame()


def load_to_db(df: pd.DataFrame, engine) -> int:
    """Laduje dane akcji do bazy, pomija duplikaty."""
    if df.empty:
        return 0

    rows  = df.to_dict(orient="records")
    query = text("""
        INSERT INTO stock_prices
            (date, ticker, open, high, low, close, volume, adj_close, currency)
        VALUES
            (:date, :ticker, :open, :high, :low, :close, :volume, :adj_close, :currency)
        ON CONFLICT (date, ticker) DO NOTHING
    """)

    with engine.begin() as conn:
        result = conn.execute(query, rows)
        return result.rowcount


def get_last_date_stock(ticker: str, engine) -> date:
    """Zwraca ostatnia date w bazie dla danego tickera.
    Jak brak danych - zwraca 365 dni temu."""
    query = text("""
        SELECT MAX(date) FROM stock_prices
        WHERE ticker = :ticker
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"ticker": ticker}).scalar()

    if result is None:
        return date.today() - timedelta(days=365)
    return result


def get_gaps_stock(ticker: str, engine) -> list:
    import holidays as hl

    query = text("""
        SELECT date FROM stock_prices
        WHERE ticker = :ticker
        ORDER BY date
    """)
    with engine.connect() as conn:
        daty_w_bazie = set(r[0] for r in conn.execute(query, {"ticker": ticker}))

    if not daty_w_bazie:
        return []

    start = min(daty_w_bazie)
    end   = max(daty_w_bazie)

    # swieta dla US (NYSE) i PL (GPW)
    us_holidays = hl.US(years=range(start.year, end.year + 1))
    pl_holidays = hl.Poland(years=range(start.year, end.year + 1))

    wszystkie_dni_robocze = set(
        d for d in pd.date_range(start, end, freq="B").date
    )

    def is_holiday(d, ticker):
        if ticker.endswith(".WA"):
            return d in pl_holidays
        return d in us_holidays

    luki = sorted(
        d for d in wszystkie_dni_robocze - daty_w_bazie
        if not is_holiday(d, ticker)
    )
    return luki


def fill_gaps_stock(ticker: str, engine) -> int:
    """Wypelnia luki w danych dla danego tickera."""
    from itertools import groupby
    from operator import itemgetter

    luki = get_gaps_stock(ticker, engine)
    if not luki:
        print(f"  {ticker}: brak luk")
        return 0

    zakresy = []
    for k, g in groupby(enumerate(luki), lambda x: x[0] - (x[1] - luki[0]).days):
        grupa = list(map(itemgetter(1), g))
        zakresy.append((grupa[0], grupa[-1]))

    inserted = 0
    for start, end in zakresy:
        print(f"  Wypelniam luke {start} -> {end}...")
        df = fetch_stock(ticker, start, end)
        inserted += load_to_db(df, engine)

    return inserted


def run(mode: str = "daily", history_start: date = None):
    """
    Tryby:
    - initial   : pobiera historie od history_start do dzis
    - daily     : pobiera od ostatniej daty w bazie do dzis
    - gap_check : sprawdza i wypelnia luki
    """
    engine     = get_engine()
    all_tickers = [t for group in TICKERS.values() for t in group]

    with log_run("extract_stocks", mode, engine) as pipeline_run:
        print(f"Tryb: {mode}")
        print(f"Tickery: {all_tickers}")
        print()

        total = 0

        for ticker in all_tickers:
            print(f"--- {ticker} ---")

            if mode == "initial":
                start = history_start or date(2020, 1, 1)
                end   = date.today()
                print(f"  Pobieram historie od {start}...")
                df = fetch_stock(ticker, start, end)
                inserted = load_to_db(df, engine)
                print(f"  Wrzucono {inserted} rekordow")

            elif mode == "daily":
                last_date = get_last_date_stock(ticker, engine)
                start     = last_date + timedelta(days=1)
                end       = date.today()

                if start > end:
                    print(f"  Aktualne, nic do pobrania")
                    inserted = 0
                else:
                    print(f"  Pobieram {start} -> {end}...")
                    df = fetch_stock(ticker, start, end)
                    inserted = load_to_db(df, engine)
                    print(f"  Wrzucono {inserted} rekordow")

            elif mode == "gap_check":
                inserted = fill_gaps_stock(ticker, engine)
                print(f"  Wypelniono {inserted} rekordow")

            else:
                print(f"  Nieznany tryb: {mode}")
                inserted = 0

            total += inserted

        pipeline_run["rows_inserted"] = total
        print(f"\nGotowe. Lacznie: {total} rekordow.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Pulse - Stocks extractor")
    parser.add_argument(
        "--mode",
        choices=["initial", "daily", "gap_check"],
        default="daily",
        help="Tryb dzialania: initial/daily/gap_check"
    )
    parser.add_argument(
        "--from",
        dest="history_start",
        type=date.fromisoformat,
        default=date(2020, 1, 1),
        help="Data poczatkowa dla trybu initial (YYYY-MM-DD)"
    )
    args = parser.parse_args()
    run(mode=args.mode, history_start=args.history_start)