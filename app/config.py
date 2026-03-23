from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    app_host: str = '0.0.0.0'
    app_port: int = 8000

    database_url: str = 'sqlite+aiosqlite:///./repricer.db'

    yandex_api_base_url: str = 'https://api.partner.market.yandex.ru'
    yandex_api_token: str = Field(default='', description='OAuth token from Yandex Market Partner API')
    yandex_business_id: int = 0
    yandex_campaign_id: int = 0
    yandex_price_update_path: str = '/businesses/{business_id}/offer-prices/updates'
    yandex_offer_info_path: str = '/v2/businesses/{business_id}/offer-mappings'
    yandex_offer_prices_path: str = '/v2/businesses/{business_id}/offer-prices'

    poll_interval_seconds: int = 300
    chunk_size: int = 200


settings = Settings()
