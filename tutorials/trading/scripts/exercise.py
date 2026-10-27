#!/usr/bin/env python3
# Copyright 2026 The Drasi Authors.
# Licensed under the Apache License, Version 2.0.
"""Observe initial and live query chaining using this tutorial's disposable Trading run."""

import argparse
import json
import math
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

from demo import INSTANCE, STATE, command, request, runtime_ready, wait_for


ALERT = {
    "id": "tutorial-price-alerts", "queryLanguage": "Cypher",
    "query": "MATCH (p:Result) WHERE p.price > 200 RETURN p.symbol AS symbol, p.price AS price",
    "inputs": ["price-ticker-query"], "result": {"label": "PriceAlert"}, "autoStart": True,
}
COUNT = {
    "id": "tutorial-price-alert-count", "queryLanguage": "Cypher",
    "query": "MATCH (p:PriceAlert) RETURN count(p) AS alertCount",
    "inputs": [ALERT["id"]], "result": {"label": "PriceAlertCount"}, "autoStart": True,
}


def owned_run(work):
    work = work.resolve()
    if work.parent != STATE.resolve() or not work.name.startswith("run-"):
        raise ValueError("Use a run directory created by this tutorial's demo.py")
    record = json.loads((work / "endpoints.json").read_text())
    if record["instance"] != INSTANCE or record["random_prices"]:
        raise ValueError("Start a fresh tutorial run with --no-prices first")
    if any(urlparse(url).scheme != "http" or urlparse(url).hostname != "127.0.0.1"
           for url in record["urls"].values()):
        raise ValueError("This exercise only modifies the loopback tutorial services")
    label = command(["podman", "inspect", "--format",
                     '{{index .Config.Labels "drasi.tutorial.trading"}}', record["container"]])
    if label != work.name:
        raise ValueError("The recorded database no longer belongs to this tutorial run")
    return record


