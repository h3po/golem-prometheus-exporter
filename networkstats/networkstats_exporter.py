from typing import Counter
import prometheus_client
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
import requests

labels = {
    "node_id": lambda p: p["node_id"],
    #"info_url": lambda p: f"https://stats.golem.network/node/{p['node_id']}"
}
def labelgetter(provider):
    return (f(provider) for f in labels.values())

class GolemGauge(GaugeMetricFamily):

    def __init__(self, name, unit=""):
        super().__init__(f"golem_provider_{name}", name, labels=labels.keys(), unit=unit)

class GolemCounter(CounterMetricFamily):

    def __init__(self, name, unit=""):
        super().__init__(f"golem_provider_{name}", name, labels=labels.keys(), unit=unit)

class GolemOnlineCollector(object):
 
    def collect(self):
        providers = requests.get('https://api.stats.golem.network/v1/network/online').json()

        online = GolemGauge("online", unit="bool")
        earnings_total = GolemCounter("earnings_total", unit="GLM")
        mem_bytes = GolemGauge("mem", unit="bytes")
        cpu_threads = GolemGauge("cpu_threads")
        storage_bytes = GolemGauge("storage", unit="bytes")
        price_start = GolemGauge("price_start", unit="GLM")
        price_per_second = GolemGauge("price_per_second", unit="GLM")
        price_per_cpu_second = GolemGauge("price_per_cpu_second", unit="GLM")

        for provider in providers:
            provider.update(provider["data"])

            online.add_metric(labelgetter(provider), provider["online"])
            earnings_total.add_metric(labelgetter(provider), provider["earnings_total"])
            mem_bytes.add_metric(labelgetter(provider), provider["golem.inf.mem.gib"] * 1024 * 1024 * 1024)
            cpu_threads.add_metric(labelgetter(provider), provider["golem.inf.cpu.threads"])
            storage_bytes.add_metric(labelgetter(provider), provider["golem.inf.storage.gib"] * 1024 * 1024 * 1024)
            price_start.add_metric(labelgetter(provider), provider["golem.com.pricing.model.linear.coeffs"][0])
            price_per_second.add_metric(labelgetter(provider), provider["golem.com.pricing.model.linear.coeffs"][1])
            price_per_cpu_second.add_metric(labelgetter(provider), provider["golem.com.pricing.model.linear.coeffs"][2])

        yield online
        yield earnings_total
        yield mem_bytes
        yield cpu_threads
        yield storage_bytes
        yield price_start
        yield price_per_second
        yield price_per_cpu_second

if __name__ == '__main__':
    from prometheus_client import start_http_server
    from prometheus_client.core import REGISTRY
    from time import sleep
    
    REGISTRY.register(GolemOnlineCollector())
    start_http_server(1234)
    while True:
        sleep(1)