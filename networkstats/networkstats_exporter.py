from prometheus_client import Gauge
from prometheus_client.core import GaugeMetricFamily, Summary
import requests
import cachetools
import os
import time

class GolemCollectorBase(object):

    api_requests = Summary("golem_api_request_seconds", "time spent requesting golem api data", labelnames=("api",))
    api_response_size = Summary("golem_api_response_size_bytes", "size of the golem api data returned", labelnames=("api",))
    ttlcache = cachetools.TTLCache(1e6, int(os.getenv("GLM_CACHE_TTL", 30)))

    def __init__(self, api_url):
        self.api_url = api_url

    @cachetools.cached(ttlcache)
    def _request(self):
        with self.api_requests.labels(self.api_url).time():
            r = requests.get(self.api_url)
            self.api_response_size.labels(self.api_url).observe(len(r.content))
            return (r.json(), time.time())

class GolemOnlineCollector(GolemCollectorBase):

    class GolemGauge(GaugeMetricFamily):
        common_labelmap = {
            "node_id": lambda p: p["node_id"],
            "subnet": lambda p: p["golem.node.debug.subnet"],
            "runtime": lambda p: p["golem.runtime.name"]
        }

        def _labelgetter(self, provider, labelmap=common_labelmap):
            return (f(provider) for f in labelmap.values())

        def __init__(self, name, unit="", extra_labels=None):
            self.labelmap = self.common_labelmap.copy()
            if extra_labels: self.labelmap.update(extra_labels)
            super().__init__(f"golem_provider_{name}", name, labels=self.labelmap.keys(), unit=unit)

        def try_add_metric(self, provider, key, timestamp, subkey=None, multiplier=None):
            if key in provider:
                value = provider[key]
                if subkey is not None: value = value[subkey]
                if value is None: value = 0
                if multiplier: value *= multiplier
                self.add_metric(self._labelgetter(provider, self.labelmap), value, timestamp)

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/online")

    def collect(self):
        providers, timestamp = self._request()

        online = self.GolemGauge("online", unit="bool")
        earnings_total = self.GolemGauge("earnings_total", extra_labels={"currency": lambda p: "GLM",})
        mem_bytes = self.GolemGauge("mem", unit="bytes")
        cpu_threads = self.GolemGauge("cpu_threads", extra_labels={
            "cpu_vendor": lambda p: p.get("golem.inf.cpu.vendor", "unknown"),
            "cpu_architecture": lambda p: p["golem.inf.cpu.architecture"]})
        storage_bytes = self.GolemGauge("storage", unit="bytes")
        price_start = self.GolemGauge("price_start", extra_labels={"currency": lambda p: "GLM",})
        price_per_second = self.GolemGauge("price_per_second", extra_labels={"currency": lambda p: "GLM",})
        price_per_cpu_second = self.GolemGauge("price_per_cpu_second", extra_labels={"currency": lambda p: "GLM",})

        for provider in providers:
            provider.update(provider["data"])

            online.try_add_metric(provider, "online", timestamp)
            earnings_total.try_add_metric(provider, "earnings_total", timestamp)
            mem_bytes.try_add_metric(provider, "golem.inf.mem.gib", timestamp, multiplier=1024*1024*1024)
            cpu_threads.try_add_metric(provider, "golem.inf.cpu.threads", timestamp)
            storage_bytes.try_add_metric(provider, "golem.inf.storage.gib", timestamp, multiplier=1024*1024*1024)

            #so far all providers are "linear":
            #wget https://api.stats.golem.network/v1/network/online -qO- | jq '.[].data."golem.com.pricing.model"' | sort | uniq
            if provider["golem.com.pricing.model"] == "linear":
                price_start.try_add_metric(provider, "golem.com.pricing.model.linear.coeffs", timestamp, subkey=0)
                price_per_second.try_add_metric(provider, "golem.com.pricing.model.linear.coeffs", timestamp, subkey=1)
                price_per_cpu_second.try_add_metric(provider, "golem.com.pricing.model.linear.coeffs", timestamp, subkey=2)

        yield online
        yield earnings_total
        yield mem_bytes
        yield cpu_threads
        yield storage_bytes
        yield price_start
        yield price_per_second
        yield price_per_cpu_second

class GolemUtilizationCollector(GolemCollectorBase):

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/utilization")

    def collect(self):
        utilization, timestamp = self._request()
        latest = utilization["data"]["result"][0]["values"][-1]
        computing = GaugeMetricFamily("golem_providers_computing_count", "golem_providers_computing_count")
        computing.add_metric([], float(latest[1]), latest[0])

        yield computing

if __name__ == '__main__':
    from prometheus_client import start_http_server
    from prometheus_client.core import REGISTRY
    from time import sleep
    import signal

    REGISTRY.register(GolemOnlineCollector())
    REGISTRY.register(GolemUtilizationCollector())
    start_http_server(1234)

    run = True
    def signal_handler(signal, frame):
        global run
        run = False

    signal.signal(signal.SIGTERM, signal_handler)

    while run:
        sleep(1)
