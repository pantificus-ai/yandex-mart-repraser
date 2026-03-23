from decimal import Decimal
from typing import Any

import httpx


class YandexMarketClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        business_id: int,
        campaign_id: int,
        price_update_path: str,
        offer_info_path: str,
        offer_prices_path: str,
        timeout: float = 20.0,
    ):
        self._business_id = business_id
        self._campaign_id = campaign_id
        self._price_update_path = price_update_path
        self._offer_info_path = offer_info_path
        self._offer_prices_path = offer_prices_path
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def update_prices(self, items: list[dict]) -> None:
        path = self._price_update_path.format(business_id=self._business_id)
        payload = {
            'offers': [
                {
                    'offerId': item['vendor_code'],
                    'price': {'value': str(Decimal(item['rrp']))},
                }
                for item in items
            ],
            'campaignId': self._campaign_id,
        }
        response = await self._client.post(path, json=payload)
        response.raise_for_status()

    async def get_market_prices(self, vendor_codes: list[str]) -> dict[str, dict[str, Decimal | str | None]]:
        if not vendor_codes:
            return {}

        result = await self._post_offer_prices(
            body={'offerIds': vendor_codes},
            params={'limit': min(len(vendor_codes), 500)},
        )

        prices: dict[str, dict[str, Decimal | str | None]] = {}
        for offer in result.get('offers', []):
            prices[offer.get('offerId')] = self._extract_price_data(offer)
        return prices

    async def export_catalog_with_prices(self) -> list[dict[str, Any]]:
        mappings = await self._fetch_all_offer_mappings()
        prices = await self._fetch_all_offer_prices()

        merged: list[dict[str, Any]] = []
        for offer_id, mapping in mappings.items():
            price_data = prices.get(offer_id, {})
            offer = mapping.get('offer', {})
            merged.append(
                {
                    'vendor_code': offer_id,
                    'name': offer.get('name'),
                    'vendor': offer.get('vendor'),
                    'category': offer.get('category'),
                    'archived': mapping.get('mapping', {}).get('archived'),
                    'market_sku': mapping.get('mapping', {}).get('marketSku'),
                    'market_price': price_data.get('market_price'),
                    'currency': price_data.get('currency'),
                    'market_price_updated_at': price_data.get('updated_at'),
                }
            )

        for offer_id, price_data in prices.items():
            if offer_id in mappings:
                continue
            merged.append(
                {
                    'vendor_code': offer_id,
                    'name': None,
                    'vendor': None,
                    'category': None,
                    'archived': None,
                    'market_sku': None,
                    'market_price': price_data.get('market_price'),
                    'currency': price_data.get('currency'),
                    'market_price_updated_at': price_data.get('updated_at'),
                }
            )

        merged.sort(key=lambda item: item['vendor_code'] or '')
        return merged

    async def _fetch_all_offer_mappings(self) -> dict[str, dict[str, Any]]:
        path = self._offer_info_path.format(business_id=self._business_id)
        page_token: str | None = None
        mappings: dict[str, dict[str, Any]] = {}

        while True:
            params = {'limit': 100}
            if page_token:
                params['pageToken'] = page_token

            response = await self._client.post(path, params=params, json={'archived': False})
            response.raise_for_status()
            result = response.json().get('result', {})

            for offer_mapping in result.get('offerMappings', []):
                offer_id = offer_mapping.get('offer', {}).get('offerId')
                if offer_id:
                    mappings[offer_id] = offer_mapping

            page_token = result.get('paging', {}).get('nextPageToken')
            if not page_token:
                break

        return mappings

    async def _fetch_all_offer_prices(self) -> dict[str, dict[str, Decimal | str | None]]:
        page_token: str | None = None
        prices: dict[str, dict[str, Decimal | str | None]] = {}

        while True:
            params = {'limit': 500}
            if page_token:
                params['pageToken'] = page_token

            result = await self._post_offer_prices(body={'archived': False}, params=params)
            for offer in result.get('offers', []):
                offer_id = offer.get('offerId')
                if offer_id:
                    prices[offer_id] = self._extract_price_data(offer)

            page_token = result.get('paging', {}).get('nextPageToken')
            if not page_token:
                break

        return prices

    async def _post_offer_prices(self, body: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self._offer_prices_path.format(business_id=self._business_id)
        response = await self._client.post(path, params=params, json=body)
        response.raise_for_status()
        return response.json().get('result', {})

    def _extract_price_data(self, offer: dict[str, Any]) -> dict[str, Decimal | str | None]:
        price = offer.get('price', {})
        value = price.get('value')
        return {
            'market_price': Decimal(str(value)) if value is not None else None,
            'currency': price.get('currencyId'),
            'updated_at': price.get('updatedAt'),
        }
