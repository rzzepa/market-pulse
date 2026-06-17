FROM apache/airflow:2.9.0
USER airflow
RUN pip install --no-cache-dir \
    "dbt-postgres==1.9.0" \
    "yfinance" \
    "pandas" \
    "holidays" \
    "sqlalchemy" \
    "psycopg2-binary" \
    "click==8.1.7"