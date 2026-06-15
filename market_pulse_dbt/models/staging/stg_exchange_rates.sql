with source as (

    select
        date,
        currency_code,
        rate,
        source
    from {{ source('market_pulse', 'exchange_rates') }}

),

renamed as (

    select
        date                            as rate_date,
        currency_code,
        rate                            as rate_pln,
        source                          as data_source,
        current_timestamp               as _loaded_at
    from source

)

select * from renamed