import subprocess
import sys
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, f"run_{datetime.now().strftime('%Y%m%d')}.log")

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_script(script: str, mode: str):
    log(f"Start: {script} --mode {mode}")
    try:
        result = subprocess.run(
            [sys.executable, script, "--mode", mode],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=300
        )
        if result.stdout:
            log(result.stdout.strip())
        if result.stderr:
            log(f"STDERR: {result.stderr.strip()}")
        log(f"Koniec: {script} (kod: {result.returncode})")
        return result.returncode

    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: {script} przekroczyl 5 minut - przerywam")
        return -1


if __name__ == "__main__":
    from datetime import datetime
    import holidays as hl

    dzisiaj = datetime.today().date()
    pl_holidays = hl.Poland(years=dzisiaj.year)
    us_holidays = hl.US(years=dzisiaj.year)

    if dzisiaj in pl_holidays and dzisiaj in us_holidays:
        log(f"Swieto PL i US ({dzisiaj}) - pomijam")
    elif dzisiaj in pl_holidays:
        log(f"Swieto PL ({dzisiaj}) - pomijam NBP, lece stocks")
        run_script("src/extract_stocks.py", "daily")
        run_script("src/extract_stocks.py", "gap_check")
    elif dzisiaj in us_holidays:
        log(f"Swieto US ({dzisiaj}) - pomijam stocks, lece NBP")
        run_script("src/extract_nbp.py", "daily")
        run_script("src/extract_nbp.py", "gap_check")
    else:
        log("=== Market Pulse daily run ===")
        run_script("src/extract_nbp.py",    "daily")
        run_script("src/extract_stocks.py", "daily")
        run_script("src/extract_nbp.py",    "gap_check")
        run_script("src/extract_stocks.py", "gap_check")
        log("=== Koniec ===")