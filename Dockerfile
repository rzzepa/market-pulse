# baza: oficjalny obraz Python 3.13, wersja slim (mniejsza, bez zbednych pakietow)
FROM python:3.13-slim

# folder roboczy wewnątrz kontenera
WORKDIR /app

# kopiujemy requirements i instalujemy PRZED kodem
# (warstwa cache - jak kod sie zmieni ale requirements nie, Docker nie reinstaluje)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# kopiujemy reszte projektu
COPY . .

# domyslna komenda - mozna nadpisac przy uruchomieniu
CMD ["python", "run_daily.py"]