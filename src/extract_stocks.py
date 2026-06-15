import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG, TICKERS
from src.extract_nbp import get_engine


def fetch_stock(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Sciaga ceny akcji przez yfinance."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)

        if df.empty:
            print(f"  Brak danych dla {ticker}")
            return pd.DataFrame()

        # yfinance zwraca MultiIndex na kolumnach - splaszczamy
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

        df["date"]   = pd.to_datetime(df["date"]).dt.date
        df["ticker"] = ticker

        # waluta: GPW to PLN, reszta USD
        df["currency"] = "PLN" if ticker.endswith(".WA") else "USD"

        cols = ["date", "ticker", "open", "high", "low", "close", "volume", "adj_close", "currency"]
        existing = [c for c in cols if c in df.columns]
        return df[existing]

    except Exception as e:
        print(f"  Blad dla {ticker}: {e}")
        return pd.DataFrame()


def load_to_db(df: pd.DataFrame, engine) -> int:
    """Laduje dane akcji do bazy, pomija duplikaty."""
    if df.empty:
        return 0

    rows = df.to_dict(orient="records")
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


def run(start: date, end: date):
    engine = get_engine()
    print(f"Zakres dat: {start} → {end}")
    print()

    # splaszczamy slownik tickerow w jedna liste
    all_tickers = [t for group in TICKERS.values() for t in group]
    total = 0

    for ticker in all_tickers:
        print(f"Pobieram {ticker}...")
        df = fetch_stock(ticker, start, end)
        inserted = load_to_db(df, engine)
        print(f"  Wrzucono {inserted} rekordow")
        total += inserted

    print(f"\nGotowe. Lacznie wrzucono: {total} rekordow.")


if __name__ == "__main__":
    end   = date.today()
    start = end - timedelta(days=365)
    run(start, end)