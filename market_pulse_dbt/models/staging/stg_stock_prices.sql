with source as (

    select
        date,
        ticker,
        open,
        high,
        low,
        close,
        volume,
        adj_close,
        currency
    from {{ source('market_pulse', 'stock_prices') }}

),

renamed as (

    select
        date                            as price_date,
        ticker,
        open                            as open_price,
        high                            as high_price,
        low                             as low_price,
        close                           as close_price,
        adj_close                       as adj_close_price,
        volume,
        currency,
        current_timestamp               as _loaded_at
    from source

)

select * from renamed