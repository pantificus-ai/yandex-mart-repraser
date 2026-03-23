from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductIn(BaseModel):
    vendor_code: str = Field(min_length=1, max_length=120)
    rrp: Decimal = Field(gt=0)
    min_price: Decimal | None = Field(default=None, gt=0)


class ProductOut(ProductIn):
    market_price: Decimal | None = None
    updated_at: datetime


class ImportResult(BaseModel):
    inserted_or_updated: int
