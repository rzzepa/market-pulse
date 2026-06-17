{{
    config(
        materialized='table'
    )
}}

with ticker_currency as (

    -- waluta tickera bierzemy z istniejacego zrodla prawdy (stock_prices),
    -- zamiast duplikowac logike ".WA = PLN" w drugim miejscu
    select distinct ticker, currency
    from {{ source('market_pulse', 'stock_prices') }}

),

transactions as (

    select
        t.ticker,
        t.transaction_type,
        t.quantity,
        t.price,
        t.transaction_date,
        coalesce(tc.currency, 'USD') as currency
    from {{ source('market_pulse', 'portfolio_transactions') }} t
    left join ticker_currency tc on tc.ticker = t.ticker

),

-- dla kazdej transakcji w USD znajdujemy najblizszy dostepny kurs
-- NBP nie publikuje kursow w weekendy/swieta, wiec szukamy <= data transakcji
transactions_pln as (

    select
        t.*,
        case
            when t.currency = 'PLN' then t.price
            else t.price * fx.rate
        end as price_pln
    from transactions t
    left join lateral (
        select rate
        from {{ source('market_pulse', 'exchange_rates') }}
        where currency_code = 'USD'
          and date <= t.transaction_date
        order by date desc
        limit 1
    ) fx on true

),

valued as (

    select
        *,
        quantity * price_pln as transaction_value_pln
    from transactions_pln

),

buys as (

    select
        ticker,
        currency,
        sum(quantity)                  as total_bought,
        sum(price * quantity)          as total_cost_original,
        sum(transaction_value_pln)     as total_cost_pln
    from valued
    where transaction_type = 'buy'
    group by ticker, currency

),

sells as (

    select
        ticker,
        sum(quantity)                  as total_sold,
        sum(transaction_value_pln)     as total_sell_value_pln
    from valued
    where transaction_type = 'sell'
    group by ticker

),

positions as (

    select
        b.ticker,
        b.currency,
        b.total_bought,
        coalesce(s.total_sold, 0)                              as total_sold,
        b.total_bought - coalesce(s.total_sold, 0)              as current_quantity,
        -- sr. cena zakupu w WALUCIE ORYGINALNEJ (do porownania z cena rynkowa)
        round((b.total_cost_original / b.total_bought)::numeric, 4) as avg_buy_price,
        -- kwoty pieniezne w PLN (do agregacji portfela w jednej walucie)
        round(b.total_cost_pln::numeric, 2)                    as total_invested_pln,
        round(coalesce(s.total_sell_value_pln, 0)::numeric, 2) as realized_sell_value_pln,
        round((
            coalesce(s.total_sell_value_pln, 0) -
            (coalesce(s.total_sold, 0) * (b.total_cost_pln / b.total_bought))
        )::numeric, 2)                                          as realized_profit_pln
    from buys b
    left join sells s on b.ticker = s.ticker

)

select * from positions
where current_quantity > 0
order by ticker