from decimal import Decimal
from io import BytesIO

import pandas as pd

from app.models import ProductRRP


REQUIRED_COLUMNS = {'vendor_code', 'rrp'}
OPTIONAL_COLUMNS = {'min_price'}


class ExcelFormatError(ValueError):
    pass


def parse_products_excel(content: bytes) -> list[ProductRRP]:
    dataframe = pd.read_excel(BytesIO(content))
    normalized_columns = {column.strip().lower(): column for column in dataframe.columns}

    if not REQUIRED_COLUMNS.issubset(normalized_columns):
        raise ExcelFormatError(
            f'Excel must contain columns: {", ".join(sorted(REQUIRED_COLUMNS | OPTIONAL_COLUMNS))}'
        )

    rows: list[ProductRRP] = []
    for _, row in dataframe.iterrows():
        vendor_code = str(row[normalized_columns['vendor_code']]).strip()
        if not vendor_code or vendor_code.lower() == 'nan':
            continue

        rrp = Decimal(str(row[normalized_columns['rrp']]))
        min_price = None
        if 'min_price' in normalized_columns:
            raw_min_price = row[normalized_columns['min_price']]
            if pd.notna(raw_min_price):
                min_price = Decimal(str(raw_min_price))

        rows.append(ProductRRP(vendor_code=vendor_code, rrp=rrp, min_price=min_price))

    return rows
