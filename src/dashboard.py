import streamlit as st
import pandas as pd
import plotly.graph_objects as go
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
        SELECT date, open, high, low, close, volume
        FROM stock_prices
        WHERE ticker = :ticker
          AND date BETWEEN :start AND :end
        ORDER BY date
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn,
                           params={"ticker": ticker, "start": start, "end": end})


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


# ── SIDEBAR ───────────────────────────────────────────────
st.sidebar.header("Filtry")
widok = st.sidebar.radio("Widok", ["Kursy walut", "Akcje"])

col1, col2 = st.sidebar.columns(2)
with col1:
    start = st.date_input("Od", value=date.today() - timedelta(days=180))
with col2:
    end = st.date_input("Do", value=date.today())

# ── KURSY WALUT ───────────────────────────────────────────
if widok == "Kursy walut":

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

# ── AKCJE ─────────────────────────────────────────────────
else:

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
    df["MA20"] = df["close"].rolling(window=20).mean()
    df["MA50"] = df["close"].rolling(window=50).mean()

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
            y=df["MA20"],
            name="MA20",
            mode="lines",
            line=dict(color="#FFA726", width=1.5, dash="dot"),
        ))

    if ma50:
        fig2.add_trace(go.Scatter(
            x=df.index,
            y=df["MA50"],
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
    st.dataframe(df[["open","high","low","close","volume"]].sort_index(ascending=False).head(30),
                 use_container_width=True)