import pandas as pd
from datetime import datetime
from sqlalchemy import text
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import get_engine
from src.pipeline_logger import log_run


def get_active_rules(engine) -> pd.DataFrame:
    """Pobiera aktywne reguly alertow."""
    query = text("""
        SELECT id, ticker, condition_type, threshold, last_triggered_at
        FROM alert_rules
        WHERE is_active = true
        ORDER BY ticker
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def get_latest_price(ticker: str, engine):
    """Zwraca najnowsza cene zamkniecia dla tickera."""
    query = text("""
        SELECT close, date
        FROM stock_prices
        WHERE ticker = :ticker
        ORDER BY date DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"ticker": ticker}).fetchone()
    return result if result else (None, None)


def condition_met(condition_type: str, price: float, threshold: float) -> bool:
    if condition_type == "above":
        return price > threshold
    elif condition_type == "below":
        return price < threshold
    return False


def mark_triggered(rule_id: int, engine):
    """Zapisuje ze alert zostal wlasnie odpalony - zapobiega spamowi."""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE alert_rules
            SET last_triggered_at = :now
            WHERE id = :id
        """), {"now": datetime.now(), "id": rule_id})


def reset_if_condition_no_longer_met(rule_id: int, engine):
    """
    Jak warunek juz nie jest spelniony, zerujemy last_triggered_at.
    Dzieki temu alert moze odpalic sie ZNOWU jak warunek wroci
    (np. cena spadla pod prog, wrocila powyzej, znowu spadla).
    """
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE alert_rules
            SET last_triggered_at = NULL
            WHERE id = :id
        """), {"id": rule_id})


def notify(ticker: str, condition_type: str, threshold: float, price: float, price_date):
    """
    Powiadomienie na terminal (kanal docelowy do podmiany na e-mail/Slack
    w przyszlosci - logika alertow zostaje identyczna, zmienia sie tylko
    ta jedna funkcja).
    """
    strzalka = "ponizej" if condition_type == "below" else "powyzej"
    print(f"  🔔 ALERT: {ticker} jest {strzalka} progu {threshold} "
          f"(aktualna cena: {price} z dnia {price_date})")


def run():
    engine = get_engine()

    with log_run("check_alerts", "daily", engine) as pipeline_run:
        print("Sprawdzam reguly alertow...")
        print()

        rules = get_active_rules(engine)

        if rules.empty:
            print("Brak aktywnych regul.")
            pipeline_run["rows_inserted"] = 0
            return

        triggered_count = 0

        for _, rule in rules.iterrows():
            price, price_date = get_latest_price(rule["ticker"], engine)

            if price is None:
                print(f"  {rule['ticker']}: brak danych cenowych - pomijam")
                continue

            price = float(price)
            threshold = float(rule["threshold"])
            spelniony = condition_met(rule["condition_type"], price, threshold)

            if spelniony:
                if rule["last_triggered_at"] is None:
                    # nowe wystapienie warunku - powiadamiamy
                    notify(rule["ticker"], rule["condition_type"], threshold, price, price_date)
                    mark_triggered(rule["id"], engine)
                    triggered_count += 1
                else:
                    # warunek wciaz spelniony, ale juz powiadomiono - cisza
                    print(f"  {rule['ticker']}: warunek wciaz aktywny "
                          f"(juz powiadomiono {rule['last_triggered_at']})")
            else:
                # warunek nie jest spelniony - jak byl wczesniej oznaczony,
                # resetujemy zeby alert mogl znowu zadzialac w przyszlosci
                if rule["last_triggered_at"] is not None:
                    reset_if_condition_no_longer_met(rule["id"], engine)
                print(f"  {rule['ticker']}: OK ({price} vs prog {threshold} {rule['condition_type']})")

        pipeline_run["rows_inserted"] = triggered_count
        print(f"\nGotowe. Nowych alertow: {triggered_count}.")


if __name__ == "__main__":
    run()