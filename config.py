# config.py - NIE wrzucaj haseł tutaj, tylko strukturę
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

DB_CONFIG = {
    "host":     os.getenv("DB_HOST_DOCKER", os.getenv("DB_HOST", "localhost")),
    "port":     os.getenv("DB_PORT", "5432"),
    "database": os.getenv("DB_NAME", "market_pulse_db"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# instrumenty do sledzenia
CURRENCIES = ["EUR", "USD", "GBP", "CHF"]

TICKERS = {
    "polska":   ["CDR.WA", "PKN.WA", "PKO.WA"],
    "globalne": ["SPY", "QQQ", "AAPL", "NVDA"],
}