from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from app.config import settings
from app.excel_import import ExcelFormatError, parse_products_excel
from app.models import ProductRRP
from app.repricer import RepricerService
from app.schemas import ImportResult, ProductIn, ProductOut
from app.storage import ProductStorage
from app.yandex_api import YandexMarketClient, YandexMarketConfigurationError

storage = ProductStorage(settings.database_url)
yandex_client = YandexMarketClient(
    base_url=settings.yandex_api_base_url,
    token=settings.yandex_api_token,
    business_id=settings.yandex_business_id,
    campaign_id=settings.yandex_campaign_id,
    price_update_path=settings.yandex_price_update_path,
    offer_info_path=settings.yandex_offer_info_path,
    offer_prices_path=settings.yandex_offer_prices_path,
)
repricer = RepricerService(
    storage=storage,
    yandex_client=yandex_client,
    poll_interval_seconds=settings.poll_interval_seconds,
    chunk_size=settings.chunk_size,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.init()
    await repricer.start()
    yield
    await repricer.stop()
    await yandex_client.close()


app = FastAPI(title='Yandex Market Repricer', lifespan=lifespan)


def _to_schema(item: ProductRRP) -> ProductOut:
    return ProductOut(
        vendor_code=item.vendor_code,
        rrp=Decimal(item.rrp),
        min_price=item.min_price,
        market_price=item.market_price,
        updated_at=item.updated_at,
    )


def _product_matches(
    item: ProductRRP,
    query: str,
    rrp_min: Decimal | None,
    rrp_max: Decimal | None,
    market_min: Decimal | None,
    market_max: Decimal | None,
) -> bool:
    if query and query.lower() not in item.vendor_code.lower():
        return False
    if rrp_min is not None and Decimal(item.rrp) < rrp_min:
        return False
    if rrp_max is not None and Decimal(item.rrp) > rrp_max:
        return False
    if market_min is not None and (item.market_price is None or Decimal(item.market_price) < market_min):
        return False
    if market_max is not None and (item.market_price is None or Decimal(item.market_price) > market_max):
        return False
    return True


def _excel_response(dataframe: pd.DataFrame, filename: str) -> StreamingResponse:
    stream = BytesIO()
    dataframe.to_excel(stream, index=False)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@app.get('/', response_class=HTMLResponse)
async def web_ui() -> str:
    return """
<!doctype html>
<html lang='ru'>
<head>
<meta charset='utf-8' />
<meta name='viewport' content='width=device-width, initial-scale=1' />
<title>Yandex Market Repricer</title>
<style>
body{font-family:Arial,sans-serif;padding:20px;background:#f5f7fa;color:#111}
.container{max-width:1280px;margin:0 auto}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:14px}
table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;vertical-align:top}
input,button,.button-link{padding:8px;border:1px solid #bbb;border-radius:6px}
button,.button-link{cursor:pointer;background:#111;color:#fff;text-decoration:none;display:inline-flex;align-items:center}
.button-link.api-export{background:#0b6b3a;border-color:#0b6b3a}
.actions{display:flex;gap:8px;flex-wrap:wrap}.filters{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:8px}
.small{font-size:12px;color:#666}
.hint{margin-top:8px;color:#555}
</style>
</head>
<body>
<div class='container'>
<h1>Репрайсер Яндекс Маркет</h1>
<div class='card'>
<div class='actions'>
<button onclick='syncNow()'>Синхронизировать РРЦ сейчас</button>
<button onclick='refreshMarket()'>Обновить текущие цены с Яндекса</button>
<button onclick='downloadExcel()'>Выгрузить локальный Excel</button>
<input type='file' id='excelFile' accept='.xlsx,.xls' />
<button onclick='uploadExcel()'>Загрузить Excel</button>
</div>
<p class='small' id='status'>Готово</p>
</div>
<div class='card'>
<h3>Экспорт данных</h3>
<div class='actions'>
<a class='button-link' href='/products/export'>Скачать локальный Excel</a>
<a class='button-link api-export' href='/products/export/yandex-api'>Выгрузить товары и цены по API</a>
</div>
<p class='small hint'>API-выгрузка делает прямой запрос в Yandex Market Partner API и скачивает отдельный Excel с актуальными товарами и ценами.</p>
</div>
<div class='card'>
<div class='filters'>
<input id='q' placeholder='Поиск по артикулу' oninput='loadProducts()' />
<input id='rrpMin' type='number' step='0.01' placeholder='РРЦ от' oninput='loadProducts()' />
<input id='rrpMax' type='number' step='0.01' placeholder='РРЦ до' oninput='loadProducts()' />
<input id='mMin' type='number' step='0.01' placeholder='Цена Яндекс от' oninput='loadProducts()' />
<input id='mMax' type='number' step='0.01' placeholder='Цена Яндекс до' oninput='loadProducts()' />
</div>
</div>
<div class='card'>
<h3>Добавить/обновить один артикул</h3>
<div class='actions'>
<input id='newCode' placeholder='Артикул' />
<input id='newRrp' type='number' step='0.01' placeholder='РРЦ' />
<input id='newMin' type='number' step='0.01' placeholder='Мин. цена (опц.)' />
<button onclick='saveOne()'>Сохранить</button>
</div>
</div>
<div class='card'>
<table>
<thead><tr><th>Артикул</th><th>РРЦ</th><th>Цена Яндекс сейчас</th><th>Обновлено</th><th>Действия</th></tr></thead>
<tbody id='rows'></tbody>
</table>
</div>
</div>
<script>
async function api(url, options={}){const r=await fetch(url,options);if(!r.ok){throw new Error(await r.text())};return r.headers.get('content-type')?.includes('application/json')?r.json():r.text()}
function setStatus(t){document.getElementById('status').textContent=t}
function qs(){
 const p=new URLSearchParams();
 const map=[['q','query'],['rrpMin','rrp_min'],['rrpMax','rrp_max'],['mMin','market_min'],['mMax','market_max']];
 for(const [id,key] of map){const v=document.getElementById(id).value;if(v)p.append(key,v)}
 return p.toString()
}
async function loadProducts(){
  const data=await api('/products?'+qs());
  const rows=document.getElementById('rows'); rows.innerHTML='';
  for(const p of data){
    const tr=document.createElement('tr');
    tr.innerHTML=`<td>${p.vendor_code}</td><td><input id='rrp-${p.vendor_code}' type='number' step='0.01' value='${p.rrp}' /></td><td>${p.market_price ?? '-'}</td><td>${new Date(p.updated_at).toLocaleString()}</td><td><button onclick="editOne('${p.vendor_code}')">Сохранить</button> <button onclick="removeOne('${p.vendor_code}')">Удалить</button></td>`;
    rows.appendChild(tr);
  }
}
async function saveOne(){
  const body={vendor_code:newCode.value,rrp:Number(newRrp.value),min_price:newMin.value?Number(newMin.value):null};
  await api('/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  setStatus('Сохранено');loadProducts();
}
async function editOne(code){
  const rrp=Number(document.getElementById('rrp-'+code).value);
  await api('/products',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vendor_code:code,rrp:rrp,min_price:null})});
  setStatus('Цена обновлена');loadProducts();
}
async function removeOne(code){await api('/products/'+code,{method:'DELETE'});setStatus('Удалено');loadProducts();}
async function syncNow(){const r=await api('/sync-now',{method:'POST'});setStatus('Отправлено в Яндекс: '+r.synced)}
async function refreshMarket(){const r=await api('/refresh-market-prices',{method:'POST'});setStatus('Обновлено цен с Яндекса: '+r.refreshed);loadProducts()}
function downloadExcel(){window.location='/products/export'}
async function uploadExcel(){
  const file=document.getElementById('excelFile').files[0];if(!file){setStatus('Выберите файл');return}
  const fd=new FormData();fd.append('file',file);
  const r=await fetch('/products/import',{method:'POST',body:fd});
  if(!r.ok){setStatus('Ошибка загрузки'); return}
  const j=await r.json();setStatus('Импортировано: '+j.inserted_or_updated);loadProducts()
}
loadProducts();
</script>
</body>
</html>
"""


@app.get('/products', response_model=list[ProductOut])
async def list_products(
    query: str = Query(default=''),
    rrp_min: Decimal | None = Query(default=None),
    rrp_max: Decimal | None = Query(default=None),
    market_min: Decimal | None = Query(default=None),
    market_max: Decimal | None = Query(default=None),
) -> list[ProductOut]:
    products = await storage.list_products()
    filtered = [
        x
        for x in products
        if _product_matches(x, query=query, rrp_min=rrp_min, rrp_max=rrp_max, market_min=market_min, market_max=market_max)
    ]
    return [_to_schema(item) for item in filtered]


@app.post('/products', response_model=ProductOut)
async def upsert_product(product: ProductIn) -> ProductOut:
    model = ProductRRP(
        vendor_code=product.vendor_code,
        rrp=product.rrp,
        min_price=product.min_price,
        updated_at=datetime.now(timezone.utc),
    )
    await storage.upsert_products([model])
    current = [x for x in await storage.list_products() if x.vendor_code == product.vendor_code][0]
    return _to_schema(current)


@app.delete('/products/{vendor_code}', status_code=204)
async def delete_product(vendor_code: str) -> None:
    deleted = await storage.delete(vendor_code)
    if not deleted:
        raise HTTPException(status_code=404, detail='Product not found')


@app.post('/products/import', response_model=ImportResult)
async def import_products_excel(file: UploadFile = File(...)) -> ImportResult:
    try:
        records = parse_products_excel(await file.read())
    except ExcelFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await storage.upsert_products(records)
    return ImportResult(inserted_or_updated=len(records))


@app.get('/products/export')
async def export_products_excel() -> StreamingResponse:
    products = await storage.list_products()
    dataframe = pd.DataFrame(
        [
            {
                'vendor_code': x.vendor_code,
                'rrp': float(x.rrp),
                'market_price': float(x.market_price) if x.market_price is not None else None,
                'min_price': float(x.min_price) if x.min_price is not None else None,
                'updated_at': x.updated_at.isoformat() if x.updated_at else None,
            }
            for x in products
        ]
    )
    return _excel_response(dataframe, 'repricer_products.xlsx')


@app.get('/products/export/yandex-api')
async def export_products_from_yandex_api() -> StreamingResponse:
    try:
        api_products = await yandex_client.export_catalog_with_prices()
    except YandexMarketConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    local_products = {item.vendor_code: item for item in await storage.list_products()}

    dataframe = pd.DataFrame(
        [
            {
                'vendor_code': item['vendor_code'],
                'name': item['name'],
                'vendor': item['vendor'],
                'category': item['category'],
                'market_sku': item['market_sku'],
                'market_price': float(item['market_price']) if item['market_price'] is not None else None,
                'currency': item['currency'],
                'market_price_updated_at': item['market_price_updated_at'],
                'rrp': float(local_products[item['vendor_code']].rrp) if item['vendor_code'] in local_products else None,
                'min_price': float(local_products[item['vendor_code']].min_price)
                if item['vendor_code'] in local_products and local_products[item['vendor_code']].min_price is not None
                else None,
                'local_updated_at': local_products[item['vendor_code']].updated_at.isoformat()
                if item['vendor_code'] in local_products and local_products[item['vendor_code']].updated_at is not None
                else None,
            }
            for item in api_products
        ]
    )
    return _excel_response(dataframe, 'yandex_market_api_products.xlsx')


@app.post('/sync-now')
async def sync_now() -> dict:
    try:
        synced = await repricer.sync_once()
    except YandexMarketConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'synced': synced}


@app.post('/refresh-market-prices')
async def refresh_market_prices() -> dict:
    try:
        refreshed = await repricer.refresh_market_prices()
    except YandexMarketConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'refreshed': refreshed}
