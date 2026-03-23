import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from app.models import ProductRRP
from app.storage import ProductStorage
from app.yandex_api import YandexMarketClient

logger = logging.getLogger(__name__)


@dataclass
class RepricerService:
    storage: ProductStorage
    yandex_client: YandexMarketClient
    poll_interval_seconds: int
    chunk_size: int

    _task: asyncio.Task | None = None
    _stop_event: asyncio.Event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def sync_once(self) -> int:
        if not self.yandex_client.is_configured:
            logger.warning('Yandex Market client is not configured; skipping sync')
            return 0

        products = await self.storage.list_products()
        if not products:
            return 0

        total_sent = 0
        for chunk in _chunks(products, self.chunk_size):
            payload = [
                {
                    'vendor_code': p.vendor_code,
                    'rrp': p.rrp,
                    'min_price': p.min_price,
                }
                for p in chunk
            ]
            await self.yandex_client.update_prices(payload)
            total_sent += len(payload)

        await self.storage.update_market_prices({p.vendor_code: Decimal(p.rrp) for p in products})
        logger.info('Yandex Market prices synced: %s offers', total_sent)
        return total_sent

    async def refresh_market_prices(self) -> int:
        if not self.yandex_client.is_configured:
            logger.warning('Yandex Market client is not configured; skipping market price refresh')
            return 0

        products = await self.storage.list_products()
        total = 0
        for chunk in _chunks(products, self.chunk_size):
            chunk_codes = [x.vendor_code for x in chunk]
            prices = await self.yandex_client.get_market_prices(chunk_codes)
            await self.storage.update_market_prices(prices)
            total += len(prices)
        return total

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.sync_once()
            except Exception:
                logger.exception('Failed to sync prices with Yandex Market')
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval_seconds)
            except TimeoutError:
                continue


def _chunks(items: list[ProductRRP], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
