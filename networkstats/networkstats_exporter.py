from typing import Counter
import prometheus_client
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily
import requests
from itertools import chain

common_labelmap = {
    "node_id": lambda p: p["node_id"],
    "subnet": lambda p: p["golem.node.debug.subnet"],
    "runtime": lambda p: p["golem.runtime.name"]
    #"info_url": lambda p: f"https://stats.golem.network/node/{p['node_id']}"
}
def labelgetter(provider, labelmap=common_labelmap):
    return (f(provider) for f in labelmap.values())

class GolemGauge(GaugeMetricFamily):

    def __init__(self, name, unit="", extra_labels=None):
        self.labelmap = common_labelmap.copy()
        if extra_labels: self.labelmap.update(extra_labels)
        super().__init__(f"golem_provider_{name}", name, labels=self.labelmap.keys(), unit=unit)

class GolemCounter(CounterMetricFamily):

    def __init__(self, name, unit="", extra_labels=None):
        self.labelmap = common_labelmap.copy()
        if extra_labels: self.labelmap.update(extra_labels)
        super().__init__(f"golem_provider_{name}", name, labels=self.labelmap.keys(), unit=unit)

def try_add_metric(metric, provider, key, subkey=None, multiplier=None):
    if key in provider:
        value = provider[key]
        if subkey is not None: value = value[subkey]
        if value is None: value = 0
        if multiplier: value *= multiplier
        metric.add_metric(labelgetter(provider, metric.labelmap), value)

class GolemOnlineCollector(object):
 
    def collect(self):
        providers = requests.get('https://api.stats.golem.network/v1/network/online').json()

        online = GolemGauge("online", unit="bool")
        earnings_total = GolemCounter("earnings_total", unit="GLM")
        mem_bytes = GolemGauge("mem", unit="bytes")
        cpu_threads = GolemGauge("cpu_threads", extra_labels={
            "cpu_vendor": lambda p: p["golem.inf.cpu.vendor"],
            "cpu_vendor": lambda p: p["golem.inf.cpu.architecture"]})
        storage_bytes = GolemGauge("storage", unit="bytes")
        price_start = GolemGauge("price_start", unit="GLM")
        price_per_second = GolemGauge("price_per_second", unit="GLM")
        price_per_cpu_second = GolemGauge("price_per_cpu_second", unit="GLM")

        for provider in providers:
            provider.update(provider["data"])

            try_add_metric(online, provider, "online")
            try_add_metric(earnings_total, provider, "earnings_total")
            try_add_metric(mem_bytes, provider, "golem.inf.mem.gib", multiplier=1024*1024*1024)
            try_add_metric(cpu_threads, provider, "golem.inf.cpu.threads")
            try_add_metric(storage_bytes, provider, "golem.inf.storage.gib", multiplier=1024*1024*1024)

            #so far all providers are "linear":
            #wget https://api.stats.golem.network/v1/network/online -qO- | jq '.[].data."golem.com.pricing.model"' | sort | uniq
            if provider["golem.com.pricing.model"] == "linear":
                try_add_metric(price_start, provider, "golem.com.pricing.model.linear.coeffs", subkey=0)
                try_add_metric(price_per_second, provider, "golem.com.pricing.model.linear.coeffs", subkey=1)
                try_add_metric(price_per_cpu_second, provider, "golem.com.pricing.model.linear.coeffs", subkey=2)

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
