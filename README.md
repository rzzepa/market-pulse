# Market Pulse

Financial data pipeline with PostgreSQL dashboard.

## Stack
- **Python** (pandas, requests, SQLAlchemy)
- **PostgreSQL** — data storage
- **Streamlit + Plotly** — interactive dashboard
- **Sources:** NBP API (exchange rates), yfinance (stocks)

## Features
- Daily exchange rates: EUR, USD, GBP, CHF (NBP API)
- Stock prices: CDR.WA, PKN.WA, PKO.WA, SPY, QQQ, AAPL, NVDA
- Interactive dashboard with date range filters
- Duplicate-safe loading (ON CONFLICT DO NOTHING)

## Setup
1. Clone repo and create virtual environment:
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt

2. Create .env file:
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=market_pulse_db
   DB_USER=postgres
   DB_PASSWORD=your_password

3. Run pipelines:
   python src/extract_nbp.py
   python src/extract_stocks.py

4. Launch dashboard:
   streamlit run src/dashboard.py

## Roadmap
- [ ] News scraping with AI analysis
- [ ] dbt transformations
- [ ] Airflow orchestration
- [ ] Docker setup