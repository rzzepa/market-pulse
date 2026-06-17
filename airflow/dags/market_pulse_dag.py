from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import sys
import os

# dodajemy sciezke do projektu
sys.path.insert(0, '/opt/airflow/project')

default_args = {
    "owner": "market_pulse",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="market_pulse_daily",
    default_args=default_args,
    description="Codzienne zasilanie danych rynkowych",
    schedule="0 18 * * 1-5",   # pon-pt o 18:00
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["market_pulse", "etl"],
) as dag:

    extract_nbp = BashOperator(
        task_id="extract_nbp",
        bash_command="cd /opt/airflow/project && PYTHONPATH=/opt/airflow/project python src/extract_nbp.py --mode daily",
    )

    extract_stocks = BashOperator(
        task_id="extract_stocks",
        bash_command="cd /opt/airflow/project && PYTHONPATH=/opt/airflow/project python src/extract_stocks.py --mode daily",
    )

    gap_check_nbp = BashOperator(
        task_id="gap_check_nbp",
        bash_command="cd /opt/airflow/project && PYTHONPATH=/opt/airflow/project python src/extract_nbp.py --mode gap_check",
    )

    gap_check_stocks = BashOperator(
        task_id="gap_check_stocks",
        bash_command="cd /opt/airflow/project && PYTHONPATH=/opt/airflow/project python src/extract_stocks.py --mode gap_check",
    )

    check_alerts = BashOperator(
        task_id="check_alerts",
        bash_command="cd /opt/airflow/project && PYTHONPATH=/opt/airflow/project python src/check_alerts.py",
    )

    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command="cd /opt/airflow/project/market_pulse_dbt && dbt run --profiles-dir /opt/airflow/dbt_profiles",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="cd /opt/airflow/project/market_pulse_dbt && dbt test --profiles-dir /opt/airflow/dbt_profiles",
    )

    extract_nbp >> gap_check_nbp
    extract_stocks >> gap_check_stocks
    gap_check_nbp >> check_alerts
    gap_check_stocks >> check_alerts
    check_alerts >> run_dbt
    run_dbt >> dbt_test