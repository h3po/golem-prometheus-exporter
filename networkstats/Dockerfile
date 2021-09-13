FROM python:alpine

RUN \
    pip install --no-cache-dir prometheus-client requests

COPY ./networkstats_exporter.py /app/

ENTRYPOINT ["python", "/app/networkstats_exporter.py"]