from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, ProductRRP


class ProductStorage:
    def __init__(self, database_url: str):
        self._engine = create_async_engine(database_url, future=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            columns = {row[1] for row in (await conn.execute(text('PRAGMA table_info(product_rrp)'))).all()}
            if 'market_price' not in columns:
                await conn.execute(text('ALTER TABLE product_rrp ADD COLUMN market_price NUMERIC(10,2)'))
            if 'updated_at' not in columns:
                await conn.execute(text('ALTER TABLE product_rrp ADD COLUMN updated_at DATETIME'))
            await conn.execute(text("UPDATE product_rrp SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))

    async def list_products(self) -> list[ProductRRP]:
        async with self._session_factory() as session:
            result = await session.execute(select(ProductRRP).order_by(ProductRRP.vendor_code))
            return list(result.scalars().all())

    async def upsert_products(self, records: Iterable[ProductRRP]) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            for record in records:
                await self._upsert(session, record, now)
            await session.commit()

    async def _upsert(self, session: AsyncSession, record: ProductRRP, now: datetime) -> None:
        existing = await session.get(ProductRRP, record.vendor_code)
        if existing is None:
            if record.updated_at is None:
                record.updated_at = now
            session.add(record)
            return
        existing.rrp = Decimal(record.rrp)
        existing.min_price = Decimal(record.min_price) if record.min_price is not None else None
        if record.market_price is not None:
            existing.market_price = Decimal(record.market_price)
        existing.updated_at = now

    async def update_market_prices(self, prices_by_vendor_code: dict[str, Decimal | None]) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            for vendor_code, market_price in prices_by_vendor_code.items():
                row = await session.get(ProductRRP, vendor_code)
                if row is None:
                    continue
                row.market_price = Decimal(market_price) if market_price is not None else None
                row.updated_at = now
            await session.commit()

    async def delete(self, vendor_code: str) -> bool:
        async with self._session_factory() as session:
            item = await session.get(ProductRRP, vendor_code)
            if item is None:
                return False
            await session.delete(item)
            await session.commit()
            return True
