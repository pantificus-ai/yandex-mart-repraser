from decimal import Decimal

import pytest

from app.models import ProductRRP
from app.repricer import RepricerService


class FakeStorage:
    def __init__(self):
        self.updated = {}

    async def list_products(self):
        return [
            ProductRRP(vendor_code='a', rrp=Decimal('10.00'), min_price=None),
            ProductRRP(vendor_code='b', rrp=Decimal('20.00'), min_price=None),
            ProductRRP(vendor_code='c', rrp=Decimal('30.00'), min_price=None),
        ]

    async def update_market_prices(self, prices_by_vendor_code):
        self.updated = prices_by_vendor_code


class FakeYandexClient:
    def __init__(self):
        self.calls = []

    async def update_prices(self, items):
        self.calls.append(items)


@pytest.mark.asyncio
async def test_sync_once_chunks_requests():
    storage = FakeStorage()
    client = FakeYandexClient()
    service = RepricerService(
        storage=storage,
        yandex_client=client,
        poll_interval_seconds=1,
        chunk_size=2,
    )

    synced = await service.sync_once()

    assert synced == 3
    assert len(client.calls) == 2
    assert len(client.calls[0]) == 2
    assert len(client.calls[1]) == 1
    assert storage.updated == {'a': Decimal('10.00'), 'b': Decimal('20.00'), 'c': Decimal('30.00')}
