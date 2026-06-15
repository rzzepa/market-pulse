import requests
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import text
from itertools import groupby
from operator import itemgetter
import argparse
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CURRENCIES
from src.db import get_engine


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
        print(f"  Brak danych: {currency} {start} -> {end}")
        return pd.DataFrame()

    else:
        print(f"  Blad {response.status_code}: {currency} {start} -> {end}")
        return pd.DataFrame()


def load_to_db(df: pd.DataFrame, engine) -> int:
    """Laduje DataFrame do tabeli exchange_rates. Pomija duplikaty."""
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


def get_last_date(currency: str, engine) -> date:
    """Zwraca ostatnia date w bazie dla danej waluty.
    Jak brak danych - zwraca 365 dni temu (pierwsze uruchomienie)."""
    query = text("""
        SELECT MAX(date) FROM exchange_rates
        WHERE currency_code = :currency
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"currency": currency}).scalar()

    if result is None:
        return date.today() - timedelta(days=365)
    return result


def get_gaps(currency: str, engine) -> list:
    """Znajduje luki w danych - dni robocze bez notowania."""
    query = text("""
        SELECT date FROM exchange_rates
        WHERE currency_code = :currency
        ORDER BY date
    """)
    with engine.connect() as conn:
        daty_w_bazie = set(r[0] for r in conn.execute(query, {"currency": currency}))

    if not daty_w_bazie:
        return []

    start = min(daty_w_bazie)
    end   = max(daty_w_bazie)

    wszystkie_dni_robocze = set(
        d for d in pd.date_range(start, end, freq="B").date
    )

    luki = sorted(wszystkie_dni_robocze - daty_w_bazie)
    return luki


def fill_gaps(currency: str, engine) -> int:
    """Wypelnia luki w danych."""
    luki = get_gaps(currency, engine)
    if not luki:
        print(f"  {currency}: brak luk")
        return 0

    zakresy = []
    for k, g in groupby(enumerate(luki), lambda x: x[0] - (x[1] - luki[0]).days):
        grupa = list(map(itemgetter(1), g))
        zakresy.append((grupa[0], grupa[-1]))

    inserted = 0
    for start, end in zakresy:
        print(f"  Wypelniam luke {start} -> {end}...")
        df = fetch_rates(currency, start, end)
        inserted += load_to_db(df, engine)

    return inserted


def run(mode: str = "daily", history_start: date = None):
    """
    Tryby:
    - initial   : pobiera historie od history_start do dzis
    - daily     : pobiera od ostatniej daty w bazie do dzis
    - gap_check : sprawdza i wypelnia luki
    """
    engine = get_engine()
    print(f"Tryb: {mode}")
    print(f"Waluty: {CURRENCIES}")
    print()

    total = 0

    for currency in CURRENCIES:
        print(f"--- {currency} ---")

        if mode == "initial":
            start = history_start or date(2020, 1, 1)
            end   = date.today()
            print(f"  Pobieram historie od {start}...")
            df = fetch_rates(currency, start, end)
            inserted = load_to_db(df, engine)
            print(f"  Wrzucono {inserted} rekordow")

        elif mode == "daily":
            last_date = get_last_date(currency, engine)
            start = last_date + timedelta(days=1)
            end   = date.today()

            if start > end:
                print(f"  Aktualne, nic do pobrania")
                inserted = 0
            else:
                print(f"  Pobieram {start} -> {end}...")
                df = fetch_rates(currency, start, end)
                inserted = load_to_db(df, engine)
                print(f"  Wrzucono {inserted} rekordow")

        elif mode == "gap_check":
            inserted = fill_gaps(currency, engine)
            print(f"  Wypelniono {inserted} rekordow")

        else:
            print(f"  Nieznany tryb: {mode}")
            inserted = 0

        total += inserted

    print(f"\nGotowe. Lacznie: {total} rekordow.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Market Pulse - NBP extractor")
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