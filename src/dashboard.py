import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import text
from datetime import date, timedelta
import sys, os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.extract_nbp import get_engine

st.set_page_config(page_title="Market Pulse", layout="wide")
st.title("Market Pulse")

engine = get_engine()

st.sidebar.header("Filtry")
widok = st.sidebar.radio("Widok", ["Kursy walut", "Akcje"])

col1, col2 = st.sidebar.columns(2)
with col1:
    start = st.date_input("Od", value=date.today() - timedelta(days=90))
with col2:
    end = st.date_input("Do", value=date.today())

# ── KURSY WALUT ───────────────────────────────────────────
if widok == "Kursy walut":

    with engine.connect() as conn:
        waluty = [r[0] for r in conn.execute(
            text("SELECT DISTINCT currency_code FROM exchange_rates ORDER BY 1")
        )]

    wybrane = st.sidebar.multiselect("Waluty", waluty, default=waluty[:2])

    if not wybrane:
        st.warning("Wybierz przynajmniej jedna walute.")
        st.stop()

    query = text("""
        SELECT date, currency_code, rate
        FROM exchange_rates
        WHERE currency_code = ANY(:waluty)
          AND date BETWEEN :start AND :end
        ORDER BY date
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn,
                         params={"waluty": wybrane, "start": start, "end": end})

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
            delta = ostatni - poprzedni
            cols[i].metric(
                label=f"{waluta}/PLN",
                value=f"{ostatni:.4f}",
                delta=f"{delta:+.4f}"
            )

    st.subheader("Dane tabelaryczne")
    st.dataframe(pivot.sort_index(ascending=False).head(30), use_container_width=True)

# ── AKCJE ─────────────────────────────────────────────────
else:

    with engine.connect() as conn:
        tickery = [r[0] for r in conn.execute(
            text("SELECT DISTINCT ticker FROM stock_prices ORDER BY 1")
        )]

    ticker = st.sidebar.selectbox("Ticker", tickery)

    query = text("""
        SELECT date, open, high, low, close, volume
        FROM stock_prices
        WHERE ticker = :ticker
          AND date BETWEEN :start AND :end
        ORDER BY date
    """)

    with engine.connect() as conn:
        df = pd.read_sql(query, conn,
                         params={"ticker": ticker, "start": start, "end": end})

    if df.empty:
        st.warning("Brak danych dla wybranego zakresu.")
        st.stop()

    df = df.set_index("date")

    st.subheader(f"{ticker} -- cena zamkniecia ({start} -> {end})")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df.index,
        y=df["close"],
        name="Close",
        mode="lines",
        line=dict(color="#00CC96"),
    ))
    fig2.update_layout(
        yaxis=dict(autorange=True, tickformat=".2f"),
        xaxis=dict(rangeslider=dict(visible=True), type="date"),
        hovermode="x unified",
        height=450,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig2, use_container_width=True)

    ostatni   = df["close"].iloc[-1]
    poprzedni = df["close"].iloc[-2]
    delta_pct = (ostatni - poprzedni) / poprzedni * 100

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ostatnia cena", f"{ostatni:.2f}",  f"{delta_pct:+.2f}%")
    c2.metric("Max (zakres)",  f"{df['high'].max():.2f}")
    c3.metric("Min (zakres)",  f"{df['low'].min():.2f}")
    c4.metric("Sr. wolumen",   f"{df['volume'].mean():,.0f}")

    st.subheader("Dane tabelaryczne")
    st.dataframe(df.sort_index(ascending=False).head(30), use_container_width=True)