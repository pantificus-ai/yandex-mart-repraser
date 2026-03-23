# Yandex Market Repricer

Сервис для удержания РРЦ (рекомендованной розничной цены) в магазине на Яндекс Маркете через Partner API + простой веб-интерфейс для оператора.

## Что реализовано

- Фоновый синк цен по расписанию (`poll_interval_seconds`).
- Ручной запуск синка (`POST /sync-now`).
- Обновление текущих цен с Яндекса (`POST /refresh-market-prices`).
- CRUD по товарам с РРЦ (`/products`).
- Импорт списка артикулов и цен из Excel (`POST /products/import`).
- Выгрузка списка товаров и цен в Excel (`GET /products/export`).
- Веб-интерфейс (`GET /`) с:
  - таблицей товаров,
  - колонками РРЦ, текущей цены на Яндексе и даты обновления,
  - поиском и фильтрами,
  - редактированием цены для одного артикула,
  - импортом/экспортом Excel.

## Архитектура (эффективно и правильно)

1. **Источник истины по РРЦ** — таблица `product_rrp`.
2. **Удержание РРЦ** — периодическая отправка эталонных цен в API Маркета.
3. **Видимость фактической цены** — отдельный запрос к API для обновления `market_price`.
4. **Операционное управление** — UI + API + массовый Excel импорт/экспорт.
5. **Готовность к росту** — можно заменить SQLite на PostgreSQL через `DATABASE_URL`.

## Формат Excel для импорта

Обязательные колонки:
- `vendor_code` — артикул.
- `rrp` — РРЦ.

Опциональная колонка:
- `min_price` — минимальная цена.

## Настройки (`.env`)

```dotenv
APP_HOST=0.0.0.0
APP_PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./repricer.db

YANDEX_API_BASE_URL=https://api.partner.market.yandex.ru
YANDEX_API_TOKEN=<oauth token>
YANDEX_BUSINESS_ID=<business id>
YANDEX_CAMPAIGN_ID=<campaign id>
YANDEX_PRICE_UPDATE_PATH=/businesses/{business_id}/offer-prices/updates
YANDEX_OFFER_INFO_PATH=/businesses/{business_id}/offer-mappings

POLL_INTERVAL_SECONDS=300
CHUNK_SIZE=200
```

> Пути API вынесены в конфиг, чтобы гибко адаптировать под актуальную документацию:
> https://yandex.ru/dev/market/partner-api/doc/ru/

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- UI: `http://localhost:8000/`
- Swagger: `http://localhost:8000/docs`

## Рекомендации для production

- Добавить retry/backoff на 429/5xx.
- Ограничить скорость вызовов по rate limit API Маркета.
- Добавить аудит изменений цен и метрики (Prometheus).
- Добавить авторизацию в веб-интерфейс.
