from datetime import datetime
from sqlalchemy import text
from contextlib import contextmanager


@contextmanager
def log_run(pipeline_name: str, mode: str, engine):
    """
    Context manager do logowania uruchomien pipeline'u.
    Uzycie:
        with log_run("extract_nbp", "daily", engine) as run:
            ... kod pipeline'u ...
            run["rows_inserted"] = 123
    """
    started_at = datetime.now()
    run_data = {"rows_inserted": 0}

    # zapisujemy start
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO pipeline_runs (pipeline_name, mode, started_at, status)
            VALUES (:name, :mode, :started, 'running')
            RETURNING id
        """), {"name": pipeline_name, "mode": mode, "started": started_at})
        run_id = result.scalar()

    error_message = None
    status = "success"

    try:
        yield run_data
    except Exception as e:
        status = "failed"
        error_message = str(e)[:500]
        raise
    finally:
        finished_at = datetime.now()
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE pipeline_runs
                SET finished_at = :finished,
                    status = :status,
                    rows_inserted = :rows,
                    error_message = :error
                WHERE id = :run_id
            """), {
                "finished": finished_at,
                "status": status,
                "rows": run_data["rows_inserted"],
                "error": error_message,
                "run_id": run_id
            })