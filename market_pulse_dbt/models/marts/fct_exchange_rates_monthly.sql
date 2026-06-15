{{
    config(
        materialized='table'
    )
}}

with daily_rates as (

    select
        rate_date,
        currency_code,
        rate_pln
    from {{ ref('stg_exchange_rates') }}

),

monthly as (

    select
        date_trunc('month', rate_date)::date    as month,
        currency_code,
        round(avg(rate_pln)::numeric, 4)        as avg_rate,
        round(min(rate_pln)::numeric, 4)        as min_rate,
        round(max(rate_pln)::numeric, 4)        as max_rate,
        round((max(rate_pln) - min(rate_pln))::numeric, 4) as rate_range,
        count(*)                                as trading_days
    from daily_rates
    group by 1, 2

)

select * from monthly
order by month, currency_code