FROM python:alpine

RUN \
    pip install --no-cache-dir prometheus-client requests cachetools

COPY ./coinmarketcap_exporter.py /app/

ENTRYPOINT ["python", "/app/coinmarketcap_exporter.py"]    
