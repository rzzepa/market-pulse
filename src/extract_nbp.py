import requests
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import create_engine, text
import sys
import os

# dodajemy glowny folder do sciezki zeby config.py byl widoczny
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG, CURRENCIES


def get_engine():
    """Tworzy polaczenie z baza przez SQLAlchemy."""
    url = (
        f"postgresql+psycopg2://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)


def fetch_rates(currency: str, start: date, end: date) -> pd.DataFrame:
    """Sciaga kursy NBP dla jednej waluty i zakresu dat."""
    url = (
        f"https://api.nbp.pl/api/exchangerates/rates/a/{currency}/"
        f"{start}/{end}/?format=json"
    )
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data["rates"])
        df = df.rename(columns={"effectiveDate": "date", "mid": "rate"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["currency_code"] = currency.upper()
        df["source"] = "NBP"
        return df[["date", "currency_code", "rate", "source"]]

    elif response.status_code == 404:
        print(f"  Brak danych: {currency} {start}→{end}")
        return pd.DataFrame()

    else:
        print(f"  Blad {response.status_code}: {currency} {start}→{end}")
        return pd.DataFrame()


def load_to_db(df: pd.DataFrame, engine) -> int:
    """Laduje DataFrame do tabeli exchange_rates.
    Pomija duplikaty dzieki ON CONFLICT DO NOTHING."""
    if df.empty:
        return 0

    rows = df.to_dict(orient="records")
    query = text("""
        INSERT INTO exchange_rates (date, currency_code, rate, source)
        VALUES (:date, :currency_code, :rate, :source)
        ON CONFLICT (date, currency_code) DO NOTHING
    """)

    with engine.begin() as conn:
        result = conn.execute(query, rows)
        return result.rowcount


def run(start: date, end: date):
    """Glowna funkcja: sciaga kursy dla wszystkich walut i laduje do bazy."""
    engine = get_engine()
    print(f"Laczenie z baza: {DB_CONFIG['database']}")
    print(f"Zakres dat: {start} → {end}")
    print(f"Waluty: {CURRENCIES}")
    print()

    total = 0
    for currency in CURRENCIES:
        print(f"Pobieram {currency}...")
        df = fetch_rates(currency, start, end)
        inserted = load_to_db(df, engine)
        print(f"  Wrzucono {inserted} rekordow (pominięto duplikaty)")
        total += inserted

    print(f"\nGotowe. Lacznie wrzucono: {total} rekordow.")


if __name__ == "__main__":
    # domyslnie: ostatnie 365 dni
    end = date.today()
    start = end - timedelta(days=365)
    run(start, end)