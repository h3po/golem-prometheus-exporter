from prometheus_client.core import GaugeMetricFamily, Summary, StateSetMetricFamily
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

common_labelmap = {
    "node_id": lambda p: p["node_id"],
    "subnet": lambda p: p["golem.node.debug.subnet"]
}

def labelgetter(provider, labelmap):
    return (f(provider) for f in labelmap.values())

class GolemOnlineGauge(GaugeMetricFamily):

    def __init__(self, name, unit="", extra_labels=None):
        self.labelmap = common_labelmap.copy()
        if extra_labels: self.labelmap.update(extra_labels)
        super().__init__(f"golem_provider_{name}", name, labels=self.labelmap.keys(), unit=unit)

    def try_add_metric(self, provider, key, timestamp, subkey=None, multiplier=None):
        if key in provider:
            value = provider[key]
            if subkey is not None: value = value[subkey]
            if value is None: value = 0
            if multiplier: value *= multiplier
            self.add_metric(labelgetter(provider, self.labelmap), value, timestamp)

class GolemOnlineCollector(GolemCollectorBase):

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/online")

    def collect(self):
        providers, timestamp = self._request()

        online = GolemOnlineGauge("online", unit="bool")
        earnings_total = GolemOnlineGauge("earnings_total", extra_labels={"currency": lambda p: "GLM",})
        mem_bytes = GolemOnlineGauge("mem", unit="bytes")
        cpu_threads = GolemOnlineGauge("cpu_threads", extra_labels={
            #"cpu_vendor": lambda p: p.get("golem.inf.cpu.vendor", "unknown"),
            "cpu_architecture": lambda p: p["golem.inf.cpu.architecture"]})
        storage_bytes = GolemOnlineGauge("storage", unit="bytes")
        price_start = GolemOnlineGauge("price_start", extra_labels={"currency": lambda p: "GLM",})
        price_per_second = GolemOnlineGauge("price_per_second", extra_labels={"currency": lambda p: "GLM",})
        price_per_cpu_second = GolemOnlineGauge("price_per_cpu_second", extra_labels={"currency": lambda p: "GLM",})

        runtime = StateSetMetricFamily("golem_provider_runtime", "golem_provider_runtime", labels=list(common_labelmap.keys())+["runtime"])
        version = StateSetMetricFamily("golem_provider_version", "golem_provider_version", labels=list(common_labelmap.keys())+["version"])

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

            runtime.add_metric(labelgetter(provider, common_labelmap), {"vm": provider["golem.runtime.name"] == "vm"}, timestamp)
            runtime.add_metric(labelgetter(provider, common_labelmap), {"wasmtime": provider["golem.runtime.name"] == "wasmtime"}, timestamp)
            version.add_metric(labelgetter(provider, common_labelmap), {provider["version"]: 1}, timestamp)

        yield online
        yield earnings_total
        yield mem_bytes
        yield cpu_threads
        yield storage_bytes
        yield price_start
        yield price_per_second
        yield price_per_cpu_second
        yield runtime
        yield version

class GolemUtilizationCollector(GolemCollectorBase):

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/utilization")

    def collect(self):
        utilization, timestamp = self._request()
        latest = utilization["data"]["result"][0]["values"][-1]
        computing = GaugeMetricFamily("golem_providers_computing_count", "golem_providers_computing_count")
        computing.add_metric((), float(latest[1]), latest[0])

        yield computing

class GolemInvoicesCollectorBase(GolemCollectorBase):

    def __init__(self, api_url, metricname):
        self.metricname = metricname
        super().__init__(api_url)

    def collect(self):
        data, timestamp = self._request()
        computing = GaugeMetricFamily(self.metricname, self.metricname)
        computing.add_metric((), list(data.values())[0] / 100, timestamp)

        yield computing

class GolemInvoicesPaidCollector(GolemInvoicesCollectorBase):

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/market/invoice/paid/1h", "golem_invoices_paid_ratio_1h")

class GolemInvoicesAcceptedCollector(GolemInvoicesCollectorBase):

    def __init__(self):
        super().__init__("https://api.stats.golem.network/v1/network/market/provider/invoice/accepted/1h", "golem_invoices_accepted_ratio_1h")

if __name__ == '__main__':
    from prometheus_client import start_http_server
    from prometheus_client.core import REGISTRY
    from time import sleep
    import signal

    REGISTRY.register(GolemOnlineCollector())
    REGISTRY.register(GolemUtilizationCollector())
    REGISTRY.register(GolemInvoicesPaidCollector())
    REGISTRY.register(GolemInvoicesAcceptedCollector())
    start_http_server(1234)

    run = True
    def signal_handler(signal, frame):
        global run
        run = False

    signal.signal(signal.SIGTERM, signal_handler)

    while run:
        sleep(1)
