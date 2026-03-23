from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProductRRP(Base):
    __tablename__ = 'product_rrp'

    vendor_code: Mapped[str] = mapped_column(String(120), primary_key=True)
    rrp: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
