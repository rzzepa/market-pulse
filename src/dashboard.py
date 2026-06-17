import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import text
from datetime import date, timedelta
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import get_engine

st.set_page_config(page_title="Market Pulse", layout="wide")
st.title("Market Pulse")

engine = get_engine()


@st.cache_data(ttl=3600)
def get_exchange_rates(waluty: tuple, start, end) -> pd.DataFrame:
    query = text("""
        SELECT date, currency_code, rate
        FROM exchange_rates
        WHERE currency_code = ANY(:waluty)
          AND date BETWEEN :start AND :end
        ORDER BY date
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn,
                           params={"waluty": list(waluty), "start": start, "end": end})


@st.cache_data(ttl=3600)
def get_stock_prices(ticker: str, start, end) -> pd.DataFrame:
    query = text("""
        SELECT
            sp.date,
            sp.open,
            sp.high,
            sp.low,
            sp.close,
            sp.volume,
            fp.ma20,
            fp.ma50
        FROM stock_prices sp
        LEFT JOIN dbt_dev.fct_stock_performance fp
            ON sp.ticker = fp.ticker AND sp.date = fp.price_date
        WHERE sp.ticker = :ticker
          AND sp.date BETWEEN :start AND :end
        ORDER BY sp.date
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn,
                           params={"ticker": ticker, "start": start, "end": end})


@st.cache_data(ttl=3600)
def get_monthly_rates(waluty: tuple) -> pd.DataFrame:
    query = text("""
        SELECT month, currency_code, avg_rate, min_rate, max_rate,
               rate_range, trading_days
        FROM dbt_dev.fct_exchange_rates_monthly
        WHERE currency_code = ANY(:waluty)
        ORDER BY month, currency_code
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"waluty": list(waluty)})


@st.cache_data(ttl=3600)
def get_currencies() -> list:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT DISTINCT currency_code FROM exchange_rates ORDER BY 1")
        )]


@st.cache_data(ttl=3600)
def get_tickers() -> list:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(
            text("SELECT DISTINCT ticker FROM stock_prices ORDER BY 1")
        )]


@st.cache_data(ttl=300)
def get_portfolio_positions() -> pd.DataFrame:
    query = text("""
        SELECT
            pp.ticker,
            pp.currency,
            pp.current_quantity,
            pp.avg_buy_price,
            pp.total_invested_pln,
            pp.realized_profit_pln,
            sp.close as current_price,
            fx.rate as usd_pln_rate
        FROM dbt_dev.fct_portfolio_positions pp
        LEFT JOIN LATERAL (
            SELECT close
            FROM stock_prices
            WHERE ticker = pp.ticker
            ORDER BY date DESC
            LIMIT 1
        ) sp ON true
        LEFT JOIN LATERAL (
            SELECT rate
            FROM exchange_rates
            WHERE currency_code = 'USD'
            ORDER BY date DESC
            LIMIT 1
        ) fx ON true
        ORDER BY pp.ticker
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=300)
def get_portfolio_value_history() -> pd.DataFrame:
    query = text("""
        WITH positions AS (
            SELECT ticker, currency, current_quantity
            FROM dbt_dev.fct_portfolio_positions
        ),
        -- pelny kalendarz dni (nie tylko dni handlowe), zeby kazdy ticker
        -- mial wartosc kazdego dnia, niezaleznie od lokalnych swiat gieldy
        calendar AS (
            SELECT generate_series(
                (SELECT MIN(date) FROM stock_prices WHERE ticker IN (SELECT ticker FROM positions)),
                (SELECT MAX(date) FROM stock_prices WHERE ticker IN (SELECT ticker FROM positions)),
                interval '1 day'
            )::date AS date
        ),
        calendar_positions AS (
            SELECT c.date, p.ticker, p.currency, p.current_quantity
            FROM calendar c
            CROSS JOIN positions p
        ),
        -- as-of join: dla kazdego (data, ticker) bierzemy ostatnia ZNANA cene
        -- (forward-fill) zamiast wymagac dokladnego dopasowania daty
        priced AS (
            SELECT
                cp.date,
                cp.current_quantity,
                cp.currency,
                sp.close AS price,
                fx.rate AS fx_rate
            FROM calendar_positions cp
            LEFT JOIN LATERAL (
                SELECT close
                FROM stock_prices
                WHERE ticker = cp.ticker AND date <= cp.date
                ORDER BY date DESC
                LIMIT 1
            ) sp ON true
            LEFT JOIN LATERAL (
                SELECT rate
                FROM exchange_rates
                WHERE currency_code = 'USD' AND date <= cp.date
                ORDER BY date DESC
                LIMIT 1
            ) fx ON true
        )
        SELECT
            date,
            SUM(
                price * current_quantity *
                CASE WHEN currency = 'PLN' THEN 1 ELSE fx_rate END
            ) AS portfolio_value
        FROM priced
        WHERE price IS NOT NULL
        GROUP BY date
        ORDER BY date
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data(ttl=60)
def get_pipeline_runs(limit: int = 50) -> pd.DataFrame:
    query = text("""
        SELECT pipeline_name, mode, started_at, finished_at, status,
               rows_inserted, error_message,
               EXTRACT(EPOCH FROM (finished_at - started_at)) as duration_sec
        FROM pipeline_runs
        ORDER BY started_at DESC
        LIMIT :limit
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"limit": limit})


