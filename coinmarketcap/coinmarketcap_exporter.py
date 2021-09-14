#inspired by https://github.com/bonovoxly/coinmarketcap-exporter/blob/master/coinmarketcap.py

from prometheus_client.core import GaugeMetricFamily, Summary
import requests
import time
import cachetools
import os

ttlcache = cachetools.TTLCache(10000, int(os.getenv("CMC_CACHE_TTL", 300)))
api_requests = Summary("coinmarketcap_api_request_seconds", "time spent requesting coinmarketcap api data")
api_response_size = Summary("coinmarketcap_api_response_size_bytes", "size of the coinmarketcap api data returned")

class CoinmarketcapCollector(object):

    def __init__(self, apikey, coins, currencies):
        self.headers = {"Accepts": "application/json", "X-CMC_PRO_API_KEY": apikey}
        self.params = {"symbol": coins, "convert": currencies}

    @cachetools.cached(ttlcache)
    @api_requests.time()
    def __request(self):
        session = requests.Session()
        session.headers.update(self.headers)
        r = session.get('https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest', params=self.params)
        api_response_size.observe(len(r.content))
        data = r.json()
        assert "data" in data, data
        assert data["status"]["error_code"] == 0, data
        return (data["data"], time.time())

    def collect(self):
        coinmarketcap_rank = GaugeMetricFamily("coinmarketcap_rank", "", labels=("fromcurrency",))
        coinmarketcap_pairs = GaugeMetricFamily("coinmarketcap_pairs", "", labels=("fromcurrency",))
        coinmarketcap_price = GaugeMetricFamily("coinmarketcap_price", "", labels=("fromcurrency", "currency"))
        coinmarketcap_volume_24h = GaugeMetricFamily("coinmarketcap_volume_24h", "", labels=("fromcurrency", "currency"))
        coinmarketcap_marketcap = GaugeMetricFamily("coinmarketcap_marketcap", "", labels=("fromcurrency", "currency"))
        coinmarketcap_dominance = GaugeMetricFamily("coinmarketcap_dominance", "", labels=("fromcurrency", "currency"))

        req, timestamp = self.__request()

        for fromcurrency, data in req.items():

            coinmarketcap_rank.add_metric((fromcurrency,), data["cmc_rank"], timestamp)
            coinmarketcap_pairs.add_metric((fromcurrency,), data["num_market_pairs"], timestamp)
            
            for currency, quote in data["quote"].items():
                coinmarketcap_price.add_metric((fromcurrency, currency), quote["price"], timestamp)
                coinmarketcap_volume_24h.add_metric((fromcurrency, currency), quote["volume_24h"], timestamp)
                coinmarketcap_marketcap.add_metric((fromcurrency, currency), quote["market_cap"], timestamp)
                coinmarketcap_dominance.add_metric((fromcurrency, currency), quote["market_cap_dominance"], timestamp)

        yield coinmarketcap_rank
        yield coinmarketcap_pairs
        yield coinmarketcap_price
        yield coinmarketcap_volume_24h
        yield coinmarketcap_marketcap
        yield coinmarketcap_dominance

if __name__ == '__main__':
    from prometheus_client import start_http_server
    from prometheus_client.core import REGISTRY
    from time import sleep
    import signal

    assert (apikey := os.getenv("CMC_API_KEY")), "CMC_API_KEY env var not set"
    assert (symbols := os.getenv("CMC_SYMBOLS")), "CMC_SYMBOLS env var not set"
    assert (currencies := os.getenv("CMC_CURRENCIES")), "CMC_CURRENCIES env var not set"

    REGISTRY.register(CoinmarketcapCollector(apikey, symbols, currencies))
    start_http_server(9101)

    run = True
    def signal_handler(signal, frame):
        global run
        run = False

    signal.signal(signal.SIGTERM, signal_handler)

    while run:
        sleep(1)
