{{
    config(
        materialized='table'
    )
}}

with daily as (

    select
        price_date,
        ticker,
        close_price,
        volume
    from {{ ref('stg_stock_prices') }}

),

with_changes as (

    select
        price_date,
        ticker,
        close_price,
        volume,
        lag(close_price) over (
            partition by ticker
            order by price_date
        )                                       as prev_close,
        avg(close_price) over (
            partition by ticker
            order by price_date
            rows between 19 preceding and current row
        )                                       as ma20,
        avg(close_price) over (
            partition by ticker
            order by price_date
            rows between 49 preceding and current row
        )                                       as ma50
    from daily

),

final as (

    select
        price_date,
        ticker,
        round(close_price::numeric, 4)          as close_price,
        round(prev_close::numeric, 4)           as prev_close,
        round(
            ((close_price - prev_close) / prev_close * 100)::numeric, 2
        )                                       as daily_change_pct,
        round(ma20::numeric, 4)                 as ma20,
        round(ma50::numeric, 4)                 as ma50,
        volume
    from with_changes

)

select * from final
order by price_date, ticker