import aiohttp
import logging
import re
import json
from config.config import config

logger = logging.getLogger(__name__)

class PolymarketAPI:
    def __init__(self):
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.data_url = "https://data-api.polymarket.com"
        self.graph_url = "https://api.thegraph.com/subgraphs/name/polymarket/matic-markets-7"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    async def get_market_data(self, market_id: str):
        url = f"{self.gamma_url}/markets/{market_id}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                return None
        return None

    async def get_markets_by_url(self, link: str):
        slug_match = re.search(r'polymarket\.com/event/([^/?]+)', link)
        if not slug_match:
            return []
        
        event_slug = slug_match.group(1)
        url = f"{self.gamma_url}/events?slug={event_slug}"
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            return data[0].get('markets', [])
                        elif isinstance(data, dict):
                            return data.get('markets', [])
            except Exception:
                return []
        return []

    async def get_recent_markets(self):
        url = f"{self.gamma_url}/markets?limit=1000&active=true&closed=false&order=createdAt&ascending=false"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                return []
        return []

    async def get_recent_events(self):
        url = f"{self.gamma_url}/events?limit=1000&active=true&closed=false&order=createdAt&ascending=false"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception:
                return []
        return []

    async def get_wallet_activity(self, address: str):
        query = """
        query GetTrades($user: String!) {
            fpmmTrades(
                first: 5, 
                orderBy: creationTimestamp, 
                orderDirection: desc, 
                where: {creator: $user}
            ) {
                id
                type
                outcomeIndex
                outcomeTokensTraded
                transactionAmount
                transactionHash
                creationTimestamp
                fpmm {
                    id
                    question
                    slug
                }
            }
        }
        """
        variables = {"user": address.lower()}
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.post(
                    self.graph_url, 
                    json={'query': query, 'variables': variables}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'data' in data and 'fpmmTrades' in data['data']:
                            return data['data']['fpmmTrades']
            except Exception:
                return []
        return []

    async def get_wallet_positions(self, address: str):
        url = f"{self.data_url}/positions?user={address}&sizeThreshold=0.1&limit=20&sortBy=CURRENT_ASSET_VALUE&sortDirection=DESC"
        
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and 'data' in data:
                            return data['data']
            except Exception as e:
                logger.error(f"Error fetching positions: {e}")
        return []

    async def check_arbitrage(self):
        url = f"{self.gamma_url}/markets?active=true&closed=false&limit=100&order=volume&ascending=false"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        markets = await resp.json()
                        opportunities = []
                        for m in markets:
                            try:
                                outcomes = json.loads(m.get('outcomePrices', '[]'))
                                if len(outcomes) == 2:
                                    price_yes = float(outcomes[0])
                                    price_no = float(outcomes[1])
                                    total = price_yes + price_no
                                    if 0.5 < total < 0.985: 
                                        profit = (1.0 - total) * 100
                                        opportunities.append({
                                            "id": m.get('id'),
                                            "question": m.get('question'),
                                            "profit": profit,
                                            "profit_str": f"{profit:.2f}%",
                                            "yes": price_yes,
                                            "no": price_no,
                                            "url": f"https://polymarket.com/market/{m.get('slug')}"
                                        })
                            except:
                                continue
                        return sorted(opportunities, key=lambda x: x['profit'], reverse=True)
            except Exception:
                return []
        return []

poly_api = PolymarketAPI()