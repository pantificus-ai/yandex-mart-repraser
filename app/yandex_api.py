from decimal import Decimal

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
        timeout: float = 20.0,
    ):
        self._business_id = business_id
        self._campaign_id = campaign_id
        self._price_update_path = price_update_path
        self._offer_info_path = offer_info_path
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

    async def get_market_prices(self, vendor_codes: list[str]) -> dict[str, Decimal | None]:
        if not vendor_codes:
            return {}
        path = self._offer_info_path.format(business_id=self._business_id)
        response = await self._client.post(path, json={'offerIds': vendor_codes, 'campaignId': self._campaign_id})
        response.raise_for_status()
        data = response.json()

        result: dict[str, Decimal | None] = {}
        for offer in data.get('offers', []):
            offer_id = offer.get('offerId')
            value = (
                offer.get('price', {}).get('value')
                or offer.get('basicPrice', {}).get('value')
                or offer.get('buyerPrice', {}).get('value')
            )
            result[offer_id] = Decimal(str(value)) if value is not None else None
        return result