@st.cache_data(ttl=60)
def get_pipeline_summary() -> pd.DataFrame:
    query = text("""
        SELECT
            pipeline_name,
            MAX(started_at) FILTER (WHERE status = 'success') as last_success,
            MAX(started_at) as last_run,
            COUNT(*) FILTER (WHERE started_at > now() - interval '30 days') as runs_30d,
            COUNT(*) FILTER (WHERE status = 'success' AND started_at > now() - interval '30 days') as success_30d,
            COUNT(*) FILTER (WHERE status = 'failed' AND started_at > now() - interval '7 days') as failed_7d
        FROM pipeline_runs
        GROUP BY pipeline_name
        ORDER BY pipeline_name
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.header("Filtry")
widok = st.sidebar.radio("Widok", ["Kursy walut", "Analiza miesięczna", "Akcje", "Portfel", "Data Quality"])

# ── KURSY WALUT ───────────────────────────────────────────
if widok == "Kursy walut":

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start = st.date_input("Od", value=date.today() - timedelta(days=180))
    with col2:
        end = st.date_input("Do", value=date.today())

    waluty  = get_currencies()
    wybrane = st.sidebar.multiselect("Waluty", waluty, default=waluty[:2])

    if not wybrane:
        st.warning("Wybierz przynajmniej jedna walute.")
        st.stop()

    df = get_exchange_rates(tuple(wybrane), start, end)

    if df.empty:
        st.warning("Brak danych dla wybranego zakresu.")
        st.stop()

    pivot = df.pivot(index="date", columns="currency_code", values="rate")

    st.subheader(f"Kursy walut ({start} -> {end})")

    fig = go.Figure()
    for waluta in wybrane:
        if waluta in pivot.columns:
            fig.add_trace(go.Scatter(
                x=pivot.index,
                y=pivot[waluta],
                name=waluta,
                mode="lines",
            ))

    fig.update_layout(
        yaxis=dict(tickformat=".4f", autorange=True),
        xaxis=dict(rangeslider=dict(visible=True), type="date"),
        hovermode="x unified",
        height=450,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    cols = st.columns(len(wybrane))
    for i, waluta in enumerate(wybrane):
        if waluta in pivot.columns:
            ostatni   = pivot[waluta].dropna().iloc[-1]
            poprzedni = pivot[waluta].dropna().iloc[-2]
            delta     = ostatni - poprzedni
            cols[i].metric(
                label=f"{waluta}/PLN",
                value=f"{ostatni:.4f}",
                delta=f"{delta:+.4f}"
            )

    st.subheader("Dane tabelaryczne")
    st.dataframe(pivot.sort_index(ascending=False).head(30), use_container_width=True)

# ── ANALIZA MIESIĘCZNA (dbt Gold layer) ───────────────────
elif widok == "Analiza miesięczna":

    waluty  = get_currencies()
    wybrane = st.sidebar.multiselect("Waluty", waluty, default=waluty)

    if not wybrane:
        st.warning("Wybierz przynajmniej jedna walute.")
        st.stop()

    df = get_monthly_rates(tuple(wybrane))

    if df.empty:
        st.warning("Brak danych.")
        st.stop()

    df["month"] = pd.to_datetime(df["month"])

    st.subheader("Sredni kurs miesięczny")
    fig_avg = go.Figure()
    for waluta in wybrane:
        d = df[df["currency_code"] == waluta]
        fig_avg.add_trace(go.Scatter(
            x=d["month"],
            y=d["avg_rate"],
            name=waluta,
            mode="lines+markers",
        ))
    fig_avg.update_layout(
        yaxis=dict(tickformat=".4f", autorange=True),
        xaxis=dict(type="date"),
        hovermode="x unified",
        height=400,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig_avg, use_container_width=True)

    st.subheader("Zmiennosc miesięczna (max - min)")
    fig_vol = go.Figure()
    for waluta in wybrane:
        d = df[df["currency_code"] == waluta]
        fig_vol.add_trace(go.Bar(
            x=d["month"],
            y=d["rate_range"],
            name=waluta,
        ))
    fig_vol.update_layout(
        barmode="group",
        yaxis=dict(tickformat=".4f"),
        hovermode="x unified",
        height=350,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    st.subheader("Szczegoly miesięczne")
    waluta_tab = st.selectbox("Waluta", wybrane)
    d = df[df["currency_code"] == waluta_tab].copy()
    d["month"] = d["month"].dt.strftime("%Y-%m")
    d = d.drop(columns="currency_code").set_index("month")
    d.columns = ["Sredni", "Min", "Max", "Zmiennosc", "Dni handlowe"]
    st.dataframe(d.sort_index(ascending=False), use_container_width=True)

# ── AKCJE ─────────────────────────────────────────────────
elif widok == "Akcje":

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start = st.date_input("Od", value=date.today() - timedelta(days=180))
    with col2:
        end = st.date_input("Do", value=date.today())

    tickery     = get_tickers()
    ticker      = st.sidebar.selectbox("Ticker", tickery)
    ma20        = st.sidebar.checkbox("MA20", value=True)
    ma50        = st.sidebar.checkbox("MA50", value=True)
    typ_wykresu = st.sidebar.radio("Typ wykresu", ["Candlestick", "Linia"])

    df = get_stock_prices(ticker, start, end)

    if df.empty:
        st.warning("Brak danych dla wybranego zakresu.")
        st.stop()

    df = df.set_index("date")

    st.subheader(f"{ticker} ({start} -> {end})")

    fig2 = go.Figure()

    if typ_wykresu == "Candlestick":
        fig2.add_trace(go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=ticker,
            increasing_line_color="#26A69A",
            decreasing_line_color="#EF5350",
        ))
    else:
        fig2.add_trace(go.Scatter(
            x=df.index,
            y=df["close"],
            name="Close",
            mode="lines",
            line=dict(color="#00CC96"),
        ))

    if ma20:
        fig2.add_trace(go.Scatter(
            x=df.index,
            y=df["ma20"],
            name="MA20",
            mode="lines",
            line=dict(color="#FFA726", width=1.5, dash="dot"),
        ))

    if ma50:
        fig2.add_trace(go.Scatter(
            x=df.index,
            y=df["ma50"],
            name="MA50",
            mode="lines",
            line=dict(color="#AB47BC", width=1.5, dash="dash"),
        ))

    fig2.update_layout(
        yaxis=dict(autorange=True, tickformat=".2f"),
        xaxis=dict(rangeslider=dict(visible=False), type="date"),
        hovermode="x unified",
        height=500,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig2, use_container_width=True)

    fig_vol = go.Figure()
    fig_vol.add_trace(go.Bar(
        x=df.index,
        y=df["volume"],
        name="Volume",
        marker_color="#42A5F5",
    ))
    fig_vol.update_layout(
        height=150,
        margin=dict(l=0, r=0, t=0, b=0),
        yaxis=dict(title="Wolumen"),
        showlegend=False,
    )
    st.plotly_chart(fig_vol, use_container_width=True)

    ostatni   = df["close"].iloc[-1]
    poprzedni = df["close"].iloc[-2]
    delta_pct = (ostatni - poprzedni) / poprzedni * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ostatnia cena", f"{ostatni:.2f}",          f"{delta_pct:+.2f}%")
    c2.metric("Max (zakres)",  f"{df['high'].max():.2f}")
    c3.metric("Min (zakres)",  f"{df['low'].min():.2f}")
    c4.metric("Sr. wolumen",   f"{df['volume'].mean():,.0f}")

    st.subheader("Dane tabelaryczne")
    st.dataframe(df[["open","high","low","close","volume","ma20","ma50"]].sort_index(ascending=False).head(30),
                 use_container_width=True)

# ── PORTFEL ───────────────────────────────────────────────
elif widok == "Portfel":

    positions = get_portfolio_positions()

    if positions.empty:
        st.warning("Brak pozycji w portfelu.")
        st.stop()

    positions["current_price"]      = positions["current_price"].astype(float)
    positions["avg_buy_price"]      = positions["avg_buy_price"].astype(float)
    positions["current_quantity"]   = positions["current_quantity"].astype(float)
    positions["total_invested_pln"] = positions["total_invested_pln"].astype(float)
    positions["realized_profit_pln"] = positions["realized_profit_pln"].astype(float)
    positions["usd_pln_rate"]       = positions["usd_pln_rate"].astype(float)

    # aktualna wartosc pozycji przeliczona na PLN po dzisiejszym kursie
    positions["current_value_pln"] = positions.apply(
        lambda r: r["current_price"] * r["current_quantity"] *
                  (1.0 if r["currency"] == "PLN" else r["usd_pln_rate"]),
        axis=1
    )

    positions["unrealized_profit_pln"] = (
        positions["current_value_pln"] - positions["total_invested_pln"]
    )
    positions["unrealized_profit_pct"] = (
        positions["unrealized_profit_pln"] / positions["total_invested_pln"] * 100
    )

    total_invested       = positions["total_invested_pln"].sum()
    total_value           = positions["current_value_pln"].sum()
    total_unrealized       = positions["unrealized_profit_pln"].sum()
    total_realized         = positions["realized_profit_pln"].sum()
    total_unrealized_pct   = (total_unrealized / total_invested * 100) if total_invested else 0

    st.caption("Wszystkie wartosci przeliczone na PLN po aktualnym kursie NBP "
               "(srednia cena zakupu pokazana w walucie oryginalnej instrumentu).")

    st.subheader("Podsumowanie portfela")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Zainwestowano", f"{total_invested:,.0f} PLN")
    c2.metric("Aktualna wartosc", f"{total_value:,.0f} PLN")
    c3.metric("Zysk niezrealizowany", f"{total_unrealized:+,.0f} PLN", f"{total_unrealized_pct:+.1f}%")
    c4.metric("Zysk zrealizowany", f"{total_realized:+,.0f} PLN")

    st.subheader("Pozycje")

    display = positions[[
        "ticker", "currency", "current_quantity", "avg_buy_price", "current_price",
        "current_value_pln", "unrealized_profit_pln", "unrealized_profit_pct", "realized_profit_pln"
    ]].rename(columns={
        "ticker": "Ticker",
        "currency": "Waluta",
        "current_quantity": "Ilosc",
        "avg_buy_price": "Sr. cena zakupu",
        "current_price": "Aktualna cena",
        "current_value_pln": "Wartosc (PLN)",
        "unrealized_profit_pln": "Zysk niezrealizowany (PLN)",
        "unrealized_profit_pct": "Zysk %",
        "realized_profit_pln": "Zysk zrealizowany (PLN)",
    })

    st.dataframe(
        display.style.format({
            "Ilosc": "{:.2f}",
            "Sr. cena zakupu": "{:.2f}",
            "Aktualna cena": "{:.2f}",
            "Wartosc (PLN)": "{:,.2f}",
            "Zysk niezrealizowany (PLN)": "{:+,.2f}",
            "Zysk %": "{:+.1f}%",
            "Zysk zrealizowany (PLN)": "{:+,.2f}",
        }),
        use_container_width=True
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Alokacja portfela")
        fig_pie = go.Figure(data=[go.Pie(
            labels=positions["ticker"],
            values=positions["current_value_pln"],
            hole=0.4,
        )])
        fig_pie.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        st.subheader("Zysk/strata per pozycja (PLN)")
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            x=positions["ticker"],
            y=positions["unrealized_profit_pln"],
            marker_color=["#26A69A" if v >= 0 else "#EF5350" for v in positions["unrealized_profit_pln"]],
        ))
        fig_bar.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="Zysk/strata (PLN)"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("Wartosc portfela w czasie (PLN)")

    history = get_portfolio_value_history()

    if not history.empty:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=history["date"],
            y=history["portfolio_value"],
            mode="lines",
            fill="tozeroy",
            line=dict(color="#26A69A"),
        ))
        fig_hist.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="Wartosc portfela"),
            xaxis=dict(type="date"),
        )
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Brak historii do wyswietlenia.")

# ── DATA QUALITY ──────────────────────────────────────────
else:

    st.subheader("Zdrowie pipeline'u")

    summary = get_pipeline_summary()

    if summary.empty:
        st.warning("Brak zarejestrowanych uruchomien pipeline'u.")
        st.stop()

    now = pd.Timestamp.now()

    cols = st.columns(len(summary))
    for i, row in summary.iterrows():
        ostatni_sukces = row["last_success"]

        if pd.isna(ostatni_sukces):
            cols[i].metric(row["pipeline_name"], "brak danych")
            continue

        godziny_temu = (now - ostatni_sukces).total_seconds() / 3600

        if godziny_temu < 36:
            status_label = f"{godziny_temu:.0f}h temu"
            delta_color = "normal"
        else:
            dni_temu = godziny_temu / 24
            status_label = f"{dni_temu:.0f}d temu"
            delta_color = "inverse"

        wskaznik_sukcesu = (
            row["success_30d"] / row["runs_30d"] * 100
            if row["runs_30d"] > 0 else 0
        )

        cols[i].metric(
            label=row["pipeline_name"],
            value=status_label,
            delta=f"{wskaznik_sukcesu:.0f}% sukcesow (30d)",
            delta_color=delta_color if row["failed_7d"] == 0 else "off",
        )

        if row["failed_7d"] > 0:
            cols[i].caption(f"⚠️ {row['failed_7d']} blad(y) w ostatnich 7 dniach")

    st.subheader("Historia uruchomien")

    runs = get_pipeline_runs(limit=50)

    if runs.empty:
        st.info("Brak historii uruchomien.")
        st.stop()

    runs_display = runs.copy()
    runs_display["started_at"] = pd.to_datetime(runs_display["started_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    runs_display["duration_sec"] = runs_display["duration_sec"].round(2)

    def koloruj_status(status):
        if status == "success":
            return "background-color: #1b3a1f"
        elif status == "failed":
            return "background-color: #4a1414"
        else:
            return "background-color: #4a3a14"

    styled = runs_display[[
        "pipeline_name", "mode", "started_at", "status",
        "duration_sec", "rows_inserted", "error_message"
    ]].rename(columns={
        "pipeline_name": "Pipeline",
        "mode": "Tryb",
        "started_at": "Start",
        "status": "Status",
        "duration_sec": "Czas (s)",
        "rows_inserted": "Rekordy",
        "error_message": "Blad",
    }).style.map(koloruj_status, subset=["Status"])

    st.dataframe(styled, use_container_width=True, height=600)

    st.subheader("Wskaznik sukcesu w czasie")

    runs_chart = runs.copy()
    runs_chart["started_at"] = pd.to_datetime(runs_chart["started_at"])
    runs_chart["dzien"] = runs_chart["started_at"].dt.date
    runs_chart["sukces"] = (runs_chart["status"] == "success").astype(int)

    daily_rate = runs_chart.groupby(["dzien", "pipeline_name"])["sukces"].mean().reset_index()
    daily_rate["sukces_pct"] = daily_rate["sukces"] * 100

    fig_dq = go.Figure()
    for pname in daily_rate["pipeline_name"].unique():
        d = daily_rate[daily_rate["pipeline_name"] == pname]
        fig_dq.add_trace(go.Scatter(
            x=d["dzien"],
            y=d["sukces_pct"],
            name=pname,
            mode="lines+markers",
        ))

    fig_dq.update_layout(
        yaxis=dict(title="% sukcesow", range=[0, 105]),
        xaxis=dict(title="Dzien"),
        hovermode="x unified",
        height=350,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig_dq, use_container_width=True)