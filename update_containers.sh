#!/bin/bash

CURRENT_IMG=$(docker images --no-trunc --quiet golem-networkstats-exporter:latest)
echo "updating golem-networkstats-exporter"
NEW_IMG=$(docker build -q --pull -t golem-networkstats-exporter networkstats)

if [ $CURRENT_IMG != $NEW_IMG ]; then
    echo "image changed, restarting golem-networkstats-exporter"
    sudo systemctl restart golem-networkstats-exporter
fi

CURRENT_IMG=$(docker images --no-trunc --quiet golem-coinmarketcap-exporter:latest)
echo "updating golem-coinmarketcap-exporter"
NEW_IMG=$(docker build -q --pull -t golem-coinmarketcap-exporter coinmarketcap)

if [ $CURRENT_IMG != $NEW_IMG ]; then
    echo "image changed, restarting golem-coinmarketcap-exporter"
    sudo systemctl restart golem-coinmarketcap-exporter
fi