def exercise(work):
    record = owned_run(work)
    urls = record["urls"]
    api = urls["server"] + f"/api/v1/instances/{INSTANCE}"
    if not runtime_ready(request(api + "/runtime")):
        raise RuntimeError("The expected local ComputationGraph is not running")
    seed = next(item for item in request(urls["api"] + "/api/initial-prices")["items"]
                if item["properties"]["symbol"] == "AAPL")
    created = []
    added_watchlist = False
    changed_price = False
    observations = {}

    def rows(query):
        body = request(api + f"/queries/{query}/results")
        if body.get("success") is not True or not isinstance(body.get("data"), list):
            raise RuntimeError(f"Invalid snapshot for {query}")
        return body["data"]

    def price(properties):
        body = request(urls["source"] + "/sources/price-feed/events", {
            "operation": "update", "timestamp": time.time_ns(),
            "element": {"type": "node", "id": seed["id"], "labels": ["stock_prices"],
                        "properties": properties},
        })
        if body.get("success") is not True:
            raise RuntimeError(f"Price source rejected the demo change: {body}")

    def has_apple(query, expected):
        return any(row.get("symbol") == "AAPL" and row.get("price") == expected for row in rows(query))

    try:
        baseline = [row for row in rows("price-ticker-query") if row["price"] > 200]
        if not any(row["symbol"] == "AAPL" for row in rows("watchlist-query")):
            body = request(urls["api"] + "/api/watchlist", {"symbol": "AAPL"})
            if body.get("success") is not True:
                raise RuntimeError(f"Could not add the exercise watchlist entry: {body}")
            added_watchlist = True
            wait_for("temporary AAPL watchlist entry through real PostgreSQL CDC",
                     lambda: has_apple("watchlist-query", seed["properties"]["price"]))
        positions = rows("portfolio-query")
        summaries = rows("portfolio-summary-query")
        if len(summaries) != 1:
            raise RuntimeError("Expected one current portfolio summary before the exercise")
        summary = summaries[0]
        apple_positions = [row for row in positions if row["symbol"] == "AAPL"]
        if not apple_positions:
            raise RuntimeError("Use the original seeded portfolio, which includes AAPL")
        apple_quantity = sum(row["quantity"] for row in apple_positions)

        def original_views_match(value):
            current_positions = rows("portfolio-query")
            current_summaries = rows("portfolio-summary-query")
            apple = [row for row in current_positions if row["symbol"] == "AAPL"]
            expected_value = summary["totalValue"] + (value - seed["properties"]["price"]) * apple_quantity
            gainers = {row["symbol"] for row in rows("top-gainers-query")}
            losers = {row["symbol"] for row in rows("top-losers-query")}
            return (len(current_positions) == len(positions) and len(apple) == len(apple_positions)
                    and all(row["currentPrice"] == value
                            and math.isclose(row["currentValue"], value * row["quantity"]) for row in apple)
                    and len(current_summaries) == 1
                    and math.isclose(current_summaries[0]["totalValue"], expected_value)
                    and math.isclose(current_summaries[0]["totalCost"], summary["totalCost"])
                    and math.isclose(current_summaries[0]["totalProfitLoss"], expected_value - summary["totalCost"])
                    and has_apple("watchlist-query", value)
                    and ("AAPL" in gainers) == (value > seed["properties"]["previous_close"])
                    and ("AAPL" in losers) == (value < seed["properties"]["previous_close"]))

        if not original_views_match(seed["properties"]["price"]):
            raise RuntimeError("The original views are not at their seed values; start a fresh --no-prices run")
        for definition in (ALERT, COUNT):
            body = request(api + "/queries", definition)
            if body.get("success") is not True:
                raise RuntimeError(f"Query creation failed: {body}")
            created.append(definition["id"])
            wait_for(definition["id"], lambda: request(api + f"/queries/{definition['id']}")["data"]["status"] == "Running")
        expected = sorted((row["symbol"], row["price"]) for row in baseline)
        wait_for("downstream snapshot without new price events",
                 lambda: sorted((row["symbol"], row["price"]) for row in rows(ALERT["id"])) == expected
                 and rows(COUNT["id"]) == [{"alertCount": len(baseline)}])
        observations["initial"] = {"alerts": rows(ALERT["id"]), "count": rows(COUNT["id"])}
        for value, count in [(210.0, len(baseline) + 1), (170.0, len(baseline))]:
            changed_price = True
            price({**seed["properties"], "price": value})
            wait_for(f"AAPL {value}: original dashboard calculations plus both downstream queries",
                     lambda: has_apple("price-ticker-query", value)
                     and original_views_match(value)
                     and (has_apple(ALERT["id"], value) if value > 200
                          else not any(row["symbol"] == "AAPL" for row in rows(ALERT["id"])))
                     and rows(COUNT["id"]) == [{"alertCount": count}])
            observations[str(value)] = {
                "alerts": rows(ALERT["id"]), "count": rows(COUNT["id"]),
                "watchlist": rows("watchlist-query"), "portfolio": rows("portfolio-query"),
                "summary": rows("portfolio-summary-query"),
            }
            print("Observe the dashboard price, positions and market movers.", flush=True)
            time.sleep(3)
        price(seed["properties"])
        wait_for("restored AAPL seed price", lambda: has_apple("price-ticker-query", seed["properties"]["price"])
                 and original_views_match(seed["properties"]["price"])
                 and rows(COUNT["id"]) == [{"alertCount": len(baseline)}])
        changed_price = False
        observations["restored"] = {"alerts": rows(ALERT["id"]), "count": rows(COUNT["id"])}
        (work / "chaining.json").write_text(json.dumps(observations, indent=2) + "\n")
    finally:
        errors = []
        if changed_price:
            try:
                price(seed["properties"])
            except (OSError, ValueError, RuntimeError) as error:
                errors.append(error)
        for query in reversed(created):
            try:
                body = request(api + f"/queries/{query}", method="DELETE")
                if body.get("success") is not True:
                    raise RuntimeError(f"Failed to remove owned exercise query {query}: {body}")
            except (OSError, ValueError, RuntimeError) as error:
                errors.append(error)
        if added_watchlist:
            try:
                body = request(urls["api"] + "/api/watchlist/AAPL", method="DELETE")
                if body.get("success") is not True:
                    raise RuntimeError(f"Failed to remove the exercise watchlist entry: {body}")
                wait_for("original watchlist restored through CDC",
                         lambda: not any(row["symbol"] == "AAPL" for row in rows("watchlist-query")))
            except (OSError, ValueError, RuntimeError) as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Trading exercise cleanup failed", errors)
    print(f"Snapshot/live chaining verified; seed restored and exercise queries removed: {work / 'chaining.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    arguments = parser.parse_args()
    try:
        exercise(arguments.run_directory.resolve())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Trading exercise failed: {error}", file=sys.stderr)
        sys.exit(1)
