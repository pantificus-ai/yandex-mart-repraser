from io import BytesIO

import pandas as pd

from app.excel_import import parse_products_excel


def test_parse_products_excel_success():
    df = pd.DataFrame(
        [
            {'vendor_code': 'sku-1', 'rrp': 100.5, 'min_price': 90},
            {'vendor_code': 'sku-2', 'rrp': 200},
        ]
    )
    stream = BytesIO()
    df.to_excel(stream, index=False)

    products = parse_products_excel(stream.getvalue())

    assert len(products) == 2
    assert products[0].vendor_code == 'sku-1'
    assert float(products[0].rrp) == 100.5
    assert float(products[0].min_price) == 90.0
